# Protocol

## Bots ⇄ server (websocket, Showdown style)

Commands (send from any room unless noted):

| Command | Meaning |
|---|---|
| `/mj search` | Queue for a table. A table starts when 4 players are queued. |
| `/mj cancel` | Leave the queue. |
| `/mj table A, B, C, D [, seed=N] [, timeout=S]` | Start a table with these users. The same `seed` gives the same walls. |
| `/mj play` | Play against 3 simulator bots. |
| `/choose RQID CHOICE` (in the table room) | Answer request `RQID`. Same as `/mj choose`. |
| `/mj autoplay on\|off` (in the table room) | Let the simulator play your seat. |
| `/mj advice on\|off` (in the table room) | Turn the advisor on or off for your seat (practice tables only). |

Table rooms are named `mahjong-…`. Messages in a table room:

- `|request|{json}` — only to the player who must decide.
- `|mj|…` — public events (below).
- `|mj|gameend|{"names":[…],"scores":[…],"ranks":[…],"points":[…]}` — result.
- `|mj|practice|advice` or `|mj|practice|noadvice` — this is a practice table (`/mj play`), with or without an advisor.
- `|mj|advice|{json}` — only to the player: the advisor's answer to the pending request (see [Advisor](#advisor)).
- `|error|text` — your choice was invalid (the request is sent again).

### Requests

Every request has `rqid`, `type` and `state` (everything the player can see). The server adds `practice` (true on
practice tables) and `advice` (true when an advisor's answer will follow as `|mj|advice|`):

```json
{"rqid": 7, "type": "discard", "can_riichi": ["7s"],
 "state": {"seat": 0,
           "table": {"round": 0, "round_label": "東1局", "honba": 0, "kyotaku": 0, "dealer": 0,
                     "scores": [25000, 25000, 25000, 25000], "wall": 61, "dora_indicators": ["3m"]},
           "hand": ["1m", "2m", "0p", "東"], "drawn": "5p",
           "melds": [[], [{"kind": "pon", "tiles": ["白", "白", "白"], "called": "白", "from": 3}], [], []],
           "rivers": [[{"tile": "9m", "tsumogiri": true, "riichi": false, "called": false}], [], [], []],
           "riichi": [false, false, false, false], "riichi_index": [null, null, null, null],
           "passed": [[], [], [], []], "forbidden": []}}
```

Tiles are `1m`…`9m`, `1p`…`9p`, `1s`…`9s`, `0m/0p/0s` (red fives) and `東南西北白發中`.
Seats are absolute (0 = the first dealer). `passed[s]` = tile kinds that passed after seat `s` declared riichi.
`forbidden` = tiles you cannot discard right after a call (kuikae).

| type | extra fields | answer |
|---|---|---|
| `discard` | `can_riichi` (tiles you may discard with riichi) | `discard 5p` / `discard 0p riichi` |
| `call` | `tile`, `from`, `options` (`[{"kind":"pon","tiles":["5p","5p"],"label":"ポン 5p"}]`) | `call 0` / `pass` |
| `win` | `kind` (`tsumo`/`ron`), `tile`, `label`, `yaku`, `han`, `fu`, `payments` | `win` / `pass` |

If a player does not answer within the table timeout, the simulator discards the drawn tile, passes on calls and
accepts wins.

### Public events (`|mj|…`)

```
|mj|init|NAME1,NAME2,NAME3,NAME4|SEED
|mj|kyoku|東1局|ROUND|HONBA|KYOTAKU|pDEALER|SCORES|DORA_INDICATORS
|mj|draw|p1|WALL_LEFT
|mj|discard|p1|5p|tsumogiri|riichi        (tedashi / tsumogiri, optional riichi)
|mj|riichi|p1|SCORES|KYOTAKU               (riichi accepted: the deposit is paid)
|mj|call|p2|pon|5p,5p,5p|p1
|mj|win|p3|p1|5p|満貫8000点|Riichi,...|PAYMENTS|HAND|URA_INDICATORS   (p1 = ron from; tsumo = "tsumo")
|mj|ryuukyoku|1,0,0,1|PAYMENTS
|mj|end|SCORES|RANKS|POINTS
```

## Advisor

On practice tables (one person + three simulator bots, `/mj play`), the server sends each request of that person to
the advisor set by `MJ_ADVISOR` (or `Config.mjadvisor`) and passes the answer on to that person only. Tables with two
or more people never get advice. The person can turn it off with `/mj advice off`.

```
POST {MJ_ADVISOR}            {"rqid": 7, "request": {…the request JSON above…}}
→ 200 {"ok": true, "name": "efficiency", "choice": "discard 5p riichi",
       "headline": "打5p 立直 (向聴 0・受け入れ 8 枚)",
       "candidates": [{"choice": "discard 5p", "label": "5p", "plan": "立直",
                       "stats": {"win": 0.34, "dealin": 0.06, "ev": 12.3, "shanten": 0, "ukeire": 8}}],
       "lines": ["…reasons, one per line…"], "ms": 812}
→ 200 {"ok": false, "error": "…"}
```

`choice` is a valid answer to the request (the client offers it as 「推奨で打つ」). `candidates`, `stats`, `plan` and
`lines` are optional; the client shows `win`/`dealin`/`rentai` (finishing 1st or 2nd)/`last` (finishing 4th)/`top`
(finishing 1st)/`ai` (how likely a learned net is to pick it) as percentages, `ev` with a sign and the others as they are.
The server waits up to `MJ_ADVISOR_TIMEOUT_MS` (default 30000) and drops answers that arrive after the person chose.
`python -m mjsim.advisor` is an example advisor (the efficiency bot). `GET /health` answers `{"ok": true, "name": …}`.

## Bots over HTTP

An empty seat can be played by an outside program instead of the efficiency bot: set `MJ_PRACTICE_BOT=http://…`
(or `Config.mjpracticebot`) on the server, or put the URL in the simulator's `bots` list. For every decision of that
seat the simulator POSTs the same body as to an advisor, plus the table id and the seat, and plays `choice`:

```
POST {MJ_PRACTICE_BOT}       {"rqid": 7, "table": "mahjong-1", "seat": 2, "request": {…the request JSON above…}}
→ 200 {"ok": true, "choice": "discard 5p"}
```

If the answer does not come within 10 seconds, or is not a valid choice, that one decision is played by the efficiency
bot (the first few failures are written to the simulator's stderr). A table with one person and HTTP bots is still a
practice table, so the person gets advice as usual.

## Server ⇄ simulator (`python -m mjsim.stream`, JSON lines on stdin/stdout)

In: `{"type":"start","id":T,"names":[…],"seed":N,"rules":"tenhou-houou","calls":true,"timeout":60,"bots":[null,…]}`,
`{"type":"choose","id":T,"player":S,"rqid":R,"choice":"…"}`, `{"type":"autoplay","id":T,"player":S,"on":true}`,
`{"type":"stop","id":T}`.

Out: `{"type":"update","id":T,"lines":[…]}`, `{"type":"request","id":T,"player":S,"rqid":R,"request":{…}}`,
`{"type":"error","id":T,"player":S,"message":"…"}`, `{"type":"end","id":T,"result":{…},"log":{Tenhou JSON}}`.

One simulator process runs many tables (one thread each). The server runs several processes and assigns new tables to
the least loaded one.
