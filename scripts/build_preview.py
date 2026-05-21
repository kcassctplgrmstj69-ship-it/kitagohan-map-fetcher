#!/usr/bin/env python3
"""
data/shops.json を読み込み、検索フィルター付きのテスト版
web/preview.html を生成する。

本番 (index.html) とは別ファイルなので、
  https://<user>.github.io/kitagohan-map-fetcher/preview.html
で確認できる。OK が出たら build_map.py の本テンプレートに昇格させる。

依存: 標準ライブラリのみ
"""
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SHOPS_PATH = ROOT / "data" / "shops.json"
PREVIEW_PATH = ROOT / "web" / "preview.html"

TEMPLATE = """<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="utf-8">
<title>きたごはんMAP (preview)</title>
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<style>
  :root {
    --accent: #ff6b35; --bg: #fff; --text: #1a1a1a; --sub: #6b6b6b;
    --line: #e8e8e8; --shadow: 0 2px 12px rgba(0,0,0,0.14);
  }
  * { box-sizing: border-box; -webkit-tap-highlight-color: transparent; }
  html, body {
    margin: 0; padding: 0; height: 100%; overflow: hidden;
    font-family: -apple-system, BlinkMacSystemFont, "Hiragino Sans", "Yu Gothic", sans-serif;
    color: var(--text); background: #e9e9e9;
  }
  #map { position: fixed; inset: 0; z-index: 0; }

  /* 上部バー */
  #topbar { position: fixed; top: 0; left: 0; right: 0; z-index: 1000; padding: 10px 12px 0; pointer-events: none; }
  #topbar .bar { background: var(--bg); border-radius: 14px; box-shadow: var(--shadow); padding: 8px 10px; pointer-events: auto; }
  #topbar .brand { display: flex; align-items: baseline; gap: 7px; font-size: 15px; font-weight: 700; margin-bottom: 7px; }
  #topbar .brand .ver { font-size: 11px; font-weight: 400; color: var(--sub); }
  .searchrow { display: flex; gap: 7px; }
  #q {
    flex: 1; min-width: 0; font-size: 14px; padding: 8px 10px;
    border: 1px solid var(--line); border-radius: 9px; background: #f6f6f6;
  }
  #btn-filter {
    flex-shrink: 0; font-size: 13px; padding: 0 12px; border: 1px solid var(--line);
    border-radius: 9px; background: #fff; cursor: pointer; position: relative;
    display: flex; align-items: center; gap: 4px;
  }
  #btn-filter .fbadge {
    background: var(--accent); color: #fff; font-size: 10px; font-weight: 700;
    border-radius: 9px; padding: 1px 6px; min-width: 17px; text-align: center;
  }
  .selrow { display: flex; gap: 7px; margin-top: 7px; }
  .selrow select {
    flex: 1; min-width: 0; font-size: 13px; padding: 7px 8px; color: var(--text);
    border: 1px solid var(--line); border-radius: 9px; background: #fff;
    -webkit-appearance: none; appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23999'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 9px center;
  }
  /* 適用中フィルターのチップ */
  #chips { display: flex; gap: 6px; margin-top: 7px; overflow-x: auto; -webkit-overflow-scrolling: touch; }
  #chips:empty { display: none; }
  #chips .chip {
    flex-shrink: 0; font-size: 12px; background: #fff4ef; color: var(--accent);
    border: 1px solid #ffd9c9; border-radius: 14px; padding: 3px 9px;
    display: flex; align-items: center; gap: 4px; cursor: pointer; white-space: nowrap;
  }
  #chips .chip .x { font-weight: 700; }

  /* マーカー */
  .pin { width: 18px; height: 18px; background: #ea4335; border: 2.5px solid #fff;
    border-radius: 50% 50% 50% 0; transform: rotate(-45deg);
    box-shadow: 0 1px 4px rgba(0,0,0,0.4); cursor: pointer; }
  .pin.sel { background: var(--accent); width: 26px; height: 26px; z-index: 999 !important; }

  /* ボトムシート */
  #sheet { position: fixed; left: 0; right: 0; bottom: 0; z-index: 900;
    height: 88vh; background: var(--bg); border-radius: 16px 16px 0 0;
    box-shadow: 0 -2px 16px rgba(0,0,0,0.16); display: flex; flex-direction: column;
    transition: transform 0.28s cubic-bezier(.4,0,.2,1); touch-action: none; }
  #sheet-handle { padding: 8px 14px 6px; cursor: grab; flex-shrink: 0; }
  #sheet-handle .grip { width: 36px; height: 4px; border-radius: 2px; background: #d2d2d2; margin: 0 auto 8px; }
  #sheet-top { display: flex; align-items: center; justify-content: space-between; }
  #sheet-top .count { font-size: 13px; color: var(--sub); }
  #sheet-top .count b { color: var(--text); font-weight: 700; }
  #sort {
    font-size: 12px; padding: 5px 7px; border: 1px solid var(--line);
    border-radius: 8px; background: #fff; color: var(--text);
    -webkit-appearance: none; appearance: none; padding-right: 22px;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23999'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 7px center;
  }
  #sheet-list { flex: 1; overflow-y: auto; -webkit-overflow-scrolling: touch; padding-bottom: 24px; }
  .empty { padding: 40px 20px; text-align: center; color: var(--sub); font-size: 13px; }

  .card { display: flex; gap: 11px; padding: 11px 14px; border-bottom: 1px solid var(--line); cursor: pointer; }
  .card:active { background: #f6f6f6; }
  .card.sel { background: #fff4ef; }
  .card .thumb-wrap { position: relative; flex-shrink: 0; }
  .card .thumb { width: 60px; aspect-ratio: 9/16; object-fit: cover; border-radius: 8px; background: #e4e4e4; display: block; }
  .card .play-badge { position: absolute; left: 50%; top: 50%; transform: translate(-50%,-50%);
    width: 22px; height: 22px; border-radius: 50%; background: rgba(0,0,0,0.5);
    color: #fff; font-size: 10px; display: flex; align-items: center; justify-content: center; }
  .card .body { flex: 1; min-width: 0; }
  .card .name { font-size: 14px; font-weight: 700; line-height: 1.35; margin-bottom: 3px; }
  .card .row { font-size: 12px; color: var(--sub); margin-bottom: 2px; }
  .card .row .star { color: #f5a623; font-weight: 700; }
  .card .row .plays { color: var(--accent); font-weight: 700; }
  .card .genre { display: inline-block; font-size: 11px; color: #555; background: #f0f0f0;
    border-radius: 6px; padding: 1px 7px; margin-top: 3px; }

  /* 絞り込みパネル */
  #panel { position: fixed; inset: 0; z-index: 1500; background: var(--bg);
    transform: translateY(100%); transition: transform 0.3s cubic-bezier(.4,0,.2,1);
    display: flex; flex-direction: column; }
  #panel.open { transform: translateY(0); }
  #panel .p-head { display: flex; align-items: center; justify-content: space-between;
    padding: 14px 16px; border-bottom: 1px solid var(--line); }
  #panel .p-head .t { font-size: 16px; font-weight: 700; }
  #panel .p-head button { background: none; border: none; font-size: 22px; cursor: pointer; color: var(--sub); }
  #panel .p-body { flex: 1; overflow-y: auto; padding: 6px 16px 16px; }
  .fgroup { padding: 14px 0; border-bottom: 1px solid var(--line); }
  .fgroup .flabel { font-size: 13px; font-weight: 700; margin-bottom: 9px; }
  .seg { display: flex; flex-wrap: wrap; gap: 7px; }
  .seg button {
    font-size: 13px; padding: 7px 13px; border: 1px solid var(--line);
    border-radius: 18px; background: #fff; color: var(--text); cursor: pointer;
  }
  .seg button.on { background: var(--accent); color: #fff; border-color: var(--accent); }
  .fgroup select {
    width: 100%; font-size: 14px; padding: 9px 10px; border: 1px solid var(--line);
    border-radius: 9px; background: #fff; color: var(--text);
    -webkit-appearance: none; appearance: none;
    background-image: url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='10' height='6'%3E%3Cpath d='M0 0l5 6 5-6z' fill='%23999'/%3E%3C/svg%3E");
    background-repeat: no-repeat; background-position: right 11px center;
  }
  #panel .p-foot { display: flex; gap: 10px; padding: 12px 16px; border-top: 1px solid var(--line); }
  #panel .p-foot button { font-size: 14px; font-weight: 700; border-radius: 10px; padding: 12px; cursor: pointer; }
  #panel #f-reset { flex: 0 0 90px; background: #f0f0f0; border: none; color: var(--text); }
  #panel #f-apply { flex: 1; background: var(--accent); border: none; color: #fff; }

  /* 詳細オーバーレイ */
  #detail { position: fixed; inset: 0; z-index: 2000; background: var(--bg);
    transform: translateY(100%); transition: transform 0.3s cubic-bezier(.4,0,.2,1);
    display: flex; flex-direction: column; overflow: hidden; }
  #detail.open { transform: translateY(0); }
  #detail .d-close { position: absolute; top: 12px; right: 12px; z-index: 5;
    width: 36px; height: 36px; border-radius: 50%; border: none;
    background: rgba(0,0,0,0.55); color: #fff; font-size: 20px; cursor: pointer;
    display: flex; align-items: center; justify-content: center; }
  #detail .d-scroll { flex: 1; overflow-y: auto; -webkit-overflow-scrolling: touch; }
  #detail .d-media { width: 100%; aspect-ratio: 9/16; max-height: 56vh; background: #000;
    display: flex; align-items: center; justify-content: center; }
  #detail .d-media video, #detail .d-media img { width: 100%; height: 100%; object-fit: contain; background: #000; }
  #detail .d-thumbs { display: flex; gap: 6px; padding: 8px 14px 0; }
  #detail .d-thumbs img { width: 44px; aspect-ratio: 9/16; object-fit: cover; border-radius: 6px;
    border: 2px solid transparent; cursor: pointer; }
  #detail .d-thumbs img.active { border-color: var(--accent); }
  #detail .d-body { padding: 12px 16px 40px; }
  #detail .d-name { font-size: 19px; font-weight: 700; line-height: 1.4; }
  #detail .d-stat { font-size: 14px; margin-top: 7px; }
  #detail .d-stat .star { color: #f5a623; font-weight: 700; }
  #detail .d-stat .plays { color: var(--accent); font-weight: 700; }
  #detail .d-genre { margin-top: 8px; }
  #detail .d-genre span { display: inline-block; font-size: 12px; background: #f0f0f0; color: #555;
    border-radius: 7px; padding: 3px 9px; margin: 0 5px 5px 0; }
  #detail .d-info { margin-top: 14px; border-top: 1px solid var(--line); padding-top: 12px; }
  #detail .d-info .line { display: flex; gap: 9px; font-size: 13px; margin-bottom: 9px; }
  #detail .d-info .line .ic { width: 18px; flex-shrink: 0; text-align: center; }
  #detail .d-info .line .tx { flex: 1; line-height: 1.5; }
  #detail .d-info .line .tx .lb { color: var(--sub); font-size: 11px; display: block; }
  #detail .d-hl { margin-top: 12px; background: #fff4ef; border-radius: 10px; padding: 10px 12px; font-size: 13px; line-height: 1.6; }
  #detail .d-tags { margin-top: 12px; }
  #detail .d-tags span { display: inline-block; font-size: 12px; background: #eef3ff; color: #3355aa;
    border-radius: 11px; padding: 3px 10px; margin: 0 5px 5px 0; }
  #detail .d-links { margin-top: 16px; }
  #detail .d-links a { display: block; text-align: center; text-decoration: none;
    background: #f0f0f0; color: var(--text); font-size: 14px; font-weight: 700;
    border-radius: 10px; padding: 11px; margin-bottom: 8px; }
  .leaflet-control-attribution { font-size: 9px; opacity: 0.7; }
</style>
</head>
<body>

<div id="map"></div>

<div id="topbar">
  <div class="bar">
    <div class="brand">🍽️ きたごはんMAP <span class="ver">ver 0.04 preview</span></div>
    <div class="searchrow">
      <input id="q" type="search" placeholder="店名・キーワードで検索" autocomplete="off">
      <button id="btn-filter">絞り込み<span class="fbadge" id="fbadge" style="display:none">0</span></button>
    </div>
    <div class="selrow">
      <select id="f-area"><option value="">すべてのエリア</option></select>
      <select id="f-genre"><option value="">すべてのジャンル</option></select>
    </div>
    <div id="chips"></div>
  </div>
</div>

<div id="sheet">
  <div id="sheet-handle">
    <div class="grip"></div>
    <div id="sheet-top">
      <div class="count"><b id="cnt">0</b> 店</div>
      <select id="sort">
        <option value="plays">再生数順</option>
        <option value="rating">Google評価順</option>
        <option value="reviews">口コミ数順</option>
        <option value="date">取材日順</option>
      </select>
    </div>
  </div>
  <div id="sheet-list"></div>
</div>

<div id="panel">
  <div class="p-head">
    <div class="t">絞り込み</div>
    <button id="p-close" aria-label="閉じる">×</button>
  </div>
  <div class="p-body">
    <div class="fgroup">
      <div class="flabel">Google評価</div>
      <div class="seg" id="seg-rating">
        <button data-v="0" class="on">指定なし</button>
        <button data-v="4">★4.0以上</button>
        <button data-v="4.5">★4.5以上</button>
      </div>
    </div>
    <div class="fgroup">
      <div class="flabel">予算帯（1人あたり・上限）</div>
      <select id="f-budget">
        <option value="0">指定なし</option>
        <option value="3000">〜3,000円</option>
        <option value="5000">〜5,000円</option>
        <option value="7000">〜7,000円</option>
        <option value="10000">〜10,000円</option>
        <option value="20000">〜20,000円</option>
        <option value="50000">〜50,000円</option>
      </select>
    </div>
    <div class="fgroup">
      <div class="flabel">個室</div>
      <div class="seg" id="seg-room">
        <button data-v="" class="on">指定なし</button>
        <button data-v="yes">あり</button>
        <button data-v="no">なし</button>
      </div>
    </div>
    <div class="fgroup">
      <div class="flabel">喫煙</div>
      <div class="seg" id="seg-smoking">
        <button data-v="" class="on">指定なし</button>
        <button data-v="禁煙">禁煙</button>
        <button data-v="喫煙">喫煙可</button>
        <button data-v="分煙">分煙</button>
      </div>
    </div>
    <div class="fgroup" style="border-bottom:none;">
      <div class="flabel">こだわり条件</div>
      <div class="seg" id="seg-flags">
        <button data-f="video">動画あり</button>
        <button data-f="parking">駐車場</button>
        <button data-f="kids">子供入店OK</button>
        <button data-f="stroller">ベビーカーOK</button>
        <button data-f="takeout">テイクアウト</button>
        <button data-f="cashless">キャッシュレス</button>
        <button data-f="pet">ペット同伴</button>
      </div>
    </div>
  </div>
  <div class="p-foot">
    <button id="f-reset">リセット</button>
    <button id="f-apply"><span id="apply-n">0</span>件を表示</button>
  </div>
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
  return (s || '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
}
function formatPlays(n) {
  if (n == null || isNaN(n)) return '-';
  if (n >= 10000) return (n / 10000).toFixed(1).replace(/\\.0$/, '') + '万';
  return n.toLocaleString();
}
function shopPosts(s) { return (s.posts || []).filter(p => p.thumbnail_url || p.media_url); }
function hasVideo(s) { return shopPosts(s).some(p => p.media_type === 'VIDEO' && p.media_url); }
function shopBudget(s) {
  const d = parseInt((s.budget_dinner||'').replace(/[^0-9]/g,''), 10);
  const l = parseInt((s.budget_lunch||'').replace(/[^0-9]/g,''), 10);
  if (!isNaN(d)) return d;
  if (!isNaN(l)) return l;
  return null;
}
function faqYes(v) {
  v = (v || '').trim();
  if (!v) return false;
  return !/^(なし|不可|×|✕|無|N\\/?A|要確認)/.test(v);
}

/* 地図 */
const map = L.map('map', { zoomControl: false }).setView([43.0621, 141.3544], 13);
L.control.zoom({ position: 'bottomright' }).addTo(map);
L.tileLayer('https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png', {
  maxZoom: 20, subdomains: 'abcd', attribution: '&copy; OpenStreetMap &copy; CARTO'
}).addTo(map);

const withGeo = SHOPS.filter(s => s.lat != null && s.lon != null);
const markersById = {};
withGeo.forEach(s => {
  const icon = L.divIcon({ className: '', html: '<div class="pin"></div>', iconSize: [18,18], iconAnchor: [9,18] });
  const m = L.marker([s.lat, s.lon], { icon }).addTo(map);
  m.on('click', () => selectShop(s.idx, true));
  markersById[s.idx] = m;
});
if (withGeo.length) map.fitBounds(withGeo.map(s => [s.lat, s.lon]), { padding: [40,40], maxZoom: 14 });

/* フィルター状態 */
const F = { q:'', area:'', genre:'', rating:0, budget:0, room:'', smoking:'',
            video:false, parking:false, kids:false, stroller:false, takeout:false, cashless:false, pet:false };
let sortKey = 'plays';

const fArea = document.getElementById('f-area');
const fGenre = document.getElementById('f-genre');
[...new Set(withGeo.map(s => s.area).filter(Boolean))].sort().forEach(a => fArea.add(new Option(a, a)));
[...new Set(withGeo.map(s => s.main_genre).filter(Boolean))].sort().forEach(g => fGenre.add(new Option(g, g)));

function matches(s) {
  if (F.q) {
    const hay = [s.name, s.area, s.main_genre, s.sub_genre, s.scene_tags, s.highlight, s.address]
      .join(' ').toLowerCase();
    if (!hay.includes(F.q.toLowerCase())) return false;
  }
  if (F.area && s.area !== F.area) return false;
  if (F.genre && s.main_genre !== F.genre) return false;
  if (F.rating && !(s.google_rating != null && s.google_rating >= F.rating)) return false;
  if (F.budget) { const b = shopBudget(s); if (b == null || b > F.budget) return false; }
  if (F.room === 'yes' && !/あり|貸切/.test(s.private_room || '')) return false;
  if (F.room === 'no' && !/^なし/.test(s.private_room || '')) return false;
  if (F.smoking && !(s.smoking || '').includes(F.smoking)) return false;
  if (F.video && !hasVideo(s)) return false;
  if (F.parking && !faqYes(s.faq_parking)) return false;
  if (F.kids && !faqYes(s.faq_kids)) return false;
  if (F.stroller && !faqYes(s.faq_stroller)) return false;
  if (F.takeout && !faqYes(s.faq_takeout)) return false;
  if (F.cashless && !faqYes(s.faq_cashless)) return false;
  if (F.pet && !faqYes(s.faq_pet)) return false;
  return true;
}
function sortShops(arr) {
  const k = sortKey;
  return arr.slice().sort((a, b) => {
    if (k === 'plays') return (b.max_plays||0) - (a.max_plays||0);
    if (k === 'rating') return (b.google_rating||0) - (a.google_rating||0);
    if (k === 'reviews') return (b.google_reviews||0) - (a.google_reviews||0);
    if (k === 'date') return (b.latest_ts||'').localeCompare(a.latest_ts||'');
    return 0;
  });
}
function activeCount() {
  let n = 0;
  if (F.rating) n++; if (F.budget) n++; if (F.room) n++; if (F.smoking) n++;
  ['video','parking','kids','stroller','takeout','cashless','pet'].forEach(f => { if (F[f]) n++; });
  return n;
}

/* 描画 */
const sheetList = document.getElementById('sheet-list');
const cntEl = document.getElementById('cnt');
let selectedIdx = null;

function applyAll() {
  const vis = withGeo.filter(matches);
  const visSet = new Set(vis.map(s => s.idx));
  withGeo.forEach(s => {
    const m = markersById[s.idx];
    if (visSet.has(s.idx)) { if (!map.hasLayer(m)) m.addTo(map); }
    else if (map.hasLayer(m)) map.removeLayer(m);
  });
  renderList(sortShops(vis));
  renderChips();
  const ac = activeCount();
  const badge = document.getElementById('fbadge');
  badge.style.display = ac ? 'inline-block' : 'none';
  badge.textContent = ac;
}

function renderList(shops) {
  cntEl.textContent = shops.length;
  sheetList.innerHTML = '';
  if (!shops.length) {
    sheetList.innerHTML = '<div class="empty">条件に合う店舗が見つかりませんでした。<br>絞り込みを緩めてみてください。</div>';
    return;
  }
  shops.forEach(s => {
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
      </div>`;
    card.addEventListener('click', () => selectShop(s.idx, false));
    sheetList.appendChild(card);
  });
}

function renderChips() {
  const chips = document.getElementById('chips');
  chips.innerHTML = '';
  const add = (label, clear) => {
    const c = document.createElement('div');
    c.className = 'chip';
    c.innerHTML = `${esc(label)} <span class="x">×</span>`;
    c.addEventListener('click', () => { clear(); syncControls(); applyAll(); });
    chips.appendChild(c);
  };
  if (F.rating) add('★' + F.rating + '以上', () => F.rating = 0);
  if (F.budget) add('〜' + F.budget.toLocaleString() + '円', () => F.budget = 0);
  if (F.room === 'yes') add('個室あり', () => F.room = '');
  if (F.room === 'no') add('個室なし', () => F.room = '');
  if (F.smoking) add('喫煙: ' + F.smoking, () => F.smoking = '');
  const flagLabel = { video:'動画あり', parking:'駐車場', kids:'子供入店OK',
    stroller:'ベビーカーOK', takeout:'テイクアウト', cashless:'キャッシュレス', pet:'ペット同伴' };
  Object.keys(flagLabel).forEach(f => { if (F[f]) add(flagLabel[f], () => F[f] = false); });
}

/* コントロール → F 同期 */
function syncControls() {
  document.querySelectorAll('#seg-rating button').forEach(b =>
    b.classList.toggle('on', parseFloat(b.dataset.v) === F.rating));
  document.getElementById('f-budget').value = String(F.budget);
  document.querySelectorAll('#seg-room button').forEach(b =>
    b.classList.toggle('on', b.dataset.v === F.room));
  document.querySelectorAll('#seg-smoking button').forEach(b =>
    b.classList.toggle('on', b.dataset.v === F.smoking));
  document.querySelectorAll('#seg-flags button').forEach(b =>
    b.classList.toggle('on', F[b.dataset.f]));
  document.getElementById('apply-n').textContent = withGeo.filter(matches).length;
}

/* イベント */
document.getElementById('q').addEventListener('input', e => { F.q = e.target.value.trim(); applyAll(); });
fArea.addEventListener('change', e => { F.area = e.target.value; applyAll(); });
fGenre.addEventListener('change', e => { F.genre = e.target.value; applyAll(); });
document.getElementById('sort').addEventListener('change', e => { sortKey = e.target.value; applyAll(); });

const panel = document.getElementById('panel');
document.getElementById('btn-filter').addEventListener('click', () => { syncControls(); panel.classList.add('open'); });
document.getElementById('p-close').addEventListener('click', () => panel.classList.remove('open'));
document.getElementById('f-apply').addEventListener('click', () => { panel.classList.remove('open'); applyAll(); });
document.getElementById('f-reset').addEventListener('click', () => {
  F.rating=0; F.budget=0; F.room=''; F.smoking='';
  ['video','parking','kids','stroller','takeout','cashless','pet'].forEach(f => F[f]=false);
  syncControls();
});

document.getElementById('seg-rating').addEventListener('click', e => {
  if (e.target.tagName !== 'BUTTON') return;
  F.rating = parseFloat(e.target.dataset.v); syncControls();
});
document.getElementById('f-budget').addEventListener('change', e => { F.budget = parseInt(e.target.value, 10); syncControls(); });
document.getElementById('seg-room').addEventListener('click', e => {
  if (e.target.tagName !== 'BUTTON') return;
  F.room = e.target.dataset.v; syncControls();
});
document.getElementById('seg-smoking').addEventListener('click', e => {
  if (e.target.tagName !== 'BUTTON') return;
  F.smoking = e.target.dataset.v; syncControls();
});
document.getElementById('seg-flags').addEventListener('click', e => {
  if (e.target.tagName !== 'BUTTON') return;
  const f = e.target.dataset.f; F[f] = !F[f]; syncControls();
});

/* 店舗選択 */
function selectShop(idx, fromPin) {
  selectedIdx = idx;
  const s = SHOPS[idx];
  Object.entries(markersById).forEach(([i, m]) => {
    const el = m.getElement && m.getElement();
    if (el) { const pin = el.querySelector('.pin'); if (pin) pin.classList.toggle('sel', +i === idx); }
  });
  if (s.lat != null && s.lon != null) map.panTo([s.lat, s.lon], { animate: true });
  sheetList.querySelectorAll('.card').forEach(c => {
    const on = +c.dataset.idx === idx;
    c.classList.toggle('sel', on);
    if (on && fromPin) { setSheet('peek'); c.scrollIntoView({ block: 'nearest' }); }
  });
  if (!fromPin) openDetail(idx);
}

/* 詳細 */
const detail = document.getElementById('detail');
const dScroll = document.getElementById('d-scroll');
document.getElementById('d-close').addEventListener('click', closeDetail);
function mediaHTML(post, autoplay) {
  if (post.media_type === 'VIDEO' && post.media_url)
    return `<video src="${esc(post.media_url)}" poster="${esc(post.thumbnail_url||'')}" controls playsinline preload="metadata" ${autoplay?'autoplay':''}></video>`;
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
    ${posts.length > 1 ? `<div class="d-thumbs">${posts.map((p,i) =>
      `<img class="${i===0?'active':''}" data-post="${i}" src="${esc(p.thumbnail_url||p.media_url)}" alt="">`).join('')}</div>` : ''}
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
        ${infoLine('📍','エリア・住所',[s.area,s.address].filter(Boolean).join(' / '))}
        ${infoLine('🕒','営業時間',s.hours)}
        ${infoLine('🚫','定休日',s.closed)}
        ${infoLine('💴','予算',budget)}
        ${infoLine('🚪','個室',s.private_room)}
        ${infoLine('🚬','喫煙',s.smoking)}
        ${infoLine('🅿️','駐車場',s.faq_parking)}
      </div>
      ${s.highlight ? `<div class="d-hl">💡 ${esc(s.highlight)}</div>` : ''}
      ${tags.length ? `<div class="d-tags">${tags.map(t => `<span># ${esc(t)}</span>`).join('')}</div>` : ''}
      <div class="d-links">
        ${posts.map((p,i) => `<a href="${esc(p.permalink)}" target="_blank" rel="noopener">投稿${i+1}を Instagram で見る</a>`).join('')}
      </div>
      <div style="text-align:center;color:#aaa;font-size:11px;margin-top:14px;">最終更新 ${esc(UPDATED_AT)}</div>
    </div>`;
  dScroll.querySelectorAll('.d-thumbs img').forEach(img => {
    img.addEventListener('click', () => {
      const pi = +img.dataset.post;
      document.getElementById('d-media').innerHTML = mediaHTML(posts[pi], true);
      dScroll.querySelectorAll('.d-thumbs img').forEach((x,i) => x.classList.toggle('active', i === pi));
    });
  });
  dScroll.scrollTop = 0;
  detail.classList.add('open');
}
function closeDetail() {
  detail.classList.remove('open');
  const v = dScroll.querySelector('video'); if (v) v.pause();
}

/* ボトムシート ドラッグ */
const sheet = document.getElementById('sheet');
const handle = document.getElementById('sheet-handle');
function sheetPx() { return window.innerHeight * 0.88; }
const states = { peek: () => sheetPx() - 196, full: () => 0 };
let sheetState = 'peek';
function setSheet(st) { sheetState = st; sheet.style.transform = `translateY(${states[st]()}px)`; }
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
  let t = Math.max(0, Math.min(states.peek(), dragStartT + (y - dragStartY)));
  sheet.style.transform = `translateY(${t}px)`;
}
function onUp() {
  if (!dragging) return;
  dragging = false; sheet.style.transition = '';
  setSheet(curT() < states.peek() / 2 ? 'full' : 'peek');
}
handle.addEventListener('touchstart', e => onDown(e.touches[0].clientY), { passive: true });
handle.addEventListener('touchmove', e => onMove(e.touches[0].clientY), { passive: true });
handle.addEventListener('touchend', onUp);
handle.addEventListener('mousedown', e => {
  if (e.target.id === 'sort') return;
  onDown(e.clientY);
  const mm = ev => onMove(ev.clientY), mu = () => { onUp(); document.removeEventListener('mousemove', mm); document.removeEventListener('mouseup', mu); };
  document.addEventListener('mousemove', mm); document.addEventListener('mouseup', mu);
});
handle.addEventListener('click', e => {
  if (e.target.id === 'sort') return;
  if (!dragging) setSheet(sheetState === 'peek' ? 'full' : 'peek');
});

/* 初期描画 */
applyAll();
</script>
</body>
</html>
"""


def main() -> int:
    if not SHOPS_PATH.exists():
        print(f"ERROR: {SHOPS_PATH} が見つかりません。先に build_map.py を実行してください。", file=sys.stderr)
        return 1

    shops = json.loads(SHOPS_PATH.read_text())
    JST = timezone(timedelta(hours=9))
    now = datetime.now(JST).strftime("%Y-%m-%d %H:%M JST")

    html = (TEMPLATE
            .replace("__UPDATED_AT__", now)
            .replace("__SHOPS_JSON__", json.dumps(shops, ensure_ascii=False)))
    PREVIEW_PATH.parent.mkdir(parents=True, exist_ok=True)
    PREVIEW_PATH.write_text(html)
    print(f"生成: {PREVIEW_PATH} ({len(shops)} 店舗)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
