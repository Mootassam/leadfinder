"""
Official business registers — every *registered* company in an area, including
the ones that never appear on a map. Each returns plain lead dicts.

* FR  Annuaire des entreprises (INSEE SIRENE + RNE) — no key; establishments
      with GPS, trade names, directors.
* NO  Brønnøysund Enhetsregisteret — no key; often email / phone / website;
      owners & board members via the roles endpoint.
* FI  PRH / YTJ open data — no key; website when registered.
* GB  Companies House — free API key (Settings); officers = decision makers.

Big areas are split (region → départements / fylker, city → postcodes …) so a
query never hits a register's result cap.
"""

from __future__ import annotations

import base64
import re
import threading
import time

import requests

import taxonomy

UA = "LeadFinder/1.0 (local desktop lead research app)"
_S = requests.Session()
_S.headers["User-Agent"] = UA

SUPPORTED = {"FR": "France (SIRENE)", "NO": "Norway (Brønnøysund)", "FI": "Finland (PRH)",
             "GB": "United Kingdom (Companies House — free key)"}


class Cancelled(Exception):
    pass


class _Rate:
    def __init__(self, per_sec):
        self.gap, self.last, self.lock = 1.0 / per_sec, 0.0, threading.Lock()

    def wait(self):
        with self.lock:
            d = self.gap - (time.time() - self.last)
            if d > 0:
                time.sleep(d)
            self.last = time.time()


_RATES = {"FR": _Rate(6), "NO": _Rate(8), "FI": _Rate(4), "GB": _Rate(2)}


def supported(cc: str) -> bool:
    return (cc or "").upper() in SUPPORTED


# Global sources (work for any country, so they are not keyed by country code).
GLOBAL_SOURCES = {"opencorporates": "OpenCorporates (worldwide registries)",
                  "wikidata": "Wikidata (notable companies, any country)"}


def _get(cc, url, cancel, **kw):
    for attempt in range(5):
        if cancel.is_set():
            raise Cancelled()
        _RATES[cc].wait()
        try:
            r = _S.get(url, timeout=40, **kw)
        except requests.RequestException:
            time.sleep(2 + attempt * 3)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(3 + attempt * 5)
            continue
        return r
    raise RuntimeError(f"{SUPPORTED[cc]} is not answering right now")


def _title(s: str) -> str:
    s = (s or "").strip()
    if s and s.upper() == s:
        s = re.sub(r"\b([A-Za-zÀ-ÿ])([A-Za-zÀ-ÿ']*)", lambda m: m.group(1).upper() + m.group(2).lower(), s)
        s = re.sub(r"\b(Sas|Sarl|Sa|Eurl|Sasu|Sci|Selarl|Scp|Snc|Sel|As|Asa|Oy|Oyj|Ab|Ltd|Llp|Plc)\b",
                   lambda m: m.group(1).upper(), s)
    return s


def search(cc: str, m: dict, geo: dict, settings: dict, cancel, log, on_batch) -> int:
    cc = cc.upper()
    fn = {"FR": _fr, "NO": _no, "FI": _fi, "GB": _gb}[cc]
    return fn(m, geo, settings, cancel, log, on_batch)


# --------------------------------------------------------------------------- #
# France — recherche-entreprises.api.gouv.fr
# --------------------------------------------------------------------------- #
FR_API = "https://recherche-entreprises.api.gouv.fr/search"
FR_EFFECTIF = {"00": "0", "01": "1-2", "02": "3-5", "03": "6-9", "11": "10-19", "12": "20-49", "21": "50-99",
               "22": "100-199", "31": "200-249", "32": "250-499", "41": "500-999", "42": "1000-1999",
               "51": "2000-4999", "52": "5000-9999", "53": "10000+"}
FR_SECTIONS = list("ABCDEFGHIJKLMNOPQRSU")
FR_CAP = 9975  # the API pages through at most ~10,000 results per query


def _geo_fr(path, **params):
    r = _S.get("https://geo.api.gouv.fr/" + path, params=params, timeout=30)
    r.raise_for_status()
    return r.json()


def _fr_locations(geo) -> list[dict]:
    kind = geo.get("kind", "")
    dep = re.search(r"FR-(\d[0-9AB])", geo.get("iso6", "") or "")
    if kind in ("city", "town", "village", "municipality", "suburb", "city_district", "borough", "hamlet",
                "quarter", "neighbourhood", "postcode"):
        c = _geo_fr("communes", lat=geo["lat"], lon=geo["lon"], fields="code,nom,codesPostaux")
        if c:
            return [{"code_postal": ",".join(c[0]["codesPostaux"])}] if c[0].get("codesPostaux") \
                else [{"code_commune": c[0]["code"]}]
    if kind in ("county", "state_district", "department") and dep:
        return [{"departement": dep.group(1)}]
    if kind in ("state", "region"):
        regs = _geo_fr("regions", nom=geo.get("name", ""), fields="code")
        if regs:
            return [{"region": regs[0]["code"]}]
    if kind == "country":
        return [{}]
    if dep:
        return [{"departement": dep.group(1)}]
    return [{}]


def _fr_split(loc: dict, act: dict) -> list[tuple[dict, dict]]:
    """Refine a query that has more results than the API will page through."""
    if not loc or "region" in loc:
        deps = _geo_fr(f"regions/{loc['region']}/departements" if loc else "departements", fields="code")
        return [({"departement": d["code"]}, act) for d in deps]
    if "departement" in loc:
        pcs = sorted({p for c in _geo_fr(f"departements/{loc['departement']}/communes", fields="codesPostaux")
                      for p in c.get("codesPostaux", [])})
        return [({"code_postal": ",".join(pcs[i:i + 8])}, act) for i in range(0, len(pcs), 8)]
    if "code_postal" in loc and "," in loc["code_postal"]:
        return [({"code_postal": p}, act) for p in loc["code_postal"].split(",")]
    if not act.get("activite_principale") and not act.get("section_activite_principale"):
        return [(loc, {"section_activite_principale": s}) for s in FR_SECTIONS]
    return []


def _fr(m, geo, settings, cancel, log, on_batch) -> int:
    act = {} if m["key"] == "all" else {"activite_principale": ",".join(taxonomy.activity_codes(m["key"], "naf"))}
    if m["key"] != "all" and not act["activite_principale"]:
        log("French register: no official activity code for this business type — skipped.")
        return 0
    queue = [(loc, act) for loc in _fr_locations(geo)]
    seen, total = set(), 0
    while queue:
        loc, a = queue.pop(0)
        params = {**loc, **a, "etat_administratif": "A", "per_page": 25, "limite_matching_etablissements": 100}
        r = _get("FR", FR_API, cancel, params={**params, "page": 1})
        if r.status_code != 200:
            log(f"French register: {r.text[:160]}", "warn")
            continue
        j = r.json()
        n = j.get("total_results") or 0
        if n > FR_CAP:
            parts = _fr_split(loc, a)
            if parts:
                queue = parts + queue
                continue
            log(f"French register: {n:,} companies in one slice — reading the first {FR_CAP:,}.", "warn")
        pages = min(j.get("total_pages") or 1, FR_CAP // 25)
        where = ", ".join(f"{v[:40]}" for v in loc.values()) or "France"
        log(f"French register: {n:,} companies ({where}).")
        for page in range(1, pages + 1):
            if page > 1:
                r = _get("FR", FR_API, cancel, params={**params, "page": page})
                if r.status_code != 200:
                    break
                j = r.json()
            batch = []
            for co in j.get("results", []):
                people = [{"name": _title(f"{d.get('prenoms', '').split(' ')[0]} {d.get('nom', '')}"),
                           "role": d.get("qualite") or "Director", "source": "French register"}
                          for d in co.get("dirigeants") or [] if d.get("type_dirigeant") == "personne physique"
                          and d.get("nom")][:6]
                for e in co.get("matching_etablissements") or []:
                    if e.get("etat_administratif") != "A" or e.get("statut_diffusion_etablissement") == "P":
                        continue
                    if e["siret"] in seen:
                        continue
                    seen.add(e["siret"])
                    trade = e.get("nom_commercial") or (e.get("liste_enseignes") or [None])[0]
                    legal = co.get("nom_raison_sociale") or co.get("nom_complet") or ""
                    try:
                        lat, lon = float(e.get("latitude")), float(e.get("longitude"))
                    except (TypeError, ValueError):
                        lat = lon = None
                    batch.append({
                        "name": _title(trade or re.sub(r"\s*\(.*\)$", "", co.get("nom_complet") or legal)),
                        "legal_name": _title(legal), "category": m["label"] if m["key"] != "all" else
                        (e.get("activite_principale") or ""), "address": _title(e.get("adresse") or ""),
                        "city": _title(e.get("libelle_commune") or ""), "postcode": e.get("code_postal") or "",
                        "country": "France", "country_code": "FR", "lat": lat, "lon": lon,
                        "reg_id": "FR:" + e["siret"], "company_id": co.get("siren", ""),
                        "employees": FR_EFFECTIF.get(e.get("tranche_effectif_salarie") or "", ""),
                        "founded": e.get("date_creation") or co.get("date_creation") or "",
                        "people": people, "sources": ["Registry FR"],
                    })
            total += len(batch)
            if batch:
                on_batch(batch)
            if page % 20 == 0:
                log(f"French register: page {page}/{pages} — {total:,} establishments so far.")
    return total


# --------------------------------------------------------------------------- #
# Norway — data.brreg.no
# --------------------------------------------------------------------------- #
NO_API = "https://data.brreg.no/enhetsregisteret/api/enheter"
NO_GEO = "https://ws.geonorge.no/kommuneinfo/v1/"


def _no_locations(geo):
    kind = geo.get("kind", "")
    if kind == "country":
        return [None]
    if kind in ("state", "county", "region"):
        fy = re.search(r"NO-(\d+)", geo.get("iso4", "") or "")
        if fy:
            j = _S.get(NO_GEO + f"fylker/{fy.group(1)}", timeout=30).json()
            return [",".join(k["kommunenummer"] for k in j.get("kommuner", []))]
    j = _S.get(NO_GEO + "punkt", params={"nord": geo["lat"], "ost": geo["lon"], "koordsys": 4258}, timeout=30).json()
    return [j["kommunenummer"]] if j.get("kommunenummer") else [None]


def _no(m, geo, settings, cancel, log, on_batch) -> int:
    codes = [] if m["key"] == "all" else taxonomy.activity_codes(m["key"], "nace")
    if m["key"] != "all" and not codes:
        log("Norwegian register: no official activity code for this business type — skipped.")
        return 0
    queue = [(k, codes) for k in _no_locations(geo)]
    total = 0
    while queue:
        kom, cds = queue.pop(0)
        base = {"size": 100, "konkurs": "false", "underAvvikling": "false"}
        if kom:
            base["kommunenummer"] = kom
        if cds:
            base["naeringskode"] = ",".join(cds)
        r = _get("NO", NO_API, cancel, params={**base, "page": 0})
        if r.status_code != 200:
            log(f"Norwegian register: {r.text[:160]}", "warn")
            continue
        j = r.json()
        n = j.get("page", {}).get("totalElements", 0)
        if n > 9900:
            if kom is None:
                fy = _S.get(NO_GEO + "kommuner", timeout=30).json()
                queue = [(k["kommunenummer"], cds) for k in fy] + queue
                continue
            if "," in kom:
                queue = [(k, cds) for k in kom.split(",")] + queue
                continue
            log(f"Norwegian register: {n:,} companies in one slice — reading the first 9,900.", "warn")
        log(f"Norwegian register: {n:,} companies.")
        pages = min(j.get("page", {}).get("totalPages", 1), 99)
        for page in range(pages):
            if page:
                r = _get("NO", NO_API, cancel, params={**base, "page": page})
                if r.status_code != 200:
                    break
                j = r.json()
            batch = []
            for e in j.get("_embedded", {}).get("enheter", []):
                a = e.get("forretningsadresse") or e.get("postadresse") or {}
                web = e.get("hjemmeside") or ""
                phones = [p for p in (e.get("telefon"), e.get("mobil")) if p]
                em = (e.get("epostadresse") or "").strip().lower()
                batch.append({
                    "name": _title(e.get("navn", "")), "legal_name": _title(e.get("navn", "")),
                    "category": (e.get("naeringskode1") or {}).get("beskrivelse", "") or m["label"],
                    "address": ", ".join(x for x in (" ".join(a.get("adresse") or []),
                                                     f"{a.get('postnummer', '')} {_title(a.get('poststed', ''))}".strip()) if x),
                    "city": _title(a.get("poststed") or a.get("kommune") or ""), "postcode": a.get("postnummer", ""),
                    "country": "Norway", "country_code": "NO",
                    "website": ("http://" + web) if web and not web.startswith("http") else web,
                    "phone": phones[0] if phones else "", "phones": phones, "emails": [em] if "@" in em else [],
                    "reg_id": "NO:" + e["organisasjonsnummer"], "company_id": e["organisasjonsnummer"],
                    "employees": str(e.get("antallAnsatte") or "") if e.get("harRegistrertAntallAnsatte") else "",
                    "founded": e.get("stiftelsesdato") or e.get("registreringsdatoEnhetsregisteret") or "",
                    "sources": ["Registry NO"],
                })
            total += len(batch)
            if batch:
                on_batch(batch)
    return total


# --------------------------------------------------------------------------- #
# Finland — avoindata.prh.fi
# --------------------------------------------------------------------------- #
FI_API = "https://avoindata.prh.fi/opendata-ytj-api/v3/companies"


def _fi(m, geo, settings, cancel, log, on_batch) -> int:
    codes = [None] if m["key"] == "all" else taxonomy.activity_codes(m["key"], "tol")
    if not codes:
        log("Finnish register: no official activity code for this business type — skipped.")
        return 0
    loc = None if geo.get("kind") == "country" else (geo.get("city") or geo.get("name"))
    total = 0
    for code in codes:
        params = {k: v for k, v in (("mainBusinessLine", code), ("location", loc)) if v}
        page = 1
        while True:
            r = _get("FI", FI_API, cancel, params={**params, "page": page})
            if r.status_code != 200:
                log(f"Finnish register: {r.text[:160]}", "warn")
                break
            j = r.json()
            if page == 1:
                log(f"Finnish register: {j.get('totalResults', 0):,} companies"
                    f"{' for ' + code if code else ''}.")
            batch = []
            for c in j.get("companies", []):
                if str(c.get("status")) not in ("2", "") or c.get("endDate"):
                    continue
                names = [n for n in c.get("names", []) if not n.get("endDate")]
                legal = next((n["name"] for n in names if str(n.get("type")) == "1"), names[0]["name"] if names else "")
                trade = next((n["name"] for n in names if str(n.get("type")) == "3"), "")
                a = next((x for x in c.get("addresses", []) if x.get("type") == 1), (c.get("addresses") or [{}])[0])
                city = next((p["city"] for p in a.get("postOffices", []) if p.get("languageCode") == "1"), "")
                web = (c.get("website") or {}).get("url", "")
                batch.append({
                    "name": _title(trade or legal), "legal_name": legal,
                    "category": next((d["description"] for d in (c.get("mainBusinessLine") or {}).get("descriptions", [])
                                      if d.get("languageCode") == "3"), m["label"]),
                    "address": ", ".join(x for x in (f"{a.get('street', '')} {a.get('buildingNumber', '')}".strip(),
                                                     f"{a.get('postCode', '')} {_title(city)}".strip()) if x),
                    "city": _title(city), "postcode": a.get("postCode", ""), "country": "Finland", "country_code": "FI",
                    "website": ("http://" + web) if web and not web.startswith("http") else web,
                    "reg_id": "FI:" + c["businessId"]["value"], "company_id": c["businessId"]["value"],
                    "founded": c.get("registrationDate", ""), "sources": ["Registry FI"],
                })
            total += len(batch)
            if batch:
                on_batch(batch)
            if len(j.get("companies", [])) < 100 or page >= 100:
                break
            page += 1
    return total


# --------------------------------------------------------------------------- #
# United Kingdom — Companies House (free key)
# --------------------------------------------------------------------------- #
GB_API = "https://api.company-information.service.gov.uk"


def _gb_auth(key):
    return {"Authorization": "Basic " + base64.b64encode(f"{key}:".encode()).decode()}


def _gb(m, geo, settings, cancel, log, on_batch) -> int:
    key = (settings.get("companies_house_key") or "").strip()
    if not key:
        log("UK register skipped — add a free Companies House API key in Settings.", "warn")
        return 0
    sic = [] if m["key"] == "all" else taxonomy.activity_codes(m["key"], "sic_uk")
    params = {"company_status": "active", "size": 5000}
    if geo.get("kind") != "country":
        params["location"] = geo.get("city") or geo.get("name")
    if sic:
        params["sic_codes"] = ",".join(sic)
    total, start = 0, 0
    while True:
        r = _get("GB", GB_API + "/advanced-search/companies", cancel, params={**params, "start_index": start},
                 headers=_gb_auth(key))
        if r.status_code == 401:
            log("Companies House rejected the API key.", "error")
            return total
        if r.status_code == 404:
            break
        if r.status_code != 200:
            log(f"Companies House: {r.text[:160]}", "warn")
            break
        j = r.json()
        items = j.get("items", [])
        if start == 0:
            log(f"UK register: {j.get('hits', len(items)):,} companies.")
        batch = []
        for c in items:
            a = c.get("registered_office_address") or {}
            batch.append({
                "name": _title(c.get("company_name", "")), "legal_name": _title(c.get("company_name", "")),
                "category": m["label"] if m["key"] != "all" else ", ".join(c.get("sic_codes") or []),
                "address": ", ".join(x for x in (a.get("address_line_1"), a.get("address_line_2"), a.get("locality"),
                                                 a.get("postal_code")) if x),
                "city": _title(a.get("locality", "")), "postcode": a.get("postal_code", ""),
                "country": "United Kingdom", "country_code": "GB",
                "reg_id": "GB:" + c["company_number"], "company_id": c["company_number"],
                "founded": c.get("date_of_creation", ""), "sources": ["Registry GB"],
            })
        total += len(batch)
        if batch:
            on_batch(batch)
        if len(items) < params["size"] or start + len(items) >= 10000:
            break
        start += len(items)
    return total


# --------------------------------------------------------------------------- #
# OpenCorporates — worldwide company registry aggregator (optional free token)
# --------------------------------------------------------------------------- #
OC_API = "https://api.opencorporates.com/v0.4/companies/search"
_OC_RATE = _Rate(2)

# Countries OpenCorporates indexes under a single ISO-alpha2 jurisdiction code.
_OC_SINGLE_JUR = set("gb fr de es it nl be pt ie dk se no fi pl cz at ch gr hu ro sk si "
                     "bg hr ee lv lt lu mt cy is nz za sg hk".split())


def _oc_get(params, cancel):
    for attempt in range(5):
        if cancel.is_set():
            raise Cancelled()
        _OC_RATE.wait()
        try:
            r = _S.get(OC_API, params=params, timeout=40)
        except requests.RequestException:
            time.sleep(2 + attempt * 3)
            continue
        if r.status_code == 429 or r.status_code >= 500:
            time.sleep(3 + attempt * 5)
            continue
        return r
    raise RuntimeError("OpenCorporates is not answering right now")


def opencorporates(m, geo, settings, cancel, log, on_batch) -> int:
    token = (settings.get("opencorporates_token") or "").strip()
    if not token:
        log("OpenCorporates skipped — it needs a free API token (add one in Settings).", "warn")
        return 0
    cc = (geo.get("country_code") or "").lower()
    term = "" if m["key"] == "all" else (m.get("term") or m["label"])
    params = {"per_page": 100, "order": "score", "api_token": token}
    if cc in _OC_SINGLE_JUR:
        params["jurisdiction_code"] = cc
    elif cc:
        params["country_code"] = cc            # federated countries (us/ca/au…): filter by country
    if term:
        params["q"] = term
    total, page = 0, 1
    max_pages = 20 if token else 5            # the free tier without a token is limited
    while page <= max_pages:
        r = _oc_get({**params, "page": page}, cancel)
        if r.status_code == 401:
            log("OpenCorporates rejected the API token.", "warn")
            return total
        if r.status_code == 403:
            log("OpenCorporates: free limit reached — add a free API token in Settings for more.", "warn")
            return total
        if r.status_code != 200:
            log(f"OpenCorporates: {r.text[:160]}", "warn")
            return total
        try:
            res = r.json().get("results", {})
        except ValueError:
            break
        companies = res.get("companies", [])
        if page == 1:
            log(f"OpenCorporates: {res.get('total_count', len(companies)):,} companies"
                f"{' for ' + term if term else ''}.")
        batch = []
        for wrap in companies:
            co = wrap.get("company") or {}
            if co.get("inactive") or co.get("dissolution_date"):
                continue
            jur = co.get("jurisdiction_code") or ""
            num = co.get("company_number") or ""
            if not num:
                continue
            ra = co.get("registered_address") or {}
            batch.append({
                "name": _title(co.get("name", "")), "legal_name": _title(co.get("name", "")),
                "category": m["label"] if m["key"] != "all" else (co.get("company_type") or ""),
                "address": co.get("registered_address_in_full") or "",
                "city": _title(ra.get("locality") or ""), "postcode": ra.get("postal_code") or "",
                "country": ra.get("country") or geo.get("country", ""),
                "country_code": (jur.split("_")[0] or geo.get("country_code", "")).upper(),
                "reg_id": f"OC:{jur}/{num}", "company_id": num,
                "founded": co.get("incorporation_date") or "",
                "maps_url": co.get("opencorporates_url") or co.get("registry_url") or "",
                "sources": ["OpenCorporates"],
            })
        total += len(batch)
        if batch:
            on_batch(batch)
        if len(companies) < 100:
            break
        page += 1
    return total


# --------------------------------------------------------------------------- #
# Wikidata — notable companies anywhere, located inside the search area (SPARQL)
# --------------------------------------------------------------------------- #
WD_API = "https://query.wikidata.org/sparql"
_WD_RATE = _Rate(1)
# instance-of values that mean "a company/business"
_WD_TYPES = "wd:Q4830453 wd:Q6881511 wd:Q783794 wd:Q891723 wd:Q18388277 wd:Q210167 wd:Q43229"


def _wd_query(bbox, term, cap):
    s, w, n, e = bbox
    flt = ""
    if term:
        t = term.lower().replace('"', "")
        flt = (f'  ?item rdfs:label ?lbl . FILTER(LANG(?lbl)="en")\n'
               f'  OPTIONAL {{ ?item wdt:P452 ?ind . ?ind rdfs:label ?indL . FILTER(LANG(?indL)="en") }}\n'
               f'  FILTER(CONTAINS(LCASE(?lbl), "{t}") || CONTAINS(LCASE(COALESCE(?indL,"")), "{t}"))\n')
    return (
        "SELECT ?item ?itemLabel ?website ?coord ?countryLabel ?indLabel WHERE {\n"
        "  SERVICE wikibase:box {\n"
        "    ?item wdt:P625 ?coord .\n"
        f'    bd:serviceParam wikibase:cornerSouthWest "Point({w} {s})"^^geo:wktLiteral .\n'
        f'    bd:serviceParam wikibase:cornerNorthEast "Point({e} {n})"^^geo:wktLiteral .\n'
        "  }\n"
        f"  VALUES ?type {{ {_WD_TYPES} }}\n"
        "  ?item wdt:P31 ?type .\n"
        "  OPTIONAL { ?item wdt:P856 ?website. }\n"
        "  OPTIONAL { ?item wdt:P17 ?country. }\n"
        "  OPTIONAL { ?item wdt:P452 ?industry. }\n"
        f"{flt}"
        '  SERVICE wikibase:label { bd:serviceParam wikibase:language "en". }\n'
        f"}} LIMIT {cap}"
    )


def wikidata(m, geo, settings, cancel, log, on_batch) -> int:
    bbox = geo.get("bbox")
    if not bbox:
        return 0
    term = "" if m["key"] == "all" else (m.get("term") or m["label"])
    cap = int(settings.get("wikidata_max") or 1500)
    if cancel.is_set():
        raise Cancelled()
    _WD_RATE.wait()
    try:
        r = _S.get(WD_API, params={"query": _wd_query(bbox, term, cap), "format": "json"},
                   headers={"Accept": "application/sparql-results+json"}, timeout=90)
    except requests.RequestException as ex:
        log(f"Wikidata: {type(ex).__name__} — skipped.", "warn")
        return 0
    if r.status_code != 200:
        log(f"Wikidata: query failed ({r.status_code}) — skipped.", "warn")
        return 0
    try:
        rows = r.json().get("results", {}).get("bindings", [])
    except ValueError:
        return 0
    log(f"Wikidata: {len(rows):,} notable companies in this area"
        f"{' matching ' + term if term else ''}.")
    seen, batch = set(), []
    for b in rows:
        qid = b.get("item", {}).get("value", "").rsplit("/", 1)[-1]
        if not qid or qid in seen:
            continue
        seen.add(qid)
        name = b.get("itemLabel", {}).get("value", "")
        if not name or name == qid:
            continue
        lat = lon = None
        coord = b.get("coord", {}).get("value", "")
        mm = re.match(r"Point\(([-\d.]+) ([-\d.]+)\)", coord)
        if mm:
            lon, lat = float(mm.group(1)), float(mm.group(2))
        web = b.get("website", {}).get("value", "")
        batch.append({
            "name": name, "legal_name": name,
            "category": m["label"] if m["key"] != "all" else b.get("indLabel", {}).get("value", ""),
            "country": b.get("countryLabel", {}).get("value", "") or geo.get("country", ""),
            "country_code": geo.get("country_code", ""), "lat": lat, "lon": lon,
            "website": web, "reg_id": f"WD:{qid}", "company_id": qid,
            "maps_url": f"https://www.wikidata.org/wiki/{qid}", "sources": ["Wikidata"],
        })
    if batch:
        on_batch(batch)
    return len(batch)


# --------------------------------------------------------------------------- #
# decision makers for registry leads (called per lead during enrichment)
# --------------------------------------------------------------------------- #
def people(reg_id: str, settings: dict, cancel) -> list[dict] | None:
    cc, _, num = (reg_id or "").partition(":")
    try:
        if cc == "NO":
            r = _get("NO", f"{NO_API}/{num}/roller", cancel)
            if r.status_code != 200:
                return None
            out = []
            for g in r.json().get("rollegrupper", []):
                for ro in g.get("roller", []):
                    p = ro.get("person") or {}
                    n = p.get("navn") or {}
                    if ro.get("avregistrert") or p.get("erDoed") or not n:
                        continue
                    out.append({"name": " ".join(x for x in (n.get("fornavn"), n.get("mellomnavn"), n.get("etternavn")) if x),
                                "role": (ro.get("type") or {}).get("beskrivelse", ""), "source": "Norwegian register"})
            return out[:8]
        if cc == "GB":
            key = (settings.get("companies_house_key") or "").strip()
            if not key:
                return None
            r = _get("GB", f"{GB_API}/company/{num}/officers", cancel, headers=_gb_auth(key),
                     params={"items_per_page": 20})
            if r.status_code != 200:
                return None
            out = []
            for o in r.json().get("items", []):
                if o.get("resigned_on"):
                    continue
                nm = o.get("name", "")
                if "," in nm:
                    last, first = nm.split(",", 1)
                    nm = f"{first.strip()} {last.strip()}"
                out.append({"name": _title(nm), "role": (o.get("officer_role") or "").replace("-", " "),
                            "source": "Companies House"})
            return out[:8]
    except Cancelled:
        raise
    except Exception:
        return None
    return None
