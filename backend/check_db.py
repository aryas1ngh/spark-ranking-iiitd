#!/usr/bin/env python3
import django, os, sys
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
django.setup()

from api.models import Publication, Authorship, Conference, Faculty, Institution

print("=== DATABASE STATUS ===")
print(f"Institutions : {Institution.objects.count()}")
print(f"Faculty      : {Faculty.objects.count()}")
print(f"Publications : {Publication.objects.count()}")
print(f"Authorships  : {Authorship.objects.count()}")

jp = Publication.objects.filter(conference__venue_type='journal').count()
cp = Publication.objects.filter(conference__venue_type='conference').count()
print(f"\nPub breakdown - conferences:{cp}  journals:{jp}")

jv = Conference.objects.filter(venue_type='journal').count()
cv = Conference.objects.filter(venue_type='conference').count()
print(f"Venue breakdown - conferences:{cv}  journals:{jv}")

# Sample top 3 institutions by pub count
from django.db.models import Count
top = Institution.objects.annotate(n=Count('faculty__authorships')).order_by('-n')[:3]
print("\nTop 3 institutions by authorships:")
for inst in top:
    print(f"  {inst.name}: {inst.n}")
print("=== DONE ===")
