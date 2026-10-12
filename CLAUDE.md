# Mahjong_Showdown — Claude Code への指示

## 母艦連携(必読)

- このディレクトリは母艦 `ai-context-engine` の**衛星** `mahjong-showdown` です。正本は母艦の登録簿 `/Users/Shared/Developments/ai-context-engine/claw_bot/config/projects.json`。
- **Discord**: `#mahjong-showdown`(Clawくん がこの衛星のプロジェクトカードを読んで応答する)。通知 source は `project:mahjong-showdown`。
- **Vault**: `01_Projects/Mahjong_Showdown/_Index.md`(プロジェクトカード)。セッション開始時に注入される。意味のある作業を終えたら「次の一手」を更新し、決定は `Decisions.md` に追記する。進行中タスクの動的状態は AIRFLOW board の `handoff_note`(`AI_Handoff.md` には書かない)。
- **機微クラス**: `public`。
- **連携型**: `none`(org/13 §6.5)。母艦のモジュールを import しない。母艦との境界は無し (登録簿・チャンネル・カードだけの関係)。
- **母艦から借りるもの**: worktree 作成(`ai-context-engine/scripts/mac/new-worktree.sh`)・Air/mini 運用の前提(`ai-context-engine/docs/AIR_MINI_DEVOPS.md`)。それ以外の母艦コードには依存しない。

## 開発フロー

1. 共有ディレクトリなので、**新しいブランチは必ず専用 worktree** で作る(worktree-guard が手順を注入する)。
2. 変更は user CLAUDE.md の Step 1(見える化)→ Step 2(最小改修)→ Step 3(周辺整合)の順。
3. mini がリーダー(org/13 D9)。この衛星は Lane A(Mutagen・`sync-projects.sh` が張る)で mini `/Users/Shared/Developments/mahjong-showdown` に一方向複製される。母艦の rsync や手動コピーに乗せない。mini の Lane A 側は直接編集しない。
4. 作業の終わりに `01_Projects/Mahjong_Showdown/_Index.md` の「現状」「次の一手」を更新する。

## 禁止事項

- 母艦 `ai-context-engine` のコードを import する / 母艦 repo へ直接書き込む(A 型の状態ファイル更新を除く)。
- 衛星のパスを母艦のコードに直書きする(登録簿経由にする)。
- 公開リポジトリなので、秘密・個人の情報・非公開の衛星 (コーチ) の判断のコードを入れない。
- 上流 (Pokémon Showdown・poke-env) への PR や Issue は出さない。上流の LICENSE と NOTICE.md の出典を消さない。
- Pokémon の名前・ロゴを、この製品の名前や宣伝に使わない (NOTICE.md の商標の但し書きを守る)。

## この衛星固有の指示

- 使い方は README.md、やり取りの形式は sim/PROTOCOL.md。上流の取り込み元は NOTICE.md。
- 検証: `cd sim && uv run pytest -q` / サーバーの型検査 `cd server && npx tsc --noEmit -p .` / つなぎの確認は README の Quick start。
- 罠: プラグインを直したら `node build` してからサーバーを再起動する (動いているのは dist/)。Showdown は既定で 1 発言 0.6 秒の制限があり、config の `nothrottle` で外している。天鳳 JSON の大明槓は、打牌欄の 0 が嶺上牌のツモより前にある。
