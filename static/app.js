/* Lead Finder — single-page UI */
"use strict";

// ------------------------------------------------------------------ helpers
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const fmt = n => (n ?? 0).toLocaleString();
const sleep = ms => new Promise(r => setTimeout(r, ms));
const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };
const ago = t => { if (!t) return ""; const s = Date.now() / 1000 - t; if (s < 60) return "just now"; if (s < 3600) return Math.floor(s / 60) + " min ago"; if (s < 86400) return Math.floor(s / 3600) + " h ago"; return new Date(t * 1000).toLocaleDateString(); };
const dur = s => { s = Math.round(s || 0); return s < 60 ? s + "s" : s < 3600 ? Math.floor(s / 60) + "m " + (s % 60) + "s" : Math.floor(s / 3600) + "h " + Math.floor(s % 3600 / 60) + "m"; };

async function api(path, opts = {}) {
  const o = { headers: {} , ...opts };
  if (o.body && typeof o.body !== "string") { o.body = JSON.stringify(o.body); o.headers["Content-Type"] = "application/json"; }
  const r = await fetch(path, o);
  let j = null;
  try { j = await r.json(); } catch { /* not json */ }
  if (!r.ok) throw new Error((j && j.error) || `Request failed (${r.status})`);
  return j;
}
const qs = o => Object.entries(o).filter(([, v]) => v !== undefined && v !== null && v !== "" && v !== false).map(([k, v]) => `${k}=${encodeURIComponent(v === true ? 1 : v)}`).join("&");

const ICONS = {
  search: '<circle cx="11" cy="11" r="7"/><path d="M20 20l-3.5-3.5"/>',
  users: '<path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/>',
  clock: '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
  gear: '<circle cx="12" cy="12" r="3"/><path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06A1.65 1.65 0 0 0 4.68 15a1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06A1.65 1.65 0 0 0 9 4.68a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06A1.65 1.65 0 0 0 19.4 9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z"/>',
  moon: '<path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
  pin: '<path d="M21 10c0 7-9 13-9 13S3 17 3 10a9 9 0 0 1 18 0z"/><circle cx="12" cy="10" r="3"/>',
  mail: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
  phone: '<path d="M22 16.9v3a2 2 0 0 1-2.2 2 19.8 19.8 0 0 1-8.6-3.1 19.5 19.5 0 0 1-6-6A19.8 19.8 0 0 1 2.1 4.2 2 2 0 0 1 4.1 2h3a2 2 0 0 1 2 1.7c.1.9.4 1.8.7 2.7a2 2 0 0 1-.5 2.1L8 9.8a16 16 0 0 0 6 6l1.3-1.3a2 2 0 0 1 2.1-.4c.9.3 1.8.6 2.7.7a2 2 0 0 1 1.7 2z"/>',
  globe: '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
  star: '<path d="M12 2l3.1 6.3 6.9 1-5 4.9 1.2 6.8L12 17.8 5.8 21l1.2-6.8-5-4.9 6.9-1z"/>',
  x: '<path d="M18 6L6 18M6 6l12 12"/>',
  check: '<path d="M20 6L9 17l-5-5"/>',
  download: '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4M7 10l5 5 5-5M12 15V3"/>',
  send: '<path d="M22 2L11 13M22 2l-7 20-4-9-9-4z"/>',
  refresh: '<path d="M23 4v6h-6M1 20v-6h6"/><path d="M3.5 9a9 9 0 0 1 14.9-3.4L23 10M1 14l4.6 4.4A9 9 0 0 0 20.5 15"/>',
  trash: '<path d="M3 6h18M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  play: '<path d="M6 4l14 8-14 8z"/>',
  map: '<path d="M1 6v16l7-4 8 4 7-4V2l-7 4-8-4z"/><path d="M8 2v16M16 6v16"/>',
  list: '<path d="M8 6h13M8 12h13M8 18h13M3 6h.01M3 12h.01M3 18h.01"/>',
  copy: '<rect x="9" y="9" width="13" height="13" rx="2"/><path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1"/>',
  bolt: '<path d="M13 2L3 14h9l-1 8 10-12h-9z"/>',
  building: '<rect x="4" y="2" width="16" height="20" rx="2"/><path d="M9 22v-4h6v4M8 6h.01M16 6h.01M12 6h.01M12 10h.01M12 14h.01M16 10h.01M16 14h.01M8 10h.01M8 14h.01"/>',
  external: '<path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 16v-4M12 8h.01"/>',
  alert: '<path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0zM12 9v4M12 17h.01"/>',
  sparkle: '<path d="M12 3l1.9 5.1L19 10l-5.1 1.9L12 17l-1.9-5.1L5 10l5.1-1.9zM19 16l.9 2.1L22 19l-2.1.9L19 22l-.9-2.1L16 19l2.1-.9z"/>',
  bulb: '<path d="M9 18h6M10 22h4M12 2a7 7 0 0 0-4 12.7V17h8v-2.3A7 7 0 0 0 12 2z"/>',
  shield: '<path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"/><path d="M9 12l2 2 4-4"/>',
  layers: '<path d="M12 2l10 5-10 5L2 7z"/><path d="M2 17l10 5 10-5M2 12l10 5 10-5"/>',
  tag: '<path d="M20.6 13.4L13.4 20.6a2 2 0 0 1-2.8 0L2 12V2h10l8.6 8.6a2 2 0 0 1 0 2.8z"/><path d="M7 7h.01"/>',
  facebook: '<path d="M18 2h-3a5 5 0 0 0-5 5v3H7v4h3v8h4v-8h3l1-4h-4V7a1 1 0 0 1 1-1h3z"/>',
  instagram: '<rect x="2" y="2" width="20" height="20" rx="5"/><circle cx="12" cy="12" r="4"/><path d="M17.5 6.5h.01"/>',
  linkedin: '<path d="M16 8a6 6 0 0 1 6 6v7h-4v-7a2 2 0 0 0-4 0v7h-4v-7a6 6 0 0 1 6-6zM2 9h4v12H2z"/><circle cx="4" cy="4" r="2"/>',
  twitter: '<path d="M4 4l16 16M20 4L4 20"/>',
  youtube: '<rect x="2" y="5" width="20" height="14" rx="4"/><path d="M10 9l5 3-5 3z"/>',
  tiktok: '<path d="M9 12a4 4 0 1 0 4 4V2c.5 2.5 2.5 4.5 5 5"/>',
  whatsapp: '<path d="M21 11.5a8.4 8.4 0 0 1-12.5 7.4L3 21l2.1-5.4A8.4 8.4 0 1 1 21 11.5z"/>',
  telegram: '<path d="M22 3L2 11l7 2 2 7 4-5 5 4z"/>',
  pinterest: '<circle cx="12" cy="12" r="9"/><path d="M11 8l-3 13M9 14c3 2 7 0 7-4a4 4 0 0 0-8-1"/>',
  yelp: '<path d="M12 2v10l-6-6M12 12l7 2M12 12l-6 5"/>',
  tripadvisor: '<circle cx="7" cy="13" r="4"/><circle cx="17" cy="13" r="4"/><path d="M3 9h18"/>',
};
const icon = (n, cls = "") => `<svg class="ic ${cls}" viewBox="0 0 24 24">${ICONS[n] || ICONS.info}</svg>`;
function hydrateIcons(root = document) { $$("i[data-i]", root).forEach(i => { i.outerHTML = icon(i.dataset.i); }); }

function toast(msg, kind = "ok") {
  const t = document.createElement("div");
  t.className = "toast " + kind;
  t.innerHTML = icon(kind === "ok" ? "check" : kind === "err" ? "alert" : "info") + `<span>${esc(msg)}</span>`;
  $("#toasts").appendChild(t);
  setTimeout(() => { t.style.opacity = "0"; t.style.transition = ".3s"; setTimeout(() => t.remove(), 300); }, kind === "err" ? 6000 : 3500);
}
async function copy(text) { try { await navigator.clipboard.writeText(text); toast("Copied: " + text); } catch { toast("Could not copy", "err"); } }

function modal(html, onMount) {
  const m = $("#modal");
  m.innerHTML = `<div class="modal-box">${html}</div>`;
  m.classList.remove("hidden");
  hydrateIcons(m);
  const close = () => { m.classList.add("hidden"); m.innerHTML = ""; };
  m.onclick = e => { if (e.target === m || e.target.closest("[data-close]")) close(); };
  onMount && onMount(m, close);
  return close;
}
function confirmBox(title, text, okLabel = "Confirm", danger = false) {
  return new Promise(res => {
    modal(`<div class="mh"><h2>${esc(title)}</h2></div><div class="mb"><p class="sub">${text}</p></div>
      <div class="mf"><button class="btn" data-close>Cancel</button><button class="btn ${danger ? "danger" : "primary"}" id="mOk">${esc(okLabel)}</button></div>`,
      (m, close) => { $("#mOk", m).onclick = () => { close(); res(true); }; m.addEventListener("click", e => { if (e.target === m || e.target.closest("[data-close]")) res(false); }); });
  });
}

const PALETTE = ["#6366f1", "#8b5cf6", "#ec4899", "#f59e0b", "#10b981", "#06b6d4", "#3b82f6", "#ef4444"];
const colorFor = s => PALETTE[[...String(s || "?")].reduce((a, c) => a + c.charCodeAt(0), 0) % PALETTE.length];
const scoreCls = s => s >= 60 ? "s3" : s >= 35 ? "s2" : s >= 15 ? "s1" : "s0";
const hostOf = u => { try { return new URL(u).hostname.replace(/^www\./, ""); } catch { return u; } };

// ------------------------------------------------------------------ theme
function theme(set) {
  let t = set;
  if (!t) { try { t = localStorage.getItem("lf-theme"); } catch { /* storage blocked */ } }
  if (t) document.documentElement.dataset.theme = t;
  const dark = t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  $("#themeBtn").innerHTML = icon(dark ? "sun" : "moon");
  if (set) { try { localStorage.setItem("lf-theme", set); } catch { /* ignore */ } }
  return dark;
}
$("#themeBtn").onclick = () => {
  const dark = document.documentElement.dataset.theme ? document.documentElement.dataset.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  theme(dark ? "light" : "dark");
};
const isDark = () => { const t = document.documentElement.dataset.theme; return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches; };

// ------------------------------------------------------------------ maps
const MAPS = new Set();
// CARTO basemaps now need an API key; OpenStreetMap tiles are free (dark mode = CSS filter, see app.css)
const tileUrl = () => "https://tile.openstreetmap.org/{z}/{x}/{y}.png";
function makeMap(el, opts = {}) {
  if (!window.L) { el.innerHTML = `<div class="empty">Map unavailable offline.</div>`; return null; }
  const m = L.map(el, { zoomControl: true, attributionControl: true, worldCopyJump: true, ...opts }).setView([30, 10], 2);
  m._lfTiles = L.tileLayer(tileUrl(), { maxZoom: 19, attribution: '&copy; OpenStreetMap contributors' }).addTo(m);
  MAPS.add(m);
  return m;
}
function dotIcon(p) {
  const c = p.e ? "#10b981" : p.score >= 20 ? "#6366f1" : "#94a3b8";
  return L.divIcon({ className: "", html: `<div class="mk" style="background:${c}"></div>`, iconSize: [12, 12], iconAnchor: [6, 6] });
}
function plot(map, layerKey, points, fit) {
  if (!map) return;
  if (map[layerKey]) map.removeLayer(map[layerKey]);
  const grp = L.markerClusterGroup ? L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 45, chunkedLoading: true }) : L.layerGroup();
  points.forEach(p => {
    if (p.lat == null) return;
    const mk = L.marker([p.lat, p.lon], { icon: dotIcon(p) });
    mk.bindTooltip(esc(p.name));
    mk.on("click", () => openLead(p.id));
    grp.addLayer(mk);
  });
  grp.addTo(map);
  map[layerKey] = grp;
  if (fit && points.length) {
    const b = L.latLngBounds(points.filter(p => p.lat != null).map(p => [p.lat, p.lon]));
    if (b.isValid()) map.fitBounds(b.pad(0.1), { maxZoom: 14 });
  }
}

// ------------------------------------------------------------------ router
const view = $("#view");
let cleanup = [];
let routeGen = 0; // bumps on every navigation; async views bail out once it moves on
const stale = g => g !== routeGen;
function onLeave(fn) { cleanup.push(fn); }
function route() {
  cleanup.forEach(f => { try { f(); } catch { /* ignore */ } });
  cleanup = [];
  routeGen++;
  MAPS.forEach(m => { try { m.remove(); } catch { /* ignore */ } });
  MAPS.clear();
  const h = location.hash.replace(/^#/, "") || "/";
  const [path, query] = h.split("?");
  const params = Object.fromEntries(new URLSearchParams(query || ""));
  const parts = path.split("/").filter(Boolean);
  const r = parts[0] || "home";
  $$("#nav a").forEach(a => a.classList.toggle("on", a.dataset.r === (r === "run" ? "history" : r)));
  window.scrollTo(0, 0);
  if (r === "home") return Home();
  if (r === "run") return Run(+parts[1]);
  if (r === "leads") return Leads(params);
  if (r === "history") return History();
  if (r === "settings") return Settings();
  view.innerHTML = `<div class="empty">Page not found.</div>`;
}
window.addEventListener("hashchange", route);

// ------------------------------------------------------------------ HOME
const POPULAR = ["All businesses", "Dentists", "Real estate agencies", "Restaurants", "Lawyers", "Accountants", "Hotels", "Gyms", "Hair salons",
  "Car dealers", "Plumbers", "Marketing agencies", "Beauty salons", "Architects", "Clinics", "Cafés"];
// every switch on the home screen: [id, label, hint, default on]
const SRC_OPTS = [
  ["oOverture", "Overture Maps", "Tens of millions of businesses · worldwide · free", true],
  ["oRegistry", "Business registers", "Every registered company · FR · NO · FI · UK", true],
  ["oOsm", "OpenStreetMap", "Community map · worldwide · free", true],
  ["oFsq", "Foursquare", "100M+ places · free Hugging Face token", false],
  ["oGoogle", "Google Places", "Phones & websites · your API key", false],
  ["oYelp", "Yelp", "Ratings & reviews · your API key", false],
];
const DEEP_OPTS = [
  ["oFindWeb", "Find missing websites", "Guesses & verifies sites for businesses without one", true],
  ["oPeople", "Decision makers", "Owners & directors from registers and team pages", true],
  ["oEnrich", "Visit websites", "Emails, phones, socials & people from every site", true],
  ["oFast", "Faster: skip leads with an email", "Visit only sites of leads still missing an email", false],
];
const optPrefs = () => { try { return JSON.parse(localStorage.getItem("lf-opts") || "{}"); } catch { return {}; } };
const saveOptPrefs = () => { try { localStorage.setItem("lf-opts", JSON.stringify(Object.fromEntries([...SRC_OPTS, ...DEEP_OPTS].map(([id]) => [id, $("#" + id).checked])))); } catch { /* ignore */ } };
const optHtml = (list, prefs) => list.map(([id, label, hint, on]) => `<div class="opt" id="w_${id}"><label class="toggle"><input type="checkbox" id="${id}" ${(prefs[id] ?? on) ? "checked" : ""}><span class="sw"></span>${label}</label><small id="n_${id}">${hint}</small></div>`).join("");
const home = { niches: [], locs: [], catalogue: null, settings: null };

async function Home() {
  const g = routeGen;
  view.innerHTML = `
  <section class="hero">
    <h1>Find businesses to reach, anywhere in the world</h1>
    <p class="sub">Pick a business type and a place. Lead Finder maps every matching business, then visits their websites for emails, phones and social profiles.</p>
    <div class="hero-grid">
      <div class="field" id="fNiche"><span>${icon("building")} What businesses?</span>
        <div class="chips" id="nicheChips"><input id="nicheIn" placeholder="e.g. dentists, lawyers, hotels…" autocomplete="off"></div>
        <div class="suggest hidden" id="nicheSug"></div></div>
      <div class="field" id="fLoc"><span>${icon("pin")} Where?</span>
        <div class="chips" id="locChips"><input id="locIn" placeholder="City, region or whole country" autocomplete="off"></div>
        <div class="suggest hidden" id="locSug"></div></div>
      <button class="btn primary" id="goBtn">${icon("search")} Find leads</button>
    </div>
    <div class="quick"><span>Popular:</span>${POPULAR.map(p => `<button data-q="${esc(p)}">${esc(p)}</button>`).join("")}</div>
    <div class="opt-h">${icon("layers")} Where to look</div>
    <div class="opts opts3">${optHtml(SRC_OPTS, optPrefs())}</div>
    <div class="opt-h">${icon("sparkle")} How deep to dig</div>
    <div class="opts">${optHtml(DEEP_OPTS, optPrefs())}</div>
    <div class="row" style="margin-top:12px">
      <div class="opt" style="flex:0 0 260px"><small style="margin:0 0 4px">Maximum leads for this search</small>
        <select id="oMax"><option value="0">No limit — get everything</option><option value="100">100</option><option value="500">500</option><option value="1000">1,000</option><option value="5000">5,000</option><option value="10000">10,000</option><option value="50000">50,000</option></select></div>
      <div class="tip grow">${icon("bulb")}<span><b>Want everything?</b> Pick <b>“All businesses”</b> to pull every business in a place, or search a whole region or country. Overture + the official registers typically find <b>10× more</b> than maps alone; a big city gives tens of thousands.</span></div>
    </div>
  </section>
  <div class="stats" id="stats"></div>
  <div class="row" style="margin-bottom:12px"><h2 class="grow">Recent searches</h2><a class="btn ghost sm" href="#/history">View all</a></div>
  <div class="searches" id="recent"></div>`;

  const nicheIn = $("#nicheIn"), locIn = $("#locIn");
  renderChips();
  $$(".quick button").forEach(b => b.onclick = () => { addNiche(b.dataset.q); nicheIn.focus(); });

  // niche autocomplete
  home.catalogue = home.catalogue || await api("/api/niches").catch(() => []);
  if (stale(g)) return;
  let nIdx = -1;
  const showNicheSug = () => {
    const q = nicheIn.value.trim().toLowerCase();
    const sug = $("#nicheSug");
    if (!q) { sug.classList.add("hidden"); return; }
    const items = home.catalogue.filter(c => c.label.toLowerCase().includes(q) || c.hint.includes(q) || c.key.includes(q)).slice(0, 8);
    const custom = !items.some(i => i.label.toLowerCase() === q);
    sug.innerHTML = items.map((c, i) => `<div data-v="${esc(c.label)}" class="${i === nIdx ? "on" : ""}">${icon("building")}${esc(c.label)}</div>`).join("")
      + (custom ? `<div data-v="${esc(nicheIn.value.trim())}">${icon("search")}Search for “${esc(nicheIn.value.trim())}”<small>custom keyword</small></div>` : "");
    sug.classList.remove("hidden");
    $$("div", sug).forEach(d => d.onmousedown = e => { e.preventDefault(); addNiche(d.dataset.v); nicheIn.value = ""; sug.classList.add("hidden"); });
  };
  nicheIn.oninput = () => { nIdx = -1; showNicheSug(); };
  nicheIn.onkeydown = e => keyNav(e, nicheIn, $("#nicheSug"), v => addNiche(v), () => nIdx, v => { nIdx = v; });
  nicheIn.onblur = () => setTimeout(() => $("#nicheSug")?.classList.add("hidden"), 150);

  // location autocomplete (Nominatim)
  let lIdx = -1, lastQ = "";
  const fetchPlaces = debounce(async () => {
    const q = locIn.value.trim();
    const sug = $("#locSug");
    if (q.length < 2) { sug.classList.add("hidden"); return; }
    lastQ = q;
    const res = await api("/api/places?q=" + encodeURIComponent(q)).catch(() => []);
    if (q !== lastQ || !Array.isArray(res)) return;
    sug.innerHTML = res.map(p => `<div data-v="${esc(p.label)}">${icon("pin")}<span>${esc(p.label)}</span><small>${esc(p.type || "")}</small></div>`).join("")
      || `<div data-v="${esc(q)}">${icon("search")}Use “${esc(q)}”</div>`;
    sug.classList.remove("hidden");
    $$("div", sug).forEach(d => d.onmousedown = e => { e.preventDefault(); addLoc(d.dataset.v); locIn.value = ""; sug.classList.add("hidden"); });
  }, 380);
  locIn.oninput = () => { lIdx = -1; fetchPlaces(); };
  locIn.onkeydown = e => keyNav(e, locIn, $("#locSug"), v => addLoc(v), () => lIdx, v => { lIdx = v; });
  locIn.onblur = () => setTimeout(() => $("#locSug")?.classList.add("hidden"), 150);

  // sources availability
  home.settings = await api("/api/settings").catch(() => ({}));
  if (stale(g)) return;
  // sources that need a key stay off (with a link) until the key is in Settings
  const s = home.settings;
  const needKey = { oGoogle: [s.google_key, "Add a Google key in Settings"], oYelp: [s.yelp_key, "Add a Yelp key in Settings"],
    oFsq: [s.hf_token, "Add a free Hugging Face token in Settings"] };
  Object.entries(needKey).forEach(([id, [key, msg]]) => {
    if (key) return;
    $("#" + id).checked = false; $("#" + id).disabled = true; $("#w_" + id).classList.add("off");
    $("#n_" + id).innerHTML = `<a href="#/settings" style="color:#c7c9ff">${msg}</a>`;
  });
  if (!s.companies_house_key) $("#n_oRegistry").innerHTML = `Every registered company · FR · NO · FI · <a href="#/settings" style="color:#c7c9ff">UK needs a free key</a>`;
  $$(".opts input").forEach(i => i.onchange = saveOptPrefs);

  $("#goBtn").onclick = start;
  loadHomeStats();
}

function keyNav(e, input, sug, add, getIdx, setIdx) {
  const items = $$("div", sug);
  if (e.key === "ArrowDown" || e.key === "ArrowUp") {
    e.preventDefault();
    let i = getIdx() + (e.key === "ArrowDown" ? 1 : -1);
    i = Math.max(0, Math.min(items.length - 1, i));
    setIdx(i);
    items.forEach((d, k) => d.classList.toggle("on", k === i));
  } else if (e.key === "Enter" || e.key === ",") {
    e.preventDefault();
    const i = getIdx();
    const v = (i >= 0 && items[i] && !sug.classList.contains("hidden")) ? items[i].dataset.v : input.value.trim();
    if (v) { add(v); input.value = ""; sug.classList.add("hidden"); setIdx(-1); }
    else if (e.key === "Enter" && home.niches.length && home.locs.length) start();
  } else if (e.key === "Backspace" && !input.value) {
    if (input.id === "nicheIn") home.niches.pop(); else home.locs.pop();
    renderChips();
  } else if (e.key === "Escape") sug.classList.add("hidden");
}
function addNiche(v) { v = v.trim(); if (v && !home.niches.some(n => n.toLowerCase() === v.toLowerCase())) home.niches.push(v); renderChips(); }
function addLoc(v) { v = v.trim(); if (v && !home.locs.includes(v)) home.locs.push(v); renderChips(); }
function renderChips() {
  const short = s => s.split(",").slice(0, 3).join(",");
  const nc = $("#nicheChips"), lc = $("#locChips");
  if (!nc) return;
  $$(".chip", nc).forEach(c => c.remove()); $$(".chip", lc).forEach(c => c.remove());
  home.niches.forEach((n, i) => nc.insertBefore(chipEl(n, () => { home.niches.splice(i, 1); renderChips(); }), $("#nicheIn")));
  home.locs.forEach((n, i) => lc.insertBefore(chipEl(short(n), () => { home.locs.splice(i, 1); renderChips(); }, n), $("#locIn")));
  $("#nicheIn").placeholder = home.niches.length ? "add another…" : "e.g. dentists, lawyers, hotels…";
  $("#locIn").placeholder = home.locs.length ? "add another place…" : "City, region or whole country";
}
function chipEl(text, onX, title) {
  const c = document.createElement("span");
  c.className = "chip"; c.title = title || text;
  c.innerHTML = `${esc(text)}<button title="Remove">×</button>`;
  c.querySelector("button").onclick = onX;
  return c;
}
async function start() {
  const ni = $("#nicheIn").value.trim(), li = $("#locIn").value.trim();
  if (ni) addNiche(ni);
  if (li) addLoc(li);
  $("#nicheIn").value = ""; $("#locIn").value = "";
  if (!home.niches.length) { toast("Add at least one business type", "err"); $("#nicheIn").focus(); return; }
  if (!home.locs.length) { toast("Add at least one place", "err"); $("#locIn").focus(); return; }
  if (!SRC_OPTS.some(([id]) => $("#" + id).checked)) { toast("Switch on at least one place to look (e.g. Overture Maps)", "err"); return; }
  const btn = $("#goBtn"); btn.disabled = true;
  try {
    const r = await api("/api/search", { method: "POST", body: {
      niches: home.niches, locations: home.locs, max_leads: +$("#oMax").value,
      enrich: $("#oEnrich").checked, find_websites: $("#oFindWeb").checked, people: $("#oPeople").checked,
      enrich_missing_only: $("#oFast").checked,
      sources: { overture: $("#oOverture").checked, registry: $("#oRegistry").checked, osm: $("#oOsm").checked,
        fsq: $("#oFsq").checked, google: $("#oGoogle").checked, yelp: $("#oYelp").checked } } });
    home.niches = []; home.locs = [];
    location.hash = "#/run/" + r.id;
    refreshSide();
  } catch (e) { toast(e.message, "err"); btn.disabled = false; }
}
async function loadHomeStats() {
  const [s, list] = await Promise.all([api("/api/stats"), api("/api/searches")]).catch(() => [null, []]);
  if (!s || !$("#stats")) return;
  $("#stats").innerHTML = [
    ["users", "", fmt(s.leads), "Leads collected"], ["mail", "g", fmt(s.emails), "With an email"],
    ["phone", "o", fmt(s.phones), "With a phone"], ["globe", "p", fmt(s.countries), "Countries covered"],
  ].map(([i, c, v, l]) => `<div class="card stat"><div class="si ${c}">${icon(i)}</div><div><b>${v}</b><span>${l}</span></div></div>`).join("");
  $("#recent").innerHTML = list.length ? list.slice(0, 6).map(searchCard).join("")
    : `<div class="card empty" style="grid-column:1/-1">${icon("sparkle")}<div>No searches yet — try <b>“Dentists”</b> in <b>“Belgium”</b> to see it pull a thousand leads in about a minute.</div></div>`;
  bindSearchCards($("#recent"));
}
function statusPill(st) {
  return { running: `<span class="pill run">Running</span>`, queued: `<span class="pill run">Queued</span>`, done: `<span class="pill ok">Done</span>`,
    stopped: `<span class="pill warn">Stopped</span>`, error: `<span class="pill bad">Error</span>` }[st] || `<span class="pill">${esc(st)}</span>`;
}
function searchCard(s) {
  const st = s.stats || {};
  return `<div class="card scard" data-id="${s.id}" data-st="${s.status}">
    <div class="row"><h3 class="grow">${esc(s.niche)}</h3>${statusPill(s.status)}</div>
    <div class="loc">${icon("pin")}${esc(s.location)}</div>
    <div class="nums"><div><b>${fmt(st.leads)}</b>leads</div><div><b>${fmt(st.emails)}</b>emails</div><div><b>${fmt(st.phones)}</b>phones</div><div><b>${fmt(st.websites)}</b>sites</div></div>
    <div class="foot">${icon("clock")}${ago(s.created_at)}${st.pending ? ` · <span style="color:var(--warn)">${fmt(st.pending)} sites not visited yet</span>` : ""}</div></div>`;
}
function bindSearchCards(root) {
  $$(".scard", root).forEach(c => c.onclick = () => {
    location.hash = (c.dataset.st === "running" || c.dataset.st === "queued") ? "#/run/" + c.dataset.id : "#/leads?search=" + c.dataset.id;
  });
}

// ------------------------------------------------------------------ RUN
const RUN_STEPS = [["Locate", "pin"], ["Discover businesses", "search"], ["Find websites", "globe"],
  ["Decision makers", "users"], ["Visit websites", "mail"], ["Done", "check"]];
// which step a phase belongs to, and that step's own progress counters
function runStep(phase, c) {
  const ph = (phase || "").toLowerCase();
  if (ph.startsWith("locat") || ph.startsWith("start")) return [0];
  if (ph.includes("missing websites")) return [2, c.web_done, c.web_total];
  if (ph.includes("decision makers")) return [3, c.people_done, c.people_total];
  if (ph.includes("visiting")) return [4, c.enriched, c.enrich_total];
  return [1];
}

async function Run(id) {
  view.innerHTML = `
  <div class="run-head">
    <div><div class="row" style="gap:10px"><h1 id="rTitle">Search #${id}</h1><span id="rStatus"></span></div>
      <p class="sub" id="rSub"></p></div>
    <div class="row" id="rActions"></div>
  </div>
  <div class="card card-b" style="margin-bottom:16px">
    <div class="steps" id="steps">
      ${RUN_STEPS.map(([s, ic], i) => `<div class="step" data-s="${i}"><div class="dot">${icon(ic)}</div><span>${s}</span></div>`).join("")}
    </div>
    <div class="row"><div class="grow"><div class="bar" id="rBar"><i style="width:0"></i></div></div><span class="hint" id="rPhase"></span></div>
  </div>
  <div class="counters" id="counters"></div>
  <div class="run-grid">
    <div class="card"><div class="card-h"><h2>${icon("map")} Live map</h2><span class="hint" id="mapNote"></span></div><div class="map" id="runMap"></div></div>
    <div class="card"><div class="card-h"><h2>${icon("bolt")} Live feed</h2><a class="btn sm" href="#/leads?search=${id}">Open all leads →</a></div><div class="feed" id="feed"></div></div>
  </div>
  <div class="card" style="margin-top:16px"><div class="card-h"><h2>Activity log</h2></div><div class="log" id="log"></div></div>`;

  const map = makeMap($("#runMap"));
  let alive = true, fitted = false, lastGeo = 0, lastFeed = "";
  onLeave(() => { alive = false; });
  while (alive) {
    let j;
    try { j = await api(`/api/jobs/${id}`); } catch (e) { view.innerHTML = `<div class="empty">${esc(e.message)}</div>`; return; }
    if (!alive) return;
    const p = j.params || {};
    $("#rTitle").textContent = (p.niches || []).join(", ") || "Search #" + id;
    $("#rSub").innerHTML = `${icon("pin")} ${esc((p.locations || []).join(" · "))} · ${dur(j.elapsed)}`;
    $("#rStatus").innerHTML = statusPill(j.status);
    const running = j.status === "running" || j.status === "queued";
    const st = j.stats || {}, c = j.counts || {};
    $("#rActions").innerHTML = running
      ? `<button class="btn danger" id="stopBtn">${icon("stop")} Stop</button>`
      : `${st.pending ? `<button class="btn" id="resumeBtn">${icon("play")} Visit ${fmt(st.pending)} remaining sites</button>` : ""}<a class="btn primary" href="#/leads?search=${id}">${icon("users")} View ${fmt(st.leads)} leads</a>`;
    $("#stopBtn") && ($("#stopBtn").onclick = async () => { await api(`/api/jobs/${id}/cancel`, { method: "POST" }); toast("Stopping…", "info"); });
    $("#resumeBtn") && ($("#resumeBtn").onclick = async () => { await api(`/api/searches/${id}/resume`, { method: "POST" }); toast("Resumed"); refreshSide(); });

    // steps
    const [step, done, total] = running ? runStep(j.phase, c) : [RUN_STEPS.length];
    $$(".step").forEach((s, i) => { s.classList.toggle("done", i < step || (!running && i === RUN_STEPS.length - 1)); s.classList.toggle("on", i === step && running); });
    const bar = $("#rBar");
    const measured = running && total > 0;
    const pct = measured ? Math.round(100 * (done || 0) / total) : 100;
    bar.classList.toggle("indet", running && !measured);
    bar.firstElementChild.style.width = (running && !measured ? 30 : pct) + "%";
    $("#rPhase").textContent = running ? (j.phase || "") + (measured ? ` · ${fmt(done)}/${fmt(total)} (${pct}%)` : "") : (j.phase || j.status);

    const leadsN = Math.max(st.leads || 0, c.leads || 0);
    $("#counters").innerHTML = [
      ["Leads", leadsN, c.brand_new != null ? `${fmt(c.brand_new)} new to your database` : "in this search"],
      ["With email", st.emails, leadsN ? Math.round(100 * (st.emails || 0) / leadsN) + "% of leads" : ""],
      ["With phone", st.phones, leadsN ? Math.round(100 * (st.phones || 0) / leadsN) + "% of leads" : ""],
      ["Websites", st.websites, c.web_found ? `${fmt(c.web_found)} found by the website finder` : c.enrich_total ? `${fmt(c.enriched)} of ${fmt(c.enrich_total)} visited` : (st.pending ? `${fmt(st.pending)} not visited` : "")],
      ["Decision makers", st.people, leadsN ? Math.round(100 * (st.people || 0) / leadsN) + "% of leads" : ""],
    ].map(([l, v, s]) => `<div class="card counter"><span>${l}</span><b>${fmt(v)}</b><small>${s}</small></div>`).join("");

    // feed
    const feedKey = (j.recent || []).map(r => r.id + (r.found || "")).join();
    if (feedKey !== lastFeed) {
      lastFeed = feedKey;
      $("#feed").innerHTML = (j.recent || []).length ? j.recent.map(r => `
        <div class="feed-item" data-id="${r.id}"><div class="av" style="background:${colorFor(r.name)}">${esc((r.name || "?")[0].toUpperCase())}</div>
          <div style="min-width:0"><b>${esc(r.found ? r.found : r.name)}</b><small>${r.found ? "email found on " + esc(r.name) : esc([r.cat, r.city].filter(Boolean).join(" · "))}</small></div>
          <div class="tags">${r.email ? `<span class="pill ok">${icon("mail")}</span>` : ""}${r.web ? `<span class="pill">${icon("globe")}</span>` : ""}</div></div>`).join("")
        : `<div class="empty">${running ? "Waiting for the first results…" : "Nothing new in this run."}</div>`;
      $$(".feed-item", $("#feed")).forEach(d => d.onclick = () => openLead(+d.dataset.id));
    }
    // log
    const logEl = $("#log");
    const atBottom = logEl.scrollHeight - logEl.scrollTop - logEl.clientHeight < 30;
    logEl.innerHTML = (j.log || []).map(l => `<div class="${l.l}"><time>${new Date(l.t * 1000).toLocaleTimeString()}</time><span>${esc(l.m)}</span></div>`).join("");
    if (atBottom) logEl.scrollTop = logEl.scrollHeight;

    // map (every ~5 s while running)
    if (map && (Date.now() - lastGeo > 5000 || !running)) {
      lastGeo = Date.now();
      const pts = await api(`/api/leads/geo?search=${id}`).catch(() => []);
      if (!alive) return;
      plot(map, "_pts", pts, !fitted && pts.length > 0);
      if (pts.length) fitted = true;
      $("#mapNote").textContent = `${fmt(pts.length)} on map · green = has email`;
    }
    if (!running) { refreshSide(); break; }
    await sleep(1500);
  }
}

// ------------------------------------------------------------------ LEADS
const FLAGS = [["has_email", "mail", "Has email"], ["has_phone", "phone", "Has phone"], ["has_website", "globe", "Has website"],
  ["has_social", "instagram", "Has socials"], ["has_people", "users", "Has decision maker"], ["mx_ok", "shield", "Email domain verified"], ["starred", "star", "Starred"], ["not_exported", "send", "Not exported yet"]];
const ls = { f: {}, page: 1, size: 50, sel: new Set(), allMatching: false, data: null, tab: "table", searches: [] };

async function Leads(params) {
  const g = routeGen;
  ls.f = { sort: "score", ...params };
  ls.page = 1; ls.sel.clear(); ls.allMatching = false;
  ls.searches = await api("/api/searches").catch(() => []);
  if (stale(g)) return;
  const cur = ls.searches.find(s => String(s.id) === String(ls.f.search));
  view.innerHTML = `
  <div class="row" style="margin-bottom:16px;align-items:flex-end">
    <div class="grow"><h1>${cur ? esc(cur.niche) : "All leads"}</h1><p class="sub">${cur ? icon("pin") + " " + esc(cur.location) : "Every business you have collected, deduplicated across searches."}</p></div>
    <div class="tabs"><button data-t="table" class="on">${icon("list")} Table</button><button data-t="map">${icon("map")} Map</button></div>
    <button class="btn" id="expBtn">${icon("download")} Export</button>
    <button class="btn primary" id="mbBtn">${icon("send")} Send to MailBlaster</button>
  </div>
  <div class="card">
    <div class="toolbar">
      <div class="search-in">${icon("search")}<input class="input" id="lq" placeholder="Search name, email, domain, city, phone…" value="${esc(ls.f.q || "")}"></div>
      <select class="input" id="lsearch" style="width:auto;max-width:280px"><option value="">All searches</option>${ls.searches.map(s => `<option value="${s.id}" ${String(s.id) === String(ls.f.search) ? "selected" : ""}>${esc(s.niche)} — ${esc(s.location.slice(0, 40))} (${fmt(s.stats.leads)})</option>`).join("")}</select>
      <select class="input" id="lsort" style="width:auto"><option value="score">Best leads first</option><option value="newest">Newest</option><option value="name">Name A–Z</option><option value="city">City</option><option value="rating">Rating</option></select>
    </div>
    <div class="fchips" id="fchips"></div>
    <div class="summary" id="summary"></div>
    <div id="lbody"></div>
  </div>
  <div class="selbar" id="selbar"></div>`;
  $("#lsort").value = ls.f.sort || "score";
  $("#lq").oninput = debounce(() => { ls.f.q = $("#lq").value.trim(); ls.page = 1; loadLeads(); }, 300);
  $("#lsearch").onchange = () => { location.hash = "#/leads" + ($("#lsearch").value ? "?search=" + $("#lsearch").value : ""); };
  $("#lsort").onchange = () => { ls.f.sort = $("#lsort").value; loadLeads(); };
  $$(".tabs button").forEach(b => b.onclick = () => { ls.tab = b.dataset.t; $$(".tabs button").forEach(x => x.classList.toggle("on", x === b)); renderBody(); });
  $("#expBtn").onclick = exportDialog;
  $("#mbBtn").onclick = mailblasterDialog;
  ls.tab = "table";
  await loadLeads();
}

async function loadLeads() {
  const g = routeGen;
  const d = await api("/api/leads?" + qs({ ...ls.f, page: ls.page, size: ls.size })).catch(e => { toast(e.message, "err"); return null; });
  if (!d || stale(g) || !$("#lbody")) return;
  ls.data = d;
  renderFilters(); renderSummary(); renderBody(); renderSelbar();
  $("#navCount") && api("/api/stats").then(s => { $("#navCount").textContent = s.leads ? fmt(s.leads) : ""; });
}

function renderFilters() {
  const fc = ls.data.facets || {};
  const sel = (key, label) => fc[key] && fc[key].length ? `<select class="mini" data-f="${key}"><option value="">${label}</option>${fc[key].map(o => `<option value="${esc(o.v)}" ${ls.f[key] === o.v ? "selected" : ""}>${esc(o.v)} (${fmt(o.n)})</option>`).join("")}</select>` : "";
  $("#fchips").innerHTML = FLAGS.map(([k, i, l]) => `<button class="fchip ${ls.f[k] ? "on" : ""}" data-k="${k}">${icon(i)}${l}</button>`).join("")
    + `<select class="mini" data-f="min_score"><option value="">Any score</option>${[20, 40, 60, 80].map(v => `<option value="${v}" ${String(ls.f.min_score) === String(v) ? "selected" : ""}>Score ${v}+</option>`).join("")}</select>`
    + sel("country", "All countries") + sel("city", "All cities") + sel("category", "All categories")
    + (Object.keys(ls.f).some(k => !["sort", "search", "q"].includes(k)) ? `<button class="btn ghost sm" id="clearF">${icon("x")} Clear filters</button>` : "");
  $$(".fchip", $("#fchips")).forEach(b => b.onclick = () => { ls.f[b.dataset.k] = ls.f[b.dataset.k] ? "" : "1"; if (!ls.f[b.dataset.k]) delete ls.f[b.dataset.k]; ls.page = 1; loadLeads(); });
  $$("select.mini", $("#fchips")).forEach(s => s.onchange = () => { if (s.value) ls.f[s.dataset.f] = s.value; else delete ls.f[s.dataset.f]; ls.page = 1; loadLeads(); });
  $("#clearF") && ($("#clearF").onclick = () => { ls.f = { sort: ls.f.sort, search: ls.f.search, q: ls.f.q }; ls.page = 1; loadLeads(); });
}
function renderSummary() {
  const d = ls.data, c = d.counts;
  $("#summary").innerHTML = `<span><b>${fmt(d.total)}</b> leads</span><span>${icon("mail")} <b>${fmt(c.emails)}</b> emails</span><span>${icon("phone")} <b>${fmt(c.phones)}</b> phones</span><span>${icon("globe")} <b>${fmt(c.websites)}</b> websites</span>`
    + (c.pending ? `<span style="margin-left:auto;color:var(--warn)">${fmt(c.pending)} websites not visited yet</span>${ls.f.search ? `<button class="btn sm" id="resumeL">${icon("play")} Visit them now</button>` : ""}` : "");
  $("#resumeL") && ($("#resumeL").onclick = async () => { await api(`/api/searches/${ls.f.search}/resume`, { method: "POST" }); location.hash = "#/run/" + ls.f.search; });
}

function socialIcons(s, max = 5) {
  const ks = Object.keys(s || {}).slice(0, max);
  return ks.length ? `<div class="soc">${ks.map(k => `<a href="${esc(s[k])}" target="_blank" rel="noopener" title="${k}" onclick="event.stopPropagation()">${icon(k)}</a>`).join("")}</div>` : `<span class="muted">—</span>`;
}

function renderBody() {
  const body = $("#lbody");
  MAPS.forEach(m => { try { m.remove(); } catch { /* ignore */ } }); MAPS.clear();
  if (ls.tab === "map") {
    body.innerHTML = `<div class="map" id="leadsMap" style="height:620px"></div>`;
    const m = makeMap($("#leadsMap"));
    api("/api/leads/geo?" + qs(ls.f)).then(pts => plot(m, "_pts", pts, true));
    return;
  }
  const d = ls.data;
  if (!d.items.length) {
    body.innerHTML = `<div class="empty">${icon("search")}<div>No leads match. ${ls.searches.length ? "Try clearing filters." : `<a href="#/">Run your first search →</a>`}</div></div>`;
    return;
  }
  const pages = Math.max(1, Math.ceil(d.total / ls.size));
  const allOnPage = d.items.every(l => ls.sel.has(l.id));
  body.innerHTML = `<div class="tbl-wrap"><table class="tbl"><thead><tr>
      <th style="width:34px"><input type="checkbox" class="cb" id="selAll" ${allOnPage ? "checked" : ""}></th><th>Score</th><th>Business</th><th>Email</th><th>Phone</th><th>Website</th><th>Location</th><th>Socials</th></tr></thead>
    <tbody>${d.items.map(l => `<tr data-id="${l.id}" class="${ls.sel.has(l.id) || ls.allMatching ? "sel" : ""}">
      <td onclick="event.stopPropagation()"><input type="checkbox" class="cb rowcb" ${ls.sel.has(l.id) || ls.allMatching ? "checked" : ""}></td>
      <td><span class="score ${scoreCls(l.score)}">${l.score}</span></td>
      <td class="nm"><b>${l.starred ? `<span style="color:#f59e0b">★</span> ` : ""}${esc(l.name)}</b><small>${esc(l.category || l.niche)}${l.rating ? ` · ★ ${l.rating}${l.reviews ? ` (${fmt(l.reviews)})` : ""}` : ""}</small>${l.people && l.people.length ? `<small class="who">${icon("users")} ${esc(l.people[0].name)}${l.people[0].role ? " · " + esc(l.people[0].role) : ""}${l.people.length > 1 ? ` +${l.people.length - 1}` : ""}</small>` : ""}</td>
      <td class="cell-e">${l.email ? `${esc(l.email)}<button class="copy" data-c="${esc(l.email)}" title="Copy">${icon("copy")}</button>${l.emails.length > 1 ? ` <span class="pill">+${l.emails.length - 1}</span>` : ""}` : l.enrich_status === "pending" ? `<span class="muted">not visited yet</span>` : `<span class="muted">—</span>`}</td>
      <td style="white-space:nowrap">${l.phone ? esc(l.phone) + `<button class="copy" data-c="${esc(l.phone)}" title="Copy">${icon("copy")}</button>` : `<span class="muted">—</span>`}</td>
      <td class="cell-e">${l.website ? `<a href="${esc(l.website)}" target="_blank" rel="noopener" onclick="event.stopPropagation()">${esc(l.domain || hostOf(l.website))}</a>${l.site_status && l.site_status !== "ok" ? ` <span class="pill warn">${esc(l.site_status)}</span>` : ""}` : `<span class="muted">—</span>`}</td>
      <td>${esc([l.city, l.country_code || l.country].filter(Boolean).join(", ")) || `<span class="muted">—</span>`}</td>
      <td>${socialIcons(l.socials, 4)}</td></tr>`).join("")}</tbody></table></div>
    <div class="pager"><span>Showing ${fmt((ls.page - 1) * ls.size + 1)}–${fmt(Math.min(ls.page * ls.size, d.total))} of ${fmt(d.total)}</span>
      <div class="row" style="gap:6px"><select class="mini" id="psize">${[25, 50, 100, 250, 500].map(n => `<option ${n === ls.size ? "selected" : ""}>${n}</option>`).join("")}</select>
      <button class="btn sm" id="prev" ${ls.page <= 1 ? "disabled" : ""}>← Prev</button><span>Page ${ls.page} / ${fmt(pages)}</span><button class="btn sm" id="next" ${ls.page >= pages ? "disabled" : ""}>Next →</button></div></div>`;
  $$("tbody tr", body).forEach(tr => tr.onclick = e => { if (e.target.closest("a,button")) return; openLead(+tr.dataset.id); });
  $$(".copy", body).forEach(b => b.onclick = e => { e.stopPropagation(); copy(b.dataset.c); });
  $$(".rowcb", body).forEach(cb => cb.onchange = () => {
    const id = +cb.closest("tr").dataset.id;
    if (ls.allMatching) { ls.allMatching = false; d.items.forEach(l => ls.sel.add(l.id)); }
    cb.checked ? ls.sel.add(id) : ls.sel.delete(id);
    cb.closest("tr").classList.toggle("sel", cb.checked);
    renderSelbar();
  });
  $("#selAll").onchange = e => { ls.allMatching = false; d.items.forEach(l => e.target.checked ? ls.sel.add(l.id) : ls.sel.delete(l.id)); renderBody(); renderSelbar(); };
  $("#prev").onclick = () => { ls.page--; loadLeads(); };
  $("#next").onclick = () => { ls.page++; loadLeads(); };
  $("#psize").onchange = e => { ls.size = +e.target.value; ls.page = 1; loadLeads(); };
}

function selCount() { return ls.allMatching ? ls.data.total : ls.sel.size; }
function selPayload() { return ls.allMatching ? { all: true, filters: ls.f } : { ids: [...ls.sel] }; }
function renderSelbar() {
  const bar = $("#selbar");
  if (!bar) return;
  const n = selCount();
  bar.classList.toggle("show", n > 0);
  if (!n) return;
  const canAll = !ls.allMatching && ls.data.total > ls.sel.size && ls.data.items.every(l => ls.sel.has(l.id));
  bar.innerHTML = `<b>${fmt(n)} selected</b>${canAll ? `<button class="btn sm" id="sAll">Select all ${fmt(ls.data.total)}</button>` : ""}
    <button class="btn sm" id="sExp">${icon("download")} Export</button><button class="btn sm" id="sMb">${icon("send")} MailBlaster</button>
    <button class="btn sm" id="sRe">${icon("refresh")} Re-check sites</button><button class="btn sm" id="sDel">${icon("trash")} Delete</button>
    <button class="btn sm" id="sX" title="Clear selection">${icon("x")}</button>`;
  $("#sAll") && ($("#sAll").onclick = () => { ls.allMatching = true; renderBody(); renderSelbar(); });
  $("#sX").onclick = () => { ls.sel.clear(); ls.allMatching = false; renderBody(); renderSelbar(); };
  $("#sExp").onclick = () => exportDialog(true);
  $("#sMb").onclick = () => mailblasterDialog(true);
  $("#sRe").onclick = async () => {
    try { const r = await api("/api/leads/recheck", { method: "POST", body: selPayload() }); toast("Re-checking websites…"); location.hash = "#/run/" + r.id; }
    catch (e) { toast(e.message, "err"); }
  };
  $("#sDel").onclick = async () => {
    if (!await confirmBox("Delete leads?", `This permanently removes <b>${fmt(n)}</b> leads from your database.`, "Delete", true)) return;
    const r = await api("/api/leads/delete", { method: "POST", body: selPayload() });
    toast(`Deleted ${fmt(r.deleted)} leads`); ls.sel.clear(); ls.allMatching = false; loadLeads();
  };
}

function exportDialog(selected) {
  const useSel = selected === true && selCount() > 0;
  const n = useSel ? selCount() : ls.data.total;
  modal(`<div class="mh"><h2>Export ${fmt(n)} leads</h2><p class="sub">${useSel ? "Your selection" : "Everything matching the current filters"}.</p></div>
    <div class="mb"><label class="toggle" style="margin:6px 0 12px"><input type="checkbox" id="xOnly"><span class="sw"></span>Only leads with an email</label>
    <div class="row"><button class="btn grow" id="xCsv">${icon("download")} CSV (Excel, Sheets, CRMs)</button><button class="btn primary grow" id="xXlsx">${icon("download")} Excel .xlsx</button></div></div>
    <div class="mf"><button class="btn ghost" data-close>Close</button></div>`, (m, close) => {
    const go = fmtx => {
      const f = useSel && !ls.allMatching ? { ids: [...ls.sel].join(","), sort: ls.f.sort } : ls.f;
      location.href = "/api/export?" + qs({ ...f, fmt: fmtx, only_email: $("#xOnly", m).checked ? 1 : "" });
      toast("Export started"); close();
    };
    $("#xCsv", m).onclick = () => go("csv"); $("#xXlsx", m).onclick = () => go("xlsx");
  });
}

async function mailblasterDialog(selected) {
  const info = await api("/api/mailblaster").catch(() => ({ found: false }));
  if (!info.found) { toast("MailBlaster database not found — set its path in Settings", "err"); return; }
  const useSel = selected === true && selCount() > 0;
  const n = useSel ? selCount() : ls.data.total;
  const cur = ls.searches.find(s => String(s.id) === String(ls.f.search));
  const def = cur ? `${cur.niche} — ${cur.location}`.slice(0, 60) : "Lead Finder " + new Date().toISOString().slice(0, 10);
  modal(`<div class="mh"><h2>Send to MailBlaster</h2><p class="sub">${fmt(n)} leads → contacts in a MailBlaster group. Leads without an email are skipped; unsubscribed/bounced addresses stay suppressed.</p></div>
    <div class="mb"><label class="lbl">Group</label>
      <input class="input" id="mbGroup" list="mbGroups" value="${esc(def)}"><datalist id="mbGroups">${(info.groups || []).map(g => `<option value="${esc(g.name)}">${fmt(g.n)} contacts</option>`).join("")}</datalist>
      <p class="hint">Type a new name to create a group, or pick an existing one.</p>
      <label class="toggle" style="margin-top:10px"><input type="checkbox" id="mbAll"><span class="sw"></span>Add every email found per business (not just the best one)</label>
      <label class="toggle" style="margin-top:10px"><input type="checkbox" id="mbPeople" checked><span class="sw"></span>Also add decision makers as named contacts (published or mailbox-verified emails only)</label>
      <p class="hint" style="margin-top:12px">${icon("info")} Database: ${esc(info.path)}</p></div>
    <div class="mf"><button class="btn" data-close>Cancel</button><button class="btn primary" id="mbGo">${icon("send")} Send</button></div>`, (m, close) => {
    $("#mbGo", m).onclick = async () => {
      $("#mbGo", m).disabled = true;
      try {
        const body = { ...(useSel ? selPayload() : { all: true, filters: ls.f }), group: $("#mbGroup", m).value, all_emails: $("#mbAll", m).checked, with_people: $("#mbPeople", m).checked };
        const r = await api("/api/export/mailblaster", { method: "POST", body });
        close();
        modal(`<div class="mh"><h2>${icon("check")} Sent to “${esc(r.group)}”</h2></div><div class="mb">
          <p><b>${fmt(r.added)}</b> new contacts added, <b>${fmt(r.updated)}</b> existing contacts updated.</p>
          ${r.skipped_no_email ? `<p class="hint">${fmt(r.skipped_no_email)} leads had no email and were skipped.</p>` : ""}
          ${r.suppressed ? `<p class="hint">${fmt(r.suppressed)} were already unsubscribed/bounced and stay suppressed.</p>` : ""}
          <p class="hint">Open MailBlaster → Contacts to see the group (refresh if it is open).</p></div>
          <div class="mf"><button class="btn primary" data-close>Done</button></div>`);
        loadLeads();
      } catch (e) { toast(e.message, "err"); $("#mbGo", m).disabled = false; }
    };
  });
}

function peopleSection(d) {
  if (!d.people || !d.people.length) return "";
  const badge = p => p.email_status === "published" ? `<span class="pill valid">published</span>`
    : p.email_check === "valid" ? `<span class="pill valid">guess · mailbox exists</span>`
    : p.email_check === "catch_all" ? `<span class="pill guess">guess · server accepts all</span>`
    : p.email_status === "guessed" ? `<span class="pill guess">guess</span>` : "";
  return `<div class="sec"><h4>Decision makers</h4>${d.people.map(p => `<div class="person">
    <div class="av" style="background:${colorFor(p.name)}">${esc(p.name.split(" ").map(w => w[0]).slice(0, 2).join("").toUpperCase())}</div>
    <div style="min-width:0"><b>${esc(p.name)}</b><small>${esc([p.role, p.source].filter(Boolean).join(" · "))}</small>
      ${p.email ? `<div class="pe"><a href="mailto:${esc(p.email)}">${esc(p.email)}</a> ${badge(p)}</div>` : ""}</div>
    ${p.email ? `<button class="copy" data-c="${esc(p.email)}" title="Copy">${icon("copy")}</button>` : "<span></span>"}</div>`).join("")}</div>`;
}
// ------------------------------------------------------------------ LEAD DRAWER
async function openLead(id) {
  const d = await api("/api/leads/" + id).catch(() => null);
  if (!d) return;
  const dr = $("#drawer"), p = $("#drawerPanel");
  const kv = (ic, v, extra = "") => `<div class="kv">${icon(ic)}<div class="v">${v}</div>${extra}</div>`;
  const emails = d.emails.length ? d.emails : (d.email ? [d.email] : []);
  p.innerHTML = `
    <div class="dh"><div class="row"><span class="score ${scoreCls(d.score)}">${d.score}</span><span class="pill">${esc(d.category || d.niche || "business")}</span>
      <span class="grow"></span><button class="icon-btn" id="dStar" title="Star">${icon("star")}</button><button class="icon-btn" data-close title="Close">${icon("x")}</button></div>
      <h2>${esc(d.name)}</h2><p class="sub">${esc([d.city, d.country].filter(Boolean).join(", "))}</p></div>
    <div class="db">
      <div class="sec"><h4>Contact</h4>
        ${emails.map((e, i) => kv("mail", `<a href="mailto:${esc(e)}">${esc(e)}</a>`, `${i === 0 ? `<span class="pill ok tag">best</span>` : ""}${i === 0 && d.mx_ok === 1 ? `<span class="pill tag" title="The email domain accepts mail">MX ✓</span>` : ""}<button class="copy" data-c="${esc(e)}">${icon("copy")}</button>`)).join("")
          || kv("mail", `<span class="muted">${d.enrich_status === "pending" ? "Website not visited yet" : d.website ? "No public email on the website" : "No website, so no email to find"}</span>`)}
        ${(d.phones.length ? d.phones : d.phone ? [d.phone] : []).map(ph => kv("phone", `<a href="tel:${esc(ph)}">${esc(ph)}</a>`, `<button class="copy" data-c="${esc(ph)}">${icon("copy")}</button>`)).join("") || kv("phone", `<span class="muted">No phone</span>`)}
        ${d.website ? kv("globe", `<a href="${esc(d.website)}" target="_blank" rel="noopener">${esc(d.website)}</a>`, d.site_status && d.site_status !== "ok" ? `<span class="pill warn tag">${esc(d.site_status)}</span>` : "") : ""}
        ${d.contact_page ? kv("external", `<a href="${esc(d.contact_page)}" target="_blank" rel="noopener">Contact page</a>`) : ""}
      </div>
      ${peopleSection(d)}
      ${Object.keys(d.socials).length ? `<div class="sec"><h4>Social profiles</h4>${Object.entries(d.socials).map(([k, u]) => kv(ICONS[k] ? k : "globe", `<a href="${esc(u)}" target="_blank" rel="noopener">${esc(u.replace(/^https?:\/\/(www\.)?/, ""))}</a>`)).join("")}</div>` : ""}
      <div class="sec"><h4>Location</h4>${d.address ? kv("pin", esc(d.address)) : ""}${d.lat != null ? `<div class="dmap" id="dmap"></div>` : ""}</div>
      <div class="sec"><h4>Details</h4>
        ${d.title ? kv("info", esc(d.title)) : ""}${d.description ? kv("tag", esc(d.description)) : ""}
        ${d.rating ? kv("star", `${d.rating} ★${d.reviews ? ` · ${fmt(d.reviews)} reviews` : ""}`) : ""}${d.hours ? kv("clock", esc(d.hours)) : ""}
        ${d.legal_name && d.legal_name !== d.name ? kv("building", "Legal name: " + esc(d.legal_name)) : ""}
        ${d.company_id ? kv("tag", "Company number: " + esc(d.company_id)) : ""}
        ${d.employees ? kv("users", "Employees: " + esc(d.employees)) : ""}${d.founded ? kv("clock", "Founded: " + esc(d.founded)) : ""}
        ${d.website_src && d.website_src !== "listing" && d.website ? kv("globe", "Website found by: " + esc({ guessed: "the website finder (domain check)", search: "web search" }[d.website_src] || d.website_src)) : ""}
        ${kv("layers", "Sources: " + esc(d.sources.join(", ")) + (d.maps_url ? ` · <a href="${esc(d.maps_url)}" target="_blank" rel="noopener">view listing</a>` : ""))}
        ${kv("clock", "Found in: " + d.searches.map(s => `<a href="#/leads?search=${s.id}">${esc(s.niche)} · ${esc(s.location.slice(0, 30))}</a>`).join(", "))}
      </div>
      <div class="sec"><h4>Notes</h4><textarea class="input" id="dNote" rows="3" placeholder="Private note…">${esc(d.note)}</textarea></div>
      <div class="row">${d.website ? `<button class="btn" id="dRe">${icon("refresh")} Re-check website</button>` : ""}<button class="btn danger" id="dDel">${icon("trash")} Delete</button></div>
    </div>`;
  dr.classList.add("open");
  const setStar = on => { $("#dStar").style.color = on ? "#f59e0b" : ""; $("#dStar svg").style.fill = on ? "#f59e0b" : "none"; };
  setStar(d.starred);
  $("#dStar").onclick = async () => { d.starred = d.starred ? 0 : 1; setStar(d.starred); await api("/api/leads/" + id, { method: "PATCH", body: { starred: d.starred } }); };
  $("#dNote").onchange = () => api("/api/leads/" + id, { method: "PATCH", body: { note: $("#dNote").value } }).then(() => toast("Note saved"));
  $$(".copy", p).forEach(b => b.onclick = () => copy(b.dataset.c));
  $("#dRe") && ($("#dRe").onclick = async () => { const r = await api("/api/leads/recheck", { method: "POST", body: { ids: [id] } }); closeDrawer(); location.hash = "#/run/" + r.id; });
  $("#dDel").onclick = async () => { await api("/api/leads/delete", { method: "POST", body: { ids: [id] } }); closeDrawer(); toast("Lead deleted"); if (ls.data && location.hash.startsWith("#/leads")) loadLeads(); };
  if (d.lat != null && window.L) {
    setTimeout(() => {
      const m = L.map($("#dmap"), { zoomControl: false, attributionControl: false }).setView([d.lat, d.lon], 16);
      L.tileLayer(tileUrl(), { maxZoom: 19 }).addTo(m);
      L.marker([d.lat, d.lon], { icon: dotIcon({ e: !!d.email, score: d.score }) }).addTo(m);
      dr._map = m;
    }, 260);
  }
}
function closeDrawer() { const dr = $("#drawer"); dr.classList.remove("open"); if (dr._map) { dr._map.remove(); dr._map = null; } }
$("#drawer").addEventListener("click", e => { if (e.target.closest("[data-close]")) closeDrawer(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") { closeDrawer(); $("#modal").classList.add("hidden"); } });

// ------------------------------------------------------------------ HISTORY
async function History() {
  view.innerHTML = `<div class="row" style="margin-bottom:18px"><div class="grow"><h1>Searches</h1><p class="sub">Every search you have run. Leads are shared across searches — the same business is never stored twice.</p></div><a class="btn primary" href="#/">${icon("search")} New search</a></div><div id="hist"></div>`;
  const g = routeGen;
  const list = await api("/api/searches").catch(() => []);
  if (stale(g)) return;
  if (!list.length) { $("#hist").innerHTML = `<div class="card empty">${icon("clock")}<div>No searches yet. <a href="#/">Start one →</a></div></div>`; return; }
  $("#hist").innerHTML = `<div class="card"><div class="tbl-wrap"><table class="tbl"><thead><tr><th>Search</th><th>Status</th><th>Leads</th><th>Emails</th><th>Phones</th><th>Websites</th><th>When</th><th></th></tr></thead><tbody>
    ${list.map(s => `<tr data-id="${s.id}" data-st="${s.status}"><td class="nm"><b>${esc(s.niche)}</b><small>${esc(s.location)}</small></td><td>${statusPill(s.status)}</td>
      <td><b>${fmt(s.stats.leads)}</b></td><td>${fmt(s.stats.emails)}</td><td>${fmt(s.stats.phones)}</td><td>${fmt(s.stats.websites)}${s.stats.pending ? ` <span class="pill warn" title="Websites not visited yet">${fmt(s.stats.pending)} left</span>` : ""}</td>
      <td class="muted">${ago(s.created_at)}</td>
      <td style="white-space:nowrap" onclick="event.stopPropagation()"><a class="btn sm" href="#/run/${s.id}">Run log</a>
        ${s.stats.pending && s.status !== "running" ? `<button class="btn sm" data-resume="${s.id}">${icon("play")} Resume</button>` : ""}
        <button class="btn sm danger" data-del="${s.id}">${icon("trash")}</button></td></tr>`).join("")}</tbody></table></div></div>`;
  $$("#hist tbody tr").forEach(tr => tr.onclick = () => { location.hash = tr.dataset.st === "running" ? "#/run/" + tr.dataset.id : "#/leads?search=" + tr.dataset.id; });
  $$("[data-resume]").forEach(b => b.onclick = async () => { await api(`/api/searches/${b.dataset.resume}/resume`, { method: "POST" }); location.hash = "#/run/" + b.dataset.resume; });
  $$("[data-del]").forEach(b => b.onclick = () => {
    modal(`<div class="mh"><h2>Delete this search?</h2></div><div class="mb"><label class="toggle"><input type="checkbox" id="delLeads"><span class="sw"></span>Also delete its leads (those not found by any other search)</label></div>
      <div class="mf"><button class="btn" data-close>Cancel</button><button class="btn danger" id="delGo">Delete</button></div>`, (m, close) => {
      $("#delGo", m).onclick = async () => { await api(`/api/searches/${b.dataset.del}?leads=${$("#delLeads", m).checked ? 1 : 0}`, { method: "DELETE" }); close(); toast("Search deleted"); History(); };
    });
  });
}

// ------------------------------------------------------------------ SETTINGS
async function Settings() {
  const g = routeGen;
  const s = await api("/api/settings").catch(e => { toast(e.message, "err"); return null; });
  if (!s || stale(g)) return;
  view.innerHTML = `<h1>Settings</h1><p class="sub" style="margin-bottom:20px">Everything is stored on this PC in <code>${esc(s.data_dir)}</code>.</p>
  <div class="set-grid">
    <div class="card"><div class="card-h"><h2>Data sources</h2></div><div class="card-b">
      <div class="src-note">${icon("check")} Built in, free, no key: <b>Overture Maps</b> (tens of millions of businesses worldwide), <b>OpenStreetMap</b>, and the official business registers of <b>France, Norway and Finland</b>.</div>
      <div><label class="lbl">Google Places API key <span class="hint">(optional — more businesses + websites + ratings)</span></label>
        <div class="keyrow"><input class="input" id="gKey" type="password" value="${esc(s.google_key)}" placeholder="AIza…"><button class="btn" data-test="google">Test</button></div>
        <p class="hint">Create one in Google Cloud Console → enable “Places API (New)”. Google bills per request after its free monthly credit; the budget below caps each search.</p></div>
      <div><label class="lbl">Google requests per search (budget)</label><input class="input" id="gBud" type="number" min="1" value="${esc(s.google_budget)}"></div>
      <div><label class="lbl">Yelp Fusion API key <span class="hint">(optional — ratings & reviews, best in US/UK/EU cities)</span></label>
        <div class="keyrow"><input class="input" id="yKey" type="password" value="${esc(s.yelp_key)}" placeholder="Bearer key"><button class="btn" data-test="yelp">Test</button></div></div>
      <div><label class="lbl">Yelp requests per search (budget)</label><input class="input" id="yBud" type="number" min="1" value="${esc(s.yelp_budget)}"></div>
      <div><label class="lbl">Companies House API key <span class="hint">(free — every UK company + its directors)</span></label>
        <div class="keyrow"><input class="input" id="chKey" type="password" value="${esc(s.companies_house_key)}" placeholder="REST API key"><button class="btn" data-test="companies_house">Test</button></div>
        <p class="hint">Register at developer.company-information.service.gov.uk → create an application → REST API key.</p></div>
      <div><label class="lbl">Hugging Face token <span class="hint">(free — unlocks Foursquare Open Places, 100M+ places)</span></label>
        <div class="keyrow"><input class="input" id="hfKey" type="password" value="${esc(s.hf_token)}" placeholder="hf_…"><button class="btn" data-test="hf">Test</button></div>
        <p class="hint">huggingface.co → Settings → Access tokens (read). Then open the fsq-os-places dataset page once and accept its terms.</p></div>
      <div><label class="lbl">Brave Search API key <span class="hint">(optional — finds websites the domain guesser misses)</span></label>
        <div class="keyrow"><input class="input" id="brKey" type="password" value="${esc(s.brave_key)}" placeholder="BSA…"><button class="btn" data-test="brave">Test</button></div>
        <p class="hint">api-dashboard.search.brave.com — includes a free monthly allowance.</p></div>
    </div></div>
    <div>
    <div class="card"><div class="card-h"><h2>Website visits</h2></div><div class="card-b">
      <div><label class="lbl">Websites visited at the same time</label><input class="input" id="wk" type="number" min="2" max="48" value="${esc(s.workers)}"><p class="hint">Higher is faster; 16–32 suits most connections.</p></div>
      <div><label class="lbl">Pages read per website</label><input class="input" id="pp" type="number" min="1" max="15" value="${esc(s.pages_per_site)}"><p class="hint">Home page + contact / about / imprint / team pages.</p></div>
      <div><label class="lbl">Timeout per page (seconds)</label><input class="input" id="to" type="number" min="5" max="40" value="${esc(s.site_timeout)}"></div>
      <div><label class="lbl">Website finder: max businesses per search</label><input class="input" id="wfMax" type="number" min="0" value="${esc(s.webfind_max)}"><p class="hint">Businesses with no website on file get a verified domain check. 0 turns it off.</p></div>
      <div><label class="lbl">Overture: minimum confidence (0–1)</label><input class="input" id="ovConf" type="number" min="0" max="1" step="0.05" value="${esc(s.overture_min_conf)}"><p class="hint">Lower = more places (some may be closed); higher = only well-confirmed ones. 0.35 is a good balance.</p></div>
      <label class="toggle"><input type="checkbox" id="vfy" ${s.verify_guesses === "1" ? "checked" : ""}><span class="sw"></span>Check guessed decision-maker emails with the mail server</label>
      <p class="hint" style="margin-top:-6px">Nothing is sent — the server is only asked if the mailbox exists. Kept to guessed addresses so your IP stays clean.</p>
    </div></div>
    <div class="card" style="margin-top:16px"><div class="card-h"><h2>MailBlaster</h2></div><div class="card-b">
      <div><label class="lbl">MailBlaster database</label><input class="input" id="mbPath" value="${esc(s.mailblaster_db)}" placeholder="${esc(s.mailblaster_detected || "auto-detect")}">
      <p class="hint">${s.mailblaster_detected ? icon("check") + " Using " + esc(s.mailblaster_detected) : "Not found — paste the path to mailblaster.db"}. Leave empty to auto-detect.</p></div>
    </div></div>
    </div>
  </div>
  <div class="row" style="margin-top:18px"><button class="btn primary big" id="saveS">${icon("check")} Save settings</button></div>`;
  $$("[data-test]").forEach(b => b.onclick = async () => {
    const key = ({ google: $("#gKey"), yelp: $("#yKey"), companies_house: $("#chKey"), hf: $("#hfKey"), brave: $("#brKey") }[b.dataset.test]).value;
    if (!key) { toast("Paste a key first", "err"); return; }
    b.disabled = true; b.textContent = "Testing…";
    const r = await api("/api/settings/test", { method: "POST", body: { which: b.dataset.test, key } }).catch(e => ({ ok: false, msg: e.message }));
    b.disabled = false; b.textContent = "Test";
    toast(r.msg, r.ok ? "ok" : "err");
  });
  $("#saveS").onclick = async () => {
    await api("/api/settings", { method: "POST", body: { google_key: $("#gKey").value.trim(), yelp_key: $("#yKey").value.trim(), google_budget: $("#gBud").value,
      yelp_budget: $("#yBud").value, workers: $("#wk").value, pages_per_site: $("#pp").value, site_timeout: $("#to").value, mailblaster_db: $("#mbPath").value.trim(),
      companies_house_key: $("#chKey").value.trim(), hf_token: $("#hfKey").value.trim(), brave_key: $("#brKey").value.trim(),
      webfind_max: $("#wfMax").value, overture_min_conf: $("#ovConf").value, verify_guesses: $("#vfy").checked ? "1" : "0" } });
    toast("Settings saved");
  };
}

// ------------------------------------------------------------------ sidebar live status
async function refreshSide() {
  const s = await api("/api/stats").catch(() => null);
  if (!s) return;
  $("#navCount").textContent = s.leads ? fmt(s.leads) : "";
  const box = $("#runningBox");
  if (!s.running.length) { box.classList.add("hidden"); return; }
  const j = await api("/api/jobs/" + s.running[0]).catch(() => null);
  if (!j) return;
  const c = j.counts || {};
  const pct = c.enrich_total ? Math.round(100 * (c.enriched || 0) / c.enrich_total) : 0;
  box.classList.remove("hidden");
  box.innerHTML = `<a href="#/run/${j.id}">${esc((j.params.niches || []).join(", ") || "Working…")}</a>${esc(j.phase || "")}<br><b style="color:#fff">${fmt(j.stats?.leads || c.leads)}</b> leads · <b style="color:#fff">${fmt(j.stats?.emails)}</b> emails
    <div class="bar ${pct ? "" : "indet"}"><i style="width:${pct || 30}%"></i></div>${s.running.length > 1 ? `<small>+${s.running.length - 1} more running</small>` : ""}`;
}
setInterval(refreshSide, 4000);

// ------------------------------------------------------------------ boot
theme();
hydrateIcons();
route();
refreshSide();
