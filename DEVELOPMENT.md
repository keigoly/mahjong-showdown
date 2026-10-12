# Mahjong_Showdown — DEVELOPMENT.md

## 1. このディレクトリの役割

<この衛星が存在する理由を 1〜3 行で。何を作る / 何を扱う / 誰のためか>

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
| 母艦側アダプタ | `<claw_bot/tasks/... / taskboard/... / scripts/mac/launchd/com.keigoly.mahjong-showdown-*.plist>`(無ければ「—」) |

登録簿とこの表がずれたら登録簿を正とし、この表を直す。

## 3. 現在の問題点

- <既知の問題・未解決の課題。無ければ「なし(YYYY-MM-DD 時点)」>

## 4. バグ修正時の手順(user CLAUDE.md 準拠・一気に直さない)

### Step 1: 調査とログ追加(見える化)
- <どのログ・どの計測で問題の所在を数値で掴むか。requestId / フェーズ名 / 所要 ms / 成否 / エラー内容>
- 結果を確認してから Step 2 へ。

### Step 2: 原因箇所のみ最小限の改修
- <関係ない箇所は触らない。冪等性を意識する>
- 結果を確認してから Step 3 へ。

### Step 3: 周辺の整合性確認と改修
- <母艦側アダプタ・Vault カード・Discord トピック・登録簿の更新が要るか>
- 動作確認が終わるまで旧経路は残す。

## 5. 開発の作法

- 共有ディレクトリのため **新しいブランチは必ず専用 worktree** で(`/Users/Shared/Developments/ai-context-engine/scripts/mac/new-worktree.sh <branch>` を `REPO_ROOT=<この dir>` で呼ぶか、衛星側に同等のスクリプトを置く)。
- 母艦のコードを import しない。連携は org/13 §6.5 の型に限る。
- mini がリーダー(org/13 D9)。この衛星は Lane A(Mutagen・`sync-projects.sh` が張る)で mini `/Users/Shared/Developments/mahjong-showdown` に一方向複製される。母艦の rsync や手動コピーに乗せない。mini の Lane A 側は直接編集しない。

## 6. 関連ドキュメント

- 母艦: `ai-context-engine/org/13-satellite-projects.md`(衛星の契約・連携・機微クラス)
- Vault カード: `01_Projects/Mahjong_Showdown/_Index.md`・決定事項: `01_Projects/Mahjong_Showdown/Decisions.md`
- <この衛星固有の設計書・手順書>
