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

        # 最新取材日 = マッチした投稿のタイムスタンプ最大値
        ts_vals = [p["timestamp"] for p in shop_posts if p.get("timestamp")]
        latest_ts = max(ts_vals) if ts_vals else None

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
            "faq_parking": (r.get("FAQ_駐車場") or "").strip(),
            "faq_kids": (r.get("FAQ_子供入店") or "").strip(),
            "faq_stroller": (r.get("FAQ_ベビーカー") or "").strip(),
            "faq_takeout": (r.get("FAQ_テイクアウト") or "").strip(),
            "faq_cashless": (r.get("FAQ_キャッシュレス") or "").strip(),
            "faq_pet": (r.get("FAQ_ペット同伴") or "").strip(),
            "max_plays": to_int(r.get("再生数_最大")),
            "google_rating": to_float(r.get("Google評価")),
            "google_reviews": to_int(r.get("Google口コミ数")),
            "latest_ts": latest_ts,
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
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  :root {
    --accent: #ff6b35;
    --bg: #ffffff;
    --text: #1a1a1a;
    --text-sub: #6b6b6b;
    --line: #e8e8e8;
    --shadow: 0 2px 12px rgba(0,0,0,0.14);
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html, body {
    margin: 0; padding: 0; height: 100%; overflow: hidden;
    font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic", sans-serif;
    color: var(--text); background: #e9e9e9;
  }
  #map { position: fixed; inset: 0; z-index: 0; }

  /* ===== 上部フローティングバー ===== */
  #topbar {
    position: fixed; top: 0; left: 0; right: 0; z-index: 1000;
    padding: 10px 12px 0;
    pointer-events: none;
  }
  #topbar .bar {
    background: var(--bg); border-radius: 14px; box-shadow: var(--shadow);
    padding: 8px 12px; pointer-events: auto;
  }
  #topbar .brand {
    display: flex; align-items: baseline; gap: 7px;
    font-size: 15px; font-weight: 700;
  }
  #topbar .brand .ver { font-size: 11px; font-weight: 400; color: var(--text-sub); }
  #topbar .filters { display: flex; gap: 8px; margin-top: 8px; }
  #topbar select {
    flex: 1; min-width: 0; font-size: 13px; padding: 7px 8px;
    border: 1px solid var(--line); border-radius: 9px; background: #fff;
    color: var(--text); -webkit-appearance: none; appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23999'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 9px center;
  }

  /* ===== マーカー ===== */
  .pin {
    width: 18px; height: 18px; background: #ea4335;
    border: 2.5px solid #fff; border-radius: 50% 50% 50% 0;
    transform: rotate(-45deg); box-shadow: 0 1px 4px rgba(0,0,0,0.4);
    cursor: pointer;
  }
  .pin.sel { background: var(--accent); width: 26px; height: 26px; z-index: 999 !important; }

  /* ===== ボトムシート ===== */
  #sheet {
    position: fixed; left: 0; right: 0; bottom: 0; z-index: 900;
    height: 88vh; background: var(--bg);
    border-radius: 16px 16px 0 0; box-shadow: 0 -2px 16px rgba(0,0,0,0.16);
    display: flex; flex-direction: column;
    transition: transform 0.28s cubic-bezier(.4,0,.2,1);
    touch-action: none;
  }
  #sheet-handle { padding: 8px 16px 6px; cursor: grab; flex-shrink: 0; }
  #sheet-handle .grip {
    width: 36px; height: 4px; border-radius: 2px; background: #d2d2d2; margin: 0 auto 8px;
  }
  #sheet-handle .count { font-size: 13px; color: var(--text-sub); text-align: center; }
  #sheet-handle .count b { color: var(--text); font-weight: 700; }
  #sheet-list { flex: 1; overflow-y: auto; -webkit-overflow-scrolling: touch; padding-bottom: 24px; }

  /* ===== リストカード ===== */
  .card {
    display: flex; gap: 11px; padding: 11px 14px;
    border-bottom: 1px solid var(--line); cursor: pointer;
  }
  .card:active { background: #f6f6f6; }
  .card.sel { background: #fff4ef; }
  .card .thumb {
    width: 60px; aspect-ratio: 9/16; flex-shrink: 0;
    object-fit: cover; border-radius: 8px; background: #e4e4e4;
  }
  .card .thumb-wrap { position: relative; flex-shrink: 0; }
  .card .thumb-wrap .play-badge {
    position: absolute; left: 50%; top: 50%; transform: translate(-50%,-50%);
    width: 22px; height: 22px; border-radius: 50%;
    background: rgba(0,0,0,0.5); color: #fff; font-size: 10px;
    display: flex; align-items: center; justify-content: center;
  }
  .card .body { flex: 1; min-width: 0; }
  .card .name { font-size: 14px; font-weight: 700; line-height: 1.35; margin-bottom: 3px; }
  .card .row { font-size: 12px; color: var(--text-sub); margin-bottom: 2px; }
  .card .row .star { color: #f5a623; font-weight: 700; }
  .card .row .plays { color: var(--accent); font-weight: 700; }
  .card .genre { display: inline-block; font-size: 11px; color: #555;
    background: #f0f0f0; border-radius: 6px; padding: 1px 7px; margin-top: 3px; }

  /* ===== 詳細オーバーレイ ===== */
  #detail {
    position: fixed; inset: 0; z-index: 2000; background: var(--bg);
    transform: translateY(100%); transition: transform 0.3s cubic-bezier(.4,0,.2,1);
    display: flex; flex-direction: column; overflow: hidden;
  }
  #detail.open { transform: translateY(0); }
  #detail .d-close {
    position: absolute; top: 12px; right: 12px; z-index: 5;
    width: 36px; height: 36px; border-radius: 50%; border: none;
    background: rgba(0,0,0,0.55); color: #fff; font-size: 20px; cursor: pointer;
    display: flex; align-items: center; justify-content: center;
  }
  #detail .d-scroll { flex: 1; overflow-y: auto; -webkit-overflow-scrolling: touch; }
  #detail .d-media {
    width: 100%; aspect-ratio: 9/16; max-height: 56vh; background: #000;
    display: flex; align-items: center; justify-content: center;
  }
  #detail .d-media video, #detail .d-media img {
    width: 100%; height: 100%; object-fit: contain; background: #000;
  }
  #detail .d-thumbs { display: flex; gap: 6px; padding: 8px 14px 0; }
  #detail .d-thumbs img {
    width: 44px; aspect-ratio: 9/16; object-fit: cover; border-radius: 6px;
    border: 2px solid transparent; cursor: pointer;
  }
  #detail .d-thumbs img.active { border-color: var(--accent); }
  #detail .d-body { padding: 12px 16px 40px; }
  #detail .d-name { font-size: 19px; font-weight: 700; line-height: 1.4; }
  #detail .d-stat { font-size: 14px; margin-top: 7px; }
  #detail .d-stat .star { color: #f5a623; font-weight: 700; }
  #detail .d-stat .plays { color: var(--accent); font-weight: 700; }
  #detail .d-genre { margin-top: 8px; }
  #detail .d-genre span {
    display: inline-block; font-size: 12px; background: #f0f0f0; color: #555;
    border-radius: 7px; padding: 3px 9px; margin: 0 5px 5px 0;
  }
  #detail .d-info { margin-top: 14px; border-top: 1px solid var(--line); padding-top: 12px; }
  #detail .d-info .line { display: flex; gap: 9px; font-size: 13px; margin-bottom: 9px; }
  #detail .d-info .line .ic { width: 18px; flex-shrink: 0; text-align: center; }
  #detail .d-info .line .tx { flex: 1; line-height: 1.5; }
  #detail .d-info .line .tx .lb { color: var(--text-sub); font-size: 11px; display: block; }
  #detail .d-hl {
    margin-top: 12px; background: #fff4ef; border-radius: 10px;
    padding: 10px 12px; font-size: 13px; line-height: 1.6;
  }
  #detail .d-tags { margin-top: 12px; }
  #detail .d-tags span {
    display: inline-block; font-size: 12px; background: #eef3ff; color: #3355aa;
    border-radius: 11px; padding: 3px 10px; margin: 0 5px 5px 0;
  }
  #detail .d-links { margin-top: 16px; }
  #detail .d-links a {
    display: block; text-align: center; text-decoration: none;
    background: var(--accent); color: #fff; font-size: 14px; font-weight: 700;
    border-radius: 10px; padding: 11px; margin-bottom: 8px;
  }
  #detail .d-links a.sub { background: #f0f0f0; color: var(--text); }

  /* Leaflet 既定の attribution を控えめに */
  .leaflet-control-attribution { font-size: 9px; opacity: 0.7; }
</style>
</head>
<body>

<div id="map"></div>

<div id="topbar">
  <div class="bar">
    <div class="brand">🍽️ きたごはんMAP <span class="ver">ver 0.03</span></div>
    <div class="filters">
      <select id="f-area"><option value="">すべてのエリア</option></select>
      <select id="f-genre"><option value="">すべてのジャンル</option></select>
    </div>
  </div>
</div>

<div id="sheet">
  <div id="sheet-handle">
    <div class="grip"></div>
    <div class="count"><b id="cnt">0</b> 店 · 再生数順</div>
  </div>
  <div id="sheet-list"></div>
</div>

<div id="detail">
  <button class="d-close" id="d-close" aria-label="閉じる">×</button>
  <div class="d-scroll" id="d-scroll"></div>
</div>

<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<script>
const SHOPS = __SHOPS_JSON__;
SHOPS.forEach((s, i) => { s.idx = i; });
const UPDATED_AT = "__UPDATED_AT__";

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
function shopPosts(s) {
  return (s.posts || []).filter(p => p.thumbnail_url || p.media_url);
}
function hasVideo(s) {
  return shopPosts(s).some(p => p.media_type === 'VIDEO' && p.media_url);
}

/* ===== 地図 ===== */
const map = L.map('map', { zoomControl: false, attributionControl: true })
  .setView([43.0621, 141.3544], 13);
L.control.zoom({ position: 'bottomright' }).addTo(map);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
  maxZoom: 20, subdomains: 'abcd',
  attribution: '&copy; OpenStreetMap &copy; CARTO'
}).addTo(map);

const withGeo = SHOPS.filter(s => s.lat != null && s.lon != null);
const markersById = {};
let selectedIdx = null;

withGeo.forEach(s => {
  const icon = L.divIcon({
    className: '', html: '<div class="pin"></div>',
    iconSize: [18, 18], iconAnchor: [9, 18]
  });
  const m = L.marker([s.lat, s.lon], { icon }).addTo(map);
  m.on('click', () => selectShop(s.idx, true));
  markersById[s.idx] = m;
});

if (withGeo.length) {
  map.fitBounds(withGeo.map(s => [s.lat, s.lon]), { padding: [40, 40], maxZoom: 14 });
}

/* ===== フィルタ ===== */
const fArea = document.getElementById('f-area');
const fGenre = document.getElementById('f-genre');
[...new Set(withGeo.map(s => s.area).filter(Boolean))].sort()
  .forEach(a => fArea.add(new Option(a, a)));
[...new Set(withGeo.map(s => s.main_genre).filter(Boolean))].sort()
  .forEach(g => fGenre.add(new Option(g, g)));
fArea.addEventListener('change', applyFilter);
fGenre.addEventListener('change', applyFilter);

function visibleShops() {
  const a = fArea.value, g = fGenre.value;
  return withGeo.filter(s =>
    (!a || s.area === a) && (!g || s.main_genre === g)
  );
}
function applyFilter() {
  const vis = visibleShops();
  const visSet = new Set(vis.map(s => s.idx));
  withGeo.forEach(s => {
    const m = markersById[s.idx];
    if (visSet.has(s.idx)) { if (!map.hasLayer(m)) m.addTo(map); }
    else { if (map.hasLayer(m)) map.removeLayer(m); }
  });
  renderList(vis);
  if (vis.length) {
    map.fitBounds(vis.map(s => [s.lat, s.lon]), { padding: [40, 40], maxZoom: 15 });
  }
}

/* ===== リスト ===== */
const sheetList = document.getElementById('sheet-list');
const cntEl = document.getElementById('cnt');

function renderList(shops) {
  const sorted = shops.slice().sort((a, b) => (b.max_plays || 0) - (a.max_plays || 0));
  cntEl.textContent = sorted.length;
  sheetList.innerHTML = '';
  sorted.forEach(s => {
    const posts = shopPosts(s);
    const thumb = posts.length ? (posts[0].thumbnail_url || posts[0].media_url) : '';
    const card = document.createElement('div');
    card.className = 'card';
    card.dataset.idx = s.idx;
    card.innerHTML = `
      <div class="thumb-wrap">
        <img class="thumb" loading="lazy" src="${esc(thumb)}" alt="">
        ${hasVideo(s) ? '<div class="play-badge">▶</div>' : ''}
      </div>
      <div class="body">
        <div class="name">${esc(s.name)}</div>
        <div class="row">
          ${s.google_rating != null ? `<span class="star">★ ${s.google_rating.toFixed(1)}</span> (${s.google_reviews ?? '?'})` : ''}
          ${s.max_plays != null ? ` &nbsp;<span class="plays">▶ ${formatPlays(s.max_plays)}</span>` : ''}
        </div>
        ${s.area ? `<div class="row">${esc(s.area)}</div>` : ''}
        ${s.main_genre ? `<span class="genre">${esc(s.main_genre)}</span>` : ''}
      </div>
    `;
    card.addEventListener('click', () => selectShop(s.idx, false));
    sheetList.appendChild(card);
  });
}

/* ===== 店舗選択 ===== */
function selectShop(idx, fromPin) {
  selectedIdx = idx;
  const s = SHOPS[idx];
  // マーカー強調
  Object.entries(markersById).forEach(([i, m]) => {
    const el = m.getElement && m.getElement();
    if (el) {
      const pin = el.querySelector('.pin');
      if (pin) pin.classList.toggle('sel', +i === idx);
    }
  });
  // 地図移動
  if (s.lat != null && s.lon != null) {
    map.panTo([s.lat, s.lon], { animate: true });
  }
  // リストカード強調＋スクロール
  sheetList.querySelectorAll('.card').forEach(c => {
    const on = +c.dataset.idx === idx;
    c.classList.toggle('sel', on);
    if (on && fromPin) {
      setSheet('peek');
      c.scrollIntoView({ block: 'nearest' });
    }
  });
  if (fromPin) {
    // ピンから来たらワンタップで詳細は出さず、リストで見せる
    return;
  }
  openDetail(idx);
}

/* ===== 詳細オーバーレイ ===== */
const detail = document.getElementById('detail');
const dScroll = document.getElementById('d-scroll');
document.getElementById('d-close').addEventListener('click', closeDetail);

function mediaHTML(post, autoplay) {
  if (post.media_type === 'VIDEO' && post.media_url) {
    return `<video src="${esc(post.media_url)}" poster="${esc(post.thumbnail_url||'')}"
              controls playsinline preload="metadata" ${autoplay ? 'autoplay' : ''}></video>`;
  }
  return `<img src="${esc(post.thumbnail_url || post.media_url)}" alt="">`;
}

function openDetail(idx) {
  const s = SHOPS[idx];
  const posts = shopPosts(s);
  const tags = (s.scene_tags || '').split(',').map(t => t.trim()).filter(Boolean);
  const infoLine = (ic, lb, val) => val
    ? `<div class="line"><div class="ic">${ic}</div><div class="tx"><span class="lb">${lb}</span>${esc(val)}</div></div>` : '';

  let budget = '';
  if (s.budget_lunch) budget += '昼 ¥' + s.budget_lunch;
  if (s.budget_dinner) budget += (budget ? ' / ' : '') + '夜 ¥' + s.budget_dinner;

  dScroll.innerHTML = `
    <div class="d-media" id="d-media">${posts.length ? mediaHTML(posts[0], false) : '<div style="color:#888;font-size:13px">写真なし</div>'}</div>
    ${posts.length > 1 ? `<div class="d-thumbs">${posts.map((p, i) =>
      `<img class="${i===0?'active':''}" data-post="${i}" src="${esc(p.thumbnail_url||p.media_url)}" alt="">`
    ).join('')}</div>` : ''}
    <div class="d-body">
      <div class="d-name">${esc(s.name)}</div>
      <div class="d-stat">
        ${s.google_rating != null ? `<span class="star">★ ${s.google_rating.toFixed(1)}</span> <span style="color:#888">(${s.google_reviews ?? '?'}件のGoogle口コミ)</span>` : ''}
        ${s.max_plays != null ? ` &nbsp; <span class="plays">▶ ${formatPlays(s.max_plays)}回</span>` : ''}
      </div>
      <div class="d-genre">
        ${s.main_genre ? `<span>${esc(s.main_genre)}</span>` : ''}
        ${s.sub_genre ? `<span>${esc(s.sub_genre)}</span>` : ''}
        ${s.visit_count ? `<span>取材${s.visit_count}回</span>` : ''}
      </div>
      <div class="d-info">
        ${infoLine('📍', 'エリア・住所', [s.area, s.address].filter(Boolean).join(' / '))}
        ${infoLine('🕒', '営業時間', s.hours)}
        ${infoLine('🚫', '定休日', s.closed)}
        ${infoLine('💴', '予算', budget)}
        ${infoLine('🚪', '個室', s.private_room)}
        ${infoLine('🚬', '喫煙', s.smoking)}
      </div>
      ${s.highlight ? `<div class="d-hl">💡 ${esc(s.highlight)}</div>` : ''}
      ${tags.length ? `<div class="d-tags">${tags.map(t => `<span># ${esc(t)}</span>`).join('')}</div>` : ''}
      <div class="d-links">
        ${posts.map((p, i) => `<a href="${esc(p.permalink)}" target="_blank" rel="noopener" class="sub">投稿${i+1}を Instagram で見る</a>`).join('')}
      </div>
      <div style="text-align:center;color:#aaa;font-size:11px;margin-top:14px;">最終更新 ${esc(UPDATED_AT)}</div>
    </div>
  `;
  // サムネ切り替え
  dScroll.querySelectorAll('.d-thumbs img').forEach(img => {
    img.addEventListener('click', () => {
      const pi = +img.dataset.post;
      document.getElementById('d-media').innerHTML = mediaHTML(posts[pi], true);
      dScroll.querySelectorAll('.d-thumbs img').forEach((x, i) => x.classList.toggle('active', i === pi));
    });
  });
  dScroll.scrollTop = 0;
  detail.classList.add('open');
}

function closeDetail() {
  detail.classList.remove('open');
  const v = dScroll.querySelector('video');
  if (v) v.pause();
}

/* ===== ボトムシートのドラッグ ===== */
const sheet = document.getElementById('sheet');
const handle = document.getElementById('sheet-handle');
const SHEET_VH = 0.88;
function sheetPx() { return window.innerHeight * SHEET_VH; }
const states = { peek: () => sheetPx() - 188, full: () => 0 };
let sheetState = 'peek';
function setSheet(st) {
  sheetState = st;
  sheet.style.transform = `translateY(${states[st]()}px)`;
}
setSheet('peek');
window.addEventListener('resize', () => setSheet(sheetState));

let dragStartY = 0, dragStartT = 0, dragging = false;
function curT() {
  const m = /translateY\\(([-0-9.]+)px\\)/.exec(sheet.style.transform);
  return m ? parseFloat(m[1]) : states.peek();
}
function onDown(y) { dragging = true; dragStartY = y; dragStartT = curT(); sheet.style.transition = 'none'; }
function onMove(y) {
  if (!dragging) return;
  let t = dragStartT + (y - dragStartY);
  t = Math.max(0, Math.min(states.peek(), t));
  sheet.style.transform = `translateY(${t}px)`;
}
function onUp() {
  if (!dragging) return;
  dragging = false;
  sheet.style.transition = '';
  const t = curT();
  setSheet(t < states.peek() / 2 ? 'full' : 'peek');
}
handle.addEventListener('touchstart', e => onDown(e.touches[0].clientY), { passive: true });
handle.addEventListener('touchmove', e => onMove(e.touches[0].clientY), { passive: true });
handle.addEventListener('touchend', onUp);
handle.addEventListener('mousedown', e => { onDown(e.clientY);
  const mm = e => onMove(e.clientY), mu = () => { onUp(); document.removeEventListener('mousemove', mm); document.removeEventListener('mouseup', mu); };
  document.addEventListener('mousemove', mm); document.addEventListener('mouseup', mu);
});
handle.addEventListener('click', () => { if (!dragging) setSheet(sheetState === 'peek' ? 'full' : 'peek'); });

/* ===== 初期描画 ===== */
renderList(withGeo);
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
