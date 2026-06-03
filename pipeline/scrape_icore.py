#!/usr/bin/env python3
"""
Scrape ICORE2026 A* and A conference rankings from portal.core.edu.au.
Outputs data/icore_conferences.json with DBLP venue keys for matching.
"""

import json
import os
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

BASE_URL = "http://portal.core.edu.au/conf-ranks/"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
OUTPUT_FILE = os.path.join(OUTPUT_DIR, "icore_conferences.json")

# Use ICORE2026 source
PARAMS_BASE = {
    "search": "",
    "by": "all",
    "source": "ICORE2026",
    "sort": "arank",
}

DELAY_SECONDS = 2  # Be polite to the server


def extract_dblp_key(dblp_url):
    """Extract DBLP venue key from a DBLP URL.
    
    Examples:
        https://dblp.uni-trier.de/db/conf/aaai -> aaai
        https://dblp.org/db/conf/chi -> chi
    """
    if not dblp_url:
        return None
    # Match conf/KEY or journals/KEY pattern
    match = re.search(r'/db/(conf|journals)/([^/\s]+)', dblp_url)
    if match:
        return match.group(2)
    return None


def scrape_page(page_num, session):
    """Scrape a single page of results from the ICORE portal."""
    params = {**PARAMS_BASE, "page": str(page_num)}
    
    print(f"  Fetching page {page_num}...")
    resp = session.get(BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, "html.parser")
    conferences = []
    
    # Find all table rows (skip header)
    rows = soup.select("table tr.evenrow, table tr.oddrow")
    
    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 7:
            continue
        
        title = cells[0].get_text(strip=True)
        acronym = cells[1].get_text(strip=True)
        source = cells[2].get_text(strip=True)
        rank = cells[3].get_text(strip=True)
        
        # Extract DBLP URL
        dblp_link = cells[5].find("a")
        dblp_url = dblp_link["href"] if dblp_link else None
        dblp_key = extract_dblp_key(dblp_url)
        
        # FoR code
        for_code = cells[6].get_text(strip=True)
        
        conferences.append({
            "title": title,
            "acronym": acronym,
            "rank": rank,
            "source": source,
            "dblp_key": dblp_key,
            "dblp_url": dblp_url,
            "for_code": for_code,
        })
    
    return conferences


def get_total_pages(session):
    """Get the total number of pages from the first page."""
    params = {**PARAMS_BASE, "page": "1"}
    resp = session.get(BASE_URL, params=params, timeout=30)
    resp.raise_for_status()
    
    soup = BeautifulSoup(resp.text, "html.parser")
    
    # Look for "Showing results 1 - 50 of 987"
    text = soup.get_text()
    match = re.search(r'Showing results \d+ - \d+ of (\d+)', text)
    if match:
        total = int(match.group(1))
        return (total + 49) // 50  # Ceiling division
    return 20  # Fallback


def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    session = requests.Session()
    session.headers.update({
        "User-Agent": "SPARK-Academic-Ranking-Tool/1.0 (academic research project)"
    })
    
    print("=" * 60)
    print("SPARK — ICORE2026 Conference Scraper")
    print("=" * 60)
    
    # Get total pages
    total_pages = get_total_pages(session)
    print(f"\nTotal pages to scrape: {total_pages}")
    
    all_conferences = []
    
    for page in range(1, total_pages + 1):
        try:
            conferences = scrape_page(page, session)
            all_conferences.extend(conferences)
            print(f"    → Got {len(conferences)} conferences (total: {len(all_conferences)})")
        except Exception as e:
            print(f"    ✗ Error on page {page}: {e}")
        
        if page < total_pages:
            time.sleep(DELAY_SECONDS)
    
    # Filter to A* and A only
    a_star = [c for c in all_conferences if c["rank"] == "A*"]
    a_rank = [c for c in all_conferences if c["rank"] == "A"]
    filtered = a_star + a_rank
    
    # Count those with DBLP keys
    with_dblp = [c for c in filtered if c["dblp_key"]]
    without_dblp = [c for c in filtered if not c["dblp_key"]]
    
    print(f"\n{'=' * 60}")
    print(f"Results Summary:")
    print(f"  Total scraped:     {len(all_conferences)}")
    print(f"  A* conferences:    {len(a_star)}")
    print(f"  A conferences:     {len(a_rank)}")
    print(f"  A*/A total:        {len(filtered)}")
    print(f"  With DBLP key:     {len(with_dblp)}")
    print(f"  Without DBLP key:  {len(without_dblp)}")
    
    if without_dblp:
        print(f"\n  Conferences without DBLP key (cannot match publications):")
        for c in without_dblp:
            print(f"    - {c['acronym']}: {c['title']}")
    
    # Save
    output = {
        "source": "ICORE2026",
        "scraped_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "total_all_ranks": len(all_conferences),
        "total_a_star": len(a_star),
        "total_a": len(a_rank),
        "conferences": filtered,
    }
    
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, indent=2, ensure_ascii=False)
    
    print(f"\n  ✓ Saved to {OUTPUT_FILE}")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
