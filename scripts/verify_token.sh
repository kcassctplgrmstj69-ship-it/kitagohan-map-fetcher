#!/usr/bin/env bash
# ローカルで .env の Token が有効か確認するスクリプト
# 使い方: bash scripts/verify_token.sh

set -euo pipefail

# .env を読み込み（プロジェクトルート想定）
if [ -f "$(dirname "$0")/../.env" ]; then
  # コメントと空行を除いて export
  set -a
  # shellcheck disable=SC1091
  source "$(dirname "$0")/../.env"
  set +a
else
  echo "ERROR: .env が見つかりません" >&2
  exit 1
fi

if [ -z "${INSTAGRAM_PAGE_TOKEN:-}" ]; then
  echo "ERROR: .env の INSTAGRAM_PAGE_TOKEN が空です" >&2
  exit 1
fi

echo "→ Token 検証中..."
curl -s -G "https://graph.facebook.com/v21.0/${INSTAGRAM_BUSINESS_ACCOUNT_ID}" \
  --data-urlencode "fields=id,username,name" \
  --data-urlencode "access_token=${INSTAGRAM_PAGE_TOKEN}" \
  | python3 -m json.tool
