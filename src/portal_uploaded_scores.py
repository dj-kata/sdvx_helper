"""Portal 送信済みスコアの管理。

out/uploaded_score.pkl に送信済みリビジョン・スコア情報を保存する。
v1 (sdvxh_classes.py) の ManageUploadedScores / OneUploadedScore と互換形式。
"""
from __future__ import annotations

import io
import os
import pickle
import traceback
from typing import List, Optional

from src.logger import get_logger

logger = get_logger(__name__)

UPLOADED_SCORE_PATH = 'out/uploaded_score.pkl'


class OneUploadedScore:
    """1件の送信済みスコアを表す。"""

    def __init__(
        self,
        revision: int = None,
        music_id: str = None,
        difficulty: str = None,
        score: int = None,
        exscore: int = None,
        lamp: str = None,
    ):
        self.revision = revision
        self.music_id = music_id
        self.difficulty = difficulty
        self.score = score
        self.exscore = exscore
        self.lamp = lamp

    def __repr__(self) -> str:
        return (
            f'OneUploadedScore(rev={self.revision}, id={self.music_id}, '
            f'diff={self.difficulty}, score={self.score}, lamp={self.lamp})'
        )


class _CompatUnpickler(pickle.Unpickler):
    """v1 (sdvxh_classes 等) のモジュールパスを v2 クラスにマップする互換 unpickler。"""

    def find_class(self, module: str, name: str):
        if name == 'OneUploadedScore':
            return OneUploadedScore
        return super().find_class(module, name)


class ManageUploadedScores:
    """out/uploaded_score.pkl に送信済みスコアリストを永続化するクラス。"""

    def __init__(self):
        self.scores: List[OneUploadedScore] = []
        self.load()

    def push(self, data: OneUploadedScore) -> int:
        self.scores.append(data)
        return len(self.scores)

    def delete(self, revision: int, music_id: str) -> bool:
        for i, s in enumerate(self.scores):
            if s.music_id == music_id and s.revision == revision:
                self.scores.pop(i)
                logger.info(f'uploaded score deleted (id:{s.music_id}, rev:{s.revision})')
                return True
        return False

    def load(self):
        try:
            with open(UPLOADED_SCORE_PATH, 'rb') as fp:
                self.scores = _CompatUnpickler(fp).load()
            logger.debug(f'uploaded_score.pkl loaded: {len(self.scores)} entries')
        except FileNotFoundError:
            self.scores = []
        except Exception:
            logger.warning(f'uploaded_score.pkl 読み込み失敗:\n{traceback.format_exc()}')
            self.scores = []

    def save(self):
        os.makedirs('out', exist_ok=True)
        with open(UPLOADED_SCORE_PATH, 'wb') as fp:
            pickle.dump(self.scores, fp)
        logger.debug(f'uploaded_score.pkl saved: {len(self.scores)} entries')

    def get_by_revision(self, revision: int) -> List[OneUploadedScore]:
        return [s for s in self.scores if s.revision == revision]
