import json
import os
from django.core.management.base import BaseCommand
from api.models import Institution, Faculty, Conference

class Command(BaseCommand):
    help = 'Load seed data into the database'

    def handle(self, *args, **kwargs):
        base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))
        data_dir = os.path.join(base_dir, 'data')

        # Load Conferences
        with open(os.path.join(data_dir, 'icore_conferences.json'), 'r') as f:
            icore_data = json.load(f)
            for conf in icore_data.get('conferences', []):
                Conference.objects.get_or_create(
                    acronym=conf['acronym'],
                    defaults={
                        'full_name': conf['title'],
                        'dblp_key': conf.get('dblp_key', ''),
                        'core_rank': conf['rank'],
                        'area': conf.get('for_code', '')
                    }
                )
        self.stdout.write(self.style.SUCCESS(f"Loaded {Conference.objects.count()} conferences"))

        # Load Journals
        journals_file = os.path.join(data_dir, 'ieee_acm_journals.json')
        if os.path.exists(journals_file):
            with open(journals_file, 'r') as f:
                journals_data = json.load(f)
                for journal in journals_data.get('journals', []):
                    Conference.objects.get_or_create(
                        acronym=journal['acronym'],
                        defaults={
                            'full_name': journal['title'],
                            'core_rank': 'Journal'
                        }
                    )
            self.stdout.write(self.style.SUCCESS("Loaded journals"))

        # Load Faculty & Institutions
        with open(os.path.join(data_dir, 'faculty.json'), 'r') as f:
            faculty_data = json.load(f)
            for inst_data in faculty_data.get('institutions', []):
                inst, created = Institution.objects.get_or_create(
                    name=inst_data['name'],
                    defaults={
                        'website': inst_data.get('website', ''),
                        'state': inst_data.get('state', ''),
                        'city': inst_data.get('city', '')
                    }
                )
                
                for fac_data in inst_data.get('faculty', []):
                    Faculty.objects.get_or_create(
                        name=fac_data['name'],
                        institution=inst,
                        defaults={
                            'dblp_pid': fac_data.get('dblp_pid', ''),
                            'designation': fac_data.get('role', ''),
                            'homepage': fac_data.get('homepage', '')
                        }
                    )
        
        self.stdout.write(self.style.SUCCESS(f"Loaded {Institution.objects.count()} institutions and {Faculty.objects.count()} faculty members"))
