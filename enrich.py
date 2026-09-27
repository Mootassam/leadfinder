"""
Website enrichment: visit a business's own site (home + contact / about /
imprint / team pages) and read the public contact details it publishes —
emails (incl. obfuscated and Cloudflare-protected ones), phone numbers, social
profiles, title, description, language. Then check the email domain has MX.
"""

from __future__ import annotations

import codecs
import html as htmllib
import re
import threading
import urllib.parse

import requests

import people as people_mod

try:
    import dns.resolver
except ImportError:  # optional
    dns = None

BROWSER_UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) "
              "Chrome/126.0 Safari/537.36")
MAX_BYTES = 1_500_000

EMAIL_RE = re.compile(r"(?<![\w.+-])([a-z0-9][a-z0-9._%+-]{0,63}@[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
                      r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*\.[a-z]{2,24})(?![\w-])", re.I)
OBFUSC_RE = re.compile(r"([a-z0-9._%+-]{2,64})\s*(?:\[|\(|\{|\s)\s*(?:at|arobase|@)\s*(?:\]|\)|\}|\s)\s*"
                       r"([a-z0-9-]{2,63})\s*(?:\[|\(|\{|\s)\s*(?:dot|point|punkt|\.)\s*(?:\]|\)|\}|\s)\s*([a-z]{2,24})",
                       re.I)
CFEMAIL_RE = re.compile(r'data-cfemail="([0-9a-f]+)"', re.I)
CF_HREF_RE = re.compile(r"/cdn-cgi/l/email-protection#([0-9a-f]+)", re.I)
MAILTO_RE = re.compile(r'href\s*=\s*["\']mailto:([^"\'?]+)', re.I)
TEL_RE = re.compile(r'href\s*=\s*["\']tel:([^"\']+)', re.I)
HREF_RE = re.compile(r'<a\b[^>]*?href\s*=\s*["\']([^"\'#]+)["\'][^>]*>(.*?)</a>', re.I | re.S)
TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.I | re.S)
DESC_RE = re.compile(r'<meta[^>]+(?:name|property)\s*=\s*["\'](?:og:)?description["\'][^>]*content\s*=\s*["\']([^"\']*)',
                     re.I)
DESC_RE2 = re.compile(r'<meta[^>]+content\s*=\s*["\']([^"\']*)["\'][^>]*(?:name|property)\s*=\s*["\'](?:og:)?description',
                      re.I)
LANG_RE = re.compile(r"<html[^>]*\blang\s*=\s*[\"']?([a-z]{2})", re.I)
JSONLD_EMAIL = re.compile(r'"email"\s*:\s*"(?:mailto:)?([^"]+@[^"]+)"', re.I)
JSONLD_PHONE = re.compile(r'"telephone"\s*:\s*"([^"]{6,30})"', re.I)
TAGS_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>|<[^>]+>", re.I | re.S)

SOCIAL = {
    "facebook": r"(?:^|\.)facebook\.com$|(?:^|\.)fb\.com$",
    "instagram": r"(?:^|\.)instagram\.com$",
    "linkedin": r"(?:^|\.)linkedin\.com$",
    "twitter": r"(?:^|\.)(?:twitter|x)\.com$",
    "youtube": r"(?:^|\.)youtube\.com$|^youtu\.be$",
    "tiktok": r"(?:^|\.)tiktok\.com$",
    "pinterest": r"(?:^|\.)pinterest\.[a-z.]+$",
    "whatsapp": r"^wa\.me$|(?:^|\.)whatsapp\.com$",
    "telegram": r"^t\.me$",
    "yelp": r"(?:^|\.)yelp\.[a-z.]+$",
    "tripadvisor": r"(?:^|\.)tripadvisor\.[a-z.]+$",
}
SOCIAL_SKIP = re.compile(r"/(sharer|share|intent|plugins|dialog|hashtag|tr\?|policy|privacy|legal|help|login|"
                         r"watch\?|embed|search)|facebook\.com/?$|instagram\.com/?$", re.I)

# pages that usually carry contact details, in many languages
CONTACT_WORDS = re.compile(
    r"contact|kontakt|contacto|contatti|contato|kontakta|yhteys|impressum|imprint|legal|mentions|"
    r"about|uber-uns|ueber-uns|a-propos|qui-sommes|chi-siamo|quienes|sobre|over-ons|team|equipe|"
    r"our-team|staff|people|location|standort|find-us|reach|get-in-touch|nous-trouver|kontaktai|iletisim|"
    r"%d8%a7%d8%aa%d8%b5%d9%84|اتصل|connect", re.I)
FALLBACK_PATHS = ("/contact", "/contact-us", "/kontakt", "/impressum", "/about", "/contacto", "/about-us")

BAD_EMAIL = re.compile(
    r"(\.(png|jpe?g|gif|svg|webp|css|js|ico|woff2?|ttf|pdf|mp4)$|@\dx\b|@[\d.]+$|"
    r"example\.|domain\.com$|yourdomain|sentry|wixpress|@sentry|godaddy|@email\.com$|@company\.com$|"
    r"noreply|no-reply|donotreply|do-not-reply|mailer-daemon|postmaster@|abuse@|"
    r"@(?:test|localhost)|^(?:name|email|user|your|you|firstname|lastname|vorname|nom|prenom|someone|"
    r"john\.?doe|jane\.?doe|max\.?mustermann|mustermann)@|@(?:mysite|website|site|votredomaine|ihredomain)\.|"
    r"cloudflare|u00|%[0-9a-f]{2}|\.(?:x|y|z)$|@(?:2x|3x)|wordpress\.(?:com|org)$|w3\.org|schema\.org|"
    r"placeholder|lorem|ipsum|@pp\.|@ingest\.|hubspot|mailchimp|sendgrid|amazonaws|googlegroups|"
    r"mustermann|musterfrau|@email\.(?:com|fr|de|es|it)$|@exceptions\.|^[0-9a-f]{20,}@|@sentry)", re.I)
ROLE = ("info", "contact", "hello", "office", "mail", "kontakt", "contacto", "hola", "bonjour", "admin",
        "sales", "support", "team", "enquiries", "inquiries", "reception", "booking", "bookings",
        "reservations", "service", "praxis", "cabinet", "secretariat")
LOW_VALUE = {"jobs", "job", "career", "careers", "karriere", "emploi", "recrutement", "recruiting", "recruitment",
             "hr", "rh", "bewerbung", "stage", "privacy", "dpo", "gdpr", "rgpd", "datenschutz", "dataprotection",
             "press", "presse", "media", "webmaster", "compliance", "whistleblowing", "investor", "investors"}

_MX_CACHE: dict[str, bool] = {}
_MX_LOCK = threading.Lock()


def _session(timeout):
    s = requests.Session()
    s.headers.update({"User-Agent": BROWSER_UA, "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                      "Accept-Language": "en,fr;q=0.8,de;q=0.7,es;q=0.6,*;q=0.5"})
    s.request_timeout = timeout
    return s


def _get(s, url):
    try:
        r = s.get(url, timeout=(6, s.request_timeout), allow_redirects=True, stream=True)
    except requests.exceptions.SSLError:
        if url.startswith("https://"):
            return _get(s, "http://" + url[8:])
        return None, None
    except requests.RequestException:
        return None, None
    ctype = r.headers.get("content-type", "")
    if r.status_code >= 400 or ("html" not in ctype and "text" not in ctype and ctype):
        r.close()
        return r, ""
    body = b""
    try:
        for chunk in r.iter_content(65536):
            body += chunk
            if len(body) > MAX_BYTES:
                break
    except requests.RequestException:
        pass
    r.close()
    enc = r.encoding if r.encoding and r.encoding.lower() != "iso-8859-1" else None
    try:
        text = body.decode(enc or "utf-8", errors="replace")
    except LookupError:
        text = body.decode("utf-8", errors="replace")
    return r, text


def _cf_decode(hexstr):
    try:
        key = int(hexstr[:2], 16)
        return "".join(chr(int(hexstr[i:i + 2], 16) ^ key) for i in range(2, len(hexstr), 2))
    except ValueError:
        return ""


def _clean_email(e):
    e = urllib.parse.unquote(htmllib.unescape(e or "")).strip().strip(".,;:'\"<>()[]").lower()
    e = e.removeprefix("mailto:").split("?")[0]
    if not EMAIL_RE.fullmatch(e) or BAD_EMAIL.search(e) or len(e) > 80:
        return ""
    return e


def extract_emails(html: str) -> list[str]:
    found = []

    def add(e):
        e = _clean_email(e)
        if e and e not in found:
            found.append(e)

    for m in MAILTO_RE.findall(html):
        for part in re.split(r"[,;]", m):
            add(part)
    for m in CFEMAIL_RE.findall(html) + CF_HREF_RE.findall(html):
        add(_cf_decode(m))
    for m in JSONLD_EMAIL.findall(html):
        add(m)
    text = htmllib.unescape(TAGS_RE.sub(" ", html))
    for m in _near_at(text):
        add(m)
    if OBFUSC_HINT.search(text):  # "name [at] domain [dot] com" — only worth the slow pattern when hinted
        for u, d, tld in OBFUSC_RE.findall(text):
            add(f"{u}@{d}.{tld}")
    # emails inside attributes / scripts (e.g. JSON configs) — last, least trusted
    for m in _near_at(html.replace("\\u0040", "@").replace("&#64;", "@").replace("&#x40;", "@")):
        add(m)
    return found


OBFUSC_HINT = re.compile(r"[\[({]\s*(?:at|arobase)\s*[\])}]|\s(?:at|arobase)\s+\S+\s+(?:dot|point|punkt)\s", re.I)


def _near_at(s: str) -> list[str]:
    """EMAIL_RE only where an '@' is — scanning a whole 1 MB page letter by letter is what made
    parsing slow enough to starve the app's own web pages."""
    out, pos = [], 0
    while True:
        i = s.find("@", pos)
        if i < 0:
            return out
        out += EMAIL_RE.findall(s, max(0, i - 70), i + 260)
        pos = i + 1


def trim_html(html: str) -> str:
    """Contact details live in headers and footers: huge pages keep their start and end."""
    return html if len(html) <= 600_000 else html[:450_000] + html[-150_000:]


# at most a few pages are parsed at once, so the app's own web pages always get CPU time
PARSE_SLOTS = threading.Semaphore(3)


def extract_phones(html: str) -> list[str]:
    out = []
    for p in TEL_RE.findall(html) + JSONLD_PHONE.findall(html):
        p = urllib.parse.unquote(p).strip()
        p = re.sub(r"[^\d+()\-. /]", "", p).strip()
        digits = re.sub(r"\D", "", p)
        if 7 <= len(digits) <= 15 and p not in out:
            out.append(p)
    return out


def extract_socials(html: str, base: str) -> dict:
    out = {}
    for href, _txt in HREF_RE.findall(html):
        href = htmllib.unescape(href.strip())
        if not href.startswith("http"):
            continue
        host = urllib.parse.urlparse(href).netloc.lower().removeprefix("www.").removeprefix("m.")
        for kind, pat in SOCIAL.items():
            if kind not in out and re.search(pat, host) and not SOCIAL_SKIP.search(href):
                path = urllib.parse.urlparse(href).path.strip("/")
                if path or kind in ("whatsapp",):
                    out[kind] = href.split("?")[0] if kind != "whatsapp" else href
    return out


def _contact_links(html: str, base: str, domain: str) -> list[str]:
    scored = []
    for href, txt in HREF_RE.findall(html):
        href = htmllib.unescape(href.strip())
        if href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        url = urllib.parse.urljoin(base, href)
        p = urllib.parse.urlparse(url)
        if p.scheme not in ("http", "https"):
            continue
        host = p.netloc.lower().removeprefix("www.")
        if host != domain and not host.endswith("." + domain):
            continue
        if re.search(r"\.(pdf|jpe?g|png|gif|zip|docx?|xlsx?|mp4|svg)$", p.path, re.I):
            continue
        label = TAGS_RE.sub(" ", txt)
        hit_path = CONTACT_WORDS.search(urllib.parse.unquote(p.path))
        hit_txt = CONTACT_WORDS.search(label)
        if hit_path or hit_txt:
            s = 0
            key = (p.path + " " + label).lower()
            if re.search(r"contact|kontakt|contacto|contatti|impressum|imprint", key):
                s += 10
            if re.search(r"impressum|imprint|mentions|legal", key):
                s += 4  # imprints (EU) are legally required to list an email
            if re.search(r"team|staff|people|about|uber", key):
                s += 3
            clean = urllib.parse.urlunparse(p._replace(fragment="", query=""))
            scored.append((s, clean))
    seen, out = set(), []
    for s, u in sorted(scored, key=lambda x: -x[0]):
        if u not in seen:
            seen.add(u)
            out.append(u)
    return out


def _rank_emails(emails: list[str], domain: str) -> list[str]:
    def key(e):
        local, _, dom = e.partition("@")
        own = dom == domain or dom.endswith("." + domain) or domain.endswith("." + dom)
        free = dom in ("gmail.com", "yahoo.com", "hotmail.com", "outlook.com", "gmx.de", "web.de", "orange.fr",
                       "wanadoo.fr", "free.fr", "icloud.com", "live.com", "hotmail.fr", "yahoo.fr", "aol.com",
                       "t-online.de", "libero.it", "mail.ru", "yandex.ru", "outlook.fr", "protonmail.com")
        head = local.split(".")[0].split("-")[0].split("_")[0]
        # 0 = general inbox, 1 = a person, 2 = a department that won't buy (jobs@, privacy@, press@…)
        rank = 2 if head in LOW_VALUE else 0 if head in ROLE else 1
        return (0 if own else 1 if free else 2, rank, len(e))
    return sorted(emails, key=key)


def has_mx(domain: str) -> bool | None:
    if not dns or not domain:
        return None
    with _MX_LOCK:
        if domain in _MX_CACHE:
            return _MX_CACHE[domain]
    ok = None
    try:
        res = dns.resolver.Resolver()
        res.lifetime = 6
        ok = len(res.resolve(domain, "MX")) > 0
    except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
        try:
            dns.resolver.resolve(domain, "A", lifetime=5)
            ok = True  # RFC 5321: falls back to the A record
        except Exception:
            ok = False
    except Exception:
        ok = None
    with _MX_LOCK:
        _MX_CACHE[domain] = ok
    return ok


def _parse(html: str, url: str, domain: str, want_links: bool = False):
    html = trim_html(html)
    with PARSE_SLOTS:
        return (extract_emails(html), extract_phones(html), extract_socials(html, url), people_mod.from_html(html),
                _contact_links(html, url, domain) if want_links else [])


def enrich_site(website: str, domain: str, max_pages: int = 6, timeout: int = 12, cancel=None) -> dict:
    s = _session(timeout)
    url = website if website.startswith("http") else "http://" + website
    info = {"ok": False, "status": "", "emails": [], "phones": [], "socials": {}, "pages": [], "people": []}
    r, html = _get(s, url)
    if r is None and not url.startswith("https://"):
        r, html = _get(s, "https://" + re.sub(r"^\w+://", "", url))
    if r is None:
        info["status"] = "dead"
        return info
    if not html:
        info["status"] = f"http {r.status_code}" if r.status_code >= 400 else "no html"
        if r.status_code in (401, 403, 429, 503):
            info["status"] = "blocked"
        return info
    final = r.url
    final_dom = urllib.parse.urlparse(final).netloc.lower().removeprefix("www.")
    info["ok"] = True
    info["status"] = "ok"
    info["final_url"] = final
    m = TITLE_RE.search(html)
    info["title"] = re.sub(r"\s+", " ", htmllib.unescape(m.group(1))).strip()[:200] if m else ""
    m = DESC_RE.search(html) or DESC_RE2.search(html)
    info["description"] = htmllib.unescape(m.group(1)).strip()[:400] if m else ""
    m = LANG_RE.search(html)
    info["language"] = m.group(1).lower() if m else ""

    emails, phones, socials, found_people, links = _parse(html, final, final_dom or domain, want_links=True)
    pages = [final]
    if not links:
        root = f"{urllib.parse.urlparse(final).scheme}://{urllib.parse.urlparse(final).netloc}"
        links = [root + p for p in FALLBACK_PATHS]
    tried = 0
    for link in links:
        if tried >= max_pages - 1 or (cancel and cancel.is_set()):
            break
        # stop early once we have a same-domain email and a contact page has been read
        if tried >= 2 and any(e.endswith("@" + domain) or e.endswith("@" + final_dom) for e in emails):
            break
        tried += 1
        r2, h2 = _get(s, link)
        if not h2:
            continue
        pages.append(r2.url)
        e2, p2, s2, pp2, _ = _parse(h2, r2.url, final_dom or domain)
        for e in e2:
            if e not in emails:
                emails.append(e)
                info.setdefault("contact_page", r2.url)
        for p in p2:
            if p not in phones:
                phones.append(p)
        for k, v in s2.items():
            socials.setdefault(k, v)
        for p in pp2:
            if all(p["name"].lower() != q["name"].lower() for q in found_people):
                found_people.append(p)
    s.close()

    emails = _unrot13(emails, {domain, final_dom} - {""})
    ranked = _rank_emails(emails, final_dom or domain)
    # an address whose domain can't receive mail is never "best": check the top domains, sink dead ones
    mx = {}
    for e in ranked:
        dom = e.split("@", 1)[1]
        if dom not in mx and len(mx) < 4:
            mx[dom] = has_mx(dom)
    ranked = sorted(ranked, key=lambda e: mx.get(e.split("@", 1)[1]) is False)  # stable: keeps rank order
    info.update(emails=ranked[:15], phones=phones[:8], socials=socials, pages=pages, people=found_people[:12])
    if ranked:
        info["mx"] = mx.get(ranked[0].split("@", 1)[1])
    return info


def _unrot13(emails: list[str], own: set[str]) -> list[str]:
    """Some sites ROT13 their address against bots (info@cocottes.lu → vasb@pbpbggrf.yh).
    Decode it when the result lands on the site's own domain."""
    out = []
    for e in emails:
        d = codecs.decode(e, "rot13")
        dd = d.split("@", 1)[1]
        if any(dd == o or dd.endswith("." + o) for o in own) and not any(
                e.split("@", 1)[1] == o for o in own):
            e = d
        if e not in out:
            out.append(e)
    return out
