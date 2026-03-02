"""SDVX ライバルスコアデータの取得・管理モジュール

sdvx_helper の out/sdvx_score.csv 形式を扱う。
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
from typing import Dict, List, Tuple, Optional

from PySide6.QtCore import QObject, QThread, Signal

from src.classes import clear_lamp
from src.funcs import convert_lamp
from src.logger import get_logger

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
    """バックグラウンドでライバルCSVを取得するワーカー"""

    finished = Signal(list)   # List[RivalData]

    def __init__(self, rival_configs: List[Dict[str, str]]):
        super().__init__()
        self.rival_configs   = rival_configs
        self._is_cancelled   = False

    def cancel(self):
        self._is_cancelled = True
        self.wait()

    def run(self):
        try:
            results: List[RivalData] = []
            for cfg in self.rival_configs:
                if self._is_cancelled:
                    break
                rival = RivalData(cfg['name'])
                try:
                    import requests
                    url      = self._convert_to_direct_url(cfg.get('url', ''))
                    resp     = requests.get(url, timeout=20)
                    resp.raise_for_status()
                    text     = resp.content.decode('utf-8-sig')
                    self._parse_csv(text, rival)
                    logger.info(f"ライバル '{rival.name}' の CSV 取得完了 ({len(rival.scores)} 件)")
                except Exception as e:
                    rival.error = str(e)
                    logger.warning(f"ライバル '{cfg['name']}' の CSV 取得失敗: {e}")
                results.append(rival)
            self.finished.emit(results)
        except Exception:
            logger.error(traceback.format_exc())
        finally:
            self.finished.disconnect()

    # ── URL 変換 ────────────────────────────────────────────────────────────

    @staticmethod
    def _convert_to_direct_url(url: str) -> str:
        """Google Drive 共有 URL / ファイル ID を直接ダウンロード URL に変換"""
        m = re.search(r'/file/d/([^/?]+)', url)
        if m:
            return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
        m = re.search(r'[?&]id=([^&]+)', url)
        if m:
            return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
        # 英数字・ハイフン・アンダースコアのみ → ファイルID単体とみなす
        if re.fullmatch(r'[\w-]+', url):
            return f"https://drive.google.com/uc?export=download&id={url}"
        return url

    # ── CSV パース ─────────────────────────────────────────────────────────

    @staticmethod
    def _parse_csv(csv_text: str, rival: RivalData):
        """sdvx_score.csv 形式をパースして RivalData に格納

        ヘッダーは大文字小文字どちらでも受け入れる。
        必須列: Title(title), Difficulty(difficulty), Score(score)
        任意列: Lamp(lamp)
        """
        reader = csv.DictReader(io.StringIO(csv_text))
        if reader.fieldnames is None:
            return

        # ヘッダーを case-insensitive に正規化するための対応表
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
            title    = _get(row, 'title')
            diff_str = _get(row, 'difficulty').upper()
            score_s  = _get(row, 'score')
            lamp_s   = _get(row, 'lamp')
            ex_s     = _get(row, 'exscore')

            if not title or not score_s:
                continue
            try:
                score = int(score_s)
            except ValueError:
                continue

            entry         = RivalScoreEntry()
            entry.score   = score
            entry.lamp    = convert_lamp(lamp_s) if lamp_s else clear_lamp.noplay
            entry.exscore = int(ex_s) if ex_s.isdigit() else None
            rival.scores[(title, diff_str)] = entry


class RivalManager(QObject):
    """ライバルデータの取得・保持を管理するクラス"""

    CACHE_PATH = os.path.join('out', 'rival_scores.sdvxh')

    rivals_loaded = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.rivals:            List[RivalData]         = []
        self._worker:           Optional[RivalFetchWorker] = None
        self.last_fetch_time:   Optional[str]           = None

    # ── キャッシュ ────────────────────────────────────────────────────────

    def load_cache(self):
        """起動時にキャッシュを読み込んで即座に反映する"""
        try:
            with bz2.BZ2File(self.CACHE_PATH, 'rb') as f:
                self.rivals = pickle.load(f)
            ok = len([r for r in self.rivals if not r.error])
            logger.info(f"ライバルキャッシュ読み込み完了 ({ok} 人)")
            self.rivals_loaded.emit()
        except FileNotFoundError:
            logger.debug("ライバルキャッシュが見つかりません")
        except Exception:
            logger.warning(f"ライバルキャッシュ読み込み失敗:\n{traceback.format_exc()}")

    def _save_cache(self):
        """ライバルデータをキャッシュファイルに保存する"""
        try:
            os.makedirs('out', exist_ok=True)
            with bz2.BZ2File(self.CACHE_PATH, 'wb', compresslevel=9) as f:
                pickle.dump(self.rivals, f)
            logger.info("ライバルキャッシュ保存完了")
        except Exception:
            logger.error(f"ライバルキャッシュ保存失敗:\n{traceback.format_exc()}")

    # ── フェッチ ──────────────────────────────────────────────────────────

    def start_fetch(self, rival_configs: List[Dict[str, str]]):
        """全ライバルの CSV をバックグラウンドで取得開始"""
        if not rival_configs:
            self.rivals = []
            self.rivals_loaded.emit()
            return

        if self._worker and self._worker.isRunning():
            self._worker.cancel()
            self._worker.wait(2000)

        self._worker = RivalFetchWorker(rival_configs)
        self._worker.finished.connect(self._on_fetch_finished)
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
