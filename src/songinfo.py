"""SDVX楽曲データベース。resources/musiclist.pkl をラップする。

musiclist.pklの構造:
  jacket[diff][title]  = hash_hex  # ジャケット画像のaverage_hashヘックス文字列
  info[diff][title]    = hash_hex  # 曲名表示部分のhash（補助照合用）
  titles[title]        = [title, artist, bpm, nov_lv, adv_lv, exh_lv, mxm_lv]
  gradeS_lv{N}         = {title: '1', ...}  # グレードS対象曲リスト(lv17/18/19)

diffキー: 'nov' / 'adv' / 'exh' / 'APPEND'  (MXM/INF両方ともAPPEND)
"""
from __future__ import annotations
import json
import pickle
import imagehash
import traceback
import urllib.request
from pathlib import Path
from typing import Dict, Optional

from src.classes import difficulty
from src.logger import get_logger
logger = get_logger(__name__)

_MUSICLIST_PATH = Path('resources') / 'musiclist.pkl'
_PARAMS_PATH = Path('resources') / 'params.json'

# ジャケット照合でこの距離以上なら「未登録曲」とみなす
JACKET_MATCH_THRESHOLD = 10


def update_musiclist_from_remote() -> bool:
    """resources/params.json の url_musiclist から musiclist.pkl を更新する。"""
    try:
        with open(_PARAMS_PATH, 'r', encoding='utf-8') as f:
            params = json.load(f)
        url = params.get('url_musiclist')
        if not url:
            logger.debug('url_musiclist が設定されていないため musiclist.pkl 更新をスキップします')
            return False

        with urllib.request.urlopen(url, timeout=15) as response:
            data = response.read()

        musiclist = pickle.loads(data)
        if not isinstance(musiclist, dict):
            raise ValueError('downloaded musiclist is not a dict')

        _MUSICLIST_PATH.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = _MUSICLIST_PATH.with_suffix(_MUSICLIST_PATH.suffix + '.tmp')
        with open(tmp_path, 'wb') as f:
            f.write(data)
        tmp_path.replace(_MUSICLIST_PATH)

        logger.info(f"musiclist.pklを更新しました: {len(musiclist.get('titles', {}))} 曲")
        return True
    except Exception:
        logger.warning(f"musiclist.pkl の更新に失敗しました:\n{traceback.format_exc()}")
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
                 ):
        self.title  = title
        self.artist = artist
        self.bpm    = bpm   # "5-315" のような文字列

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

    def __str__(self):
        diffs = ' / '.join(
            f"{d}:{lv}" for d, lv in self._levels.items()
            if lv and d in (difficulty.novice, difficulty.advanced, difficulty.exhaust, difficulty.maximum)
        )
        return f"{self.title} [{self.artist}] BPM:{self.bpm} ({diffs})"


class SongDatabase:
    """musiclist.pkl をロードし、ジャケット照合・楽曲情報提供を行うクラス"""

    def __init__(self):
        self._musiclist: dict = {}
        """musiclist.pkl の内容をそのまま保持"""
        self._songs: Dict[str, OneSongInfo] = {}
        """title → OneSongInfo のキャッシュ"""
        self.load()

    def load(self):
        """musiclist.pkl を読み込む"""
        try:
            with open(_MUSICLIST_PATH, 'rb') as f:
                self._musiclist = pickle.load(f)
            self._build_song_cache()
            logger.info(f"musiclist.pkl 読み込み完了: {len(self._songs)} 曲")
        except Exception:
            logger.error(f"musiclist.pkl の読み込みに失敗しました:\n{traceback.format_exc()}")

    def _build_song_cache(self):
        """titles セクションから OneSongInfo のキャッシュを構築する"""
        self._songs = {}
        for title, data in self._musiclist.get('titles', {}).items():
            if len(data) < 7:
                continue
            self._songs[title] = OneSongInfo(
                title=data[0], artist=data[1], bpm=data[2],
                nov_lv=data[3], adv_lv=data[4], exh_lv=data[5], mxm_lv=data[6],
            )

    def get_song_info(self, title: str) -> Optional[OneSongInfo]:
        """曲名から楽曲情報を返す。未登録ならNone。"""
        return self._songs.get(title)

    def identify_jacket(self, jacket_img, diff: difficulty) -> Optional[str]:
        """ジャケット画像のaverage_hashで最近傍の曲名を返す。

        Args:
            jacket_img: PIL.Image — ジャケット領域の切り出し画像
            diff: difficulty — 現在の難易度（DBキー選択に使用）

        Returns:
            str: 曲名。JACKET_MATCH_THRESHOLD以上離れていればNone。
        """
        db_key = diff.to_db_key()
        jacket_db: dict = self._musiclist.get('jacket', {}).get(db_key, {})
        if not jacket_db:
            return None

        hash_jacket = imagehash.average_hash(jacket_img)
        min_dist = JACKET_MATCH_THRESHOLD
        best_title = None

        for title, hash_hex in jacket_db.items():
            try:
                dist = abs(imagehash.hex_to_hash(hash_hex) - hash_jacket)
            except Exception:
                continue
            if dist < min_dist:
                min_dist = dist
                best_title = title

        return best_title

    def get_gradeS_titles(self, level: int) -> list[str]:
        """指定レベルのグレードS対象曲タイトルのリストを返す（lv17/18/19のみ収録）。"""
        key = f'gradeS_lv{level}'
        raw: dict = self._musiclist.get(key, {})
        return [title for title, val in raw.items() if val == '1']

    def __len__(self):
        return len(self._songs)
