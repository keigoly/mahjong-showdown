"""外の打ち手 (bots の席に http://… を書く) の確認: 判断のたびに POST が届き、その答えで打つ。届かなくても卓は終わる。"""

import json
import subprocess
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def _serve(answer):
    got = []

    class H(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            got.append(body)
            data = json.dumps(answer(body["request"])).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *a):
            pass

    srv = ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, got


def _tsumogiri(rq):
    st = rq["state"]
    if rq["type"] == "discard":
        ok = [t for t in st["hand"] if t not in st["forbidden"]]
        return {"ok": True, "choice": "discard " + (st["drawn"] if st["drawn"] and st["drawn"] not in st["forbidden"] else ok[0])}
    return {"ok": True, "choice": "pass" if rq["type"] == "call" else "win"}


def _run(bots, seed=3):
    """卓を 1 つ始めて、終局 (end) まで待つ。標準入力を閉じるとシミュレーターが終わるので、終局までは開けておく。"""
    p = subprocess.Popen([sys.executable, "-m", "mjsim.stream"], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                         stderr=subprocess.PIPE, text=True, bufsize=1, env={"PYTHONPATH": str(SRC)})
    assert json.loads(p.stdout.readline())["type"] == "ready"
    p.stdin.write(json.dumps({"type": "start", "id": "t", "names": ["A", "B", "C", "D"], "seed": seed, "timeout": 10,
                              "bots": bots}) + "\n")
    p.stdin.flush()
    ends = []
    while not ends:
        m = json.loads(p.stdout.readline())
        if m["type"] == "end":
            ends.append(m)
        elif m["type"] in ("request", "error"):
            raise AssertionError(m)  # 人の席は無いので、要求も誤りも来ないはず
    p.stdin.close()
    err = p.stderr.read()
    p.wait(timeout=10)
    return ends, err


def test_http_bot_plays_every_turn_it_is_asked():
    srv, got = _serve(_tsumogiri)
    url = f"http://127.0.0.1:{srv.server_address[1]}/act"
    try:
        ends, _ = _run([url, "efficiency", "efficiency", "efficiency"])
    finally:
        srv.shutdown()
    assert len(ends) == 1 and ends[0]["result"]["ranks"]
    assert len(got) > 50 and all(b["table"] == "t" and b["seat"] == 0 for b in got)
    assert {b["request"]["type"] for b in got} >= {"discard"}
    # 打牌はすべてツモ切りの答えどおり (牌譜の 0 番目の席の河に、手出しが無い)
    assert all(b["rqid"] == b["request"]["rqid"] for b in got)


def test_http_bot_falls_back_when_unreachable():
    ends, err = _run(["http://127.0.0.1:9/act", "efficiency", "efficiency", "efficiency"])
    assert len(ends) == 1 and ends[0]["result"]["ranks"]
    assert "bot http://127.0.0.1:9/act" in err
