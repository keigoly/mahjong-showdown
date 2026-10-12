"""シミュレーターの中で直接動かす打ち手 (テストと、サーバーで席が空いたときの代打ち)。"""

from __future__ import annotations

import math
import random

from .danger import deal_in_probability
from .efficiency import evaluate_discards
from .engine import CallOption, View, WinInfo
from .shanten import shanten
from .tiles import Tile, counts34, dora_from_indicator, is_yaochu


def _pick(hand: list[Tile], kind: int) -> Tile:
    same = [t for t in hand if t.kind == kind]
    plain = [t for t in same if not t.red]
    return plain[0] if plain else same[0]


class RandomAgent:
    """ランダムに切る (喰い替えは避ける)。和了はする・鳴かない・立直しない。"""

    def __init__(self, name: str = "random", seed: int | None = None):
        self.name = name
        self.rng = random.Random(seed)

    def discard(self, view: View) -> tuple[Tile, bool]:
        ok = [t for t in view.hand if t.kind not in view.forbidden] or list(view.hand)
        return self.rng.choice(ok), False

    def call(self, view: View, options: list[CallOption]) -> CallOption | None:
        return None

    def tsumo(self, view: View, win: WinInfo) -> bool:
        return True

    def ron(self, view: View, tile: Tile, win: WinInfo) -> bool:
        return True

    def notify(self, event: dict) -> None:
        pass


class EfficiencyAgent(RandomAgent):
    """牌効率どおりに打ち、立直を受けたら遅い手は降りる。役牌はポン、断么九と鳴いた手は進むときだけ鳴く。"""

    def __init__(self, name: str = "efficiency", *, fold_shanten: int = 2, fold_late_wall: int = 32, calls: bool = True,
                 riichi: bool = True):
        super().__init__(name)
        self.fold_shanten, self.fold_late_wall, self.calls, self.riichi_on = fold_shanten, fold_late_wall, calls, riichi

    def discard(self, view: View) -> tuple[Tile, bool]:
        hand34 = counts34(view.hand)
        unseen = view.unseen()
        melds = len(view.my_melds)
        evals = [e for e in evaluate_discards(hand34, unseen, melds, lookahead_top=0) if e.kind not in view.forbidden] \
            or evaluate_discards(hand34, unseen, melds, lookahead_top=0)
        threats = [o for o in view.opponents() if o.riichi]
        visible = view.visible_counts()
        best = evals[0]
        fold = bool(threats) and (best.shanten >= self.fold_shanten or (best.shanten == 1 and view.wall_left < self.fold_late_wall))
        if fold:
            order = [e.kind for e in evals]

            def danger(k: int) -> float:
                return 1 - math.prod(1 - deal_in_probability(k, o, visible)[0] for o in threats)

            kind = min(order, key=lambda k: (round(danger(k), 4), order.index(k)))
        else:
            dora = {dora_from_indicator(t.kind) for t in view.dora_indicators}
            top = [e for e in evals if (e.shanten, e.ukeire) == (best.shanten, best.ukeire)]
            kind = min(top, key=lambda e: (e.kind in dora, 0 if e.kind >= 27 else (1 if e.kind % 9 in (0, 8) else 2))).kind
        tile = _pick(view.hand, kind)
        rest = list(view.hand)
        rest.remove(tile)
        riichi = self.riichi_on and not view.my_riichi and not view.my_melds and shanten(counts34(rest)) == 0 \
            and view.wall_left >= 4 and view.table.scores[view.seat] >= 1000
        return tile, riichi

    def call(self, view: View, options: list[CallOption]) -> CallOption | None:
        if view.my_riichi or not self.calls:
            return None
        melds = len(view.my_melds)
        now = shanten(counts34(view.hand), melds)
        t = view.table
        yakuhai = {31, 32, 33, 27 + (view.seat - t.dealer) % 4, 27 + min(t.round_index // 4, 3)}
        has_yaku = any(m.kind == "pon" and m.tiles[0].kind in yakuhai for m in view.my_melds)
        for opt in options:
            rest = list(view.hand)
            for x in opt.tiles:
                rest.remove(x)
            c = counts34(rest)
            after = min((shanten([c[j] - (1 if j == k else 0) for j in range(34)], melds + 1)
                         for k in range(34) if c[k] and k not in opt.forbidden()), default=9)
            if opt.kind == "pon" and opt.called.kind in yakuhai and after <= now:
                return opt
            tiles = [x for m in view.my_melds for x in m.tiles] + [*opt.tiles, opt.called]
            tanyao = all(not is_yaochu(x.kind) for x in tiles) and sum(1 for x in rest if is_yaochu(x.kind)) <= 1
            if (has_yaku or tanyao) and after < now:
                return opt
        return None
