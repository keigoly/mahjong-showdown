"""助言役の見本: 牌効率のボット (EfficiencyAgent) の判断を、練習卓の助言として返す HTTP サーバー。

    python -m mjsim.advisor --port 8787
    MJ_ADVISOR=http://127.0.0.1:8787/advise node pokemon-showdown start 8000 --no-security

サーバーは練習卓 (/mj play: 人 1 人 + シミュレーターのボット 3 人) の要求だけをここへ送り、答えをその人にだけ見せる。
やり取りの形は sim/PROTOCOL.md の "Advisor"。自分の打ち手を助言役にするときも同じ形で答えればよい。
"""

from __future__ import annotations

import argparse
import json
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Callable

from .agents import EfficiencyAgent
from .efficiency import evaluate_discards
from .engine import CallOption, View
from .rules import get_rules
from .tiles import counts34, parse_tile, tile_str

Advice = dict[str, Any]


def _call_options(request: dict) -> list[CallOption]:
    called = parse_tile(request["tile"])
    return [CallOption(o["kind"], (parse_tile(o["tiles"][0]), parse_tile(o["tiles"][1])), called, request["from"])
            for o in request["options"]]


def efficiency_advice(request: dict, rules_name: str = "tenhou-houou") -> Advice:
    """要求 (サーバーが選手に送るものと同じ JSON) に対する牌効率のボットの判断。"""
    view = View.from_dict(request["state"], get_rules(rules_name))
    agent = EfficiencyAgent("advisor")
    kind = request["type"]
    if kind == "discard":
        tile, riichi = agent.discard(view)
        name = tile_str(tile.kind, tile.red)
        can = set(request.get("can_riichi", []))
        riichi = riichi and (name in can or tile_str(tile.kind) in can)
        evals = [e for e in evaluate_discards(counts34(view.hand), view.unseen(), len(view.my_melds), lookahead_top=0)
                 if e.kind not in view.forbidden]
        cands = [{"choice": f"discard {tile_str(e.kind)}", "label": tile_str(e.kind),
                  "stats": {"shanten": e.shanten, "ukeire": e.ukeire}} for e in evals[:5]]
        best = next((e for e in evals if e.kind == tile.kind), None)
        head = f"打{name}" + (" 立直" if riichi else "")
        if best is not None:
            head += f" (向聴 {best.shanten}・受け入れ {best.ukeire} 枚)"
        folding = bool(evals) and best is not None and any(o.riichi for o in view.opponents()) \
            and (best.shanten, best.ukeire) != (evals[0].shanten, evals[0].ukeire)
        lines = ["他家の立直を受けて、安全な牌を選びました" if folding else "向聴数と受け入れ枚数で選びました (牌効率)"]
        return {"ok": True, "name": "efficiency", "choice": f"discard {name}" + (" riichi" if riichi else ""),
                "headline": head, "candidates": cands, "lines": lines}
    if kind == "call":
        options = _call_options(request)
        pick = agent.call(view, options)
        choice = "pass" if pick is None else f"call {options.index(pick)}"
        head = "見送り" if pick is None else pick.label()
        return {"ok": True, "name": "efficiency", "choice": choice, "headline": head, "candidates": [],
                "lines": ["役牌のポンと、断么九や役のある手が進む鳴きだけを鳴きます"]}
    if kind == "win":
        return {"ok": True, "name": "efficiency", "choice": "win", "headline": f"和了 ({request.get('label', '')})",
                "candidates": [], "lines": []}
    return {"ok": False, "error": f"unknown request type: {kind}"}


def make_handler(advise: Callable[[dict], Advice], name: str) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def _send(self, code: int, body: dict) -> None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self) -> None:  # noqa: N802
            if self.path.rstrip("/") in ("", "/health"):
                self._send(200, {"ok": True, "name": name})
            else:
                self._send(404, {"ok": False, "error": "not found"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path.rstrip("/") != "/advise":
                self._send(404, {"ok": False, "error": "not found"})
                return
            t0 = time.perf_counter()
            try:
                body = json.loads(self.rfile.read(int(self.headers.get("Content-Length") or 0)) or b"{}")
                out = advise(body["request"])
            except Exception as e:  # noqa: BLE001  助言役の不具合で対局を止めない
                out = {"ok": False, "error": f"{type(e).__name__}: {e}"}
            out["ms"] = round((time.perf_counter() - t0) * 1000)
            self._send(200, out)

        def log_message(self, fmt: str, *args: Any) -> None:
            pass

    return Handler


def serve(advise: Callable[[dict], Advice], name: str, host: str = "127.0.0.1", port: int = 8787) -> None:
    server = ThreadingHTTPServer((host, port), make_handler(advise, name))
    print(f"advisor {name}: http://{host}:{port}/advise", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Example advisor for practice tables (the efficiency bot)")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8787)
    ap.add_argument("--rules", default="tenhou-houou")
    a = ap.parse_args(argv)
    serve(lambda req: efficiency_advice(req, a.rules), "efficiency", a.host, a.port)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
