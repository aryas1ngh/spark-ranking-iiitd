import re
import time
import xml.etree.ElementTree as ET
import requests
from django.core.management.base import BaseCommand
from api.models import Faculty, Conference, Publication, Authorship

DBLP_BASE = "https://dblp.org"
MAX_RETRIES = 4
RETRY_BASE_DELAY = 5
YEAR_START = 2015
YEAR_END = 2026

class Command(BaseCommand):
    help = 'Fetch publications from DBLP and save to DB'

    def handle(self, *args, **kwargs):
        session = requests.Session()
        faculties = Faculty.objects.exclude(dblp_pid='')

        for faculty in faculties:
            self.stdout.write(f"Fetching publications for {faculty.name} (pid: {faculty.dblp_pid})...")
            pubs = self.fetch_author_publications(faculty.dblp_pid, session)
            
            # Filter by year and match against conferences
            matched_count = 0
            for pub in pubs:
                if not (YEAR_START <= pub['year'] <= YEAR_END):
                    continue
                
                # Check if it matches an ICORE conference
                if not pub['venue_key']:
                    continue
                
                # Match against dblp_key (case-insensitive)
                conference = Conference.objects.filter(dblp_key__iexact=pub['venue_key']).first()
                if not conference:
                    continue
                
                # Save Publication
                publication, created = Publication.objects.get_or_create(
                    dblp_key=pub['dblp_key'],
                    defaults={
                        'title': pub['title'],
                        'year': pub['year'],
                        'doi': pub['url'] if pub['url'] and 'doi.org' in pub['url'] else '',
                        'conference': conference,
                        'page_count': pub['page_count'],
                        'is_workshop': pub['is_workshop'],
                    }
                )
                
                # Save Authorship
                credit = 1.0 / max(pub['num_authors'], 1)
                Authorship.objects.update_or_create(
                    faculty=faculty,
                    publication=publication,
                    defaults={'credit': credit}
                )
                matched_count += 1
            
            self.stdout.write(self.style.SUCCESS(f"  Matched {matched_count} papers"))
            time.sleep(3) # Be polite to DBLP

    def fetch_author_publications(self, pid, session):
        url = f"{DBLP_BASE}/pid/{pid}.xml"
        resp = None
        for attempt in range(MAX_RETRIES):
            try:
                resp = session.get(url, timeout=30)
                resp.raise_for_status()
                break
            except requests.exceptions.RequestException as e:
                if resp is not None and resp.status_code == 404:
                    return []
                if attempt < MAX_RETRIES - 1:
                    time.sleep(RETRY_BASE_DELAY * (2 ** attempt))
                    continue
                else:
                    self.stderr.write(f"Failed to fetch {url} after {MAX_RETRIES} attempts: {e}")
                    return []
        
        if resp is None:
            return []
        
        root = ET.fromstring(resp.content)
        publications = []
        for r_elem in root.findall(".//r"):
            for pub_elem in r_elem:
                if pub_elem.tag != "inproceedings":
                    continue
                
                pub_key = pub_elem.get("key", "")
                title_elem = pub_elem.find("title")
                title = "".join(title_elem.itertext()).strip() if title_elem is not None else ""
                
                year_elem = pub_elem.find("year")
                year = int(year_elem.text) if year_elem is not None and year_elem.text else 0
                
                authors = [ "".join(a.itertext()).strip() for a in pub_elem.findall("author") ]
                
                venue_key = None
                key_match = re.match(r'conf/([^/]+)/', pub_key)
                if key_match:
                    venue_key = key_match.group(1)
                
                url_elem = pub_elem.find("ee")
                pub_url = url_elem.text if url_elem is not None else None
                
                # Parse pages to detect workshop papers (<= 5 pages)
                pages_elem = pub_elem.find("pages")
                pages_text = pages_elem.text if pages_elem is not None else ""
                page_count = None
                
                if pages_text:
                    # Match formats like "123-128" or "12-16"
                    match = re.search(r'(\d+)\s*-\s*(\d+)', pages_text)
                    if match:
                        try:
                            start_page = int(match.group(1))
                            end_page = int(match.group(2))
                            if end_page >= start_page:
                                page_count = end_page - start_page + 1
                        except ValueError:
                            pass
                    elif pages_text.isdigit():
                        # Sometimes it's just a single page number or total pages
                        page_count = 1
                
                is_workshop = False
                if page_count is not None and page_count <= 5:
                    is_workshop = True
                
                publications.append({
                    "title": title,
                    "year": year,
                    "venue_key": venue_key,
                    "num_authors": len(authors),
                    "dblp_key": pub_key,
                    "url": pub_url,
                    "page_count": page_count,
                    "is_workshop": is_workshop,
                })
        return publications
