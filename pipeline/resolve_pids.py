#!/usr/bin/env python3
"""
Resolve & verify DBLP PIDs for an institution's faculty, using the public
CSRankings CSV as the faculty roster (data only — no CSRankings code).

This is the first, reproducible step of adding/refreshing an institution in
SPARK. It does NOT touch existing data (faculty.json, rankings.json, the DB);
it only emits new draft/report files for review. Integrating the resolved PIDs
into the live roster is a separate, later step.

Pipeline:
  1. Read the CSRankings CSV, filter to one institution's affiliation string.
  2. Collapse alias rows (CSRankings lists name variants that share a
     Google Scholar id / ORCID) into unique people.
  3. Resolve each person to a DBLP PID via the DBLP author-search API, taking
     the hit whose author string EXACTLY equals a CSRankings name spelling
     (CSRankings names are DBLP names, incl. homonym suffixes like "0001").
  4. Verify each PID against the DBLP person record (pid.xml): ORCID match,
     homepage/affiliation match, and recent-publication activity — then tier
     each as HIGH / MEDIUM / REVIEW.
  5. Write outputs and update an idempotent cache so re-runs only resolve
     newly-added faculty (the hook for the future monthly refresh job).

Manual overrides (data/pid_overrides.csv) let a human force/drop/ack a PID and
are honoured on every run — see load_overrides(). The monthly entry point is
pipeline/refresh.sh, which runs `--all --refresh-csv` and alerts on untriaged
review items.

Usage:
    python pipeline/resolve_pids.py --all                          # combined roster + shared review file
    python pipeline/resolve_pids.py --all --refresh-csv            # fresh roster, keep PID cache (monthly)
    python pipeline/resolve_pids.py --institution IITD             # one institution
    python pipeline/resolve_pids.py --affiliation "IIT Delhi" --short IITD --name "IIT Delhi"
    python pipeline/resolve_pids.py --institution IITD --limit 5   # quick test
"""

import argparse
import csv
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import OrderedDict

import requests

# ──────────────────────────────────────────────────────────────────
# Configuration
# ──────────────────────────────────────────────────────────────────
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")

CSRANKINGS_CSV_URL = (
    "https://raw.githubusercontent.com/emeryberger/CSrankings/gh-pages/csrankings.csv"
)
CSV_CACHE = os.path.join(DATA_DIR, "csrankings.csv")

# Maintainer-editable, durable source of truth for manual PID decisions. Read
# (never written) by the resolver and applied BEFORE any DBLP call, so manual
# fixes survive every re-run. See load_overrides() for the schema.
OVERRIDES_FILE = os.path.join(DATA_DIR, "pid_overrides.csv")

DBLP_SEARCH_URL = "https://dblp.org/search/author/api"
DBLP_PID_XML = "https://dblp.org/pid/{pid}.xml"

# Polite gap between DBLP calls. The search API throttles hard: at 3s a bulk
# run (100+ uncached people) slides into a 503 spiral where nearly every call
# burns the retry ladder below, costing ~60s/person. Backing off to 8s stays
# under the limit and finishes a large batch sooner than fighting the throttle.
DELAY_SECONDS = 8.0
MAX_RETRIES = 5
RETRY_BASE_DELAY = 8         # seconds, doubles each retry
COOLDOWN_AFTER_FAILURE = 45  # extra pause after exhausting retries (DBLP IP block cools down)
RECENT_YEAR = 2015           # "active researcher" sanity threshold

# CSRankings placeholder tokens that mean "no value".
NO_SCHOLAR = "NOSCHOLARPAGE"
NO_ORCID = "0000-0000-0000-0000"

HEADERS = {"User-Agent": "SPARK-Academic-Ranking-Tool/1.0 (academic research project)"}

# DBLP records these as "affiliation" but they name an email network / generic
# entity, not the person's institution (scraped from old *.ernet.in emails).
# Treat them as no-affiliation so they don't trigger a false "affiliation
# mismatch" review for genuine faculty.
UNINFORMATIVE_AFFILIATIONS = {"ernet india", "ernet"}

# Tracked institutions live in pipeline/institutions.py — one entry per
# department, edited by hand when adding one. `--all` processes every entry;
# `--institution SHORT` picks one; otherwise pass --affiliation/--short/--name.
sys.path.insert(0, SCRIPT_DIR)
from institutions import INSTITUTIONS  # noqa: E402

DISAMBIG_SUFFIX = re.compile(r"\s+\d{4}$")   # DBLP homonym suffix, e.g. "Amit Kumar 0001"


# ──────────────────────────────────────────────────────────────────
# CSV ingest
# ──────────────────────────────────────────────────────────────────
def ensure_csv(path, refresh=False):
    """Download the CSRankings CSV to `path` if missing (or --refresh)."""
    if os.path.exists(path) and not refresh:
        return path
    print(f"  Downloading CSRankings CSV → {path} ...")
    resp = requests.get(CSRANKINGS_CSV_URL, headers=HEADERS, timeout=60)
    resp.raise_for_status()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(resp.text)
    return path


def load_roster(csv_path, affiliation):
    """Return CSRankings rows for one affiliation string (exact match)."""
    rows = []
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("affiliation", "").strip() == affiliation:
                rows.append({
                    "name": row["name"].strip(),
                    "homepage": (row.get("homepage") or "").strip(),
                    "scholarid": (row.get("scholarid") or "").strip(),
                    "orcid": (row.get("orcid") or "").strip(),
                })
    return rows


def real_orcid(orcid):
    return orcid if orcid and orcid != NO_ORCID else None


def real_scholar(scholarid):
    return scholarid if scholarid and scholarid != NO_SCHOLAR else None


def dedup_people(rows):
    """Collapse alias rows into unique people.

    CSRankings lists spelling variants of one person as separate rows that
    share a Google Scholar id (or ORCID). Group by scholarid, else ORCID,
    else the name itself. Keep every alias name spelling.
    """
    groups = OrderedDict()
    for row in rows:
        sid = real_scholar(row["scholarid"])
        oid = real_orcid(row["orcid"])
        if sid:
            key = f"scholar:{sid}"
        elif oid:
            key = f"orcid:{oid}"
        else:
            key = f"name:{row['name']}"

        if key not in groups:
            groups[key] = {
                "identity": key,
                "aliases": [],
                "homepage": "",
                "orcid": oid,
                "scholarid": sid,
            }
        g = groups[key]
        if row["name"] not in g["aliases"]:
            g["aliases"].append(row["name"])
        if not g["homepage"] and row["homepage"]:
            g["homepage"] = row["homepage"]
        if not g["orcid"] and oid:
            g["orcid"] = oid

    # Prefer a disambiguation-suffixed spelling first (resolves most reliably),
    # then longer spellings.
    for g in groups.values():
        g["aliases"].sort(key=lambda n: (0 if DISAMBIG_SUFFIX.search(n) else 1, -len(n)))
    return list(groups.values())


# ──────────────────────────────────────────────────────────────────
# DBLP calls (with retry/backoff)
# ──────────────────────────────────────────────────────────────────
def dblp_get(session, url, params=None):
    """GET with retry on 429/5xx. Returns Response or None."""
    resp = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            return resp
        except requests.exceptions.RequestException as e:
            code = getattr(getattr(e, "response", None), "status_code", None)
            if code == 404:
                return None
            if attempt < MAX_RETRIES - 1:
                wait = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"      ⚠ {type(e).__name__} ({code}); retry {attempt+1}/{MAX_RETRIES} in {wait}s")
                time.sleep(wait)
                continue
            # Exhausted retries — likely a sustained DBLP IP block. Cool down
            # so the *next* person has a chance instead of cascading failures.
            print(f"      ✗ giving up on {url}: {e} — cooling down {COOLDOWN_AFTER_FAILURE}s")
            time.sleep(COOLDOWN_AFTER_FAILURE)
            return None
    return resp


def pid_from_url(url):
    """Extract the DBLP PID from a hit url like https://dblp.org/pid/38/768[.html]."""
    m = re.search(r"/pid/(.+?)(?:\.html)?$", url or "")
    return m.group(1) if m else None


def resolve_pid(session, aliases):
    """Resolve a person to a DBLP PID by exact author-name match.

    Tries each alias spelling; scans ALL hits for an exact (case-insensitive)
    author-string match. Returns (pid, matched_name, distinct_pids_seen).
    `distinct_pids_seen` > 1 signals an alias→PID conflict.
    """
    found = None            # (pid, matched_name)
    distinct = set()
    for name in aliases:
        resp = dblp_get(session, DBLP_SEARCH_URL, params={"q": name, "format": "json", "h": 1000})
        time.sleep(DELAY_SECONDS)
        if resp is None:
            continue
        try:
            hits = resp.json()["result"]["hits"].get("hit", [])
        except (ValueError, KeyError):
            continue
        for h in hits:
            info = h.get("info", {})
            author = info.get("author", "")
            if author.strip().lower() == name.strip().lower():
                pid = pid_from_url(info.get("url", ""))
                if pid:
                    distinct.add(pid)
                    if found is None:
                        found = (pid, author.strip())
                break  # exact match found for this alias; move to next alias
    if found is None:
        return None, None, distinct
    return found[0], found[1], distinct


def norm_url(u):
    """Normalize a URL for loose comparison: drop scheme, www., trailing slash."""
    u = (u or "").strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    return u.rstrip("/")


def fetch_person_record(session, pid):
    """Fetch pid.xml and extract person-level fields + pub-year stats."""
    resp = dblp_get(session, DBLP_PID_XML.format(pid=pid))
    time.sleep(DELAY_SECONDS)
    if resp is None:
        return None
    try:
        root = ET.fromstring(resp.content)
    except ET.ParseError:
        return None

    person = root.find("person")
    urls, orcid, affiliations = [], None, []
    if person is not None:
        for u in person.findall("url"):
            txt = (u.text or "").strip()
            if not txt:
                continue
            m = re.search(r"orcid\.org/([\dX-]+)", txt)
            if m:
                orcid = m.group(1)
            else:
                urls.append(txt)
        for note in person.findall("note"):
            if note.get("type") == "affiliation" and note.text:
                affiliations.append(note.text.strip())

    # Publication recency: each <r> wraps one publication element with a <year>.
    total_pubs, recent_pubs = 0, 0
    for r in root.findall("r"):
        for pub in r:
            yr = pub.find("year")
            if yr is not None and yr.text and yr.text.isdigit():
                total_pubs += 1
                if int(yr.text) >= RECENT_YEAR:
                    recent_pubs += 1
            break

    return {
        "dblp_name": root.attrib.get("name"),
        "urls": urls,
        "orcid": orcid,
        "affiliations": affiliations,
        "total_pubs": total_pubs,
        "recent_pubs": recent_pubs,
    }


# ──────────────────────────────────────────────────────────────────
# Verification & tiering
# ──────────────────────────────────────────────────────────────────
def verify(person, record, inst, pid, matched_name, distinct_pids):
    """Compute verification signals and a confidence tier for a resolved PID."""
    csv_orcid = person.get("orcid")
    dblp_orcid = record.get("orcid") if record else None

    orcid_match = bool(csv_orcid and dblp_orcid and csv_orcid.lower() == dblp_orcid.lower())

    homepage_match = False
    if record and person.get("homepage"):
        ch = norm_url(person["homepage"])
        if ch:
            for du in record["urls"]:
                d = norm_url(du)
                if d and (ch == d or ch in d or d in ch):
                    homepage_match = True
                    break

    aff_notes_all = record["affiliations"] if record else []
    # Normalize punctuation so "Indian Institute of Technology, Delhi" matches
    # the keyword "indian institute of technology delhi".
    def _norm_txt(s):
        return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", s.lower())).strip()
    # Ignore uninformative notes (e.g. "ERNET, India") when judging affiliation.
    aff_notes = [a for a in aff_notes_all if _norm_txt(a) not in UNINFORMATIVE_AFFILIATIONS]
    aff_blob = _norm_txt(" || ".join(aff_notes))
    affiliation_match = any(_norm_txt(kw) in aff_blob for kw in inst["affiliation_keywords"])
    has_aff = bool(aff_notes)

    recent = record["recent_pubs"] if record else 0
    conflict = len(distinct_pids) > 1

    signals = {
        "exact_name": matched_name is not None,
        "orcid_csv": csv_orcid,
        "orcid_dblp": dblp_orcid,
        "orcid_match": orcid_match,
        "homepage_match": homepage_match,
        "affiliation_match": affiliation_match,
        "affiliations": aff_notes_all,
        "recent_pubs": recent,
        "total_pubs": record["total_pubs"] if record else 0,
        "alias_pid_conflict": conflict,
    }

    notes = []
    if conflict:
        notes.append(f"aliases resolved to multiple PIDs: {sorted(distinct_pids)}")

    # Tiering
    if not signals["exact_name"] or pid is None:
        tier = "REVIEW"
        notes.append("no exact DBLP author-name match")
    elif conflict:
        tier = "REVIEW"
    elif recent == 0:
        tier = "REVIEW"
        notes.append(f"no publications since {RECENT_YEAR}")
    elif orcid_match or homepage_match or affiliation_match:
        tier = "HIGH"
    elif has_aff and not affiliation_match:
        tier = "REVIEW"
        notes.append("DBLP affiliation does not mention this institution")
    else:
        tier = "MEDIUM"
        notes.append("exact name only; no ORCID/homepage/affiliation corroboration")

    return tier, signals, "; ".join(notes)


# ──────────────────────────────────────────────────────────────────
# Cache
# ──────────────────────────────────────────────────────────────────
def cache_path(short):
    return os.path.join(DATA_DIR, f"{short.lower()}_pid_cache.json")


def load_cache(short):
    p = cache_path(short)
    if os.path.exists(p):
        with open(p, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(short, cache):
    with open(cache_path(short), "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────────
# Manual overrides (maintainer's durable human-in-the-loop control)
# ──────────────────────────────────────────────────────────────────
OVERRIDE_ACTIONS = {"set", "drop", "ack"}


def _norm_person_name(n):
    """Loose name key for matching a maintainer's override to a CSRankings person."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", (n or "").lower())).strip()


def load_overrides():
    """Load data/pid_overrides.csv → {short_upper: {norm_name: override}}.

    Schema: institution,csrankings_name,dblp_pid,action,note
      action=set  → force dblp_pid for this person (roster, tier MANUAL)
      action=drop → exclude this person entirely (not in roster, not in review)
      action=ack  → leave in review but mute it from the "needs review" alert

    Blank lines and rows whose institution starts with '#' are ignored, so the
    file can carry comments/examples.
    """
    overrides = {}
    if not os.path.exists(OVERRIDES_FILE):
        return overrides
    with open(OVERRIDES_FILE, "r", encoding="utf-8") as f:
        # Drop comment lines FIRST so a leading '#' block doesn't get parsed as
        # the CSV header. The header is then the first remaining line.
        lines = [ln for ln in f if not ln.lstrip().startswith("#")]
    for row in csv.DictReader(lines):
        short = (row.get("institution") or "").strip()
        if not short or short.startswith("#"):
            continue
        action = (row.get("action") or "").strip().lower()
        if action not in OVERRIDE_ACTIONS:
            continue
        name = (row.get("csrankings_name") or "").strip()
        entry = {
            "action": action,
            "dblp_pid": (row.get("dblp_pid") or "").strip(),
            "note": (row.get("note") or "").strip(),
        }
        overrides.setdefault(short.upper(), {})[_norm_person_name(name)] = entry
    return overrides


def match_override(inst_overrides, person):
    """Return the override for a person, matching any alias/display-name spelling."""
    if not inst_overrides:
        return None
    keys = {_norm_person_name(a) for a in person["aliases"]}
    keys.add(_norm_person_name(display_name(person["aliases"][0])))
    for k in keys:
        if k in inst_overrides:
            return inst_overrides[k]
    return None


def manual_result(person, override):
    """Build a MANUAL roster result from a `set` override (no DBLP calls)."""
    return {
        "identity": person["identity"],
        "canonical_name": person["aliases"][0],
        "aliases": person["aliases"],
        "homepage": person["homepage"],
        "dblp_pid": override["dblp_pid"],
        "dblp_match_name": None,
        "confidence": "MANUAL",
        "signals": {"manual": True, "note": override["note"]},
        "notes": f"manual override: {override['note']}" if override["note"] else "manual override",
    }


# ──────────────────────────────────────────────────────────────────
# Output writers
# ──────────────────────────────────────────────────────────────────
# Combined ("all institutions in one file") outputs
RESOLVED_FILE = os.path.join(DATA_DIR, "resolved_faculty.json")
NEEDS_REVIEW_JSON = os.path.join(DATA_DIR, "needs_review.json")
NEEDS_REVIEW_MD = os.path.join(DATA_DIR, "needs_review.md")
NEEDS_REVIEW_CSV = os.path.join(DATA_DIR, "needs_review.csv")


def display_name(name):
    """Strip a trailing DBLP homonym suffix for a clean display name."""
    return DISAMBIG_SUFFIX.sub("", name).strip()


def faculty_entry(r):
    """Faculty dict for the roster/draft (faculty.json-compatible + extras)."""
    return {
        "name": display_name(r["canonical_name"]),
        "csrankings_name": r["canonical_name"],
        "aliases": r["aliases"],
        "homepage": r["homepage"],
        "orcid": r["signals"].get("orcid_csv"),
        "dblp_match_name": r["dblp_match_name"],
        "dblp_pid": r["dblp_pid"],
        "match_confidence": r["confidence"].lower(),
    }


def inst_meta(short, inst):
    """Institution header fields (mirrors faculty.json institution blocks)."""
    meta = {
        "name": inst["name"], "short": short,
        "country": inst.get("country", ""), "website": inst.get("website", ""),
    }
    if inst.get("state"):
        meta["state"] = inst["state"]
    if inst.get("city"):
        meta["city"] = inst["city"]
    return meta


def resolve_institution(short, inst, csv_path, session, refresh=False, limit=None, overrides=None):
    """Resolve one institution's roster. Returns (rows, people, results, counts).

    Manual overrides (data/pid_overrides.csv) are applied FIRST — `set` forces a
    MANUAL roster entry, `drop` excludes the person, `ack` mutes an unresolved
    person from the alert — so a maintainer's fixes never re-hit DBLP or expire.
    Otherwise idempotent: HIGH/MEDIUM people cached from a prior run are reused;
    only new/unresolved people are (re)resolved, so re-runs cheaply pick up new
    faculty.
    """
    inst_overrides = (overrides or {}).get(short.upper(), {})
    rows = load_roster(csv_path, inst["affiliation"])
    people = dedup_people(rows)
    if limit:
        people = people[:limit]
    print(f"\n── {inst['name']} ({short}) — {len(rows)} rows → {len(people)} people")

    cache = {} if refresh else load_cache(short)
    results = []
    for i, person in enumerate(people, 1):
        canonical = person["aliases"][0]

        # 1. Manual overrides win, before cache or any network call.
        ov = match_override(inst_overrides, person)
        if ov and ov["action"] == "drop":
            print(f"  [{i}/{len(people)}] {canonical} — DROP (override): {ov['note']}")
            continue
        if ov and ov["action"] == "set":
            results.append(manual_result(person, ov))
            print(f"  [{i}/{len(people)}] {canonical} — MANUAL {ov['dblp_pid']} (override)")
            continue

        # 2. Cache, then DBLP resolution + verification.
        cached = cache.get(person["identity"])
        if cached and cached.get("confidence") in ("HIGH", "MEDIUM"):
            print(f"  [{i}/{len(people)}] {canonical} — cached {cached['dblp_pid']} ({cached['confidence']})")
            results.append(cached)
            continue
        print(f"  [{i}/{len(people)}] {canonical} ...", flush=True)
        pid, matched_name, distinct = resolve_pid(session, person["aliases"])
        record = fetch_person_record(session, pid) if pid else None
        tier, signals, notes = verify(person, record, inst, pid, matched_name, distinct)
        result = {
            "identity": person["identity"],
            "canonical_name": canonical,
            "aliases": person["aliases"],
            "homepage": person["homepage"],
            "dblp_pid": pid,
            "dblp_match_name": matched_name,
            "confidence": tier,
            "signals": signals,
            "notes": notes,
        }
        # 3. `ack` override: leave unresolved but mute from the alert.
        if ov and ov["action"] == "ack":
            result["acknowledged"] = True
            result["notes"] = (notes + "; acknowledged by maintainer").lstrip("; ")
        results.append(result)
        cache[person["identity"]] = result
        print(f"        → {pid or 'UNRESOLVED'} [{tier}] {notes}")
        # Persist after every person, not just at the end of the institution:
        # a DBLP throttle can stretch one institution over hours, and an
        # interrupted run should never re-resolve work already paid for.
        save_cache(short, cache)

    save_cache(short, cache)
    counts = {
        "csrankings_rows": len(rows),
        "unique_people": len(people),
        "resolved": sum(1 for r in results if r["dblp_pid"]),
        "high": sum(1 for r in results if r["confidence"] == "HIGH"),
        "medium": sum(1 for r in results if r["confidence"] == "MEDIUM"),
        "manual": sum(1 for r in results if r["confidence"] == "MANUAL"),
        "review": sum(1 for r in results if r["confidence"] == "REVIEW"),
    }
    return rows, people, results, counts


def read_json(path):
    """Load a JSON file, or return None if it isn't there / is unreadable."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def write_combined(all_inst, merge=False):
    """Write ONE roster file (every institution, HIGH+MEDIUM faculty) and ONE
    shared needs-review file (REVIEW + unresolved, every institution).

    all_inst: list of (short, inst, results, counts).

    merge=False (an --all run) rebuilds both files from scratch.
    merge=True (single-institution mode) rewrites only the blocks and review
    rows belonging to the institutions in `all_inst` and carries every other
    institution over verbatim from the files on disk — so adding one college
    costs one institution's worth of DBLP calls, not the whole roster's.
    """
    generated_at = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    roster = {"generated_at": generated_at, "source": "CSRankings", "institutions": []}
    review_rows = []
    summary = []

    for short, inst, results, counts in all_inst:
        faculty = []
        for r in results:
            # HIGH/MEDIUM (auto-resolved) and MANUAL (maintainer-set) → roster.
            if r["dblp_pid"] and r["confidence"] in ("HIGH", "MEDIUM", "MANUAL"):
                faculty.append(faculty_entry(r))
            else:  # REVIEW / unresolved → shared needs-review file
                review_rows.append({
                    "institution": inst["name"],
                    "short": short,
                    "name": display_name(r["canonical_name"]),
                    "csrankings_name": r["canonical_name"],
                    "aliases": r["aliases"],
                    "homepage": r["homepage"],
                    "dblp_pid": r["dblp_pid"],
                    "dblp_match_name": r["dblp_match_name"],
                    "confidence": r["confidence"],
                    "reason": r["notes"],
                    "acknowledged": bool(r.get("acknowledged")),
                    "dblp_url": f"https://dblp.org/pid/{r['dblp_pid']}" if r["dblp_pid"] else None,
                    "signals": r["signals"],
                })
        block = inst_meta(short, inst)
        block["faculty_count"] = len(faculty)
        block["faculty"] = faculty
        roster["institutions"].append(block)
        summary.append((short, inst["name"], counts, len(faculty)))

    if merge:
        touched = {short.upper() for short, *_ in all_inst}
        fresh = {b["short"].upper(): b for b in roster["institutions"]}
        prior_roster = read_json(RESOLVED_FILE) or {}
        merged = []
        for block in prior_roster.get("institutions", []):
            key = block.get("short", "").upper()
            # Replace a re-resolved institution in place (keeps file order
            # stable across runs); carry every other one over untouched.
            merged.append(fresh.pop(key) if key in fresh else block)
        merged.extend(fresh.values())  # institutions seen for the first time
        roster["institutions"] = merged

        # Same for the shared review file: drop this institution's stale rows,
        # keep everyone else's, so `untriaged` still covers the whole project
        # and refresh.sh's exit code stays meaningful.
        prior_review = read_json(NEEDS_REVIEW_JSON) or {}
        carried = [r for r in prior_review.get("results", [])
                   if r.get("short", "").upper() not in touched]
        review_rows = carried + review_rows

    with open(RESOLVED_FILE, "w", encoding="utf-8") as f:
        json.dump(roster, f, indent=2, ensure_ascii=False)

    # `untriaged` = review items the maintainer has NOT yet acknowledged/handled.
    # This (not the raw review count) is what drives the production alert.
    untriaged = sum(1 for x in review_rows if not x["acknowledged"])
    review_doc = {
        "generated_at": generated_at,
        "count": len(review_rows),
        "untriaged": untriaged,
        "results": review_rows,
    }
    with open(NEEDS_REVIEW_JSON, "w", encoding="utf-8") as f:
        json.dump(review_doc, f, indent=2, ensure_ascii=False)

    # Human-readable, self-documenting needs-review table (all institutions).
    review_sorted = sorted(
        review_rows, key=lambda x: (x["acknowledged"], x["short"], x["confidence"], x["name"]))
    rel = os.path.relpath(OVERRIDES_FILE, os.path.dirname(SCRIPT_DIR))
    lines = [
        "# SPARK — Faculty PIDs needing review",
        "",
        f"Generated: {generated_at}  |  Source: CSRankings CSV",
        "",
        f"**{untriaged}** untriaged of **{len(review_rows)}** flagged, "
        f"across {len(roster['institutions'])} institutions.",
        "",
        "## How to resolve",
        "",
        f"Edit `{rel}` (one row per person) — the resolver reads it first and it "
        "survives every re-run:",
        "",
        "- `set` — you found the right DBLP PID → person enters the roster as MANUAL.",
        "- `drop` — duplicate name variant or not really CS faculty → excluded.",
        "- `ack` — can't resolve yet, but stop alerting on it (stays listed below).",
        "",
        "```csv",
        "institution,csrankings_name,dblp_pid,action,note",
        "IITM,Kamakoti Veezhinathan,80/1234,set,verified by hand",
        "IISC,Chiru Bhattacharyya,,drop,alias of Chiranjib Bhattacharyya",
        "IITB,Bernard Menezes,,ack,retired; no clean DBLP profile",
        "```",
        "",
        "| Institution | Confidence | Name | DBLP PID | Reason | Ack |",
        "|---|---|---|---|---|---|",
    ]
    for x in review_sorted:
        pid = x["dblp_pid"]
        pid_cell = f"[{pid}]({x['dblp_url']})" if pid else "—"
        ack = "✓" if x["acknowledged"] else ""
        lines.append(
            f"| {x['short']} | {x['confidence']} | {x['name']} | {pid_cell} | {x['reason']} | {ack} |")
    with open(NEEDS_REVIEW_MD, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    # Spreadsheet-friendly CSV for the maintainer. The first five columns match
    # pid_overrides.csv, so a maintainer can fill `action`/`note` and paste the
    # row straight into the overrides file.
    with open(NEEDS_REVIEW_CSV, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(["institution", "csrankings_name", "dblp_pid", "action", "note",
                    "confidence", "reason", "acknowledged", "dblp_url", "homepage"])
        for x in review_sorted:
            w.writerow([x["short"], x["csrankings_name"], x["dblp_pid"] or "", "", "",
                        x["confidence"], x["reason"], "yes" if x["acknowledged"] else "",
                        x["dblp_url"] or "", x["homepage"]])

    return roster, review_doc, summary


def write_outputs(short, inst, results, counts):
    """Per-institution outputs (single-institution mode, useful for debugging)."""
    draft = {
        "institution": inst["name"],
        "short": short,
        "country": inst.get("country", ""),
        "website": inst.get("website", ""),
        "source": "CSRankings",
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "faculty": [faculty_entry(r) for r in results if r["dblp_pid"]],
    }
    draft_path = os.path.join(DATA_DIR, f"{short.lower()}_faculty_draft.json")
    with open(draft_path, "w", encoding="utf-8") as f:
        json.dump(draft, f, indent=2, ensure_ascii=False)

    # 2. Machine-readable report
    report = {
        "generated_at": draft["generated_at"],
        "institution": inst["name"],
        "short": short,
        "affiliation_filter": inst["affiliation"],
        "counts": counts,
        "results": results,
    }
    report_path = os.path.join(DATA_DIR, f"{short.lower()}_pid_report.json")
    with open(report_path, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # 3. Human-readable review table (worst confidence first)
    order = {"REVIEW": 0, "MEDIUM": 1, "HIGH": 2}
    rows = sorted(results, key=lambda r: (order.get(r["confidence"], 9), r["canonical_name"]))
    lines = [
        f"# {inst['name']} — DBLP PID resolution review",
        "",
        f"Generated: {draft['generated_at']}  |  Source: CSRankings CSV (affiliation = \"{inst['affiliation']}\")",
        "",
        f"- CSRankings rows: **{counts['csrankings_rows']}**",
        f"- Unique people: **{counts['unique_people']}**",
        f"- Resolved: **{counts['resolved']}**  (HIGH {counts['high']}, MEDIUM {counts['medium']}, REVIEW {counts['review']})",
        "",
        "Review MEDIUM/REVIEW rows by opening the DBLP link and confirming the institution.",
        "",
        "| Confidence | Name | DBLP PID | ORCID | Homepage | Affiliation | Recent pubs | Notes |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for r in rows:
        s = r["signals"]
        pid = r["dblp_pid"]
        pid_cell = f"[{pid}](https://dblp.org/pid/{pid})" if pid else "—"
        lines.append(
            f"| {r['confidence']} | {display_name(r['canonical_name'])} | {pid_cell} | "
            f"{'✓' if s['orcid_match'] else ('csv-only' if s['orcid_csv'] else '—')} | "
            f"{'✓' if s['homepage_match'] else '—'} | "
            f"{'✓' if s['affiliation_match'] else ('other' if s['affiliations'] else '—')} | "
            f"{s['recent_pubs']} | {r['notes']} |"
        )
    review_path = os.path.join(DATA_DIR, f"{short.lower()}_pid_review.md")
    with open(review_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")

    return draft_path, report_path, review_path


# ──────────────────────────────────────────────────────────────────
# Main
# ──────────────────────────────────────────────────────────────────
def main():
    global DELAY_SECONDS
    ap = argparse.ArgumentParser(description="Resolve & verify DBLP PIDs from the CSRankings roster.")
    ap.add_argument("--all", action="store_true",
                    help="Resolve EVERY tracked institution → combined roster + shared needs-review file")
    ap.add_argument("--institution", help="Known short code (e.g. IITD) — single-institution mode")
    ap.add_argument("--affiliation", help="Exact CSRankings affiliation string (for a new institution)")
    ap.add_argument("--short", help="Short code (with --affiliation)")
    ap.add_argument("--name", help="Display name (with --affiliation)")
    ap.add_argument("--csv", default=CSV_CACHE, help="Path to csrankings.csv (default: data/csrankings.csv)")
    ap.add_argument("--refresh-csv", dest="refresh_csv", action="store_true",
                    help="Re-download the CSV but KEEP the PID cache (monthly refresh: new roster, cached PIDs)")
    ap.add_argument("--refresh", action="store_true",
                    help="Full rebuild: re-download CSV AND ignore the PID cache")
    ap.add_argument("--limit", type=int, help="Only process the first N unique people per institution (testing)")
    ap.add_argument("--delay", type=float, help=f"Seconds between DBLP calls (default {DELAY_SECONDS})")
    ap.add_argument("--merge", dest="merge", action="store_true", default=None,
                    help="Fold this institution into data/resolved_faculty.json + needs_review.* "
                         "instead of only writing its own files. Every other institution is "
                         "carried over untouched. Default ON for --institution.")
    ap.add_argument("--no-merge", dest="merge", action="store_false",
                    help="Write only the per-institution draft/report/review files")
    args = ap.parse_args()

    if args.delay is not None:
        DELAY_SECONDS = args.delay

    ensure_csv(args.csv, refresh=args.refresh or args.refresh_csv)
    overrides = load_overrides()
    session = requests.Session()
    session.headers.update(HEADERS)

    # ── All-institutions mode: one combined roster + one shared review file ──
    if args.all:
        print("=" * 60)
        print(f"SPARK — DBLP PID resolver  |  ALL tracked institutions ({len(INSTITUTIONS)})")
        print("=" * 60)
        all_inst = []
        for short, inst in INSTITUTIONS.items():
            _, _, results, counts = resolve_institution(
                short, inst, args.csv, session, refresh=args.refresh,
                limit=args.limit, overrides=overrides)
            all_inst.append((short, inst, results, counts))

        roster, review_doc, summary = write_combined(all_inst)
        total_faculty = sum(n for *_, n in summary)
        print("\n" + "=" * 60)
        print(f"  {len(all_inst)} institutions  |  {total_faculty} roster faculty  |  "
              f"{review_doc['untriaged']} untriaged of {review_doc['count']} flagged")
        for short, name, counts, nfac in summary:
            print(f"    {short:6s} {name:16s} roster {nfac:3d}  "
                  f"(HIGH {counts['high']}, MED {counts['medium']}, "
                  f"MANUAL {counts['manual']}, REVIEW {counts['review']})")
        print(f"  roster:       {RESOLVED_FILE}")
        print(f"  needs-review: {NEEDS_REVIEW_MD}")
        print(f"                {NEEDS_REVIEW_CSV}")
        print(f"                {NEEDS_REVIEW_JSON}")
        print("=" * 60)
        return

    # ── Single-institution mode ──
    tracked = False
    if args.institution and args.institution.upper() in INSTITUTIONS:
        short = args.institution.upper()
        inst = INSTITUTIONS[short]
        tracked = True
    elif args.affiliation:
        short = (args.short or args.affiliation).upper()
        inst = {
            "name": args.name or args.affiliation,
            "affiliation": args.affiliation,
            "country": "",
            "website": "",
            "affiliation_keywords": [args.affiliation.lower()],
        }
    else:
        ap.error("provide --all, --institution <known short>, or --affiliation <string> [--short --name]")

    print("=" * 60)
    print(f"SPARK — DBLP PID resolver  |  {inst['name']} ({short})")
    print("=" * 60)

    _, _, results, counts = resolve_institution(
        short, inst, args.csv, session, refresh=args.refresh, limit=args.limit, overrides=overrides)
    draft_path, report_path, review_path = write_outputs(short, inst, results, counts)

    # An ad-hoc --affiliation probe stays out of the shared roster unless the
    # maintainer explicitly asks; a tracked --institution folds in by default,
    # which is what makes the single-college path feed integrate_roster.py.
    do_merge = args.merge if args.merge is not None else tracked

    print("\n" + "=" * 60)
    print(f"  resolved {counts['resolved']}/{counts['unique_people']}  "
          f"(HIGH {counts['high']}, MEDIUM {counts['medium']}, REVIEW {counts['review']})")
    print(f"  draft:  {draft_path}")
    print(f"  report: {report_path}")
    print(f"  review: {review_path}")

    if do_merge:
        roster, review_doc, _ = write_combined([(short, inst, results, counts)], merge=True)
        print(f"  merged into {RESOLVED_FILE}")
        total = sum(i.get("faculty_count", len(i.get("faculty", [])))
                    for i in roster["institutions"])
        print(f"    → {len(roster['institutions'])} institutions, {total} roster faculty")
        print(f"    → needs-review now {review_doc['untriaged']} untriaged "
              f"of {review_doc['count']} flagged (all institutions)")
    else:
        print("  (not merged into resolved_faculty.json — pass --merge to fold it in)")
    print("=" * 60)

    if do_merge and review_doc["untriaged"] > 0:
        sys.exit(2)  # same contract as refresh.sh: 2 = a human should look


if __name__ == "__main__":
    main()
