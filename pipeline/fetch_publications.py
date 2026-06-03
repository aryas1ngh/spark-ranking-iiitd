#!/usr/bin/env python3
"""
Fetch publications from DBLP for all faculty members.
Matches publications against ICORE A*/A conferences.
Outputs data/rankings.json with scored results.
"""

import json
import os
import re
import sys
import time
import xml.etree.ElementTree as ET
from collections import defaultdict

import requests

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")

ICORE_FILE = os.path.join(DATA_DIR, "icore_conferences.json")
FACULTY_FILE = os.path.join(DATA_DIR, "faculty.json")
OUTPUT_FILE = os.path.join(DATA_DIR, "rankings.json")

DBLP_BASE = "https://dblp.org"
DELAY_SECONDS = 3.0  # DBLP rate limit compliance - be very polite
MAX_RETRIES = 4
RETRY_BASE_DELAY = 5  # seconds, doubles each retry
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
        except requests.exceptions.HTTPError:
            if resp is not None and resp.status_code == 404:
                print(f"      ⚠ PID not found: {pid}")
                return []
            if resp is not None and resp.status_code == 429:
                wait = RETRY_BASE_DELAY * (2 ** attempt)
                print(f"      ⚠ Rate limited (429). Waiting {wait}s before retry {attempt + 1}/{MAX_RETRIES}...")
                time.sleep(wait)
                continue
            raise
    else:
        print(f"      ✗ Failed after {MAX_RETRIES} retries for PID: {pid}")
        return []
    
    # Parse XML
    root = ET.fromstring(resp.content)
    publications = []
    
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
            
            publications.append({
                "title": title,
                "year": year,
                "booktitle": booktitle,
                "venue_key": venue_key,
                "num_authors": len(authors),
                "authors": authors,
                "dblp_key": pub_key,
                "url": pub_url,
            })
    
    return publications


def process_faculty_member(faculty, icore_lookup, session):
    """Process a single faculty member: fetch pubs, match against ICORE, compute score."""
    pid = faculty["dblp_pid"]
    name = faculty["name"]
    
    print(f"    → Fetching publications for {name} (pid: {pid})...")
    
    pubs = fetch_author_publications(pid, session)
    print(f"      Found {len(pubs)} conference papers total")
    
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
        "total_matched": len(matched_pubs),
        "publications": matched_pubs,
    }


def compute_area_breakdown(faculty_results, icore_lookup):
    """Compute publication counts grouped by research area (FoR code)."""
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
    
    area_counts = defaultdict(lambda: {"papers": 0, "score": 0.0, "astar": 0, "a": 0})
    
    for fac in faculty_results:
        for pub in fac["publications"]:
            for_code = pub.get("for_code", "Unknown")
            area_counts[for_code]["papers"] += 1
            area_counts[for_code]["score"] += pub["adjusted_count"]
            if pub["venue_rank"] == "A*":
                area_counts[for_code]["astar"] += 1
            else:
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
        })
    
    return result


def main():
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
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "SPARK-Academic-Ranking-Tool/1.0 (academic research project)"
    })
    
    all_institutions = []
    
    for institution in faculty_data["institutions"]:
        inst_name = institution["name"]
        print(f"\n{'─' * 60}")
        print(f"Processing: {inst_name}")
        print(f"{'─' * 60}")
        print(f"  Faculty count: {len(institution['faculty'])}")
        
        faculty_results = []
        
        for i, fac in enumerate(institution["faculty"]):
            result = process_faculty_member(fac, icore_lookup, session)
            faculty_results.append(result)
            
            if i < len(institution["faculty"]) - 1:
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
        
        inst_result = {
            "name": inst_name,
            "short": institution.get("short", inst_name),
            "country": institution.get("country", ""),
            "website": institution.get("website", ""),
            "total_score": round(total_score, 4),
            "total_papers": total_papers,
            "total_papers_astar": total_astar,
            "total_papers_a": total_a,
            "faculty_count": len(faculty_results),
            "area_breakdown": area_breakdown,
            "faculty": faculty_results,
        }
        
        all_institutions.append(inst_result)
        
        print(f"\n  Institution Summary:")
        print(f"    Total score:    {total_score:.2f}")
        print(f"    A* papers:      {total_astar}")
        print(f"    A papers:       {total_a}")
        print(f"    Total matched:  {total_papers}")
    
    # Sort institutions by total score
    all_institutions.sort(key=lambda i: -i["total_score"])
    
    # Build final output
    # Load ICORE data for conference list in output
    with open(ICORE_FILE, "r") as f:
        icore_data = json.load(f)
    
    output = {
        "generated_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "year_range": [YEAR_START, YEAR_END],
        "conference_source": "ICORE2026",
        "total_conferences_tracked": len(icore_lookup),
        "total_conferences_astar": icore_data["total_a_star"],
        "total_conferences_a": icore_data["total_a"],
        "institutions": all_institutions,
        "conferences": icore_data["conferences"],
    }
    
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n{'=' * 60}")
    print(f"✓ Rankings saved to {OUTPUT_FILE}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
