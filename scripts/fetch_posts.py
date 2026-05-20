#!/usr/bin/env python3
"""
Instagram Graph API から @kitagohan_insta の全投稿を取得し、
data/posts.json に保存する。

環境変数:
  INSTAGRAM_BUSINESS_ACCOUNT_ID  (例: 17841460866415181)
  INSTAGRAM_PAGE_TOKEN           Page Long-Lived Token

依存: 標準ライブラリのみ
"""
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS_PATH = ROOT / "data" / "posts.json"

GRAPH_API_VERSION = "v21.0"
FIELDS = (
    "id,caption,media_type,media_url,thumbnail_url,permalink,"
    "timestamp,like_count,comments_count,media_product_type"
)
PAGE_LIMIT = 50      # 1ページあたりの取得件数（最大100）
MAX_PAGES = 30       # 安全弁: 最大ページ数（50件×30＝1500件）
SLEEP_BETWEEN_PAGES = 0.3  # API レート制限対策


def fetch_page(ig_id: str, token: str, after: str | None = None) -> dict:
    params = {
        "fields": FIELDS,
        "limit": PAGE_LIMIT,
        "access_token": token,
    }
    if after:
        params["after"] = after
    qs = urllib.parse.urlencode(params)
    url = f"https://graph.facebook.com/{GRAPH_API_VERSION}/{ig_id}/media?{qs}"
    req = urllib.request.Request(url, headers={"User-Agent": "kitagohan-map-fetcher/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        print(f"HTTP {e.code} from Graph API:\n{body}", file=sys.stderr)
        raise


def fetch_all_posts(ig_id: str, token: str) -> list[dict]:
    all_items: list[dict] = []
    after: str | None = None
    for page_no in range(1, MAX_PAGES + 1):
        page = fetch_page(ig_id, token, after)
        items = page.get("data", [])
        all_items.extend(items)
        print(f"  page {page_no}: {len(items)} 件 (累計 {len(all_items)})")
        next_cursor = page.get("paging", {}).get("cursors", {}).get("after")
        has_next = bool(page.get("paging", {}).get("next") and next_cursor)
        if not has_next:
            break
        after = next_cursor
        time.sleep(SLEEP_BETWEEN_PAGES)
    else:
        print(f"  ⚠️ MAX_PAGES={MAX_PAGES} 到達。続きがある可能性あり", file=sys.stderr)
    return all_items


def main() -> int:
    ig_id = os.environ.get("INSTAGRAM_BUSINESS_ACCOUNT_ID")
    token = os.environ.get("INSTAGRAM_PAGE_TOKEN")
    if not ig_id:
        print("ERROR: INSTAGRAM_BUSINESS_ACCOUNT_ID が未設定", file=sys.stderr)
        return 1
    if not token:
        print("ERROR: INSTAGRAM_PAGE_TOKEN が未設定", file=sys.stderr)
        return 1

    print(f"→ IG Business Account ID: {ig_id}")
    print(f"→ Graph API {GRAPH_API_VERSION} で投稿取得中…")

    items = fetch_all_posts(ig_id, token)
    print(f"\n取得完了: {len(items)} 件")

    POSTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    payload = {"data": items}
    POSTS_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
    print(f"保存: {POSTS_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
