"""プレーログ画像生成モジュール。

result_database.get_today_results() の返り値から
out/summary_full.png と out/summary_small.png を生成する。

2 つのモードを提供する:
  generate_summary()                 … OneResult データからテキスト描画で生成
  generate_summary_from_items()       … 現在画面から切り出したパーツで生成
  generate_summary_from_screenshots() … 保存済みリザルト画像を切り抜いて生成 (v1 方式)

フォント・ランプ画像はモジュールレベルでキャッシュし、
初回呼び出し時にのみロードする。
"""
from __future__ import annotations

import os
import threading
from dataclasses import dataclass
from typing import Dict, List, Optional, TYPE_CHECKING

import imagehash
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from src.classes import clear_lamp, difficulty
from src.logger import get_logger

if TYPE_CHECKING:
    from src.result import OneResult

logger = get_logger(__name__)

# ─── レイアウト定数 ──────────────────────────────────────────────────────────

_LOG_MARGIN  = 20
_LOG_ROWSIZE = 40
_LOG_MAXNUM  = 30

_FULL_WIDTH  = 960
_SMALL_WIDTH = 590

# 難易度カラーバーの色 (RGB)
_DIFF_COLORS = {
    difficulty.novice:   (64,  128, 255),
    difficulty.advanced: (255, 204,   0),
    difficulty.exhaust:  (255,  64,  64),
    difficulty.maximum:  (200,  64, 255),
}

# clear_lamp → resources/ 内ランプ画像ファイル名
_LAMP_FILE: Dict[clear_lamp, str] = {
    clear_lamp.puc:     'log_lamp_puc.png',
    clear_lamp.uc:      'log_lamp_uc.png',
    clear_lamp.exc:     'log_lamp_hard.png', # 指摘に基づき修正: EXCESSIVE CLEAR (Hard)
    clear_lamp.maxxive: 'log_lamp_exh.png',  # 指摘に基づき修正: MAXXIVE CLEAR
    clear_lamp.clear:   'log_lamp_clear.png',
    clear_lamp.played:  'log_lamp_failed.png',
    clear_lamp.noplay:  'log_lamp_failed.png',
}

_RES_DIR = 'resources'
_OUT_DIR = 'out'

# テキスト版レイアウト座標
_DIFF_BAR_X   = 10
_DIFF_BAR_W   = 8
_DIFF_BAR_Y_OFF = 5
_DIFF_BAR_H   = 30
_TITLE_X      = 90
_TITLE_Y_OFF  = 10
_SCORE_X_F    = 680
_GRADE_X_F    = 760
_LAMP_X_F     = 808
_VF_X_F       = 848
_SCORE_Y_OFF  = 10
_GRADE_Y_OFF  = 11
_LAMP_Y_OFF   = 7
_VF_Y_OFF     = 11
_SCORE_X_S    = 420
_LAMP_X_S     = 450

# ─── モジュールレベルキャッシュ ───────────────────────────────────────────────

_font_l:     Optional[ImageFont.ImageFont] = None  # タイトル・スコア用 (18pt)
_font_s:     Optional[ImageFont.ImageFont] = None  # グレード・VF 用 (14pt)
_lamp_cache: Optional[Dict[clear_lamp, Optional[Image.Image]]] = None
_lock = threading.Lock()


@dataclass
class ResultSummaryItem:
    """summary_*.png へ貼るためにリザルト画面から切り出したパーツ一式。"""
    timestamp: int
    jacket: Image.Image
    diff_bar: Image.Image
    title: Image.Image
    title_small: Image.Image
    score: Image.Image
    rank: Image.Image
    rate: Image.Image
    lamp: clear_lamp


def _ensure_cache() -> None:
    """フォントとランプ画像を初回のみロードする。"""
    global _font_l, _font_s, _lamp_cache
    if _font_l is not None:
        return
    with _lock:
        if _font_l is not None:
            return
        _font_l = _load_font(18)
        _font_s = _load_font(14)
        _lamp_cache = _load_lamp_cache()
        logger.debug('summary_generator: フォント・ランプ画像をキャッシュしました')


def _load_font(size: int) -> ImageFont.ImageFont:
    for path in (
        '/mnt/c/Windows/Fonts/meiryo.ttc',
        '/mnt/c/Windows/Fonts/msgothic.ttc',
        '/mnt/c/Windows/Fonts/YuGothM.ttc',
        '/mnt/c/Windows/Fonts/yugothb.ttc',
        '/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc',
        '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
    ):
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except Exception:
                pass
    return ImageFont.load_default()


def _load_lamp_cache() -> Dict[clear_lamp, Optional[Image.Image]]:
    cache: Dict[clear_lamp, Optional[Image.Image]] = {}
    for lk, fname in _LAMP_FILE.items():
        path = os.path.join(_RES_DIR, fname)
        try:
            cache[lk] = Image.open(path).convert('RGBA')
        except Exception:
            cache[lk] = None
    return cache


# ─── テキスト描画版 ──────────────────────────────────────────────────────────

def generate_summary(results: List['OneResult'], bg_alpha: int = 200) -> bool:
    """今日のリザルトリストからテキスト描画でサマリー画像を生成して out/ に保存する。

    メインスレッドをブロックしないようバックグラウンドスレッドで実行する。
    """
    # スレッド内で実行して main thread をブロックしない
    def _run():
        _generate_summary_sync(results, bg_alpha)
    threading.Thread(target=_run, daemon=True).start()
    return True


def _generate_summary_sync(results: List['OneResult'], bg_alpha: int) -> bool:
    """generate_summary の同期実行版（テスト・直接呼び出し用）。"""
    try:
        _ensure_cache()
        target = results[:_LOG_MAXNUM]
        if not target:
            logger.debug('サマリー生成スキップ: リザルトなし')
            return False

        h = _LOG_MARGIN * 2 + _LOG_MAXNUM * _LOG_ROWSIZE
        bg_full  = Image.new('RGBA', (_FULL_WIDTH,  h), (0, 0, 0, bg_alpha))
        bg_small = Image.new('RGBA', (_SMALL_WIDTH, h), (0, 0, 0, bg_alpha))

        for idx, r in enumerate(target):
            row_y = _LOG_MARGIN + _LOG_ROWSIZE * idx
            _draw_row(bg_full, bg_small, r, row_y)

        os.makedirs(_OUT_DIR, exist_ok=True)
        bg_full.save(f'{_OUT_DIR}/summary_full.png')
        bg_small.save(f'{_OUT_DIR}/summary_small.png')
        logger.debug(f'テキスト版サマリー生成完了: {len(target)} 件')
        return True

    except Exception:
        import traceback
        logger.error(f'テキスト版サマリー生成エラー:\n{traceback.format_exc()}')
        return False


def _draw_row(bg_full, bg_small, result, row_y):
    diff_color = _DIFF_COLORS.get(result.difficulty, (128, 128, 128))
    lamp_img   = _lamp_cache.get(result.lamp)  # type: ignore[index]
    score_str  = f'{result.score:,}' if result.score is not None else '---'
    grade_str  = result.grade
    vf_str     = f'{result.vf / 1000:.3f}' if result.vf else ''

    _draw_to(bg_full,  result.title or '', score_str, grade_str, vf_str,
             diff_color, lamp_img, row_y, is_full=True)
    _draw_to(bg_small, result.title or '', score_str, None,       None,
             diff_color, lamp_img, row_y, is_full=False)


def _draw_to(img, title, score_str, grade_str, vf_str,
             diff_color, lamp_img, row_y, is_full: bool):
    draw = ImageDraw.Draw(img)

    bar_y0 = row_y + _DIFF_BAR_Y_OFF
    bar_y1 = bar_y0 + _DIFF_BAR_H
    draw.rectangle(
        [(_DIFF_BAR_X, bar_y0), (_DIFF_BAR_X + _DIFF_BAR_W, bar_y1)],
        fill=diff_color,
    )

    score_x = _SCORE_X_F if is_full else _SCORE_X_S
    lamp_x  = _LAMP_X_F  if is_full else _LAMP_X_S

    title_max_w = score_x - _TITLE_X - 15
    title_text = _fit_text(draw, title, _font_l, title_max_w)  # type: ignore[arg-type]
    draw.text((_TITLE_X, row_y + _TITLE_Y_OFF), title_text,
              font=_font_l, fill=(255, 255, 255))

    _draw_right(draw, score_x, row_y + _SCORE_Y_OFF, score_str, _font_l, (255, 255, 255))  # type: ignore[arg-type]

    if is_full:
        if grade_str:
            draw.text((_GRADE_X_F, row_y + _GRADE_Y_OFF), grade_str,
                      font=_font_s, fill=(255, 220, 100))
        if vf_str:
            draw.text((_VF_X_F, row_y + _VF_Y_OFF), vf_str,
                      font=_font_s, fill=(160, 255, 160))

    if lamp_img is not None:
        img.paste(lamp_img, (lamp_x, row_y + _LAMP_Y_OFF), lamp_img)


# ─── スクリーンショット切り抜き版 ─────────────────────────────────────────────

def generate_summary_from_screenshots(
    image_dir: str,
    start_time: int,
    bg_alpha: int = 200,
) -> bool:
    """保存済みリザルト画像を切り抜いてサマリー画像を生成する (v1 方式)。

    image_dir にある sdvx_*.png のうち start_time 以降のものを対象とする。
    バックグラウンドスレッドで実行する。
    """
    def _run():
        _generate_from_screenshots_sync(image_dir, start_time, bg_alpha)
    threading.Thread(target=_run, daemon=True).start()
    return True


def capture_summary_item_from_screen(
    img: Image.Image,
    timestamp: int,
) -> Optional[ResultSummaryItem]:
    """現在のリザルト画面から summary 用パーツを切り出して保持する。"""
    try:
        from src.define import params as _params

        _ensure_cache()
        src = img.convert('RGB')

        def _crop(prefix: str) -> Image.Image:
            sx = _params[f'log_crop_{prefix}_sx']
            sy = _params[f'log_crop_{prefix}_sy']
            w  = _params[f'log_crop_{prefix}_w']
            h  = _params[f'log_crop_{prefix}_h']
            return src.crop((sx, sy, sx + w, sy + h)).copy()

        return ResultSummaryItem(
            timestamp=timestamp,
            jacket=_crop('jacket').resize((36, 36)),
            diff_bar=_crop('difficulty').resize((69, 15)),
            title=_crop('title'),
            title_small=_crop('title_small'),
            score=_crop('score').resize((86, 20)),
            rank=_crop('rank').resize((37, 25)),
            rate=_crop('rate').resize((80, 20)),
            lamp=_detect_lamp_from_screenshot(src, _params),
        )
    except Exception:
        import traceback
        logger.warning(f'summary 用リザルト切り出しエラー:\n{traceback.format_exc()}')
        return None


def generate_summary_from_items(
    items: List[ResultSummaryItem],
    bg_alpha: int = 200,
) -> bool:
    """保持しているリザルト切り出しパーツから summary_*.png を生成する。"""
    snapshot = list(items)

    def _run():
        _generate_from_items_sync(snapshot, bg_alpha)
    threading.Thread(target=_run, daemon=True).start()
    return True


def _generate_from_items_sync(
    items: List[ResultSummaryItem],
    bg_alpha: int,
) -> bool:
    try:
        from src.define import params as _params

        _ensure_cache()
        target = sorted(items, key=lambda item: item.timestamp, reverse=True)[:_LOG_MAXNUM]
        if not target:
            logger.debug('スクリーンショット版サマリー生成スキップ: 対象パーツなし')
            return False

        h = _LOG_MARGIN * 2 + _LOG_MAXNUM * _LOG_ROWSIZE
        bg_full  = Image.new('RGBA', (_FULL_WIDTH,  h), (0, 0, 0, bg_alpha))
        bg_small = Image.new('RGBA', (_SMALL_WIDTH, h), (0, 0, 0, bg_alpha))

        for idx, item in enumerate(target):
            row_y = _LOG_MARGIN + _LOG_ROWSIZE * idx
            _put_result_summary_item(item, bg_full, bg_small, row_y, _params)

        os.makedirs(_OUT_DIR, exist_ok=True)
        bg_full.save(f'{_OUT_DIR}/summary_full.png')
        bg_small.save(f'{_OUT_DIR}/summary_small.png')
        logger.debug(f'スクリーンショット版サマリー生成完了: {len(target)} 件')
        return True

    except Exception:
        import traceback
        logger.error(f'スクリーンショット版サマリー生成エラー:\n{traceback.format_exc()}')
        return False


def _generate_from_screenshots_sync(
    image_dir: str,
    start_time: int,
    bg_alpha: int,
) -> bool:
    try:
        import glob

        _ensure_cache()

        # start_time 以降のファイルを新しい順に取得
        all_files = sorted(
            glob.glob(os.path.join(image_dir, 'sdvx_*.png')),
            key=os.path.getmtime,
            reverse=True,
        )
        files = [f for f in all_files if os.path.getmtime(f) >= start_time]
        files = files[:_LOG_MAXNUM]

        if not files:
            logger.debug('スクリーンショット版サマリー生成スキップ: 対象ファイルなし')
            return False

        items: List[ResultSummaryItem] = []
        for f in files:
            try:
                with Image.open(f) as img:
                    item = capture_summary_item_from_screen(img, int(os.path.getmtime(f)))
                if item is not None:
                    items.append(item)
            except Exception:
                import traceback
                logger.warning(f'スクリーンショット処理エラー ({f}):\n{traceback.format_exc()}')

        return _generate_from_items_sync(items, bg_alpha)

    except Exception:
        import traceback
        logger.error(f'スクリーンショット版サマリー生成エラー:\n{traceback.format_exc()}')
        return False


def _put_result_from_screenshot(
    img: Image.Image,
    bg_full: Image.Image,
    bg_small: Image.Image,
    row_y: int,
    params: dict,
) -> None:
    """1枚のリザルト画像からパーツを切り出して bg_full / bg_small に貼り付ける。"""

    def _crop(prefix: str) -> Image.Image:
        sx = params[f'log_crop_{prefix}_sx']
        sy = params[f'log_crop_{prefix}_sy']
        w  = params[f'log_crop_{prefix}_w']
        h  = params[f'log_crop_{prefix}_h']
        return img.crop((sx, sy, sx + w, sy + h))

    # パーツ切り出し・リサイズ (v1 と同じサイズ)
    jacket    = _crop('jacket').resize((36, 36))
    diff_bar  = _crop('difficulty').resize((69, 15))
    title_img = _crop('title')
    title_sml = _crop('title_small')
    score_img = _crop('score').resize((86, 20))
    rank_img  = _crop('rank').resize((37, 25))
    rate_img  = _crop('rate').resize((80, 20))

    # ランプ検出
    lamp = _detect_lamp_from_screenshot(img, params)
    lamp_img = (_lamp_cache or {}).get(lamp)  # type: ignore[attr-defined]

    # full 画像に貼り付け
    _paste(bg_full, jacket,    params['log_pos_jacket_sx'],     params['log_pos_jacket_sy'],     row_y)
    _paste(bg_full, diff_bar,  params['log_pos_difficulty_sx'], params['log_pos_difficulty_sy'], row_y)
    _paste(bg_full, title_img, params['log_pos_title_sx'],      params['log_pos_title_sy'],      row_y)
    _paste(bg_full, score_img, params['log_pos_score_sx'],      params['log_pos_score_sy'],      row_y)
    _paste(bg_full, rank_img,  params['log_pos_rank_sx'],       params['log_pos_rank_sy'],       row_y)
    _paste(bg_full, rate_img,  params['log_pos_rate_sx'],       params['log_pos_rate_sy'],       row_y)
    if lamp_img is not None:
        _paste(bg_full, lamp_img, params['log_pos_lamp_sx'], params['log_pos_lamp_sy'], row_y,
               mask=lamp_img)

    # small 画像に貼り付け
    _paste(bg_small, jacket,    params['log_pos_jacket_small_sx'],     params['log_pos_jacket_small_sy'],     row_y)
    _paste(bg_small, diff_bar,  params['log_pos_difficulty_small_sx'], params['log_pos_difficulty_small_sy'], row_y)
    _paste(bg_small, title_sml, params['log_pos_title_small_sx'],      params['log_pos_title_small_sy'],      row_y)
    _paste(bg_small, score_img, params['log_pos_score_small_sx'],      params['log_pos_score_small_sy'],      row_y)
    if lamp_img is not None:
        _paste(bg_small, lamp_img, params['log_pos_lamp_small_sx'], params['log_pos_lamp_small_sy'], row_y,
               mask=lamp_img)


def _put_result_summary_item(
    item: ResultSummaryItem,
    bg_full: Image.Image,
    bg_small: Image.Image,
    row_y: int,
    params: dict,
) -> None:
    """保持済みパーツを bg_full / bg_small に貼り付ける。"""
    lamp_img = (_lamp_cache or {}).get(item.lamp)  # type: ignore[attr-defined]

    _paste(bg_full, item.jacket,   params['log_pos_jacket_sx'],     params['log_pos_jacket_sy'],     row_y)
    _paste(bg_full, item.diff_bar, params['log_pos_difficulty_sx'], params['log_pos_difficulty_sy'], row_y)
    _paste(bg_full, item.title,    params['log_pos_title_sx'],      params['log_pos_title_sy'],      row_y)
    _paste(bg_full, item.score,    params['log_pos_score_sx'],      params['log_pos_score_sy'],      row_y)
    _paste(bg_full, item.rank,     params['log_pos_rank_sx'],       params['log_pos_rank_sy'],       row_y)
    _paste(bg_full, item.rate,     params['log_pos_rate_sx'],       params['log_pos_rate_sy'],       row_y)
    if lamp_img is not None:
        _paste(bg_full, lamp_img, params['log_pos_lamp_sx'], params['log_pos_lamp_sy'], row_y,
               mask=lamp_img)

    _paste(bg_small, item.jacket,      params['log_pos_jacket_small_sx'],     params['log_pos_jacket_small_sy'],     row_y)
    _paste(bg_small, item.diff_bar,    params['log_pos_difficulty_small_sx'], params['log_pos_difficulty_small_sy'], row_y)
    _paste(bg_small, item.title_small, params['log_pos_title_small_sx'],      params['log_pos_title_small_sy'],      row_y)
    _paste(bg_small, item.score,       params['log_pos_score_small_sx'],      params['log_pos_score_small_sy'],      row_y)
    if lamp_img is not None:
        _paste(bg_small, lamp_img, params['log_pos_lamp_small_sx'], params['log_pos_lamp_small_sy'], row_y,
               mask=lamp_img)


def _paste(bg: Image.Image, part: Image.Image,
           sx: int, sy: int, row_y: int,
           mask: Optional[Image.Image] = None) -> None:
    """bg に part を (sx, sy + row_y) の位置に貼り付ける。"""
    if mask is not None:
        bg.paste(part, (sx, sy + row_y), mask)
    else:
        bg.paste(part, (sx, sy + row_y))


def _detect_lamp_from_screenshot(img: Image.Image, params: dict) -> clear_lamp:
    """リザルト画像からランプを判定する。"""
    try:
        from src.define import HASH_LAMP, RECT_LAMP, RECT_GAUGE

        lamp_crop = img.crop(RECT_LAMP)
        lamp_hash = imagehash.average_hash(lamp_crop)

        # puc / uc / failed を先に判定
        for key, lk in (('puc', clear_lamp.puc), ('uc', clear_lamp.uc),
                         ('failed', clear_lamp.played)):
            ref = HASH_LAMP.get(key)
            if ref is not None and abs(lamp_hash - ref) < 10:
                return lk

        # "clear" 系 → ゲージ色で細分化
        ref_clear = HASH_LAMP.get('clear')
        if ref_clear is not None and abs(lamp_hash - ref_clear) < 10:
            gauge_arr = np.array(img.crop(RECT_GAUGE))
            rsum = int(gauge_arr[:, :, 0].sum())
            gsum = int(gauge_arr[:, :, 1].sum())
            bsum = int(gauge_arr[:, :, 2].sum())
            if rsum + gsum + bsum > 780000:
                return clear_lamp.exc      # EXC: ゲージが明るい・彩度高い
            elif rsum < gsum:
                return clear_lamp.clear    # ノーマルクリア: 青緑系
            else:
                return clear_lamp.maxxive  # MAXXIVE: 白系・やや暗い

    except Exception:
        import traceback
        logger.debug(f'ランプ判定エラー:\n{traceback.format_exc()}')

    return clear_lamp.played  # フォールバック


# ─── テキスト描画ユーティリティ ───────────────────────────────────────────────

def _fit_text(draw: ImageDraw.ImageDraw, text: str,
              font: ImageFont.ImageFont, max_width: int) -> str:
    if not text:
        return ''
    try:
        while text and draw.textlength(text, font=font) > max_width:
            text = text[:-1]
    except AttributeError:
        try:
            while text and font.getlength(text) > max_width:
                text = text[:-1]
        except Exception:
            text = text[:25]
    return text


def _draw_right(draw: ImageDraw.ImageDraw, x: int, y: int,
                text: str, font: ImageFont.ImageFont, fill: tuple) -> None:
    try:
        draw.text((x, y), text, font=font, fill=fill, anchor='ra')
    except Exception:
        try:
            w = int(font.getlength(text))
        except Exception:
            w = len(text) * 10
        draw.text((x - w, y), text, font=font, fill=fill)
