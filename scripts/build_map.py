#!/usr/bin/env python3
"""
スプレッドシート (data/sheet.csv) を真の店舗マスタとして使い、
Instagram 投稿 (data/posts.json) を投稿URLで紐付けて、
web/index.html (Leaflet 地図) を生成する。

スプレッドシートにある主な列:
  店舗名 / 取材回数 /
  投稿1_URL / 投稿2_URL / 投稿3_URL (これらで IG posts と join) /
  住所 / 緯度 / 経度 / エリア /
  主ジャンル / サブジャンル / シーンタグ /
  予算_昼 / 予算_夜 / 営業時間 / 定休日 / きたごはんポイント /
  個室 / 喫煙 / FAQ_* /
  再生数_最大 / Google評価 / Google口コミ数

依存: 標準ライブラリのみ
"""
import csv
import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHEET_PATH = ROOT / "data" / "sheet.csv"
POSTS_PATH = ROOT / "data" / "posts.json"
CACHE_PATH = ROOT / "data" / "geocode_cache.json"
SHOPS_PATH = ROOT / "data" / "shops.json"
HTML_PATH = ROOT / "web" / "index.html"

# IG 投稿URLから shortcode を抽出する正規表現
SHORTCODE_RE = re.compile(r"instagram\.com/(?:p|reel|tv)/([A-Za-z0-9_-]+)")


def extract_shortcode(url: str) -> str | None:
    if not url:
        return None
    m = SHORTCODE_RE.search(url)
    return m.group(1) if m else None


def load_posts_by_shortcode() -> dict[str, dict]:
    """posts.json を読み、shortcode をキーとした辞書に変換"""
    data = json.loads(POSTS_PATH.read_text())
    items = data.get("data", [])
    out: dict[str, dict] = {}
    for p in items:
        sc = extract_shortcode(p.get("permalink", ""))
        if sc:
            out[sc] = p
    return out


# ----------- ジオコーディング (足りない緯度経度を補完) -----------

def load_cache() -> dict:
    if CACHE_PATH.exists():
        try:
            return json.loads(CACHE_PATH.read_text())
        except json.JSONDecodeError:
            return {}
    return {}


def save_cache(cache: dict) -> None:
    CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2))


def normalize_address(addr: str) -> str:
    s = addr.strip()
    s = s.translate(str.maketrans("０１２３４５６７８９ー－", "0123456789--"))
    if "札幌市" in s and s.startswith("北海道"):
        s = s.replace("北海道", "", 1).strip()
    s = re.sub(r"(\d+)丁目(\d)", r"\1-\2", s)
    s = re.split(r"[ 　]", s, maxsplit=1)[0]
    m = re.search(r"(.+?[西東南北中](?:\d+条[西東南北中])?\d+(?:-\d+){1,3})", s)
    if m:
        s = m.group(1)
    s = s.rstrip("、,。.-")
    return s


def geocode_nominatim(query: str) -> tuple | None:
    url = "https://nominatim.openstreetmap.org/search?" + urllib.parse.urlencode({
        "q": query, "format": "json", "limit": 1, "accept-language": "ja",
        "countrycodes": "jp",
    })
    req = urllib.request.Request(url, headers={
        "User-Agent": "kitagohan-map-fetcher/1.0 (https://github.com/kcassctplgrmstj69-ship-it/kitagohan-map-fetcher)"
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


# ----------- メイン処理 -----------

def to_float(v: str) -> float | None:
    v = (v or "").strip()
    if not v:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def to_int(v: str) -> int | None:
    v = (v or "").strip().replace(",", "")
    if not v:
        return None
    try:
        return int(float(v))
    except ValueError:
        return None


def build_shops() -> tuple[list[dict], int, int, int]:
    posts_by_sc = load_posts_by_shortcode()
    cache = load_cache()
    print(f"posts.json: {len(posts_by_sc)} 件 (shortcode keyed)")

    with open(SHEET_PATH, encoding="utf-8") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    print(f"sheet.csv: {len(rows)} 行")

    shops: list[dict] = []
    geocoded = 0
    new_fetched = 0
    matched_posts_count = 0

    for r in rows:
        name = (r.get("店舗名") or "").strip()
        if not name:
            continue

        # 投稿URL → 投稿データ
        shop_posts: list[dict] = []
        for col in ("投稿1_URL", "投稿2_URL", "投稿3_URL"):
            url = (r.get(col) or "").strip()
            if not url:
                continue
            sc = extract_shortcode(url)
            if not sc:
                continue
            p = posts_by_sc.get(sc)
            if p:
                shop_posts.append({
                    "id": p.get("id"),
                    "shortcode": sc,
                    "permalink": p.get("permalink"),
                    "media_type": p.get("media_type"),
                    "media_product_type": p.get("media_product_type"),
                    "media_url": p.get("media_url"),
                    "thumbnail_url": p.get("thumbnail_url"),
                    "caption": p.get("caption"),
                    "timestamp": p.get("timestamp"),
                    "like_count": p.get("like_count"),
                    "comments_count": p.get("comments_count"),
                })
                matched_posts_count += 1
            else:
                # API 結果に無い → 古すぎて消えたか、別アカウントの投稿
                shop_posts.append({
                    "shortcode": sc,
                    "permalink": url,
                    "_missing": True,
                })

        # 緯度経度
        lat = to_float(r.get("緯度(要追加)"))
        lon = to_float(r.get("経度(要追加)"))
        addr = (r.get("住所(要追加)") or "").strip()

        if (lat is None or lon is None) and addr and "要確認" not in addr:
            # スプレッドシートに座標無し → ジオコード
            addr_norm = normalize_address(addr)
            query = addr_norm if ("札幌" in addr_norm or "北海道" in addr_norm or "小樽" in addr_norm) else f"札幌市 {addr_norm}"
            cached = cache.get(query)
            if cached and isinstance(cached, list) and len(cached) == 2:
                lat, lon = cached
            else:
                # 未キャッシュ or 過去に失敗 (None) → 再試行
                print(f"  → geocoding: {query}")
                latlon = geocode_nominatim(query)
                if latlon:
                    cache[query] = list(latlon)
                    lat, lon = latlon
                else:
                    cache[query] = None  # 記録だけして次回も再試行
                new_fetched += 1
                time.sleep(1.1)  # Nominatim 利用規約 1req/sec
                save_cache(cache)

        if lat is not None and lon is not None:
            geocoded += 1

        record = {
            "name": name,
            "status": (r.get("ステータス") or "").strip(),
            "alias_note": (r.get("別名・表記揺れメモ") or "").strip(),
            "visit_count": to_int(r.get("取材回数")),
            "address": addr,
            "area": (r.get("エリア(要追加)") or "").strip(),
            "lat": lat,
            "lon": lon,
            "main_genre": (r.get("主ジャンル(要追加)") or "").strip(),
            "sub_genre": (r.get("サブジャンル(要追加)") or "").strip(),
            "scene_tags": (r.get("シーンタグ(要追加)") or "").strip(),
            "budget_lunch": (r.get("予算_昼(要追加)") or "").strip(),
            "budget_dinner": (r.get("予算_夜(要追加)") or "").strip(),
            "hours": (r.get("営業時間(要追加)") or "").strip(),
            "closed": (r.get("定休日(要追加)") or "").strip(),
            "highlight": (r.get("きたごはんポイント(要追加)") or "").strip(),
            "private_room": (r.get("個室(あり/なし)") or "").strip(),
            "smoking": (r.get("喫煙(禁煙/喫煙可/分煙)") or "").strip(),
            "max_plays": to_int(r.get("再生数_最大")),
            "google_rating": to_float(r.get("Google評価")),
            "google_reviews": to_int(r.get("Google口コミ数")),
            "posts": shop_posts,
        }
        shops.append(record)

    return shops, geocoded, new_fetched, matched_posts_count


# ----------- HTML テンプレ -----------

HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>きたごはんMAP</title>
<meta name="viewport" content="width=device-width,initial-scale=1">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  :root { color-scheme: light dark; --accent: #ff6b35; }
  *, *::before, *::after { box-sizing: border-box; }
  html, body { margin: 0; padding: 0; height: 100%; font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic", sans-serif; }
  header { padding: 12px 16px; border-bottom: 1px solid #ddd; display: flex; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  header h1 { margin: 0; font-size: 18px; }
  header .meta { color: #666; font-size: 13px; }
  main { display: grid; grid-template-columns: 1fr 380px; height: calc(100vh - 50px); }
  #map { width: 100%; height: 100%; }
  aside { overflow-y: auto; border-left: 1px solid #ddd; background: #fafafa; }

  /* リストカード */
  .card { padding: 10px; border-bottom: 1px solid #eee; cursor: pointer; display: flex; gap: 10px; }
  .card:hover { background: #f0f0f0; }
  .card.active { background: #fff3cd; }
  .card .thumb {
    width: 72px; aspect-ratio: 9 / 16;
    object-fit: cover; border-radius: 6px;
    flex-shrink: 0; background: #ddd;
  }
  .card .body { flex: 1; min-width: 0; }
  .card .name { font-weight: 600; margin: 0 0 4px; font-size: 14px; line-height: 1.3; }
  .card .meta-row { color: #777; font-size: 12px; margin-bottom: 3px; }
  .card .meta-row .star { color: #f6a623; }
  .card .meta-row .plays { color: var(--accent); font-weight: 600; }
  .card .tags { font-size: 11px; color: #999; margin-top: 3px; }
  .nogeo { padding: 12px; color: #999; font-size: 13px; border-bottom: 1px solid #eee; }

  /* ポップアップ */
  .leaflet-popup-content { margin: 12px 14px; min-width: 240px; }
  .pop-media-wrap {
    width: 240px; aspect-ratio: 9 / 16;
    background: #000; border-radius: 8px; overflow: hidden;
    margin-bottom: 8px; position: relative;
  }
  .pop-media-wrap video, .pop-media-wrap img {
    width: 100%; height: 100%; object-fit: cover; display: block;
  }
  .pop-title { font-weight: 700; font-size: 15px; margin: 6px 0 4px; }
  .pop-meta { font-size: 12px; color: #555; margin-bottom: 3px; }
  .pop-meta .star { color: #f6a623; font-weight: 600; }
  .pop-meta .plays { color: var(--accent); font-weight: 600; }
  .pop-pills {
    display: flex; flex-wrap: wrap; gap: 4px; margin: 6px 0;
  }
  .pop-pills .pill {
    background: #eef; color: #335; font-size: 11px;
    padding: 2px 8px; border-radius: 10px;
  }
  .pop-highlight { font-size: 12px; color: #444; margin: 6px 0; line-height: 1.4; }
  .pop-thumbs {
    display: flex; gap: 4px; margin-top: 6px;
  }
  .pop-thumbs .pt {
    width: 40px; aspect-ratio: 9 / 16;
    object-fit: cover; border-radius: 4px; cursor: pointer;
    border: 2px solid transparent;
  }
  .pop-thumbs .pt.active { border-color: var(--accent); }
  .pop-links { margin-top: 6px; font-size: 12px; }
  .pop-links a { color: #06c; text-decoration: none; margin-right: 8px; }
  .pop-links a:hover { text-decoration: underline; }

  @media (max-width: 700px) {
    main { grid-template-columns: 1fr; grid-template-rows: 55vh 1fr; }
    aside { border-left: none; border-top: 1px solid #ddd; }
    .pop-media-wrap { width: 200px; }
  }
</style>
</head>
<body>
<header>
  <h1>🍽️ きたごはんMAP <span style="font-size:12px; color:#888; font-weight:normal;">ver 0.02</span></h1>
  <span class="meta">@kitagohan_insta · 店舗 __SHOP_COUNT__店（うち地図表示 __PIN_COUNT__店） · 最終更新 __UPDATED_AT__</span>
</header>
<main>
  <div id="map"></div>
  <aside id="list"></aside>
</main>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const SHOPS = __SHOPS_JSON__;

const map = L.map('map').setView([43.0686, 141.3507], 13);  // 札幌駅
L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
  maxZoom: 19,
  attribution: '&copy; OpenStreetMap'
}).addTo(map);

const markersById = {};
const cardsById = {};

const list = document.getElementById('list');
const withGeo = SHOPS.filter(s => s.lat != null && s.lon != null);
const withoutGeo = SHOPS.filter(s => !(s.lat != null && s.lon != null));

function esc(s) {
  return (s || '').replace(/[&<>"']/g, c => ({
    '&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'
  }[c]));
}

function formatPlays(n) {
  if (n == null || isNaN(n)) return '-';
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\\.0$/, '') + '万';
  return n.toLocaleString();
}

function firstPostMedia(shop) {
  return (shop.posts || []).find(p => p.thumbnail_url || p.media_url) || null;
}

function buildPopupHTML(shop) {
  const posts = (shop.posts || []).filter(p => !p._missing && (p.thumbnail_url || p.media_url));
  const initial = posts[0] || {};

  const mediaSlotId = `media-${shop.idx}`;
  const renderInitialMedia = (post) => {
    if (!post) return '';
    if (post.media_type === 'VIDEO' && post.media_url) {
      return `<video src="${esc(post.media_url)}" poster="${esc(post.thumbnail_url || '')}"
                controls playsinline preload="metadata"></video>`;
    }
    return `<img src="${esc(post.thumbnail_url || post.media_url)}" alt="">`;
  };

  const tagsHTML = (shop.scene_tags || '').split(',')
    .map(t => t.trim()).filter(t => t)
    .slice(0, 5)
    .map(t => `<span class="pill">${esc(t)}</span>`).join('');

  const thumbsHTML = posts.length > 1 ? `
    <div class="pop-thumbs">
      ${posts.map((p, i) => `
        <img class="pt ${i === 0 ? 'active' : ''}"
             data-shop="${shop.idx}" data-post="${i}"
             src="${esc(p.thumbnail_url || p.media_url)}" alt="">
      `).join('')}
    </div>` : '';

  return `
    <div class="pop-media-wrap" id="${mediaSlotId}">${renderInitialMedia(initial)}</div>
    <div class="pop-title">${esc(shop.name)}</div>
    <div class="pop-meta">
      ${shop.google_rating != null ? `<span class="star">★ ${shop.google_rating.toFixed(1)}</span> (${shop.google_reviews ?? '?'}件)` : ''}
      ${shop.max_plays != null ? ` · <span class="plays">▶ ${formatPlays(shop.max_plays)}</span>` : ''}
    </div>
    ${shop.area || shop.main_genre ? `<div class="pop-meta">${esc(shop.area || '')}${shop.area && shop.main_genre ? ' · ' : ''}${esc(shop.main_genre || '')}${shop.sub_genre ? ' / ' + esc(shop.sub_genre) : ''}</div>` : ''}
    ${shop.address ? `<div class="pop-meta">${esc(shop.address)}</div>` : ''}
    ${shop.budget_lunch || shop.budget_dinner ? `<div class="pop-meta">💴 ${shop.budget_lunch ? '昼 ¥' + esc(shop.budget_lunch) : ''}${shop.budget_lunch && shop.budget_dinner ? ' / ' : ''}${shop.budget_dinner ? '夜 ¥' + esc(shop.budget_dinner) : ''}</div>` : ''}
    ${tagsHTML ? `<div class="pop-pills">${tagsHTML}</div>` : ''}
    ${shop.highlight ? `<div class="pop-highlight">💡 ${esc(shop.highlight)}</div>` : ''}
    ${thumbsHTML}
    <div class="pop-links">
      ${posts.map((p, i) => `<a href="${esc(p.permalink)}" target="_blank" rel="noopener">投稿${i+1}を Instagram で開く</a>`).join('<br>')}
    </div>
  `;
}

// ポップアップ内のサムネクリック → 動画/画像を切り替え
document.addEventListener('click', (e) => {
  const t = e.target;
  if (t.classList && t.classList.contains('pt')) {
    const shopIdx = +t.dataset.shop;
    const postIdx = +t.dataset.post;
    const shop = SHOPS[shopIdx];
    const post = (shop.posts || []).filter(p => !p._missing && (p.thumbnail_url || p.media_url))[postIdx];
    const slot = document.getElementById(`media-${shopIdx}`);
    if (slot && post) {
      if (post.media_type === 'VIDEO' && post.media_url) {
        slot.innerHTML = `<video src="${post.media_url}" poster="${post.thumbnail_url || ''}" controls playsinline preload="metadata" autoplay></video>`;
      } else {
        slot.innerHTML = `<img src="${post.thumbnail_url || post.media_url}" alt="">`;
      }
    }
    // active 切り替え
    const sibs = slot ? slot.parentNode.querySelectorAll('.pt') : [];
    sibs.forEach((el, i) => el.classList.toggle('active', i === postIdx));
  }
});

SHOPS.forEach((s, idx) => { s.idx = idx; });

withGeo.forEach(s => {
  const m = L.marker([s.lat, s.lon]).addTo(map);
  m.bindPopup(() => buildPopupHTML(s), { maxWidth: 280, minWidth: 240 });
  markersById[s.idx] = m;
});

function renderList() {
  list.innerHTML = '';
  withGeo
    .slice()
    .sort((a, b) => (b.max_plays || 0) - (a.max_plays || 0))
    .forEach(s => {
      const card = document.createElement('div');
      card.className = 'card';
      const top = firstPostMedia(s) || {};
      const thumb = top.thumbnail_url || top.media_url || '';
      card.innerHTML = `
        <img class="thumb" loading="lazy" src="${esc(thumb)}" alt="">
        <div class="body">
          <div class="name">${esc(s.name)}</div>
          <div class="meta-row">
            ${s.google_rating != null ? `<span class="star">★ ${s.google_rating.toFixed(1)}</span> (${s.google_reviews ?? '?'})` : ''}
            ${s.max_plays != null ? ` · <span class="plays">▶ ${formatPlays(s.max_plays)}</span>` : ''}
          </div>
          ${s.area || s.main_genre ? `<div class="meta-row">${esc(s.area || '')}${s.area && s.main_genre ? ' · ' : ''}${esc(s.main_genre || '')}</div>` : ''}
          ${s.highlight ? `<div class="tags">💡 ${esc(s.highlight.slice(0, 50))}</div>` : ''}
        </div>
      `;
      card.addEventListener('click', () => {
        const m = markersById[s.idx];
        if (m) {
          map.setView(m.getLatLng(), 16);
          m.openPopup();
          document.querySelectorAll('.card.active').forEach(el => el.classList.remove('active'));
          card.classList.add('active');
        }
      });
      cardsById[s.idx] = card;
      list.appendChild(card);
    });

  if (withoutGeo.length) {
    const sec = document.createElement('div');
    sec.className = 'nogeo';
    sec.innerHTML = `<strong>地図化できなかった店舗 (${withoutGeo.length}店)</strong><br>住所未確定 or ジオコード失敗のため地図ピンが立てられませんでした。`;
    list.appendChild(sec);
  }
}
renderList();
</script>
</body>
</html>
"""


def main() -> int:
    if not SHEET_PATH.exists():
        print(f"ERROR: {SHEET_PATH} が見つかりません。先に fetch_sheet.py を実行してください。", file=sys.stderr)
        return 1
    if not POSTS_PATH.exists():
        print(f"ERROR: {POSTS_PATH} が見つかりません。先に fetch_posts.py を実行してください。", file=sys.stderr)
        return 1

    shops, geocoded, new_fetched, matched = build_shops()

    SHOPS_PATH.write_text(json.dumps(shops, ensure_ascii=False, indent=2))
    print(f"\n店舗数: {len(shops)}")
    print(f"地図表示できる店舗 (緯度経度あり): {geocoded}")
    print(f"  うち新規ジオコード: {new_fetched} 件")
    print(f"投稿マッチ: {matched} 件 / {sum(len(s['posts']) for s in shops)} 件")

    from datetime import datetime, timezone, timedelta
    JST = timezone(timedelta(hours=9))
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")

    html = (HTML_TEMPLATE
            .replace("__SHOP_COUNT__", str(len(shops)))
            .replace("__PIN_COUNT__", str(geocoded))
            .replace("__UPDATED_AT__", now)
            .replace("__SHOPS_JSON__", json.dumps(shops, ensure_ascii=False)))
    HTML_PATH.parent.mkdir(parents=True, exist_ok=True)
    HTML_PATH.write_text(html)
    print(f"\n生成: {HTML_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
