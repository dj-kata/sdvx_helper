"""SDVX向けスクリーンリーダー。OBSから受け取った画像を解析する。

呼び出し手順:
    reader = ScreenReader(song_db)
    reader.update_screen(pil_image)   # OBSフレームをセット
    mode = reader.detect_screen()     # 現在の画面状態を取得
    if mode == detect_mode.result:
        data = reader.read_from_result()
"""
from __future__ import annotations

import colorsys
import traceback
from typing import Optional

import imagehash
import numpy as np
from PIL import Image

from src.classes import difficulty, clear_lamp, detect_mode, screen_orientation
from src.define import (
    RECT_ONSELECT, RECT_ONDETECT, RECT_ONPLAY1, RECT_ONPLAY2,
    RECT_ONRESULT_VAL0, RECT_ONRESULT_VAL1, RECT_ONRESULT_HEAD,
    HASH_ONSELECT, HASH_ONDETECT, HASH_ONPLAY1, HASH_ONPLAY2,
    HASH_ONRESULT1, HASH_ONRESULT2, HASH_ONRESULT_HEAD,
    ONDETECT_RGBSUM_THRESHOLD, ONRESULT_ENABLE_HEAD,
    RECT_SELECT_JACKET, RECT_SELECT_NOV, RECT_SELECT_ADV, RECT_SELECT_APPEND,
    RECT_SELECT_EXH, RECT_SELECT_LAMP,
    RECT_HAS_EXSCORE,
    RECT_SELECT_SCORE_LARGE, RECT_SELECT_SCORE_SMALL, RECT_SELECT_EXSCORE,
    RECT_INFO_JACKET, RECT_INFO_TITLE, RECT_INFO_LV,
    RECT_INFO_DIFF, RECT_INFO_BPM, RECT_INFO_EF, RECT_INFO_ILLUST,
    RECT_GAUGE, RECT_LAMP,
    RECT_RESULT_JACKET, RECT_RESULT_DIFF,
    RECT_RESULT_SCORE_LARGE, RECT_RESULT_SCORE_SMALL,
    RECT_RESULT_EXSCORE,
    HASH_LAMP, HASH_GAUGE, HASH_DIFFICULTY, HASH_SELECT_LAMP, HASH_HAS_EXSCORE,
    HASH_RESULT_SCORE_LARGE, HASH_RESULT_SCORE_SMALL, HASH_RESULT_EXSCORE,
    HASH_SELECT_SCORE, HASH_SELECT_EXSCORE,
)
from src.songinfo import SongDatabase
from src.logger import get_logger

logger = get_logger(__name__)

# 連続N回認識失敗したら向き再検出
_REDETECT_THRESHOLD = 30

# 正規化後の期待サイズ（縦画像基準）
_EXPECTED_SIZE = (1080, 1920)
# 黒帯判定輝度閾値（0-255）
_BLACKBAR_LUM_TH = 20

# ─── 数字認識 輝度補正パラメータ ───────────────────────────────────────────
_DIGIT_AMBIGUITY_TH  = 4    # 0/8混同: この距離差以内なら輝度で判別
_DIGIT_68_AMBIGUITY_TH = 14 # 6/8混同: 互いの距離差がこれ以内なら輝度で判別
_DIGIT_68_MIN_DIST   = 2    # 6/8混同: ベスト距離がこれ未満なら確信度高とみなし輝度チェックをスキップ
_DIGIT_CENTER_TH     = 80   # 0/8判別: 中央輝度がこれ以上なら '8'、未満なら '0'
_DIGIT_68_TR_TH      = 185  # 6/8判別: 右上輝度がこれ以上なら '8'、未満なら '6'
                             # 実測例: 6(EXH背景)≈164, 8(MXM背景)≈196

# ─── ランプ判別パラメータ ────────────────────────────────────────────────────
_SELECT_LAMP_SAT_TH = 0.25  # 選曲画面 exc/maxxive 判別: 彩度がこれ以上なら exc (紫), 未満なら maxxive (白)


class ScreenReader:
    """ゲーム画面を解析するクラス。

    呼び出し手順:
        reader = ScreenReader(song_db)
        reader.update_screen(pil_image)   # OBSフレームをセット
        mode = reader.detect_screen()     # 現在の状態を取得
    """

    def __init__(self, song_db: SongDatabase,
                 orientation: screen_orientation | None = None):
        self._song_db = song_db
        self._orientation = orientation  # None = 自動検出
        self._img: Image.Image | None = None  # 回転補正済み画像
        self._fail_count = 0             # 連続認識失敗カウント

    @property
    def corrected_screen(self) -> 'Image.Image | None':
        """回転補正・黒帯除去済みの画像 (1080×1920) を返す。
        save_image() などで正立した画像を保存するために使う。"""
        return self._img

    # ─── 画像更新・向き検出 ────────────────────────────────────────────────────

    def update_screen(self, img: Image.Image) -> None:
        """OBSから受け取った生画像をセットし、回転補正を適用する。

        向きが未設定の場合や連続失敗が閾値を超えた場合に自動検出を実行する。
        """
        if self._orientation is None or self._fail_count >= _REDETECT_THRESHOLD:
            detected = self._auto_detect_orientation(img)
            if detected is not None:
                self._orientation = detected
                self._fail_count = 0

        if self._orientation is not None:
            rotated = self._rotate_img(img, self._orientation)
            self._img = self._normalize_portrait(rotated)
        else:
            self._img = img  # 向き不明でも仮セット

    @staticmethod
    def _rotate_img(img: Image.Image, orientation: screen_orientation) -> Image.Image:
        angle = orientation.rotate_angle()
        return img.rotate(angle, expand=True) if angle else img

    @staticmethod
    def _normalize_portrait(img: Image.Image) -> Image.Image:
        """黒帯を除去したうえで _EXPECTED_SIZE (1080×1920) にリサイズする。

        OBSがレターボックス付きでキャプチャした場合や、
        想定外の解像度で入力された場合に座標系を統一する。
        """
        if img.size == _EXPECTED_SIZE:
            return img

        # グレースケールで輝度を調べ、黒帯行・列を検出
        arr = np.array(img.convert('L'))
        row_max = arr.max(axis=1)   # shape (h,)
        col_max = arr.max(axis=0)   # shape (w,)

        non_black_rows = np.where(row_max > _BLACKBAR_LUM_TH)[0]
        non_black_cols = np.where(col_max > _BLACKBAR_LUM_TH)[0]

        if len(non_black_rows) > 0 and len(non_black_cols) > 0:
            y1 = int(non_black_rows[0])
            y2 = int(non_black_rows[-1]) + 1
            x1 = int(non_black_cols[0])
            x2 = int(non_black_cols[-1]) + 1
            w, h = img.size
            # 全体の5%以上が黒帯と判断できる場合だけクロップ
            if x1 > w * 0.05 or x2 < w * 0.95 or y1 > h * 0.05 or y2 < h * 0.95:
                img = img.crop((x1, y1, x2, y2))

        if img.size != _EXPECTED_SIZE:
            img = img.resize(_EXPECTED_SIZE, Image.LANCZOS)

        return img

    def _auto_detect_orientation(self, img: Image.Image) -> screen_orientation | None:
        """3方向を試し、最初に画面認識できた向きを返す。

        各方向に回転したのち黒帯除去・リサイズで正規化してからハッシュ照合する。
        自動検出用の閾値は通常判定より少し緩めにしている。
        """
        for orient in screen_orientation:
            rotated    = self._rotate_img(img, orient)
            normalized = self._normalize_portrait(rotated)
            if (self._check_onselect(normalized, threshold=8)
                    or self._check_ondetect(normalized, threshold=8)
                    or self._check_onplay(normalized, threshold=15)
                    or self._check_onresult(normalized, threshold=15)):
                logger.info(
                    f"画面向き自動検出: {orient.name} "
                    f"(入力サイズ={img.size}, 正規化後={normalized.size})"
                )
                return orient
        logger.debug(f"画面向き自動検出失敗: 入力サイズ={img.size}")
        return None

    # ─── 画面識別 (static) ────────────────────────────────────────────────────

    @staticmethod
    def _check_onselect(img: Image.Image, threshold: int = 5) -> bool:
        if HASH_ONSELECT is None:
            return False
        h = imagehash.average_hash(img.crop(RECT_ONSELECT))
        return abs(HASH_ONSELECT - h) < threshold

    @staticmethod
    def _check_ondetect(img: Image.Image, threshold: int = 5) -> bool:
        if HASH_ONDETECT is None:
            return False
        region = img.crop(RECT_ONDETECT)
        h = imagehash.average_hash(region)
        if abs(HASH_ONDETECT - h) >= threshold:
            return False
        rgb_sum = int(np.array(region).sum())
        return rgb_sum > ONDETECT_RGBSUM_THRESHOLD

    @staticmethod
    def _check_onplay(img: Image.Image, threshold: int = 10) -> bool:
        if HASH_ONPLAY1 is None or HASH_ONPLAY2 is None:
            return False
        h1 = imagehash.average_hash(img.crop(RECT_ONPLAY1))
        h2 = imagehash.average_hash(img.crop(RECT_ONPLAY2))
        return abs(HASH_ONPLAY1 - h1) < threshold and abs(HASH_ONPLAY2 - h2) < threshold

    @staticmethod
    def _check_onresult(img: Image.Image, threshold: int = 10) -> bool:
        if HASH_ONRESULT1 is None or HASH_ONRESULT2 is None:
            return False
        h0 = imagehash.average_hash(img.crop(RECT_ONRESULT_VAL0))
        h1 = imagehash.average_hash(img.crop(RECT_ONRESULT_VAL1))
        if abs(HASH_ONRESULT1 - h0) >= threshold or abs(HASH_ONRESULT2 - h1) >= threshold:
            return False
        if ONRESULT_ENABLE_HEAD and HASH_ONRESULT_HEAD is not None:
            hh = imagehash.average_hash(img.crop(RECT_ONRESULT_HEAD))
            if abs(HASH_ONRESULT_HEAD - hh) >= threshold:
                return False
        return True

    # ─── 画面識別 (public) ────────────────────────────────────────────────────

    def is_onselect(self) -> bool:
        return self._img is not None and self._check_onselect(self._img)

    def is_ondetect(self) -> bool:
        return self._img is not None and self._check_ondetect(self._img)

    def is_onplay(self) -> bool:
        return self._img is not None and self._check_onplay(self._img)

    def is_onresult(self) -> bool:
        return self._img is not None and self._check_onresult(self._img)

    def detect_screen(self) -> detect_mode:
        """現在の画面状態を返す。認識失敗カウントも更新する。"""
        if self._img is None:
            return detect_mode.init
        # リザルト優先（プレー→リザルト誤検知防止）
        if self.is_onresult():
            self._fail_count = 0
            return detect_mode.result
        if self.is_onplay():
            self._fail_count = 0
            return detect_mode.play
        if self.is_ondetect():
            self._fail_count = 0
            return detect_mode.detect
        if self.is_onselect():
            self._fail_count = 0
            return detect_mode.select
        self._fail_count += 1
        return detect_mode.init

    # ─── 数字認識 ─────────────────────────────────────────────────────────────

    @staticmethod
    def _read_digit(img: Image.Image, rect: tuple, hash_dict: dict,
                    threshold: int = 10) -> str:
        """1桁を認識する。最もハッシュ距離が近い数字を返す。閾値以上なら '?'。"""
        h = imagehash.average_hash(img.crop(rect))
        min_dist = threshold
        best = '?'
        for k, tmpl_hash in hash_dict.items():
            if tmpl_hash is None:
                continue
            d = abs(h - tmpl_hash)
            if d < min_dist:
                min_dist = d
                best = str(k)
        return best

    @staticmethod
    def _sample_brightness(img: Image.Image, rect: tuple,
                            rel_y: float, rel_x: float) -> float:
        """桁領域内の相対座標 (rel_y, rel_x) 周辺 3×3px の平均輝度を返す。"""
        l, t, r, b = rect
        px = l + max(1, int((r - l) * rel_x))
        py = t + max(1, int((b - t) * rel_y))
        return float(np.array(
            img.crop((px, py, px + 3, py + 3)).convert('L')
        ).mean())

    @staticmethod
    def _resolve_digit(dists: dict, img: Image.Image, rect: tuple,
                        threshold: int = 10) -> str:
        """距離辞書 {数字: ハミング距離} から最適な数字文字を返す。
        0/8 混同は中央輝度、6/8 混同は中央輝度で補正する。
        """
        if not dists:
            return '?'
        best_k = min(dists, key=dists.get)
        top2 = set(sorted(dists, key=dists.get)[:2])
        # 0/8 混同: top2 が {0,8} かつ距離差が小さいとき
        if top2 == {0, 8} and abs(dists[0] - dists[8]) <= _DIGIT_AMBIGUITY_TH:
            bri = ScreenReader._sample_brightness(img, rect, 0.5, 0.5)
            return '8' if bri > _DIGIT_CENTER_TH else '0'
        # 6/8 混同: ベストが6か8で、距離差が閾値以内かつ距離が一定以上のとき右上輝度で判別
        # (距離が小さい=確信度高 の場合はテンプレートマッチを信頼してスキップ)
        if (best_k in (6, 8)
                and dists[best_k] >= _DIGIT_68_MIN_DIST
                and abs(dists.get(6, 99) - dists.get(8, 99)) <= _DIGIT_68_AMBIGUITY_TH):
            # 文字の骨格があるはずの地点の平均輝度を基準にする
            tr  = ScreenReader._sample_brightness(img, rect, 0.2, 0.8)
            tl  = ScreenReader._sample_brightness(img, rect, 0.2, 0.2)
            ml  = ScreenReader._sample_brightness(img, rect, 0.5, 0.2)
            ctr = ScreenReader._sample_brightness(img, rect, 0.5, 0.5)
            base_bri = (tl + ml + ctr) / 3

            # 8判定の条件:
            # 1. 右上が絶対的に明るい (従来の判定)
            # 2. あるいは、文字の他の部分 (左・中央) と比較して同等以上の明るさである
            is_8 = (tr > _DIGIT_68_TR_TH) or (tr > base_bri * 0.9 and tr > 150)
            return '8' if is_8 else '6'
        if dists[best_k] > threshold:
            return '?'
        return str(best_k)

    @staticmethod
    def _read_digit_multi(img: Image.Image, rect: tuple, hash_dicts: list,
                          threshold: int = 10) -> str:
        """複数のハッシュ辞書を横断して1桁を認識する。全辞書中で最小距離のものを返す。"""
        h = imagehash.average_hash(img.crop(rect))
        min_dist = threshold
        best = '?'
        for hash_dict in hash_dicts:
            for k, tmpl_hash in hash_dict.items():
                if tmpl_hash is None:
                    continue
                d = abs(h - tmpl_hash)
                if d < min_dist:
                    min_dist = d
                    best = str(k)
        return best

    def _read_digits_as_int(self, img: Image.Image, rects: list,
                             hash_dict: dict,
                             threshold: int = 10) -> Optional[int]:
        """複数桁を読み取り整数に変換する。1桁でも '?' なら None を返す。
        0/8・8/9 の混同は輝度サンプルで補正する。
        threshold: 許容最大ハミング距離（この値以下なら合格）
        """
        digits = ''
        for r in rects:
            h = imagehash.average_hash(img.crop(r))
            dists = {k: int(abs(h - tmpl))
                     for k, tmpl in hash_dict.items() if tmpl is not None}
            digits += self._resolve_digit(dists, img, r, threshold)
        if '?' in digits:
            return None
        try:
            return int(digits)
        except ValueError:
            return None

    def _read_score_8digit(self, img: Image.Image,
                            rects_large: list, hash_large: dict,
                            rects_small: list, hash_small: dict) -> Optional[int]:
        """8桁スコアを読み取る（大字体N桁 + 小字体M桁）。
        各位置で専用テンプレートを優先し、失敗時のみ他字体テンプレートへフォールバック。
        0/8・8/9 の混同は輝度サンプルで補正する。
        """
        def _read(rect, primary, fallback):
            h = imagehash.average_hash(img.crop(rect))
            dists: dict = {}
            for hd in (primary, fallback):
                for k, tmpl in hd.items():
                    if tmpl is None:
                        continue
                    d = int(abs(h - tmpl))
                    if k not in dists or d < dists[k]:
                        dists[k] = d
            return self._resolve_digit(dists, img, rect)

        large = ''.join(_read(r, hash_large, hash_small) for r in rects_large)
        small = ''.join(_read(r, hash_small, hash_large) for r in rects_small)
        digits = large + small
        if '?' in digits:
            return None
        try:
            return int(digits)
        except ValueError:
            return None

    # ─── ハッシュ最近傍マッチ ────────────────────────────────────────────────

    @staticmethod
    def _match_hash(img: Image.Image, rect: tuple,
                    candidates: list[tuple]) -> any:
        """candidates = [(template_hash, return_value), ...] から最近傍を返す。
        どれも Hamming 距離 10 未満に一致しなければ None。
        """
        h = imagehash.average_hash(img.crop(rect))
        min_dist = 10
        result = None
        for tmpl, val in candidates:
            if tmpl is None:
                continue
            d = abs(tmpl - h)
            if d < min_dist:
                min_dist = d
                result = val
        return result

    # ─── ランプ読み取り ───────────────────────────────────────────────────────

    def _read_lamp_from_result(self, img: Image.Image) -> clear_lamp:
        """リザルト画面のランプを読む。
        puc/uc/failed はランプ形状で判別。
        clear 系 (maxxive/exc/clear) はゲージのRGB合計で判別。
          rsum+gsum+bsum > 780000 → maxxive (白いゲージ)
          rsum < gsum             → clear   (緑ゲージ)
          それ以外                → exc     (暗いゲージ)
        """
        candidates = [
            (HASH_LAMP.get('puc'),    clear_lamp.puc),
            (HASH_LAMP.get('uc'),     clear_lamp.uc),
            (HASH_LAMP.get('clear'),  clear_lamp.clear),
            (HASH_LAMP.get('failed'), clear_lamp.played),
        ]
        result = self._match_hash(img, RECT_LAMP, candidates)
        if result is None:
            return clear_lamp.played
        if result == clear_lamp.clear:
            arr = np.array(img.crop(RECT_GAUGE), dtype=int)
            rsum = int(arr[:, :, 0].sum())
            gsum = int(arr[:, :, 1].sum())
            # R << G (R/G < 0.75): 緑系ゲージ → clear
            # R >  G             : 赤系ゲージ → exc
            # R ≈  G             : 白系ゲージ → maxxive
            # comp: R=136k, G=318k / exc: R=331k, G=151k / maxxive: R=300k, G=304k
            if rsum < gsum * 0.75:
                return clear_lamp.clear
            if rsum > gsum:
                return clear_lamp.exc
            return clear_lamp.maxxive
        return result

    def _read_lamp_from_select(self, img: Image.Image) -> clear_lamp:
        """選曲画面のランプを読む。
        exc (EXC-COMP, 紫) と maxxive (白) は形状が同じため、彩度で判別する。
        """
        candidates = [
            (HASH_SELECT_LAMP.get('puc'),    clear_lamp.puc),
            (HASH_SELECT_LAMP.get('uc'),     clear_lamp.uc),
            (HASH_SELECT_LAMP.get('exh'),    clear_lamp.maxxive),
            (HASH_SELECT_LAMP.get('hard'),   clear_lamp.exc),
            (HASH_SELECT_LAMP.get('clear'),  clear_lamp.clear),
            (HASH_SELECT_LAMP.get('failed'), clear_lamp.played),
        ]
        result = self._match_hash(img, RECT_SELECT_LAMP, candidates)
        if result is None:
            return clear_lamp.noplay
        # exc と maxxive は形状が同じため average_hash では区別できない → 彩度で判別
        if result in (clear_lamp.exc, clear_lamp.maxxive):
            arr = np.array(img.crop(RECT_SELECT_LAMP).convert('RGB'), dtype=float)
            r, g, b = arr[:, :, 0].mean(), arr[:, :, 1].mean(), arr[:, :, 2].mean()
            _, sat, _ = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            return clear_lamp.exc if sat > _SELECT_LAMP_SAT_TH else clear_lamp.maxxive
        return result

    # ─── ゲージ読み取り ───────────────────────────────────────────────────────

    def _read_gauge_type(self, img: Image.Image) -> str:
        """ゲージタイプを読む ('normal' / 'hard')。"""
        candidates = [
            (HASH_GAUGE.get('normal'), 'normal'),
            (HASH_GAUGE.get('hard'),   'hard'),
        ]
        result = self._match_hash(img, RECT_GAUGE, candidates)
        return result if result is not None else 'normal'

    # ─── 難易度読み取り ───────────────────────────────────────────────────────

    def _read_difficulty_from_select(self, img: Image.Image) -> difficulty:
        """選曲画面の難易度タブから現在選択されている難易度を判定する。
        NOV/ADV/EXH タブを HASH_DIFFICULTY と比較し、一致しなければ APPEND (MXM) とみなす。
        """
        sum_nov = np.array(img.crop(RECT_SELECT_NOV)).sum()
        sum_adv = np.array(img.crop(RECT_SELECT_ADV)).sum()
        sum_exh = np.array(img.crop(RECT_SELECT_EXH)).sum()
        sum_append = np.array(img.crop(RECT_SELECT_APPEND)).sum()
        max_sum = max(sum_nov, sum_adv, sum_exh, sum_append)
        if max_sum == sum_nov:
            return difficulty.novice
        elif max_sum == sum_adv:
            return difficulty.advanced
        elif max_sum == sum_exh:
            return difficulty.exhaust
        else:
            return difficulty.maximum

    def _read_difficulty_from_detect(self, img: Image.Image) -> difficulty:
        """detect画面（楽曲情報）の難易度バッジから難易度を判定する。
        NOV/ADV/EXH は HASH_DIFFICULTY と比較。一致しなければ MXM (APPEND) とみなす。
        """
        candidates = [
            (HASH_DIFFICULTY.get('nov'), difficulty.novice),
            (HASH_DIFFICULTY.get('adv'), difficulty.advanced),
            (HASH_DIFFICULTY.get('exh'), difficulty.exhaust),
        ]
        result = self._match_hash(img, RECT_INFO_DIFF, candidates)
        return result if result is not None else difficulty.maximum

    def _read_difficulty_from_result(self, img: Image.Image) -> difficulty:
        """リザルト画面の難易度バッジからRGB合計値で難易度を判定する。
        バッジ左70pxのR/G/B合計を見て NOV(青)/ADV(黄)/EXH(赤)/APPEND を判別。
        """
        arr = np.array(img.crop(RECT_RESULT_DIFF).crop((0, 0, 70, 30)), dtype=int)
        rsum = int(arr[:, :, 0].sum())
        gsum = int(arr[:, :, 1].sum())
        bsum = int(arr[:, :, 2].sum())
        if rsum < 190000 and gsum < 180000 and bsum > 300000:
            return difficulty.novice
        if rsum > 300000 and gsum > 260000 and bsum < 180000:
            return difficulty.advanced
        if rsum > 300000 and gsum < 180000 and bsum < 180000:
            return difficulty.exhaust
        return difficulty.maximum

    # ─── EXスコア有無 ─────────────────────────────────────────────────────────

    def _has_exscore(self, img: Image.Image) -> bool:
        """選曲画面にEXスコアが表示されているか判定する。"""
        if HASH_HAS_EXSCORE is None:
            return False
        h = imagehash.average_hash(img.crop(RECT_HAS_EXSCORE))
        return abs(HASH_HAS_EXSCORE - h) < 10

    # ─── 選曲画面読み取り ─────────────────────────────────────────────────────

    def read_from_select(self) -> Optional[dict]:
        """選曲画面から情報を読み取る。

        Returns:
            dict: title, difficulty, lamp, score, exscore
        """
        if self._img is None:
            return None
        try:
            img = self._img
            diff = self._read_difficulty_from_select(img)
            jacket_img = img.crop(RECT_SELECT_JACKET)
            title = self._song_db.identify_jacket(jacket_img, diff)
            lamp = self._read_lamp_from_select(img)
            # 選曲画面は large/small ともに同一テンプレートを使用
            score = self._read_digits_as_int(
                img,
                RECT_SELECT_SCORE_LARGE + RECT_SELECT_SCORE_SMALL,
                HASH_SELECT_SCORE,
                threshold=12
            )
            exscore = self._read_digits_as_int(
                img, RECT_SELECT_EXSCORE, HASH_SELECT_EXSCORE, threshold=20
            )
            return {
                'title':      title,
                'difficulty': diff,
                'lamp':       lamp,
                'score':      score,
                'exscore':    exscore,
            }
        except Exception:
            logger.error(f"read_from_select 失敗:\n{traceback.format_exc()}")
            return None

    # ─── detect画面読み取り ───────────────────────────────────────────────────

    def read_from_detect(self) -> Optional[dict]:
        """detect画面（楽曲情報）から情報を読み取る。

        Returns:
            dict: title, difficulty, jacket_img, title_img, lv_img,
                  bpm_img, ef_img, illust_img
        """
        if self._img is None:
            return None
        try:
            img = self._img
            diff = self._read_difficulty_from_detect(img)
            jacket_img = img.crop(RECT_INFO_JACKET)
            title = self._song_db.identify_jacket(jacket_img, diff)
            return {
                'title':      title,
                'difficulty': diff,
                'jacket_img': jacket_img,
                'title_img':  img.crop(RECT_INFO_TITLE),
                'lv_img':     img.crop(RECT_INFO_LV),
                'bpm_img':    img.crop(RECT_INFO_BPM),
                'ef_img':     img.crop(RECT_INFO_EF),
                'illust_img': img.crop(RECT_INFO_ILLUST),
            }
        except Exception:
            logger.error(f"read_from_detect 失敗:\n{traceback.format_exc()}")
            return None

    # ─── プレー画面読み取り ───────────────────────────────────────────────────

    def read_from_play(self) -> Optional[dict]:
        """プレー画面から情報を読み取る。

        Returns:
            dict: gauge_type ('normal'/'hard'), lamp
        """
        if self._img is None:
            return None
        try:
            img = self._img
            return {
                'gauge_type': self._read_gauge_type(img),
                'lamp':       self._read_lamp_from_result(img),
            }
        except Exception:
            logger.error(f"read_from_play 失敗:\n{traceback.format_exc()}")
            return None

    # ─── リザルト画面読み取り ────────────────────────────────────────────────

    def read_from_result(self) -> Optional[dict]:
        """リザルト画面から情報を読み取る。

        Returns:
            dict: title, difficulty, score, exscore, lamp
        """
        if self._img is None:
            return None
        try:
            img = self._img
            diff = self._read_difficulty_from_result(img)
            jacket_img = img.crop(RECT_RESULT_JACKET)
            title = self._song_db.identify_jacket(jacket_img, diff)
            lamp = self._read_lamp_from_result(img)
            # PUCはスコアが必ず10,000,000なので読み取り不要
            if lamp == clear_lamp.puc:
                score = 10_000_000
            else:
                score = self._read_score_8digit(
                    img,
                    RECT_RESULT_SCORE_LARGE, HASH_RESULT_SCORE_LARGE,
                    RECT_RESULT_SCORE_SMALL, HASH_RESULT_SCORE_SMALL,
                )
            exscore = self._read_digits_as_int(
                img, RECT_RESULT_EXSCORE, HASH_RESULT_EXSCORE, threshold=16
            )
            return {
                'title':      title,
                'difficulty': diff,
                'score':      score,
                'exscore':    exscore,
                'lamp':       lamp,
            }
        except Exception:
            logger.error(f"read_from_result 失敗:\n{traceback.format_exc()}")
            return None

    # ─── ユーティリティ ──────────────────────────────────────────────────────

    @property
    def current_image(self) -> Image.Image | None:
        """回転補正済みの現在フレームを返す。"""
        return self._img

    def get_orientation(self) -> screen_orientation | None:
        """現在設定されている画面向きを返す。"""
        return self._orientation

    def set_orientation(self, orientation: screen_orientation) -> None:
        """画面向きを手動設定する。"""
        self._orientation = orientation
        self._fail_count = 0

if __name__ == '__main__':
    import glob

    def _debug_hash_dist(img, rects, hash_dict, label):
        """各桁の全テンプレートとのハミング距離・各輝度サンプルを表示する。"""
        for i, rect in enumerate(rects):
            h = imagehash.average_hash(img.crop(rect))
            dists = {k: abs(v - h) for k, v in hash_dict.items() if v is not None}
            best_k = min(dists, key=dists.get)
            l, t, r, b = rect
            ht, wd = b - t, r - l
            # 中央帯 (0/8判別用)
            center = float(np.array(img.crop((l, (t+b)//2 - ht//6,
                                              r, (t+b)//2 + ht//6)).convert('L')).mean())
            # 左下 (8/9判別用: rel_y=0.35, rel_x=0.05)
            px = l + max(1, int(wd * 0.05))
            py = t + max(1, int(ht * 0.35))
            lower_left = float(np.array(img.crop((px, py, px+3, py+3)).convert('L')).mean())
            # 右上 (6/8判別用: rel_y=0.2, rel_x=0.75)
            px_tr = l + max(1, int(wd * 0.75))
            py_tr = t + max(1, int(ht * 0.20))
            top_right = float(np.array(img.crop((px_tr, py_tr, px_tr+3, py_tr+3)).convert('L')).mean())
            print(f"  {label}[{i}]: best={best_k}(d={dists[best_k]})"
                  f"  center={center:.1f}  lower_left={lower_left:.1f}  top_right={top_right:.1f}"
                  f"  all={dict(sorted(dists.items()))}")

    from src.define import (
        RECT_RESULT_SCORE_LARGE, RECT_RESULT_SCORE_SMALL,
        HASH_RESULT_SCORE_LARGE, HASH_RESULT_SCORE_SMALL,
        RECT_RESULT_EXSCORE, HASH_RESULT_EXSCORE,
    )

    sdb = SongDatabase()
    sr = ScreenReader(sdb)

    def read_result(f):
        img = Image.open(f)
        sr.update_screen(img)
        result = sr.read_from_result()
        print(f, result['title'], result['difficulty'], result['score'], result['exscore'], result['lamp'])
        rotated = sr._img

    # for f in glob.glob('debug/result/*.png'):
        # read_result(f)

    from src.define import (
        RECT_SELECT_SCORE_LARGE, RECT_SELECT_SCORE_SMALL,
        HASH_SELECT_SCORE, HASH_SELECT_EXSCORE,
        RECT_HAS_EXSCORE, HASH_HAS_EXSCORE,
        RECT_SELECT_EXSCORE,
    )

    def _debug_68(img, rects, hash_dict, label):
        """6/8 候補になっている桁だけ top_right 付きで出力する。"""
        for i, rect in enumerate(rects):
            h = imagehash.average_hash(img.crop(rect))
            dists = {k: int(abs(v - h)) for k, v in hash_dict.items() if v is not None}
            best_k = min(dists, key=dists.get)
            if best_k not in (6, 8):
                continue
            l, t, r, b = rect
            ht, wd = b - t, r - l
            center = float(np.array(img.crop((l, (t+b)//2 - ht//6,
                                              r, (t+b)//2 + ht//6)).convert('L')).mean())
            px_tr = l + max(1, int(wd * 0.75))
            py_tr = t + max(1, int(ht * 0.20))
            top_right = float(np.array(img.crop((px_tr, py_tr, px_tr+3, py_tr+3)).convert('L')).mean())
            print(f"  {label}[{i}]: best={best_k}(d={dists[best_k]})"
                  f"  center={center:.1f}  top_right={top_right:.1f}")

    def read_select(f):
        img = Image.open(f)
        sr.update_screen(img)
        result = sr.read_from_select()
        print(f, result)
        rotated = sr._img
        # ランプ領域の平均RGB・彩度を出力（exc/maxxive判別用）
        lamp_arr = np.array(rotated.crop(RECT_SELECT_LAMP).convert('RGB'), dtype=float)
        r_mean = lamp_arr[:, :, 0].mean()
        g_mean = lamp_arr[:, :, 1].mean()
        b_mean = lamp_arr[:, :, 2].mean()
        h, s, v = colorsys.rgb_to_hsv(r_mean / 255, g_mean / 255, b_mean / 255)
        print(f'  lamp RGB=({r_mean:.1f},{g_mean:.1f},{b_mean:.1f})  sat={s:.3f}  val={v:.3f}  hue={h:.3f}')

    #for f in glob.glob('debug/select/*.png'):
    #    read_select(f)
    for f in glob.glob('debug/result/*.png'):
        read_result(f)