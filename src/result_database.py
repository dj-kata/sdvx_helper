"""SDVX向けリザルトDB。リザルトの永続化・検索・集計・WebSocket配信を担当。"""
from __future__ import annotations

import bz2
import csv
import datetime
import functools
import os
import pickle
import traceback
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from src.classes import difficulty, clear_lamp, detect_mode
from src.funcs import calc_chart_id, get_chart_name, escape_for_csv, convert_lamp, convert_difficulty
from src.result import OneResult, OneBestData
from src.volforce import calc_total_vf, VF_TOP_N
from src.songinfo import SongDatabase
from src.logger import get_logger

logger = get_logger(__name__)

_PLAYLOG_PATH = Path('playlog.sdvxh')
_RIVAL_PATH   = Path('rival.sdvxh')


# ─── WebSocket配信デコレータ ────────────────────────────────────────────────

def _ws_broadcast(ws_method_name: str):
    """WebSocket配信用デコレータ。ws_server が None なら何もしない。"""
    def decorator(func):
        @functools.wraps(func)
        def wrapper(self, *args, **kwargs):
            if self.ws_server is None:
                return
            try:
                data = func(self, *args, **kwargs)
                if data is not None:
                    getattr(self.ws_server, ws_method_name)(data)
            except Exception:
                logger.error(f"{func.__name__} エラー:\n{traceback.format_exc()}")
        return wrapper
    return decorator


class ResultDatabase:
    """全リザルトを保存・検索するクラス。"""

    def __init__(self, config=None):
        self.song_database = SongDatabase()
        self.results: List[OneResult] = []

        self.config = config
        self.ws_server = None
        self.ws_loop = None
        self.ws_thread = None
        # 複数ライバル (旧形式互換): {name: [OneResult, ...]}
        self.rival_results: dict = {}
        # 新方式: RivalManager (起動後に外部から設定される)
        self.rival_manager = None

        if config is not None:
            self._init_websocket_server()

        self.load()
        self.save()

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

    # ─── 登録 ─────────────────────────────────────────────────────────────────

    def add(self, result: OneResult) -> bool:
        """リザルトを DB に追加する。

        - detect_mode.play / detect_mode.detect は登録しない
        - score / lamp がない場合は登録しない
        - 重複チェック（同じ hash）
        - detect_mode.select は DB に更新がない場合はスキップ
        - 登録前に DB から pre_best を引いて bestscore/bestexscore を補完する

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

        self.results.append(result)
        logger.info(f"result added! len:{len(self.results)} {result}")
        return True

    # ─── 永続化 ───────────────────────────────────────────────────────────────

    def load(self):
        """保存済みリザルトをロードする。"""
        try:
            with bz2.BZ2File(_PLAYLOG_PATH, 'rb') as f:
                self.results = pickle.load(f)
            logger.info(f"playlog ロード完了: {len(self.results)} 件")
        except FileNotFoundError:
            logger.info("playlog が見つかりません。新規作成します。")
        except Exception:
            logger.error(f"playlog ロード失敗:\n{traceback.format_exc()}")

    def save(self):
        """全リザルトをファイルに保存する。"""
        try:
            with bz2.BZ2File(_PLAYLOG_PATH, 'wb', compresslevel=9) as f:
                pickle.dump(self.results, f)
        except Exception:
            logger.error(f"playlog 保存失敗:\n{traceback.format_exc()}")

    def load_rivals(self):
        """ライバルデータをロードする。"""
        try:
            with bz2.BZ2File(_RIVAL_PATH, 'rb') as f:
                data = pickle.load(f)
            # 旧形式 (list) → 新形式 (dict) への移行
            if isinstance(data, list):
                self.rival_results = {'rival': data} if data else {}
            else:
                self.rival_results = data
            total = sum(len(v) for v in self.rival_results.values())
            logger.info(f"rival playlog ロード完了: {len(self.rival_results)} 人 {total} 件")
        except FileNotFoundError:
            logger.info("rival playlog が見つかりません。")
        except Exception:
            logger.error(f"rival playlog ロード失敗:\n{traceback.format_exc()}")

    def save_rivals(self):
        """ライバルデータをファイルに保存する。"""
        try:
            with bz2.BZ2File(_RIVAL_PATH, 'wb', compresslevel=9) as f:
                pickle.dump(self.rival_results, f)
        except Exception:
            logger.error(f"rival playlog 保存失敗:\n{traceback.format_exc()}")

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

        results = []
        for row in csv.DictReader(io.StringIO(text)):
            title     = row.get('title', '').strip()
            diff_str  = row.get('difficulty', '').strip()
            lv_str    = row.get('Lv', '').strip()
            score_str = row.get('score', '').strip()
            lamp_str  = row.get('lamp', '').strip()

            if not title or not score_str:
                continue

            diff = (convert_difficulty(diff_str) if diff_str else None) or difficulty.maximum
            lamp = convert_lamp(lamp_str)

            try:
                score = int(score_str)
            except ValueError:
                continue

            lv = int(lv_str) if lv_str.isdigit() else None
            if lv is None:
                info = self.song_database.get_song_info(title)
                if info:
                    lv = info.get_level(diff)

            results.append(OneResult(
                title=title,
                difficulty=diff,
                lamp=lamp,
                score=score,
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

    def get_all_best_results(self) -> Dict[Tuple[str, difficulty], OneBestData]:
        """全譜面の自己ベストを OneBestData として集計する。

        Returns:
            Dict[(title, difficulty), OneBestData]
        """
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

        data: dict = {
            'title':      title,
            'difficulty': get_chart_name(diff),
            'lv':         str(info.get_level(diff) or '') if info else '',
            'best_score': best_score or 0,
            'best_ex':    best_ex or 0,
            'best_lamp':  best_lamp.value,
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

        return data

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
        items = []
        for i, b in enumerate(ranking, 1):
            items.append({
                'rank':       i,
                'title':      b.title,
                'difficulty': get_chart_name(b.difficulty),
                'lv':         str(b.level),
                'score':      b.best_score,
                'exscore':    b.best_exscore,
                'grade':      b.grade,
                'lamp':       b.best_lamp.value,
                'vf':         b.vf,
            })
        return {'total_vf': total_vf, 'items': items}

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
