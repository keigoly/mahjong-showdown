import json
import subprocess
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parents[1] / "src"


def test_stream_runs_tables_to_the_end():
    p = subprocess.Popen([sys.executable, "-m", "mjsim.stream"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                         bufsize=1, env={"PYTHONPATH": str(SRC)})

    def send(m):
        p.stdin.write(json.dumps(m) + "\n")
        p.stdin.flush()

    assert json.loads(p.stdout.readline())["type"] == "ready"
    for i in range(2):
        send({"type": "start", "id": f"t{i}", "names": ["A", "B", "C", "D"], "seed": i + 1, "timeout": 10,
              "bots": [None, "efficiency", "efficiency", "efficiency"]})
    ended, requests = 0, 0
    while ended < 2:
        m = json.loads(p.stdout.readline())
        if m["type"] == "request":
            requests += 1
            rq = m["request"]
            st = rq["state"]
            if rq["type"] == "discard":
                ok = [t for t in st["hand"] if t not in st["forbidden"]]
                choice = "discard " + (st["drawn"] if st["drawn"] and st["drawn"] not in st["forbidden"] else ok[0])
            elif rq["type"] == "call":
                choice = "pass"
            else:
                choice = "win"
            send({"type": "choose", "id": m["id"], "player": m["player"], "rqid": m["rqid"], "choice": choice})
        elif m["type"] == "end":
            ended += 1
            assert m["log"] and m["result"]["ranks"]
        elif m["type"] == "error":
            raise AssertionError(m)
    p.stdin.close()
    p.wait(timeout=10)
    assert requests > 50
