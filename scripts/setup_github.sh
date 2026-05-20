#!/usr/bin/env bash
# kitagohan-map-fetcher を GitHub に push し、GitHub Pages 公開まで自動化するスクリプト
#
# 使い方:
#   bash scripts/setup_github.sh
#
# 事前準備:
#   1. gh CLI インストール:        brew install gh
#   2. gh 認証:                    gh auth login   (ブラウザで GitHub にログイン)
#   3. .env に正しい値がある状態   (INSTAGRAM_PAGE_TOKEN / INSTAGRAM_BUSINESS_ACCOUNT_ID)

set -euo pipefail

REPO_NAME="kitagohan-map-fetcher"
GH_USER="kcassctplgrmstj69-ship-it"
VISIBILITY="public"   # GitHub Pages 無料枠は public が必要

cd "$(dirname "$0")/.."

# -------- 0. 前提チェック --------
echo "→ 前提チェック"
if ! command -v gh >/dev/null 2>&1; then
  echo "ERROR: gh CLI がインストールされていません" >&2
  echo "  brew install gh   でインストールしてください" >&2
  exit 1
fi
if ! gh auth status >/dev/null 2>&1; then
  echo "ERROR: gh CLI が未認証です" >&2
  echo "  gh auth login    を実行してください" >&2
  exit 1
fi
if [ ! -f .env ]; then
  echo "ERROR: .env が見つかりません" >&2
  exit 1
fi
echo "  ✅ gh CLI 認証済み"
echo "  ✅ .env 存在"

# -------- 1. .env 読み込み --------
echo "→ .env から認証情報を読み込み"
set -a
# shellcheck disable=SC1091
source .env
set +a
: "${INSTAGRAM_PAGE_TOKEN:?INSTAGRAM_PAGE_TOKEN が .env に未設定}"
: "${INSTAGRAM_BUSINESS_ACCOUNT_ID:?INSTAGRAM_BUSINESS_ACCOUNT_ID が .env に未設定}"
echo "  ✅ Token / Business ID OK"

# -------- 2. 初回 commit (まだなら) --------
echo "→ Git 状態確認"
git add -A
if ! git diff --cached --quiet; then
  git commit -m "chore: initial setup with GitHub Actions workflow" || true
fi

# -------- 3. GitHub リポジトリ作成 (既存ならスキップ) --------
echo "→ GitHub リポジトリを作成"
if gh repo view "${GH_USER}/${REPO_NAME}" >/dev/null 2>&1; then
  echo "  リポジトリは既に存在: ${GH_USER}/${REPO_NAME}"
else
  gh repo create "${GH_USER}/${REPO_NAME}" \
    --"${VISIBILITY}" \
    --source=. \
    --description="@kitagohan_insta の投稿から札幌グルメマップを自動生成" \
    --remote=origin \
    --push
  echo "  ✅ リポジトリ作成 & push 完了"
fi

# remote が無ければ追加 & push
if ! git remote get-url origin >/dev/null 2>&1; then
  git remote add origin "https://github.com/${GH_USER}/${REPO_NAME}.git"
fi
git branch -M main 2>/dev/null || true
git push -u origin main || git push

# -------- 4. Secrets 登録 --------
echo "→ GitHub Secrets を登録"
gh secret set INSTAGRAM_PAGE_TOKEN --repo "${GH_USER}/${REPO_NAME}" --body "${INSTAGRAM_PAGE_TOKEN}"
gh secret set INSTAGRAM_BUSINESS_ACCOUNT_ID --repo "${GH_USER}/${REPO_NAME}" --body "${INSTAGRAM_BUSINESS_ACCOUNT_ID}"
echo "  ✅ Secrets 登録完了"

# -------- 5. GitHub Pages 有効化 --------
echo "→ GitHub Pages を有効化（source: GitHub Actions）"
gh api -X POST "repos/${GH_USER}/${REPO_NAME}/pages" \
  -f "build_type=workflow" 2>/dev/null \
  || gh api -X PUT "repos/${GH_USER}/${REPO_NAME}/pages" \
       -f "build_type=workflow" \
  || echo "  ℹ️ Pages はすでに有効か、後で手動で有効化が必要"

# -------- 6. 初回ワークフロー実行 --------
echo "→ 初回ワークフローを起動"
sleep 3
gh workflow run "Build and deploy kitagohan MAP" --repo "${GH_USER}/${REPO_NAME}" || \
  echo "  ℹ️ ワークフローが見つからない場合、push が反映されるまで数秒待ってから再試行してください"

# -------- 7. 結果案内 --------
PAGE_URL="https://${GH_USER}.github.io/${REPO_NAME}/"
echo ""
echo "========================================"
echo "✅ セットアップ完了"
echo "========================================"
echo ""
echo "リポジトリ:   https://github.com/${GH_USER}/${REPO_NAME}"
echo "Actions:      https://github.com/${GH_USER}/${REPO_NAME}/actions"
echo "公開URL:      ${PAGE_URL}"
echo ""
echo "1〜2分後に Actions タブで初回ビルドの進行を確認できます。"
echo "ビルド成功後、上記の公開URLにアクセスすれば地図が表示されます。"
echo "翌朝以降は毎日 JST 06:00 に自動更新されます。"
