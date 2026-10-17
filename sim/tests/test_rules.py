import json
import subprocess
import sys
from pathlib import Path

import pytest

from mjsim.rules import get_rules

SRC = Path(__file__).resolve().parents[1] / "src"


def test_tenhou_presets_keep_their_points():
    assert get_rules("tenhou-houou").rank_points == (90, 45, 0, -135)
    assert get_rules("tenhou-tokujou").rank_points == (75, 30, 0, -105)


def test_tenhou_tables_and_dan():
    assert get_rules("tenhou-joukyuu").rank_points == (60, 15, 0, -60)  # 上級卓 二段
    assert get_rules("tenhou-joukyuu:3").rank_points == (60, 15, 0, -75)
    assert get_rules("tenhou-houou:10").rank_points == (90, 45, 0, -180)
    assert get_rules("tenhou-ippan:1").rank_points == (30, 15, 0, -45)
    tonpuu = get_rules("tenhou-joukyuu-tonpuu:1")
    assert tonpuu.rank_points == (40, 10, 0, -30) and tonpuu.length == "tonpuu"


@pytest.mark.parametrize("key", ["tenhou-joukyuu:11", "tenhou-joukyuu:x", "tenhou-nope:2", "nope"])
def test_unknown_rules_are_refused(key):
    with pytest.raises(KeyError):
        get_rules(key)


def test_table_result_uses_the_table_rules():
    """練習卓の結果の画面の順位点は、卓を始めたときの rules (サーバーの MJ_PRACTICE_RULES) で数える。"""
    p = subprocess.Popen([sys.executable, "-m", "mjsim.stream"], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True,
                         bufsize=1, env={"PYTHONPATH": str(SRC)})
    assert json.loads(p.stdout.readline())["type"] == "ready"
    p.stdin.write(json.dumps({"type": "start", "id": "t1", "names": ["A", "B", "C", "D"], "seed": 7, "timeout": 10,
                              "rules": "tenhou-joukyuu:3", "bots": ["efficiency"] * 4}) + "\n")
    p.stdin.flush()
    while True:
        m = json.loads(p.stdout.readline())
        assert m["type"] != "error", m
        if m["type"] == "end":
            break
    p.stdin.close()
    p.wait(timeout=10)
    ranks, points = m["result"]["ranks"], m["result"]["points"]
    assert [points[ranks.index(r)] for r in (1, 2, 3, 4)] == [60, 15, 0, -75]
