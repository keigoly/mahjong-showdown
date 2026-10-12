import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from mjsim.advisor import efficiency_advice, make_handler
from mjsim.agents import EfficiencyAgent
from mjsim.engine import Game
from mjsim.rules import get_rules
from mjsim.tiles import tile_str

R = get_rules("tenhou-houou")


def _requests(seed: int = 3) -> list[dict]:
    """1 半荘を打って、席 0 の要求 (サーバーが選手に送るのと同じ形) を集める。"""
    out: list[dict] = []

    class Rec(EfficiencyAgent):
        def discard(self, view):
            out.append({"type": "discard", "state": view.to_dict(), "can_riichi": []})
            return super().discard(view)

        def call(self, view, options):
            opts = [{"kind": o.kind, "tiles": [tile_str(t.kind, t.red) for t in o.tiles], "label": o.label()} for o in options]
            out.append({"type": "call", "state": view.to_dict(), "tile": tile_str(options[0].called.kind, options[0].called.red),
                        "from": options[0].from_seat, "options": opts})
            return super().call(view, options)

    Game(R, [Rec("A")] + [EfficiencyAgent(f"E{i}") for i in range(3)], seed=seed).play()
    return out


def test_advice_is_a_legal_choice():
    reqs = _requests()
    assert any(r["type"] == "call" for r in reqs)
    for r in reqs:
        a = efficiency_advice(r)
        assert a["ok"] and a["headline"]
        if r["type"] == "discard":
            verb, tile = a["choice"].split()[:2]
            st = r["state"]
            assert verb == "discard" and tile in st["hand"] + ([st["drawn"]] if st["drawn"] else [])
            assert tile not in st["forbidden"] or all(t in st["forbidden"] for t in st["hand"])
            assert "riichi" not in a["choice"]  # can_riichi が空なら立直は勧めない
        else:
            assert a["choice"] == "pass" or a["choice"] in [f"call {i}" for i in range(len(r["options"]))]


def test_http_advise_and_errors():
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(efficiency_advice, "efficiency"))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = f"http://127.0.0.1:{server.server_address[1]}"
    try:
        req = next(r for r in _requests() if r["type"] == "discard")

        def post(body: dict) -> dict:
            rq = urllib.request.Request(url + "/advise", data=json.dumps(body).encode(), method="POST",
                                        headers={"Content-Type": "application/json"})
            return json.load(urllib.request.urlopen(rq, timeout=10))

        got = post({"rqid": 1, "request": req})
        assert got["ok"] and got["choice"].startswith("discard ") and got["ms"] >= 0
        bad = post({"rqid": 2, "request": {"type": "discard"}})
        assert bad["ok"] is False and "KeyError" in bad["error"]
        assert json.load(urllib.request.urlopen(url + "/health", timeout=10))["ok"]
    finally:
        server.shutdown()
