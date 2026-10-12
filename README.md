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
