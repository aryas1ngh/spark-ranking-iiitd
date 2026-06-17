import json
import os
from django.core.management.base import BaseCommand
from api.models import Institution, Faculty, Conference, Publication, Authorship

class Command(BaseCommand):
    help = 'Load publications from rankings.json into DB'

    def handle(self, *args, **kwargs):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
        rankings_file = os.path.join(base_dir, 'data', 'rankings.json')
        
        with open(rankings_file, 'r') as f:
            data = json.load(f)
            
        pub_count = 0
        auth_count = 0
        
        for inst_data in data.get('institutions', []):
            inst = Institution.objects.get(name=inst_data['name'])
            
            for fac_data in inst_data.get('faculty', []):
                # Try to find faculty
                faculty = Faculty.objects.filter(name=fac_data['name'], institution=inst).first()
                if not faculty:
                    self.stdout.write(self.style.WARNING(f"Faculty not found: {fac_data['name']}"))
                    continue
                
                for pub in fac_data.get('publications', []):
                    # Find conference
                    conf = Conference.objects.filter(acronym=pub['venue']).first()
                    if not conf:
                        conf = Conference.objects.create(
                            acronym=pub['venue'],
                            full_name=pub['venue_full'],
                            core_rank=pub['venue_rank'],
                            area=pub.get('for_code', '')
                        )
                    
                    # Create or get publication
                    publication, created = Publication.objects.get_or_create(
                        title=pub['title'],
                        year=pub['year'],
                        conference=conf,
                        defaults={
                            'doi': pub.get('url', '').replace('https://doi.org/', '') if pub.get('url') else None,
                            'is_workshop': False  # rankings.json already filters them
                        }
                    )
                    
                    if created:
                        pub_count += 1
                        
                    # Create authorship
                    Authorship.objects.update_or_create(
                        faculty=faculty,
                        publication=publication,
                        defaults={'credit': pub.get('adjusted_count', 1.0)}
                    )
                    auth_count += 1
                    
        self.stdout.write(self.style.SUCCESS(f"Loaded {pub_count} distinct publications and {auth_count} authorships."))
