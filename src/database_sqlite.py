import sqlite3
import os
from typing import List, Tuple, Optional, Any
from src.logger import get_logger

logger = get_logger(__name__)

class SQLiteDatabase:
    """sqlite3 へのアクセスをカプセル化するクラス"""

    def __init__(self, db_path: str = 'sdvx_helper.db'):
        self.db_path = db_path
        self._conn = None
        self._init_db()

    def _init_db(self):
        """テーブル作成とインデックス設定"""
        try:
            self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
            self._conn.row_factory = sqlite3.Row
            cur = self._conn.cursor()

            # 個人リザルトテーブル
            cur.execute('''
                CREATE TABLE IF NOT EXISTS personal_results (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    difficulty INTEGER NOT NULL,
                    lamp INTEGER NOT NULL,
                    score INTEGER NOT NULL,
                    exscore INTEGER,
                    level INTEGER,
                    timestamp INTEGER NOT NULL,
                    detect_mode INTEGER,
                    bestscore INTEGER,
                    bestexscore INTEGER
                )
            ''')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_personal_song ON personal_results (title, difficulty)')
            cur.execute('CREATE INDEX IF NOT EXISTS idx_personal_ts ON personal_results (timestamp)')

            # ライバルスコアテーブル (最新のみ保持)
            cur.execute('''
                CREATE TABLE IF NOT EXISTS rival_scores (
                    rival_name TEXT NOT NULL,
                    title TEXT NOT NULL,
                    difficulty TEXT NOT NULL,
                    lamp INTEGER NOT NULL,
                    score INTEGER NOT NULL,
                    exscore INTEGER,
                    PRIMARY KEY (rival_name, title, difficulty)
                )
            ''')
            
            self._conn.commit()
            logger.info(f"SQLite DB 初期化完了: {self.db_path}")
        except Exception as e:
            logger.error(f"SQLite 初期化失敗: {e}")
            raise

    def execute(self, sql: str, params: tuple = ()) -> sqlite3.Cursor:
        try:
            cur = self._conn.cursor()
            cur.execute(sql, params)
            return cur
        except Exception as e:
            logger.error(f"SQL実行エラー: {sql} | {e}")
            raise

    def commit(self):
        self._conn.commit()

    def close(self):
        if self._conn:
            self._conn.close()

    # --- 個人リザルト操作 ---

    def insert_personal_result(self, data: dict):
        sql = '''
            INSERT INTO personal_results (
                title, difficulty, lamp, score, exscore, level, timestamp, detect_mode, bestscore, bestexscore
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        '''
        params = (
            data['title'], data['difficulty'], data['lamp'], data['score'],
            data.get('exscore'), data.get('level'), data['timestamp'],
            data.get('detect_mode'), data.get('bestscore'), data.get('bestexscore')
        )
        self.execute(sql, params)

    def delete_personal_result(self, row_id: int):
        self.execute("DELETE FROM personal_results WHERE id = ?", (row_id,))

    def get_all_personal_results(self) -> List[sqlite3.Row]:
        cur = self.execute("SELECT * FROM personal_results ORDER BY timestamp ASC")
        return cur.fetchall()

    # --- ライバル操作 ---

    def upsert_rival_score(self, rival_name: str, title: str, difficulty: str, score: int, lamp: int, exscore: Optional[int]):
        sql = '''
            INSERT INTO rival_scores (rival_name, title, difficulty, score, lamp, exscore)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(rival_name, title, difficulty) DO UPDATE SET
                score = excluded.score,
                lamp = excluded.lamp,
                exscore = excluded.exscore
        '''
        self.execute(sql, (rival_name, title, difficulty, score, lamp, exscore))

    def delete_rival(self, rival_name: str):
        self.execute("DELETE FROM rival_scores WHERE rival_name = ?", (rival_name,))

    def get_rival_scores(self, rival_name: str) -> List[sqlite3.Row]:
        cur = self.execute("SELECT * FROM rival_scores WHERE rival_name = ?", (rival_name,))
        return cur.fetchall()
