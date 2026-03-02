"""SDVX向けのコアクラス・Enum定義"""
from enum import Enum
from src.logger import get_logger
logger = get_logger(__name__)


class difficulty(Enum):
    """難易度を表すクラス。INF/GRV/HVN/VVD/XCDはゲーム上MXMと同一枠のためmaximumに統合。"""
    novice   = 0  # NOV
    advanced = 1  # ADV
    exhaust  = 2  # EXH
    maximum  = 3  # MXM / INF / GRV / HVN / VVD / XCD（4th枠の総称）

    def __str__(self):
        return {0: 'NOV', 1: 'ADV', 2: 'EXH', 3: 'MXM'}[self.value]

    def to_db_key(self) -> str:
        """musiclist.pklのジャケットDBキーに変換。MXM枠はAPPEND扱い。"""
        return {0: 'nov', 1: 'adv', 2: 'exh', 3: 'APPEND'}[self.value]


class clear_lamp(Enum):
    """クリアランプを表すクラス"""
    noplay   = 0  # 未プレー
    played   = 1  # クリア失敗
    clear    = 2  # ノーマルクリア
    exc      = 3  # エクセッシブクリア
    maxxive  = 4  # MAXXIVE（EXCとUCの間）
    uc       = 5  # アルティメットチェーン（フルコンボ相当）
    puc      = 6  # パーフェクトアルティメットチェーン（全CRITICAL）

    def __lt__(self, other):
        return self.value < other.value

    def __str__(self):
        _NAMES = {0: 'NO PLAY', 1: 'PLAYED', 2: 'COMP', 3: 'EXC-COMP', 4: 'MAXXIVE', 5: 'UC', 6: 'PUC'}
        return _NAMES[self.value]


class detect_mode(Enum):
    """検出モード用のEnum"""
    init   = 0  # 初期状態
    select = 1  # 選曲画面
    detect = 2  # 曲決定後の楽曲情報画面
    play   = 3  # プレー画面
    result = 4  # リザルト画面


class screen_orientation(Enum):
    """画面の向き（縦1080pの回転方向）"""
    top_up    = 0  # 上向き（portrait標準。OBS上で正立している場合）
    top_right = 1  # 上が右方向（rotate 90°で正立する）
    top_left  = 2  # 上が左方向（rotate 270°で正立する）

    def rotate_angle(self) -> int:
        """正立させるために必要な回転角度を返す"""
        return {0: 0, 1: 90, 2: 270}[self.value]


class Judge:
    """リザルト画面の判定内訳（JUSTICE CRITICAL / CRITICAL / NEAR / ERROR）。
    現状SDVXでは直接読み取る予定はないが、将来の拡張に備えて定義しておく。
    EXスコア = (justice_critical + critical) × 2 + near × 1
    """
    def __init__(self, justice_critical: int = 0, critical: int = 0, near: int = 0, error: int = 0):
        self.justice_critical = justice_critical  # JUSTICE CRITICAL（最高判定）
        self.critical         = critical          # CRITICAL
        self.near             = near              # NEAR
        self.error            = error             # ERROR

    @property
    def exscore(self) -> int:
        """EXスコア（自動計算: (JC + CRITICAL)×2 + NEAR×1）"""
        return (self.justice_critical + self.critical) * 2 + self.near

    @property
    def notes(self) -> int:
        """総ノーツ数（自動計算）"""
        return self.justice_critical + self.critical + self.near + self.error

    def __eq__(self, other):
        if not isinstance(other, Judge):
            return False
        return (self.justice_critical == other.justice_critical and
                self.critical         == other.critical         and
                self.near             == other.near             and
                self.error            == other.error)

    def __hash__(self):
        return hash((self.justice_critical, self.critical, self.near, self.error))

    def __str__(self):
        return (f"JC:{self.justice_critical}, CRITICAL:{self.critical}, NEAR:{self.near}, ERROR:{self.error}"
                f" | EX:{self.exscore}, notes:{self.notes}")
