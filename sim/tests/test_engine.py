from mjsim.agents import EfficiencyAgent, RandomAgent
from mjsim.engine import Game, View
from mjsim.rules import get_rules

R = get_rules("tenhou-houou")


def test_games_conserve_points_and_emit_events():
    for seed in (1, 2, 3):
        events = []
        g = Game(R, [EfficiencyAgent(f"E{i}") for i in range(4)], seed=seed, on_event=events.append)
        g.play()
        assert sum(g.table.scores) + 1000 * g.table.kyotaku == 100000
        types = {e["type"] for e in events}
        assert {"kyoku", "draw", "discard", "end"} <= types
        log = g.tenhou_json()
        assert len(log["log"]) == len(g.history) and len(log["sc"]) == 8


def test_view_json_roundtrip():
    class Check(EfficiencyAgent):
        n = 0

        def discard(self, view):
            d = view.to_dict()
            assert View.from_dict(d, view.rules).to_dict() == d
            Check.n += 1
            return super().discard(view)

    Game(R, [Check(f"C{i}") for i in range(4)], seed=9).play()
    assert Check.n > 100


def test_efficiency_beats_random():
    # 同じ山で席を回して、ランダム 1 人 vs 牌効率 3 人
    ranks = []
    for seed in range(1, 6):
        for seat in range(4):
            agents = [RandomAgent("R") if p == seat else EfficiencyAgent(f"E{p}") for p in range(4)]
            g = Game(R, agents, seed=seed)
            g.play()
            ranks.append(g.final()[1][seat] + 1)
    assert sum(ranks) / len(ranks) > 3.2
