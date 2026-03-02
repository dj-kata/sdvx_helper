"""SDVX向けリザルトデータモデル。

OneResult  : 1プレー分のリザルト
OneBestData: 1譜面の自己ベスト情報（HTMLビュー・VFランキング用）
"""
from __future__ import annotations

import datetime
from typing import Optional

from src.classes import difficulty, clear_lamp, detect_mode
from src.funcs import calc_chart_id, calc_grade, get_title_with_chart
from src.volforce import calc_vf
from src.logger import get_logger

logger = get_logger(__name__)


class OneResult:
    """1プレー分のリザルトを表すクラス。"""

    def __init__(self,
                 title:       str,
                 difficulty:  difficulty,
                 lamp:        clear_lamp,
                 score:       Optional[int]         = None,
                 exscore:     Optional[int]         = None,
                 level:       Optional[int]         = None,
                 timestamp:   Optional[int]         = None,
                 detect_mode: Optional[detect_mode] = None,
                 bestscore:   Optional[int]         = None,
                 bestexscore: Optional[int]         = None,
                 ):
        self.title       = title
        self.difficulty  = difficulty
        self.lamp        = lamp
        self.score       = score
        self.exscore     = exscore
        self.level       = level
        """musiclist から引いた譜面レベル (1-20)。未登録曲なら None。"""
        self.timestamp   = timestamp or int(datetime.datetime.now().timestamp())
        self.detect_mode = detect_mode
        """データの取得元 (select / result など)。"""
        self.bestscore   = bestscore
        """リザルト画面で読んだ自己べスコア。DB参照なしの比較用。"""
        self.bestexscore = bestexscore
        """リザルト画面で読んだ自己べEXスコア。"""

    # ─── 計算プロパティ ────────────────────────────────────────────────────

    @property
    def chart_id(self) -> Optional[str]:
        """楽曲ID: sha256(title + difficulty.name)"""
        return calc_chart_id(self.title, self.difficulty)

    @property
    def grade(self) -> str:
        """グレード文字列 (S / AAA+ / ... / D)"""
        return calc_grade(self.score) if self.score is not None else 'D'

    @property
    def vf(self) -> int:
        """Volforce寄与値 (level・score・lamp から計算)。"""
        if self.score is None or self.level is None:
            return 0
        return calc_vf(self.level, self.score, self.lamp)

    # ─── 更新判定 ──────────────────────────────────────────────────────────

    def is_score_updated(self) -> bool:
        """スコア更新があるか。自己べ未取得の場合は True とみなす。"""
        if self.bestscore is None:
            return True
        return self.score is not None and self.score > self.bestscore

    def is_exscore_updated(self) -> bool:
        """EXスコア更新があるか。"""
        if self.bestexscore is None:
            return True
        return self.exscore is not None and self.exscore > self.bestexscore

    # ─── 比較・ハッシュ ────────────────────────────────────────────────────

    def __lt__(self, other: OneResult) -> bool:
        """日付昇順ソート用。"""
        return self.timestamp < other.timestamp

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, OneResult):
            return False
        return (self.chart_id == other.chart_id
                and self.score == other.score
                and self.lamp == other.lamp
                and self.timestamp == other.timestamp)

    def __hash__(self) -> int:
        return hash((self.chart_id, self.score, self.lamp, self.timestamp))

    def __str__(self) -> str:
        ts = datetime.datetime.fromtimestamp(self.timestamp).strftime('%Y-%m-%d %H:%M:%S')
        return (f"[{self.detect_mode.name if self.detect_mode else '?'}] "
                f"{get_title_with_chart(self.title, self.difficulty)} "
                f"lv:{self.level} score:{self.score} ex:{self.exscore} "
                f"grade:{self.grade} lamp:{self.lamp} vf:{self.vf} "
                f"ts:{ts}")


class OneBestData:
    """1譜面の自己ベスト情報（HTMLビュー・VFランキング用）。

    ResultDatabase が複数の OneResult を集計して生成する。
    """

    def __init__(self):
        self.title:        str              = ''
        self.difficulty:   difficulty       = None
        self.level:        int              = 0
        self.best_score:   int              = 0
        self.best_exscore: Optional[int]   = None
        self.best_lamp:    clear_lamp       = clear_lamp.noplay
        self.last_timestamp: int            = 0
        self.play_count:   int              = 0

    # ─── 計算プロパティ ────────────────────────────────────────────────────

    @property
    def chart_id(self) -> Optional[str]:
        return calc_chart_id(self.title, self.difficulty)

    @property
    def grade(self) -> str:
        return calc_grade(self.best_score) if self.best_score else 'D'

    @property
    def vf(self) -> int:
        """VF寄与値。HTMLビューやランキング表示に使う。"""
        return calc_vf(self.level, self.best_score, self.best_lamp)

    @property
    def last_play_date(self) -> str:
        if self.last_timestamp:
            return datetime.datetime.fromtimestamp(self.last_timestamp).strftime('%Y-%m-%d %H:%M')
        return ''

    # ─── ユーティリティ ────────────────────────────────────────────────────

    def update(self, result: OneResult) -> None:
        """OneResult でベスト情報を更新する。初回呼び出しで基本情報もセットする。"""
        if not self.title:
            self.title      = result.title
            self.difficulty = result.difficulty
            self.level      = result.level or 0

        self.play_count += 1
        if result.timestamp > self.last_timestamp:
            self.last_timestamp = result.timestamp

        if result.score is not None and result.score > self.best_score:
            self.best_score = result.score

        if result.exscore is not None:
            if self.best_exscore is None or result.exscore > self.best_exscore:
                self.best_exscore = result.exscore

        if result.lamp > self.best_lamp:
            self.best_lamp = result.lamp

    def __str__(self) -> str:
        return (f"{get_title_with_chart(self.title, self.difficulty)} "
                f"lv:{self.level} score:{self.best_score} ex:{self.best_exscore} "
                f"grade:{self.grade} lamp:{self.best_lamp} vf:{self.vf} "
                f"plays:{self.play_count} last:{self.last_play_date}")
