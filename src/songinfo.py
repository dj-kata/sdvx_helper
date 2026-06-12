"""SDVX楽曲データベース。resources/musiclistv2.sdvxh をラップする。

musiclistv2.sdvxhの構造:
  jacket[diff][title]  = hash_hex  # ジャケット画像のaverage_hashヘックス文字列
  info[diff][title]    = hash_hex  # 曲名表示部分のhash（補助照合用）
  titles[title]        = [title, artist, bpm, nov_lv, adv_lv, exh_lv, mxm_lv, title_v1?]
  gradeS_lv{N}         = {title: '1', ...}  # グレードS対象曲リスト(lv17/18/19)

diffキー: 'nov' / 'adv' / 'exh' / 'APPEND'  (MXM/INF両方ともAPPEND)
"""
from __future__ import annotations
import bz2
import pickle
import imagehash
import traceback
from pathlib import Path
from typing import Dict, Optional

from src.classes import difficulty
from src.logger import get_logger
logger = get_logger(__name__)

_MUSICLIST_V2_PATH = Path('resources') / 'musiclistv2.sdvxh'

# ジャケット照合でこの距離以上なら「未登録曲」とみなす
JACKET_MATCH_THRESHOLD = 10


def update_musiclist_from_remote() -> bool:
    """v2では旧musiclist.pklの自動更新を行わない。

    musiclistv2.sdvxh は misc/manage_db.py で portal マスタ表記に揃えて生成する。
    """
    logger.debug('musiclistv2.sdvxh に一本化したため、旧musiclist.pkl更新はスキップします')
    return False


class OneSongInfo:
    """1曲分の楽曲情報"""
    def __init__(self,
                 title:  str,
                 artist: str,
                 bpm:    str,
                 nov_lv: int,
                 adv_lv: int,
                 exh_lv: int,
                 mxm_lv: int,
                 title_v1: str | None = None,
                 jacket_hashes: Dict[difficulty, str] | None = None,
                 info_hashes: Dict[difficulty, str] | None = None,
                 ):
        self.title    = title
        self.title_v1 = title_v1 or None
        self.artist   = artist
        self.bpm      = bpm   # "5-315" のような文字列
        self.jacket_hashes: Dict[difficulty, str] = jacket_hashes or {}
        self.info_hashes: Dict[difficulty, str] = info_hashes or {}

        # 難易度別レベル（0は未収録を示す）
        self._levels: Dict[difficulty, int] = {
            difficulty.novice:   nov_lv,
            difficulty.advanced: adv_lv,
            difficulty.exhaust:  exh_lv,
            difficulty.maximum:  mxm_lv,  # MXM/INF/GRV/HVN/VVD/XCD は全て maximum
        }

    def get_level(self, diff: difficulty) -> Optional[int]:
        """指定難易度のレベルを返す。未収録（0）はNoneを返す。"""
        lv = self._levels.get(diff)
        return lv if lv else None

    @property
    def levels(self) -> Dict[difficulty, int]:
        return self._levels

    def get_jacket_hash(self, diff: difficulty) -> Optional[str]:
        return self.jacket_hashes.get(diff)

    def get_info_hash(self, diff: difficulty) -> Optional[str]:
        return self.info_hashes.get(diff)

    def __str__(self):
        diffs = ' / '.join(
            f"{d}:{lv}" for d, lv in self._levels.items()
            if lv and d in (difficulty.novice, difficulty.advanced, difficulty.exhaust, difficulty.maximum)
        )
        return f"{self.title} [{self.artist}] BPM:{self.bpm} ({diffs})"


class SongDatabase:
    """楽曲DBをロードし、ジャケット照合・楽曲情報提供を行うクラス"""

    def __init__(self):
        self._musiclist: dict = {}
        """楽曲DBの内容をそのまま保持"""
        self._songs: Dict[str, OneSongInfo] = {}
        """title → OneSongInfo のキャッシュ"""
        self._v1_to_v2_titles: Dict[str, str] = {}
        """v1表記 → v2(portal)表記 の変換キャッシュ"""
        self.load()

    def load(self):
        """musiclistv2.sdvxh を読み込む。"""
        try:
            with bz2.open(_MUSICLIST_V2_PATH, 'rb') as f:
                self._musiclist = pickle.load(f)
            self._build_song_cache()
            logger.info(f"{_MUSICLIST_V2_PATH} 読み込み完了: {len(self._songs)} 曲")
        except Exception:
            logger.error(f"楽曲DBの読み込みに失敗しました:\n{traceback.format_exc()}")

    def _build_song_cache(self):
        """titles セクションから OneSongInfo のキャッシュを構築する"""
        self._songs = {}
        self._v1_to_v2_titles = {}
        for title, data in self._musiclist.get('titles', {}).items():
            if len(data) < 7:
                continue
            title_v1 = data[7] if len(data) > 7 else None
            jacket_hashes = self._collect_hashes('jacket', title)
            info_hashes = self._collect_hashes('info', title)
            info = OneSongInfo(
                title=data[0], artist=data[1], bpm=data[2],
                nov_lv=data[3], adv_lv=data[4], exh_lv=data[5], mxm_lv=data[6],
                title_v1=title_v1,
                jacket_hashes=jacket_hashes,
                info_hashes=info_hashes,
            )
            self._songs[title] = info
            if info.title_v1 and info.title_v1 != info.title:
                self._v1_to_v2_titles[info.title_v1] = info.title

    def _collect_hashes(self, section: str, title: str) -> Dict[difficulty, str]:
        """musiclistのhash辞書から指定曲の難易度別hashをコピーする。"""
        result: Dict[difficulty, str] = {}
        section_data = self._musiclist.get(section, {})
        for diff in difficulty:
            h = section_data.get(diff.to_db_key(), {}).get(title)
            if h:
                result[diff] = h
        return result

    def get_song_info(self, title: str) -> Optional[OneSongInfo]:
        """曲名から楽曲情報を返す。未登録ならNone。"""
        return self._songs.get(title)

    def convert_v1_title(self, title: str) -> str:
        """v1表記の曲名をv2(portal)表記へ変換する。対応がなければ元の曲名を返す。"""
        return self._v1_to_v2_titles.get(title, title)

    def identify_jacket(self, jacket_img, diff: difficulty) -> Optional[str]:
        """ジャケット画像のaverage_hashで最近傍の曲名を返す。

        Args:
            jacket_img: PIL.Image — ジャケット領域の切り出し画像
            diff: difficulty — 現在の難易度（DBキー選択に使用）

        Returns:
            str: 曲名。JACKET_MATCH_THRESHOLD以上離れていればNone。
        """
        hash_jacket = imagehash.average_hash(jacket_img)
        min_dist = JACKET_MATCH_THRESHOLD
        best_title = None

        for info in self._songs.values():
            hash_hex = info.get_jacket_hash(diff)
            if not hash_hex:
                continue
            try:
                dist = abs(imagehash.hex_to_hash(hash_hex) - hash_jacket)
            except Exception:
                continue
            if dist < min_dist:
                min_dist = dist
                best_title = info.title

        return best_title

    def get_gradeS_titles(self, level: int) -> list[str]:
        """指定レベルのグレードS対象曲タイトルのリストを返す（lv17/18/19のみ収録）。"""
        key = f'gradeS_lv{level}'
        raw: dict = self._musiclist.get(key, {})
        return [title for title, val in raw.items() if val == '1']

    def __len__(self):
        return len(self._songs)
