"""
Mailbox check without sending anything: ask the domain's mail server whether it
would accept the address (SMTP RCPT TO), then hang up.

Results: valid · invalid · catch_all (server accepts any address, so the check
proves nothing) · unknown (server refused to answer, greylisted, port blocked…).

Used sparingly — mainly for guessed addresses — because heavy probing from one
home IP can get that IP onto blocklists.
"""

from __future__ import annotations

import random
import smtplib
import socket
import string
import threading

try:
    import dns.resolver
except ImportError:
    dns = None

_MX: dict[str, list[str]] = {}
_CATCH: dict[str, bool | None] = {}
_DOMAIN_LOCKS: dict[str, threading.Lock] = {}
_LOCK = threading.Lock()
HELO = "mail.leadfinder.local"
# big providers never give a useful answer (or accept everything); skip the round trip
NO_PROBE = {"yahoo.com", "yahoo.fr", "aol.com", "icloud.com", "me.com", "hotmail.com", "outlook.com",
            "live.com", "hotmail.fr", "outlook.fr", "msn.com"}


def mx_hosts(domain: str) -> list[str]:
    with _LOCK:
        if domain in _MX:
            return _MX[domain]
    hosts = []
    if dns:
        try:
            r = dns.resolver.Resolver()
            r.lifetime = 6
            hosts = [x.exchange.to_text().rstrip(".") for x in sorted(r.resolve(domain, "MX"), key=lambda x: x.preference)]
        except Exception:
            hosts = []
    with _LOCK:
        _MX[domain] = hosts
    return hosts


def _dlock(domain):
    with _LOCK:
        return _DOMAIN_LOCKS.setdefault(domain, threading.Lock())


def check(emails: list[str], timeout: int = 12) -> dict[str, str]:
    """All addresses must share one domain. One SMTP session checks them all."""
    if not emails:
        return {}
    domain = emails[0].split("@", 1)[1].lower()
    if domain in NO_PROBE:
        return {e: "unknown" for e in emails}
    hosts = mx_hosts(domain)
    if not hosts:
        return {e: "invalid" for e in emails}  # the domain can't receive mail at all
    out = {e: "unknown" for e in emails}
    with _dlock(domain):  # never hammer one server in parallel
        for host in hosts[:2]:
            try:
                s = smtplib.SMTP(host, 25, timeout=timeout, local_hostname=HELO)
            except (OSError, smtplib.SMTPException, socket.timeout):
                continue
            try:
                s.ehlo_or_helo_if_needed()
                code, _ = s.mail("")
                if code >= 400:
                    break
                if domain not in _CATCH:
                    fake = "".join(random.choices(string.ascii_lowercase + string.digits, k=14)) + "@" + domain
                    c, _ = s.rcpt(fake)
                    _CATCH[domain] = True if c < 300 else False if 500 <= c < 600 else None
                catch = _CATCH.get(domain)
                for e in emails:
                    c, _ = s.rcpt(e)
                    if c < 300:
                        out[e] = "catch_all" if catch else "valid" if catch is False else "unknown"
                    elif 500 <= c < 600 and catch is False:
                        out[e] = "invalid"
                break
            except (OSError, smtplib.SMTPException, socket.timeout):
                continue
            finally:
                try:
                    s.quit()
                except Exception:
                    pass
    return out
