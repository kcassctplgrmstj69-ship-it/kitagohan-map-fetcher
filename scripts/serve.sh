#!/usr/bin/env bash
# ローカルで MAP を表示するための簡易サーバー
# 使い方: bash scripts/serve.sh
# 終了: Ctrl+C

set -euo pipefail
cd "$(dirname "$0")/.."

PORT=8765
URL="http://localhost:${PORT}/web/index.html"

echo "→ Starting local server on port ${PORT}"
echo "→ Open: ${URL}"
echo "→ Press Ctrl+C to stop"

# 自動でブラウザを開く
( sleep 1 && open "${URL}" ) &

python3 -m http.server "${PORT}" --bind 127.0.0.1
