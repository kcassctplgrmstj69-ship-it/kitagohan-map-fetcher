# kitagohan-map-fetcher

@kitagohan_insta の Instagram 投稿データを取得し、Google スプレッドシート / マップに連携するプロジェクト。

## 構成

- **本番コード**: Google Apps Script（GAS）
  - Token は GAS の **Script Properties** に保存（クラウド側）
- **ローカル**: 設定の参照・バックアップ・ローカル開発用
  - `.env` に同じ値を保存（チャットや Git に出さない）

## ファイル

| ファイル | 用途 |
|---|---|
| `.env` | ローカル参照用。実際の Token を保持。**コミット禁止** |
| `.env.example` | 値抜きのテンプレート。新環境セットアップ時の参考 |
| `.gitignore` | `.env` などの機密ファイルを除外 |
| `src/gas/` | Google Apps Script のソース（clasp 連携時） |
| `scripts/` | ローカル検証用スクリプト |

## 認証情報の管理

| 値 | 保存先 | 備考 |
|---|---|---|
| Page Long-Lived Token | `.env` + GAS Script Properties + パスワードマネージャー | 永続有効 |
| App Secret | パスワードマネージャーのみ | API 呼び出しでは不要 |
| Business Account ID | `.env` + GAS Script Properties + README | 公開情報レベル |

## GAS 側の設定手順

1. https://script.google.com/ で新規プロジェクト作成
2. プロジェクト名を `kitagohan-map-fetcher` に
3. 左メニュー「プロジェクトの設定」→「スクリプト プロパティ」
4. 以下を追加:
   - `INSTAGRAM_PAGE_TOKEN` = `.env` と同じ値
   - `INSTAGRAM_BUSINESS_ACCOUNT_ID` = `17841460866415181`
5. `src/gas/Code.gs` の内容をコピーして GAS エディタに貼り付け
6. 「実行」で動作確認

## トークンのローテーション

万一 Token が漏洩した場合:

1. Meta for Developers → アプリ「kitagohan-map-fetcher」→「ベーシック」
2. App Secret を **リセット** → 旧 Token は次回 API 呼び出し時に無効化
3. Graph API Explorer で新しい Page Long-Lived Token を再取得
4. `.env` と GAS Script Properties の両方を更新

詳細手順は `docs/token-rotation.md` を参照（未作成）。

---

## GitHub Actions による自動運用

### 構成

```
毎日 06:00 JST
   └─ GitHub Actions が起動
        ├─ scripts/fetch_posts.py   IG API から最新投稿を取得 → data/posts.json
        ├─ scripts/build_map.py     ジオコード → web/index.html 生成
        ├─ data/ web/ を main に commit & push
        └─ web/ を GitHub Pages にデプロイ
                └─ https://kcassctplgrmstj69-ship-it.github.io/kitagohan-map-fetcher/
```

- 維持費: **無料**（GitHub Actions 月2000分まで無料、本構成は月60分程度）
- Mac の状態に依存しない（GitHub のサーバーで実行）

### 初回セットアップ (1回だけ)

#### 0. スプレッドシートを公開設定にする

`kitagohan_stores` スプレッドシートを GitHub Actions から読み取れるようにします。

1. [kitagohan_stores スプレッドシート](https://docs.google.com/spreadsheets/d/1KQUrkR2hXYhfOoMoANq0OgWcGAZdkJqepn1MGgllPX4/edit) を開く
2. 右上の **「共有」** をクリック
3. 「一般的なアクセス」を **「リンクを知っている全員」「閲覧者」** に変更
4. 完了

> ⚠️ スプレッドシートID自体は公開リポジトリに含まれます。「リンクを知っている全員」になっているため、IDを知る人なら閲覧可能になります。きたごはん MAP は店舗情報を公開する性質のページなので問題ありませんが、機密項目を追加する場合はそれらの列を別シートに分離してください。



```bash
# 1. gh CLI をインストールして認証
brew install gh
gh auth login    # ブラウザで GitHub にログイン

# 2. セットアップスクリプト実行
bash scripts/setup_github.sh
```

これだけで以下が自動実行されます:
- GitHub リポジトリ作成
- 初回 push
- Secrets 登録 (`INSTAGRAM_PAGE_TOKEN`, `INSTAGRAM_BUSINESS_ACCOUNT_ID`)
- GitHub Pages 有効化
- 初回ワークフロー実行

完了すると `https://kcassctplgrmstj69-ship-it.github.io/kitagohan-map-fetcher/` で地図が公開されます。

### 手動でワークフローを再実行

```bash
gh workflow run "Build and deploy kitagohan MAP"
```

または GitHub の Web UI → Actions → "Build and deploy kitagohan MAP" → "Run workflow" ボタン。

### Token を更新したとき

`.env` を編集した後:

```bash
source .env
gh secret set INSTAGRAM_PAGE_TOKEN --body "${INSTAGRAM_PAGE_TOKEN}"
```

### スケジュール変更

`.github/workflows/build.yml` の `cron:` 行を編集:

| 頻度 | cron (UTC) |
|---|---|
| 毎日 JST 06:00 (現在) | `0 21 * * *` |
| 毎日 JST 朝6時 + 夕方18時 | `0 21,9 * * *` |
| 1時間ごと | `0 * * * *` |

