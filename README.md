# veile-bot

> 毎朝、AI エージェント / LLM / 開発自動化まわりの新着を集めて要約し、LINE に届けるボット。

GitHub Trending・Hugging Face・note の RSS から候補を集め、興味プロファイルで採点し、
Claude に日本語で要約させて Flex Message で配信する。ソースが 1 つ落ちても、
LLM が使えなくても、配信は止まらない。

```
sources ──┐
          ├─→ ranking ──→ summarize ──→ render ──→ delivery
 seed ────┘   (採点/重複排除)  (Claude)    (Flex)     (LINE)
                   ↑
                 store (既配信の記録)
```

## クイックスタート

```bash
git clone https://github.com/gentaron/veile-bot.git
cd veile-bot
pip install -e ".[llm]"        # LLM 要約なしなら pip install -e .

# 送信せずに中身だけ確認
python -m veile_bot run --dry-run

# 実際に送る
export LINE_CHANNEL_ACCESS_TOKEN=xxx
export LINE_USER_ID=Uxxxx
python -m veile_bot run
```

`.env.example` に設定できる項目が全部載っている。

## コマンド

| コマンド | 説明 |
| --- | --- |
| `python -m veile_bot run` | ダイジェストを生成して LINE に配信 |
| `python -m veile_bot run --dry-run` | 送信せず標準出力に表示（状態も更新しない） |
| `python -m veile_bot run --no-llm` | Claude を使わず抽出要約で生成 |
| `python -m veile_bot run --limit 5` | 配信件数を変える |
| `python -m veile_bot run --sources github_trending,note` | ソースを絞る |
| `python -m veile_bot run --out digests/today.md` | Markdown アーカイブも書き出す |
| `python -m veile_bot sources` | 利用可能なソース一覧 |

終了コード: `0` 成功 / `1` 設定・実行エラー / `2` 配信失敗。

## ソース

| 名前 | 取得元 | 備考 |
| --- | --- | --- |
| `github_trending` | https://github.com/trending | 公式 API が無いため HTML パース。`stars today` を勢いの指標にする |
| `huggingface` | Hugging Face Hub API | `trendingScore` 降順 |
| `note` | 任意の RSS（既定は note.com/humble_bobcat51） | `VEILE_NOTE_FEEDS` で追加可 |
| `seed` | 同梱の [キュレーションカタログ](veile_bot/data/seed_catalog.json) | 手で選んだ項目。ネットワーク障害時の保険も兼ねる |

`seed` の項目は一次情報ではないので、配信時に必ず「※ 未検証の伝聞情報」と表示される。

## 採点のしくみ

```
score = ソース重み × (0.42×勢い + 0.33×関心度 + 0.25×新しさ) + 新着ボーナス
```

- **勢い** — GitHub は日次スター増、HF は trendingScore / likes / DL。対数で正規化するので桁違いの数字に引きずられない
- **関心度** — `VEILE_INTERESTS` のキーワードとの一致率（3 語一致でほぼ満点）
- **新しさ** — 半減期 36 時間の指数減衰。時刻不明のものは中立値 0.55
- **新着ボーナス** — 24 時間以内に公開されたものに加算

選ばれた理由は `--out` の Markdown に全部残る。納得いかない出力が来たら、まずそこを見る。

同じ対象が複数ソースから来た場合は、URL を正規化して最高スコアの 1 件に畳む
（`github.com/o/r/stargazers` と `github.com/o/r` は同一視）。

## 要約

Claude（既定 `claude-opus-5`）に構造化出力で日本語の見出し・本文・
「なぜ重要か」を書かせる。壊れたときの経路は 3 段:

1. Claude が正常に返す → そのまま使う
2. 一部の項目だけ返ってきた → 足りない分を抽出要約で埋める
3. SDK 未導入 / 認証なし / API 障害 / 拒否 → 全件を抽出要約に切り替え

つまり `ANTHROPIC_API_KEY` が無くても配信は動く。品質が落ちるだけ。

## 重複配信の防止

配信に成功した項目の ID を `state/seen.json` に記録し、既定 21 日間は再送しない。
**配信が失敗したときは記録しない** ので、翌日リトライすれば取りこぼさない。
GitHub Actions では `actions/cache` で実行間を引き継ぐ。

## GitHub Actions

`.github/workflows/main.yml` が毎日 22:00 UTC（07:00 JST）に走る。
Repository secrets に以下を登録する:

| Secret | 必須 | 用途 |
| --- | --- | --- |
| `LINE_CHANNEL_ACCESS_TOKEN` | ✅ | LINE への push |
| `LINE_USER_ID` | ✅ | 送信先 |
| `ANTHROPIC_API_KEY` | — | Claude 要約。未設定なら自動で抽出要約になる |

`workflow_dispatch` から `dry_run: true` で手動確認もできる。

## 開発

```bash
pip install -e ".[dev]"
pytest          # テスト
ruff check .    # Lint
mypy veile_bot  # 型チェック
```

設計の詳細は [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)。

## セキュリティ

認証情報はすべて環境変数から読む。リポジトリには置かない。
`.gitignore` と CI の両方で `info.json` / `.env` の混入を止めている。

> **旧バージョンからの移行**: v1 は `info.json` に LINE のアクセストークンを直接
> コミットしていた。v2 で削除したが Git 履歴には残るため、
> **LINE Developers コンソールで必ずトークンを再発行すること。**

## License

MIT
