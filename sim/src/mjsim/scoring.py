"""副露の表現と、点数計算ライブラリ (mahjong) に渡す 136 枚 ID の割り当て。"""

from __future__ import annotations

from dataclasses import dataclass

from .tiles import Tile


@dataclass
class MeldInfo:
    kind: str  # chi / pon / minkan / ankan / kakan
    tiles: list[Tile]
    called: Tile | None = None
    from_seat: int | None = None

    @property
    def opened(self) -> bool:
        return self.kind != "ankan"

    @property
    def is_kan(self) -> bool:
        return self.kind in ("minkan", "ankan", "kakan")


def _pick_id(kind: int, red: bool, used: set[int]) -> int:
    """136 枚 ID を 1 つ選ぶ。赤は 16/52/88、それ以外は赤でない ID を優先する。"""
    if red:
        tid = {4: 16, 13: 52, 22: 88}[kind]
        if tid in used:
            raise ValueError("赤 5 が 2 枚あります")
        return tid
    free = [kind * 4 + i for i in range(4) if kind * 4 + i not in used]
    free.sort(key=lambda i: i in (16, 52, 88))
    if not free:
        raise ValueError("同じ牌が 5 枚以上あります")
    return free[0]


