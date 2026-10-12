"""向聴数 (シャンテン数)。

一般形は「色ごとの分解」を種類の並び (9 枚の枚数) で覚えておき、色をまたいで組み合わせる。
同じ並びは何度でも出てくるので、2 回目からは辞書を引くだけになる (受け入れ計算で数万回呼ぶため)。

    一般形: 8 - 2×面子 - 塔子 (面子+塔子 ≤ 4 まで) - 雀頭
    七対子: 6 - 対子数 + max(0, 7 - 種類数)
    国士  : 13 - 么九牌の種類数 - (么九牌の対子があれば 1)

-1 は和了形。副露がある手は melds に副露数を渡す (七対子・国士は見ない)。
"""

from __future__ import annotations

from functools import lru_cache

from .tiles import YAOCHU

Opt = tuple[int, int, int]  # (面子, 塔子, 雀頭 0/1)


def _prune(opts: set[Opt]) -> tuple[Opt, ...]:
    """雀頭の有無ごとに、面子・塔子がともに劣る組を落とす。"""
    keep = []
    for m, t, j in opts:
        if not any(j2 == j and m2 >= m and t2 >= t and (m2, t2) != (m, t) for m2, t2, j2 in opts):
            keep.append((m, t, j))
    return tuple(sorted(keep))


@lru_cache(maxsize=None)
def _suit(c: tuple[int, ...]) -> tuple[Opt, ...]:
    """数牌 1 色 (9 枚の枚数) の分解の候補。"""
    i = 0
    while i < 9 and c[i] == 0:
        i += 1
    if i == 9:
        return ((0, 0, 0),)
    lst = list(c)
    opts: set[Opt] = set()

    def take(dm: int, dt: int, dj: int, *idx: int) -> None:
        for k in idx:
            lst[k] -= 1
        sub = tuple(lst)
        for k in idx:
            lst[k] += 1
        for m, t, j in _suit(sub):
            if j + dj <= 1:
                opts.add((m + dm, t + dt, j + dj))

    if c[i] >= 3:
        take(1, 0, 0, i, i, i)
    if i <= 6 and c[i + 1] and c[i + 2]:
        take(1, 0, 0, i, i + 1, i + 2)
    if c[i] >= 2:
        take(0, 0, 1, i, i)
        take(0, 1, 0, i, i)
    if i <= 7 and c[i + 1]:
        take(0, 1, 0, i, i + 1)
    if i <= 6 and c[i + 2]:
        take(0, 1, 0, i, i + 2)
    take(0, 0, 0, i)  # 孤立牌として捨てる
    return _prune(opts)


_HONOR: dict[int, tuple[Opt, ...]] = {
    0: ((0, 0, 0),),
    1: ((0, 0, 0),),
    2: ((0, 0, 1), (0, 1, 0)),
    3: ((0, 0, 1), (0, 1, 0), (1, 0, 0)),
    4: ((0, 1, 1), (1, 0, 0)),
}


@lru_cache(maxsize=1 << 18)
def _regular(c: tuple[int, ...], melds: int) -> int:
    groups = [_suit(c[0:9]), _suit(c[9:18]), _suit(c[18:27])]
    groups += [_HONOR[n] for n in c[27:34] if n >= 2]
    states: tuple[Opt, ...] = ((0, 0, 0),)
    for g in groups:
        if g == ((0, 0, 0),):
            continue
        states = _prune({(m1 + m2, t1 + t2, j1 + j2) for m1, t1, j1 in states for m2, t2, j2 in g if j1 + j2 <= 1})
    best = 8
    for m, t, j in states:
        mm = m + melds
        best = min(best, 8 - 2 * mm - min(t, 4 - mm) - j)
    return best


def shanten_regular(counts: list[int] | tuple[int, ...], melds: int = 0) -> int:
    return _regular(tuple(counts), melds)


def shanten_chiitoi(counts: list[int] | tuple[int, ...]) -> int:
    pairs = sum(1 for n in counts if n >= 2)
    kinds = sum(1 for n in counts if n >= 1)
    return 6 - pairs + max(0, 7 - kinds)


def shanten_kokushi(counts: list[int] | tuple[int, ...]) -> int:
    kinds = sum(1 for k in YAOCHU if counts[k] >= 1)
    pair = any(counts[k] >= 2 for k in YAOCHU)
    return 13 - kinds - (1 if pair else 0)


def shanten(counts: list[int] | tuple[int, ...], melds: int = 0) -> int:
    """手牌 (34 種の枚数) の向聴数。melds = 副露・暗槓の数。"""
    s = _regular(tuple(counts), melds)
    if melds == 0 and sum(counts) >= 13:
        s = min(s, shanten_chiitoi(counts), shanten_kokushi(counts))
    return s
