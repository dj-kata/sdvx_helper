"""座標・ハッシュなど固定データ。resources/params.json と PNG画像から生成する。

全座標は1080×1920の縦画像（回転後）に対応する。
"""
import json
import imagehash
import traceback
from PIL import Image
from pathlib import Path

from src.logger import get_logger
logger = get_logger(__name__)

_RESOURCES = Path('resources')

# ─── params.json 読み込み ────────────────────────────────────────────────────
try:
    with open(_RESOURCES / 'params.json', encoding='utf-8') as _f:
        params: dict = json.load(_f)
except Exception:
    logger.error(f"params.json の読み込みに失敗しました:\n{traceback.format_exc()}")
    params = {}


def _rect(prefix: str) -> tuple:
    """params.jsonから (left, top, right, bottom) のtupleを返す。img.crop()に直接渡せる。"""
    sx = params[f'{prefix}_sx']
    sy = params[f'{prefix}_sy']
    return (sx, sy, sx + params[f'{prefix}_w'], sy + params[f'{prefix}_h'])


def _hash(filename: str) -> imagehash.ImageHash | None:
    """resourcesフォルダのPNG画像をaverage_hashに変換する。ファイルが無ければNoneを返す。"""
    path = _RESOURCES / filename
    if not path.exists():
        logger.warning(f"参照画像が見つかりません: {path}")
        return None
    return imagehash.average_hash(Image.open(path))


def _hash_dict(prefix: str, indices) -> dict:
    """prefix{i}.png (i in indices) を {i: hash} の辞書にまとめる。"""
    return {i: _hash(f'{prefix}{i}.png') for i in indices}


# ─── 画面識別用の座標 ─────────────────────────────────────────────────────────
RECT_ONSELECT      = _rect('onselect')
RECT_ONDETECT      = _rect('ondetect')
RECT_ONPLAY1       = _rect('onplay_val1')
RECT_ONPLAY2       = _rect('onplay_val2')
RECT_ONRESULT_VAL0 = _rect('onresult_val0')
RECT_ONRESULT_VAL1 = _rect('onresult_val1')
RECT_ONRESULT_HEAD = _rect('onresult_head')

# ─── 画面識別用の基準ハッシュ ────────────────────────────────────────────────
HASH_ONSELECT      = _hash('onselect.png')
HASH_ONDETECT      = _hash('ondetect.png')
HASH_ONPLAY1       = _hash('onplay1.png')
HASH_ONPLAY2       = _hash('onplay2.png')
HASH_ONRESULT1     = _hash('onresult.png')
HASH_ONRESULT2     = _hash('onresult2.png')
HASH_ONRESULT_HEAD = _hash('result_head.png')

# detect画面: ハッシュ一致 AND RGB輝度閾値でフィルタ（既存sdvx_helperと同方式）
ONDETECT_RGBSUM_THRESHOLD = 4000000

# result_head は任意の追加判定（params.jsonで有効/無効切り替え）
ONRESULT_ENABLE_HEAD: bool = bool(params.get('onresult_enable_head', 0))

# detect後の待機時間（秒）
DETECT_WAIT: float = params.get('detect_wait', 1.5)
# 曲情報画面の切り出し待機時間（秒）。
# SDVX側の遷移が高速なため、旧detect_waitほど待たず、白フェードを避ける程度に留める。
DETECT_CAPTURE_DELAY: float = params.get('detect_capture_delay', 0.2)

# ─── 選曲画面 座標 ────────────────────────────────────────────────────────────
RECT_SELECT_JACKET = _rect('select_jacket')
RECT_SELECT_NOV    = _rect('select_nov')
RECT_SELECT_ADV    = _rect('select_adv')
RECT_SELECT_EXH    = _rect('select_exh')
RECT_SELECT_APPEND = _rect('select_APPEND')
RECT_SELECT_LAMP   = _rect('select_lamp')
RECT_SELECT_ARCADE = _rect('select_arcade')
RECT_HAS_EXSCORE   = _rect('has_exscore')
# スコア数字座標（大4桁 + 小4桁 = 8桁）
RECT_SELECT_SCORE_LARGE = [_rect(f'select_score_large_{i}') for i in range(4)]
RECT_SELECT_SCORE_SMALL = [_rect(f'select_score_small_{i}') for i in range(4, 8)]
RECT_SELECT_EXSCORE     = [_rect(f'select_exscore_{i}') for i in range(5)]

# ─── detect画面（楽曲情報）座標 ──────────────────────────────────────────────
RECT_INFO_JACKET = _rect('info_jacket')
RECT_INFO_TITLE  = _rect('info_title')
RECT_INFO_LV     = _rect('info_lv')
RECT_INFO_DIFF   = _rect('info_diff')
RECT_INFO_BPM    = _rect('info_bpm')
RECT_INFO_EF     = _rect('info_ef')
RECT_INFO_ILLUST = _rect('info_illust')

# ─── プレー画面 座標 ──────────────────────────────────────────────────────────
RECT_GAUGE      = _rect('gauge')
RECT_LAMP       = _rect('lamp')
RECT_VF         = _rect('vf')
RECT_CLASS      = _rect('class')
RECT_BLASTERMAX = _rect('blastermax')

GAUGE_CLEAR_THRESHOLD: int = params.get('gauge_clear_threshold', 10)
GAUGE_HARD_THRESHOLD:  int = params.get('gauge_hard_threshold', 15)

# ─── リザルト画面 座標 ────────────────────────────────────────────────────────
RECT_RESULT_JACKET  = _rect('result_jacket')
RECT_RESULT_DIFF    = _rect('log_crop_difficulty')  # sx=55,sy=870,w=138,h=30

# ─── リザルト画面 スコア座標 ──────────────────────────────────────────────────
# スコア (10M形式, 8桁: 大字体4桁 + 小字体4桁)
RECT_RESULT_SCORE_LARGE = [_rect(f'result_score_large_{i}') for i in range(4)]
RECT_RESULT_SCORE_SMALL = [_rect(f'result_score_small_{i}') for i in range(4, 8)]
# EXスコア (5桁)
RECT_RESULT_EXSCORE     = [_rect(f'result_exscore_{i}') for i in range(5)]
# 自己べスコア (8桁、小字体サイズ)
RECT_RESULT_BESTSCORE   = [_rect(f'result_bestscore_{i}') for i in range(8)]
# 自己べEXスコア (5桁)
RECT_RESULT_BESTEXSCORE = [_rect(f'result_bestexscore_{i}') for i in range(5)]

# ─── ランプ・ゲージ・難易度 判定用画像ハッシュ ────────────────────────────────
HASH_LAMP = {
    'clear':  _hash('lamp_clear.png'),
    'failed': _hash('lamp_failed.png'),
    'puc':    _hash('lamp_puc.png'),
    'uc':     _hash('lamp_uc.png'),
}

HASH_GAUGE = {
    'normal': _hash('gauge_normal.png'),
    'hard':   _hash('gauge_hard.png'),
}

HASH_DIFFICULTY = {
    'nov': _hash('difficulty_nov.png'),
    'adv': _hash('difficulty_adv.png'),
    'exh': _hash('difficulty_exh.png'),
}

HASH_SELECT_LAMP = {
    'clear':  _hash('select_lamp_clear.png'),
    'failed': _hash('select_lamp_failed.png'),
    'exh':    _hash('select_lamp_exh.png'),
    'hard':   _hash('select_lamp_hard.png'),
    'puc':    _hash('select_lamp_puc.png'),
    'uc':     _hash('select_lamp_uc.png'),
}

HASH_HAS_EXSCORE = _hash('has_exscore.png')

# ─── 数字認識用画像ハッシュ ──────────────────────────────────────────────────
# リザルトスコア大字体 (51×50px, 数字0-9)
HASH_RESULT_SCORE_LARGE: dict = _hash_dict('result_score_l', range(10))
# リザルトスコア小字体 (31×30px, 数字0-9)
HASH_RESULT_SCORE_SMALL: dict = _hash_dict('result_score_s', range(10))
# リザルトEXスコア (数字0-9)
HASH_RESULT_EXSCORE: dict     = _hash_dict('result_exscore_', range(10))
# 選曲スコア (数字0-9)
HASH_SELECT_SCORE:  dict      = _hash_dict('select_score_s', range(10))
# 選曲EXスコア (数字0-9)
HASH_SELECT_EXSCORE: dict     = _hash_dict('select_exscore_', range(10))
# 自己べスコア (13×13px, 数字0-9)
HASH_RESULT_BESTSCORE: dict   = _hash_dict('result_bestscore_', range(10))
# 自己べEXスコア (13×13px, 数字0-9)
HASH_RESULT_BESTEXSCORE: dict = _hash_dict('result_bestexscore_', range(10))
