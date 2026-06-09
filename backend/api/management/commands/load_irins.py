import json
import os
import re
from django.core.management.base import BaseCommand
from api.models import Institution, Faculty, Conference, Publication, Authorship

class Command(BaseCommand):
    help = 'Load IRINS data into the database from irins_publications.json'

    def handle(self, *args, **kwargs):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
        irins_file = os.path.join(base_dir, 'data', 'irins_publications.json')
        
        if not os.path.exists(irins_file):
            self.stdout.write(self.style.ERROR("irins_publications.json not found."))
            return
            
        with open(irins_file, 'r') as f:
            irins_data = json.load(f)
            
        def normalize_name(name):
            return re.sub(r'[^a-z]', '', name.lower())
            
        def normalize_title(title):
            return re.sub(r'[^a-z0-9]', '', title.lower())

        # Assume all from IIIT Delhi for now, as in the existing implementation
        iiitd = Institution.objects.get(name="IIIT Delhi")
        
        # Build existing faculty lookup by normalized name
        existing_faculty = {normalize_name(f.name): f for f in Faculty.objects.filter(institution=iiitd)}
        
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
                    institution=iiitd,
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
                
                # Match conference/journal
                venue_name = pub.get('venue_full', '') or pub.get('venue', '')
                if not venue_name:
                    continue
                
                # In IRINS, we need a fuzzy match to existing conferences/journals,
                # For this MVP loader, let's look for exact match or just create a stub
                # We can do an exact match on acronym if available, else by full name
                conference = Conference.objects.filter(full_name__iexact=venue_name).first()
                if not conference:
                    # Very simple fallback: create a stub venue if not found 
                    # (ideally we should use the same fuzzy matcher here as in python script)
                    conference = Conference.objects.create(
                        acronym=venue_name[:10],
                        full_name=venue_name,
                        core_rank='Unknown'
                    )
                
                publication, created = Publication.objects.get_or_create(
                    title=pub['title'],
                    defaults={
                        'year': pub['year'],
                        'conference': conference,
                        'doi': pub.get('doi', '')
                    }
                )
                
                credit = pub.get('adjusted_count') or (1.0 / max(pub.get('num_authors', 1), 1))
                Authorship.objects.get_or_create(
                    faculty=faculty,
                    publication=publication,
                    defaults={'credit': credit}
                )
                pubs_added += 1
                
        self.stdout.write(self.style.SUCCESS(f"Loaded {new_faculty_count} new faculty members and {pubs_added} publications from IRINS data."))
