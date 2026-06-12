"""SDVX ライバルスコアデータの取得・管理モジュール

sdvx_helper の out/sdvx_score.csv 形式、および SDVX Helper Portal API を扱う。
CSV ヘッダー: LV, Title, Difficulty, Lamp, Score, EXScore, Grade, VF, Last Played
"""
import bz2
import csv
import io
import os
import pickle
import re
import traceback
import datetime
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Tuple, Optional

from PySide6.QtCore import QObject, QThread, Signal, Qt

from src.classes import clear_lamp
from src.funcs import convert_lamp, convert_difficulty
from src.logger import get_logger
from src.database_sqlite import SQLiteDatabase

logger = get_logger(__name__)


class RivalScoreEntry:
    """1譜面分のライバルスコア"""
    __slots__ = ('lamp', 'score', 'exscore')

    def __init__(self):
        self.lamp:    clear_lamp    = clear_lamp.noplay
        self.score:   int           = 0
        self.exscore: Optional[int] = None


class RivalData:
    """1ライバルの全スコアデータ"""

    def __init__(self, name: str):
        self.name:   str                               = name
        self.scores: Dict[Tuple[str, str], RivalScoreEntry] = {}
        # キー: (title, diff_str)  diff_str = "NOV"/"ADV"/"EXH"/"MXM"
        self.error:  Optional[str]                    = None


class RivalFetchWorker(QThread):
    """バックグラウンドでライバルデータを取得するワーカー

    CSV ライバルは ThreadPoolExecutor で並列取得。
    portal_fetch_fn が渡された場合はポータル登録ライバルも並列で取得し、
    同名ライバルは CSV 側が優先される（CSV が上書き）。
    """

    finished = Signal(list)   # List[RivalData]

    def __init__(
        self,
        rival_configs: List[Dict[str, str]],
        portal_fetch_fn: Optional[Callable[[], list]] = None,
    ):
        super().__init__()
        self.rival_configs   = rival_configs
        self.portal_fetch_fn = portal_fetch_fn
        self._is_cancelled   = False

    def cancel(self):
        self._is_cancelled = True
        # wait() は QThread 内でブロックされる可能性があるため、
        # ここではフラグを立てるのみに留め、呼び出し側で wait(timeout) する。

    def run(self):
        try:
            results_by_name: Dict[str, RivalData] = {}

            with ThreadPoolExecutor(max_workers=8) as pool:
                csv_futures  = {pool.submit(self._fetch_one_csv, cfg): cfg
                                for cfg in self.rival_configs}
                portal_future = (pool.submit(self.portal_fetch_fn)
                                 if self.portal_fetch_fn else None)

                # ポータルライバルを先に収集（低優先）
                if portal_future:
                    try:
                        for rd in self._parse_portal_rivals(portal_future.result()):
                            results_by_name[rd.name] = rd
                    except Exception as e:
                        logger.warning(f'ポータルライバル取得エラー: {e}')

                # CSV ライバルを収集（高優先・同名は上書き）
                for future, cfg in csv_futures.items():
                    if self._is_cancelled:
                        break
                    try:
                        rd = future.result()
                        results_by_name[rd.name] = rd
                    except Exception as e:
                        name = cfg.get('name', '?')
                        logger.warning(f"ライバル '{name}' 取得エラー: {e}")
                        rd = RivalData(name)
                        rd.error = str(e)
                        results_by_name[rd.name] = rd

            self.finished.emit(list(results_by_name.values()))
        except Exception:
            logger.error(traceback.format_exc())

    # ── CSV 取得 ──────────────────────────────────────────────────────────────

    def _fetch_one_csv(self, cfg: Dict[str, str]) -> RivalData:
        """1ライバルの CSV を取得してパース（スレッドプールから呼ばれる）"""
        rival = RivalData(cfg['name'])
        try:
            import requests
            session = requests.Session()
            # User-Agent を設定してブラウザを装う（警告画面の解析精度を上げるため）
            session.headers.update({
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            })
            
            url = self._convert_to_direct_url(cfg.get('url', ''))
            
            # 1回目試行
            resp = session.get(url, timeout=20)
            resp.raise_for_status()
            
            # Google Drive の「ウイルススキャン実行不可」警告画面チェック
            content_text = resp.content.decode('utf-8', errors='replace')
            if 'confirm=' in content_text:
                # 複数のクォート形式やエスケープに対応した正規表現
                confirm_m = re.search(r'confirm=([a-zA-Z0-9_-]+)', content_text)
                if confirm_m:
                    confirm_token = confirm_m.group(1)
                    # URLを再構築（export=download を確実に含める）
                    file_id_m = re.search(r'id=([\w-]+)', url)
                    if file_id_m:
                        file_id = file_id_m.group(1)
                        download_url = f"https://drive.google.com/uc?export=download&id={file_id}&confirm={confirm_token}"
                        resp = session.get(download_url, timeout=20)
                        resp.raise_for_status()
            
            # エンコーディング判定とデコード
            try:
                # まず utf-8-sig (BOMあり) を試す
                text = resp.content.decode('utf-8-sig')
            except UnicodeDecodeError:
                # 失敗したら cp932 (Windows-31J / Shift-JIS) を試す
                try:
                    text = resp.content.decode('cp932')
                except UnicodeDecodeError:
                    # それでもダメなら utf-8 でエラーを置換しながらデコード
                    text = resp.content.decode('utf-8', errors='replace')
            
            self._parse_csv(text, rival)
            logger.info(f"ライバル '{rival.name}' CSV取得完了 ({len(rival.scores)} 件)")
        except Exception as e:
            rival.error = str(e)
            logger.warning(f"ライバル '{cfg['name']}' CSV取得失敗: {e}")
        return rival

    @staticmethod
    def _convert_to_direct_url(url: str) -> str:
        """Google Drive 共有 URL / ファイル ID を直接ダウンロード URL に変換"""
        # /file/d/ID/view や open?id=ID などの形式から ID を抽出
        m = re.search(r'(?:/file/d/|[\?&]id=)([\w-]+)', url)
        if m:
            return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
        if re.fullmatch(r'[\w-]+', url):
            return f"https://drive.google.com/uc?export=download&id={url}"
        return url

    @staticmethod
    def _parse_csv(csv_text: str, rival: RivalData):
        """sdvx_score.csv 形式をパースして RivalData に格納

        ヘッダーは大文字小文字どちらでも受け入れる。
        必須列: Title(title), Difficulty(difficulty), Score(score)
        任意列: Lamp(lamp), ExScore(exscore)
        """
        reader = csv.DictReader(io.StringIO(csv_text))
        if reader.fieldnames is None:
            return

        lower_map: Dict[str, str] = {
            (fn or '').lower(): fn for fn in reader.fieldnames
        }

        def _get(row: dict, *keys: str) -> str:
            for k in keys:
                v = row.get(lower_map.get(k, ''), '').strip()
                if v:
                    return v
            return ''

        for row in reader:
            title    = _get(row, 'title', '楽曲名')
            diff_raw = _get(row, 'difficulty', '難易度').upper()
            score_s  = _get(row, 'score', 'ハイスコア', 'スコア')
            lamp_s   = _get(row, 'lamp', 'クリアランク', 'クリア')
            ex_s     = _get(row, 'exscore', 'exスコア')

            if not title or not score_s:
                continue
            try:
                score = int(score_s)
            except ValueError:
                continue

            # INF/GRV/HVN/VVD/XCD はすべて "MXM" に正規化してキーを統一
            diff_enum = convert_difficulty(diff_raw)
            diff_key  = str(diff_enum) if diff_enum else diff_raw

            entry         = RivalScoreEntry()
            entry.score   = score
            entry.lamp    = convert_lamp(lamp_s) if lamp_s else clear_lamp.noplay
            entry.exscore = int(ex_s) if ex_s.isdigit() else None
            rival.scores[(title, diff_key)] = entry

    # ── ポータルライバルパース ────────────────────────────────────────────────

    @staticmethod
    def _parse_portal_rivals(rival_data: dict) -> List[RivalData]:
        """portal_manager.get_rivals() の正規化済みレスポンスを RivalData リストに変換。

        フォーマット: {rival_name: [{"title":str,"difficulty":str,
                                      "score":int,"exscore":int|None,"lamp":str}]}
        """
        results: List[RivalData] = []
        for name, scores in rival_data.items():
            if not name:
                continue
            rd = RivalData(name)
            for s in scores:
                if not isinstance(s, dict):
                    continue
                title    = s.get('title', '')
                diff_raw = s.get('difficulty', '').upper()
                score    = s.get('score', 0)
                if not title or not diff_raw:
                    continue
                # INF/GRV/HVN/VVD/XCD はすべて "MXM" に正規化してキーを統一
                diff_enum = convert_difficulty(diff_raw)
                diff_key  = str(diff_enum) if diff_enum else diff_raw
                entry         = RivalScoreEntry()
                entry.score   = int(score) if score else 0
                raw_ex        = s.get('exscore')
                entry.exscore = int(raw_ex) if raw_ex is not None else None
                lamp_s        = s.get('lamp', '')
                entry.lamp    = convert_lamp(lamp_s) if lamp_s else clear_lamp.noplay
                rd.scores[(title, diff_key)] = entry
            logger.info(f"ポータルライバル '{name}' パース完了 ({len(rd.scores)} 件)")
            results.append(rd)
        return results


class RivalManager(QObject):
    """ライバルデータの取得・保持を管理するクラス"""

    CACHE_PATH = os.path.join('out', 'rival_scores.sdvxh')

    rivals_loaded = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.db = SQLiteDatabase()  # デフォルトパス sdvx_helper.db
        self.rivals:            List[RivalData]         = []
        self._worker:           Optional[RivalFetchWorker] = None
        self.last_fetch_time:   Optional[str]           = None

    def shutdown(self):
        """アプリ終了時のクリーンアップ"""
        if self._worker and self._worker.isRunning():
            logger.info("ライバル取得スレッドをキャンセル中...")
            self._worker.cancel()
            self._worker.wait(1000) # 1秒だけ待つ

    # ── キャッシュ ────────────────────────────────────────────────────────

    # portal内部IDパターン (rival_1, rival_2, ...) → 古いキャッシュと判定
    _PORTAL_ID_PATTERN = re.compile(r'^rival_\d+$')

    def load_cache(self):
        """SQLite からライバルデータを読み込む。初回は旧キャッシュからの移行。"""
        # 1. 移行チェック
        if os.path.exists(self.CACHE_PATH):
            self._migrate_from_bz2pkl()

        # 2. SQLite から読み込み
        try:
            rival_names = [r['rival_name'] for r in self.db.execute("SELECT DISTINCT rival_name FROM rival_scores").fetchall()]
            new_rivals = []
            for name in rival_names:
                rd = RivalData(name)
                rows = self.db.get_rival_scores(name)
                for r in rows:
                    entry = RivalScoreEntry()
                    entry.lamp = clear_lamp(r['lamp'])
                    entry.score = r['score']
                    entry.exscore = r['exscore']
                    rd.scores[(r['title'], r['difficulty'])] = entry
                new_rivals.append(rd)
            
            self.rivals = new_rivals
            logger.info(f"ライバルDB読み込み完了 ({len(self.rivals)} 人)")
            self.rivals_loaded.emit()
        except Exception as e:
            logger.error(f"ライバルDBロード失敗: {e}")

    def _migrate_from_bz2pkl(self):
        """旧 rival_scores.sdvxh (bz2pkl) から SQLite へデータを移行する"""
        logger.info(f"ライバルキャッシュの移行を開始します: {self.CACHE_PATH}")
        try:
            with bz2.BZ2File(self.CACHE_PATH, 'rb') as f:
                old_rivals = pickle.load(f)
            
            for rd in old_rivals:
                for (title, diff_str), entry in rd.scores.items():
                    self.db.upsert_rival_score(
                        rd.name, title, diff_str, 
                        entry.score, entry.lamp.value, entry.exscore
                    )
            self.db.commit()
            
            backup_path = self.CACHE_PATH + '.bak'
            if os.path.exists(backup_path):
                os.remove(backup_path)
            os.rename(self.CACHE_PATH, backup_path)
            logger.info(f"ライバルキャッシュ移行完了: {len(old_rivals)} 人分。")
        except Exception as e:
            logger.error(f"ライバルキャッシュ移行失敗: {e}\n{traceback.format_exc()}")

    def _save_cache(self):
        """SQLite への保存 (逐次 upsert するため、fetch 完了時の一括保存のみ担当)"""
        try:
            active_names = {rd.name for rd in self.rivals}
            if active_names:
                placeholders = ','.join('?' for _ in active_names)
                self.db.execute(
                    f"DELETE FROM rival_scores WHERE rival_name NOT IN ({placeholders})",
                    tuple(active_names),
                )
            for rd in self.rivals:
                if rd.error: continue
                for (title, diff_str), entry in rd.scores.items():
                    self.db.upsert_rival_score(
                        rd.name, title, diff_str,
                        entry.score, entry.lamp.value, entry.exscore
                    )
            self.db.commit()
            logger.debug("ライバルDB保存完了")
        except Exception as e:
            logger.error(f"ライバルDB保存失敗: {e}")

    def delete_cached_rival(self, rival_name: str):
        """指定ライバルをメモリとSQLiteキャッシュから削除する。"""
        self.rivals = [r for r in self.rivals if r.name != rival_name]
        try:
            self.db.delete_rival(rival_name)
            self.db.commit()
            logger.info(f"ライバルDB削除完了: {rival_name}")
        except Exception as e:
            logger.error(f"ライバルDB削除失敗 ({rival_name}): {e}")
        self.rivals_loaded.emit()

    # ── フェッチ ──────────────────────────────────────────────────────────

    def start_fetch(
        self,
        rival_configs: List[Dict[str, str]],
        portal_fetch_fn: Optional[Callable[[], list]] = None,
    ):
        """全ライバルのデータをバックグラウンドで取得開始。

        Args:
            rival_configs:  CSV ライバル設定リスト [{'name': str, 'url': str}]
            portal_fetch_fn: ポータル API からライバルリストを返す callable。
                             None の場合はポータル取得をスキップ。
        """
        if not rival_configs and portal_fetch_fn is None:
            self.rivals = []
            self.rivals_loaded.emit()
            return

        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)

        self._worker = RivalFetchWorker(rival_configs, portal_fetch_fn=portal_fetch_fn)
        # QThread.run() 内の emit は QThread のスレッドアフィニティ(=メインスレッド)と
        # 同じに見えるため AutoConnection では DirectConnection になり、UI 操作がバック
        # グラウンドスレッドで実行される。QueuedConnection を明示してメインスレッドに
        # デリバリーされるよう強制する。
        self._worker.finished.connect(self._on_fetch_finished, Qt.QueuedConnection)
        self._worker.start()

    def _on_fetch_finished(self, results: List[RivalData]):
        self.rivals          = results
        self.last_fetch_time = datetime.datetime.now().strftime('%H:%M')
        self._save_cache()
        self.rivals_loaded.emit()

    # ── スコア参照 ────────────────────────────────────────────────────────

    def get_score(self, name: str, title: str, diff_str: str
                  ) -> Optional[RivalScoreEntry]:
        """指定ライバルの指定譜面スコアを返す（未登録なら None）"""
        for rd in self.rivals:
            if rd.name == name:
                return rd.scores.get((title, diff_str))
        return None

    def get_all_scores(self, title: str, diff_str: str
                       ) -> List[Tuple[str, RivalScoreEntry]]:
        """全ライバルの指定譜面スコアを (name, entry) リストで返す"""
        result = []
        for rd in self.rivals:
            if rd.error:
                continue
            entry = rd.scores.get((title, diff_str))
            if entry:
                result.append((rd.name, entry))
        return result

    @property
    def rival_names(self) -> List[str]:
        """登録済みライバル名一覧"""
        return [rd.name for rd in self.rivals]
