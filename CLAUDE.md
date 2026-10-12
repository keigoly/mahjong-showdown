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
- <この衛星固有の禁止事項(上流への関与禁止・本番ポート・秘密の置き場 など)>

## この衛星固有の指示

<設計書の場所・起動手順・検証の型・罠 など。無ければ削除>
