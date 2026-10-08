"""
Background jobs. A search job: geocode every location → run each source for
every niche → merge leads into the store → enrich every new website in a
thread pool. Progress lives in memory (polled by the UI) and the log is
persisted on the search row so history survives restarts.
"""

from __future__ import annotations

import collections
import concurrent.futures as cf
import threading
import time
import traceback

import categories
import enrich
import geo as geo_mod
import overture
import registries
import sources
import store
import verify
import webfind

_STOP = (sources.Cancelled, overture.Cancelled, registries.Cancelled)

JOBS: dict[int, "Job"] = {}
_JOBS_LOCK = threading.Lock()
_OVERPASS_SEM = threading.Semaphore(2)  # be a good citizen on the free map servers


class Job:
    def __init__(self, sid: int, params: dict, kind: str = "search"):
        self.id = sid
        self.params = params
        self.kind = kind
        self.cancel = threading.Event()
        self.status = "queued"
        self.phase = "Starting"
        self.error = ""
        self.started = time.time()
        self.finished = None
        self.c = collections.Counter()
        self.log_lines: list[dict] = []
        self.recent = collections.deque(maxlen=40)
        self.lock = threading.Lock()
        self._last_persist = 0.0
        self.new_ids: set[int] = set()

    # ------------------------------------------------------------------ utils
    def log(self, msg: str, level: str = "info"):
        with self.lock:
            self.log_lines.append({"t": time.time(), "m": msg, "l": level})
            self.log_lines = self.log_lines[-400:]
        if time.time() - self._last_persist > 3:
            self.persist()

    def persist(self, **extra):
        self._last_persist = time.time()
        store.update_search(self.id, log=list(self.log_lines), **extra)

    def snapshot(self) -> dict:
        with self.lock:
            return {
                "id": self.id, "kind": self.kind, "status": self.status, "phase": self.phase,
                "error": self.error, "started": self.started, "finished": self.finished,
                "elapsed": round((self.finished or time.time()) - self.started, 1),
                "counts": dict(self.c), "log": self.log_lines[-80:], "recent": list(self.recent),
                "params": self.params,
            }

    # ------------------------------------------------------------ discovery
    def _on_batch(self, batch, niche_label):
        cap = int(self.params.get("max_leads") or 0)
        if cap:
            room = cap - len(self.new_ids)
            if room <= 0:
                if not self.c["cap_hit"]:
                    self.c["cap_hit"] = 1
                    self.log(f"Reached your limit of {cap:,} leads — stopping discovery.", "warn")
                return
            batch = batch[:room]
        for d in batch:
            d["niche"] = niche_label
        for i in range(0, len(batch), 500):
            part = batch[i:i + 500]
            res = store.upsert_many(part, self.id)
            with self.lock:
                for d, (lid, new) in zip(part, res):
                    self.c["found"] += 1
                    if lid in self.new_ids:
                        continue
                    self.new_ids.add(lid)
                    self.c["leads"] = len(self.new_ids)
                    if new:
                        self.c["brand_new"] += 1
                    if d.get("website"):
                        self.c["websites"] += 1
                    if d.get("phone"):
                        self.c["phones"] += 1
                    if d.get("emails"):
                        self.c["emails"] += 1
                    self.recent.appendleft({"id": lid, "name": d.get("name"), "city": d.get("city"),
                                            "cat": d.get("category"), "src": (d.get("sources") or [""])[0],
                                            "lat": d.get("lat"), "lon": d.get("lon"),
                                            "email": bool(d.get("emails")), "web": bool(d.get("website"))})

    def _cap_hit(self):
        cap = int(self.params.get("max_leads") or 0)
        return bool(cap and len(self.new_ids) >= cap)

    def _source(self, name, fn):
        """Run one source; a failure is logged and the search carries on with the next."""
        try:
            return fn()
        except _STOP:
            raise
        except Exception as ex:
            traceback.print_exc()
            self.log(f"{name}: {str(ex)[:200]}", "error")
            return 0

    def discover(self):
        p = self.params
        settings = store.get_settings()
        srcs = {"osm": True, "overture": True, "registry": True, **(p.get("sources") or {})}
        sess = overture.Session() if (srcs.get("overture") or srcs.get("fsq")) and overture.available() else None
        if (srcs.get("overture") or srcs.get("fsq")) and not sess:
            self.log("Overture/Foursquare need the DuckDB engine (pip install duckdb) — skipped.", "warn")
        try:
            self._discover(p, settings, srcs, sess)
        except _STOP:
            return
        finally:
            if sess:
                sess.close()

    def _discover(self, p, settings, srcs, sess):
        for loc in p["locations"]:
            if self.cancel.is_set() or self._cap_hit():
                return
            self.phase = f"Locating {loc}"
            self.log(f"Looking up “{loc}” on the map…")
            try:
                geo = sources.geocode(loc)
            except Exception as ex:
                self.log(f"Could not locate “{loc}”: {ex}", "error")
                continue
            area = geo_mod.Area(geo.get("polygon"))
            w, h = sources.bbox_km(geo["bbox"])
            self.log(f"Found {geo['label']} (~{int(w):,} × {int(h):,} km"
                     f"{', exact boundary' if area else ''}).")
            cc = geo.get("country_code", "")
            for niche in p["niches"]:
                if self.cancel.is_set() or self._cap_hit():
                    return
                m = categories.match(niche)
                label = m["label"]
                before = len(self.new_ids)
                where = geo["name"]

                def cb(b, lb=label):
                    self._on_batch(b, lb)

                if srcs.get("overture") and sess and not self._cap_hit():
                    self.phase = f"Overture Maps · {label} · {where}"
                    n = self._source("Overture Maps", lambda: overture.overture(
                        m, geo, area, settings, sess, self.cancel, self.log, cb))
                    self.log(f"Overture Maps: {n:,} places for {label} in {where}.", "ok")
                if srcs.get("registry") and registries.supported(cc) and not self._cap_hit():
                    self.phase = f"Business register · {label} · {where}"
                    n = self._source("Business register", lambda: registries.search(
                        cc, m, geo, settings, self.cancel, self.log, cb))
                    self.log(f"{registries.SUPPORTED[cc.upper()]}: {n:,} registered businesses.", "ok")
                if srcs.get("opencorporates") and not self._cap_hit():
                    self.phase = f"OpenCorporates · {label} · {where}"
                    n = self._source("OpenCorporates", lambda: registries.opencorporates(
                        m, geo, settings, self.cancel, self.log, cb))
                    self.log(f"OpenCorporates: {n:,} companies for {label} in {where}.", "ok")
                if srcs.get("wikidata") and not self._cap_hit():
                    self.phase = f"Wikidata · {label} · {where}"
                    n = self._source("Wikidata", lambda: registries.wikidata(
                        m, geo, settings, self.cancel, self.log, cb))
                    self.log(f"Wikidata: {n:,} companies for {label} in {where}.", "ok")
                if srcs.get("fsq") and sess and not self._cap_hit():
                    self.phase = f"Foursquare · {label} · {where}"
                    n = self._source("Foursquare", lambda: overture.fsq(
                        m, geo, area, settings.get("hf_token", ""), sess, self.cancel, self.log, cb))
                    self.log(f"Foursquare: {n:,} places for {label} in {where}.", "ok")
                if srcs.get("osm") and not self._cap_hit():
                    self.phase = f"OpenStreetMap · {label} · {where}"
                    tag = "" if m["exact"] else " (custom keyword search)"
                    self.log(f"Searching OpenStreetMap for {label} in {where}{tag}…")

                    def run_osm():
                        with _OVERPASS_SEM:
                            return sources.osm(m["filters"], geo, self.cancel, self.log, cb)
                    n = self._source("OpenStreetMap", run_osm)
                    self.log(f"OpenStreetMap: {n:,} places for {label} in {where}.", "ok")
                if m["key"] == categories.ALL_KEY:
                    if srcs.get("google") or srcs.get("yelp"):
                        self.log("Google / Yelp skipped for “All businesses” (they need a business type).")
                else:
                    if srcs.get("google") and settings.get("google_key") and not self._cap_hit():
                        self.phase = f"Google Places · {label} · {where}"
                        used = self._source("Google Places", lambda: sources.google(
                            f"{m['term']} in {where}", geo, settings["google_key"],
                            int(settings.get("google_budget") or 150), self.cancel, self.log, cb))
                        self.c["google_requests"] += used or 0
                    if srcs.get("yelp") and settings.get("yelp_key") and not self._cap_hit():
                        self.phase = f"Yelp · {label} · {where}"
                        used = self._source("Yelp", lambda: sources.yelp(
                            m["term"], geo, settings["yelp_key"], int(settings.get("yelp_budget") or 100),
                            self.cancel, self.log, cb))
                        self.c["yelp_requests"] += used or 0
                self.log(f"{label} in {where}: {len(self.new_ids) - before:,} leads in this search "
                         f"(duplicates across sources merged).")

    # ------------------------------------------------------- missing websites
    def find_websites(self):
        settings = store.get_settings()
        cap = int(settings.get("webfind_max") or 5000)
        rows = store.leads_without_website(self.id, cap)
        if not rows:
            return
        brave = settings.get("brave_key", "")
        keys = {}
        self.phase = "Finding missing websites"
        self.c["web_total"] = len(rows)
        self.log(f"Looking for the websites of {len(rows):,} businesses that have none on file"
                 f"{' (domain guessing + web search)' if brave else ' (domain guessing)'}…")

        def work(r):
            if self.cancel.is_set():
                return r, None
            if r["niche"] not in keys:
                keys[r["niche"]] = categories.match(r["niche"] or "business")["key"]
            r["niche_key"] = keys[r["niche"]]
            return r, webfind.find(r, brave)

        with cf.ThreadPoolExecutor(16) as ex:
            for f in cf.as_completed([ex.submit(work, r) for r in rows]):
                try:
                    r, res = f.result()
                except Exception:
                    continue
                if self.cancel.is_set():
                    continue
                store.set_website(r["id"], res[0] if res else None, res[1] if res else "")
                with self.lock:
                    self.c["web_done"] += 1
                    if res:
                        self.c["web_found"] += 1
                        self.recent.appendleft({"id": r["id"], "name": r["name"], "found": res[0], "web": True,
                                                "src": "website finder"})
                if self.c["web_done"] % 100 == 0:
                    self.log(f"Website finder: {self.c['web_done']:,}/{len(rows):,} checked — "
                             f"{self.c['web_found']:,} found.")
        self.log(f"Website finder: found {self.c['web_found']:,} websites for "
                 f"{self.c['web_done']:,} businesses.", "ok")

    # --------------------------------------------------------- decision makers
    def fetch_people(self):
        rows = store.leads_needing_people(self.id)
        if not rows:
            return
        settings = store.get_settings()
        self.phase = "Reading decision makers from the register"
        self.c["people_total"] = len(rows)
        self.log(f"Reading owners / directors of {len(rows):,} registered companies…")

        def work(r):
            return r, registries.people(r["reg_id"], settings, self.cancel)

        with cf.ThreadPoolExecutor(6) as ex:
            for f in cf.as_completed([ex.submit(work, r) for r in rows]):
                try:
                    r, ppl = f.result()
                except Exception:
                    continue
                if ppl:
                    store.add_people(r["id"], ppl)
                with self.lock:
                    self.c["people_done"] += 1
                    self.c["people_found"] += 1 if ppl else 0
        self.log(f"Decision makers: found for {self.c['people_found']:,} companies.", "ok")

    def after_discovery(self):
        """Everything that deepens the leads already found (also what Resume runs)."""
        p = self.params
        if p.get("find_websites", True) and not self.cancel.is_set():
            self.find_websites()
        if p.get("people", True) and not self.cancel.is_set():
            self.fetch_people()
        if p.get("enrich", True) and not self.cancel.is_set():
            if p.get("enrich_missing_only"):
                n = store.skip_enrich_with_email(self.id)
                if n:
                    self.log(f"{n:,} leads already have an email — their websites are skipped (faster mode).")
            self.enrich()

    # ------------------------------------------------------------ enrichment
    def enrich(self, ids=None):
        settings = store.get_settings()
        workers = max(2, min(64, int(settings.get("workers") or 24)))
        verify_on = settings.get("verify_guesses", "1") == "1"
        pages = max(1, min(15, int(settings.get("pages_per_site") or 6)))
        timeout = max(5, min(40, int(settings.get("site_timeout") or 12)))
        todo = store.pending_enrich(None if ids else self.id, ids=ids)
        if not todo:
            self.log("No websites left to visit.")
            return
        by_domain = collections.defaultdict(list)
        for r in todo:
            by_domain[r["domain"]].append(r)
        self.c["enrich_total"] = len(by_domain)
        self.phase = "Visiting websites"
        self.log(f"Visiting {len(by_domain):,} websites to find emails, phones and social profiles "
                 f"({workers} at a time)…")
        store.set_enrich_status([r["id"] for r in todo], "working")

        def work(domain, rows):
            if self.cancel.is_set():
                return domain, rows, None
            info = None if self.params.get("force") else store.cached_site(domain)
            if info is None:
                info = enrich.enrich_site(rows[0]["website"], domain, pages, timeout, self.cancel)
                if not self.cancel.is_set():
                    store.save_site(domain, info)
            return domain, rows, info

        with cf.ThreadPoolExecutor(workers) as ex:
            futs = [ex.submit(work, d, rows) for d, rows in by_domain.items()]
            for f in cf.as_completed(futs):
                try:
                    domain, rows, info = f.result()
                except Exception as e:  # never let one site kill the run
                    self.log(f"Site error: {e}", "error")
                    continue
                if info is None:
                    store.set_enrich_status([r["id"] for r in rows], "pending")
                    continue
                for r in rows:
                    store.apply_enrichment(r["id"], info)
                if verify_on and info.get("ok"):
                    guesses = store.guessed_emails(rows[0]["id"])
                    if guesses:
                        res = verify.check(guesses)
                        for r in rows:
                            store.set_email_status(r["id"], res)
                        with self.lock:
                            self.c["verified"] += len(res)
                with self.lock:
                    self.c["enriched"] += 1
                    if info.get("emails"):
                        self.c["site_emails"] += 1
                    if not info.get("ok"):
                        self.c["site_failed"] += 1
                if info.get("emails"):
                    self.recent.appendleft({"id": rows[0]["id"], "name": domain, "email": True,
                                            "found": info["emails"][0], "web": True, "src": "website"})
                if self.c["enriched"] % 25 == 0:
                    self.log(f"Websites: {self.c['enriched']:,}/{len(by_domain):,} visited — "
                             f"{self.c['site_emails']:,} with emails.")
        if self.cancel.is_set():
            self.log("Stopped — the websites not visited yet stay queued; press Resume to continue.", "warn")
        else:
            self.log(f"Website enrichment done: {self.c['site_emails']:,} of {len(by_domain):,} sites "
                     f"published an email.", "ok")

    # ------------------------------------------------------------------ run
    def run(self):
        self.status = "running"
        store.update_search(self.id, status="running")
        try:
            if self.kind == "search":
                self.discover()
                if not self.cancel.is_set():
                    self.after_discovery()
            else:
                self.enrich(ids=self.params.get("ids"))
            self.status = "stopped" if self.cancel.is_set() else "done"
            self.phase = "Stopped" if self.cancel.is_set() else "Finished"
        except Exception as ex:
            traceback.print_exc()
            self.status, self.error, self.phase = "error", str(ex), "Error"
            self.log(f"Unexpected error: {ex}", "error")
        self.finished = time.time()
        s = store.get_search(self.id) or {}
        st = s.get("stats", {})
        if self.status == "done":
            self.log(f"Done in {int(self.finished - self.started)}s — {st.get('leads', 0):,} leads, "
                     f"{st.get('emails', 0):,} with email, {st.get('phones', 0):,} with phone.", "ok")
        self.persist(status=self.status, error=self.error, finished_at=self.finished)


def start_search(niches, locations, params) -> int:
    params = dict(params, niches=niches, locations=locations)
    sid = store.create_search(", ".join(niches), " · ".join(locations), params)
    _launch(Job(sid, params))
    return sid


def resume(sid: int) -> bool:
    s = store.get_search(sid)
    if not s or sid in running_ids():
        return False
    job = Job(sid, dict(s["params"]), kind="enrich")
    job.log_lines = s.get("log", [])
    job.log("Resuming: finishing websites, decision makers and site visits still queued…")
    job.params["ids"] = None
    _launch(job, enrich_search=True)
    return True


def enrich_leads(ids) -> int:
    sid = store.create_search("Re-check websites", f"{len(ids)} selected leads", {"ids": ids, "enrich_only": True})
    job = Job(sid, {"ids": ids, "force": True}, kind="enrich")
    _launch(job)
    return sid


def _launch(job: Job, enrich_search=False):
    with _JOBS_LOCK:
        JOBS[job.id] = job

    def target():
        if enrich_search:
            job.status = "running"
            store.update_search(job.id, status="running")
            try:
                job.after_discovery()
                job.status = "stopped" if job.cancel.is_set() else "done"
            except Exception as ex:
                job.status, job.error = "error", str(ex)
            job.finished = time.time()
            job.phase = "Finished"
            job.persist(status=job.status, error=job.error, finished_at=job.finished)
        else:
            job.run()

    threading.Thread(target=target, daemon=True, name=f"job-{job.id}").start()


def running_ids():
    return [j.id for j in JOBS.values() if j.status in ("queued", "running")]


def get(sid: int):
    j = JOBS.get(sid)
    return j.snapshot() if j else None


def cancel(sid: int) -> bool:
    j = JOBS.get(sid)
    if j and j.status in ("queued", "running"):
        j.cancel.set()
        j.phase = "Stopping…"
        return True
    return False
