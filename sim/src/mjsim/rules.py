"""対局ルールと順位点 (サイト・卓ごとのプリセット)。

順位点は「その対局を終えたときに増減する段位ポイント / 成績ポイント」。押し引きの判断は
最終的にこの期待値で比べる (東場の放銃より南場の放銃が重い、を数値で出す土台)。

数値の出典と確度は docs/RULES.md に書く。未確認の値には verified=False を付け、
画面に「未確認」と出す (確認したら True にする)。
"""

from __future__ import annotations

from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Rules:
    key: str
    label: str
    rank_points: tuple[float, float, float, float]  # 1〜4 位の順位点 (ウマ・オカ込み)
    score_weight: float = 0.0  # 終局の持ち点の扱い: (持ち点 - score_base) × score_weight を足す
    score_base: int = 25000
    start_points: int = 25000
    return_points: int = 30000  # 延長 (西入) の基準
    length: str = "hanchan"  # hanchan (東南戦) / tonpuu (東風戦)
    west_round: bool = True  # オーラス終了時に全員が返し点未満なら延長 (サドンデス)
    agari_yame: bool = True  # オーラスの親がトップで和了したら終了できる
    tenpai_yame: bool = False
    tobi: bool = True  # 0 点未満で終了
    aka: int = 3
    open_tanyao: bool = True
    verified: bool = False
    note: str = ""

    @property
    def last_round(self) -> int:
        return 7 if self.length == "hanchan" else 3

    def with_rank_points(self, pts: tuple[float, float, float, float]) -> "Rules":
        return replace(self, rank_points=pts)


# 天鳳: 4 位の減点は段位で決まる (公式マニュアル https://tenhou.net/man/ ・初段〜三段は 2026-10-14 に確認)。
TENHOU_4TH = {1: -45, 2: -60, 3: -75, 4: -90, 5: -105, 6: -120, 7: -135, 8: -150, 9: -165, 10: -180}  # 東南戦 (東風戦は 2/3)
# 卓ごとの 1 位・2 位の加算 (3 位は 0): 東南戦 / 東風戦
TENHOU_TOP = {"houou": ((90, 45), (60, 30)), "tokujou": ((75, 30), (50, 20)), "joukyuu": ((60, 15), (40, 10)),
              "ippan": ((30, 15), (20, 10))}
TENHOU_TABLE = {"houou": "鳳凰卓", "tokujou": "特上卓", "joukyuu": "上級卓", "ippan": "一般卓"}
TENHOU_DEFAULT_DAN = {"houou": 7, "tokujou": 5, "joukyuu": 2, "ippan": 1}
# 雀魂: ウマ (+15/+5/-5/-15) + 部屋の加算 (1・2 位) + (持ち点 - 25000)/1000、4 位は段位の減点 (非公式資料 2 件で一致)
MAJSOUL_ROOM = {"gold": (80, 40), "jade": (110, 55), "throne": (120, 60)}
MAJSOUL_4TH = {
    "雀傑1": 80, "雀傑2": 100, "雀傑3": 120,
    "雀豪1": 165, "雀豪2": 180, "雀豪3": 195,
    "雀聖1": 210, "雀聖2": 225, "雀聖3": 240,
}


def tenhou(table: str = "houou", dan: int = 7, tonpuu: bool = False) -> Rules:
    """天鳳の段位戦 4 人打ち。dan は 1 (初段) 〜 10 (十段)。"""
    top = TENHOU_TOP[table][1 if tonpuu else 0]
    fourth = TENHOU_4TH[dan]
    if tonpuu:
        fourth = round(fourth * 2 / 3)
    name = TENHOU_TABLE[table]
    return Rules(
        key=f"tenhou-{table}" + ("-tonpuu" if tonpuu else ""),
        label=f"天鳳 {name} {'東風戦' if tonpuu else '東南戦'} ({dan}段の 4 位 {fourth})",
        rank_points=(top[0], top[1], 0, fourth),
        length="tonpuu" if tonpuu else "hanchan",
        verified=True,
        note="段位ポイントは順位だけで決まる (持ち点は入らない)",
    )


def majsoul(room: str = "jade", rank: str = "雀豪1", tonpuu: bool = False) -> Rules:
    b1, b2 = MAJSOUL_ROOM[room]
    fourth = MAJSOUL_4TH[rank]
    if tonpuu:
        b1, b2 = {"gold": (40, 20), "jade": (55, 30), "throne": (60, 30)}[room]
        fourth = {"雀傑": (40, 50, 60), "雀豪": (80, 90, 100), "雀聖": (110, 120, 130)}[rank[:2]][int(rank[2]) - 1]
    name = {"gold": "金の間", "jade": "玉の間", "throne": "王座の間"}[room]
    return Rules(
        key=f"majsoul-{room}" + ("-tonpuu" if tonpuu else ""),
        label=f"雀魂 {name} {'東風戦' if tonpuu else '半荘戦'} ({rank})",
        rank_points=(15 + b1, 5 + b2, -5, -15 - fourth),
        score_weight=1 / 1000,
        score_base=25000,
        length="tonpuu" if tonpuu else "hanchan",
        tenpai_yame=True,
        verified=False,
        note="段位ポイント = ウマ + 部屋の加算 + (持ち点 - 25000)/1000 (4 位は段位の減点)。公式画面で未確認",
    )


PRESETS: dict[str, Rules] = {
    "tenhou-houou": tenhou("houou", 7),
    "tenhou-tokujou": tenhou("tokujou", 5),
    "tenhou-joukyuu": tenhou("joukyuu", 2),
    "majsoul-gold": majsoul("gold", "雀傑1"),
    "majsoul-jade": majsoul("jade", "雀豪1"),
    "majsoul-throne": majsoul("throne", "雀聖1"),
    "mleague": Rules(
        key="mleague",
        label="Mリーグ (順位点 +50/+10/-10/-30・30,000 点返し)",
        rank_points=(50, 10, -10, -30),
        score_weight=1 / 1000,
        score_base=30000,
        west_round=False,
        agari_yame=False,
        verified=True,
        note="成績ポイント = (持ち点 - 30000)/1000 + 順位点 (https://m-league.jp/about/)。延長なし",
    ),
    "flat": Rules(
        key="flat",
        label="順位だけ (1 位 +1 / 4 位 -1 の目安)",
        rank_points=(1, 0.33, -0.33, -1),
        verified=True,
    ),
}


def get_rules(key: str) -> Rules:
    """プリセットの名前から。天鳳は段位を「:段」で足せる (例 tenhou-joukyuu:3 = 上級卓 三段・tenhou-joukyuu-tonpuu:1)。"""
    base, _, dan = key.partition(":")
    if base.startswith("tenhou-") and (dan or base.endswith("-tonpuu")):
        table = base.removeprefix("tenhou-").removesuffix("-tonpuu")
        if table in TENHOU_TOP and (not dan or (dan.isdigit() and int(dan) in TENHOU_4TH)):
            return tenhou(table, int(dan) if dan else TENHOU_DEFAULT_DAN[table], tonpuu=base.endswith("-tonpuu"))
    try:
        return PRESETS[key]
    except KeyError:
        raise KeyError(f"ルールのプリセットがありません: {key} (候補: {', '.join(PRESETS)}・天鳳は :段 で段位 1〜10)") from None
