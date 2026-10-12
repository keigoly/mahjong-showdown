# Mahjong_Showdown — DEVELOPMENT.md

## 1. このディレクトリの役割

Pokémon Showdown (サーバー) と poke-env (ボット用の Python ライブラリ) を麻雀 (日本のリーチ麻雀・四人打ち) 用に改造した、
AI 同士の大規模な自己対戦の場 (公開)。打ち方の比較 (複製対局) と、AI を鍛えるための対局の量産に使う。
構成は `server/` (Showdown + 麻雀プラグイン)・`sim/` (Python のシミュレーター mjsim)・`env/` (ボット用ライブラリ mahjong_env)。
使い方は [README.md](README.md)、やり取りの形式は [sim/PROTOCOL.md](sim/PROTOCOL.md)、上流と出典は [NOTICE.md](NOTICE.md)。

## 2. 母艦連携(写し。正本は母艦の登録簿 `claw_bot/config/projects.json`)

| 項目 | 値 |
|---|---|
| slug | `mahjong-showdown` |
| owner | 登録簿参照 (非公開) |
| class | `public` |
| runtime | `none`(常駐が動く場所。既定 mini) |
| sync | `mutagen`(mini への実在の担保。既定 mutagen・runtime: mini は git) |
| link(連携型) | `none`(org/13 §6.5) |
| Discord | `#mahjong-showdown` |
| Vault カード | `01_Projects/Mahjong_Showdown/_Index.md` |
| data_dir(work のみ) | `—`(非 git・Vault と Discord に出さない) |
| 母艦側アダプタ | — |

登録簿とこの表がずれたら登録簿を正とし、この表を直す。

## 3. 現在の問題点

- カン・途中流局・ダブロン・流し満貫は未対応 (2026-10-13 時点)。
- `server/` には Pokémon 用のデータとシミュレーターが残っている (サーバーの起動に要るため)。麻雀には使わない。
- Python の選手は 1 プロセス 1 コアなので、重い打ち手 (順位の見込みを毎手計算する打ち手など) は選手側のプロセスを増やして並列にする (`selfplay --workers`)。

## 4. バグ修正時の手順(user CLAUDE.md 準拠・一気に直さない)

### Step 1: 調査とログ追加(見える化)
- サーバーのログ (`node pokemon-showdown start …` の標準出力・`[mjsim N]` の行) と、卓ごとの牌譜 `server/logs/mahjong/<月>/<卓>.json` で、どの卓のどの局で止まったかを特定する。
- シミュレーター単体は `cd sim && uv run pytest -q` (半荘の完走・点数の保存・JSON の往復・やり取り越しの完走)。
- 速さは `selfplay` の `hanchan_per_hour`。
- 結果を確認してから Step 2 へ。

### Step 2: 原因箇所のみ最小限の改修
- 規則の不具合は `sim/src/mjsim/engine.py` だけを直し、テストに再現する局面を足す。プラグインはやり取りだけで、規則を持たない。
- 結果を確認してから Step 3 へ。

### Step 3: 周辺の整合性確認と改修
- やり取りの形式を変えたら `sim/PROTOCOL.md`・`env/src/mahjong_env`・`server/server/chat-plugins/mahjong.ts` を同じ変更で直す。Vault カードの「現状」を更新する。
- 動作確認が終わるまで旧経路は残す。

## 5. 開発の作法

- 共有ディレクトリのため **新しいブランチは必ず専用 worktree** で(`/Users/Shared/Developments/ai-context-engine/scripts/mac/new-worktree.sh <branch>` を `REPO_ROOT=<この dir>` で呼ぶか、衛星側に同等のスクリプトを置く)。
- 母艦のコードを import しない。連携は org/13 §6.5 の型に限る。
- mini がリーダー(org/13 D9)。この衛星は Lane A(Mutagen・`sync-projects.sh` が張る)で mini `/Users/Shared/Developments/mahjong-showdown` に一方向複製される。母艦の rsync や手動コピーに乗せない。mini の Lane A 側は直接編集しない。

## 6. 関連ドキュメント

- 母艦: `ai-context-engine/org/13-satellite-projects.md`(衛星の契約・連携・機微クラス)
- Vault カード: `01_Projects/Mahjong_Showdown/_Index.md`・決定事項: `01_Projects/Mahjong_Showdown/Decisions.md`
- [README.md](README.md) / [sim/PROTOCOL.md](sim/PROTOCOL.md) / [NOTICE.md](NOTICE.md)
