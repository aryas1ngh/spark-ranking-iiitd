import json
import os
import re
from django.core.management.base import BaseCommand
from api.models import Institution, Faculty, Conference, Publication, Authorship
from api.ingest import get_rank_tier, split_ee_url, venue_type_for

class Command(BaseCommand):
    help = 'Load IRINS data into the database from irins_publications.json'

    def handle(self, *args, **kwargs):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
        data_dir = os.path.join(base_dir, 'data')
        
        # Find all per-institution IRINS files (irins_*.json, excluding checkpoints)
        import glob
        irins_files = [f for f in glob.glob(os.path.join(data_dir, 'irins_*.json'))
                       if 'checkpoint' not in f and 'sitemap' not in f]
        
        if not irins_files:
            self.stdout.write(self.style.ERROR("No IRINS data files found (irins_*.json)."))
            return
        
        # Also check legacy file
        legacy_file = os.path.join(data_dir, 'irins_publications.json')
        if legacy_file in irins_files:
            irins_files.remove(legacy_file)  # Process per-institution files instead
            
        self.stdout.write(f"Found {len(irins_files)} IRINS data files")
            
        def normalize_name(name):
            return re.sub(r'[^a-z]', '', name.lower())
            
        def normalize_title(title):
            return re.sub(r'[^a-z0-9]', '', title.lower())

        total_new_faculty = 0
        total_pubs_added = 0
        
        for irins_file in irins_files:
            with open(irins_file, 'r') as f:
                irins_data = json.load(f)
            
            inst_name = irins_data.get('institution', '')
            if not inst_name:
                self.stdout.write(self.style.WARNING(f"Skipping {irins_file}: no institution name"))
                continue
                
            # Find or create the institution
            institution = Institution.objects.filter(name=inst_name).first()
            if not institution:
                self.stdout.write(self.style.WARNING(f"Institution '{inst_name}' not in DB, skipping {irins_file}"))
                continue
            
            self.stdout.write(f"\nProcessing IRINS data for {inst_name}...")
            
            # Build existing faculty lookup by normalized name
            existing_faculty = {normalize_name(f.name): f for f in Faculty.objects.filter(institution=institution)}
        
        new_faculty_count = 0
        pubs_added = 0
        
        for irins_fac in irins_data.get('faculty', []):
            name_norm = normalize_name(irins_fac['name'])
            faculty = existing_faculty.get(name_norm)
            
            if not faculty:
                dept = irins_fac.get("department", "").lower()
                if "computer science" not in dept and "cse" not in dept:
                    continue
                
                # Create new faculty
                faculty = Faculty.objects.create(
                    name=irins_fac['name'],
                    institution=institution,
                    irins_id=irins_fac['irins_id']
                )
                new_faculty_count += 1
            else:
                # Update existing faculty
                faculty.irins_id = irins_fac['irins_id']
                faculty.save()
                
            # Add publications
            existing_pubs = set(normalize_title(a.publication.title) for a in faculty.authorships.all())
            
            for pub in irins_fac.get('publications', []):
                pub_title_norm = normalize_title(pub['title'])
                if pub_title_norm in existing_pubs:
                    continue
                
                # Match conference/journal — try multiple strategies
                venue_acronym = pub.get('venue', '')
                venue_full = pub.get('venue_full', '')
                venue_rank = pub.get('venue_rank', '')
                
                conference = None
                
                # Strategy 1: Match by acronym (most reliable)
                if venue_acronym:
                    conference = Conference.objects.filter(acronym__iexact=venue_acronym).first()
                
                # Strategy 2: Match by full name (exact)
                if not conference and venue_full:
                    conference = Conference.objects.filter(full_name__iexact=venue_full).first()
                
                # Strategy 3: Match by full name (contains)
                if not conference and venue_full:
                    conference = Conference.objects.filter(full_name__icontains=venue_full[:50]).first()
                
                # Fallback: create a stub venue
                if not conference:
                    rank = 'Journal' if venue_rank == 'Journal' else 'Unknown'
                    conference = Conference.objects.create(
                        acronym=venue_acronym or venue_full[:10],
                        full_name=venue_full or venue_acronym,
                        # 'Unknown' is created on demand with weight 1.0, which
                        # is what an unrecognised rank has always scored.
                        core_rank=get_rank_tier(rank),
                        venue_type=venue_type_for(rank),
                    )

                doi, ee_url = split_ee_url(pub.get('doi', ''))
                # Year and venue join the lookup because (title, year, venue) is
                # the publication's natural key — matching on title alone could
                # attach this authorship to a same-named paper from another
                # venue, and would collide with the constraint on insert.
                publication, created = Publication.objects.get_or_create(
                    title=pub['title'],
                    year=pub['year'],
                    conference=conference,
                    defaults={
                        'doi': doi,
                        'ee_url': ee_url,
                        'num_authors': pub.get('num_authors'),
                    }
                )
                
                credit = pub.get('adjusted_count') or (1.0 / max(pub.get('num_authors', 1), 1))
                Authorship.objects.get_or_create(
                    faculty=faculty,
                    publication=publication,
                    defaults={'credit': credit}
                )
                pubs_added += 1
                
            total_new_faculty += new_faculty_count
            total_pubs_added += pubs_added
            self.stdout.write(f"  {inst_name}: {new_faculty_count} new faculty, {pubs_added} publications")
                
        self.stdout.write(self.style.SUCCESS(
            f"Loaded {total_new_faculty} new faculty members and {total_pubs_added} publications from IRINS data."
        ))
