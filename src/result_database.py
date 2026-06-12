"""SDVX向けリザルトDB。リザルトの永続化・検索・集計・WebSocket配信を担当。"""
from __future__ import annotations

import bz2
import csv
import datetime
import functools
import os
import pickle
import threading
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.classes import difficulty, clear_lamp, detect_mode
from src.funcs import calc_chart_id, get_chart_name, escape_for_csv, convert_lamp, convert_difficulty
from src.result import OneResult, OneBestData
from src.volforce import calc_total_vf, calc_vf, VF_TOP_N
from src.songinfo import SongDatabase
from src.logger import get_logger
from PIL import Image
from src.database_sqlite import SQLiteDatabase

logger = get_logger(__name__)

_DB_PATH = 'sdvx_helper.db'

_PLAYLOG_PATH = Path('playlog.sdvxh')
_RIVAL_PATH   = Path('rival.sdvxh')


# ─── WebSocket配信デコレータ ────────────────────────────────────────────────

def _ws_broadcast(ws_method_name: str):
    """WebSocket配信用デコレータ。ws_server が None なら何もしない。"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            try:
                data = func(self, *args, **kwargs)
                if self.ws_server is not None and data is not None:
                    getattr(self.ws_server, ws_method_name)(data)
            except Exception:
                logger.error(f"{func.__name__} エラー:\n{traceback.format_exc()}")
        return wrapper
    return decorator


class ResultDatabase:
    """全リザルトを保存・検索するクラス。SQLite3 をバックエンドに使用。"""

    def __init__(self, config=None):
        self.song_database = SongDatabase()
        self.db = SQLiteDatabase(_DB_PATH)
        self.results: List[OneResult] = []  # メモリ上のキャッシュ
        self._bests_cache: Dict[Tuple[str, difficulty], OneBestData] = {}

        self.config = config
        self.ws_server = None
        self.ws_loop = None
        
        self.portal_manager = None  # メインウィンドウからセットされる
        self.ws_thread = None
        # 新方式: RivalManager (起動後に外部から設定される)
        self.rival_manager = None
        self.jacket_dir = Path('jackets')
        self.jacket_dir.mkdir(exist_ok=True)
        self.load()

        if config is not None:
            self._init_websocket_server()
            # 初期データ配信
            self.broadcast_stats_data()
            self.broadcast_vf_data()

    # ─── WebSocket ────────────────────────────────────────────────────────────

    def _init_websocket_server(self):
        import asyncio
        import threading
        from src.websocket_server import DataWebSocketServer

        self.ws_loop = asyncio.new_event_loop()
        self.ws_thread = threading.Thread(
            target=lambda: (asyncio.set_event_loop(self.ws_loop), self.ws_loop.run_forever()),
            daemon=True,
        )
        self.ws_thread.start()

        port = getattr(self.config, 'websocket_data_port', 8767)
        self.ws_server = DataWebSocketServer(port)
        self.ws_server.start(self.ws_loop)
        logger.info(f"WebSocketサーバー起動: ポート {port}")

    def shutdown(self):
        """サーバーを停止（アプリケーション終了時に呼び出す）。"""
        if self.ws_server:
            self.ws_server.stop()
        if self.ws_loop:
            self.ws_loop.call_soon_threadsafe(self.ws_loop.stop)
        self.db.close()
        logger.info("WebSocketサーバーを停止しました")

    # ─── WebSocket 配信 ──────────────────────────────────────────────────────

    @_ws_broadcast('update_cursong_data')
    def broadcast_cursong_data(self, title: str, diff: difficulty):
        return self.get_cursong_data(title, diff)

    @_ws_broadcast('update_today_results_data')
    def broadcast_today_results_data(self, start_time: int):
        return self.get_today_results_data(start_time)

    @_ws_broadcast('update_vf_data')
    def broadcast_vf_data(self):
        return self.get_vf_data()

    @_ws_broadcast('update_stats_data')
    def broadcast_stats_data(self):
        return self.get_stats_data()

    @_ws_broadcast('update_nowplaying_data')
    def broadcast_nowplaying_data(self, data: dict):
        return data

    # ─── 登録 ─────────────────────────────────────────────────────────────────

    def add(self, result: OneResult, commit: bool = True) -> bool:
        """リザルトを DB に追加する。

        Args:
            result: 登録するリザルト
            commit: SQLite へ即座に commit するかどうか（大量投入時は False を推奨）
        Returns:
            bool: 実際に登録された場合 True
        """
        if result.detect_mode in (detect_mode.play, detect_mode.detect, detect_mode.init):
            return False
        if result.score is None or result.lamp is None:
            logger.warning(f"result rejected (score or lamp missing): {result}")
            return False
        if result.title is None:
            logger.warning(f"result rejected (title unknown)")
            return False
        if result in self.results:
            return False

        # DB から自己ベストを補完（リザルト画面読み取りが失敗していた場合のフォールバック）
        db_score, db_exscore, db_lamp = self.get_best(chart_id=result.chart_id)
        if result.bestscore is None:
            result.bestscore = db_score
        if result.bestexscore is None:
            result.bestexscore = db_exscore

        # select からのリザルトは更新があるときのみ登録
        if result.detect_mode == detect_mode.select and db_score is not None:
            if result.score <= db_score and result.lamp.value <= db_lamp.value:
                logger.info(f"select result skipped (no update): {result}")
                return False

        # レベル情報が欠損している場合はSongDatabaseから補完
        if result.level is None:
            info = self.song_database.get_song_info(result.title)
            if info:
                result.level = info.get_level(result.difficulty)

        # SQLite へ保存
        data = {
            'title': result.title,
            'difficulty': result.difficulty.value,
            'lamp': result.lamp.value,
            'score': result.score,
            'exscore': result.exscore,
            'level': result.level,
            'timestamp': result.timestamp,
            'detect_mode': result.detect_mode.value if result.detect_mode else None,
            'bestscore': result.bestscore,
            'bestexscore': result.bestexscore
        }
        self.db.insert_personal_result(data)
        if commit:
            self.db.commit()

        # 追加した行の ID を取得してセット
        last_id = self.db.execute("SELECT last_insert_rowid()").fetchone()[0]
        result.id = last_id

        # メモリキャッシュ更新
        self.results.append(result)

        # ベストキャッシュ更新
        key = (result.title, result.difficulty)
        if key not in self._bests_cache:
            self._bests_cache[key] = OneBestData()
        self._bests_cache[key].update(result)

        logger.debug(f"result added! len:{len(self.results)} {result}")
        return True

    def delete(self, result: OneResult) -> bool:
        """リザルトを DB とメモリキャッシュから削除する。"""
        try:
            row_id = getattr(result, 'id', None)
            if row_id is not None:
                self.db.delete_personal_result(row_id)
                self.db.commit()
            
            if result in self.results:
                self.results.remove(result)
            
            # ベストキャッシュ再点検
            self._refresh_best_cache(result.title, result.difficulty)
            return True
        except Exception as e:
            logger.error(f"削除失敗: {e}")
            return False

    def _refresh_best_cache(self, title: str, diff: difficulty):
        """特定の譜面のベスト情報を再集計してキャッシュを更新する。"""
        results = self.search(title=title, diff=diff)
        target = [r for r in results
                  if r.detect_mode not in (detect_mode.play, detect_mode.detect, detect_mode.init)]
        
        key = (title, diff)
        if not target:
            self._bests_cache.pop(key, None)
            return

        best_data = OneBestData()
        for r in target:
            best_data.update(r)
        self._bests_cache[key] = best_data

    def commit(self):
        """SQLite の変更を確定する。"""
        self.db.commit()

    # ─── 永続化 ───────────────────────────────────────────────────────────────

    def load(self):
        """SQLite からリザルトをロードする。初回は playlog.sdvxh からの移行。"""
        # 1. 移行チェック
        if os.path.exists(_PLAYLOG_PATH):
            self._migrate_from_bz2pkl()

        # 2. SQLite から全ロード
        try:
            rows = self.db.get_all_personal_results()
            self.results = []
            for r in rows:
                res = OneResult(
                    title=r['title'],
                    difficulty=difficulty(r['difficulty']),
                    lamp=clear_lamp(r['lamp']),
                    score=r['score'],
                    exscore=r['exscore'],
                    level=r['level'],
                    timestamp=r['timestamp'],
                    detect_mode=detect_mode(r['detect_mode']) if r['detect_mode'] is not None else None,
                    bestscore=r['bestscore'],
                    bestexscore=r['bestexscore']
                )
                res.id = r['id']
                self.results.append(res)
            
            # ベストキャッシュの初期構築
            self._bests_cache = self.get_all_best_results(use_cache=False)
            logger.info(f"DBロード完了: {len(self.results)} 件 (ベストキャッシュ: {len(self._bests_cache)} 譜面)")
        except Exception as e:
            logger.error(f"DBロード失敗: {e}\n{traceback.format_exc()}")

    def _migrate_from_bz2pkl(self):
        """旧 playlog.sdvxh (bz2pkl) から SQLite へデータを移行する"""
        logger.info(f"旧データ形式からの移行を開始します: {_PLAYLOG_PATH}")
        try:
            with bz2.BZ2File(_PLAYLOG_PATH, 'rb') as f:
                old_results = pickle.load(f)
            
            # トランザクションで一括投入
            for res in old_results:
                data = {
                    'title': res.title,
                    'difficulty': res.difficulty.value,
                    'lamp': res.lamp.value,
                    'score': res.score,
                    'exscore': res.exscore,
                    'level': res.level,
                    'timestamp': res.timestamp,
                    'detect_mode': res.detect_mode.value if res.detect_mode else None,
                    'bestscore': res.bestscore,
                    'bestexscore': res.bestexscore
                }
                self.db.insert_personal_result(data)
            self.db.commit()
            
            # 移行済みファイルをリネーム
            backup_path = _PLAYLOG_PATH.with_suffix('.sdvxh.bak')
            if os.path.exists(backup_path):
                os.remove(backup_path)
            os.rename(_PLAYLOG_PATH, backup_path)
            logger.info(f"移行完了: {len(old_results)} 件をSQLiteへ。旧ファイルは .bak に退避しました。")
        except Exception as e:
            logger.error(f"移行失敗: {e}\n{traceback.format_exc()}")

    def save(self):
        """全リザルトを保存（SQLite化後は逐次保存のため、互換性のために維持）。"""
        pass

    def load_rivals(self):
        """以前のライバルデータロードロジックを統合 (SQLite化に伴い不要だが互換性のため維持)"""
        pass

    def save_rivals(self):
        """以前のライバルデータ保存ロジックを統合 (SQLite化に伴い不要だが互換性のため維持)"""
        pass

    def import_rival_csv(self, name: str, source: str) -> int:
        """指定ライバルのデータをCSVからインポートする（そのライバルの既存データは全て置き換え）。

        Args:
            name:   ライバル名
            source: ローカルCSVファイルパス or Google Drive URL
                    (https://drive.google.com/open?id=FILEID... 形式)

        Returns:
            int: インポートされた件数（失敗時は -1）
        """
        import io
        import re

        # CSV テキストを取得
        if source.startswith('http'):
            import requests
            # ?id=FILEID 形式または /file/d/FILEID/ 形式に対応
            m = re.search(r'[?&]id=([^&]+)', source) or re.search(r'/file/d/([^/?]+)', source)
            file_id = m.group(1) if m else None
            url = (f'https://drive.google.com/uc?export=download&id={file_id}'
                   if file_id else source)
            try:
                resp = requests.get(url, timeout=30)
                resp.raise_for_status()
                text = resp.content.decode('utf-8-sig')
            except Exception:
                logger.error(f"CSV ダウンロード失敗:\n{traceback.format_exc()}")
                return -1
        else:
            try:
                with open(source, encoding='utf-8-sig', newline='') as f:
                    text = f.read()
            except Exception:
                logger.error(f"CSV ファイル読み込み失敗:\n{traceback.format_exc()}")
                return -1

        reader = csv.DictReader(io.StringIO(text))
        fieldnames = reader.fieldnames or []
        is_arcade = '楽曲名' in fieldnames  # アーケード公式CSVか判定

        results = []
        for row in reader:
            if is_arcade:
                title     = row.get('楽曲名', '').strip()
                diff_str  = row.get('難易度', '').strip()
                lv_str    = row.get('楽曲レベル', '').strip()
                score_str = row.get('ハイスコア', '').strip()
                lamp_str  = row.get('クリアランク', '').strip()
                exscore_str = row.get('EXスコア', '').strip()
            else:
                title     = row.get('title', '').strip()
                diff_str  = row.get('difficulty', '').strip()
                lv_str    = row.get('Lv', '').strip()
                score_str = row.get('score', '').strip()
                lamp_str  = row.get('lamp', '').strip()
                exscore_str = ''

            if not title or not score_str:
                continue

            diff = (convert_difficulty(diff_str) if diff_str else None) or difficulty.maximum
            lamp = convert_lamp(lamp_str)

            try:
                score = int(score_str)
            except ValueError:
                continue

            # レベル: アーケードCSVは小数(18.1等)なので整数部を使う
            try:
                lv = int(float(lv_str)) if lv_str else None
            except ValueError:
                lv = None
            if lv is None:
                info = self.song_database.get_song_info(title)
                if info:
                    lv = info.get_level(diff)

            # EXスコア: 0は未記録扱い
            exscore = None
            try:
                ex = int(exscore_str)
                if ex > 0:
                    exscore = ex
            except (ValueError, TypeError):
                pass

            results.append(OneResult(
                title=title,
                difficulty=diff,
                lamp=lamp,
                score=score,
                exscore=exscore,
                level=lv,
                detect_mode=detect_mode.select,
            ))

        self.rival_results[name] = results
        self.save_rivals()
        logger.info(f"ライバルデータインポート完了: {name} {len(results)} 件")
        return len(results)

    def delete_rival(self, name: str):
        """指定ライバルのデータを削除する。"""
        self.rival_results.pop(name, None)
        self.save_rivals()
        logger.info(f"ライバル削除: {name}")

    def get_rival_names(self) -> list:
        """登録ライバル名一覧を返す。"""
        if self.rival_manager is not None:
            return self.rival_manager.rival_names
        return list(self.rival_results.keys())

    def get_rival_count(self, name: str) -> int:
        """指定ライバルのデータ件数を返す。"""
        return len(self.rival_results.get(name, []))

    def get_rival_best(self,
                       name: str,
                       title: str = None,
                       diff: difficulty = None,
                       chart_id: str = None,
                       ) -> Tuple[Optional[int], Optional[int], clear_lamp]:
        """指定ライバルの指定譜面の自己ベスト (score, exscore, lamp) を返す。"""
        if self.rival_manager is not None:
            diff_str = str(diff) if diff is not None else None
            if title is not None and diff_str is not None:
                entry = self.rival_manager.get_score(name, title, diff_str)
                if entry is not None:
                    return entry.score, None, entry.lamp
            return None, None, clear_lamp.noplay
        # 旧 rival_results フォールバック
        key = chart_id
        if key is None and title is not None and diff is not None:
            key = calc_chart_id(title, diff)
        if key is None:
            return None, None, clear_lamp.noplay
        target = [r for r in self.rival_results.get(name, []) if r.chart_id == key]
        if not target:
            return None, None, clear_lamp.noplay
        best_score = max((r.score for r in target if r.score is not None), default=None)
        exscores   = [r.exscore for r in target if r.exscore is not None]
        best_ex    = max(exscores) if exscores else None
        best_lamp  = max((r.lamp for r in target), default=clear_lamp.noplay)
        return best_score, best_ex, best_lamp

    # ─── 検索・集計 ───────────────────────────────────────────────────────────

    def search(self,
               title: str = None,
               diff: difficulty = None,
               chart_id: str = None,
               ) -> List[OneResult]:
        """指定譜面の全リザルトを返す（play / detect 含む）。"""
        key = chart_id
        if key is None and title is not None and diff is not None:
            key = calc_chart_id(title, diff)
        if key is None:
            return []
        return [r for r in self.results if r.chart_id == key]

    def get_best(self,
                 title: str = None,
                 diff: difficulty = None,
                 chart_id: str = None,
                 ) -> Tuple[Optional[int], Optional[int], clear_lamp]:
        """指定譜面の自己ベスト (best_score, best_exscore, best_lamp) を返す。
        未プレーの場合は (None, None, clear_lamp.noplay)。
        detect_mode.play / detect は集計対象外。
        """
        # キャッシュ（OneBestData）があればそれを使う（O(1)）
        # chart_id しかない場合はキャッシュキーが作れないため検索にフォールバック
        if title and diff:
            key = (title, diff)
            best = self._bests_cache.get(key)
            if best:
                return best.best_score, best.best_exscore, best.best_lamp

        results = self.search(title=title, diff=diff, chart_id=chart_id)
        target = [r for r in results
                  if r.detect_mode not in (detect_mode.play, detect_mode.detect, detect_mode.init)]
        if not target:
            return None, None, clear_lamp.noplay

        best_score  = max((r.score for r in target if r.score is not None), default=None)
        exscores    = [r.exscore for r in target if r.exscore is not None]
        best_ex     = max(exscores) if exscores else None
        best_lamp   = max((r.lamp for r in target), default=clear_lamp.noplay)
        return best_score, best_ex, best_lamp

    def get_all_best_results(self, use_cache: bool = True) -> Dict[Tuple[str, difficulty], OneBestData]:
        """全譜面の自己ベストを OneBestData として集計する。

        Args:
            use_cache: Trueなら事前に構築されたキャッシュを返す。
        Returns:
            Dict[(title, difficulty), OneBestData]
        """
        if use_cache:
            return self._bests_cache

        bests: Dict[Tuple[str, difficulty], OneBestData] = {}

        for result in self.results:
            if result.detect_mode in (detect_mode.play, detect_mode.detect, detect_mode.init):
                continue
            if result.title is None or result.difficulty is None:
                continue

            key = (result.title, result.difficulty)
            if key not in bests:
                bests[key] = OneBestData()

                # level を musiclist から補完（result に level がない場合）
                if result.level is None:
                    info = self.song_database.get_song_info(result.title)
                    if info:
                        result.level = info.get_level(result.difficulty)

            bests[key].update(result)

        return bests

    def get_vf_ranking(self, top_n: int = VF_TOP_N) -> List[OneBestData]:
        """VF寄与値が高い順に上位 top_n 譜面のリストを返す。"""
        bests = self.get_all_best_results()
        sorted_bests = sorted(bests.values(), key=lambda b: b.vf, reverse=True)
        return sorted_bests[:top_n]

    def get_total_vf(self) -> int:
        """総 Volforce を返す（上位 VF_TOP_N 曲の合計）。"""
        bests = self.get_all_best_results()
        return calc_total_vf([b.vf for b in bests.values()])

    def get_today_results(self, start_time: int) -> List[OneResult]:
        """start_time 以降の detect_mode.result リザルトを新しい順で返す。"""
        return [r for r in reversed(self.results)
                if r.detect_mode == detect_mode.result and r.timestamp >= start_time]

    # ─── WebSocket 用データ生成 ──────────────────────────────────────────────

    def get_cursong_data(self, title: str, diff: difficulty) -> dict:
        """現在の曲のプレー履歴をWebSocket送信用の辞書で返す。"""
        results = self.search(title=title, diff=diff)
        target  = [r for r in results if r.detect_mode == detect_mode.result]

        best_score, best_ex, best_lamp = self.get_best(title=title, diff=diff)
        info = self.song_database.get_song_info(title)
        diff_name = get_chart_name(diff)
        best_data = self.get_all_best_results().get((title, diff))
        level = info.get_level(diff) if info else (best_data.level if best_data else None)
        display_diff_name = diff_name
        grade_s_tier = ''
        puc_tier = ''
        if self.portal_manager:
            try:
                if diff == difficulty.maximum and level:
                    normalized_title = title.strip().lower()
                    for (map_title, map_lv), cdiff in self.portal_manager.get_4th_diff_map().items():
                        if map_lv == level and map_title.strip().lower() == normalized_title:
                            display_diff_name = cdiff
                            break
                tier_map = self.portal_manager.get_tier_map()
                grade_s_tier, puc_tier = tier_map.get((title, diff), ('', ''))
                if not grade_s_tier and not puc_tier:
                    normalized_title = title.strip().lower()
                    for (map_title, map_diff), tiers in tier_map.items():
                        if map_diff == diff and map_title.strip().lower() == normalized_title:
                            grade_s_tier, puc_tier = tiers
                            break
            except Exception:
                logger.debug(f"tier map取得失敗:\n{traceback.format_exc()}")
        best_vf = best_data.vf if best_data else 0
        if not best_vf and best_score and level:
            best_vf = calc_vf(level, best_score, best_lamp)

        data: dict = {
            'title':      title,
            'difficulty': diff_name,
            'display_difficulty': display_diff_name,
            'cdiff':      display_diff_name if diff == difficulty.maximum else None,
            'lv':         str(level or ''),
            'gradeS_tier': grade_s_tier,
            'S_tier':     grade_s_tier,
            'PUC_tier':   puc_tier,
            'p_tier':     puc_tier,
            'best_score': best_score or 0,
            'best_ex':    best_ex or 0,
            'best_lamp':  best_lamp.value,
            'vf':         best_vf,
            'play_count': len(target),
            'last_played': (
                datetime.datetime.fromtimestamp(target[0].timestamp).strftime('%Y/%m/%d')
                if target else ''
            ),
            'items': [],
        }

        for r in reversed(target):
            data['items'].append({
                'date':       datetime.datetime.fromtimestamp(r.timestamp).strftime('%Y/%m/%d'),
                'score':      r.score,
                'exscore':    r.exscore,
                'grade':      r.grade,
                'lamp':       r.lamp.value,
                'vf':         r.vf,
                'pre_score':  r.bestscore  or 0,
                'pre_ex':     r.bestexscore or 0,
            })

        data['rival_items'] = self.get_cursong_rival_items(title, diff_name, best_score, best_ex, best_lamp)
        return data

    def get_cursong_rival_items(
        self,
        title: str,
        diff_name: str,
        best_score: Optional[int],
        best_ex: Optional[int],
        best_lamp: clear_lamp,
    ) -> list[dict]:
        """現在曲のライバルランキングをWebSocket送信用の辞書リストで返す。"""
        rows = []
        player_name = self.config.player_name if self.config else 'ME'

        if best_score is not None:
            rows.append({
                'player': player_name or 'ME',
                'score': best_score or 0,
                'exscore': best_ex,
                'lamp': best_lamp.value if best_lamp else clear_lamp.noplay.value,
                'is_me': True,
            })

        if self.rival_manager is not None:
            try:
                rival_sources = {
                    rd.name: getattr(rd, 'source', 'csv')
                    for rd in getattr(self.rival_manager, 'rivals', [])
                }
                for name, entry in self.rival_manager.get_all_scores(title, diff_name):
                    rows.append({
                        'player': name,
                        'score': entry.score or 0,
                        'exscore': entry.exscore,
                        'lamp': entry.lamp.value if entry.lamp else clear_lamp.noplay.value,
                        'is_me': False,
                        'source': rival_sources.get(name, 'csv'),
                    })
            except Exception:
                logger.error(f"ライバル表示データ生成エラー:\n{traceback.format_exc()}")

        rows.sort(key=lambda item: (item.get('score') or 0, item.get('lamp') or 0), reverse=True)
        for idx, item in enumerate(rows, 1):
            item['rank'] = idx
            my_score = best_score or 0
            item['diff'] = (item.get('score') or 0) - my_score
        return rows

    def get_today_results_data(self, start_time: int) -> dict:
        """本日のリザルト一覧をWebSocket送信用の辞書で返す。"""
        today = self.get_today_results(start_time)
        items = []
        for r in today:
            info = self.song_database.get_song_info(r.title)
            lv = info.get_level(r.difficulty) if info else r.level
            items.append({
                'title':      r.title,
                'difficulty': get_chart_name(r.difficulty),
                'lv':         str(lv or ''),
                'score':      r.score,
                'exscore':    r.exscore,
                'grade':      r.grade,
                'lamp':       r.lamp.value,
                'vf':         r.vf,
                'pre_score':  r.bestscore   or 0,
                'pre_ex':     r.bestexscore or 0,
                'is_score_updated': r.is_score_updated(),
                'is_ex_updated':    r.is_exscore_updated(),
                'timestamp':  r.timestamp,
            })
        return {'items': items}

    def get_vf_data(self) -> dict:
        """VFランキングデータをWebSocket送信用の辞書で返す。"""
        ranking = self.get_vf_ranking()
        total_vf = calc_total_vf([b.vf for b in self.get_all_best_results().values()])
        
        # 難易度名 (INF/GRV/...) 解決用 (正規化タイトル -> Lv -> cdiff)
        norm_diff_map = {}
        if self.portal_manager:
            for (title, lv), cdiff in self.portal_manager.get_4th_diff_map().items():
                norm_diff_map[(title.strip().lower(), lv)] = cdiff
        
        from src.summary_generator import _LAMP_FILE
        
        items = []
        for i, b in enumerate(ranking, 1):
            # difficulty.maximum の場合のみ、マスタから個別名称を引く
            cdiff = None
            if b.difficulty == difficulty.maximum:
                cdiff = norm_diff_map.get((b.title.strip().lower(), b.level))
                
            items.append({
                'rank':       i,
                'chart_id':   b.chart_id,
                'title':      b.title,
                'difficulty': get_chart_name(b.difficulty),
                'cdiff':      cdiff,
                'lv':         str(b.level),
                'score':      b.best_score,
                'exscore':    b.best_exscore,
                'grade':      b.grade,
                'lamp':       b.best_lamp.value,
                'lamp_img':   _LAMP_FILE.get(b.best_lamp),
                'vf':         b.vf,
            })
        return {'total_vf': total_vf, 'items': items}

    def save_jacket_image(self, chart_id: str, image: Image.Image) -> bool:
        """指定したchart_idのジャケット画像が未保存の場合、保存する。"""
        if not chart_id or image is None:
            return False
        
        path = self.jacket_dir / f"{chart_id}.png"
        if path.exists():
            return False
        
        try:
            image.save(str(path))
            logger.info(f"ジャケット画像を保存しました: {chart_id}")
            return True
        except Exception:
            logger.error(f"ジャケット画像の保存に失敗しました: {chart_id}")
            return False

    def batch_generate_jackets(self, screen_reader):
        """保存済み画像フォルダをスキャンし、ジャケット画像を生成・保存する。"""
        if not self.config or not hasattr(self.config, 'image_save_path'):
            return
        
        import re
        from src.define import RECT_RESULT_JACKET
        from src.funcs import convert_difficulty
        
        save_path = Path(self.config.image_save_path)
        if not save_path.exists():
            return
        
        count = 0
        # ファイル名パターン: sdvx_{title}_{diff}_{score}_{ex}_{lamp}_{date}.png
        # または単に diff と title が入っていれば chart_id が作れる
        for img_path in save_path.glob("*.png"):
            basename = img_path.stem
            # アンダースコアで分割して推測を試みる
            parts = basename.split("_")
            if len(parts) < 3:
                continue
            
            # title = parts[1], diff = parts[2] (MainWindow.save_image の形式準拠)
            title = parts[1]
            diff_str = parts[2]
            diff = convert_difficulty(diff_str)
            if not diff:
                continue
            
            cid = calc_chart_id(title, diff)
            if not cid:
                continue
            
            if (self.jacket_dir / f"{cid}.png").exists():
                continue
            
            try:
                img = Image.open(img_path)
                jacket = img.crop(RECT_RESULT_JACKET)
                if self.save_jacket_image(cid, jacket):
                    count += 1
            except Exception:
                continue
        
        if count > 0:
            logger.info(f"一括ジャケット生成完了: {count}件")
        return count

    def get_stats_data(self) -> dict:
        """レベル別（14-20）の統計情報をWebSocket送信用の辞書で返す。"""
        bests = self.get_all_best_results()
        
        # 楽曲マスターからレベルごとの総譜面数をカウント
        total_charts = {lv: 0 for lv in range(14, 21)}
        for song in self.song_database._songs.values():
            for diff in difficulty:
                lv = song.get_level(diff)
                if lv and 14 <= lv <= 20:
                    total_charts[lv] += 1
        
        logger.info(f"Stats aggregate: total_charts={total_charts}")

        stats_by_lv = {}
        for lv in range(14, 21):
            # 当該レベルのベストデータを抽出
            lv_bests = [b for b in bests.values() if b.level == lv]
            
            puc = sum(1 for b in lv_bests if b.best_lamp == clear_lamp.puc)
            uc  = sum(1 for b in lv_bests if b.best_lamp == clear_lamp.uc)
            exc = sum(1 for b in lv_bests if b.best_lamp == clear_lamp.exc)
            mxx = sum(1 for b in lv_bests if b.best_lamp == clear_lamp.maxxive)
            clr = sum(1 for b in lv_bests if b.best_lamp == clear_lamp.clear)
            fld = sum(1 for b in lv_bests if b.best_lamp == clear_lamp.played)
            
            played_count = len(lv_bests)
            noplay = total_charts[lv] - played_count
            
            # ランク別
            s   = sum(1 for b in lv_bests if b.best_score >= 9900000)
            aaa_plus = sum(1 for b in lv_bests if 9800000 <= b.best_score < 9900000)
            aaa = sum(1 for b in lv_bests if 9700000 <= b.best_score < 9800000)
            
            avg = int(sum(b.best_score for b in lv_bests) / played_count) if played_count > 0 else 0
            
            stats_by_lv[lv] = {
                'lv': lv,
                'total': total_charts[lv],
                'played': played_count,
                'noplay': noplay,
                'puc': puc,
                'uc': uc,
                'exc': exc,
                'maxxive': mxx,
                'clear': clr,
                'failed': fld,
                's': s,
                'aaa_plus': aaa_plus,
                'aaa': aaa,
                'average': avg
            }

        return {
            'date': datetime.datetime.now().strftime('%Y/%m/%d %H:%M:%S'),
            'player_name': self.config.player_name if self.config else 'NONAME',
            'total_vf': f"{self.get_total_vf() / 1000:.3f}",
            'lvs': stats_by_lv
        }

    # ─── CSV 出力 ─────────────────────────────────────────────────────────────

    def write_best_csv(self, csv_path: str = None):
        """全譜面の自己ベストを CSV で出力する。"""
        header = ['LV', 'Title', 'Difficulty', 'Lamp', 'Score', 'EXScore',
                  'Grade', 'VF', 'Last Played']
        os.makedirs('out', exist_ok=True)
        output_file = Path(csv_path or 'out') / 'sdvx_score.csv'
        if csv_path:
            os.makedirs(csv_path, exist_ok=True)

        bests = self.get_all_best_results()

        with open(output_file, 'w', encoding='utf-8-sig', newline='') as f:
            writer = csv.writer(f)
            writer.writerow(header)
            for (title, diff), best in sorted(
                bests.items(), key=lambda kv: (-kv[1].vf, kv[0][0])
            ):
                writer.writerow([
                    best.level,
                    escape_for_csv(title),
                    get_chart_name(diff),
                    str(best.best_lamp),
                    best.best_score,
                    best.best_exscore if best.best_exscore is not None else '',
                    best.grade,
                    best.vf,
                    best.last_play_date,
                ])
        logger.info(f"CSV 出力完了: {output_file}")

    # ─── ユーティリティ ──────────────────────────────────────────────────────

    def __len__(self) -> int:
        return len(self.results)

    def __str__(self) -> str:
        lines = []
        for r in self.results:
            lines.append(str(r))
        return '\n'.join(lines)
