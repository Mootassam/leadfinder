"""
SQLite storage: searches, leads (deduplicated across sources and searches),
the search↔lead link, a per-domain enrichment cache, and settings.
"""

from __future__ import annotations

import json
import math
import os
import re
import sqlite3
import threading
import time
from contextlib import contextmanager

import people as people_mod
from app_paths import data_dir

DB_PATH = os.environ.get("LF_DB") or os.path.join(data_dir(), "leads.db")
_LOCK = threading.RLock()

LIST_FIELDS = ("emails", "phones", "socials", "sources", "people")
ID_COLS = ("osm_id", "google_id", "yelp_id", "overture_id", "fsq_id", "reg_id")
LEAD_COLS = ("name", "category", "niche", "address", "city", "postcode", "country", "country_code",
             "lat", "lon", "phone", "website", "domain", "email", "rating", "reviews", "hours",
             "description", "maps_url", "title", "language", "contact_page",
             "legal_name", "company_id", "employees", "founded", "website_src") + ID_COLS
# columns added after v1.0 — created on older databases by init()
NEW_COLS = {"overture_id": "TEXT DEFAULT ''", "fsq_id": "TEXT DEFAULT ''", "reg_id": "TEXT DEFAULT ''",
            "legal_name": "TEXT DEFAULT ''", "legal_norm": "TEXT DEFAULT ''", "company_id": "TEXT DEFAULT ''",
            "employees": "TEXT DEFAULT ''", "founded": "TEXT DEFAULT ''", "people": "TEXT DEFAULT '[]'",
            "website_src": "TEXT DEFAULT ''", "web_status": "TEXT DEFAULT ''"}


def _conn():
    c = sqlite3.connect(DB_PATH, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA synchronous=NORMAL")
    return c


@contextmanager
def _db(write: bool = False):
    """Readers never wait: WAL lets them run beside the writer. Writers are
    serialised in-process so 24 enrichment threads don't fight over the file."""
    c = _conn()
    try:
        if write:
            with _LOCK, c:
                yield c
        else:
            yield c
    finally:
        c.close()


def init():
    with _db(write=True) as c:
        c.execute("PRAGMA journal_mode=WAL")
        c.executescript("""
            CREATE TABLE IF NOT EXISTS searches(
                id INTEGER PRIMARY KEY, niche TEXT, location TEXT, params TEXT DEFAULT '{}',
                status TEXT DEFAULT 'queued', error TEXT DEFAULT '', log TEXT DEFAULT '[]',
                created_at REAL, finished_at REAL);
            CREATE TABLE IF NOT EXISTS leads(
                id INTEGER PRIMARY KEY,
                name TEXT DEFAULT '', category TEXT DEFAULT '', niche TEXT DEFAULT '',
                address TEXT DEFAULT '', city TEXT DEFAULT '', postcode TEXT DEFAULT '',
                country TEXT DEFAULT '', country_code TEXT DEFAULT '',
                lat REAL, lon REAL,
                phone TEXT DEFAULT '', phones TEXT DEFAULT '[]', phone_norm TEXT DEFAULT '',
                website TEXT DEFAULT '', domain TEXT DEFAULT '',
                email TEXT DEFAULT '', emails TEXT DEFAULT '[]', mx_ok INTEGER,
                socials TEXT DEFAULT '{}', sources TEXT DEFAULT '[]',
                rating REAL, reviews INTEGER, hours TEXT DEFAULT '', description TEXT DEFAULT '',
                title TEXT DEFAULT '', language TEXT DEFAULT '', contact_page TEXT DEFAULT '',
                maps_url TEXT DEFAULT '',
                osm_id TEXT DEFAULT '', google_id TEXT DEFAULT '', yelp_id TEXT DEFAULT '',
                name_norm TEXT DEFAULT '',
                enrich_status TEXT DEFAULT 'none', site_status TEXT DEFAULT '',
                score INTEGER DEFAULT 0, starred INTEGER DEFAULT 0, note TEXT DEFAULT '',
                exported INTEGER DEFAULT 0,
                created_at REAL, updated_at REAL);
            CREATE INDEX IF NOT EXISTS ix_leads_domain ON leads(domain);
            CREATE INDEX IF NOT EXISTS ix_leads_phone ON leads(phone_norm);
            CREATE INDEX IF NOT EXISTS ix_leads_osm ON leads(osm_id);
            CREATE INDEX IF NOT EXISTS ix_leads_google ON leads(google_id);
            CREATE INDEX IF NOT EXISTS ix_leads_yelp ON leads(yelp_id);
            CREATE INDEX IF NOT EXISTS ix_leads_name ON leads(name_norm);
            CREATE INDEX IF NOT EXISTS ix_leads_enrich ON leads(enrich_status);
            CREATE TABLE IF NOT EXISTS search_leads(
                search_id INTEGER, lead_id INTEGER, UNIQUE(search_id, lead_id));
            CREATE INDEX IF NOT EXISTS ix_sl_lead ON search_leads(lead_id);
            CREATE TABLE IF NOT EXISTS sites(
                domain TEXT PRIMARY KEY, data TEXT, fetched_at REAL);
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY, value TEXT);
        """)
        have = {r[1] for r in c.execute("PRAGMA table_info(leads)")}
        for col, decl in NEW_COLS.items():
            if col not in have:
                c.execute(f"ALTER TABLE leads ADD COLUMN {col} {decl}")
        for col in ("overture_id", "fsq_id", "reg_id", "legal_norm", "postcode", "lat"):
            c.execute(f"CREATE INDEX IF NOT EXISTS ix_leads_{col} ON leads({col})")
        # a crash / close / update mid-run leaves searches "running": they are picked up again
        # automatically at start-up (INTERRUPTED); ones the user stopped stay stopped
        INTERRUPTED[:] = [r[0] for r in c.execute("SELECT id FROM searches WHERE status IN ('running','queued')")]
        c.execute("UPDATE searches SET status='stopped' WHERE status IN ('running','queued')")
        c.execute("UPDATE leads SET enrich_status='pending' WHERE enrich_status='working'")


INTERRUPTED: list[int] = []


# --------------------------------------------------------------------------- #
# settings
# --------------------------------------------------------------------------- #
DEFAULTS = {
    "google_key": "", "yelp_key": "",
    "workers": "24", "pages_per_site": "6", "site_timeout": "12",
    "google_budget": "150", "yelp_budget": "100",
    "mailblaster_db": "",
    "companies_house_key": "", "brave_key": "", "hf_token": "",
    "opencorporates_token": "", "wikidata_max": "1500",
    "overture_min_conf": "0.35", "webfind_max": "5000", "verify_guesses": "1",
}


def get_settings() -> dict:
    with _db() as c:
        s = dict(DEFAULTS)
        s.update({r["key"]: r["value"] for r in c.execute("SELECT key,value FROM settings")})
        return s


def save_settings(d: dict):
    with _db(write=True) as c:
        for k, v in d.items():
            if k in DEFAULTS:
                c.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)", (k, str(v or "")))


def setting(key: str) -> str:
    return get_settings().get(key, "")


# --------------------------------------------------------------------------- #
# searches
# --------------------------------------------------------------------------- #
def create_search(niche: str, location: str, params: dict) -> int:
    with _db(write=True) as c:
        return c.execute("INSERT INTO searches(niche,location,params,status,created_at) VALUES(?,?,?,?,?)",
                         (niche, location, json.dumps(params), "queued", time.time())).lastrowid


def update_search(sid: int, **kw):
    if not kw:
        return
    if "log" in kw and not isinstance(kw["log"], str):
        kw["log"] = json.dumps(kw["log"][-300:])
    sets = ",".join(f"{k}=?" for k in kw)
    with _db(write=True) as c:
        c.execute(f"UPDATE searches SET {sets} WHERE id=?", (*kw.values(), sid))


def _search_stats(c, sid):
    r = c.execute("""SELECT COUNT(*) n,
                        SUM(l.email<>'') emails, SUM(l.phone<>'') phones, SUM(l.website<>'') sites,
                        SUM(l.enrich_status='pending') pending, AVG(l.score) avg_score,
                        SUM(l.people<>'[]') people
                     FROM search_leads s JOIN leads l ON l.id=s.lead_id WHERE s.search_id=?""",
                  (sid,)).fetchone()
    return {"leads": r["n"] or 0, "emails": r["emails"] or 0, "phones": r["phones"] or 0,
            "websites": r["sites"] or 0, "pending": r["pending"] or 0,
            "avg_score": round(r["avg_score"] or 0), "people": r["people"] or 0}


def get_search(sid: int) -> dict | None:
    with _db() as c:
        r = c.execute("SELECT * FROM searches WHERE id=?", (sid,)).fetchone()
        if not r:
            return None
        d = dict(r)
        d["params"] = json.loads(d["params"] or "{}")
        d["log"] = json.loads(d["log"] or "[]")
        d["stats"] = _search_stats(c, sid)
        return d


def list_searches() -> list[dict]:
    with _db() as c:
        out = []
        for r in c.execute("SELECT id,niche,location,params,status,error,created_at,finished_at "
                           "FROM searches ORDER BY id DESC"):
            d = dict(r)
            d["params"] = json.loads(d["params"] or "{}")
            d["stats"] = _search_stats(c, r["id"])
            out.append(d)
        return out


def delete_search(sid: int, delete_leads: bool):
    with _db(write=True) as c:
        if delete_leads:
            # only leads that belong to no other search
            c.execute("""DELETE FROM leads WHERE id IN (
                           SELECT lead_id FROM search_leads WHERE search_id=?)
                         AND id NOT IN (SELECT lead_id FROM search_leads WHERE search_id<>?)""",
                      (sid, sid))
        c.execute("DELETE FROM search_leads WHERE search_id=?", (sid,))
        c.execute("DELETE FROM searches WHERE id=?", (sid,))


# --------------------------------------------------------------------------- #
# leads — normalisation, dedupe/merge
# --------------------------------------------------------------------------- #
def norm_phone(p: str) -> str:
    d = re.sub(r"\D", "", p or "")
    return d[-9:] if len(d) >= 7 else ""


def norm_name(n: str) -> str:
    n = (n or "").lower()
    n = re.sub(r"\b(gmbh|ltd|llc|inc|sarl|sas|srl|bv|ag|co|kg|plc|the|dr|dds)\b\.?", " ", n)
    return re.sub(r"[^a-z0-9À-￿]+", "", n)


def domain_of(url: str) -> str:
    if not url:
        return ""
    u = url.strip().lower()
    u = re.sub(r"^[a-z]+://", "", u)
    h = u.split("/")[0].split("?")[0].split(":")[0]
    if h.startswith("www."):
        h = h[4:]
    # aggregator / social hosts are not the business's own domain
    if re.search(r"(facebook|instagram|linktr\.ee|google\.|goo\.gl|yelp\.|tripadvisor|twitter|x\.com$|"
                 r"linkedin|wa\.me|whatsapp|booking\.com|doctolib|jameda|youtube|tiktok|business\.site)",
                 h):
        return ""
    return h if "." in h else ""


_GENERIC_TOK = set("""cabinet dentaire dental dentist dentiste clinic clinique centre center praxis docteur doctor
restaurant hotel salon studio agence agency group groupe services service office bureau atelier maison boutique
shop store pharmacie pharmacy garage immobilier holding cafe coffee paris lyon london avocat avocats lawyer
lawyers law firm conseil consulting sarl selarl scp chirurgien chirurgiens medecin medical sante health beauty
institut coiffure coiffeur hair nails spa fitness sport sports""".split())


def _name_words(n: str) -> list[str]:
    import unicodedata
    n = unicodedata.normalize("NFKD", re.sub(r"\(.*?\)", " ", n or "")).encode("ascii", "ignore").decode().lower()
    return [w for w in re.findall(r"[a-z]{4,}", n) if w not in _GENERIC_TOK]


def _name_tokens(n: str) -> set[str]:
    return set(_name_words(n))


def _same_name(a: list[str], b: list[str]) -> bool:
    """Two names of one business: 2+ distinctive words in common, or the shared word is a surname /
    brand (last word, or the only distinctive word). A shared first name alone is not enough."""
    shared = set(a) & set(b)
    if not shared:
        return False
    if len(shared) >= 2:
        return True
    w = next(iter(shared))
    return (len(a) == 1 or len(b) == 1) or w in (a[-1], b[-1])


def _dist_m(a, b, c, d):
    if None in (a, b, c, d):
        return 1e9
    return math.hypot((a - c) * 111000, (b - d) * 111000 * math.cos(math.radians(a)))


def _row(r) -> dict:
    d = dict(r)
    for k in LIST_FIELDS:
        try:
            d[k] = json.loads(d.get(k) or ("{}" if k == "socials" else "[]"))
        except (ValueError, TypeError):
            d[k] = {} if k == "socials" else []
    return d


def _find_existing(c, d: dict):
    for col in ID_COLS:
        if d.get(col):
            r = c.execute(f"SELECT * FROM leads WHERE {col}=?", (d[col],)).fetchone()
            if r:
                return r
    nn = d.get("name_norm")
    names = {x for x in (nn, d.get("legal_norm")) if x and len(x) > 3}
    if d.get("domain"):
        for r in c.execute("SELECT * FROM leads WHERE domain=?", (d["domain"],)):
            # chains share a domain: only merge the same branch (same name nearby / same city)
            if (r["name_norm"] == nn or not nn) and (
                    _dist_m(r["lat"], r["lon"], d.get("lat"), d.get("lon")) < 1500
                    or (r["city"] or "").lower() == (d.get("city") or "").lower()):
                return r
    if d.get("phone_norm"):
        r = c.execute("SELECT * FROM leads WHERE phone_norm=?", (d["phone_norm"],)).fetchone()
        if r:
            return r
    lat, lon = d.get("lat"), d.get("lon")
    mine = [w for w in (_name_words(d.get("name", "")), _name_words(d.get("legal_name", ""))) if w]
    if lat is not None and lon is not None and mine:
        # same spot (≤60 m) and the same distinctive name: "Cabinet dentaire Levin" = "Dr. Michel Levin"
        dl = 0.0006
        for r in c.execute("SELECT * FROM leads WHERE lat BETWEEN ? AND ? AND lon BETWEEN ? AND ?",
                           (lat - dl, lat + dl, lon - dl * 1.6, lon + dl * 1.6)):
            if _dist_m(r["lat"], r["lon"], lat, lon) >= 60:
                continue
            theirs = [w for w in (_name_words(r["name"]), _name_words(r["legal_name"] or "")) if w]
            if any(_same_name(a, b) for a in mine for b in theirs):
                return r
    for x in names:
        for r in c.execute("SELECT * FROM leads WHERE name_norm=? OR legal_norm=?", (x, x)):
            if _dist_m(r["lat"], r["lon"], d.get("lat"), d.get("lon")) < 300:
                return r
            pc = (d.get("postcode") or "").replace(" ", "").lower()
            if pc and pc == (r["postcode"] or "").replace(" ", "").lower() and (
                    r["lat"] is None or d.get("lat") is None or
                    _dist_m(r["lat"], r["lon"], d.get("lat"), d.get("lon")) < 3000):
                return r
    return None


def _merge_lists(a, b):
    out = list(a or [])
    for x in b or []:
        if x and x not in out:
            out.append(x)
    return out


def _merge_phones(a, b):
    out, seen = [], set()
    for x in list(a or []) + list(b or []):
        k = norm_phone(x) or x
        if x and k not in seen:
            seen.add(k)
            out.append(x)
    return out


def upsert_lead(d: dict, search_id: int | None = None) -> tuple[int, bool]:
    """Insert or merge a discovered business. Returns (lead_id, is_new)."""
    with _db(write=True) as c:
        return _upsert(c, d, search_id)


def upsert_many(items: list[dict], search_id: int | None = None) -> list[tuple[int, bool]]:
    """Same as upsert_lead for a whole batch in one transaction (much faster)."""
    with _db(write=True) as c:
        return [_upsert(c, d, search_id) for d in items]


def _merge_people(a, b):
    out = list(a or [])
    seen = {norm_name(p.get("name", "")) for p in out}
    for p in b or []:
        k = norm_name(p.get("name", ""))
        if k and k not in seen:
            seen.add(k)
            out.append(p)
    return out[:12]


def _upsert(c, d: dict, search_id: int | None = None) -> tuple[int, bool]:
    d = dict(d)
    d["domain"] = d.get("domain") or domain_of(d.get("website", ""))
    if d.get("website") and not d["domain"]:
        d["website"] = ""  # a facebook page etc. — keep it in socials, not as website
    d["phone_norm"] = norm_phone(d.get("phone", ""))
    d["name_norm"] = norm_name(d.get("name", ""))
    d["legal_norm"] = norm_name(d.get("legal_name", ""))
    if d.get("website") and not d.get("website_src"):
        d["website_src"] = (d.get("sources") or ["listing"])[0]
    now = time.time()
    ex = _find_existing(c, d)
    if ex:
        cur = _row(ex)
        upd = {}
        for k in LEAD_COLS + ("phone_norm", "name_norm", "legal_norm"):
            v = d.get(k)
            if v not in (None, "", []) and cur.get(k) in (None, "", 0):
                upd[k] = v
        upd["emails"] = json.dumps(_merge_lists(cur["emails"], d.get("emails")))
        upd["phones"] = json.dumps(_merge_phones(cur["phones"], d.get("phones") or
                                                ([d["phone"]] if d.get("phone") else [])))
        soc = dict(d.get("socials") or {})
        soc.update(cur["socials"])
        upd["socials"] = json.dumps(soc)
        upd["sources"] = json.dumps(_merge_lists(cur["sources"], d.get("sources")))
        if d.get("people"):
            upd["people"] = json.dumps(_merge_people(cur["people"], d["people"]))
        if upd.get("domain") and cur["enrich_status"] in ("none", ""):
            upd["enrich_status"] = "pending"
        if not cur["email"] and d.get("emails"):
            upd["email"] = d["emails"][0]
        upd["updated_at"] = now
        sets = ",".join(f"{k}=?" for k in upd)
        c.execute(f"UPDATE leads SET {sets} WHERE id=?", (*upd.values(), ex["id"]))
        lid, new = ex["id"], False
    else:
        row = {k: d.get(k) for k in LEAD_COLS}
        for k in LEAD_COLS:
            if k not in ("lat", "lon", "rating", "reviews"):
                row[k] = row.get(k) or ""
        row["people"] = json.dumps(d.get("people") or [])
        row["legal_norm"] = d["legal_norm"]
        row["emails"] = json.dumps(d.get("emails") or [])
        row["phones"] = json.dumps(d.get("phones") or ([d["phone"]] if d.get("phone") else []))
        row["socials"] = json.dumps(d.get("socials") or {})
        row["sources"] = json.dumps(d.get("sources") or [])
        row["phone_norm"] = d["phone_norm"]
        row["name_norm"] = d["name_norm"]
        if not row["email"] and d.get("emails"):
            row["email"] = d["emails"][0]
        row["enrich_status"] = "pending" if row["domain"] else "none"
        row["created_at"] = row["updated_at"] = now
        cols = ",".join(row)
        lid = c.execute(f"INSERT INTO leads({cols}) VALUES({','.join('?' * len(row))})",
                        tuple(row.values())).lastrowid
        new = True
    if search_id:
        c.execute("INSERT OR IGNORE INTO search_leads(search_id,lead_id) VALUES(?,?)", (search_id, lid))
    _rescore(c, lid)
    return lid, new


def score_lead(d: dict) -> int:
    s = 0
    emails = d.get("emails") or []
    if d.get("email"):
        s += 35
        if d.get("domain") and d["email"].endswith("@" + d["domain"]):
            s += 10
        if d.get("mx_ok"):
            s += 10
    if d.get("phone"):
        s += 15
    if d.get("website"):
        s += 12
    s += min(len(d.get("socials") or {}), 3) * 3
    if d.get("address"):
        s += 4
    if d.get("rating"):
        s += 3
    if len(emails) > 1:
        s += 2
    if d.get("people"):
        s += 6
    if d.get("reg_id"):
        s += 3
    if d.get("site_status") == "dead":
        s -= 10
    return max(0, min(100, s))


def _rescore(c, lid):
    r = c.execute("SELECT * FROM leads WHERE id=?", (lid,)).fetchone()
    if r:
        c.execute("UPDATE leads SET score=? WHERE id=?", (score_lead(_row(r)), lid))


def pending_enrich(search_id: int | None, limit: int = 100000, ids=None) -> list[dict]:
    with _db() as c:
        if ids:
            q = f"SELECT id,domain,website FROM leads WHERE domain<>'' AND id IN ({','.join('?' * len(ids))})"
            rows = c.execute(q, tuple(ids)).fetchall()
        elif search_id:
            rows = c.execute("""SELECT l.id,l.domain,l.website FROM leads l JOIN search_leads s ON s.lead_id=l.id
                                WHERE s.search_id=? AND l.enrich_status='pending' LIMIT ?""",
                             (search_id, limit)).fetchall()
        else:
            rows = c.execute("SELECT id,domain,website FROM leads WHERE enrich_status='pending' LIMIT ?",
                             (limit,)).fetchall()
        return [dict(r) for r in rows]


def set_enrich_status(ids, status):
    with _db(write=True) as c:
        c.executemany("UPDATE leads SET enrich_status=? WHERE id=?", [(status, i) for i in ids])


def cached_site(domain: str, max_age_days: float = 30):
    with _db() as c:
        r = c.execute("SELECT data,fetched_at FROM sites WHERE domain=?", (domain,)).fetchone()
        if r and time.time() - r["fetched_at"] < max_age_days * 86400:
            return json.loads(r["data"])
    return None


def save_site(domain: str, data: dict):
    with _db(write=True) as c:
        c.execute("INSERT OR REPLACE INTO sites(domain,data,fetched_at) VALUES(?,?,?)",
                  (domain, json.dumps(data), time.time()))


def _branch_first(emails: list[str], lead: dict) -> list[str]:
    """Chains share one website: prefer the address whose mailbox names this branch
    (amay@dentius.be for "Dentius Amay") over the generic info@."""
    words = {w for w in re.findall(r"[a-zÀ-￿]{4,}", f"{lead.get('city', '')} {lead.get('name', '')}".lower())}
    if not words or len(emails) < 2:
        return emails
    hit = [e for e in emails if any(w in e.split("@")[0] for w in words)]
    return hit + [e for e in emails if e not in hit]


def apply_enrichment(lid: int, info: dict):
    """Merge what the website told us into the lead."""
    with _db(write=True) as c:
        r = c.execute("SELECT * FROM leads WHERE id=?", (lid,)).fetchone()
        if not r:
            return
        cur = _row(r)
        emails = _branch_first(_merge_lists(info.get("emails"), cur["emails"]), cur)  # site emails first (ranked)
        phones = _merge_phones(cur["phones"], info.get("phones"))
        socials = dict(info.get("socials") or {})
        socials.update(cur["socials"])
        upd = {
            "emails": json.dumps(emails[:15]), "phones": json.dumps(phones[:8]),
            "socials": json.dumps(socials),
            "email": emails[0] if emails else cur["email"],
            "enrich_status": "done" if info.get("ok") else "failed",
            "site_status": info.get("status", ""),
            "updated_at": time.time(),
        }
        if info.get("mx") is not None:
            upd["mx_ok"] = 1 if info["mx"] else 0
        if not cur["phone"] and phones:
            upd["phone"] = phones[0]
            upd["phone_norm"] = norm_phone(phones[0])
        ppl, _pattern = people_mod.infer(_merge_people(cur["people"], info.get("people")), emails,
                                         cur["domain"] or "")
        if ppl:
            upd["people"] = json.dumps(ppl)
        for k in ("title", "language", "contact_page", "description"):
            if info.get(k) and not cur.get(k):
                upd[k] = info[k][:500]
        sets = ",".join(f"{k}=?" for k in upd)
        c.execute(f"UPDATE leads SET {sets} WHERE id=?", (*upd.values(), lid))
        _rescore(c, lid)


# --------------------------------------------------------------------------- #
# querying
# --------------------------------------------------------------------------- #
SORTS = {"score": "l.score DESC, l.id DESC", "name": "l.name COLLATE NOCASE ASC",
         "newest": "l.id DESC", "city": "l.city COLLATE NOCASE, l.name COLLATE NOCASE",
         "rating": "COALESCE(l.rating,0) DESC, COALESCE(l.reviews,0) DESC"}


def _where(f: dict):
    w, a = ["1=1"], []
    if f.get("search"):
        w.append("l.id IN (SELECT lead_id FROM search_leads WHERE search_id=?)")
        a.append(int(f["search"]))
    if f.get("q"):
        like = f"%{f['q'].strip()}%"
        w.append("(l.name LIKE ? OR l.email LIKE ? OR l.domain LIKE ? OR l.city LIKE ? OR l.category LIKE ? "
                 "OR l.address LIKE ? OR l.phone LIKE ?)")
        a += [like] * 7
    for flag, cond in (("has_email", "l.email<>''"), ("has_phone", "l.phone<>''"),
                       ("has_website", "l.website<>''"), ("starred", "l.starred=1"),
                       ("has_social", "l.socials<>'{}'"), ("mx_ok", "l.mx_ok=1"), ("has_people", "l.people<>'[]'"),
                       ("not_exported", "l.exported=0")):
        if str(f.get(flag, "")).lower() in ("1", "true", "yes"):
            w.append(cond)
    if f.get("min_score"):
        w.append("l.score>=?")
        a.append(int(f["min_score"]))
    for col in ("city", "country", "category"):
        if f.get(col):
            w.append(f"l.{col}=?")
            a.append(f[col])
    if f.get("ids"):
        ids = [int(x) for x in str(f["ids"]).split(",") if x.strip().isdigit()]
        w.append(f"l.id IN ({','.join('?' * len(ids)) or 'NULL'})")
        a += ids
    return " AND ".join(w), a


def query_leads(f: dict, page: int = 1, size: int = 50) -> dict:
    where, args = _where(f)
    order = SORTS.get(f.get("sort") or "score", SORTS["score"])
    with _db() as c:
        total = c.execute(f"SELECT COUNT(*) FROM leads l WHERE {where}", args).fetchone()[0]
        rows = c.execute(f"SELECT l.* FROM leads l WHERE {where} ORDER BY {order} LIMIT ? OFFSET ?",
                         (*args, size, (page - 1) * size)).fetchall()
        agg = c.execute(f"""SELECT SUM(l.email<>'') e, SUM(l.phone<>'') p, SUM(l.website<>'') w,
                                   SUM(l.enrich_status='pending') pend FROM leads l WHERE {where}""",
                        args).fetchone()
        facets = {}
        for col in ("city", "country", "category"):
            facets[col] = [{"v": r[0], "n": r[1]} for r in c.execute(
                f"SELECT l.{col}, COUNT(*) FROM leads l WHERE {where} AND l.{col}<>'' "
                f"GROUP BY l.{col} ORDER BY COUNT(*) DESC LIMIT 60", args)]
    return {"total": total, "page": page, "size": size, "items": [_row(r) for r in rows],
            "counts": {"emails": agg["e"] or 0, "phones": agg["p"] or 0, "websites": agg["w"] or 0,
                       "pending": agg["pend"] or 0},
            "facets": facets}


def iter_leads(f: dict, limit: int = 1_000_000):
    where, args = _where(f)
    order = SORTS.get(f.get("sort") or "score", SORTS["score"])
    with _db() as c:
        rows = c.execute(f"SELECT l.* FROM leads l WHERE {where} ORDER BY {order} LIMIT ?",
                         (*args, limit)).fetchall()
    return [_row(r) for r in rows]


def geo_points(f: dict, limit: int = 6000):
    where, args = _where(f)
    with _db() as c:
        return [dict(r) for r in c.execute(
            f"SELECT l.id,l.name,l.lat,l.lon,l.score,l.email<>'' AS e FROM leads l "
            f"WHERE {where} AND l.lat IS NOT NULL ORDER BY l.score DESC LIMIT ?", (*args, limit))]


def get_lead(lid: int):
    with _db() as c:
        r = c.execute("SELECT * FROM leads WHERE id=?", (lid,)).fetchone()
        if not r:
            return None
        d = _row(r)
        d["searches"] = [dict(x) for x in c.execute(
            "SELECT s.id,s.niche,s.location FROM search_leads sl JOIN searches s ON s.id=sl.search_id "
            "WHERE sl.lead_id=?", (lid,))]
        return d


def update_lead(lid: int, d: dict):
    upd = {k: d[k] for k in ("starred", "note", "email") if k in d}
    if not upd:
        return
    with _db(write=True) as c:
        c.execute(f"UPDATE leads SET {','.join(f'{k}=?' for k in upd)} WHERE id=?", (*upd.values(), lid))


def delete_leads(ids):
    if not ids:
        return
    with _db(write=True) as c:
        q = ",".join("?" * len(ids))
        c.execute(f"DELETE FROM leads WHERE id IN ({q})", tuple(ids))
        c.execute(f"DELETE FROM search_leads WHERE lead_id IN ({q})", tuple(ids))


def mark_exported(ids):
    with _db(write=True) as c:
        c.executemany("UPDATE leads SET exported=1 WHERE id=?", [(i,) for i in ids])


def stats() -> dict:
    with _db() as c:
        r = c.execute("""SELECT COUNT(*) n, SUM(email<>'') e, SUM(phone<>'') p, SUM(website<>'') w,
                                COUNT(DISTINCT NULLIF(country,'')) countries, SUM(exported) x
                         FROM leads""").fetchone()
        s = c.execute("SELECT COUNT(*) FROM searches").fetchone()[0]
    return {"leads": r["n"] or 0, "emails": r["e"] or 0, "phones": r["p"] or 0, "websites": r["w"] or 0,
            "countries": r["countries"] or 0, "exported": r["x"] or 0, "searches": s}


# --------------------------------------------------------------------------- #
# website discovery / decision makers / mailbox checks
# --------------------------------------------------------------------------- #
def leads_without_website(search_id: int, limit: int = 100000) -> list[dict]:
    with _db() as c:
        return [_row(r) for r in c.execute(
            """SELECT l.* FROM leads l JOIN search_leads s ON s.lead_id=l.id
               WHERE s.search_id=? AND l.website='' AND l.web_status='' AND l.name<>'' LIMIT ?""",
            (search_id, limit))]


def set_website(lid: int, url: str | None, how: str):
    with _db(write=True) as c:
        if not url:
            c.execute("UPDATE leads SET web_status='none' WHERE id=?", (lid,))
            return
        dom = domain_of(url)
        c.execute("""UPDATE leads SET website=?, domain=?, website_src=?, web_status='found',
                     enrich_status=CASE WHEN enrich_status IN ('none','') THEN 'pending' ELSE enrich_status END,
                     updated_at=? WHERE id=?""", (url, dom, how, time.time(), lid))
        _rescore(c, lid)


def leads_needing_people(search_id: int) -> list[dict]:
    with _db() as c:
        return [dict(r) for r in c.execute(
            """SELECT l.id, l.reg_id FROM leads l JOIN search_leads s ON s.lead_id=l.id
               WHERE s.search_id=? AND (l.reg_id LIKE 'NO:%' OR l.reg_id LIKE 'GB:%') AND l.people='[]'""",
            (search_id,))]


def add_people(lid: int, ppl: list[dict]):
    with _db(write=True) as c:
        r = c.execute("SELECT * FROM leads WHERE id=?", (lid,)).fetchone()
        if not r:
            return
        cur = _row(r)
        merged, _ = people_mod.infer(_merge_people(cur["people"], ppl), cur["emails"], cur["domain"])
        c.execute("UPDATE leads SET people=?, updated_at=? WHERE id=?", (json.dumps(merged), time.time(), lid))
        _rescore(c, lid)


def skip_enrich_with_email(search_id: int) -> int:
    """'Visit websites: only when no email yet' — park the rest (Re-check still visits them)."""
    with _db(write=True) as c:
        return c.execute("""UPDATE leads SET enrich_status='skipped' WHERE enrich_status='pending' AND email<>''
                            AND id IN (SELECT lead_id FROM search_leads WHERE search_id=?)""",
                         (search_id,)).rowcount


def guessed_emails(lid: int) -> list[str]:
    with _db() as c:
        r = c.execute("SELECT people FROM leads WHERE id=?", (lid,)).fetchone()
    return [p["email"] for p in json.loads(r["people"] or "[]") if p.get("email_status") == "guessed"] if r else []


def set_email_status(lid: int, results: dict[str, str]):
    """Apply mailbox-check results; a guess the server rejected is dropped."""
    with _db(write=True) as c:
        r = c.execute("SELECT people, emails, email FROM leads WHERE id=?", (lid,)).fetchone()
        if not r:
            return
        ppl = json.loads(r["people"] or "[]")
        for p in ppl:
            st = results.get(p.get("email"))
            if st == "invalid" and p.get("email_status") == "guessed":
                p.pop("email", None)
                p.pop("email_status", None)
            elif st:
                p["email_check"] = st
        c.execute("UPDATE leads SET people=? WHERE id=?", (json.dumps(ppl), lid))
