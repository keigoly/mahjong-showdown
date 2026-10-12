"""牌効率: 打牌候補ごとの向聴数・受け入れ (有効牌の残り枚数)・その先の質。

受け入れは「自分から見えていない枚数」(= 4 - 手牌・河・副露・ドラ表示で見えた枚数) で数える。
1 歩先読み (next_avg) は、有効牌を引いたあと最善の打牌をしたときの次の受け入れの平均:
    1 向聴 → 聴牌したときの待ち枚数の平均 (聴牌の質)
    2 向聴以上 → 1 段進んだときの受け入れの平均
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache

from .shanten import shanten, shanten_chiitoi, shanten_kokushi, shanten_regular

FORMS = ("all", "regular", "chiitoi")  # all = 一般形・七対子・国士の最小 (和了判定・待ちに使う)


def shanten_form(hand: list[int] | tuple[int, ...], melds: int, form: str) -> int:
    if form == "regular":
        return shanten_regular(hand, melds)
    if form == "chiitoi":
        return shanten_chiitoi(hand) if melds == 0 else 99
    if form == "kokushi":
        return shanten_kokushi(hand) if melds == 0 else 99
    return shanten(hand, melds)


@lru_cache(maxsize=1 << 18)
def _effective_form(hand: tuple[int, ...], melds: int, form: str) -> tuple[int, tuple[int, ...]]:
    """(向聴数, 向聴数を 1 つ進める牌の種類) — 手牌 3n+1 枚・指定の形で。"""
    s = shanten_form(hand, melds, form)
    cur = list(hand)
    eff = []
    for t in range(34):
        if cur[t] >= 4:
            continue
        cur[t] += 1
        if shanten_form(cur, melds, form) < s:
            eff.append(t)
        cur[t] -= 1
    return s, tuple(eff)


def _effective(hand: tuple[int, ...], melds: int) -> tuple[int, tuple[int, ...]]:
    return _effective_form(hand, melds, "all")


def effective_tiles(hand: list[int] | tuple[int, ...], melds: int = 0, form: str = "all") -> tuple[int, tuple[int, ...]]:
    return _effective_form(tuple(hand), melds, form)


@dataclass
class DiscardEval:
    kind: int
    shanten: int
    ukeire: int
    effective: list[tuple[int, int]] = field(default_factory=list)  # (種類, 残り枚数)
    next_avg: float | None = None
    good_wait_rate: float | None = None  # 1 向聴: 聴牌したとき待ちが 5 枚以上になる割合 (枚数重み)

    @property
    def effective_kinds(self) -> int:
        return len(self.effective)


def _best_next(hand14: list[int], melds: int, unseen: list[int], form: str = "all") -> tuple[int, int]:
    """14 枚の手から最善の打牌をしたときの (向聴数, 受け入れ)。"""
    best = (99, -1)
    for d in range(34):
        if hand14[d] == 0:
            continue
        hand14[d] -= 1
        s, eff = _effective_form(tuple(hand14), melds, form)
        u = sum(unseen[k] for k in eff)
        hand14[d] += 1
        if (s, -u) < (best[0], -best[1]):
            best = (s, u)
    return best


def evaluate_discards(
    hand: list[int],
    unseen: list[int],
    melds: int = 0,
    lookahead_top: int = 6,
    form: str = "all",
) -> list[DiscardEval]:
    """14 枚 (3n+2 枚) の手の打牌候補を、向聴数 → 受け入れの順で並べて返す。

    unseen: 自分から見えていない枚数 (34 種)。
    lookahead_top: 1 歩先読みを付ける候補の数 (重いので上位だけ)。
    """
    cur = list(hand)
    out: list[DiscardEval] = []
    for d in range(34):
        if cur[d] == 0:
            continue
        cur[d] -= 1
        s, eff = _effective_form(tuple(cur), melds, form)
        effl = [(k, unseen[k]) for k in eff if unseen[k] > 0]
        out.append(DiscardEval(d, s, sum(n for _, n in effl), effl))
        cur[d] += 1
    out.sort(key=lambda e: (e.shanten, -e.ukeire, e.kind))

    for e in out[:lookahead_top]:
        if e.shanten < 0 or not e.effective:
            continue
        cur[e.kind] -= 1
        tot = 0
        acc = 0.0
        good = 0
        for k, n in e.effective:
            cur[k] += 1
            unseen[k] -= 1
            s2, u2 = _best_next(cur, melds, unseen, form)
            unseen[k] += 1
            cur[k] -= 1
            tot += n
            acc += n * u2
            if e.shanten == 1 and u2 >= 5:
                good += n
        cur[e.kind] += 1
        if tot:
            e.next_avg = acc / tot
            if e.shanten == 1:
                e.good_wait_rate = good / tot
    return out


def waits(hand13: list[int], unseen: list[int], melds: int = 0) -> list[tuple[int, int]]:
    """聴牌 (13 枚) の待ち (種類, 残り枚数)。聴牌でなければ空。"""
    s, eff = _effective(tuple(hand13), melds)
    if s != 0:
        return []
    return [(k, unseen[k]) for k in eff]
