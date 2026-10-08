"""
Open worldwide place datasets, queried straight from their public cloud copies
with DuckDB (only the rows and columns of the searched area are downloaded):

* Overture Maps Places — tens of millions of businesses in every country, from
  Meta / Microsoft / others, CDLA-Permissive licence. No key.
* Foursquare OS Places — 100M+ places, Apache-2.0. Gated on Hugging Face: needs the
  user's free HF access token.
"""

from __future__ import annotations

import os
import re
import threading
import time

import requests

import app_paths
import enrich
import taxonomy

OVERTURE_FALLBACK = "2026-09-23.1"
_release = {"v": None, "t": 0.0}
_fsq_release = {"v": None, "t": 0.0}
_SOCIAL_HOSTS = {k: re.compile(p) for k, p in enrich.SOCIAL.items()}


class Cancelled(Exception):
    pass


def available() -> bool:
    try:
        import duckdb  # noqa: F401
        return True
    except Exception:
        # ImportError, or a Smart App Control / DLL-load block on the native extension
        return False


def _connect():
    import duckdb
    c = duckdb.connect()
    ext = os.path.join(app_paths.bundle_dir(), "duckdb_ext")
    if os.path.isdir(ext):  # the installer ships httpfs so nothing is downloaded at run time
        c.execute(f"SET extension_directory='{ext.replace(chr(92), '/')}'")
    c.execute("INSTALL httpfs; LOAD httpfs;")
    c.execute("SET enable_object_cache=true; SET http_retries=4; SET http_timeout=60000;")
    return c


def overture_release() -> str:
    if _release["v"] and time.time() - _release["t"] < 6 * 3600:
        return _release["v"]
    try:
        v = requests.get("https://stac.overturemaps.org/catalog.json", timeout=20).json().get("latest")
    except Exception:
        v = None
    _release.update(v=v or _release["v"] or OVERTURE_FALLBACK, t=time.time())
    return _release["v"]


def _watch(con, cancel, done: threading.Event):
    """DuckDB queries can't see our cancel flag — interrupt them from outside."""
    while not done.wait(0.4):
        if cancel.is_set():
            try:
                con.interrupt()
            except Exception:
                pass
            return


def _tiles(bbox, area, step):
    s, w, n, e = bbox
    out = []
    y = s
    while y < n:
        x = w
        while x < e:
            t = (y, x, min(y + step, n), min(x + step, e))
            if area.touches(*t):
                out.append(t)
            x += step
        y += step
    return out


def _run(con, sql, args, cancel, on_rows, chunk=4000):
    done = threading.Event()
    threading.Thread(target=_watch, args=(con, cancel, done), daemon=True).start()
    try:
        cur = con.execute(sql, args)
        while True:
            rows = cur.fetchmany(chunk)
            if not rows:
                break
            on_rows(rows)
            if cancel.is_set():
                raise Cancelled()
    except Exception as ex:
        if cancel.is_set():
            raise Cancelled() from ex
        raise
    finally:
        done.set()


def _classify_urls(urls):
    website, socials = "", {}
    for u in urls or []:
        if not u:
            continue
        host = re.sub(r"^https?://", "", u.lower()).split("/")[0].removeprefix("www.").removeprefix("m.")
        kind = next((k for k, rx in _SOCIAL_HOSTS.items() if rx.search(host)), None)
        if kind:
            socials.setdefault(kind, u if u.startswith("http") else "https://" + u)
        elif not website and not re.search(r"goo\.gl|google\.|maps\.app|linktr\.ee|bit\.ly", host):
            website = u if u.startswith("http") else "http://" + u
    return website, socials


# --------------------------------------------------------------------------- #
# Overture
# --------------------------------------------------------------------------- #
_OV_COLS = """id, names.primary AS name, brand.names.primary AS brand, taxonomy.primary AS cat,
    basic_category AS basic, websites, socials, phones, emails, addresses,
    (bbox.ymin + bbox.ymax) / 2 AS lat, (bbox.xmin + bbox.xmax) / 2 AS lon"""


def _ov_filter(m: dict):
    if m["key"] == "all":
        return ("NOT list_has_any(coalesce(taxonomy.hierarchy, []::VARCHAR[]), ?::VARCHAR[]) "
                "AND NOT list_contains(?::VARCHAR[], coalesce(basic_category, ''))"), [taxonomy.NOT_BUSINESS,
                                                                           taxonomy.NOT_BUSINESS]
    if m.get("overture"):
        return ("(list_has_any(coalesce(taxonomy.hierarchy, []::VARCHAR[]), ?::VARCHAR[]) "
                "OR list_contains(?::VARCHAR[], basic_category))"), [m["overture"], m["overture"]]
    kws = [f"%{k}%" for k in (m.get("keywords") or [m["term"]])]
    ors = " OR ".join(["names.primary ILIKE ? OR taxonomy.primary ILIKE ?"] * len(kws))
    return f"({ors})", [x for k in kws for x in (k, k)]


class Session:
    """One DuckDB connection per search: the first query reads the datasets' file
    index (~15 s), every later one reuses it (~3 s)."""

    def __init__(self):
        self._con = {}

    def con(self, kind):
        if kind not in self._con:
            c = _connect()
            if kind == "overture":
                c.execute("SET s3_region='us-west-2'")
            self._con[kind] = c
        return self._con[kind]

    def close(self):
        for c in self._con.values():
            try:
                c.close()
            except Exception:
                pass
        self._con.clear()


def overture(m: dict, geo: dict, area, settings: dict, sess: Session, cancel, log, on_batch) -> int:
    rel = overture_release()
    path = f"s3://overturemaps-us-west-2/release/{rel}/theme=places/type=place/*.parquet"
    min_conf = float(settings.get("overture_min_conf") or 0.35)
    flt, fargs = _ov_filter(m)
    sql = (f"SELECT {_OV_COLS} FROM read_parquet('{path}') WHERE bbox.xmin >= ? AND bbox.xmin < ? "
           f"AND bbox.ymin >= ? AND bbox.ymin < ? AND coalesce(operating_status, 'open') = 'open' "
           f"AND coalesce(confidence, 1) >= ? AND names.primary IS NOT NULL AND {flt}")
    con = sess.con("overture")
    tiles = _tiles(geo["bbox"], area, 3.0)
    total = [0]
    log(f"Overture Maps ({rel}): scanning {len(tiles)} map square{'s' if len(tiles) != 1 else ''}…")

    def rows_to_leads(rows):
        batch = []
        for (pid, name, brand, cat, basic, webs, socs, phones, emails, addrs, lat, lon) in rows:
            if not area.contains(lat, lon):
                continue
            a = (addrs or [{}])[0] or {}
            website, soc = _classify_urls(list(webs or []) + list(socs or []))
            ems = []
            for e in emails or []:
                e = enrich._clean_email(e)
                if e and e not in ems:
                    ems.append(e)
            ph = [p for p in (phones or []) if p]
            batch.append({
                "name": name or brand, "category": (cat or basic or "").replace("_", " "),
                "address": ", ".join(x for x in (a.get("freeform"), " ".join(
                    y for y in (a.get("postcode"), a.get("locality")) if y)) if x),
                "city": a.get("locality") or "", "postcode": a.get("postcode") or "",
                "country": geo.get("country", "") if (a.get("country") or "").upper() in (
                    "", geo.get("country_code", "")) else a.get("country", ""),
                "country_code": (a.get("country") or geo.get("country_code") or "").upper(),
                "lat": lat, "lon": lon, "phone": ph[0] if ph else "", "phones": ph,
                "emails": ems, "website": website, "socials": soc, "overture_id": pid,
                "sources": ["Overture"],
            })
        total[0] += len(batch)
        if batch:
            on_batch(batch)

    for i, (s, w, n, e) in enumerate(tiles, 1):
        if cancel.is_set():
            raise Cancelled()
        for attempt in range(3):
            try:
                _run(con, sql, [w, e, s, n, min_conf] + fargs, cancel, rows_to_leads)
                break
            except Cancelled:
                raise
            except Exception as ex:
                if attempt == 2:
                    log(f"Overture square {i} failed: {str(ex)[:160]}", "error")
                else:
                    time.sleep(3 + attempt * 5)
        if len(tiles) > 1:
            log(f"Overture: square {i}/{len(tiles)} done — {total[0]:,} places so far.")
    return total[0]


# --------------------------------------------------------------------------- #
# Foursquare OS Places (needs a Hugging Face token)
# --------------------------------------------------------------------------- #
FSQ_REPO = "foursquare/fsq-os-places"


def fsq_release(token: str) -> str:
    if _fsq_release["v"] and time.time() - _fsq_release["t"] < 6 * 3600:
        return _fsq_release["v"]
    r = requests.get(f"https://huggingface.co/api/datasets/{FSQ_REPO}/tree/main/release", timeout=20,
                     headers={"Authorization": f"Bearer {token}"} if token else {})
    r.raise_for_status()
    dts = sorted(x["path"].split("dt=")[1] for x in r.json() if "dt=" in x.get("path", ""))
    if not dts:
        raise RuntimeError("could not find a Foursquare release")
    _fsq_release.update(v=dts[-1], t=time.time())
    return dts[-1]


def fsq(m: dict, geo: dict, area, token: str, sess: Session, cancel, log, on_batch) -> int:
    if not token:
        raise RuntimeError("Foursquare needs a free Hugging Face token (Settings).")
    dt = fsq_release(token)
    path = f"hf://datasets/{FSQ_REPO}/release/dt={dt}/places/parquet/*.parquet"
    con = sess.con("fsq")
    con.execute(f"CREATE OR REPLACE SECRET hf_lf (TYPE HUGGINGFACE, TOKEN '{token.replace(chr(39), '')}')")
    cols = {r[0] for r in con.execute(f"DESCRIBE SELECT * FROM read_parquet('{path}')").fetchall()}
    want = ["fsq_place_id", "name", "latitude", "longitude", "address", "locality", "postcode", "country",
            "tel", "website", "email", "facebook_id", "instagram", "twitter", "fsq_category_labels"]
    sel = ", ".join(c if c in cols else f"NULL AS {c}" for c in want)
    if m["key"] == "all":
        flt, fargs = ("NOT regexp_matches(lower(array_to_string(coalesce(fsq_category_labels, []::VARCHAR[]), '|')), "
                      "'landmarks and outdoors|transport')"), []
    else:
        rx = "|".join(re.escape(w.lower()) for w in (m.get("words") or [m["term"]]))
        flt = ("(regexp_matches(lower(array_to_string(coalesce(fsq_category_labels, []::VARCHAR[]), '|')), ?) "
               "OR regexp_matches(lower(name), ?))")
        fargs = [rx, rx]
    closed = "AND date_closed IS NULL" if "date_closed" in cols else ""
    sql = (f"SELECT {sel} FROM read_parquet('{path}') WHERE longitude >= ? AND longitude < ? "
           f"AND latitude >= ? AND latitude < ? {closed} AND name IS NOT NULL AND {flt}")
    tiles = _tiles(geo["bbox"], area, 3.0)
    total = [0]
    log(f"Foursquare ({dt}): scanning {len(tiles)} map square{'s' if len(tiles) != 1 else ''}…")

    def rows_to_leads(rows):
        batch = []
        for (pid, name, lat, lon, addr, loc, pc, cc, tel, web, email, fb, ig, tw, labels) in rows:
            if not area.contains(lat, lon):
                continue
            soc = {}
            if fb:
                soc["facebook"] = f"https://facebook.com/{fb}"
            if ig:
                soc["instagram"] = f"https://instagram.com/{str(ig).lstrip('@')}"
            if tw:
                soc["twitter"] = f"https://x.com/{str(tw).lstrip('@')}"
            website, s2 = _classify_urls([web] if web else [])
            for k, v in s2.items():
                soc.setdefault(k, v)
            e = enrich._clean_email(email) if email else ""
            batch.append({
                "name": name, "category": ((labels or [""])[0] or "").split(">")[-1].strip(),
                "address": ", ".join(x for x in (addr, " ".join(y for y in (pc, loc) if y)) if x),
                "city": loc or "", "postcode": pc or "", "country": geo.get("country", ""),
                "country_code": (cc or geo.get("country_code") or "").upper(), "lat": lat, "lon": lon,
                "phone": tel or "", "phones": [tel] if tel else [], "emails": [e] if e else [],
                "website": website, "socials": soc, "fsq_id": pid, "sources": ["Foursquare"],
            })
        total[0] += len(batch)
        if batch:
            on_batch(batch)

    for i, (s, w, n, e) in enumerate(tiles, 1):
        if cancel.is_set():
            raise Cancelled()
        _run(con, sql, [w, e, s, n] + fargs, cancel, rows_to_leads)
        if len(tiles) > 1:
            log(f"Foursquare: square {i}/{len(tiles)} done — {total[0]:,} places so far.")
    return total[0]
