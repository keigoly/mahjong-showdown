"""自己対戦: たくさんの選手を同じサーバーにつなぎ、卓を並行して回して成績と「何年分打ったか」を積み上げる。

    python -m mahjong_env.selfplay search --players efficiency:12,random:4 --tables 25
    python -m mahjong_env.selfplay duplicate --challenger random --baseline efficiency --sets 50 --groups 4

search    : 選手は /mj search で 4 人そろった順に卓に着く (同じ種類同士が集まりやすいので、比較には向かない)
duplicate : 挑戦者 1 体 + 基準 3 体を 1 組にし、同じ山 (seed) で挑戦者の席を 4 通りに変えた 4 卓を同時に打つ。
            配牌・ツモの運が打ち消され、打ち方の差だけが平均順位に出る (基準と同じ強さなら 2.5)。
1 年 = 1,825 半荘 (人が 1 日 5 半荘打つとして) で数え、台帳 (既定 ./data/selfplay_ledger.json) に半荘数を足していく。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from pathlib import Path
from typing import Dict, List

from mahjong_env.baselines import EfficiencyPlayer, RandomPlayer
from mahjong_env.concurrency import MJ_LOOP
from mahjong_env.player import MahjongPlayer
from mahjong_env.ps_client import AccountConfiguration, ServerConfiguration

HANCHAN_PER_YEAR = 365 * 5
KINDS = {"efficiency": EfficiencyPlayer, "random": RandomPlayer}


def make_players(spec: str, server: ServerConfiguration) -> List[MahjongPlayer]:
    players: List[MahjongPlayer] = []
    for part in spec.split(","):
        name, _, count = part.partition(":")
        cls = KINDS[name.strip()]
        for _ in range(int(count or 1)):
            players.append(cls(AccountConfiguration.generate(name.strip()[:10], rand=True), server_configuration=server))
    return players


async def _run(players: List[MahjongPlayer], tables: int) -> None:
    for p in players:
        await p.ps_client.logged_in.wait()
    await asyncio.gather(*(p._play_tables(tables) for p in players))


def run(players: List[MahjongPlayer], tables: int) -> Dict:
    t0 = time.perf_counter()
    asyncio.run_coroutine_threadsafe(_run(players, tables), MJ_LOOP).result()
    seconds = time.perf_counter() - t0
    by_kind: Dict[str, List[int]] = {}
    rooms = set()
    for p in players:
        kind = type(p).__name__
        for r in p.results:
            rooms.add(r.room)
            if r.rank:
                by_kind.setdefault(kind, []).append(r.rank)
    summary = {
        "hanchan": len(rooms), "seconds": round(seconds, 1),
        "hanchan_per_hour": round(len(rooms) / seconds * 3600) if seconds else None,
        "by_kind": {k: {"n": len(v), "avg_rank": round(sum(v) / len(v), 3),
                        "rank_rates": [round(v.count(i) / len(v), 3) for i in (1, 2, 3, 4)]} for k, v in by_kind.items()},
        "errors": sum(len(p.errors) for p in players),
    }
    return summary


def _make(kind: str, server: ServerConfiguration) -> MahjongPlayer:
    if kind.startswith("py:"):
        # 外の選手クラス: "py:パッケージ.モジュール:クラス" (例 py:mjcoach.online:CoachPlayer)
        import importlib

        module, _, cls_name = kind[3:].rpartition(":")
        cls = getattr(importlib.import_module(module), cls_name)
        return cls(AccountConfiguration.generate(cls_name[:10], rand=True), server_configuration=server)
    name, _, opts = kind.partition(":")
    cls = KINDS[name]
    if cls is EfficiencyPlayer and opts:
        kw = {k: (v.lower() == "true") if v.lower() in ("true", "false") else int(v)
              for k, v in (item.split("=") for item in opts.split(";"))}
        return EfficiencyPlayer(AccountConfiguration.generate(name[:10], rand=True), server_configuration=server, agent_options=kw)
    return cls(AccountConfiguration.generate(name[:10], rand=True), server_configuration=server)


async def _duplicate(challenger: str, baseline: str, sets: int, groups: int, seed0: int, server: ServerConfiguration):
    teams = [(_make(challenger, server), [_make(baseline, server) for _ in range(3)]) for _ in range(groups)]
    for ch, bs in teams:
        for p in [ch, *bs]:
            await p.ps_client.logged_in.wait()

    async def run_group(g: int) -> None:
        ch, bs = teams[g]
        for i in range(g, sets, groups):
            seed = seed0 + i
            target = len(ch.results) + 4
            for k in range(4):
                order = list(bs)
                order.insert(k, ch)  # 挑戦者の席を 0〜3 に回す
                names = ", ".join(p.username for p in order)
                await ch.ps_client.send_message(f"/mj table {names}, seed={seed}")
            while len(ch.results) < target:
                await asyncio.sleep(0.05)

    await asyncio.gather(*(run_group(g) for g in range(groups)))
    return teams


def duplicate(challenger: str, baseline: str, sets: int, groups: int, server: ServerConfiguration, seed0: int = 1) -> Dict:
    t0 = time.perf_counter()
    teams = asyncio.run_coroutine_threadsafe(_duplicate(challenger, baseline, sets, groups, seed0, server), MJ_LOOP).result()
    seconds = time.perf_counter() - t0
    # 組ごとに「同じ山の 4 卓」が終わってから次の山に進むので、挑戦者の結果は 4 件ずつ同じ山のまとまりになる
    ranks = [r.rank for ch, _ in teams for r in ch.results if r.rank]
    return _summarize(challenger, baseline, ranks, seconds, sum(len(p.errors) for ch, bs in teams for p in [ch, *bs]))


def _summarize(challenger: str, baseline: str, ranks: List[int], seconds: float, errors: int) -> Dict:
    import math

    chunks = [ranks[i:i + 4] for i in range(0, len(ranks) - len(ranks) % 4, 4)]
    means = [sum(c) / len(c) for c in chunks if c]
    n = len(ranks)
    avg = sum(ranks) / n if n else 0.0
    m = sum(means) / len(means) if means else 0.0
    se = math.sqrt(sum((x - m) ** 2 for x in means) / max(1, len(means) - 1) / max(1, len(means))) if means else 0.0
    return {
        "challenger": challenger, "baseline": baseline, "hanchan": n, "sets": len(means), "seconds": round(seconds, 1),
        "hanchan_per_hour": round(n / seconds * 3600) if seconds else None,
        "avg_rank": round(avg, 4), "ci95": round(1.96 * se, 4),
        "rank_rates": [round(ranks.count(k) / n, 4) for k in (1, 2, 3, 4)] if n else [],
        "errors": errors, "ranks": ranks,
    }


def _worker(args) -> Dict:
    challenger, baseline, sets, groups, server_url, seed0 = args
    return duplicate(challenger, baseline, sets, groups, ServerConfiguration(server_url, ""), seed0)


def duplicate_parallel(challenger: str, baseline: str, sets: int, groups: int, server: ServerConfiguration,
                       workers: int, seed0: int = 1) -> Dict:
    """複数のプロセスで複製対局を回す (Python の選手は 1 プロセス 1 コアのため)。山の範囲はプロセスごとに分ける。"""
    import multiprocessing as mp

    if workers <= 1:
        return duplicate(challenger, baseline, sets, groups, server, seed0)
    per = [sets // workers + (1 if i < sets % workers else 0) for i in range(workers)]
    jobs = [(challenger, baseline, per[i], groups, server.websocket_url, seed0 + i * 1_000_000) for i in range(workers) if per[i]]
    t0 = time.perf_counter()
    with mp.get_context("spawn").Pool(len(jobs)) as pool:
        parts = pool.map(_worker, jobs)
    ranks = [r for part in parts for r in part["ranks"]]
    return _summarize(challenger, baseline, ranks, time.perf_counter() - t0, sum(p["errors"] for p in parts))


def add_to_ledger(path: Path, hanchan: int) -> Dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    ledger = json.loads(path.read_text()) if path.exists() else {"hanchan": 0}
    ledger["hanchan"] += hanchan
    ledger["years"] = round(ledger["hanchan"] / HANCHAN_PER_YEAR, 3)
    ledger["updated"] = time.strftime("%Y-%m-%dT%H:%M:%S")
    path.write_text(json.dumps(ledger, ensure_ascii=False, indent=1) + "\n")
    return ledger


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="mahjong-showdown の自己対戦")
    ap.add_argument("mode", choices=("search", "duplicate"))
    ap.add_argument("--server", default="ws://localhost:8000/showdown/websocket")
    ap.add_argument("--players", default="efficiency:8", help='search: 種類:人数 をカンマで (例 "efficiency:12,random:4")')
    ap.add_argument("--tables", type=int, default=5, help="search: 1 人あたりの半荘数")
    ap.add_argument("--challenger", default="random", help='duplicate: 挑戦者 (例 "efficiency:fold_late_wall=24")')
    ap.add_argument("--baseline", default="efficiency")
    ap.add_argument("--sets", type=int, default=10, help="duplicate: セット数 (1 セット = 同じ山で 4 半荘)")
    ap.add_argument("--groups", type=int, default=4, help="duplicate: 並行して回す組の数")
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--workers", type=int, default=1, help="duplicate: 選手側のプロセス数")
    ap.add_argument("--ledger", default="data/selfplay_ledger.json")
    a = ap.parse_args(argv)
    server = ServerConfiguration(a.server, "")
    if a.mode == "search":
        players = make_players(a.players, server)
        if len(players) % 4:
            raise SystemExit("選手の数は 4 の倍数にしてください")
        summary = run(players, a.tables)
    else:
        summary = duplicate_parallel(a.challenger, a.baseline, a.sets, a.groups, server, a.workers, a.seed)
    ledger = add_to_ledger(Path(a.ledger), summary["hanchan"])
    summary.pop("ranks", None)
    print(json.dumps({"summary": summary, "ledger": ledger}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
