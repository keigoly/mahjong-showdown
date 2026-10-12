# mahjong-showdown

A Japanese riichi mahjong (4-player) server for bots and AI self-play, adapted from
[Pokémon Showdown](https://github.com/smogon/pokemon-showdown) and [poke-env](https://github.com/hsahovic/poke-env).

- `server/` — Showdown game server with a mahjong plugin (tables, matchmaking, requests/choices, replays as Tenhou JSON)
- `sim/` — the mahjong simulator (Python, `mjsim`): wall, calls (chi/pon), riichi, furiten, scoring, game end rules
- `env/` — Python library for writing bots (`mahjong_env`, derived from poke-env): connect, play tables, self-play, evaluate

日本語の説明は下にあります。

## Quick start

```bash
# simulator (Python 3.11+, uv)
cd sim && uv sync && cd ..

# server (Node.js 20+)
cd server && npm install && node pokemon-showdown start 8000 --no-security
#   MJSIM_PROCESSES=6 to run several simulator processes (default: CPU count - 2, max 8)

# bots (another terminal)
cd env && uv sync
uv run python -m mahjong_env.selfplay duplicate --challenger random --baseline efficiency --sets 8
```

`duplicate` plays one challenger against three baselines on the same walls, rotating the challenger through the four
seats, so luck cancels out and only the difference in play shows in the average rank (2.5 = equal strength).

Your own bot classes can play too: `--challenger "py:mybots.nn:NetPlayer?model=/models/v2.onnx;temperature=0.5"`
(everything after `?` is passed to the class as keyword arguments, so two versions of one bot can share a table).

For long self-play runs, start the server with `MJ_LOG_EVERY=50` to keep one table log in 50
(logs go to `server/logs/mahjong/<YYYY-MM>/`, about 8 KB each; `0` keeps none).

## Play in the browser (practice tables with advice)

The server also serves a table client: open `http://localhost:8000/` and press 「練習対局を始める」 to play against
three simulator bots (`/mj play`). It works on phones and tablets too (the hand stays at the bottom of the screen).

On practice tables (one person + three simulator bots) the server can ask an **advisor** for each of your decisions and
show its answer only to you. Start an advisor and tell the server where it is:

```bash
cd sim && uv run python -m mjsim.advisor --port 8787          # example advisor: the efficiency bot
cd server && MJ_ADVISOR=http://127.0.0.1:8787/advise node pokemon-showdown start 8000 --no-security
```

Tables with two or more people never get advice. Any program that answers the advisor protocol
([sim/PROTOCOL.md](sim/PROTOCOL.md#advisor)) can be the advisor, so you can practice with your own AI's opinion.

## Writing a bot

```python
from mahjong_env import MahjongPlayer, AccountConfiguration, LocalhostServerConfiguration

class MyBot(MahjongPlayer):
    def choose(self, request):
        state = request["state"]          # hand, rivers, melds, riichi, scores, dora, wall, ...
        if request["type"] == "discard":
            return f"discard {state['drawn'] or state['hand'][-1]}"
        if request["type"] == "call":
            return "pass"
        return "win"

MyBot(AccountConfiguration("mybot", None), server_configuration=LocalhostServerConfiguration).play_tables(5)
```

The message format is described in [sim/PROTOCOL.md](sim/PROTOCOL.md).

## Status

- Rules: 4-player, East-South game, red fives, chi/pon (no kan yet), riichi/ippatsu/double riichi/haitei/houtei,
  furiten (own discards, temporary, after riichi), honba/riichi sticks, West-round extension, dealer stop, bust.
- No abortive draws, no double ron (head bump), no nagashi mangan yet.
- Throughput on a 10-core laptop: about 10,000 half-games per hour (6 simulator processes, 3 bot processes).

## License

MIT. See [NOTICE.md](NOTICE.md) for the upstream projects, their licenses and the trademark notice.

---

## 日本語

Pokémon Showdown と poke-env を、日本のリーチ麻雀 (四人打ち) 用に改造した対局サーバーとボット用ライブラリです。
AI 同士の大量の自己対戦で、打ち方を比べたり鍛えたりするために作っています。

- `server/` — Showdown のサーバー + 麻雀プラグイン (卓・待ち合わせ・要求と選択・天鳳 JSON 形式の牌譜の保存)
- `sim/` — 麻雀のシミュレーター (Python・`mjsim`): 山・チー/ポン・立直・フリテン・点数計算・終局の規則
- `env/` — ボットを書くための Python ライブラリ (`mahjong_env`・poke-env 由来): 接続・卓に着く・自己対戦・評価

`duplicate` (複製対局) は、挑戦者 1 体と基準 3 体を同じ山で席を 4 通りに入れ替えて打たせます。
配牌・ツモの運が打ち消され、打ち方の差だけが平均順位に出ます (同じ強さなら 2.5)。
自作のボットは `py:モジュール:クラス?名前=値;名前=値` で指定できます (? の後ろはクラスの引数)。
大量の自己対戦では `MJ_LOG_EVERY=50` でサーバーを起動すると、牌譜を 50 卓に 1 つだけ残します。

### ブラウザで打つ (練習卓と助言)

サーバーは対局画面も配ります。`http://localhost:8000/` を開いて「練習対局を始める」を押すと、シミュレーターのボット
3 人と打てます (`/mj play`)。スマートフォンやタブレットでも使えます (手牌は画面の下に固定)。

練習卓 (人 1 人 + シミュレーターのボット 3 人) では、サーバーが判断のたびに **助言役** へ問い合わせ、その答えを本人に
だけ見せます。助言役を起動し、サーバーに `MJ_ADVISOR` で場所を教えてください
(見本は `python -m mjsim.advisor`・牌効率のボット)。人が 2 人以上いる卓には助言を出しません。
助言役のやり取りの形 ([sim/PROTOCOL.md](sim/PROTOCOL.md#advisor)) で答えるプログラムなら何でも助言役にできます。
