"""麻雀のシミュレーターの本体: 四人打ち・東南戦・赤あり。

v1.5: チー・ポンあり (カンなし)。途中流局なし / ダブロンなし (上家取り) / 流し満貫なし。
扱うもの: 立直・一発 (鳴きで消える)・ダブル立直・海底・河底・裏ドラ・フリテン (捨て牌・同巡・立直後の見逃し)・
喰い替えの禁止・本場・供託・西入・アガリやめ・飛び。終局判定は placement.after_kyoku (順位の見込みと同じ規則)。
牌譜は天鳳 JSON 形式で残す (`mjc review` でそのまま検討できる)。

各席の判断は Agent が行う。Agent に渡す View は「その席から見える情報」だけ (他家の手牌は入れない)。
出来事 (局の開始・打牌・鳴き・立直・和了・流局・終局) は on_event に流す (観戦・記録・サーバー用)。
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from typing import Protocol

import mahjong.constants as C
from mahjong.hand_calculating.hand import HandCalculator
from mahjong.hand_calculating.hand_config import HandConfig, OptionalRules
from mahjong.meld import Meld as LibMeld

from .danger import Opponent
from .efficiency import effective_tiles
from .rules import Rules
from .scoring import MeldInfo, _pick_id
from .shanten import shanten
from .table import TableState, after_kyoku, draw_payments, final_ranks, points_for, round_label
from .tiles import Tile, counts34, dora_from_indicator, tile_str, to_tenhou_code


@dataclass
class RiverTile:
    tile: Tile
    tsumogiri: bool
    riichi: bool = False
    called: bool = False

_CALC = HandCalculator()
_WINDS = (C.EAST, C.SOUTH, C.WEST, C.NORTH)
_LEVELS = {"mangan": "満貫", "haneman": "跳満", "baiman": "倍満", "sanbaiman": "三倍満", "yakuman": "役満"}


def build_wall(rng: random.Random, aka: bool = True) -> list[Tile]:
    wall = [Tile(k, aka and k in (4, 13, 22) and i == 0) for k in range(34) for i in range(4)]
    rng.shuffle(wall)
    return wall


@dataclass
class WinInfo:
    winner: int
    loser: int | None  # ツモなら None
    tile: Tile
    han: int
    fu: int
    yaku: list[str]
    payments: list[int]  # 本場・供託込みの点数移動
    label: str  # 例 "30符2飜2000点" / "満貫8000点"

    @property
    def gain(self) -> int:
        return self.payments[self.winner]


@dataclass(frozen=True)
class CallOption:
    kind: str  # pon / chi
    tiles: tuple[Tile, Tile]  # 手牌から出す 2 枚
    called: Tile
    from_seat: int

    def label(self) -> str:
        if self.kind == "pon":
            return f"ポン {tile_str(self.called.kind, self.called.red)}"
        ks = sorted([self.tiles[0], self.tiles[1], self.called], key=lambda t: t.kind)
        return "チー " + "".join(tile_str(t.kind, t.red) for t in ks)

    def forbidden(self) -> set[int]:
        """喰い替えで切れない牌の種類 (同じ牌・チーの筋の反対側)。"""
        c = self.called.kind
        out = {c}
        if self.kind == "chi":
            ks = sorted([self.tiles[0].kind, self.tiles[1].kind, c])
            if c == ks[0] and c % 9 <= 5:
                out.add(c + 3)
            if c == ks[2] and c % 9 >= 3:
                out.add(c - 3)
        return out


@dataclass
class SeatState:
    hand: list[Tile]
    river: list[RiverTile] = field(default_factory=list)
    melds: list[MeldInfo] = field(default_factory=list)
    riichi: bool = False
    riichi_index: int | None = None
    ippatsu: bool = False
    double_riichi: bool = False
    furiten_temp: bool = False
    furiten_riichi: bool = False
    passed: set[int] = field(default_factory=set)  # この席の立直後に通った牌の種類


@dataclass
class View:
    """ある席から見える情報 (他家の手牌は含まない)。"""

    seat: int
    table: TableState  # いまの点数と供託 (立直の供託を反映済み)
    hand: list[Tile]
    drawn: Tile | None
    rivers: list[list[RiverTile]]
    melds: list[list[MeldInfo]]
    riichi: list[bool]
    riichi_index: list[int | None]
    passed: list[set[int]]
    dora_indicators: list[Tile]
    wall_left: int
    rules: Rules
    forbidden: set[int] = field(default_factory=set)  # 喰い替えで切れない牌

    @property
    def my_riichi(self) -> bool:
        return self.riichi[self.seat]

    @property
    def my_melds(self) -> list[MeldInfo]:
        return self.melds[self.seat]

    def visible_counts(self) -> list[int]:
        v = counts34(self.hand)
        for rv in self.rivers:
            for r in rv:
                if not r.called:
                    v[r.tile.kind] += 1
        for ms in self.melds:
            for m in ms:
                for t in m.tiles:
                    v[t.kind] += 1
        for t in self.dora_indicators:
            v[t.kind] += 1
        return [min(4, x) for x in v]

    def unseen(self) -> list[int]:
        return [4 - x for x in self.visible_counts()]

    def opponents(self) -> list[Opponent]:
        dora = {dora_from_indicator(t.kind) for t in self.dora_indicators}
        return [
            Opponent(seat=q, discards=[r.tile.kind for r in self.rivers[q]], riichi=self.riichi[q],
                     riichi_turn=self.riichi_index[q], melds=len(self.melds[q]), passed=set(self.passed[q]),
                     dora_melded=sum(1 for m in self.melds[q] for t in m.tiles if t.red or t.kind in dora))
            for q in range(4) if q != self.seat
        ]

    @classmethod
    def from_dict(cls, d: dict, rules: Rules | None = None) -> "View":
        """to_dict の逆 (サーバー越しの要求から局面を組み立て直す。ボットが同じ判断のコードを使うため)。"""
        from .rules import get_rules
        from .tiles import parse_tile

        def tl(xs: list[str]) -> list[Tile]:
            return [parse_tile(x) for x in xs]

        tb = d["table"]
        table = TableState(tb["round"], tb["honba"], tb["kyotaku"], tuple(tb["scores"]))  # type: ignore[arg-type]
        return cls(
            seat=d["seat"], table=table, hand=tl(d["hand"]),
            drawn=parse_tile(d["drawn"]) if d.get("drawn") else None,
            rivers=[[RiverTile(parse_tile(r["tile"]), r["tsumogiri"], r["riichi"], r["called"]) for r in rv] for rv in d["rivers"]],
            melds=[[MeldInfo(m["kind"], tl(m["tiles"]), parse_tile(m["called"]) if m.get("called") else None, m.get("from"))
                    for m in ms] for ms in d["melds"]],
            riichi=list(d["riichi"]), riichi_index=list(d["riichi_index"]),
            passed=[{parse_tile(x).kind for x in ps} for ps in d["passed"]],
            dora_indicators=tl(tb["dora_indicators"]), wall_left=tb["wall"], rules=rules or get_rules("tenhou-houou"),
            forbidden={parse_tile(x).kind for x in d.get("forbidden", [])},
        )

    def to_dict(self) -> dict:
        """選手に渡す局面 (JSON にできる形)。牌は "5p" / "0p" (赤) / "東" の文字列。"""
        t = self.table

        def ts(x: Tile) -> str:
            return tile_str(x.kind, x.red)

        return {
            "seat": self.seat,
            "table": {"round": t.round_index, "round_label": round_label(t.round_index, t.honba), "honba": t.honba,
                      "kyotaku": t.kyotaku, "dealer": t.dealer, "scores": list(t.scores), "wall": self.wall_left,
                      "dora_indicators": [ts(x) for x in self.dora_indicators]},
            "hand": [ts(x) for x in sorted(self.hand, key=lambda y: (y.kind, not y.red))],
            "drawn": ts(self.drawn) if self.drawn is not None else None,
            "melds": [[{"kind": m.kind, "tiles": [ts(x) for x in m.tiles], "called": ts(m.called) if m.called else None,
                        "from": m.from_seat} for m in ms] for ms in self.melds],
            "rivers": [[{"tile": ts(r.tile), "tsumogiri": r.tsumogiri, "riichi": r.riichi, "called": r.called} for r in rv]
                       for rv in self.rivers],
            "riichi": list(self.riichi),
            "riichi_index": list(self.riichi_index),
            "passed": [sorted(tile_str(k) for k in ps) for ps in self.passed],
            "forbidden": sorted(tile_str(k) for k in self.forbidden),
        }


class Agent(Protocol):
    name: str

    def discard(self, view: View) -> tuple[Tile, bool]:
        """切る牌と立直するか。view.forbidden の牌は切らない。"""

    def call(self, view: View, options: list[CallOption]) -> CallOption | None:
        """鳴くならその選択肢、見送るなら None。"""

    def tsumo(self, view: View, win: WinInfo) -> bool: ...

    def ron(self, view: View, tile: Tile, win: WinInfo) -> bool: ...

    def notify(self, event: dict) -> None: ...


class QuitGame(Exception):
    pass


@dataclass
class KyokuOutcome:
    kind: str  # 和了 / 流局
    win: WinInfo | None
    tenpai: list[bool] | None
    deltas: list[int]  # 局の始めからの点数の変化 (立直の供託込み)
    record: list


def _call_string(opt: CallOption, caller: int) -> str:
    """天鳳 JSON の鳴きの文字列 (記号の位置 = 鳴いた相手の向き)。"""
    c = f"{to_tenhou_code(opt.called):02d}"
    own = [f"{to_tenhou_code(t):02d}" for t in sorted(opt.tiles, key=lambda t: (t.kind, not t.red))]
    if opt.kind == "chi":
        return "c" + c + own[0] + own[1]
    rel = (opt.from_seat - caller) % 4  # 3 = 上家, 2 = 対面, 1 = 下家
    if rel == 3:
        return "p" + c + own[0] + own[1]
    if rel == 2:
        return own[0] + "p" + c + own[1]
    return own[0] + own[1] + "p" + c


class Game:
    def __init__(self, rules: Rules, agents: list[Agent], *, seed: int | None = None, names: list[str] | None = None,
                 allow_calls: bool = True, on_event=None):
        self.rules = rules
        self.on_event = on_event or (lambda ev: None)
        self.agents = agents
        self.rng = random.Random(seed)
        self.names = names or [a.name for a in agents]
        self.allow_calls = allow_calls
        self.table = TableState(0, 0, 0, (25000, 25000, 25000, 25000))
        self.log: list[list] = []
        self.history: list[KyokuOutcome] = []

    # --- 1 局 ---------------------------------------------------------------

    def play_kyoku(self) -> KyokuOutcome:
        t = self.table
        dealer = t.dealer
        wall = build_wall(self.rng, self.rules.aka > 0)
        dead, live = wall[-14:], wall[:-14]
        dora_ind, ura_ind = [dead[0]], [dead[1]]
        seats = [SeatState(hand=[]) for _ in range(4)]
        for _ in range(13):
            for i in range(4):
                seats[(dealer + i) % 4].hand.append(live.pop(0))
        haipai = [sorted(to_tenhou_code(x) for x in s.hand) for s in seats]
        draws_rec: list[list] = [[] for _ in range(4)]
        disc_rec: list[list] = [[] for _ in range(4)]
        self._seats, self._scores, self._kyotaku = seats, list(t.scores), t.kyotaku
        self._dora, self._ura = dora_ind, ura_ind
        cur = dealer
        need_draw = True
        forbidden: set[int] = set()
        any_call = False
        self.on_event({"type": "kyoku", "round": t.round_index, "label": round_label(t.round_index, t.honba),
                       "honba": t.honba, "kyotaku": t.kyotaku, "dealer": dealer, "scores": list(t.scores),
                       "dora_indicators": [tile_str(x.kind, x.red) for x in dora_ind]})

        def view(seat: int, drawn: Tile | None, forb: set[int] | None = None) -> View:
            return View(
                seat=seat, table=TableState(t.round_index, t.honba, self._kyotaku, tuple(self._scores)),  # type: ignore[arg-type]
                hand=list(seats[seat].hand), drawn=drawn,
                rivers=[[RiverTile(r.tile, r.tsumogiri, r.riichi, r.called) for r in s.river] for s in seats],
                melds=[[MeldInfo(m.kind, list(m.tiles), m.called, m.from_seat) for m in s.melds] for s in seats],
                riichi=[s.riichi for s in seats], riichi_index=[s.riichi_index for s in seats],
                passed=[set(s.passed) for s in seats], dora_indicators=list(dora_ind), wall_left=len(live),
                rules=self.rules, forbidden=set(forb or ()),
            )

        def finish(kind: str, win: WinInfo | None, tenpai: list[bool] | None, result: list) -> KyokuOutcome:
            deltas = [self._scores[p] - t.scores[p] for p in range(4)]
            rec = [[t.round_index, t.honba, t.kyotaku], list(t.scores), [to_tenhou_code(x) for x in dora_ind],
                   ([to_tenhou_code(x) for x in ura_ind] if win and seats[win.winner].riichi else [])]
            for p in range(4):
                rec += [haipai[p], draws_rec[p], disc_rec[p]]
            rec.append(result)
            return KyokuOutcome(kind, win, tenpai, deltas, rec)

        while True:
            s = seats[cur]
            tile: Tile | None = None
            if need_draw:
                if not live:
                    tenpai = [shanten(counts34(x.hand), len(x.melds)) == 0 for x in seats]
                    pay = draw_payments(tenpai)
                    for p in range(4):
                        self._scores[p] += pay[p]
                    self.on_event({"type": "ryuukyoku", "tenpai": tenpai, "payments": pay, "scores": list(self._scores),
                                   "hands": {p: [tile_str(x.kind, x.red) for x in seats[p].hand] for p in range(4) if tenpai[p]}})
                    return finish("流局", None, tenpai, ["流局", pay])
                tile = live.pop(0)
                s.hand.append(tile)
                s.furiten_temp = False
                draws_rec[cur].append(to_tenhou_code(tile))
                self.on_event({"type": "draw", "seat": cur, "wall": len(live)})
                # ツモ和了
                if shanten(counts34(s.hand), len(s.melds)) == -1:
                    win = self.score_win(cur, None, tile, haitei=not live)
                    if win is not None and self.agents[cur].tsumo(view(cur, tile), win):
                        self._apply(win)
                        return finish("和了", win, None, ["和了", win.payments, [cur, cur, cur, win.label, *win.yaku]])
            # 打牌
            if s.riichi and tile is not None:
                choice, declare = tile, False
            else:
                choice, declare = self.agents[cur].discard(view(cur, tile, forbidden))
                if choice not in s.hand:
                    raise ValueError(f"手牌に無い牌を切ろうとしました: {choice}")
                if choice.kind in forbidden and any(x.kind not in forbidden for x in s.hand):
                    raise ValueError(f"喰い替えになる牌は切れません: {tile_str(choice.kind)}")
                if declare and not self.can_riichi(cur, choice, len(live)):
                    declare = False
            s.hand.remove(choice)
            tsumogiri = tile is not None and choice == tile
            first_discard = not s.river
            s.river.append(RiverTile(choice, tsumogiri, declare))
            code = 60 if tsumogiri else to_tenhou_code(choice)
            disc_rec[cur].append(f"r{code}" if declare else code)
            self.on_event({"type": "discard", "seat": cur, "tile": tile_str(choice.kind, choice.red), "tsumogiri": tsumogiri,
                           "riichi": declare})
            forbidden = set()
            if s.riichi:
                s.ippatsu = False  # 立直後の最初の打牌を過ぎたら一発は消える
            for r in range(4):
                if r != cur and seats[r].riichi:
                    seats[r].passed.add(choice.kind)
            # ロン (下家から順に・上家取り)
            for q in ((cur + 1) % 4, (cur + 2) % 4, (cur + 3) % 4):
                sq = seats[q]
                if shanten(counts34(sq.hand + [choice]), len(sq.melds)) != -1 or self.is_furiten(q):
                    continue
                win = self.score_win(q, cur, choice, houtei=not live)
                if win is None:
                    continue
                if self.agents[q].ron(view(q, None), choice, win):
                    self._apply(win)
                    return finish("和了", win, None, ["和了", win.payments, [q, cur, q, win.label, *win.yaku]])
                if sq.riichi:
                    sq.furiten_riichi = True
                else:
                    sq.furiten_temp = True
            # 立直の成立 (宣言牌が通った)
            if declare:
                self._scores[cur] -= 1000
                self._kyotaku += 1
                s.riichi = True
                s.riichi_index = len(s.river) - 1
                s.ippatsu = True
                s.double_riichi = first_discard and not any_call and all(len(x.river) <= 1 for x in seats)
                self.on_event({"type": "riichi", "seat": cur, "scores": list(self._scores), "kyotaku": self._kyotaku})
            # 鳴き (ポン優先・チーは下家だけ・最後の牌は鳴けない)
            if self.allow_calls and live:
                called = self._offer_calls(cur, choice, view)
                if called is not None:
                    q, opt = called
                    sq = seats[q]
                    for x in opt.tiles:
                        sq.hand.remove(x)
                    sq.melds.append(MeldInfo(opt.kind, [*opt.tiles, choice], called=choice, from_seat=cur))
                    s.river[-1].called = True
                    draws_rec[q].append(_call_string(opt, q))
                    self.on_event({"type": "call", "seat": q, "kind": opt.kind, "from": cur,
                                   "tiles": [tile_str(x.kind, x.red) for x in (*opt.tiles, choice)]})
                    for x in seats:
                        x.ippatsu = False  # 鳴きが入ると一発は消える
                    any_call = True
                    cur, need_draw, forbidden = q, False, opt.forbidden()
                    continue
            cur = (cur + 1) % 4
            need_draw = True

    def _offer_calls(self, cur: int, tile: Tile, view) -> tuple[int, CallOption] | None:
        """打牌 tile に対する鳴きを、ポン (誰でも) → チー (下家) の順に聞く。"""
        k = tile.kind
        pon_opts: dict[int, list[CallOption]] = {}
        for q in ((cur + 1) % 4, (cur + 2) % 4, (cur + 3) % 4):
            sq = self._seats[q]
            if sq.riichi:
                continue
            same = [x for x in sq.hand if x.kind == k]
            if len(same) >= 2:
                plain = sorted(same, key=lambda x: x.red)
                opts = {CallOption("pon", (plain[0], plain[1]), tile, cur)}
                if len(same) >= 3 and any(x.red for x in same):
                    reds = [x for x in same if x.red]
                    opts.add(CallOption("pon", (reds[0], [x for x in same if not x.red][0]), tile, cur))
                pon_opts[q] = sorted(opts, key=lambda o: sum(x.red for x in o.tiles))
        for q, opts in pon_opts.items():
            choice = self.agents[q].call(view(q, None), opts)
            if choice is not None:
                return q, choice
        q = (cur + 1) % 4
        sq = self._seats[q]
        if k < 27 and not sq.riichi:
            n = k % 9
            opts: list[CallOption] = []
            for a, b in ((k - 2, k - 1), (k - 1, k + 1), (k + 1, k + 2)):
                if a < k - n or b > k - n + 8:
                    continue
                ta = [x for x in sq.hand if x.kind == a]
                tb = [x for x in sq.hand if x.kind == b]
                if ta and tb:
                    opts.append(CallOption("chi", (sorted(ta, key=lambda x: x.red)[0], sorted(tb, key=lambda x: x.red)[0]), tile, cur))
            # 鳴いたあと切れる牌が残らない形は除く (喰い替えだけになる)
            ok = []
            for o in opts:
                rest = list(sq.hand)
                for x in o.tiles:
                    rest.remove(x)
                if any(x.kind not in o.forbidden() for x in rest):
                    ok.append(o)
            if ok:
                choice = self.agents[q].call(view(q, None), ok)
                if choice is not None:
                    return q, choice
        return None

    # --- 判定 ---------------------------------------------------------------

    def can_riichi(self, seat: int, discard: Tile, wall_left: int) -> bool:
        s = self._seats[seat]
        if s.riichi or s.melds or wall_left < 4 or self._scores[seat] < 1000:
            return False
        rest = list(s.hand)
        rest.remove(discard)
        return shanten(counts34(rest)) == 0

    def is_furiten(self, seat: int) -> bool:
        s = self._seats[seat]
        if s.furiten_temp or s.furiten_riichi:
            return True
        sh, eff = effective_tiles(counts34(s.hand), len(s.melds))
        if sh != 0:
            return False
        own = {r.tile.kind for r in s.river}
        return any(k in own for k in eff)

    def score_win(self, seat: int, loser: int | None, tile: Tile, *, haitei: bool = False, houtei: bool = False) -> WinInfo | None:
        """和了の点数 (役が無ければ None)。"""
        t = self.table
        s = self._seats[seat]
        used: set[int] = set()
        lib_melds = []
        meld_ids: list[int] = []
        for m in s.melds:
            ids = []
            for x in sorted(m.tiles, key=lambda y: (y.kind, not y.red)):
                tid = _pick_id(x.kind, x.red, used)
                used.add(tid)
                ids.append(tid)
            lib_melds.append(LibMeld(meld_type=LibMeld.CHI if m.kind == "chi" else LibMeld.PON, tiles=ids, opened=True))
            meld_ids += ids
        concealed = list(s.hand) if loser is None else s.hand + [tile]
        ids = []
        win_id = None
        for x in sorted(concealed, key=lambda y: (y.kind, not y.red)):
            tid = _pick_id(x.kind, x.red, used)
            used.add(tid)
            ids.append(tid)
            if win_id is None and x == tile:
                win_id = tid
        assert win_id is not None
        closed = not s.melds
        cfg = HandConfig(
            is_tsumo=loser is None,
            is_riichi=closed and s.riichi and not s.double_riichi,
            is_daburu_riichi=closed and s.double_riichi,
            is_ippatsu=closed and s.riichi and s.ippatsu,
            is_haitei=haitei and loser is None,
            is_houtei=houtei and loser is not None,
            player_wind=_WINDS[(seat - t.dealer) % 4],
            round_wind=_WINDS[min(t.round_index // 4, 3)],
            tsumi_number=t.honba,
            kyoutaku_number=self._kyotaku,
            options=OptionalRules(has_aka_dora=self.rules.aka > 0, has_open_tanyao=self.rules.open_tanyao),
        )
        r = _CALC.estimate_hand_value(
            ids + meld_ids, win_id, melds=lib_melds or None, dora_indicators=[x.kind * 4 for x in self._dora], config=cfg,
            ura_dora_indicators=[x.kind * 4 for x in self._ura] if s.riichi else None,
        )
        if r.error:
            return None
        c = r.cost
        pay = [0, 0, 0, 0]
        if loser is not None:
            amount = c["main"] + c["main_bonus"]
            pay[loser] -= amount
            pay[seat] += amount
            base = c["main"]
        else:
            for p in range(4):
                if p == seat:
                    continue
                amount = (c["main"] + c["main_bonus"]) if (p == t.dealer or seat == t.dealer) else (c["additional"] + c["additional_bonus"])
                pay[p] -= amount
                pay[seat] += amount
            base = c["main"] * 3 if seat == t.dealer else c["main"] + c["additional"] * 2
        pay[seat] += c.get("kyoutaku_bonus", 0)
        level = _LEVELS.get(c.get("yaku_level") or "", "")
        label = f"{level}{base}点" if level else f"{r.fu}符{r.han}飜{base}点"
        return WinInfo(seat, loser, tile, r.han, r.fu, [str(y) for y in r.yaku], pay, label)

    def _apply(self, win: WinInfo) -> None:
        for p in range(4):
            self._scores[p] += win.payments[p]
        self._kyotaku = 0
        s = self._seats[win.winner]
        self.on_event({"type": "win", "seat": win.winner, "from": win.loser, "tile": tile_str(win.tile.kind, win.tile.red),
                       "han": win.han, "fu": win.fu, "label": win.label, "yaku": win.yaku, "payments": win.payments,
                       "scores": list(self._scores), "hand": [tile_str(x.kind, x.red) for x in s.hand],
                       "ura_indicators": [tile_str(x.kind, x.red) for x in self._ura] if s.riichi else []})

    # --- 半荘 ---------------------------------------------------------------

    def play(self, max_kyoku: int = 40) -> list[int]:
        for _ in range(max_kyoku):
            t = self.table
            out = self.play_kyoku()
            self.log.append(out.record)
            self.history.append(out)
            dealer = t.dealer
            dealer_won = out.win is not None and out.win.winner == dealer
            is_draw = out.kind == "流局"
            dealer_cont = dealer_won or (is_draw and bool(out.tenpai and out.tenpai[dealer]))
            nxt, ended = after_kyoku(
                t, self.rules, out.deltas, dealer_continues=dealer_cont, dealer_won=dealer_won,
                is_draw=is_draw, kyotaku_next=self._kyotaku,
            )
            for a in self.agents:
                a.notify({"type": "kyoku_end", "outcome": out, "table": t, "next": nxt, "ended": ended, "names": self.names})
            self.table = nxt
            if ended:
                break
        scores, ranks, pts = self.final()
        self.on_event({"type": "end", "scores": scores, "ranks": [r + 1 for r in ranks], "points": pts})
        return list(self.table.scores)

    def final(self) -> tuple[list[int], list[int], list[float]]:
        scores = list(self.table.scores)
        ranks = final_ranks(scores)
        top = ranks.index(0)
        scores[top] += 1000 * self.table.kyotaku
        pts = [round(points_for(self.rules, ranks[p], scores[p]), 1) for p in range(4)]
        return scores, ranks, pts

    def tenhou_json(self, ref: str = "practice") -> dict:
        scores, _, pts = self.final()
        sc: list = []
        for p in range(4):
            sc += [scores[p], pts[p]]
        return {
            "ver": 2.3, "ref": ref, "log": self.log, "name": self.names,
            "rule": {"disp": "練習南喰赤", "aka": 1 if self.rules.aka else 0}, "sc": sc,
        }
