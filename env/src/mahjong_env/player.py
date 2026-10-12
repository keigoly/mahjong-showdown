# Derived from poke-env (https://github.com/hsahovic/poke-env, MIT License, Copyright (c) 2019 hsahovic).
# Rewritten for mahjong-showdown: battles -> mahjong tables.
"""mahjong-showdown の卓で打つ選手の土台。

    class MyPlayer(MahjongPlayer):
        def choose(self, request: dict) -> str:
            ...  # "discard 5p" / "discard 5p riichi" / "call 0" / "pass" / "win"

    p = MyPlayer(AccountConfiguration("bot1", None), server_configuration=LocalhostServerConfiguration)
    p.play_tables(10)        # /mj search で 4 人そろうのを待って打つ、を 10 回

request は |request| の JSON。request["type"] は discard / call / win、request["state"] に局面
(手牌・河・副露・立直・点数・ドラ・残り山・喰い替えで切れない牌)。詳しくは sim/PROTOCOL.md。
"""

from __future__ import annotations

import asyncio
import inspect
import json
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from mahjong_env.concurrency import MJ_LOOP, create_in_loop
from mahjong_env.ps_client import AccountConfiguration, LocalhostServerConfiguration, PSClient, ServerConfiguration


@dataclass
class TableResult:
    room: str
    names: List[str]
    scores: List[int]
    ranks: List[int]
    points: List[float]
    seat: Optional[int]
    finished_at: float = field(default_factory=time.time)

    @property
    def rank(self) -> Optional[int]:
        return self.ranks[self.seat] if self.seat is not None and self.ranks else None


class MahjongPlayer:
    """選手の土台。choose() だけ実装すれば卓で打てる。"""

    def __init__(
        self,
        account_configuration: Optional[AccountConfiguration] = None,
        *,
        server_configuration: Optional[ServerConfiguration] = None,
        log_level: Optional[int] = None,
        start_listening: bool = True,
    ):
        if account_configuration is None:
            account_configuration = AccountConfiguration.generate(type(self).__name__, rand=True)
        self.ps_client = PSClient(
            account_configuration,
            server_configuration=server_configuration or LocalhostServerConfiguration,
            log_level=log_level,
            on_battle_message=self._handle_table_message,  # type: ignore[arg-type]
            start_listening=start_listening,
        )
        self.results: List[TableResult] = []
        self.requests_answered = 0
        self.errors: List[str] = []
        self._seat: Dict[str, int] = {}
        self._game_done: asyncio.Event = create_in_loop(asyncio.Event, MJ_LOOP)
        self._busy = False

    # --- 実装するところ ------------------------------------------------------

    def choose(self, request: Dict[str, Any]) -> str:
        """要求に答える文字列を返す (async にしてもよい)。"""
        raise NotImplementedError

    # --- 受信 ----------------------------------------------------------------

    @property
    def username(self) -> str:
        return self.ps_client.username

    async def _handle_table_message(self, split_messages: List[List[str]]) -> None:
        room = split_messages[0][0][1:]
        if not room.startswith("mahjong"):
            return
        for parts in split_messages[1:]:
            if len(parts) < 2:
                continue
            tag = parts[1]
            if tag == "request":
                request = json.loads("|".join(parts[2:]))
                self._seat[room] = request["state"]["seat"]
                await self._answer(room, request)
            elif tag == "mj" and len(parts) > 2 and parts[2] == "gameend":
                result = json.loads("|".join(parts[3:]))
                self._finish(room, result)
            elif tag == "error":
                self.errors.append(f"{room}: {'|'.join(parts[2:])}")
                self.ps_client.logger.warning("%s: %s", room, "|".join(parts[2:]))

    async def _answer(self, room: str, request: Dict[str, Any]) -> None:
        choice = self.choose(request)
        if inspect.isawaitable(choice):
            choice = await choice
        self.requests_answered += 1
        await self.ps_client.send_message(f"/choose {request['rqid']} {choice}", room)

    def _finish(self, room: str, result: Dict[str, Any]) -> None:
        if result.get("ranks"):
            self.results.append(TableResult(room, result.get("names", []), result.get("scores", []),
                                            result.get("ranks", []), result.get("points", []), self._seat.get(room)))
        self._game_done.set()
        asyncio.ensure_future(self.ps_client.send_message(f"/leave {room}"))

    # --- 卓に着く ----------------------------------------------------------------

    async def _play_tables(self, n: int) -> None:
        await self.ps_client.logged_in.wait()
        for _ in range(n):
            self._game_done.clear()
            await self.ps_client.send_message("/mj search")
            await self._game_done.wait()

    def play_tables(self, n: int = 1) -> None:
        """/mj search で卓に着き、終局を待つ、を n 回 (別スレッドのイベントループで動かして待つ)。"""
        asyncio.run_coroutine_threadsafe(self._play_tables(n), MJ_LOOP).result()

    async def play_tables_async(self, n: int = 1) -> None:
        await asyncio.wrap_future(asyncio.run_coroutine_threadsafe(self._play_tables(n), MJ_LOOP))

    def stats(self) -> Dict[str, Any]:
        ranks = [r.rank for r in self.results if r.rank]
        n = len(ranks)
        if not n:
            return {"tables": 0}
        return {
            "tables": n,
            "avg_rank": round(sum(ranks) / n, 4),
            "rank_rates": [round(ranks.count(k) / n, 4) for k in (1, 2, 3, 4)],
            "avg_points": round(sum(r.points[r.seat] for r in self.results if r.seat is not None) / n, 2),
        }
