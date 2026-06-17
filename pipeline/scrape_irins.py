#!/usr/bin/env python3
"""
Scrape faculty publications from IRINS profiles.
Matches against ICORE A*/A conferences and curated IEEE/ACM journals.
Outputs data/irins_publications.json.

College-agnostic: change BASE_URL and SITEMAP_FILE to target any IRINS instance.

Usage:
    python pipeline/scrape_irins.py                    # Full scrape
    python pipeline/scrape_irins.py --test-single 61462  # Test single profile
    python pipeline/scrape_irins.py --resume             # Resume interrupted run
"""

import argparse
import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict

import requests
from bs4 import BeautifulSoup

# ──────────────────────────────────────────────────────────────────
# Configuration — change these to target a different college
# ──────────────────────────────────────────────────────────────────
BASE_URL = "https://iiitd.irins.org"
INSTITUTION_NAME = "IIIT Delhi"
INSTITUTION_SHORT = "IIITD"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")

SITEMAP_FILE = os.path.join(DATA_DIR, "irins_sitemap.xml")
ICORE_FILE = os.path.join(DATA_DIR, "icore_conferences.json")
JOURNALS_FILE = os.path.join(DATA_DIR, "ieee_acm_journals.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "irins_publications.json")
CHECKPOINT_FILE = os.path.join(DATA_DIR, "irins_checkpoint.json")

YEAR_START = 2015
YEAR_END = 2026
DELAY_SECONDS = 0.5  # IRINS is less strict than DBLP
PUBS_PER_PAGE = 5    # IRINS returns 5 per page
MAX_PAGES = 100      # Safety limit

HEADERS = {"User-Agent": "SPARK-Academic-Ranking-Tool/1.0 (academic research project)"}

# Department keywords for filtering — only faculty whose department
# contains one of these (case-insensitive) will be included.
CS_DEPARTMENT_KEYWORDS = [
    "computer science",
    "computer engineering",
    "cse",
    "csam",  # CS + Applied Math at some IITs
]


# ──────────────────────────────────────────────────────────────────
# Sitemap parsing
# ──────────────────────────────────────────────────────────────────
def parse_sitemap(sitemap_path):
    """Parse IRINS sitemap XML → list of {name, profile_id, url}."""
    with open(sitemap_path, "r") as f:
        text = f.read()

    # Extract profile IDs and names from <loc> + <!-- Name --> pairs
    pattern = r"<loc>https?://[^/]+/profile/(\d+)</loc>.*?<!-- (.+?) -->"
    entries = []
    seen_ids = set()

    for m in re.finditer(pattern, text, re.DOTALL):
        pid = m.group(1)
        name = m.group(2).strip()
        if pid not in seen_ids:
            seen_ids.add(pid)
            entries.append({
                "name": name,
                "profile_id": pid,
                "url": f"{BASE_URL}/profile/{pid}",
            })

    return entries


# ──────────────────────────────────────────────────────────────────
# Conference & journal matching
# ──────────────────────────────────────────────────────────────────
def build_conference_matcher(icore_path):
    """Build lookup structures for matching IRINS venue text to ICORE conferences.

    Returns:
        - acronym_lookup: {normalized_acronym: conference_dict}
        - name_fragments: [(fragment, conference_dict)] sorted longest-first
    """
    with open(icore_path, "r") as f:
        data = json.load(f)

    acronym_lookup = {}
    name_fragments = []

    for conf in data["conferences"]:
        acr = conf["acronym"].strip().upper()
        acronym_lookup[acr] = conf

        # Also add common variants
        # e.g., "ACMMM" -> also match "ACM MM"
        if acr == "ACMMM":
            acronym_lookup["ACM MM"] = conf
        if acr == "SIGIR":
            acronym_lookup["ACM SIGIR"] = conf

        # Build name fragment for fuzzy matching
        title = conf["title"].lower()
        name_fragments.append((title, conf))

    # Sort fragments longest first for greedy matching
    name_fragments.sort(key=lambda x: -len(x[0]))

    return acronym_lookup, name_fragments


def build_journal_matcher(journals_path):
    """Build lookup structures for matching IRINS venue text to IEEE/ACM journals.

    Returns:
        - name_variants: [(normalized_variant, journal_dict)] sorted longest-first
    """
    with open(journals_path, "r") as f:
        data = json.load(f)

    name_variants = []
    for journal in data["journals"]:
        # Add the full title
        name_variants.append((journal["title"].lower(), journal))
        # Add acronym
        name_variants.append((journal["acronym"].lower(), journal))
        # Add all name variants
        for variant in journal.get("name_variants", []):
            name_variants.append((variant.lower(), journal))

    # Sort longest first for greedy matching
    name_variants.sort(key=lambda x: -len(x[0]))
    return name_variants


def normalize_venue(venue_text):
    """Normalize IRINS venue text for matching."""
    if not venue_text:
        return ""
    # Remove extra whitespace, commas, volume info
    text = re.sub(r"\s+", " ", venue_text).strip()
    text = text.rstrip(",").strip()
    return text


def match_conference(venue_text, pub_type, acronym_lookup, name_fragments):
    """Try to match venue text against ICORE conferences.

    Returns conference dict or None.
    """
    if not venue_text or pub_type != "Conference Paper":
        return None

    normalized = normalize_venue(venue_text).lower()

    # Strategy 1: Extract acronym from venue text and do exact lookup
    # Common patterns: "... AAAI ...", "Proceedings of AAAI", "ICML 2023", etc.
    # Also handle: "Proceedings IEEE International Conference on Multimedia and Expo"
    # where the acronym may not appear but the conference name does.

    # Try acronym extraction — look for known acronyms in the text
    upper_venue = venue_text.upper()
    for acr, conf in acronym_lookup.items():
        # Word-boundary match for the acronym
        pattern = r'\b' + re.escape(acr) + r'\b'
        if re.search(pattern, upper_venue):
            return conf

    # Strategy 2: Name fragment matching
    for fragment, conf in name_fragments:
        if fragment in normalized:
            return conf

    return None


def match_journal(venue_text, pub_type, journal_variants):
    """Try to match venue text against IEEE/ACM journal list.

    Returns journal dict or None.
    """
    if not venue_text or pub_type not in ("Article", "Review", "Editorial"):
        return None

    normalized = normalize_venue(venue_text).lower()

    for variant, journal in journal_variants:
        if variant in normalized:
            return journal

    return None


# ──────────────────────────────────────────────────────────────────
# IRINS publication scraping
# ──────────────────────────────────────────────────────────────────
def fetch_all_publications(session, expert_id):
    """Fetch all publications for a faculty member from IRINS API.

    Returns list of raw publication dicts (deduplicated).
    """
    url = f"{BASE_URL}/profile/get_publication"
    headers = {**HEADERS, "X-Requested-With": "XMLHttpRequest"}
    all_pubs = []
    seen_keys = set()
    page = 0

    while page < MAX_PAGES:
        data = {
            "expert_id": expert_id,
            "current_page": str(page),
            "sort_by": "year",
            "direction": "desc",
        }

        try:
            resp = session.post(url, headers=headers, data=data, timeout=15)
            if not resp.text.strip():
                break

            soup = BeautifulSoup(resp.text, "html.parser")
            boxes = soup.find_all("div", class_="funny-boxes")
            if not boxes:
                break

            for pub_div in boxes:
                pub = parse_publication_div(pub_div)
                if pub:
                    # Deduplicate: use DOI as primary key, fall back to title+year
                    dedup_key = pub.get("doi") or f"{pub['title'].lower().strip()}|{pub.get('year', '')}"
                    if dedup_key not in seen_keys:
                        seen_keys.add(dedup_key)
                        all_pubs.append(pub)

            page += 1
            time.sleep(DELAY_SECONDS)

        except Exception as e:
            print(f"      ⚠ Error on page {page}: {e}")
            break

    return all_pubs


def parse_publication_div(pub_div):
    """Parse a single funny-boxes div into a publication dict."""
    # Title
    title_tag = pub_div.find("h2")
    if not title_tag:
        return None
    title = title_tag.get_text(strip=True)

    # Authors
    author_tag = pub_div.find("p", class_="author")
    authors_str = author_tag.get_text(strip=True) if author_tag else ""
    # Split authors by semicolons
    authors = [a.strip() for a in authors_str.split(";") if a.strip()] if authors_str else []

    # Publication type (Conference Paper, Article, Review, etc.)
    type_tag = pub_div.find("span", class_="label")
    pub_type = type_tag.get_text(strip=True) if type_tag else ""

    # Venue text — text after the label tag, before the <strong>Year</strong> tag
    venue_text = ""
    if type_tag:
        for sib in type_tag.next_siblings:
            if hasattr(sib, "name") and sib.name in ("strong", "div"):
                break
            if isinstance(sib, str):
                venue_text += sib
    venue_text = venue_text.strip().rstrip(",").strip()

    # Year — from <strong>Year </strong>YYYY pattern
    year = None
    strong_tag = pub_div.find("strong", string=lambda t: t and "Year" in t)
    if strong_tag and strong_tag.next_sibling:
        year_str = str(strong_tag.next_sibling).strip()
        m = re.search(r"(\d{4})", year_str)
        if m:
            year = int(m.group(1))

    # DOI
    doi = None
    doi_link = None
    for a_tag in pub_div.find_all("a"):
        href = a_tag.get("href", "")
        if "doi.org/" in href:
            doi_link = href
            doi_match = re.search(r"doi\.org/(.+?)$", href)
            if doi_match:
                doi = doi_match.group(1)
            break

    return {
        "title": title,
        "authors": authors,
        "num_authors": len(authors),
        "type": pub_type,
        "venue_text": venue_text,
        "year": year,
        "doi": doi,
        "doi_link": doi_link,
    }


# ──────────────────────────────────────────────────────────────────
# Checkpoint/resume
# ──────────────────────────────────────────────────────────────────
def load_checkpoint():
    """Load checkpoint if exists."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE, "r") as f:
            return json.load(f)
    return {"completed": [], "results": {}}


def save_checkpoint(checkpoint):
    """Save checkpoint after each faculty member."""
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(checkpoint, f, indent=2, ensure_ascii=False)


# ──────────────────────────────────────────────────────────────────
# Faculty profile metadata
# ──────────────────────────────────────────────────────────────────
def fetch_profile_metadata(session, profile_id):
    """Fetch basic profile info (designation, department) from IRINS profile page.

    Department is extracted from the experience section, which contains the actual
    department name (e.g. 'Department of Computer Science and Engineering'), unlike
    the sidebar which only shows the institution name.
    """
    url = f"{BASE_URL}/profile/{profile_id}"
    try:
        resp = session.get(url, headers=HEADERS, timeout=15)
        soup = BeautifulSoup(resp.text, "html.parser")

        # Designation — from sidebar
        role = ""
        for li in soup.find_all("li"):
            icon = li.find("i", class_="fa-suitcase")
            if icon:
                role = li.get_text(strip=True)
                break

        # Department — from the experience section (most recent position)
        # The experience section has the *actual* department name.
        department = ""
        exp_div = soup.find("div", id="list_panel_experience")
        if exp_div:
            first_label = exp_div.find("div", class_="cbp_tmlabel")
            if first_label:
                ps = first_label.find_all("p")
                if ps:
                    department = ps[0].get_text(strip=True)

        # Homepage
        homepage = ""
        url_span = soup.find("span", id="p_p_url")
        if url_span:
            link = url_span.find("a")
            if link:
                homepage = link.get("href", "")

        return {
            "role": role,
            "department": department,
            "homepage": homepage,
        }

    except Exception as e:
        print(f"      ⚠ Could not fetch profile metadata: {e}")
        return {"role": "", "department": "", "homepage": ""}


def is_cs_faculty(department):
    """Check if a department string indicates CS/CSE."""
    if not department:
        return False
    dept_lower = department.lower()
    return any(kw in dept_lower for kw in CS_DEPARTMENT_KEYWORDS)


def is_short_or_workshop_paper(title):
    """Check if paper is a short paper, demo, or workshop paper based on title heuristics."""
    pattern = r'\b(demo|poster|student abstract|doctoral consortium|extended abstract|tutorial|workshop|companion)\b'
    if re.search(pattern, title.lower()):
        return True
    return False


# ──────────────────────────────────────────────────────────────────
# Main processing
# ──────────────────────────────────────────────────────────────────
def process_faculty(entry, session, conf_acr, conf_frags, journal_variants, skip_metadata=False):
    """Process a single faculty member: fetch pubs, match, score."""
    name = entry["name"]
    pid = entry["profile_id"]

    print(f"    → Fetching publications for {name} (ID: {pid})...")

    # Fetch profile metadata (role, department)
    meta = {"role": "", "department": "", "homepage": ""}
    if not skip_metadata:
        meta = fetch_profile_metadata(session, pid)
        time.sleep(DELAY_SECONDS)

    # Fetch all publications
    raw_pubs = fetch_all_publications(session, pid)
    print(f"      Found {len(raw_pubs)} publications total")

    # Filter by year
    raw_pubs = [p for p in raw_pubs if p["year"] and YEAR_START <= p["year"] <= YEAR_END]
    print(f"      {len(raw_pubs)} in year range {YEAR_START}-{YEAR_END}")

    # Match against conferences and journals
    matched_pubs = []
    total_score = 0.0
    papers_astar = 0
    papers_a = 0
    papers_journal = 0
    conf_count = 0
    journal_count = 0

    for pub in raw_pubs:
        # Check title heuristics to skip short/workshop papers
        if is_short_or_workshop_paper(pub["title"]):
            continue
            
        matched_conf = match_conference(pub["venue_text"], pub["type"], conf_acr, conf_frags)
        matched_journal = match_journal(pub["venue_text"], pub["type"], journal_variants)

        if matched_conf:
            adjusted_count = 1.0 / max(pub["num_authors"], 1)
            total_score += adjusted_count
            rank = matched_conf["rank"]
            if rank == "A*":
                papers_astar += 1
            elif rank == "A":
                papers_a += 1
            conf_count += 1

            matched_pubs.append({
                "title": pub["title"],
                "venue": matched_conf["acronym"],
                "venue_full": matched_conf["title"],
                "venue_rank": rank,
                "year": pub["year"],
                "num_authors": pub["num_authors"],
                "authors": pub["authors"],
                "adjusted_count": round(adjusted_count, 4),
                "doi": pub.get("doi"),
                "url": pub.get("doi_link"),
                "for_code": matched_conf.get("for_code", ""),
                "source": "irins",
                "pub_type": "conference",
            })

        elif matched_journal:
            adjusted_count = 1.0 / max(pub["num_authors"], 1)
            total_score += adjusted_count
            papers_journal += 1
            journal_count += 1

            matched_pubs.append({
                "title": pub["title"],
                "venue": matched_journal["acronym"],
                "venue_full": matched_journal["title"],
                "venue_rank": "Journal",
                "publisher": matched_journal["publisher"],
                "year": pub["year"],
                "num_authors": pub["num_authors"],
                "authors": pub["authors"],
                "adjusted_count": round(adjusted_count, 4),
                "doi": pub.get("doi"),
                "url": pub.get("doi_link"),
                "source": "irins",
                "pub_type": "journal",
            })

    # Sort: conferences first (A* then A), then journals, all by year desc
    def sort_key(p):
        type_order = {"A*": 0, "A": 1, "Journal": 2}
        return (type_order.get(p["venue_rank"], 3), -p["year"], p["venue"])

    matched_pubs.sort(key=sort_key)

    total_conf = papers_astar + papers_a
    print(f"      Matched: {total_conf} conf ({papers_astar} A*, {papers_a} A) + {papers_journal} journals")
    print(f"      Score: {total_score:.2f}")

    return {
        "name": name,
        "irins_id": pid,
        "irins_url": entry["url"],
        "role": meta["role"],
        "department": meta["department"],
        "homepage": meta["homepage"],
        "score": round(total_score, 4),
        "papers_astar": papers_astar,
        "papers_a": papers_a,
        "papers_journal": papers_journal,
        "total_matched": len(matched_pubs),
        "total_scraped": len(raw_pubs),
        "publications": matched_pubs,
    }


def main():
    parser = argparse.ArgumentParser(description="Scrape IRINS faculty publications")
    parser.add_argument("--test-single", type=str, help="Test with a single profile ID")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--no-dept-filter", action="store_true",
                        help="Include ALL departments (default: CS/CSE only)")
    args = parser.parse_args()

    print("=" * 60)
    print("SPARK — IRINS Publication Scraper")
    print("=" * 60)

    # Load matchers
    print(f"\nLoading ICORE conferences from {ICORE_FILE}...")
    conf_acr, conf_frags = build_conference_matcher(ICORE_FILE)
    print(f"  Loaded {len(conf_acr)} conference acronyms")

    print(f"Loading IEEE/ACM journals from {JOURNALS_FILE}...")
    journal_variants = build_journal_matcher(JOURNALS_FILE)
    print(f"  Loaded {len(journal_variants)} journal name variants")

    # Session
    session = requests.Session()
    session.headers.update(HEADERS)

    # Single-profile test mode
    if args.test_single:
        pid = args.test_single
        print(f"\n{'─' * 60}")
        print(f"TEST MODE: Profile {pid}")
        print(f"{'─' * 60}")
        entry = {"name": f"Test Profile {pid}", "profile_id": pid, "url": f"{BASE_URL}/profile/{pid}"}
        result = process_faculty(entry, session, conf_acr, conf_frags, journal_variants)
        print(f"\n  Results:")
        print(json.dumps(result, indent=2, ensure_ascii=False)[:3000])
        return

    # Parse sitemap
    print(f"\nParsing sitemap: {SITEMAP_FILE}...")
    entries = parse_sitemap(SITEMAP_FILE)
    print(f"  Found {len(entries)} faculty profiles")

    # Load checkpoint if resuming
    checkpoint = {"completed": [], "results": {}}
    if args.resume:
        checkpoint = load_checkpoint()
        print(f"  Resuming: {len(checkpoint['completed'])} already completed")

    # Process all faculty
    print(f"\n{'─' * 60}")
    print(f"Processing: {INSTITUTION_NAME}")
    print(f"{'─' * 60}")

    all_results = []
    # Load previously completed results
    for pid in checkpoint["completed"]:
        if pid in checkpoint["results"]:
            all_results.append(checkpoint["results"][pid])

    dept_filter = not args.no_dept_filter
    if dept_filter:
        print(f"  Department filter: ON (CS/CSE keywords: {CS_DEPARTMENT_KEYWORDS})")
    else:
        print(f"  Department filter: OFF (all departments)")

    skipped_checkpoint = 0
    skipped_dept = 0
    for i, entry in enumerate(entries, 1):
        pid = entry["profile_id"]

        if pid in checkpoint["completed"]:
            # Reload from checkpoint but apply department filter
            if pid in checkpoint["results"]:
                cached = checkpoint["results"][pid]
                if dept_filter and not is_cs_faculty(cached.get("department", "")):
                    skipped_dept += 1
                elif cached not in all_results:
                    all_results.append(cached)
            skipped_checkpoint += 1
            continue

        print(f"\n  [{i}/{len(entries)}]")

        # Always fetch metadata so we can filter by department
        meta = fetch_profile_metadata(session, pid)
        time.sleep(DELAY_SECONDS)

        if dept_filter and not is_cs_faculty(meta.get("department", "")):
            print(f"    → Skipping {entry['name']} (dept: {meta.get('department', 'unknown')})")
            # Still save to checkpoint so we don't re-fetch on resume
            checkpoint["completed"].append(pid)
            checkpoint["results"][pid] = {
                "name": entry["name"], "irins_id": pid, "irins_url": entry["url"],
                "department": meta.get("department", ""), "role": meta.get("role", ""),
                "homepage": meta.get("homepage", ""),
                "score": 0, "papers_astar": 0, "papers_a": 0, "papers_journal": 0,
                "total_matched": 0, "total_scraped": 0, "publications": [],
                "_skipped_dept": True,
            }
            save_checkpoint(checkpoint)
            skipped_dept += 1
            continue

        # Inject pre-fetched metadata into the entry
        entry["_prefetched_meta"] = meta

        result = process_faculty(
            entry, session, conf_acr, conf_frags, journal_variants,
            skip_metadata=True,  # Already fetched above
        )
        # Patch in the metadata we already fetched
        result["role"] = meta["role"]
        result["department"] = meta["department"]
        result["homepage"] = meta["homepage"]
        all_results.append(result)

        # Update checkpoint
        checkpoint["completed"].append(pid)
        checkpoint["results"][pid] = result
        save_checkpoint(checkpoint)

        # Rate limiting
        time.sleep(DELAY_SECONDS)

    if skipped_checkpoint > 0:
        print(f"\n  Skipped {skipped_checkpoint} already-completed profiles")
    if skipped_dept > 0:
        print(f"  Skipped {skipped_dept} non-CS department profiles")

    # Sort by score
    all_results.sort(key=lambda r: -r["score"])

    # Compute totals
    total_score = sum(r["score"] for r in all_results)
    total_astar = sum(r["papers_astar"] for r in all_results)
    total_a = sum(r["papers_a"] for r in all_results)
    total_journal = sum(r["papers_journal"] for r in all_results)
    total_matched = sum(r["total_matched"] for r in all_results)
    total_scraped = sum(r["total_scraped"] for r in all_results)

    # Build output
    output = {
        "source": "IRINS",
        "institution": INSTITUTION_NAME,
        "institution_short": INSTITUTION_SHORT,
        "base_url": BASE_URL,
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "year_range": [YEAR_START, YEAR_END],
        "conference_source": "ICORE2026",
        "journal_source": "Curated IEEE/ACM",
        "total_faculty_scraped": len(all_results),
        "total_publications_scraped": total_scraped,
        "total_publications_matched": total_matched,
        "total_score": round(total_score, 4),
        "total_papers_astar": total_astar,
        "total_papers_a": total_a,
        "total_papers_journal": total_journal,
        "faculty": all_results,
    }

    # Save output
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)

    # Clean up checkpoint on successful completion
    if os.path.exists(CHECKPOINT_FILE):
        os.remove(CHECKPOINT_FILE)
        print("  Cleaned up checkpoint file")

    # Summary
    print(f"\n{'=' * 60}")
    print(f"Summary")
    print(f"{'=' * 60}")
    print(f"  Faculty scraped:       {len(all_results)}")
    print(f"  Total pubs scraped:    {total_scraped}")
    print(f"  Matched (A* conf):     {total_astar}")
    print(f"  Matched (A conf):      {total_a}")
    print(f"  Matched (IEEE/ACM J):  {total_journal}")
    print(f"  Total matched:         {total_matched}")
    print(f"  Total score:           {total_score:.2f}")
    print(f"\n  ✓ Saved to {OUTPUT_FILE}")
    print(f"{'=' * 60}")

    # Print top 10 faculty
    print(f"\n  Top 10 Faculty:")
    for i, r in enumerate(all_results[:10], 1):
        print(f"    {i:2d}. {r['name']:<30s}  score={r['score']:.2f}  "
              f"A*={r['papers_astar']} A={r['papers_a']} J={r['papers_journal']}")


if __name__ == "__main__":
    main()
