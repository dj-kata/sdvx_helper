"""SDVX向け共通ユーティリティ関数"""
from .classes import difficulty, clear_lamp
import hashlib
import re
from PIL import Image

from src.logger import get_logger
logger = get_logger(__name__)

from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from src.ui_jp import UIText


def load_ui_text(config):
    """設定に応じて適切な言語ファイルをロードする"""
    if config.language == 'en':
        from src.ui_en import UIText
    else:
        from src.ui_jp import UIText
    return UIText


# ─── 譜面ID ──────────────────────────────────────────────────────────────────

def calc_chart_id(title: str, diff: difficulty) -> str | None:
    """楽曲IDを計算する（sha256(title + difficulty.name)）。
    SDVXはplay_styleがないためdifficultyのみをキーとする。
    """
    if title and diff:
        key = title + diff.name
        return hashlib.sha256(key.encode('utf-8')).hexdigest()
    return None


# ─── 表示用文字列 ─────────────────────────────────────────────────────────────

def get_chart_name(diff: difficulty) -> str:
    """NOV / ADV / EXH / MXM / INF のような難易度略称を返す"""
    if diff:
        return str(diff)
    return ''


def get_title_with_chart(title: str, diff: difficulty) -> str:
    """'AA (EXH)' のような表示用タイトル文字列を返す"""
    if title and diff:
        return f"{title} ({get_chart_name(diff)})"
    return title or ''


# ─── グレード ─────────────────────────────────────────────────────────────────

# SDVX グレード境界値（スコア10,000,000基準）
_GRADE_THRESHOLDS = [
    (9_900_000, 'S'),
    (9_800_000, 'AAA+'),
    (9_700_000, 'AAA'),
    (9_500_000, 'AA+'),
    (9_200_000, 'AA'),
    (8_900_000, 'A+'),
    (8_600_000, 'A'),
    (8_000_000, 'B'),
    (7_000_000, 'C'),
    (0,         'D'),
]

_GRADE_COEF = {
    'S':    1.05,
    'AAA+': 1.02,
    'AAA':  1.00,
    'AA+':  0.97,
    'AA':   0.94,
    'A+':   0.91,
    'A':    0.88,
    'B':    0.85,
    'C':    0.82,
    'D':    0.80,
}


def calc_grade(score: int) -> str:
    """スコアからグレード文字列を返す（S / AAA+ / AAA / ... / D）"""
    for threshold, grade in _GRADE_THRESHOLDS:
        if score >= threshold:
            return grade
    return 'D'


def get_grade_coef(score: int) -> float:
    """VF計算用のグレード係数を返す"""
    return _GRADE_COEF.get(calc_grade(score), 0.80)


# ─── ランプ変換 ───────────────────────────────────────────────────────────────

_LAMP_MAP = {
    'NO PLAY':  clear_lamp.noplay,
    'PLAYED':   clear_lamp.played,
    'FAILED':   clear_lamp.played,   # CSV旧形式
    'CLEAR':    clear_lamp.clear,
    'COMP':     clear_lamp.clear,    # portal/CSV旧形式
    'EXC-COMP': clear_lamp.exc,
    'EX_COMP':  clear_lamp.exc,      # portal形式
    'EXC':      clear_lamp.exc,      # CSV旧形式
    'MAXXIVE':  clear_lamp.maxxive,
    'MAX_COMP': clear_lamp.maxxive,  # portal形式
    'UC':       clear_lamp.uc,
    'PUC':      clear_lamp.puc,
}


def convert_lamp(lamp_str: str) -> clear_lamp:
    """ランプ用文字列をEnumに変換。未知の値はnoplayを返す。"""
    return _LAMP_MAP.get(lamp_str, clear_lamp.noplay)


# ─── 難易度変換 ───────────────────────────────────────────────────────────────

_DIFFICULTY_MAP = {
    'NOV': difficulty.novice,
    'ADV': difficulty.advanced,
    'EXH': difficulty.exhaust,
    'MXM': difficulty.maximum,
    'INF': difficulty.maximum,
    'GRV': difficulty.maximum,
    'HVN': difficulty.maximum,
    'VVD': difficulty.maximum,
    'XCD': difficulty.maximum,
}


def convert_difficulty(diff_str: str) -> difficulty | None:
    """難易度の文字列をEnumに変換"""
    return _DIFFICULTY_MAP.get(diff_str.upper() if diff_str else '')


# ─── 文字列エスケープ ────────────────────────────────────────────────────────

def escape_for_filename(text: str) -> str:
    """Windowsのファイル名に使えない文字を除去する"""
    return re.sub(r'[\\/:*?"<>|]', '', text)


def escape_for_csv(text: str) -> str:
    """CSVに使えない文字を変換する"""
    return text.replace(',', '，')
