"""手本の選手: シミュレーター (mjsim) の打ち手をそのままサーバー越しに動かす (判断のコードを共有する)。"""

from __future__ import annotations

from typing import Any, Dict

from mjsim.agents import EfficiencyAgent, RandomAgent
from mjsim.engine import CallOption, View
from mjsim.tiles import parse_tile, tile_str

from mahjong_env.player import MahjongPlayer


class SimAgentPlayer(MahjongPlayer):
    """mjsim の Agent (discard / call / tsumo / ron) を包む。make_agent() で中身を決める。"""

    def make_agent(self):
        raise NotImplementedError

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.agent = self.make_agent()

    def choose(self, request: Dict[str, Any]) -> str:
        view = View.from_dict(request["state"])
        kind = request["type"]
        if kind == "discard":
            tile, riichi = self.agent.discard(view)
            name = tile_str(tile.kind, tile.red)
            can = set(request.get("can_riichi", []))
            if riichi and (name in can or tile_str(tile.kind) in can):
                return f"discard {name} riichi"
            return f"discard {name}"
        if kind == "call":
            called = parse_tile(request["tile"])
            options = [CallOption(o["kind"], (parse_tile(o["tiles"][0]), parse_tile(o["tiles"][1])), called, request["from"])
                       for o in request["options"]]
            pick = self.agent.call(view, options)
            return "pass" if pick is None else f"call {options.index(pick)}"
        if kind == "win":
            return "win"
        return "pass"


class RandomPlayer(SimAgentPlayer):
    def make_agent(self):
        return RandomAgent(self.username)


class EfficiencyPlayer(SimAgentPlayer):
    """牌効率どおりに打ち、立直を受けたら遅い手は降りる (設定は EfficiencyAgent と同じ)。"""

    def __init__(self, *args, agent_options: Dict[str, Any] | None = None, **kwargs):
        self.agent_options = agent_options or {}
        super().__init__(*args, **kwargs)

    def make_agent(self):
        return EfficiencyAgent(self.username, **self.agent_options)
