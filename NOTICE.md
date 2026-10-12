# Notices / 出典

This repository is a mahjong adaptation of two MIT-licensed projects. Their original license texts are kept in
`server/LICENSE` and `env/LICENSE`.

| Directory | Based on | License | Imported at |
|---|---|---|---|
| `server/` | [Pokémon Showdown](https://github.com/smogon/pokemon-showdown) — Copyright (c) 2011-2026 Guangcong Luo and other contributors | MIT | `smogon/pokemon-showdown@942cda7` (2026-10-09) |
| `env/` | [poke-env](https://github.com/hsahovic/poke-env) — Copyright (c) 2019 hsahovic | MIT | `hsahovic/poke-env@7ff6212` (2026-09-18) |

Changes from upstream:

- `server/server/chat-plugins/mahjong.ts` (new): mahjong tables built on Showdown's `RoomGame`, backed by the Python simulator.
- `server/config/config-example.js`: chat throttling is disabled by default (`nothrottle = true`) because the main use is bot self-play.
- `env/`: the Pokémon-specific parts of poke-env (battles, data, team builder, RL environments, tests, docs) were removed.
  The websocket client (`ps_client`) and concurrency helpers were kept and adapted; `player.py`, `baselines.py` and
  `selfplay.py` were rewritten for mahjong.
- `sim/` (new): the mahjong simulator (Python). Hand scoring uses the [`mahjong`](https://github.com/MahjongRepository/mahjong) library (MIT).

Data used for default parameters:

- Deal-in rates by tile class against riichi: Tenhou Houou table 2019 statistics published at
  <https://blog.kobalab.net/entry/2021/01/16/130716>.

Trademarks: Pokémon is a trademark of Nintendo, Creatures Inc. and GAME FREAK inc. This project is not affiliated with
or endorsed by them, by Smogon, or by the authors of poke-env.
