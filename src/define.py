"""座標・ハッシュなど固定データ。

全座標は1080×1920の縦画像（回転後）に対応する。
"""

import imagehash
from PIL import Image
from pathlib import Path

from src.logger import get_logger
from src.screen_layout import DETECT, INFO, PLAY, RESULT, SELECT, TIMING

logger = get_logger(__name__)

_RESOURCES = Path("resources")


def _hash(filename: str) -> imagehash.ImageHash | None:
    """resourcesフォルダのPNG画像をaverage_hashに変換する。ファイルが無ければNoneを返す。"""
    path = _RESOURCES / filename
    if not path.exists():
        logger.warning(f"参照画像が見つかりません: {path}")
        return None
    return imagehash.average_hash(Image.open(path))


def _hash_dict(prefix: str, indices) -> dict:
    """prefix{i}.png (i in indices) を {i: hash} の辞書にまとめる。"""
    return {i: _hash(f"{prefix}{i}.png") for i in indices}


# ─── 画面識別用の座標 ─────────────────────────────────────────────────────────
RECT_ONSELECT = DETECT.onselect.box
RECT_ONDETECT = DETECT.ondetect.box
RECT_ONPLAY1 = DETECT.onplay1.box
RECT_ONPLAY2 = DETECT.onplay2.box
RECT_ONRESULT_VAL0 = DETECT.onresult_val0.box
RECT_ONRESULT_VAL1 = DETECT.onresult_val1.box
RECT_ONRESULT_HEAD = DETECT.onresult_head.box

# ─── 画面識別用の基準ハッシュ ────────────────────────────────────────────────
HASH_ONSELECT = _hash("onselect.png")
HASH_ONDETECT = _hash("ondetect.png")
HASH_ONPLAY1 = _hash("onplay1.png")
HASH_ONPLAY2 = _hash("onplay2.png")
HASH_ONRESULT1 = _hash("onresult.png")
HASH_ONRESULT2 = _hash("onresult2.png")
HASH_ONRESULT_HEAD = _hash("result_head.png")

# detect画面: ハッシュ一致 AND RGB輝度閾値でフィルタ（既存sdvx_helperと同方式）
ONDETECT_RGBSUM_THRESHOLD = 4000000

# result_head は任意の追加判定
ONRESULT_ENABLE_HEAD: bool = DETECT.onresult_enable_head

# detect後の待機時間（秒）
DETECT_WAIT: float = TIMING.detect_wait
# 曲情報画面の切り出し待機時間（秒）。
# SDVX側の遷移が高速なため、旧detect_waitほど待たず、白フェードを避ける程度に留める。
DETECT_CAPTURE_DELAY: float = TIMING.detect_capture_delay

# ─── 選曲画面 座標 ────────────────────────────────────────────────────────────
RECT_SELECT_JACKET = SELECT.jacket.box
RECT_SELECT_NOV = SELECT.novice.box
RECT_SELECT_ADV = SELECT.advanced.box
RECT_SELECT_EXH = SELECT.exhaust.box
RECT_SELECT_APPEND = SELECT.append.box
RECT_SELECT_LAMP = SELECT.lamp.box
RECT_SELECT_ARCADE = SELECT.arcade.box
RECT_HAS_EXSCORE = SELECT.has_exscore.box
# スコア数字座標（大4桁 + 小4桁 = 8桁）
RECT_SELECT_SCORE_LARGE = [r.box for r in SELECT.score_large]
RECT_SELECT_SCORE_SMALL = [r.box for r in SELECT.score_small]
RECT_SELECT_EXSCORE = [r.box for r in SELECT.exscore]

# ─── detect画面（楽曲情報）座標 ──────────────────────────────────────────────
RECT_INFO_JACKET = INFO.jacket.box
RECT_INFO_TITLE = INFO.title.box
RECT_INFO_LV = INFO.level.box
RECT_INFO_DIFF = INFO.difficulty.box
RECT_INFO_BPM = INFO.bpm.box
RECT_INFO_EF = INFO.effector.box
RECT_INFO_ILLUST = INFO.illustrator.box

# ─── プレー画面 座標 ──────────────────────────────────────────────────────────
RECT_GAUGE = PLAY.gauge.box
RECT_LAMP = PLAY.lamp.box
RECT_VF = PLAY.vf.box
RECT_CLASS = PLAY.player_class.box
RECT_BLASTERMAX = PLAY.blastermax.box

GAUGE_CLEAR_THRESHOLD: int = PLAY.gauge_clear_threshold
GAUGE_HARD_THRESHOLD: int = PLAY.gauge_hard_threshold

# ─── リザルト画面 座標 ────────────────────────────────────────────────────────
RECT_RESULT_JACKET = RESULT.jacket.box
RECT_RESULT_DIFF = RESULT.difficulty.box
RECT_RESULT_MODE = RESULT.score_mode_detect_marker.box

# ─── リザルト画面 スコア座標 ──────────────────────────────────────────────────
# スコア (10M形式, 8桁: 大字体4桁 + 小字体4桁)
RECT_RESULT_SCORE_LARGE = [r.box for r in RESULT.score_large]
RECT_RESULT_SCORE_SMALL = [r.box for r in RESULT.score_small]
# EXスコア (5桁)
RECT_RESULT_EXSCORE = [r.box for r in RESULT.exscore]
# 自己べスコア (8桁、小字体サイズ)
RECT_RESULT_BESTSCORE = [r.box for r in RESULT.bestscore]
# 自己べEXスコア (5桁)
RECT_RESULT_BESTEXSCORE = [r.box for r in RESULT.bestexscore]

# ─── ランプ・ゲージ・難易度 判定用画像ハッシュ ────────────────────────────────
HASH_LAMP = {
    "clear": _hash("lamp_clear.png"),
    "failed": _hash("lamp_failed.png"),
    "puc": _hash("lamp_puc.png"),
    "uc": _hash("lamp_uc.png"),
}

HASH_GAUGE = {
    "normal": _hash("gauge_normal.png"),
    "hard": _hash("gauge_hard.png"),
}

HASH_DIFFICULTY = {
    "nov": _hash("difficulty_nov.png"),
    "adv": _hash("difficulty_adv.png"),
    "exh": _hash("difficulty_exh.png"),
}

HASH_SELECT_LAMP = {
    "clear": _hash("select_lamp_clear.png"),
    "failed": _hash("select_lamp_failed.png"),
    "exh": _hash("select_lamp_exh.png"),
    "hard": _hash("select_lamp_hard.png"),
    "puc": _hash("select_lamp_puc.png"),
    "uc": _hash("select_lamp_uc.png"),
}

HASH_HAS_EXSCORE = _hash("has_exscore.png")

HASH_RESULT_MODE_SCORE = _hash("result_mode_score.png")

# ─── 数字認識用画像ハッシュ ──────────────────────────────────────────────────
# リザルトスコア大字体 (51×50px, 数字0-9)
HASH_RESULT_SCORE_LARGE: dict = _hash_dict("result_score_l", range(10))
# リザルトスコア小字体 (31×30px, 数字0-9)
HASH_RESULT_SCORE_SMALL: dict = _hash_dict("result_score_s", range(10))
# リザルトEXスコア (数字0-9)
HASH_RESULT_EXSCORE: dict = _hash_dict("result_exscore_", range(10))
# 選曲スコア (数字0-9)
HASH_SELECT_SCORE: dict = _hash_dict("select_score_s", range(10))
# 選曲EXスコア (数字0-9)
HASH_SELECT_EXSCORE: dict = _hash_dict("select_exscore_", range(10))
# 自己べスコア (13×13px, 数字0-9)
HASH_RESULT_BESTSCORE: dict = _hash_dict("result_bestscore_", range(10))
# 自己べEXスコア (13×13px, 数字0-9)
HASH_RESULT_BESTEXSCORE: dict = _hash_dict("result_bestexscore_", range(10))
