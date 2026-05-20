#!/usr/bin/env python3
"""
Google スプレッドシート kitagohan_stores を CSV としてダウンロードし、
data/sheet.csv に保存する。

スプレッドシートは「リンクを知っている全員」または「閲覧者として共有された
サービスアカウント」のいずれかで公開されている必要がある。

環境変数:
  KITAGOHAN_SHEET_ID    既定: 1KQUrkR2hXYhfOoMoANq0OgWcGAZdkJqepn1MGgllPX4
  KITAGOHAN_SHEET_GID   既定: 0 (最初のシート)

依存: 標準ライブラリのみ
"""
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHEET_PATH = ROOT / "data" / "sheet.csv"

DEFAULT_ID = "1KQUrkR2hXYhfOoMoANq0OgWcGAZdkJqepn1MGgllPX4"
DEFAULT_GID = "0"


def main() -> int:
    sheet_id = os.environ.get("KITAGOHAN_SHEET_ID", DEFAULT_ID)
    gid = os.environ.get("KITAGOHAN_SHEET_GID", DEFAULT_GID)
    url = (
        f"https://docs.google.com/spreadsheets/d/{sheet_id}"
        f"/export?format=csv&gid={gid}"
    )
    print(f"→ ダウンロード中: {url}")

    req = urllib.request.Request(url, headers={"User-Agent": "kitagohan-map-fetcher/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            content = r.read()
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code}: {e.reason}", file=sys.stderr)
        if e.code in (401, 403, 404):
            print(
                "  スプレッドシートが「リンクを知っている全員に閲覧権限」になっているか確認してください。",
                file=sys.stderr,
            )
        return 1
    except urllib.error.URLError as e:
        print(f"接続エラー: {e}", file=sys.stderr)
        return 1

    # 一行目に「店舗名」が含まれているかでざっくり検証
    head = content[:200].decode("utf-8", errors="replace")
    if "店舗名" not in head:
        print("ERROR: 先頭行に '店舗名' が見つかりません。", file=sys.stderr)
        print(f"  受信内容(先頭200B): {head!r}", file=sys.stderr)
        return 1

    SHEET_PATH.parent.mkdir(parents=True, exist_ok=True)
    SHEET_PATH.write_bytes(content)
    line_count = content.count(b"\n")
    print(f"保存: {SHEET_PATH} ({line_count} 行, {len(content)} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
