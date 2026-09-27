"""
Decision makers: who runs the business, read from the business's own pages
(structured data, "Name – CEO" lines, legal notices …) and from personal email
addresses; plus the company's email pattern, so a person without a published
address gets a best guess (marked as a guess, and mailbox-checked when enabled).
"""

from __future__ import annotations

import html as htmllib
import json
import re
import unicodedata

ROLE_WORDS = (
    r"CEO|CFO|COO|CTO|CMO|Founder|Co-?founder|Owner|Proprietor|Managing Director|Managing Partner|Director|"
    r"General Manager|Manager|Partner|President|Head of [A-Z][a-z]+|Principal|Chairman|Chairwoman|"
    r"G[ée]rante?|Directeur(?: général| g[ée]n[ée]rale)?|Directrice(?: générale)?|Fondat(?:eur|rice)|Pr[ée]sidente?|"
    r"Associ[ée]e?|Responsable|Co-?g[ée]rante?|Ma[iî]tre|"
    r"Gesch[äa]ftsf[üu]hrer(?:in)?|Inhaber(?:in)?|Vorstand|Vertreten durch|Prokurist(?:in)?|"
    r"Daglig leder|Styreleder|Innehaver|Toimitusjohtaja|Omistaja|Hallituksen puheenjohtaja|"
    r"Director General|Gerente|Propietari[oa]|Socio|Amministratore(?: delegato)?|Titolare|Eigenaar|Directeur")
# the words of one name sit on one line: "Dr Audrey Abbou" must not swallow a "PRENDRE RDV" button below it
NAME = r"[A-ZÀ-Ý][a-zà-ÿ'’]+(?:-[A-ZÀ-Ý][a-zà-ÿ'’]+)?(?:[ \t]+(?:de |van |von |du |le |la )?[A-ZÀ-Ý][A-Za-zÀ-Ýà-ÿ'’]+(?:-[A-ZÀ-Ý][a-zà-ÿ'’]+)?){1,2}"
RX_NAME_ROLE = re.compile(rf"\b({NAME})\s*(?:,|–|—|-|\||:|\(|\n)\s*({ROLE_WORDS})\b")
RX_ROLE_NAME = re.compile(rf"\b({ROLE_WORDS})\s*(?::|–|—|-|,)?\s*(?:Dr\.?\s+|M\.\s+|Mme\s+|Mr\.?\s+|Mrs\.?\s+|Ms\.?\s+)?({NAME})\b")
RX_DOCTOR = re.compile(rf"\b(?:Dr|Docteur|Doctor|Dre|Prof)\.?\s+({NAME})\b")
BAD_NAME = re.compile(
    r"\b(Our|Notre|Nos|Unser|Team|Contact|Privacy|Policy|Terms|Cookie|Home|Accueil|About|Services?|Mentions|"
    r"Legal|Impressum|Lorem|Ipsum|Read|More|Learn|Click|Book|Rendez|Online|Google|Facebook|Instagram|Linked|"
    r"Twitter|Monday|Tuesday|Lundi|Mardi|Street|Rue|Avenue|Road|Strasse|Straße|Copyright|All|Rights|Reserved|"
    r"Company|Limited|Group|Cabinet|Clinic|Hotel|Restaurant|Office|Director|Manager|Partner|Owner|Founder|"
    r"Directeur|Gérant|Inhaber|The|And|Und|Les|Des|Pour|For|With|Avec|January|Janvier|Paris|London|Lyon|"
    r"People|Solutions|Consulting|Systems|Media|Digital|Studio|Design|Health|Care|Dental|Medical|Law|Legal)\b")
ROLE_IN_NAME = re.compile(rf"\b({ROLE_WORDS})\b", re.I)
JSONLD_RX = re.compile(r'<script[^>]+application/ld\+json[^>]*>(.*?)</script>', re.I | re.S)
BLOCK_TAGS = re.compile(r"</?(p|div|li|br|h\d|tr|td|section|article|span|strong|b|em|a)[^>]*>", re.I)
TAGS = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>|<[^>]+>", re.I | re.S)


def _fold(s):
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def _clean_role(r: str) -> str:
    r = re.sub(r"\s+", " ", r).strip(" :-–—,")
    return "Legal representative" if r.lower() == "vertreten durch" else r[:60]


def _ok_name(n: str) -> bool:
    ws = n.split()
    return (2 <= len(ws) <= 4 and not BAD_NAME.search(n) and not ROLE_IN_NAME.search(n)
            and all(len(w) >= 2 for w in ws) and len(n) <= 45)


def _visible_lines(html: str) -> str:
    t = BLOCK_TAGS.sub("\n", re.sub(r"<(script|style|noscript)[^>]*>.*?</\1>", " ", html, flags=re.I | re.S))
    t = htmllib.unescape(TAGS.sub(" ", t))
    return "\n".join(re.sub(r"[ \t\xa0]+", " ", ln).strip() for ln in t.split("\n") if ln.strip())


def from_html(html: str) -> list[dict]:
    out: dict[str, dict] = {}

    def add(name, role, how):
        name = re.sub(r"\s+", " ", name).strip()
        if not _ok_name(name):
            return
        k = _fold(name)
        if k not in out or (role and not out[k]["role"]):
            out[k] = {"name": name, "role": _clean_role(role) if role else "", "source": how}

    for block in JSONLD_RX.findall(html):
        try:
            data = json.loads(block.strip())
        except ValueError:
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack += x
            elif isinstance(x, dict):
                if x.get("@type") in ("Person", ["Person"]) and isinstance(x.get("name"), str):
                    add(x["name"], x.get("jobTitle") if isinstance(x.get("jobTitle"), str) else "", "website")
                for key in ("founder", "employee", "member", "author", "@graph", "contactPoint"):
                    if key in x:
                        stack.append(x[key])
    text = _visible_lines(html)
    # "Role: Name" is explicit, so it runs first; "Name⏎Role" (team cards) only fills in the rest
    for r, n in RX_ROLE_NAME.findall(text):
        add(n, r, "website")
    for n, r in RX_NAME_ROLE.findall(text):
        add(n, r, "website")
    for n in RX_DOCTOR.findall(text):
        add(n, "Doctor", "website")
    return list(out.values())[:12]


# --------------------------------------------------------------------------- #
# email patterns
# --------------------------------------------------------------------------- #
PATTERNS = {  # key → builder(first, last)
    "first.last": lambda f, l: f"{f}.{l}", "firstlast": lambda f, l: f"{f}{l}", "first_last": lambda f, l: f"{f}_{l}",
    "first-last": lambda f, l: f"{f}-{l}", "f.last": lambda f, l: f"{f[0]}.{l}", "flast": lambda f, l: f"{f[0]}{l}",
    "last.first": lambda f, l: f"{l}.{f}", "lastf": lambda f, l: f"{l}{f[0]}", "first": lambda f, l: f,
    "last": lambda f, l: l, "first.l": lambda f, l: f"{f}.{l[0]}",
}


def _parts(name: str):
    # "Antoine-Michel Rodriguez" writes his address as antoine.rodriguez@
    ws = [re.sub(r"[^a-z]", "", _fold(w.split("-")[0] if i == 0 else w)) for i, w in enumerate(name.split())]
    ws = [w for w in ws if w and w not in ("dr", "mr", "mrs", "ms", "me", "prof")]
    return (ws[0], ws[-1]) if len(ws) >= 2 else (None, None)


def pattern_of(local: str, name: str) -> str | None:
    f, l = _parts(name)
    if not f:
        return None
    for key, fn in PATTERNS.items():
        if fn(f, l) == local:
            return key
    return None


def name_from_email(local: str) -> str | None:
    m = re.fullmatch(r"([a-z]{2,})[._-]([a-z]{2,})", local)
    if not m or m.group(1) in ("info", "contact", "office", "admin", "sales", "support", "hello", "team", "mail"):
        return None
    return f"{m.group(1).title()} {m.group(2).title()}"


def infer(people: list[dict], emails: list[str], domain: str) -> tuple[list[dict], str | None]:
    """Attach known / guessed emails to people. Returns (people, pattern)."""
    own = [e for e in emails if domain and e.endswith("@" + domain)]
    people = [dict(p) for p in people]
    pattern = None
    for p in people:
        for e in own:
            key = pattern_of(e.split("@")[0], p.get("name", ""))
            if key:
                p["email"], p["email_status"] = e, p.get("email_status") or "published"
                pattern = pattern or key
    known = {_fold(p["name"]) for p in people}
    taken = {p.get("email") for p in people}
    for e in own:  # a personal address we have no person for yet: first.last@ → "First Last"
        n = name_from_email(e.split("@")[0])
        if n and _fold(n) not in known and e not in taken:
            people.append({"name": n, "role": "", "source": "email", "email": e, "email_status": "published"})
            known.add(_fold(n))
            pattern = pattern or "first.last"
    if pattern and domain:
        for p in people:
            if not p.get("email"):
                f, l = _parts(p.get("name", ""))
                if f:
                    p["email"] = f"{PATTERNS[pattern](f, l)}@{domain}"
                    p["email_status"] = "guessed"
    return people[:12], pattern
