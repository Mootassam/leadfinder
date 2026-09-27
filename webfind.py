"""
Find the website of a business that has none on file (typical for register
entries). Two ways, both verified before we accept anything:

1. Domain guessing — "Cabinet Dentaire Dupont" in France → cabinetdentairedupont.fr,
   cabinet-dentaire-dupont.fr, dupont-dentaire.fr … (DNS first, then the page).
2. Web search (optional, the user's own Brave Search API key).

A candidate counts only when the page shows the business name AND something
local (postcode, city or phone) — and is not a parked / for-sale domain.
"""

from __future__ import annotations

import re
import unicodedata
import urllib.parse

import requests

import enrich

try:
    import dns.resolver
except ImportError:
    dns = None

CCTLD = {"GB": "co.uk", "UK": "co.uk"}
LEGAL = re.compile(r"\b(sarl|sas|sasu|sa|eurl|sci|selarl|selas|scp|snc|sel|scm|gmbh|ag|kg|ug|ohg|ltd|limited|llc|"
                   r"llp|plc|inc|corp|bv|nv|vof|as|asa|ab|oy|oyj|aps|srl|spa|sl|slu|sprl|srl|kft|zrt|sp z o o|"
                   r"company|co|cie|et|and|und|the|de|du|des|la|le|les|l|d|of|der|die|das|van|von)\b")
GENERIC = {"cabinet", "dentaire", "dental", "clinic", "clinique", "centre", "center", "praxis", "dr", "docteur",
           "doctor", "restaurant", "hotel", "cafe", "bar", "salon", "studio", "agence", "agency", "group", "groupe",
           "services", "service", "consulting", "conseil", "office", "bureau", "atelier", "maison", "boutique",
           "shop", "store", "pharmacie", "pharmacy", "garage", "auto", "immobilier", "holding", "france", "norge"}
AGGREGATORS = re.compile(r"(pagesjaunes|doctolib|facebook|instagram|linkedin|yelp|tripadvisor|societe\.com|pappers|"
                         r"infogreffe|annuaire|verif\.com|manageo|kompass|proff\.no|gulesider|1881\.no|finder\.fi|"
                         r"fonecta|companieshouse|endole|yell\.com|google\.|bing\.|wikipedia|youtube|booking\.com|"
                         r"mappy|118000|118712|justacote|hoodspot|cylex|hotfrog|europages|dnb\.com|opencorporates)")
PARKED = re.compile(r"(domain (is )?for sale|buy this domain|this domain (may be|is) for sale|parked free|"
                    r"sedoparking|domain parking|parkingcrew|bodis|dan\.com|afternic|hugedomains|"
                    r"website coming soon|site en construction|under construction|nom de domaine .{0,20}r[ée]serv)", re.I)


def _fold(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9 ]+", " ", s)


def tokens(name: str) -> list[str]:
    t = LEGAL.sub(" ", _fold(name))
    return [w for w in t.split() if len(w) > 1]


# the profession word people put in their domain, per country (dupont-dentiste.fr)
TRADE_WORD = {
    "FR": {"dentist": "dentiste", "doctor": "medecin", "lawyer": "avocat", "accountant": "expert-comptable",
           "architect": "architecte", "physiotherapist": "kine", "veterinary": "veterinaire", "psychologist": "psychologue",
           "pharmacy": "pharmacie", "hairdresser": "coiffure", "real_estate": "immobilier", "plumber": "plombier",
           "electrician": "electricien", "photographer": "photographe", "optician": "opticien", "beauty": "institut"},
    "NO": {"dentist": "tannlege", "lawyer": "advokat", "accountant": "regnskap", "real_estate": "eiendom"},
    "FI": {"dentist": "hammas", "lawyer": "asianajo", "accountant": "tilitoimisto"},
    "GB": {"dentist": "dental", "lawyer": "solicitors", "accountant": "accountants"},
}
# professions whose council hosts member sites (dr-jean-dupont.chirurgiens-dentistes.fr)
COUNCIL_HOST = {("FR", "dentist"): "chirurgiens-dentistes.fr"}


def candidates(name: str, legal: str, cc: str, niche: str = "", person: bool = False) -> list[str]:
    cc = (cc or "").upper()
    tld = CCTLD.get(cc, (cc or "com").lower())
    trade = TRADE_WORD.get(cc, {}).get(niche, "")
    out = []

    def add(label, tlds=(tld, "com")):
        if 3 <= len(label) <= 45:
            for t in dict.fromkeys(tlds):
                d = f"{label}.{t}"
                if d not in out:
                    out.append(d)

    for nm in dict.fromkeys(x for x in (name, legal) if x):
        ws = tokens(re.sub(r"\(.*?\)", " ", nm))
        if not ws:
            continue
        core = [w for w in ws if w not in GENERIC]
        add("".join(ws))
        add("-".join(ws))
        if core and core != ws and (len(core) >= 2 or len(core[0]) >= 6):
            add("".join(core))
            add("-".join(core))
        if person and 2 <= len(ws) <= 4:
            first, last = ws[0], ws[-1]
            add(f"dr-{first}-{last}", (tld,))
            add(f"dr-{last}", (tld,))
            if (cc, niche) in COUNCIL_HOST:
                add(f"dr-{first}-{last}", (COUNCIL_HOST[(cc, niche)],))
            if trade:
                add(f"{last}-{trade}", (tld,))
                add(f"{trade}-{last}", (tld,))
        elif trade and core:
            add(f"{'-'.join(core)}-{trade}", (tld,))
    return out[:14]


def _resolves(domain: str) -> bool:
    if not dns:
        return True
    try:
        r = dns.resolver.Resolver()
        r.lifetime = 4
        r.resolve(domain, "A")
        return True
    except Exception:
        return False


def _page(url: str, timeout=8):
    try:
        r = requests.get(url, timeout=(5, timeout), allow_redirects=True, stream=True,
                         headers={"User-Agent": enrich.BROWSER_UA, "Accept": "text/html,*/*"})
        if r.status_code >= 400 or "html" not in r.headers.get("content-type", "html"):
            r.close()
            return None, ""
        body = r.raw.read(600_000, decode_content=True)
        r.close()
        return r.url, body.decode(r.encoding or "utf-8", errors="replace")
    except Exception:
        return None, ""


def matches(html: str, lead: dict) -> bool:
    """The page is this business: its name + one local detail, and not a parked domain."""
    if not html or PARKED.search(html[:20000]):
        return False
    text = _fold(re.sub(r"<[^>]+>", " ", html))
    words = set(text.split())
    for nm in (lead.get("name"), lead.get("legal_name")):
        ws = [w for w in tokens(nm or "") if w not in GENERIC] or tokens(nm or "")
        if ws and sum(w in words for w in ws) / len(ws) >= 0.67:
            break
    else:
        return False
    digits = re.sub(r"\D", "", text)
    pc = re.sub(r"\s", "", lead.get("postcode") or "").lower()
    ph = re.sub(r"\D", "", lead.get("phone") or "")[-6:]
    city = _fold(lead.get("city") or "").strip()
    return bool((pc and pc in text.replace(" ", "")) or (ph and len(ph) == 6 and ph in digits)
                or (city and len(city) > 2 and f" {city} " in f" {text} "))


def _is_person(lead: dict) -> bool:
    n = tokens(lead.get("name") or "")
    return any(tokens(p.get("name", ""))[-1:] == n[-1:] for p in lead.get("people") or [] if n and p.get("name"))


def guess(lead: dict) -> str | None:
    for dom in candidates(lead.get("name", ""), lead.get("legal_name", ""), lead.get("country_code", ""),
                          lead.get("niche_key", ""), _is_person(lead)):
        if not _resolves(dom):
            continue
        for scheme in ("https://", "http://"):
            final, html = _page(scheme + dom)
            if html:
                if matches(html, lead):
                    return final or scheme + dom
                break
    return None


def search(lead: dict, key: str) -> str | None:
    q = f'"{lead.get("name")}" {lead.get("city") or lead.get("postcode") or ""}'.strip()
    try:
        r = requests.get("https://api.search.brave.com/res/v1/web/search", timeout=20,
                         headers={"X-Subscription-Token": key, "Accept": "application/json"},
                         params={"q": q, "count": 8})
        if r.status_code != 200:
            return None
        results = r.json().get("web", {}).get("results", [])
    except Exception:
        return None
    for it in results:
        url = it.get("url", "")
        host = urllib.parse.urlparse(url).netloc.lower()
        if not host or AGGREGATORS.search(host):
            continue
        final, html = _page(url)
        if matches(html, lead):
            p = urllib.parse.urlparse(final or url)
            return f"{p.scheme}://{p.netloc}/"
    return None


def find(lead: dict, brave_key: str = "") -> tuple[str, str] | None:
    """→ (website, how) or None"""
    url = guess(lead)
    if url:
        return url, "guessed"
    if brave_key:
        url = search(lead, brave_key)
        if url:
            return url, "search"
    return None
