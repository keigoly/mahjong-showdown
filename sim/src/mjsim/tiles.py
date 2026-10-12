"""牌の表現と表記の相互変換。

種類 (kind) は 34 種のインデックス:
    0-8 = 1m-9m / 9-17 = 1p-9p / 18-26 = 1s-9s / 27-33 = 東南西北白發中
赤ドラは種類とは別に red フラグで持つ (5m=4, 5p=13, 5s=22 の赤)。

扱う表記:
    文字列      "123m406p789s東東" / "1122z" (0 = 赤 5)
    天鳳 JSON   11-19 / 21-29 / 31-39 = 数牌、41-47 = 字牌、51-53 = 赤 5m/5p/5s
    mjlog       136 枚 ID (id // 4 = 種類、16 / 52 / 88 = 赤)
"""

from __future__ import annotations

from dataclasses import dataclass

HONORS = "東南西北白發中"
_HONOR_ALIASES = {"発": "發", "ハ": "白"}
SUIT_CHARS = "mps"
RED_KINDS = (4, 13, 22)
YAOCHU = (0, 8, 9, 17, 18, 26, 27, 28, 29, 30, 31, 32, 33)
_RED_136 = {16: 4, 52: 13, 88: 22}


@dataclass(frozen=True, slots=True, order=True)
class Tile:
    kind: int
    red: bool = False

    def __str__(self) -> str:
        return tile_str(self.kind, self.red)


def is_honor(k: int) -> bool:
    return k >= 27


def is_terminal(k: int) -> bool:
    return k < 27 and k % 9 in (0, 8)


def is_yaochu(k: int) -> bool:
    return k >= 27 or k % 9 in (0, 8)


def is_simple(k: int) -> bool:
    return not is_yaochu(k)


def suit_of(k: int) -> int:
    """0=萬子 1=筒子 2=索子 3=字牌。"""
    return k // 9


def number_of(k: int) -> int:
    """数牌の数字 (1-9)。字牌は 1-7 (東=1 … 中=7)。"""
    return k % 9 + 1 if k < 27 else k - 26


def tile_str(k: int, red: bool = False) -> str:
    if k >= 27:
        return HONORS[k - 27]
    return f"{0 if red else k % 9 + 1}{SUIT_CHARS[k // 9]}"


def parse_tiles(text: str) -> list[Tile]:
    """"123m406p789s東東" や "1122z" を牌の並びにする。0 は赤 5。"""
    out: list[Tile] = []
    pending: list[int] = []
    for ch in text.replace(" ", "").replace("　", ""):
        ch = _HONOR_ALIASES.get(ch, ch)
        if ch.isdigit():
            pending.append(int(ch))
        elif ch in SUIT_CHARS:
            base = SUIT_CHARS.index(ch) * 9
            for n in pending:
                out.append(Tile(base + 4, True) if n == 0 else Tile(base + n - 1))
            pending = []
        elif ch == "z":
            for n in pending:
                if not 1 <= n <= 7:
                    raise ValueError(f"字牌は 1z-7z です: {n}z")
                out.append(Tile(27 + n - 1))
            pending = []
        elif ch in HONORS:
            if pending:
                raise ValueError(f"数字の後ろに種類 (m/p/s/z) がありません: {text!r}")
            out.append(Tile(27 + HONORS.index(ch)))
        else:
            raise ValueError(f"読めない文字です: {ch!r} ({text!r})")
    if pending:
        raise ValueError(f"数字の後ろに種類 (m/p/s/z) がありません: {text!r}")
    return out


def parse_tile(text: str) -> Tile:
    tiles = parse_tiles(text)
    if len(tiles) != 1:
        raise ValueError(f"牌 1 枚を指定してください: {text!r}")
    return tiles[0]


def format_tiles(tiles: list[Tile] | list[int]) -> str:
    """種類ごとにまとめて "123m406p東東" の形で出す (並べ替える)。"""
    ts = [t if isinstance(t, Tile) else Tile(t) for t in tiles]
    groups: list[list[str]] = [[], [], []]
    honors: list[str] = []
    for t in sorted(ts, key=lambda x: (x.kind, not x.red)):
        if t.kind >= 27:
            honors.append(HONORS[t.kind - 27])
        else:
            groups[t.kind // 9].append("0" if t.red else str(t.kind % 9 + 1))
    s = "".join("".join(g) + SUIT_CHARS[i] for i, g in enumerate(groups) if g)
    return s + "".join(honors)


def counts34(tiles: list[Tile] | list[int]) -> list[int]:
    c = [0] * 34
    for t in tiles:
        c[t.kind if isinstance(t, Tile) else t] += 1
    return c


def dora_from_indicator(k: int) -> int:
    """ドラ表示牌からドラの種類を出す (9→1、北→東、中→白)。"""
    if k < 27:
        return (k // 9) * 9 + (k % 9 + 1) % 9
    if k < 31:
        return 27 + (k - 27 + 1) % 4
    return 31 + (k - 31 + 1) % 3


# --- 天鳳 JSON の牌コード ---------------------------------------------------


def from_tenhou_code(code: int) -> Tile:
    if code in (51, 52, 53):
        return Tile((code - 51) * 9 + 4, True)
    s, n = divmod(code, 10)
    if s == 4 and 1 <= n <= 7:
        return Tile(27 + n - 1)
    if 1 <= s <= 3 and 1 <= n <= 9:
        return Tile((s - 1) * 9 + n - 1)
    raise ValueError(f"天鳳の牌コードではありません: {code}")


def to_tenhou_code(t: Tile) -> int:
    if t.red:
        return 51 + t.kind // 9
    if t.kind >= 27:
        return 41 + t.kind - 27
    return (t.kind // 9 + 1) * 10 + t.kind % 9 + 1


# --- mjlog の 136 枚 ID -----------------------------------------------------


def from_136(tile_id: int, aka: bool = True) -> Tile:
    k = tile_id // 4
    return Tile(k, aka and tile_id in _RED_136)


def to_136_list(tiles: list[Tile]) -> list[int]:
    """牌の並びを 136 枚 ID に割り当てる (mahjong ライブラリの点数計算用)。赤は 16/52/88。"""
    used: set[int] = set()
    out: list[int] = []
    for t in sorted(tiles, key=lambda x: (x.kind, not x.red)):
        free = [t.kind * 4 + i for i in range(4) if t.kind * 4 + i not in used]
        if t.red:
            tid = {4: 16, 13: 52, 22: 88}[t.kind]
        else:
            # 赤の ID は最後に回す (赤なしルールで 4 枚目の 5 を持つときだけ使う)
            free.sort(key=lambda i: i in _RED_136)
            tid = free[0] if free else -1
        if tid < 0 or tid in used:
            raise ValueError(f"同じ牌が 5 枚以上あります: {tile_str(t.kind, t.red)}")
        used.add(tid)
        out.append(tid)
    return out
