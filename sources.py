"""
Discovery sources.

* geocode()  — Nominatim: a typed place → area id / bbox / country.
* osm()      — OpenStreetMap via Overpass. Free, worldwide, no key. Big areas are
               split into tiles automatically when a server refuses the whole thing.
* google()   — Google Places (New) Text Search with the user's own key. One query
               caps at 60 results, so the area is gridded and saturated cells split.
* yelp()     — Yelp Fusion with the user's own key, gridded the same way.

Every source yields plain dicts in the lead shape store.upsert_lead() expects.
"""

from __future__ import annotations

import math
import queue
import random
import re
import threading
import time

import requests

UA = "LeadFinder/1.0 (local desktop lead research app)"
_S = requests.Session()
_S.headers["User-Agent"] = UA

OVERPASS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.private.coffee/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]
_NOMI_LOCK = threading.Lock()
_nomi_last = [0.0]


class Cancelled(Exception):
    pass


# --------------------------------------------------------------------------- #
# geocoding
# --------------------------------------------------------------------------- #
def _nominatim(params: dict):
    with _NOMI_LOCK:  # Nominatim policy: max 1 request / second
        wait = 1.05 - (time.time() - _nomi_last[0])
        if wait > 0:
            time.sleep(wait)
        _nomi_last[0] = time.time()
    r = _S.get("https://nominatim.openstreetmap.org/search",
               params={"format": "jsonv2", "addressdetails": 1, "accept-language": "en", **params}, timeout=25)
    r.raise_for_status()
    return r.json()


def suggest(q: str, limit: int = 6) -> list[dict]:
    out = []
    for x in _nominatim({"q": q, "limit": limit}):
        out.append({"label": x.get("display_name", ""), "type": x.get("addresstype") or x.get("type"),
                    "osm_type": x.get("osm_type"), "osm_id": x.get("osm_id")})
    return out


def geocode(q: str) -> dict:
    # the outline comes simplified (~300 m) — plenty to decide in/out, small even for countries
    res = _nominatim({"q": q, "limit": 5, "polygon_geojson": 1, "polygon_threshold": 0.003})
    if not res:
        raise ValueError(f'Could not find the place "{q}". Try adding the country, e.g. "Lyon, France".')
    # prefer an administrative area (a relation) over a point with the same name
    pick = next((x for x in res if x.get("osm_type") == "relation"), res[0])
    s, n, w, e = (float(v) for v in pick["boundingbox"])
    lat, lon = float(pick["lat"]), float(pick["lon"])
    if pick["osm_type"] != "relation":
        # a point/way: search a radius around it (≥ 3 km each way)
        dlat = max((n - s) / 2, 0.027)
        dlon = max((e - w) / 2, 0.027 / max(math.cos(math.radians(lat)), 0.2))
        s, n, w, e = lat - dlat, lat + dlat, lon - dlon, lon + dlon
    addr = pick.get("address", {})
    return {
        "label": pick.get("display_name", q),
        "name": pick.get("name") or q,
        "area_id": 3600000000 + int(pick["osm_id"]) if pick["osm_type"] == "relation" else None,
        "bbox": (s, w, n, e), "lat": lat, "lon": lon,
        "country": addr.get("country", ""), "country_code": (addr.get("country_code") or "").upper(),
        "city": addr.get("city") or addr.get("town") or addr.get("village") or addr.get("municipality") or "",
        "kind": pick.get("addresstype") or pick.get("type") or "",
        # outline only for real areas (a relation); a point search keeps its square
        "polygon": pick.get("geojson") if pick["osm_type"] == "relation" and
        (pick.get("geojson") or {}).get("type") in ("Polygon", "MultiPolygon") else None,
        "iso4": addr.get("ISO3166-2-lvl4", ""), "iso6": addr.get("ISO3166-2-lvl6", ""),
        "postcode": addr.get("postcode", ""),
    }


def bbox_km(b):
    s, w, n, e = b
    h = (n - s) * 111
    wd = (e - w) * 111 * math.cos(math.radians((n + s) / 2))
    return abs(wd), abs(h)


def split_bbox(b, nx=2, ny=2):
    s, w, n, e = b
    dx, dy = (e - w) / nx, (n - s) / ny
    return [(s + j * dy, w + i * dx, s + (j + 1) * dy, w + (i + 1) * dx) for j in range(ny) for i in range(nx)]


# --------------------------------------------------------------------------- #
# OpenStreetMap / Overpass
# --------------------------------------------------------------------------- #
class _TooBig(Exception):
    pass


_EP_SPEED: dict[str, float] = {}  # endpoint → smoothed seconds of recent good answers
_EP_LOCK = threading.Lock()


def _ranked_endpoints():
    with _EP_LOCK:
        return sorted(OVERPASS, key=lambda e: _EP_SPEED.get(e, 20.0))


def _one(ep, query, timeout, out: "queue.Queue"):
    t0 = time.time()
    host = ep.split("/")[2]
    try:
        r = _S.post(ep, data={"data": query}, timeout=timeout + 30)
    except requests.Timeout:
        out.put(("toobig", ep, f"{host} timed out"))
        return
    except requests.RequestException as ex:
        out.put(("busy", ep, f"{host}: {type(ex).__name__}"))
        return
    if r.status_code == 200:
        try:
            j = r.json()
        except ValueError:
            out.put(("busy", ep, f"{host}: unreadable answer"))
            return
        rem = (j.get("remark") or "").lower()
        if "timed out" in rem or "out of memory" in rem:
            out.put(("toobig", ep, rem[:120]))
            return
        if "runtime error" in rem:
            out.put(("busy", ep, rem[:120]))
            return
        with _EP_LOCK:
            prev = _EP_SPEED.get(ep, time.time() - t0)
            _EP_SPEED[ep] = 0.5 * prev + 0.5 * (time.time() - t0)
        out.put(("ok", ep, j))
        return
    text = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", r.text))
    with _EP_LOCK:
        _EP_SPEED[ep] = _EP_SPEED.get(ep, 20.0) + 15  # push busy servers down the list
    if r.status_code == 400:
        out.put(("bad", ep, text[-300:]))
    elif "timed out" in text.lower() and "dispatcher" not in text.lower():
        out.put(("toobig", ep, f"{host} query timed out"))
    else:
        out.put(("busy", ep, f"{host} busy (HTTP {r.status_code})"))


def _overpass(query: str, cancel, log, timeout: int) -> dict:
    """Hedged request: ask the fastest-known server first; if it has not answered
    after a few seconds, also ask the next one — first good answer wins.
    HTTP 429/504 = busy (try another / back off); a timeout = the tile is too big."""
    last = ""
    for rnd in range(3):
        eps = _ranked_endpoints()
        out: queue.Queue = queue.Queue()
        launched, answered, toobig = 0, 0, 0
        next_launch = 0.0
        while answered < len(eps):
            if cancel.is_set():
                raise Cancelled()
            if launched < len(eps) and time.time() >= next_launch:
                threading.Thread(target=_one, args=(eps[launched], query, timeout, out), daemon=True).start()
                launched += 1
                next_launch = time.time() + 8
            try:
                kind, ep, val = out.get(timeout=0.5)
            except queue.Empty:
                continue
            answered += 1
            if kind == "ok":
                return val
            if kind == "bad":
                raise RuntimeError("Map server rejected the query: " + val)
            if kind == "toobig":
                toobig += 1
                if toobig >= 2 or (toobig and answered >= len(eps)):
                    raise _TooBig()
            last = val
            next_launch = 0  # that one failed — ask the next server right away
        log(f"Map servers busy — waiting a moment and retrying ({last}).", "warn")
        _sleep(cancel, 8 + rnd * 10 + random.random() * 4)
    raise RuntimeError("All map servers are busy right now — try again in a few minutes. " + last)


def _sleep(cancel, secs):
    if cancel.wait(secs):
        raise Cancelled()


def _osm_query(filters, area_id, bbox, timeout):
    scope = ""
    if area_id:
        scope += "(area.a)"
    if bbox:
        scope += "({:.6f},{:.6f},{:.6f},{:.6f})".format(*bbox)
    head = f"[out:json][timeout:{timeout}];"
    if area_id:
        head += f"area(id:{area_id})->.a;"
    body = "".join(f"nwr{f}{scope};" for f in filters)
    return f"{head}({body});out center tags;"


def osm(filters, geo, cancel, log, on_batch, max_depth=5):
    """Fetch every matching element in the area, splitting into tiles when needed."""
    seen = set()
    area_id = geo["area_id"]
    wkm, hkm = bbox_km(geo["bbox"])
    # very large areas (big countries) start pre-tiled so one query never has to do it all
    tiles = [(geo["bbox"], 0)]
    if wkm * hkm > 900_000:
        n = min(6, max(2, int(math.sqrt(wkm * hkm / 300_000))))
        tiles = [(t, 1) for t in split_bbox(geo["bbox"], n, n)]
    use_bbox_first = not area_id
    done = 0
    while tiles:
        if cancel.is_set():
            raise Cancelled()
        tile, depth = tiles.pop(0)
        bbox = tile if (depth > 0 or use_bbox_first) else None
        timeout = 180 if depth == 0 else 120
        try:
            j = _overpass(_osm_query(filters, area_id, bbox, timeout), cancel, log, timeout)
        except _TooBig:
            if depth >= max_depth:
                log("A map tile is too dense even after splitting — skipping it.")
                continue
            log(f"Area is large — splitting it into smaller tiles (level {depth + 1}).")
            tiles = [(t, depth + 1) for t in split_bbox(tile)] + tiles
            continue
        batch = []
        for el in j.get("elements", []):
            uid = f"{el['type'][0]}{el['id']}"
            if uid in seen:
                continue
            seen.add(uid)
            lead = _osm_lead(el, geo)
            if lead:
                batch.append(lead)
        done += 1
        if batch:
            on_batch(batch)
        if tiles:
            log(f"Map tile {done} done — {len(seen):,} places so far, {len(tiles)} tiles left.")
            _sleep(cancel, 1.0)
    return len(seen)


_CAT_KEYS = ("amenity", "shop", "office", "craft", "healthcare", "tourism", "leisure", "club", "industrial", "man_made")
_SOCIAL_TAGS = {"facebook": "facebook", "instagram": "instagram", "twitter": "twitter", "linkedin": "linkedin",
                "youtube": "youtube", "tiktok": "tiktok", "telegram": "telegram", "whatsapp": "whatsapp",
                "pinterest": "pinterest", "vk": "vk"}


def _first(t, *keys):
    for k in keys:
        v = t.get(k)
        if v:
            return v.split(";")[0].strip()
    return ""


def _social_url(kind, v):
    if v.startswith("http"):
        return v
    v = v.lstrip("@")
    base = {"facebook": "https://facebook.com/", "instagram": "https://instagram.com/",
            "twitter": "https://x.com/", "linkedin": "https://linkedin.com/company/",
            "youtube": "https://youtube.com/", "tiktok": "https://tiktok.com/@",
            "telegram": "https://t.me/", "whatsapp": "https://wa.me/", "pinterest": "https://pinterest.com/",
            "vk": "https://vk.com/"}[kind]
    return base + re.sub(r"\D", "", v) if kind == "whatsapp" else base + v


def _osm_lead(el, geo):
    t = el.get("tags", {})
    name = t.get("name") or t.get("brand") or t.get("operator")
    if not name:
        return None
    lat = el.get("lat") or el.get("center", {}).get("lat")
    lon = el.get("lon") or el.get("center", {}).get("lon")
    cat = next((f"{t[k]}".replace("_", " ") for k in _CAT_KEYS if t.get(k) and t[k] != "yes"), "")
    street = " ".join(x for x in (t.get("addr:housenumber", ""), t.get("addr:street", "")) if x)
    if t.get("addr:street") and geo.get("country_code") in ("DE", "AT", "CH", "NL", "BE", "IT", "ES", "PL",
                                                            "CZ", "DK", "SE", "NO", "FI", "PT", "HR", "SK"):
        street = " ".join(x for x in (t.get("addr:street", ""), t.get("addr:housenumber", "")) if x)
    city = t.get("addr:city") or t.get("addr:town") or t.get("addr:place") or ""
    pc = t.get("addr:postcode", "")
    address = ", ".join(x for x in (street, " ".join(y for y in (pc, city) if y)) if x) or t.get("addr:full", "")
    phones = []
    for k in ("phone", "contact:phone", "mobile", "contact:mobile", "phone:mobile"):
        for p in (t.get(k) or "").split(";"):
            p = p.strip()
            if p and p not in phones:
                phones.append(p)
    emails = []
    for k in ("email", "contact:email"):
        for e in (t.get(k) or "").split(";"):
            e = e.strip().lower().removeprefix("mailto:")
            if "@" in e and e not in emails:
                emails.append(e)
    website = _first(t, "website", "contact:website", "url", "brand:website", "operator:website")
    if website and not website.startswith("http"):
        website = "http://" + website
    socials = {}
    for tag, kind in _SOCIAL_TAGS.items():
        v = _first(t, f"contact:{tag}", tag)
        if v:
            socials[kind] = _social_url(kind, v)
    return {
        "name": name, "category": cat, "address": address, "city": city or geo.get("city", ""),
        "postcode": pc, "country": geo.get("country", ""), "country_code": t.get("addr:country") or geo.get("country_code", ""),
        "lat": lat, "lon": lon, "phone": phones[0] if phones else "", "phones": phones,
        "emails": emails, "website": website, "socials": socials,
        "hours": t.get("opening_hours", ""), "description": t.get("description", ""),
        "osm_id": f"{el['type']}/{el['id']}",
        "maps_url": f"https://www.openstreetmap.org/{el['type']}/{el['id']}",
        "sources": ["OpenStreetMap"],
    }


# --------------------------------------------------------------------------- #
# Google Places (New) — user's own key
# --------------------------------------------------------------------------- #
G_FIELDS = ",".join("places." + f for f in (
    "id", "displayName", "formattedAddress", "addressComponents", "nationalPhoneNumber",
    "internationalPhoneNumber", "websiteUri", "rating", "userRatingCount", "location",
    "primaryTypeDisplayName", "googleMapsUri", "businessStatus")) + ",nextPageToken"


def _grid(bbox, cell_km):
    wkm, hkm = bbox_km(bbox)
    nx = max(1, min(12, math.ceil(wkm / cell_km)))
    ny = max(1, min(12, math.ceil(hkm / cell_km)))
    return split_bbox(bbox, nx, ny)


def google(term, geo, key, budget, cancel, log, on_batch):
    used = [0]
    total = [0]

    def run_cell(b, depth):
        got = 0
        token = None
        for _page in range(3):
            if cancel.is_set():
                raise Cancelled()
            if used[0] >= budget:
                return got, True
            body = {"textQuery": term, "pageSize": 20,
                    "locationRestriction": {"rectangle": {"low": {"latitude": b[0], "longitude": b[1]},
                                                          "high": {"latitude": b[2], "longitude": b[3]}}}}
            if token:
                body["pageToken"] = token
            r = _S.post("https://places.googleapis.com/v1/places:searchText", json=body, timeout=30,
                        headers={"X-Goog-Api-Key": key, "X-Goog-FieldMask": G_FIELDS})
            used[0] += 1
            if r.status_code != 200:
                msg = r.json().get("error", {}).get("message", r.text[:200]) if r.text else r.status_code
                raise RuntimeError(f"Google Places: {msg}")
            j = r.json()
            batch = [_g_lead(p, geo) for p in j.get("places", [])]
            got += len(batch)
            total[0] += len(batch)
            if batch:
                on_batch(batch)
            token = j.get("nextPageToken")
            if not token:
                break
            _sleep(cancel, 1.5)
        return got, got >= 60

    wkm, hkm = bbox_km(geo["bbox"])
    cells = [(c, 0) for c in _grid(geo["bbox"], max(8, math.sqrt(wkm * hkm / max(budget / 3, 1))))]
    log(f"Google Places: scanning {len(cells)} grid cells (budget {budget} requests).")
    while cells and used[0] < budget:
        b, depth = cells.pop(0)
        got, saturated = run_cell(b, depth)
        if saturated and depth < 3 and used[0] < budget:
            cells = [(c, depth + 1) for c in split_bbox(b)] + cells  # dense cell — zoom in
    log(f"Google Places: {total[0]:,} results from {used[0]} requests.")
    return used[0]


def _g_lead(p, geo):
    comp = {c["types"][0]: c for c in p.get("addressComponents", []) if c.get("types")}
    city = (comp.get("locality") or comp.get("postal_town") or {}).get("longText", "")
    country = (comp.get("country") or {})
    loc = p.get("location", {})
    phone = p.get("internationalPhoneNumber") or p.get("nationalPhoneNumber") or ""
    return {
        "name": p.get("displayName", {}).get("text", ""),
        "category": (p.get("primaryTypeDisplayName") or {}).get("text", ""),
        "address": p.get("formattedAddress", ""), "city": city or geo.get("city", ""),
        "postcode": (comp.get("postal_code") or {}).get("longText", ""),
        "country": country.get("longText") or geo.get("country", ""),
        "country_code": country.get("shortText") or geo.get("country_code", ""),
        "lat": loc.get("latitude"), "lon": loc.get("longitude"),
        "phone": phone, "phones": [phone] if phone else [],
        "website": p.get("websiteUri", ""), "rating": p.get("rating"), "reviews": p.get("userRatingCount"),
        "google_id": p.get("id", ""), "maps_url": p.get("googleMapsUri", ""), "sources": ["Google"],
    }


# --------------------------------------------------------------------------- #
# Yelp Fusion — user's own key
# --------------------------------------------------------------------------- #
def yelp(term, geo, key, budget, cancel, log, on_batch):
    used = [0]
    total = 0
    cells = _grid(geo["bbox"], 12)
    log(f"Yelp: scanning {len(cells)} grid cells (budget {budget} requests).")
    for b in cells:
        clat, clon = (b[0] + b[2]) / 2, (b[1] + b[3]) / 2
        wkm, hkm = bbox_km(b)
        radius = int(min(40000, max(1000, math.hypot(wkm, hkm) * 500)))
        for offset in range(0, 200, 50):
            if cancel.is_set():
                raise Cancelled()
            if used[0] >= budget:
                log(f"Yelp: budget reached — {total:,} results.")
                return used[0]
            r = _S.get("https://api.yelp.com/v3/businesses/search", timeout=30,
                       headers={"Authorization": f"Bearer {key}"},
                       params={"term": term, "latitude": clat, "longitude": clon, "radius": radius,
                               "limit": 50, "offset": offset})
            used[0] += 1
            if r.status_code != 200:
                try:
                    msg = r.json().get("error", {}).get("description", r.status_code)
                except ValueError:
                    msg = r.status_code
                if r.status_code in (400,) and offset:
                    break
                raise RuntimeError(f"Yelp: {msg}")
            biz = r.json().get("businesses", [])
            batch = [_y_lead(x, geo) for x in biz]
            total += len(batch)
            if batch:
                on_batch(batch)
            if len(biz) < 50:
                break
            _sleep(cancel, 0.4)
    log(f"Yelp: {total:,} results from {used[0]} requests.")
    return used[0]


def _y_lead(x, geo):
    loc = x.get("location", {})
    co = x.get("coordinates", {})
    phone = x.get("display_phone") or x.get("phone") or ""
    return {
        "name": x.get("name", ""), "category": ", ".join(c["title"] for c in x.get("categories", [])[:2]),
        "address": ", ".join(loc.get("display_address", [])), "city": loc.get("city") or geo.get("city", ""),
        "postcode": loc.get("zip_code", ""), "country": geo.get("country", ""),
        "country_code": loc.get("country") or geo.get("country_code", ""),
        "lat": co.get("latitude"), "lon": co.get("longitude"),
        "phone": phone, "phones": [phone] if phone else [],
        "rating": x.get("rating"), "reviews": x.get("review_count"),
        "yelp_id": x.get("id", ""), "maps_url": (x.get("url") or "").split("?")[0], "sources": ["Yelp"],
    }
