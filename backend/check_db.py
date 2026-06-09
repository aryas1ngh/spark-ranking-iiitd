import os, django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
django.setup()
from api.models import Faculty, Publication, Authorship
for f in Faculty.objects.all(): print(f.name, f.irins_id)
print("Total Faculty:", Faculty.objects.count())
print("Total Pubs:", Publication.objects.count())
print("Total Authorships:", Authorship.objects.count())
