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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Dict, List, Tuple, Optional

from PySide6.QtCore import QObject, QThread, Signal

from src.classes import clear_lamp
from src.funcs import convert_lamp, convert_difficulty
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
        self.wait()

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
        finally:
            self.finished.disconnect()

    # ── CSV 取得 ──────────────────────────────────────────────────────────────

    def _fetch_one_csv(self, cfg: Dict[str, str]) -> RivalData:
        """1ライバルの CSV を取得してパース（スレッドプールから呼ばれる）"""
        rival = RivalData(cfg['name'])
        try:
            import requests
            url  = self._convert_to_direct_url(cfg.get('url', ''))
            resp = requests.get(url, timeout=20)
            resp.raise_for_status()
            text = resp.content.decode('utf-8-sig')
            self._parse_csv(text, rival)
            logger.info(f"ライバル '{rival.name}' CSV取得完了 ({len(rival.scores)} 件)")
        except Exception as e:
            rival.error = str(e)
            logger.warning(f"ライバル '{cfg['name']}' CSV取得失敗: {e}")
        return rival

    @staticmethod
    def _convert_to_direct_url(url: str) -> str:
        """Google Drive 共有 URL / ファイル ID を直接ダウンロード URL に変換"""
        m = re.search(r'/file/d/([^/?]+)', url)
        if m:
            return f"https://drive.google.com/uc?export=download&id={m.group(1)}"
        m = re.search(r'[?&]id=([^&]+)', url)
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
            title    = _get(row, 'title')
            diff_raw = _get(row, 'difficulty').upper()
            score_s  = _get(row, 'score')
            lamp_s   = _get(row, 'lamp')
            ex_s     = _get(row, 'exscore')

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
        self.rivals:            List[RivalData]         = []
        self._worker:           Optional[RivalFetchWorker] = None
        self.last_fetch_time:   Optional[str]           = None

    # ── キャッシュ ────────────────────────────────────────────────────────

    # portal内部IDパターン (rival_1, rival_2, ...) → 古いキャッシュと判定
    _PORTAL_ID_PATTERN = re.compile(r'^rival_\d+$')

    def load_cache(self):
        """起動時にキャッシュを読み込んで即座に反映する。
        portal内部IDが名前になっている古いキャッシュは無視してフェッチを促す。
        """
        try:
            with bz2.BZ2File(self.CACHE_PATH, 'rb') as f:
                loaded = pickle.load(f)
            # 古い形式チェック: portal内部ID (rival_1 など) が名前に含まれていれば破棄
            if any(self._PORTAL_ID_PATTERN.match(r.name) for r in loaded):
                logger.info("古いフォーマットのキャッシュを検出。フェッチで上書きします。")
                return
            self.rivals = loaded
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
            # compresslevel=1 で高速保存（ファイルサイズはやや大きいが十分小さい）
            with bz2.BZ2File(self.CACHE_PATH, 'wb', compresslevel=1) as f:
                pickle.dump(self.rivals, f)
            logger.info("ライバルキャッシュ保存完了")
        except Exception:
            logger.error(f"ライバルキャッシュ保存失敗:\n{traceback.format_exc()}")

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
