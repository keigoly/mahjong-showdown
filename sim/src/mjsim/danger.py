"""危険度: この牌を切ったら、その相手に放銃する確率。

立直者への放銃率は「牌の種類 (現物・筋・片筋・無筋・字牌の見え枚数)」でほぼ決まる、という
定番の統計の型をそのまま使う。初期値 (BASE_VS_RIICHI) は一般に知られた目安で、
天鳳の牌譜で較正したら knowledge/calibration/ の表に置き換える (docs/DESIGN.md §4)。

立直していない相手は「聴牌している確率 × 聴牌していたときの危険度」で見積もる。
"""

from __future__ import annotations

from dataclasses import dataclass, field

# 立直者に対する放銃率 (天鳳 鳳凰卓 2019・立直 130 万件・宣言牌の直後・現物を除く)。
# 出典: https://blog.kobalab.net/entry/2021/01/16/130716 (docs/RULES.md §4)。キーは classify() の分類名。
BASE_VS_RIICHI: dict[str, float] = {
    "現物": 0.0,
    "字牌3枚見え": 0.0001,
    "字牌2枚見え": 0.0028,
    "字牌1枚見え": 0.0211,
    "字牌0枚見え": 0.0429,
    "筋19": 0.0202,
    "筋28": 0.0350,
    "筋37": 0.0462,
    "両筋456": 0.0281,
    "片筋456": 0.0710,
    "無筋19": 0.0665,
    "無筋28": 0.0772,
    "無筋37": 0.0842,
    "無筋456": 0.1156,
}
CALIBRATION_SOURCE = "天鳳 鳳凰卓 2019 の実測 (kobalab) + 残り筋本数の補正 (NAGA の近似式)"
# 無筋の危険度 (%) ≈ K / 残り筋本数 (多喜田翔吾『麻雀AI「NAGA」の鉄戦術』2024)。残り 12 本で上の表とほぼ一致する。
_MUSUJI_K = {"無筋456": 140.0, "無筋37": 100.0, "無筋28": 90.0, "無筋19": 80.0}
_REF_SUJI = 12

_SUJI = {1: (4,), 2: (5,), 3: (6,), 4: (1, 7), 5: (2, 8), 6: (3, 9), 7: (4,), 8: (5,), 9: (6,)}


@dataclass
class Opponent:
    """自分から見た相手 1 人の情報。"""

    seat: int
    discards: list[int] = field(default_factory=list)  # 河 (鳴かれた牌も含む) の種類
    riichi: bool = False
    riichi_turn: int | None = None  # 立直宣言牌の河の位置
    melds: int = 0  # 副露数 (暗槓を除く)
    passed: set[int] = field(default_factory=set)  # 立直後に誰かが切って通った牌 (立直者には安全)
    dora_melded: int = 0  # 副露に見えているドラ・赤の枚数 (打点の目安)

    @property
    def turn(self) -> int:
        return len(self.discards)

    def safe_kinds(self) -> set[int]:
        """この相手に対して当たらない種類 (現物 + 立直後に通った牌)。"""
        s = set(self.discards)
        if self.riichi:
            s |= self.passed
        return s


def _ryanmen_blocked(k: int, visible: list[int]) -> tuple[bool, bool]:
    """(両面で当たり得ない = ノーチャンス, 両面の形が残り 1 枚しかない = ワンチャンス)。"""
    n = k % 9 + 1
    base = k - (n - 1)
    shapes = []
    if n <= 7:
        shapes.append((base + n, base + n + 1))  # n+1, n+2 の両面 (n と n+3 待ち)
    if n >= 3:
        shapes.append((base + n - 3, base + n - 2))  # n-2, n-1 の両面
    if not shapes:
        return False, False
    possible = [s for s in shapes if visible[s[0]] < 4 and visible[s[1]] < 4]
    if not possible:
        return True, False
    one = all(min(4 - visible[a], 4 - visible[b]) <= 1 for a, b in possible)
    return False, one


def remaining_suji(opp: Opponent) -> int:
    """まだ通っていない筋の本数 (全 18 本: 各色の 1-4/2-5/3-6/4-7/5-8/6-9)。両端どちらかが安全なら消える。"""
    safe = opp.safe_kinds()
    rest = 0
    for suit in range(3):
        for a in range(6):
            if suit * 9 + a not in safe and suit * 9 + a + 3 not in safe:
                rest += 1
    return rest


def classify(k: int, opp: Opponent, visible: list[int]) -> str:
    """牌の分類 (BASE_VS_RIICHI のキー)。"""
    if k in opp.safe_kinds():
        return "現物"
    if k >= 27:
        seen = min(visible[k], 3)
        return f"字牌{seen}枚見え"
    n = k % 9 + 1
    base = k - (n - 1)
    suji_hits = [m for m in _SUJI[n] if (base + m - 1) in opp.safe_kinds()]
    if n in (4, 5, 6):
        if len(suji_hits) == 2:
            return "両筋456"
        if len(suji_hits) == 1:
            return "片筋456"
        return "無筋456"
    group = {1: "19", 9: "19", 2: "28", 8: "28", 3: "37", 7: "37"}[n]
    return ("筋" if suji_hits else "無筋") + group


def danger_if_tenpai(k: int, opp: Opponent, visible: list[int], table: dict[str, float] | None = None) -> tuple[float, str]:
    """相手が聴牌しているとき、k を切って放銃する確率と分類 (説明用)。"""
    table = table or BASE_VS_RIICHI
    cls = classify(k, opp, visible)
    p = table[cls]
    if p == 0.0:
        return 0.0, cls
    label = cls
    if k < 27 and not cls.startswith(("筋", "両筋")):
        no_chance, one_chance = _ryanmen_blocked(k, visible)
        if no_chance:
            p *= 0.35
            label += "・ノーチャンス"
        elif one_chance:
            p *= 0.7
            label += "・ワンチャンス"
    # 巡目の代わりに残り筋本数で補正する (筋が通るほど残りの無筋に危険が集まる)
    rest = remaining_suji(opp)
    if cls in _MUSUJI_K and table is BASE_VS_RIICHI:
        p *= (_MUSUJI_K[cls] / max(rest, 3) / 100) / BASE_VS_RIICHI[cls]
    elif cls == "片筋456":
        p *= 0.47 + 0.53 * _REF_SUJI / max(rest, 3)  # 片側の両面だけが残りに比例する
    return min(p, 0.5), label


def tenpai_probability(opp: Opponent) -> float:
    """相手が聴牌している確率の目安 (立直なら 1)。"""
    if opp.riichi:
        return 1.0
    t = opp.turn
    if opp.melds >= 3:
        return min(0.95, 0.6 + 0.05 * max(0, t - 4))
    if opp.melds == 2:
        return min(0.8, 0.25 + 0.05 * max(0, t - 4))
    if opp.melds == 1:
        return min(0.6, 0.1 + 0.04 * max(0, t - 4))
    return min(0.35, 0.03 + 0.02 * max(0, t - 6))


def deal_in_probability(k: int, opp: Opponent, visible: list[int], table: dict[str, float] | None = None) -> tuple[float, str]:
    p, label = danger_if_tenpai(k, opp, visible, table)
    pt = tenpai_probability(opp)
    if not opp.riichi:
        p *= 0.85  # 黙聴・副露の待ちは立直ほど偏らない分を割り引く目安
    return p * pt, label


def is_threat(opp: Opponent) -> bool:
    """押し引きを考えるべき相手か (立直・2 副露以上・ドラの見える副露)。"""
    return opp.riichi or opp.melds >= 2 or (opp.melds >= 1 and opp.dora_melded >= 2)
