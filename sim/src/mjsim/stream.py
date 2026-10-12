"""サーバーとのやり取り: 標準入出力の JSON 行で、多数の卓を同時に動かす。

    python -m mjsim.stream

入力 (サーバー → シミュレーター):
    {"type": "start", "id": "t1", "names": ["a","b","c","d"], "seed": 1, "rules": "tenhou-houou",
     "calls": true, "timeout": 60, "bots": [null, null, "efficiency", null]}   # bots の席は内部の打ち手
    {"type": "choose", "id": "t1", "player": 0, "rqid": 5, "choice": "discard 5p riichi"}
    {"type": "autoplay", "id": "t1", "player": 2, "on": true}                  # 切断などで代打ちに任せる
    {"type": "stop", "id": "t1"}
出力 (シミュレーター → サーバー):
    {"type": "update", "id": "t1", "lines": ["|mj|discard|p1|5p|tsumogiri"]}   # 卓の全員に見せる出来事
    {"type": "request", "id": "t1", "player": 0, "rqid": 5, "request": {...}}   # その選手だけに送る
    {"type": "error", "id": "t1", "player": 0, "message": "..."}                 # その選手への誤りの知らせ
    {"type": "end", "id": "t1", "result": {...}, "log": {...}}                   # 終局 (天鳳 JSON 形式の牌譜つき)

選択の書き方: "discard 5p" / "discard 0p riichi" (0 = 赤) / "call 0" (選択肢の番号) / "pass" / "win"。
返事が timeout 秒来なければ、ツモ切り (打牌) か見送り (鳴き) で進め、和了は和了する。
"""

from __future__ import annotations

import json
import queue
import sys
import threading
import traceback

from .agents import EfficiencyAgent, RandomAgent
from .engine import CallOption, Game, QuitGame, View, WinInfo
from .rules import get_rules
from .tiles import Tile, parse_tile, tile_str

_OUT_LOCK = threading.Lock()


def emit(msg: dict) -> None:
    line = json.dumps(msg, ensure_ascii=False)
    with _OUT_LOCK:
        sys.stdout.write(line + "\n")
        sys.stdout.flush()


def _event_lines(ev: dict) -> list[str]:
    t = ev["type"]
    p = lambda s: f"p{s + 1}"  # noqa: E731
    if t == "kyoku":
        return [f"|mj|kyoku|{ev['label']}|{ev['round']}|{ev['honba']}|{ev['kyotaku']}|p{ev['dealer'] + 1}|"
                + ",".join(map(str, ev["scores"])) + "|" + ",".join(ev["dora_indicators"])]
    if t == "draw":
        return [f"|mj|draw|{p(ev['seat'])}|{ev['wall']}"]
    if t == "discard":
        return [f"|mj|discard|{p(ev['seat'])}|{ev['tile']}" + ("|tsumogiri" if ev["tsumogiri"] else "|tedashi")
                + ("|riichi" if ev["riichi"] else "")]
    if t == "riichi":
        return [f"|mj|riichi|{p(ev['seat'])}|" + ",".join(map(str, ev["scores"])) + f"|{ev['kyotaku']}"]
    if t == "call":
        return [f"|mj|call|{p(ev['seat'])}|{ev['kind']}|" + ",".join(ev["tiles"]) + f"|{p(ev['from'])}"]
    if t == "win":
        frm = p(ev["from"]) if ev["from"] is not None else "tsumo"
        return [f"|mj|win|{p(ev['seat'])}|{frm}|{ev['tile']}|{ev['label']}|" + ",".join(ev["yaku"]) + "|"
                + ",".join(map(str, ev["payments"])) + "|" + ",".join(ev["hand"]) + "|" + ",".join(ev["ura_indicators"])]
    if t == "ryuukyoku":
        return ["|mj|ryuukyoku|" + ",".join("1" if x else "0" for x in ev["tenpai"]) + "|" + ",".join(map(str, ev["payments"]))]
    if t == "end":
        return ["|mj|end|" + ",".join(map(str, ev["scores"])) + "|" + ",".join(map(str, ev["ranks"])) + "|"
                + ",".join(map(str, ev["points"]))]
    return []


class RemoteAgent:
    """サーバーの向こうの選手。判断のたびに要求を出し、返事を待つ (来なければ既定の手)。"""

    def __init__(self, table: "Table", seat: int, name: str):
        self.table = table
        self.seat = seat
        self.name = name
        self.inbox: queue.Queue = queue.Queue()
        self.rqid = 0
        self.autoplay = False
        self.fallback = EfficiencyAgent(name)

    def _ask(self, kind: str, view: View, extra: dict, parse):
        if self.autoplay or self.table.stopped:
            return None
        self.rqid += 1
        req = {"type": kind, "rqid": self.rqid, "state": view.to_dict(), **extra}
        emit({"type": "request", "id": self.table.id, "player": self.seat, "rqid": self.rqid, "request": req})
        while True:
            try:
                rqid, choice = self.inbox.get(timeout=self.table.timeout)
            except queue.Empty:
                return None
            if self.table.stopped:
                raise QuitGame()
            if rqid is not None and rqid != self.rqid:
                continue  # 古い要求への返事は捨てる
            try:
                return parse(choice)
            except ValueError as e:
                emit({"type": "error", "id": self.table.id, "player": self.seat, "message": str(e)})
                emit({"type": "request", "id": self.table.id, "player": self.seat, "rqid": self.rqid, "request": req})

    def discard(self, view: View) -> tuple[Tile, bool]:
        can_riichi = sorted({tile_str(t.kind, t.red) for t in view.hand if self.table.game.can_riichi(self.seat, t, view.wall_left)})

        def parse(choice: str):
            parts = choice.split()
            if not parts or parts[0] != "discard" or len(parts) < 2:
                raise ValueError(f"打牌は 'discard <牌> [riichi]' です: {choice!r}")
            want = parse_tile(parts[1])
            cand = [t for t in view.hand if t == want] or [t for t in view.hand if t.kind == want.kind]
            if not cand:
                raise ValueError(f"手牌に {parts[1]} がありません")
            tile = cand[0]
            if tile.kind in view.forbidden and any(t.kind not in view.forbidden for t in view.hand):
                raise ValueError(f"喰い替えになるため {parts[1]} は切れません")
            riichi = len(parts) > 2 and parts[2] == "riichi"
            if riichi and tile_str(tile.kind, tile.red) not in can_riichi and tile_str(tile.kind) not in can_riichi:
                raise ValueError(f"{parts[1]} を切って立直はできません")
            return tile, riichi

        got = self._ask("discard", view, {"can_riichi": can_riichi}, parse)
        if got is None:
            return self.fallback.discard(view) if self.autoplay else ((view.drawn, False) if view.drawn else self.fallback.discard(view))
        return got

    def call(self, view: View, options: list[CallOption]) -> CallOption | None:
        opts = [{"kind": o.kind, "tiles": [tile_str(t.kind, t.red) for t in o.tiles], "label": o.label()} for o in options]

        def parse(choice: str):
            parts = choice.split()
            if parts == ["pass"]:
                return "pass"
            if len(parts) == 2 and parts[0] == "call" and parts[1].isdigit() and int(parts[1]) < len(options):
                return options[int(parts[1])]
            raise ValueError(f"鳴きは 'call <番号>' か 'pass' です: {choice!r}")

        called = options[0].called
        got = self._ask("call", view, {"tile": tile_str(called.kind, called.red), "from": options[0].from_seat, "options": opts}, parse)
        if got is None:
            return self.fallback.call(view, options) if self.autoplay else None
        return None if got == "pass" else got

    def _win(self, kind: str, view: View, win: WinInfo) -> bool:
        def parse(choice: str):
            if choice.strip() in ("win", "pass"):
                return choice.strip() == "win"
            raise ValueError(f"和了は 'win' か 'pass' です: {choice!r}")

        got = self._ask("win", view, {"kind": kind, "tile": tile_str(win.tile.kind, win.tile.red), "label": win.label,
                                      "yaku": win.yaku, "han": win.han, "fu": win.fu, "payments": win.payments}, parse)
        return True if got is None else got

    def tsumo(self, view: View, win: WinInfo) -> bool:
        return self._win("tsumo", view, win)

    def ron(self, view: View, tile: Tile, win: WinInfo) -> bool:
        return self._win("ron", view, win)

    def notify(self, event: dict) -> None:
        pass


class Table:
    def __init__(self, msg: dict):
        self.id = msg["id"]
        self.timeout = float(msg.get("timeout", 60))
        self.stopped = False
        names = msg.get("names") or [f"P{i + 1}" for i in range(4)]
        bots = msg.get("bots") or [None] * 4
        self.agents = []
        for seat in range(4):
            if bots[seat] == "random":
                self.agents.append(RandomAgent(names[seat], seed=msg.get("seed")))
            elif bots[seat]:
                self.agents.append(EfficiencyAgent(names[seat]))
            else:
                self.agents.append(RemoteAgent(self, seat, names[seat]))
        self.game = Game(get_rules(msg.get("rules", "tenhou-houou")), self.agents, seed=msg.get("seed"), names=names,
                         allow_calls=bool(msg.get("calls", True)), on_event=self._on_event)
        self.thread = threading.Thread(target=self._run, name=f"table-{self.id}", daemon=True)

    def _on_event(self, ev: dict) -> None:
        lines = _event_lines(ev)
        if lines:
            emit({"type": "update", "id": self.id, "lines": lines})

    def _run(self) -> None:
        try:
            self.game.play()
            scores, ranks, pts = self.game.final()
            emit({"type": "end", "id": self.id, "result": {"names": self.game.names, "scores": scores,
                                                           "ranks": [r + 1 for r in ranks], "points": pts},
                  "log": self.game.tenhou_json(ref=self.id)})
        except QuitGame:
            emit({"type": "end", "id": self.id, "result": {"stopped": True}, "log": None})
        except Exception as e:  # noqa: BLE001 — 卓 1 つの失敗でシミュレーター全体を止めない
            emit({"type": "error", "id": self.id, "player": None, "message": f"{type(e).__name__}: {e}",
                  "trace": traceback.format_exc()[-2000:]})
            emit({"type": "end", "id": self.id, "result": {"crashed": True}, "log": None})
        finally:
            TABLES.pop(self.id, None)


TABLES: dict[str, Table] = {}


def handle(msg: dict) -> None:
    t = msg.get("type")
    tid = msg.get("id")
    if t == "start":
        table = Table(msg)
        TABLES[tid] = table
        table.thread.start()
        return
    table = TABLES.get(tid)
    if table is None:
        emit({"type": "error", "id": tid, "player": msg.get("player"), "message": "その卓はありません"})
        return
    if t == "choose":
        agent = table.agents[msg["player"]]
        if isinstance(agent, RemoteAgent):
            agent.inbox.put((msg.get("rqid"), str(msg.get("choice", ""))))
    elif t == "autoplay":
        agent = table.agents[msg["player"]]
        if isinstance(agent, RemoteAgent):
            agent.autoplay = bool(msg.get("on", True))
            agent.inbox.put((None, ""))  # 待っている要求を起こす
    elif t == "stop":
        table.stopped = True
        for a in table.agents:
            if isinstance(a, RemoteAgent):
                a.inbox.put((None, ""))


def main() -> int:
    emit({"type": "ready", "version": 1})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            handle(json.loads(line))
        except Exception as e:  # noqa: BLE001
            emit({"type": "error", "id": None, "player": None, "message": f"{type(e).__name__}: {e}"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
