#!/usr/bin/env python3
"""
Fetch publications from DBLP for faculty members, match them against ICORE
A*/A conferences, and write the scored results to data/rankings.json.

Two ways to run it:

    # everything, cache honoured — cheap after an interrupted run
    python pipeline/fetch_publications.py

    # ONE institution: fetch only its faculty and splice the result into the
    # existing rankings.json. The other institutions are carried over verbatim,
    # so adding a college costs that college's DBLP calls and nothing else.
    python pipeline/fetch_publications.py --institution IITK

    # overnight refresh: re-fetch anyone whose DBLP data is over 30 days old,
    # which is how new publications and new papers by existing faculty land.
    python pipeline/fetch_publications.py --max-age 30
"""

import argparse
import json
import math
import os
import re
import sys
import time
from collections import defaultdict

import requests
# defusedxml over xml.etree: DBLP's XML is third-party input parsed here
# unvalidated. Drop-in replacement, same tree API.
from defusedxml import ElementTree as ET

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")

ICORE_FILE = os.path.join(DATA_DIR, "icore_conferences.json")
FACULTY_FILE = os.path.join(DATA_DIR, "faculty.json")
IRINS_DIR = DATA_DIR  # Per-institution IRINS files: irins_{short}.json
JOURNALS_FILE = os.path.join(DATA_DIR, "ieee_acm_journals.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "rankings.json")

DBLP_BASE = "https://dblp.uni-trier.de"
# Polite gap between DBLP calls. Matches resolve_pids.py: at 3s a bulk run over
# hundreds of faculty slides into a 503 spiral where nearly every call burns the
# retry ladder, which is slower overall than simply asking less often.
DELAY_SECONDS = 8.0
MAX_RETRIES = 4
RETRY_BASE_DELAY = 5  # seconds, doubles each retry

# Checkpoint of raw DBLP fetches, keyed by PID. A full run over 592 faculty is a
# multi-hour job against a throttling API, and rankings.json is only written at
# the very end — without this, one failure at hour two loses everything.
#
# Deliberately caches the *network* result, not the scored result: venue matching
# and scoring are cheap and depend on icore_conferences.json, so they are
# recomputed every run and an ICORE refresh takes effect without a re-fetch.
#
# Entries carry a `fetched_at` epoch so --max-age can expire them selectively:
# without that, the only way to pick up new publications was to delete the whole
# file and re-fetch every faculty member from scratch.
FETCH_CACHE_FILE = os.path.join(DATA_DIR, "dblp_fetch_cache.json")
YEAR_START = 2015
YEAR_END = 2026


def load_icore_conferences():
    """Load ICORE conference data and build a lookup by DBLP key."""
    with open(ICORE_FILE, "r") as f:
        data = json.load(f)
    
    lookup = {}
    for conf in data["conferences"]:
        key = conf.get("dblp_key")
        if key:
            lookup[key.lower()] = conf
    
    return lookup


def load_faculty():
    """Load faculty data."""
    with open(FACULTY_FILE, "r") as f:
        return json.load(f)


def get_page_count(pages_str):
    """Parse DBLP pages string and return the number of pages."""
    if not pages_str:
        return None
    try:
        # Check for colon-separated ranges like 12:1-12:15
        if ':' in pages_str:
            parts = pages_str.split('-')
            if len(parts) == 2:
                start = int(parts[0].split(':')[-1])
                end = int(parts[1].split(':')[-1])
                return max(1, end - start + 1)
        
        # Check for standard ranges like 12-25
        parts = pages_str.split('-')
        if len(parts) == 2:
            start_str = re.sub(r'[^0-9]', '', parts[0])
            end_str = re.sub(r'[^0-9]', '', parts[1])
            if start_str and end_str:
                return max(1, int(end_str) - int(start_str) + 1)
            
        # Single page number
        if pages_str.isdigit():
            return 1
    except Exception:
        pass
    return None


def is_short_or_workshop_paper(title, pages_str, booktitle=""):
    """Check if paper is a short paper, demo, or workshop paper based on title/pages/booktitle."""
    # Check title and booktitle heuristics
    pattern = r'\b(demo|poster|student abstract|doctoral consortium|extended abstract|tutorial|workshop|workshops|companion)\b'
    if re.search(pattern, title.lower()):
        return True
    
    # Check proceeding title for "Adjunct" or other workshop patterns
    if "adjunct" in booktitle.lower():
        return True
    if re.search(pattern, booktitle.lower()):
        return True
    
    # Check page count (<= 5 pages)
    pages = get_page_count(pages_str)
    if pages is not None and pages <= 5:
        return True
        
    return False


def load_fetch_cache():
    """Load the raw-DBLP-fetch checkpoint (see FETCH_CACHE_FILE)."""
    if os.path.exists(FETCH_CACHE_FILE):
        with open(FETCH_CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_fetch_cache(cache):
    """Persist the checkpoint. Called after every faculty member, so an
    interrupted run resumes rather than repeating hours of DBLP calls."""
    tmp = FETCH_CACHE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    os.replace(tmp, FETCH_CACHE_FILE)   # atomic: a kill mid-write can't corrupt it


def cache_lookup(cache, pid, max_age_days=None):
    """Return the cached DBLP result for `pid`, or None to (re-)fetch it.

    max_age_days=None keeps every entry, however old — the resumable-checkpoint
    behaviour. With a max age, entries older than that expire, and so do the
    pre-timestamp entries written before this flag existed: their real age is
    unknown, and treating unknown as stale is the safe direction for a refresh.
    """
    entry = cache.get(pid) if cache is not None else None
    if not entry or "pubs" not in entry:
        return None
    if max_age_days is None:
        return entry
    fetched_at = entry.get("fetched_at")
    if fetched_at is None or (time.time() - fetched_at) > max_age_days * 86400:
        return None
    return entry


def fetch_author_publications(pid, session):
    """Fetch all publications for an author from DBLP using their PID.

    Returns a list of publication dicts. Includes retry logic for 429 errors.
    """
    url = f"{DBLP_BASE}/pid/{pid}.xml"
    
    resp = None
    for attempt in range(MAX_RETRIES):
        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            break
        except requests.exceptions.RequestException as e:
            # Handle specific HTTP errors if response exists
            if getattr(e, 'response', None) is not None:
                if e.response.status_code == 404:
                    print(f"      ⚠ PID not found: {pid}")
                    return [], []
                if e.response.status_code in (429, 503, 502, 500, 504):
                    wait = RETRY_BASE_DELAY * (2 ** attempt)
                    print(f"      ⚠ Rate limited/Overloaded ({e.response.status_code}). Waiting {wait}s before retry {attempt + 1}/{MAX_RETRIES}...")
                    time.sleep(wait)
                    continue
            # Handle timeout or connection errors
            elif isinstance(e, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
                wait = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"      ⚠ Connection issue ({type(e).__name__}). Waiting {wait}s before retry {attempt + 1}/{MAX_RETRIES}...")
                time.sleep(wait)
                continue
            # Raise other unexpected exceptions
            raise
    else:
        print(f"      ✗ Failed after {MAX_RETRIES} retries for PID: {pid}")
        return []
    
    # Parse XML
    root = ET.fromstring(resp.content)
    publications = []
    skipped_publications = []
    
    # DBLP XML has <r> elements containing <inproceedings>, <article>, etc.
    for r_elem in root.findall(".//r"):
        for pub_elem in r_elem:
            pub_type = pub_elem.tag  # inproceedings, article, etc.
            
            # We only care about conference papers (inproceedings)
            if pub_type != "inproceedings":
                continue
            
            # Extract key (contains venue info)
            pub_key = pub_elem.get("key", "")
            
            # Extract title
            title_elem = pub_elem.find("title")
            title = title_elem.text if title_elem is not None and title_elem.text else ""
            # Handle mixed content in title
            if title_elem is not None:
                title = "".join(title_elem.itertext()).strip()
            
            # Extract year
            year_elem = pub_elem.find("year")
            year = int(year_elem.text) if year_elem is not None and year_elem.text else 0
            
            # Extract venue/booktitle
            booktitle_elem = pub_elem.find("booktitle")
            booktitle = booktitle_elem.text if booktitle_elem is not None else ""
            
            # Extract all authors
            authors = []
            for author_elem in pub_elem.findall("author"):
                authors.append("".join(author_elem.itertext()).strip())
            
            # Extract DBLP venue key from the publication key
            # Format: conf/VENUE/... e.g., conf/aaai/SmithJ23
            venue_key = None
            key_match = re.match(r'conf/([^/]+)/', pub_key)
            if key_match:
                venue_key = key_match.group(1)
            
            # Extract URL
            url_elem = pub_elem.find("ee")
            pub_url = url_elem.text if url_elem is not None else None
            
            # Extract pages
            pages_elem = pub_elem.find("pages")
            pages_str = pages_elem.text if pages_elem is not None else ""
            
            pub_data = {
                "title": title,
                "year": year,
                "booktitle": booktitle,
                "venue_key": venue_key,
                "num_authors": len(authors),
                "authors": authors,
                "dblp_key": pub_key,
                "url": pub_url,
                "pages": pages_str,
            }
            
            # Filter out co-located workshop papers (e.g., ARMS-CC@PODC)
            if "@" in booktitle:
                skipped_publications.append(pub_data)
                continue
            
            # Filter out short/workshop papers
            if is_short_or_workshop_paper(title, pages_str, booktitle):
                skipped_publications.append(pub_data)
                continue
            
            publications.append(pub_data)
    
    return publications, skipped_publications


def process_faculty_member(faculty, icore_lookup, session, fetch_cache=None, max_age_days=None):
    """Process a single faculty member: fetch pubs, match against ICORE, compute score.

    `fetch_cache` (pid → raw DBLP result) makes the network step resumable; pass
    None to always hit DBLP. `max_age_days` expires stale entries (see
    cache_lookup). Scoring below always runs, cached or not.
    """
    pid = faculty["dblp_pid"]
    name = faculty["name"]

    cached = cache_lookup(fetch_cache, pid, max_age_days)
    if cached is not None:
        pubs, skipped_pubs = cached["pubs"], cached["skipped"]
        print(f"    → {name} (pid: {pid}) — cached {len(pubs)} papers")
    else:
        print(f"    → Fetching publications for {name} (pid: {pid})...")
        pubs, skipped_pubs = fetch_author_publications(pid, session)
        if fetch_cache is not None:
            fetch_cache[pid] = {"pubs": pubs, "skipped": skipped_pubs,
                                "fetched_at": time.time()}
            save_fetch_cache(fetch_cache)
        print(f"      Found {len(pubs)} conference papers total (skipped {len(skipped_pubs)} short/workshop)")
    
    # Filter by year range
    pubs = [p for p in pubs if YEAR_START <= p["year"] <= YEAR_END]
    print(f"      {len(pubs)} in year range {YEAR_START}-{YEAR_END}")
    
    # Match against ICORE conferences
    matched_pubs = []
    total_score = 0.0
    papers_astar = 0
    papers_a = 0
    
    for pub in pubs:
        venue_key = pub.get("venue_key")
        if not venue_key:
            continue
        
        # Skip co-located workshop papers: DBLP puts workshops like
        # ARMS-CC@PODC under conf/podc/, but the booktitle contains '@'
        # to indicate it's not the main conference.
        booktitle = pub.get("booktitle", "")
        if "@" in booktitle:
            continue
        
        conf = icore_lookup.get(venue_key.lower())
        if conf:
            adjusted_count = 1.0 / max(pub["num_authors"], 1)
            total_score += adjusted_count
            
            rank = conf["rank"]
            if rank == "A*":
                papers_astar += 1
            elif rank == "A":
                papers_a += 1
            
            matched_pubs.append({
                "title": pub["title"],
                "venue": conf["acronym"],
                "venue_full": conf["title"],
                "venue_rank": rank,
                "year": pub["year"],
                "num_authors": pub["num_authors"],
                "adjusted_count": round(adjusted_count, 4),
                "url": pub.get("url"),
                "for_code": conf.get("for_code", ""),
            })
    
    # Sort by year descending
    matched_pubs.sort(key=lambda p: (-p["year"], p["venue"]))
    
    print(f"      Matched: {len(matched_pubs)} papers ({papers_astar} A*, {papers_a} A)")
    print(f"      Score: {total_score:.2f}")
    
    return {
        "name": name,
        "dblp_pid": pid,
        "role": faculty.get("role", ""),
        "homepage": faculty.get("homepage", ""),
        "score": round(total_score, 4),
        "papers_astar": papers_astar,
        "papers_a": papers_a,
        "papers_journal": 0,
        "total_matched": len(matched_pubs),
        "publications": matched_pubs,
        "skipped_publications": skipped_pubs,
    }


def compute_area_breakdown(faculty_results, icore_lookup):
    """Compute publication counts grouped by research area (FoR code).
    
    Also computes weighted scores per area (A*=4, A=2, Journal=1)
    and the geometric mean across all areas.
    """
    # FoR code descriptions (common CS ones)
    for_descriptions = {
        "4601": "Applied Computing",
        "4602": "Artificial Intelligence",
        "4603": "Computer Vision and Multimedia",
        "4604": "Cybersecurity and Privacy",
        "4605": "Data Management and Data Science",
        "4606": "Distributed Computing and Systems Software",
        "4607": "Graphics, Augmented Reality and Games",
        "4608": "Human-Centred Computing",
        "4609": "Information Systems",
        "4610": "Library and Information Studies",
        "4611": "Machine Learning",
        "4612": "Software Engineering",
        "4613": "Theory of Computation",
        "CSE": "Computer Science and Engineering",
    }
    
    RANK_WEIGHTS = {"A*": 4.0, "A": 2.0, "Journal": 1.0}
    
    area_counts = defaultdict(lambda: {"papers": 0, "score": 0.0, "weighted_score": 0.0, "astar": 0, "a": 0})
    
    for fac in faculty_results:
        for pub in fac["publications"]:
            for_code = pub.get("for_code", "Unknown")
            area_counts[for_code]["papers"] += 1
            area_counts[for_code]["score"] += pub["adjusted_count"]
            rank = pub.get("venue_rank", "")
            weight = RANK_WEIGHTS.get(rank, 1.0)
            area_counts[for_code]["weighted_score"] += pub["adjusted_count"] * weight
            if rank == "A*":
                area_counts[for_code]["astar"] += 1
            elif rank == "A":
                area_counts[for_code]["a"] += 1
    
    result = []
    for code, counts in sorted(area_counts.items()):
        result.append({
            "for_code": code,
            "description": for_descriptions.get(code, f"FoR {code}"),
            "papers": counts["papers"],
            "papers_astar": counts["astar"],
            "papers_a": counts["a"],
            "score": round(counts["score"], 4),
            "weighted_score": round(counts["weighted_score"], 4),
        })
    
    return result


def compute_geo_mean_score(area_breakdown):
    """Compute geometric mean of weighted_score across all areas."""
    weighted_scores = [a["weighted_score"] for a in area_breakdown if a["weighted_score"] > 0]
    if not weighted_scores:
        return 0.0
    return math.exp(sum(math.log(s) for s in weighted_scores) / len(weighted_scores))


def load_irins_data(inst_short=None):
    """Load IRINS publication data for an institution.

    Looks for per-institution file (irins_{short}.json).
    Falls back to legacy irins_publications.json only when inst_short is not given.
    """
    if inst_short:
        per_inst_file = os.path.join(IRINS_DIR, f"irins_{inst_short.lower()}.json")
        if os.path.exists(per_inst_file):
            with open(per_inst_file, "r") as f:
                return json.load(f)
        return None
    # Legacy fallback (no institution specified)
    legacy_file = os.path.join(IRINS_DIR, "irins_publications.json")
    if os.path.exists(legacy_file):
        with open(legacy_file, "r") as f:
            return json.load(f)
    return None


def extract_doi(pub):
    """Extract normalized DOI from a publication (works for both DBLP and IRINS).

    DBLP stores DOI in the url field (e.g., https://doi.org/10.1609/aaai.v34i10.7146).
    IRINS stores DOI in the doi field (e.g., 10.1609/aaai.v34i10.7146).
    """
    doi = pub.get("doi", "")
    if doi:
        return doi.lower().rstrip(".")
    url = pub.get("url", "")
    if url:
        m = re.search(r'doi\.org/(.+)', url)
        if m:
            return m.group(1).lower().rstrip(".")
    return None


def titles_match_fuzzy(title1, title2, threshold=0.80):
    """Check if two titles are near-duplicates.

    Uses two signals:
      - Containment: if one normalized title is a substring of the other
        (catches DBLP suffixes like 'Student Abstract', 'Demo', etc.)
      - Jaccard similarity >= threshold on word sets
    """
    norm1 = re.sub(r'[^a-z0-9 ]', '', title1.lower()).strip()
    norm2 = re.sub(r'[^a-z0-9 ]', '', title2.lower()).strip()
    if not norm1 or not norm2:
        return False

    # Containment check: one title is a prefix/subset of the other
    if norm1 in norm2 or norm2 in norm1:
        return True

    # Jaccard similarity on word sets
    words1 = set(norm1.split())
    words2 = set(norm2.split())
    jaccard = len(words1 & words2) / len(words1 | words2)
    return jaccard >= threshold


def merge_irins_into_faculty(faculty_results, irins_data):
    """Merge IRINS-sourced publications (journals + extra conferences) into DBLP results.

    Uses three-layer deduplication to avoid counting the same paper twice:
      1. DOI match — exact DOI comparison (highest confidence, ~89% coverage)
      2. Exact normalized title match
      3. Fuzzy title match — word-set Jaccard ≥ 0.80 for same-year papers
    """
    if not irins_data:
        return faculty_results

    def normalize_name(name):
        return re.sub(r'[^a-z]', '', name.lower())

    def name_keys(name):
        """Match keys for one person's name.

        Includes the fully normalised form plus an initials-stripped form, so
        IRINS's "Gautam Shroff" matches the roster's "Gautam M. Shroff" (and
        "V. Raghava Mutharaju" matches "Raghava Mutharaju") instead of being
        mistaken for a new person and double-counted.

        Initials are only stripped when >= 2 real tokens remain, so distinct
        people like "S. Kumar" / "R. Kumar" never collapse onto each other.
        """
        keys = {normalize_name(name)}
        tokens = [t for t in re.split(r'[^a-z]+', name.lower()) if t]
        core = [t for t in tokens if len(t) > 1]
        if len(core) >= 2:
            keys.add("".join(core))
        return keys

    # Build match-key -> irins faculty name lookup (first spelling wins).
    irins_by_name = {fac["name"]: fac for fac in irins_data.get("faculty", [])}
    key_to_irins_name = {}
    for irins_name in irins_by_name:
        for key in name_keys(irins_name):
            key_to_irins_name.setdefault(key, irins_name)

    merged_count = 0
    deduped_count = 0
    journal_count = 0
    matched_names = set()

    for fac_result in faculty_results:
        irins_name = None
        for key in name_keys(fac_result["name"]):
            if key in key_to_irins_name:
                irins_name = key_to_irins_name[key]
                break
        if not irins_name:
            continue
        irins_fac = irins_by_name[irins_name]

        matched_names.add(irins_name)

        def normalize_title(title):
            return re.sub(r'[^a-z0-9]', '', title.lower())

        # Build dedup sets from existing DBLP publications (and skipped ones)
        existing_titles = set()
        existing_dois = set()
        skipped_titles = set()
        skipped_dois = set()
        
        for pub in fac_result["publications"]:
            existing_titles.add(normalize_title(pub["title"]))
            doi = extract_doi(pub)
            if doi:
                existing_dois.add(doi)
                
        for pub in fac_result.get("skipped_publications", []):
            skipped_titles.add(normalize_title(pub["title"]))
            doi = extract_doi(pub)
            if doi:
                skipped_dois.add(doi)

        # Add source field to existing DBLP publications
        for pub in fac_result["publications"]:
            if "source" not in pub:
                pub["source"] = "dblp"
            if "pub_type" not in pub:
                pub["pub_type"] = "conference"

        # Merge IRINS publications
        for irins_pub in irins_fac.get("publications", []):
            # Block 0: Filter IRINS papers intrinsically
            if is_short_or_workshop_paper(irins_pub["title"], "", irins_pub.get("venue_full", "")):
                continue
                
            irins_doi = extract_doi(irins_pub)
            norm_title = normalize_title(irins_pub["title"])
            
            # Block 1: Check if DBLP actively skipped it (workshop/short)
            if irins_doi and irins_doi in skipped_dois:
                deduped_count += 1
                continue
            if norm_title in skipped_titles:
                deduped_count += 1
                continue
            
            # Block 2: Check if DBLP accepted it (already have it)
            if irins_doi and irins_doi in existing_dois:
                deduped_count += 1
                continue  # Definite duplicate
            if norm_title in existing_titles:
                deduped_count += 1
                continue  # Already have this from DBLP

            # Layer 3: Fuzzy title match (same year only) against accepted
            is_fuzzy_dup = False
            for existing_pub in fac_result["publications"]:
                if existing_pub.get("year") == irins_pub.get("year"):
                    if titles_match_fuzzy(existing_pub["title"], irins_pub["title"]):
                        is_fuzzy_dup = True
                        break
            # And against skipped
            for skipped_pub in fac_result.get("skipped_publications", []):
                if skipped_pub.get("year") == irins_pub.get("year"):
                    if titles_match_fuzzy(skipped_pub["title"], irins_pub["title"]):
                        is_fuzzy_dup = True
                        break
                        
            if is_fuzzy_dup:
                deduped_count += 1
                continue

            # Not a duplicate — add the publication
            fac_result["publications"].append(irins_pub)
            fac_result["score"] = round(fac_result["score"] + irins_pub["adjusted_count"], 4)
            fac_result["total_matched"] += 1
            existing_titles.add(norm_title)
            if irins_doi:
                existing_dois.add(irins_doi)
            merged_count += 1

            if irins_pub.get("pub_type") == "journal":
                fac_result["papers_journal"] = fac_result.get("papers_journal", 0) + 1
                journal_count += 1
            elif irins_pub.get("venue_rank") == "A*":
                fac_result["papers_astar"] += 1
            elif irins_pub.get("venue_rank") == "A":
                fac_result["papers_a"] += 1

        # Re-sort publications
        def sort_key(p):
            type_order = {"A*": 0, "A": 1, "Journal": 2}
            return (type_order.get(p.get("venue_rank", ""), 3), -p.get("year", 0), p.get("venue", ""))
        fac_result["publications"].sort(key=sort_key)

    # Add faculty found ONLY in IRINS (genuinely absent from faculty.json —
    # name variants of existing faculty were matched above, not re-added).
    new_faculty_count = 0
    for irins_name, irins_fac in irins_by_name.items():
        if irins_name not in matched_names and irins_fac.get("total_matched", 0) > 0:
            fac_result = {
                "name": irins_fac["name"],
                "dblp_pid": None,
                "irins_id": irins_fac.get("irins_id"),
                "irins_url": irins_fac.get("irins_url"),
                "role": irins_fac.get("role", ""),
                "homepage": irins_fac.get("homepage", ""),
                "score": irins_fac.get("score", 0),
                "papers_astar": irins_fac.get("papers_astar", 0),
                "papers_a": irins_fac.get("papers_a", 0),
                "papers_journal": irins_fac.get("papers_journal", 0),
                "total_matched": irins_fac.get("total_matched", 0),
                "publications": irins_fac.get("publications", []),
            }
            faculty_results.append(fac_result)
            new_faculty_count += 1

    print(f"  Merged {merged_count} IRINS publications ({journal_count} journals) into existing faculty")
    print(f"  Deduped {deduped_count} cross-source duplicates (DOI + title + fuzzy)")
    if new_faculty_count > 0:
        print(f"  Added {new_faculty_count} newly discovered faculty from IRINS")

    return faculty_results


def parse_codes(values):
    """--institution IITK --institution IITB  ==  --institution IITK,IITB"""
    if not values:
        return None
    return {c.strip().upper() for v in values for c in v.split(",") if c.strip()}


def main():
    global DELAY_SECONDS
    ap = argparse.ArgumentParser(
        description="Fetch DBLP publications and score them against ICORE A*/A venues.")
    ap.add_argument("--institution", action="append", metavar="CODE",
                    help="Only fetch these short codes (repeatable or comma-separated). "
                         "Every other institution is carried over from the existing "
                         "rankings.json instead of being re-fetched.")
    ap.add_argument("--max-age", dest="max_age", type=float, metavar="DAYS",
                    help="Re-fetch faculty whose cached DBLP data is older than DAYS "
                         "(this is how a refresh picks up new publications).")
    ap.add_argument("--refresh", action="store_true",
                    help="Ignore the fetch cache completely — equivalent to --max-age 0")
    ap.add_argument("--delay", type=float,
                    help=f"Seconds between DBLP calls (default {DELAY_SECONDS})")
    args = ap.parse_args()

    if args.delay is not None:
        DELAY_SECONDS = args.delay
    max_age_days = 0 if args.refresh else args.max_age

    print("=" * 60)
    print("SPARK — DBLP Publication Fetcher & Ranker")
    print("=" * 60)

    # Load ICORE conferences
    print(f"\nLoading ICORE conferences from {ICORE_FILE}...")
    icore_lookup = load_icore_conferences()
    print(f"  Loaded {len(icore_lookup)} conferences with DBLP keys")

    # Load faculty
    print(f"\nLoading faculty from {FACULTY_FILE}...")
    faculty_data = load_faculty()

    # Institution selection. `only` is None for a whole-roster run; otherwise
    # we fetch just those blocks and splice them into the previous rankings.
    only = parse_codes(args.institution)
    if only:
        known = {i.get("short", "").upper() for i in faculty_data["institutions"]}
        unknown = only - known
        if unknown:
            ap.error(f"not in {FACULTY_FILE}: {', '.join(sorted(unknown))}\n"
                     f"       known codes: {', '.join(sorted(known))}\n"
                     f"       (a brand-new college must go through resolve_pids.py + "
                     f"integrate_roster.py first)")
        targets = [i for i in faculty_data["institutions"]
                   if i.get("short", "").upper() in only]
        print(f"  Partial run: {', '.join(i['short'] for i in targets)} "
              f"({len(faculty_data['institutions']) - len(targets)} institutions carried over)")
    else:
        targets = faculty_data["institutions"]

    if max_age_days is not None:
        print(f"  Cache policy: re-fetch anything older than {max_age_days} day(s)")

    session = requests.Session()
    session.headers.update({
        "User-Agent": "SPARK-Academic-Ranking-Tool/1.0 (academic research project)"
    })

    fetch_cache = load_fetch_cache()
    if fetch_cache:
        print(f"\nResuming from {FETCH_CACHE_FILE}: {len(fetch_cache)} faculty already fetched")

    all_institutions = []

    for institution in targets:
        inst_name = institution["name"]
        print(f"\n{'─' * 60}")
        print(f"Processing: {inst_name}")
        print(f"{'─' * 60}")
        print(f"  Faculty count: {len(institution['faculty'])}")
        
        faculty_results = []
        
        for i, fac in enumerate(institution["faculty"]):
            was_cached = cache_lookup(fetch_cache, fac["dblp_pid"], max_age_days) is not None
            result = process_faculty_member(
                fac, icore_lookup, session, fetch_cache, max_age_days)
            faculty_results.append(result)

            # Only pace ourselves when we actually called DBLP; replaying the
            # checkpoint after an interrupted run should be instant.
            if not was_cached and i < len(institution["faculty"]) - 1:
                time.sleep(DELAY_SECONDS)
        
        # Sort faculty by score descending
        faculty_results.sort(key=lambda f: -f["score"])
        
        # Compute institution totals
        total_score = sum(f["score"] for f in faculty_results)
        total_astar = sum(f["papers_astar"] for f in faculty_results)
        total_a = sum(f["papers_a"] for f in faculty_results)
        total_papers = sum(f["total_matched"] for f in faculty_results)
        
        # Compute area breakdown
        area_breakdown = compute_area_breakdown(faculty_results, icore_lookup)
        geo_mean_score = compute_geo_mean_score(area_breakdown)
        
        inst_result = {
            "name": inst_name,
            "short": institution.get("short", inst_name),
            "country": institution.get("country", ""),
            "website": institution.get("website", ""),
            "total_score": round(total_score, 4),
            "geo_mean_score": round(geo_mean_score, 4),
            "total_papers": total_papers,
            "total_papers_astar": total_astar,
            "total_papers_a": total_a,
            "faculty_count": len(faculty_results),
            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "area_breakdown": area_breakdown,
            "faculty": faculty_results,
        }

        all_institutions.append(inst_result)
        
        print(f"\n  Institution Summary:")
        print(f"    Total score:    {total_score:.2f}")
        print(f"    A* papers:      {total_astar}")
        print(f"    A papers:       {total_a}")
        print(f"    Total matched:  {total_papers}")
    
    # Try to merge IRINS data (per-institution)
    print(f"\nMerging IRINS data...")
    for inst in all_institutions:
        inst_short = inst.get("short", "")
        irins_data = load_irins_data(inst_short)
        if irins_data:
            print(f"  Found IRINS data for {inst['name']}: {irins_data['total_faculty_scraped']} faculty, "
                  f"{irins_data['total_publications_matched']} matched publications")
            inst["faculty"] = merge_irins_into_faculty(inst["faculty"], irins_data)
            # Recompute totals after merge
            inst["total_score"] = round(sum(f["score"] for f in inst["faculty"]), 4)
            inst["total_papers_astar"] = sum(f["papers_astar"] for f in inst["faculty"])
            inst["total_papers_a"] = sum(f["papers_a"] for f in inst["faculty"])
            inst["total_papers_journal"] = sum(f.get("papers_journal", 0) for f in inst["faculty"])
            inst["total_papers"] = sum(f["total_matched"] for f in inst["faculty"])
            inst["faculty_count"] = len(inst["faculty"])
            # Re-sort faculty
            inst["faculty"].sort(key=lambda f: -f["score"])
            # Recompute area breakdown
            inst["area_breakdown"] = compute_area_breakdown(inst["faculty"], icore_lookup)
            inst["geo_mean_score"] = round(compute_geo_mean_score(inst["area_breakdown"]), 4)

            print(f"    Post-merge: score={inst['total_score']:.2f}  "
                  f"A*={inst['total_papers_astar']} A={inst['total_papers_a']} "
                  f"J={inst.get('total_papers_journal', 0)}")
        else:
            print(f"  No IRINS data for {inst['name']} (run scrape_irins.py --institution {inst_short})")

    # Splice into the previous rankings when only some institutions were run.
    # Blocks we didn't fetch are reused byte-for-byte; the freshly scored ones
    # replace their old selves, and the whole list is re-sorted so ranks stay
    # consistent with the new scores.
    carried = []
    if only:
        try:
            with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
                prior = json.load(f)
        except (OSError, ValueError):
            prior = None
        if prior is None:
            print(f"\nWARNING: no readable {OUTPUT_FILE} to merge into — writing "
                  f"only the {len(all_institutions)} institution(s) fetched this run.")
        else:
            fresh = {i["short"].upper() for i in all_institutions}
            carried = [i for i in prior.get("institutions", [])
                       if i.get("short", "").upper() not in fresh]
            all_institutions = all_institutions + carried
            print(f"\nCarried over {len(carried)} institution(s) from the previous rankings.")

    all_institutions.sort(key=lambda i: -i["geo_mean_score"])

    # Build final output
    # Load ICORE data for conference list in output
    with open(ICORE_FILE, "r") as f:
        icore_data = json.load(f)

    # Load journal data if available
    journal_count = 0
    if os.path.exists(JOURNALS_FILE):
        with open(JOURNALS_FILE, "r") as f:
            journals_data = json.load(f)
        journal_count = len(journals_data.get("journals", []))

    # Derived from the files on disk rather than from whichever institution
    # happened to be processed last, so a partial run can't drop "IRINS".
    any_irins = any(
        os.path.exists(os.path.join(IRINS_DIR, f"irins_{i['short'].lower()}.json"))
        for i in all_institutions if i.get("short")
    )

    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "year_range": [YEAR_START, YEAR_END],
        "conference_source": "ICORE2026",
        "journal_source": "Curated IEEE/ACM" if journal_count else None,
        "data_sources": ["DBLP"] + (["IRINS"] if any_irins else []),
        "total_conferences_tracked": len(icore_lookup),
        "total_conferences_astar": icore_data["total_a_star"],
        "total_conferences_a": icore_data["total_a"],
        "total_journals_tracked": journal_count,
        "institutions": all_institutions,
        "conferences": icore_data["conferences"],
    }

    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = OUTPUT_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    os.replace(tmp, OUTPUT_FILE)   # never leave a half-written rankings.json behind

    print(f"\n{'=' * 60}")
    print(f"✓ Rankings saved to {OUTPUT_FILE}")
    print(f"  {len(all_institutions)} institutions "
          f"({len(all_institutions) - len(carried)} scored this run, {len(carried)} carried over)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
