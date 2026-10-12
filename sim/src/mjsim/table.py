"""卓の状態と終局の規則 (局の進み・本場・供託・西入・アガリやめ・飛び・着順・順位点)。"""

from __future__ import annotations

import math
from dataclasses import dataclass

from .rules import Rules


@dataclass(frozen=True)
class TableState:
    round_index: int
    honba: int
    kyotaku: int
    scores: tuple[int, int, int, int]

    @property
    def dealer(self) -> int:
        return self.round_index % 4

    def label(self) -> str:
        return round_label(self.round_index, self.honba)


def round_label(round_index: int, honba: int = 0) -> str:
    wind = "東南西北"[min(round_index // 4, 3)]
    s = f"{wind}{round_index % 4 + 1}局"
    return s + (f" {honba}本場" if honba else "")


def _ceil100(x: float) -> int:
    return int(math.ceil(x / 100.0) * 100)


def win_payments(winner: int, loser: int | None, value: int, dealer: int, honba: int, kyotaku: int) -> list[int]:
    """和了 1 回の点数移動。value は和了者から見たロン打点 (子なら子のロン、親なら親のロン)。"""
    d = [0, 0, 0, 0]
    if loser is not None:
        pay = value + 300 * honba
        d[loser] -= pay
        d[winner] += pay
    else:
        if winner == dealer:
            basic = value / 6
            each = _ceil100(2 * basic) + 100 * honba
            for p in range(4):
                if p != winner:
                    d[p] -= each
                    d[winner] += each
        else:
            basic = value / 4
            for p in range(4):
                if p == winner:
                    continue
                each = (_ceil100(2 * basic) if p == dealer else _ceil100(basic)) + 100 * honba
                d[p] -= each
                d[winner] += each
    d[winner] += 1000 * kyotaku
    return [int(x) for x in d]


def draw_payments(tenpai: list[bool]) -> list[int]:
    n = sum(tenpai)
    if n in (0, 4):
        return [0, 0, 0, 0]
    return [3000 // n if t else -3000 // (4 - n) for t in tenpai]


def after_kyoku(
    state: TableState,
    rules: Rules,
    deltas: list[int],
    *,
    dealer_continues: bool,
    dealer_won: bool,
    is_draw: bool,
    kyotaku_next: int,
) -> tuple[TableState, bool]:
    """1 局の結果を反映した次の局の状態と、終局したか。"""
    scores = tuple(s + d for s, d in zip(state.scores, deltas))
    honba_next = state.honba + 1 if (is_draw or dealer_won) else 0
    ri_next = state.round_index if dealer_continues else state.round_index + 1
    nxt = TableState(ri_next, honba_next, kyotaku_next, scores)  # type: ignore[arg-type]
    if rules.tobi and min(scores) < 0:
        return nxt, True
    last = rules.last_round
    if state.round_index < last:
        return nxt, False
    top_score = max(scores)
    dealer = state.dealer
    dealer_is_top = scores[dealer] == top_score and all(scores[p] < top_score for p in range(dealer))
    reached = top_score >= rules.return_points
    if state.round_index > last and reached:
        return nxt, True  # 延長戦はサドンデス
    if dealer_continues:
        stop = (dealer_won and rules.agari_yame) or (is_draw and rules.tenpai_yame)
        if stop and dealer_is_top and (reached or not rules.west_round):
            return nxt, True
        return nxt, False
    if not rules.west_round or reached:
        return nxt, True
    return nxt, ri_next > last + 4  # 西4 局まで


def final_ranks(scores: tuple[int, ...] | list[int]) -> list[int]:
    """着順 (0 = 1 位)。同点は起家に近い方が上。"""
    order = sorted(range(4), key=lambda p: (-scores[p], p))
    ranks = [0] * 4
    for r, p in enumerate(order):
        ranks[p] = r
    return ranks


def points_for(rules: Rules, rank: int, score: float) -> float:
    return rules.rank_points[rank] + (score - rules.score_base) * rules.score_weight


