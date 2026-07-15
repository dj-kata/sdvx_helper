"""Screen-coordinate layout constants for SDVX recognition.

All rectangles use the normalized portrait coordinate space: 1080 x 1920.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Point:
    x: int
    y: int


@dataclass(frozen=True)
class Rect:
    x: int
    y: int
    w: int
    h: int

    @property
    def box(self) -> tuple[int, int, int, int]:
        """Return a PIL-compatible crop box: (left, top, right, bottom)."""
        return (self.x, self.y, self.x + self.w, self.y + self.h)


@dataclass(frozen=True)
class ScreenDetectLayout:
    onselect: Rect
    ondetect: Rect
    onplay1: Rect
    onplay2: Rect
    onresult_val0: Rect
    onresult_val1: Rect
    onresult_head: Rect
    onresult_enable_head: bool


@dataclass(frozen=True)
class SelectLayout:
    jacket: Rect
    novice: Rect
    advanced: Rect
    exhaust: Rect
    append: Rect
    lamp: Rect
    arcade: Rect
    has_exscore: Rect
    score_large: tuple[Rect, ...]
    score_small: tuple[Rect, ...]
    exscore: tuple[Rect, ...]


@dataclass(frozen=True)
class InfoLayout:
    jacket: Rect
    title: Rect
    level: Rect
    difficulty: Rect
    bpm: Rect
    effector: Rect
    illustrator: Rect


@dataclass(frozen=True)
class PlayLayout:
    lamp: Rect
    gauge: Rect
    vf: Rect
    player_class: Rect
    blastermax: Rect
    gauge_clear_threshold: int
    gauge_hard_threshold: int


@dataclass(frozen=True)
class ResultLayout:
    """リザルト画面内での座標系。トリミングモードの有無に関わらず、1080x1920に対する座標を指定。"""

    jacket: Rect
    difficulty: Rect
    lamp: Rect
    gauge: Rect
    score_large: tuple[Rect, ...]
    score_small: tuple[Rect, ...]
    exscore: tuple[Rect, ...]
    bestscore: tuple[Rect, ...]
    bestexscore: tuple[Rect, ...]
    score_mode_detect_marker: Rect


@dataclass(frozen=True)
class ResultLayoutExScoreMode:
    """リザルト画面(EXスコアモード)内での座標系。トリミングモードの有無に関わらず、1080x1920に対する座標を指定。"""

    score: tuple[Rect, ...]
    exscore: tuple[Rect, ...]
    bestscore: tuple[Rect, ...]
    bestexscore: tuple[Rect, ...]


@dataclass(frozen=True)
class SummaryLayout:
    max_rows: int
    row_size: int
    margin: int
    full_width: int
    small_width: int
    crop_title: Rect
    crop_title_small: Rect
    crop_difficulty: Rect
    crop_rate: Rect
    crop_score: Rect
    crop_jacket: Rect
    crop_rank: Rect
    crop_info: Rect
    pos_title: Point
    pos_title_small: Point
    pos_difficulty: Point
    pos_difficulty_small: Point
    pos_rate: Point
    pos_score: Point
    pos_score_small: Point
    pos_jacket: Point
    pos_jacket_small: Point
    pos_rank: Point
    pos_rank_small: Point
    pos_lamp: Point
    pos_lamp_small: Point
    parts: tuple[str, ...]
    small_parts: tuple[str, ...]

    def crop(self, name: str) -> Rect:
        return getattr(self, f"crop_{name}")


@dataclass(frozen=True)
class TimingLayout:
    detect_wait: float
    detect_capture_delay: float


DETECT = ScreenDetectLayout(
    onselect=Rect(50, 650, 40, 150),
    ondetect=Rect(340, 250, 400, 35),
    onplay1=Rect(0, 420, 131, 88),
    onplay2=Rect(15, 876, 296, 16),
    onresult_val0=Rect(340, 1600, 200, 40),
    onresult_val1=Rect(30, 1390, 210, 40),
    onresult_head=Rect(0, 0, 1080, 150),
    onresult_enable_head=False,
)

SELECT = SelectLayout(
    jacket=Rect(94, 242, 352, 352),
    novice=Rect(68, 1044, 62, 12),
    advanced=Rect(182, 1044, 62, 12),
    exhaust=Rect(297, 1044, 62, 12),
    append=Rect(411, 1044, 62, 12),
    lamp=Rect(344, 840, 56, 50),
    arcade=Rect(251, 808, 50, 10),
    has_exscore=Rect(440, 1148, 77, 15),
    score_large=(
        Rect(18, 823, 42, 40),
        Rect(63, 823, 42, 40),
        Rect(108, 823, 42, 40),
        Rect(153, 823, 42, 40),
    ),
    score_small=(
        Rect(199, 840, 24, 24),
        Rect(227, 840, 24, 24),
        Rect(255, 840, 24, 24),
        Rect(283, 840, 24, 24),
    ),
    exscore=(
        Rect(125, 879, 12, 14),
        Rect(138, 879, 12, 14),
        Rect(151, 879, 12, 14),
        Rect(164, 879, 12, 14),
        Rect(177, 879, 12, 14),
    ),
)

INFO = InfoLayout(
    jacket=Rect(237, 387, 607, 607),
    title=Rect(201, 1091, 678, 122),
    level=Rect(908, 1107, 91, 86),
    difficulty=Rect(917, 1172, 73, 12),
    bpm=Rect(92, 1127, 74, 46),
    effector=Rect(313, 1275, 489, 28),
    illustrator=Rect(313, 1333, 489, 28),
)

PLAY = PlayLayout(
    lamp=Rect(630, 930, 230, 50),
    gauge=Rect(730, 1200, 100, 16),
    vf=Rect(317, 1529, 96, 36),
    player_class=Rect(184, 1514, 118, 58),
    blastermax=Rect(356, 1582, 58, 19),
    gauge_clear_threshold=10,
    gauge_hard_threshold=15,
)

RESULT = ResultLayout(
    jacket=Rect(57, 916, 263, 263),
    difficulty=Rect(55, 870, 138, 30),
    lamp=PLAY.lamp,
    gauge=PLAY.gauge,
    score_large=(
        Rect(431, 1069, 52, 51),
        Rect(489, 1069, 52, 51),
        Rect(547, 1069, 52, 51),
        Rect(605, 1069, 52, 51),
    ),
    score_small=(
        Rect(662, 1089, 32, 31),
        Rect(698, 1089, 32, 31),
        Rect(734, 1089, 32, 31),
        Rect(770, 1089, 32, 31),
    ),
    exscore=(
        Rect(532, 1145, 16, 19),
        Rect(550, 1145, 16, 19),
        Rect(568, 1145, 16, 19),
        Rect(586, 1145, 16, 19),
        Rect(604, 1145, 16, 19),
    ),
    bestscore=(
        Rect(837, 1088, 14, 14),
        Rect(851, 1088, 14, 14),
        Rect(865, 1088, 14, 14),
        Rect(879, 1088, 14, 14),
        Rect(893, 1088, 14, 14),
        Rect(907, 1088, 14, 14),
        Rect(921, 1088, 14, 14),
        Rect(935, 1088, 14, 14),
    ),
    bestexscore=(
        Rect(912, 1140, 14, 14),
        Rect(926, 1140, 14, 14),
        Rect(940, 1140, 14, 14),
        Rect(954, 1140, 14, 14),
        Rect(968, 1140, 14, 14),
    ),
    # リザルト画面について通常スコアかEXスコアかを判別するのに利用
    score_mode_detect_marker=Rect(816, 1069, 107, 13),
)

# EXスコアモードのリザルト画面
RESULT_EX = ResultLayoutExScoreMode(
    score=(
        Rect(843, 1138, 16, 19),
        Rect(863, 1138, 16, 19),
        Rect(883, 1138, 16, 19),
        Rect(903, 1138, 16, 19),
        Rect(923, 1138, 16, 19),
        Rect(943, 1138, 16, 19),
        Rect(963, 1138, 16, 19),
        Rect(983, 1138, 16, 19),
    ),
    exscore=(
        Rect(439, 1069, 52, 51),
        Rect(496, 1069, 52, 51),
        Rect(553, 1069, 52, 51),
        Rect(610, 1069, 52, 51),
        Rect(667, 1069, 52, 51),
    ),
    bestscore=(
        Rect(837, 1088, 14, 14),
        Rect(851, 1088, 14, 14),
        Rect(865, 1088, 14, 14),
        Rect(879, 1088, 14, 14),
        Rect(893, 1088, 14, 14),
        Rect(907, 1088, 14, 14),
        Rect(921, 1088, 14, 14),
        Rect(935, 1088, 14, 14),
    ),
    bestexscore=(
        Rect(912, 1140, 14, 14),
        Rect(926, 1140, 14, 14),
        Rect(940, 1140, 14, 14),
        Rect(954, 1140, 14, 14),
        Rect(968, 1140, 14, 14),
    ),
)

SUMMARY = SummaryLayout(
    max_rows=30,
    row_size=40,
    margin=20,
    full_width=960,
    small_width=590,
    crop_title=Rect(389, 996, 527, 30),
    crop_title_small=Rect(389, 996, 287, 30),
    crop_difficulty=Rect(55, 870, 138, 30),
    crop_rate=Rect(690, 1142, 97, 25),
    crop_score=Rect(431, 1067, 230, 55),
    crop_jacket=Rect(57, 916, 263, 263),
    crop_rank=Rect(958, 1034, 88, 78),
    crop_info=Rect(379, 1001, 527, 65),
    pos_title=Point(150, 20),
    pos_title_small=Point(150, 20),
    pos_difficulty=Point(70, 28),
    pos_difficulty_small=Point(70, 28),
    pos_rate=Point(865, 25),
    pos_score=Point(682, 25),
    pos_score_small=Point(442, 25),
    pos_jacket=Point(20, 17),
    pos_jacket_small=Point(20, 17),
    pos_rank=Point(780, 22),
    pos_rank_small=Point(540, 22),
    pos_lamp=Point(830, 22),
    pos_lamp_small=Point(540, 22),
    parts=("jacket", "difficulty", "title", "score", "rank", "rate", "lamp"),
    small_parts=(
        "jacket_small",
        "difficulty_small",
        "title_small",
        "score_small",
        "lamp_small",
    ),
)

TIMING = TimingLayout(
    detect_wait=1.5,
    detect_capture_delay=0.2,
)
