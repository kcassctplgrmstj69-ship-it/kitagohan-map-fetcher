#!/usr/bin/env python3
"""
posts.json からショップ情報を抽出し、ジオコーディング後に
web/index.html (Leaflet 地図) を生成する。

依存: 標準ライブラリのみ
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POSTS_PATH = ROOT / "data" / "posts.json"
CACHE_PATH = ROOT / "data" / "geocode_cache.json"
SHOPS_PATH = ROOT / "data" / "shops.json"
HTML_PATH = ROOT / "web" / "index.html"

# ----------- 1) パース -----------

# 「📍店名」(改行 or " / " 区切り or 行末まで)
RE_SHOP = re.compile(r"📍\s*(.+?)(?:\n|$|\s*/\s)")
# 「・場所：...」または「・場所:...」
RE_PLACE = re.compile(r"[・･]\s*場所[：:]\s*(.+?)(?:\n|$|\s*/\s)")
# 「〒XXX-XXXX (住所)」
RE_POSTAL = re.compile(r"〒\d{3}-?\d{4}\s*(.+?)(?:\n|$|\s*/\s)")
# 投稿冒頭の @handle（複数あれば最初の📍より下にある最初の @）
RE_HANDLE = re.compile(r"@([A-Za-z0-9_\.]+)")
# 価格・予算 行
RE_PRICE = re.compile(r"[・･]\s*(?:価格|予算)[：:]\s*(.+?)(?:\n|$|\s*/\s)")


def parse_caption(caption: str) -> dict:
    """キャプションから構造化データを抽出。失敗した項目は None。"""
    if not caption:
        return {}
    info = {}
    m = RE_SHOP.search(caption)
    if m:
        info["shop_name"] = m.group(1).strip().split("（")[0].strip()
        # 📍以降の文字列から @handle を探す
        tail = caption[m.end():]
        m2 = RE_HANDLE.search(tail)
        if m2:
            info["handle"] = m2.group(1)
    m = RE_PLACE.search(caption)
    if m:
        info["address"] = m.group(1).strip()
    if "address" not in info:
        m = RE_POSTAL.search(caption)
        if m:
            info["address"] = m.group(1).strip()
    m = RE_PRICE.search(caption)
    if m:
        info["price"] = m.group(1).strip()
    return info


# ----------- 2) ジオコーディング -----------

def normalize_address(addr: str) -> str:
    """ジオコーディング精度を上げるため住所を正規化"""
    s = addr.strip()
    # 全角数字→半角
    s = s.translate(str.maketrans("０１２３４５６７８９ー－", "0123456789--"))
    # 「北海道」前置は札幌市があれば省く（Nominatim は重複を嫌う）
    if "札幌市" in s and s.startswith("北海道"):
        s = s.replace("北海道", "", 1).strip()
    # 1) 「南X条西Y丁目Z」→「南X条西Y-Z」、「南X条西Y丁目Z-W」→「南X条西Y-Z-W」
    s = re.sub(r"(\d+)丁目(\d)", r"\1-\2", s)
    # 末尾の「丁目」だけは残す（例: "南5条西3丁目"）
    # 2) スペース以降のビル名を削除
    s = re.split(r"[ 　]", s, maxsplit=1)[0]
    # 3) 住所の数字部分（X-Y-Z パターン）の後に続く文字を切る
    #    例: "南1条西9-4-1札幌19L" → "南1条西9-4-1"
    m = re.search(r"(.+?[西東南北中](?:\d+条[西東南北中])?\d+(?:-\d+){1,3})", s)
    if m:
        s = m.group(1)
    # 末尾の余計な記号
    s = s.rstrip("、,。.-")
    return s


def geocode_nominatim(query: str) -> tuple | None:
    """OpenStreetMap Nominatim で住所→緯度経度。失敗時 None。"""
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": query, "format": "json", "limit": 1, "accept-language": "ja",
        "countrycodes": "jp",
    })
    req = urllib.request.Request(url, headers={
        # Nominatim は User-Agent を要求
        "User-Agent": "kitagohan-map-fetcher/0.1 (local dev)"
    })
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.load(r)
        if not data:
            return None
        return float(data[0]["lat"]), float(data[0]["lon"])
    except Exception as e:
        print(f"  geocode error for {query!r}: {e}", file=sys.stderr)
        return None


def load_cache() -> dict:
    if CACHE_PATH.exists():
        return json.loads(CACHE_PATH.read_text())
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


# ----------- 3) HTML 生成 -----------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>きたごはんMAP</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  :root { color-scheme: light dark; }
  *, *::before, *::after { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", sans-serif; }
  header { padding: 12px 16px; border-bottom: 1px solid #ddd; display: flex; align-items: baseline; gap: 12px; }
  header h1 { margin: 0; font-size: 18px; }
  header .meta { color: #666; font-size: 13px; }
  main { display: grid; grid-template-columns: 1fr 380px; height: calc(100vh - 50px); }
  #map { width: 100%; height: 100%; }
  aside { overflow-y: auto; border-left: 1px solid #ddd; background: #fafafa; }
  .card { padding: 10px; border-bottom: 1px solid #eee; cursor: pointer; display: flex; gap: 10px; }
  .card:hover { background: #f0f0f0; }
  .card.active { background: #fff3cd; }
  .card img { width: 80px; height: 80px; object-fit: cover; border-radius: 6px; flex-shrink: 0; background: #ddd; }
  .card .body { flex: 1; min-width: 0; }
  .card .name { font-weight: 600; margin: 0 0 4px; font-size: 14px; }
  .card .meta-row { color: #777; font-size: 12px; margin-bottom: 4px; }
  .card .caption { font-size: 12px; color: #444; max-height: 50px; overflow: hidden;
                   display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; }
  .nogeo { padding: 12px; color: #999; font-size: 13px; }
  .pop-thumb { width: 200px; height: 150px; object-fit: cover; border-radius: 6px; }
  .pop-title { font-weight: 700; margin: 6px 0 2px; }
  .pop-meta { font-size: 12px; color: #555; margin-bottom: 4px; }
  @media (max-width: 700px) {
    main { grid-template-columns: 1fr; grid-template-rows: 50vh 1fr; }
    aside { border-left: none; border-top: 1px solid #ddd; }
  }
</style>
</head>
<body>
<header>
  <h1>🍽️ きたごはんMAP</h1>
  <span class="meta">@kitagohan_insta · 投稿 __POST_COUNT__件（うち地図表示 __PIN_COUNT__件）</span>
</header>
<main>
  <div id="map"></div>
  <aside id="list"></aside>
</main>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const POSTS = __POSTS_JSON__;

const map = L.map('map').setView([43.0686, 141.3507], 13); // 札幌駅中心
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap'
}).addTo(map);

const markersById = {};
const cardsById = {};

const list = document.getElementById('list');
const withGeo = POSTS.filter(p => p.lat && p.lon);
const withoutGeo = POSTS.filter(p => !(p.lat && p.lon));

function escapeHtml(s) {
  return (s || '').replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}

withGeo.forEach(p => {
  const m = L.marker([p.lat, p.lon]).addTo(map);
  const thumb = p.thumbnail_url || p.media_url || '';
  m.bindPopup(`
    <div style="min-width:200px">
      ${thumb ? `<img class="pop-thumb" src="${escapeHtml(thumb)}" loading="lazy">` : ''}
      <div class="pop-title">${escapeHtml(p.shop_name || '(店名不明)')}</div>
      <div class="pop-meta">${escapeHtml(p.address || '')}</div>
      <div class="pop-meta">♥ ${p.like_count ?? '-'} ・ 💬 ${p.comments_count ?? '-'}</div>
      ${p.handle ? `<a href="https://www.instagram.com/${encodeURIComponent(p.handle)}/" target="_blank">@${escapeHtml(p.handle)}</a> · ` : ''}
      <a href="${escapeHtml(p.permalink)}" target="_blank">投稿を開く</a>
    </div>
  `);
  markersById[p.id] = m;
});

function renderList() {
  list.innerHTML = '';
  withGeo.forEach(p => {
    const card = document.createElement('div');
    card.className = 'card';
    card.innerHTML = `
      <img loading="lazy" src="${escapeHtml(p.thumbnail_url || p.media_url || '')}">
      <div class="body">
        <div class="name">📍 ${escapeHtml(p.shop_name || '(店名不明)')}</div>
        <div class="meta-row">${escapeHtml(p.address || '')}</div>
        <div class="meta-row">♥ ${p.like_count ?? '-'} ・ ${(p.timestamp || '').slice(0,10)}</div>
        <div class="caption">${escapeHtml((p.caption || '').slice(0, 80))}</div>
      </div>
    `;
    card.addEventListener('click', () => {
      const m = markersById[p.id];
      if (m) {
        map.setView(m.getLatLng(), 16);
        m.openPopup();
        document.querySelectorAll('.card.active').forEach(el => el.classList.remove('active'));
        card.classList.add('active');
      }
    });
    cardsById[p.id] = card;
    list.appendChild(card);
  });

  if (withoutGeo.length) {
    const sec = document.createElement('div');
    sec.className = 'nogeo';
    sec.innerHTML = `<strong>地図化できなかった投稿 (${withoutGeo.length}件)</strong><br>` +
      'キャプションから住所を抽出できなかった投稿です。';
    list.appendChild(sec);
    withoutGeo.forEach(p => {
      const card = document.createElement('div');
      card.className = 'card';
      card.style.opacity = '0.6';
      card.innerHTML = `
        <img loading="lazy" src="${escapeHtml(p.thumbnail_url || p.media_url || '')}">
        <div class="body">
          <div class="name">${escapeHtml(p.shop_name || '(住所不明)')}</div>
          <div class="meta-row">♥ ${p.like_count ?? '-'} ・ ${(p.timestamp || '').slice(0,10)}</div>
          <div class="caption">${escapeHtml((p.caption || '').slice(0, 80))}</div>
        </div>
      `;
      list.appendChild(card);
    });
  }
}
renderList();
</script>
</body>
</html>
"""


# ----------- メイン -----------

def main():
    posts = json.loads(POSTS_PATH.read_text()).get("data", [])
    print(f"投稿: {len(posts)}件")

    cache = load_cache()
    shops = []

    for p in posts:
        caption = p.get("caption") or ""
        info = parse_caption(caption)
        record = {
            "id": p["id"],
            "permalink": p.get("permalink"),
            "timestamp": p.get("timestamp"),
            "media_type": p.get("media_type"),
            "media_url": p.get("media_url"),
            "thumbnail_url": p.get("thumbnail_url"),
            "like_count": p.get("like_count"),
            "comments_count": p.get("comments_count"),
            "caption": caption,
            **info,
        }
        shops.append(record)

    # 住所のジオコーディング（キャッシュ付き）
    geocoded = 0
    new_fetched = 0
    for r in shops:
        addr = r.get("address")
        if not addr:
            continue
        addr_norm = normalize_address(addr)
        # 「札幌」を含まない短い住所には接頭を付けてみる
        query = addr_norm if "札幌" in addr_norm or "北海道" in addr_norm else f"札幌市 {addr_norm}"
        if query in cache:
            latlon = cache[query]
        else:
            print(f"  → geocoding: {query}")
            latlon = geocode_nominatim(query)
            cache[query] = latlon
            new_fetched += 1
            time.sleep(1.1)  # Nominatim の利用規約: 1req/sec 以下
            save_cache(cache)
        if latlon:
            r["lat"], r["lon"] = latlon
            geocoded += 1

    SHOPS_PATH.write_text(json.dumps(shops, ensure_ascii=False, indent=2))
    print(f"\nジオコード成功: {geocoded}/{sum(1 for r in shops if r.get('address'))} 件")
    print(f"  (新規取得 {new_fetched}件、キャッシュ {len(cache)} エントリ)")

    html = (HTML_TEMPLATE
            .replace("__POST_COUNT__", str(len(shops)))
            .replace("__PIN_COUNT__", str(geocoded))
            .replace("__POSTS_JSON__", json.dumps(shops, ensure_ascii=False)))
    HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(html)
    print(f"\n生成: {HTML_PATH}")


if __name__ == "__main__":
    main()
