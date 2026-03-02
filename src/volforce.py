"""SDVX Volforce 計算。

VF寄与値 = int(level × score × grade_coef × lamp_coef × 20 / 10,000,000)
総VF = 上位50曲の VF寄与値 の合計
"""
from src.classes import clear_lamp
from src.funcs import get_grade_coef

# ランプ係数
_LAMP_COEF: dict[clear_lamp, float] = {
    clear_lamp.puc:     1.10,
    clear_lamp.uc:      1.05, # nablaで係数が変更された
    clear_lamp.maxxive: 1.04,
    clear_lamp.exc:     1.02,
    clear_lamp.clear:   1.00,
    clear_lamp.played:  0.50,
    clear_lamp.noplay:  0.00,
}

VF_TOP_N = 50  # 総VF算出に使う上位曲数


def calc_vf(level: int, score: int, lamp: clear_lamp) -> int:
    """1譜面のVolforce寄与値を計算する。

    Args:
        level: 譜面レベル (1-20)
        score: スコア (0-10,000,000)
        lamp: クリアランプ

    Returns:
        int: VF寄与値。未プレーまたは引数不正なら 0。
    """
    if not level or not score or lamp == clear_lamp.noplay:
        return 0
    grade_coef = get_grade_coef(score)
    lamp_coef = _LAMP_COEF.get(lamp, 0.0)
    return int(level * score * grade_coef * lamp_coef * 20 / 10_000_000)


def calc_total_vf(vf_list: list[int], top_n: int = VF_TOP_N) -> int:
    """VF寄与値リストから総Volforceを計算する。

    Args:
        vf_list: 各譜面の VF 寄与値リスト
        top_n: 上位何曲を合算するか（デフォルト50）

    Returns:
        int: 総Volforce
    """
    return sum(sorted(vf_list, reverse=True)[:top_n])


def get_lamp_coef(lamp: clear_lamp) -> float:
    """ランプ係数を返す。"""
    return _LAMP_COEF.get(lamp, 0.0)
