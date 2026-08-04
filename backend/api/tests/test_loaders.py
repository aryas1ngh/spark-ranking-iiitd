"""Rebuild the database from the pipeline's JSON and check it satisfies the schema.

The publication and authorship tables are a materialised view over
data/rankings.json — load_rankings deletes and reinserts them wholesale — so the
real test of a schema change is whether a from-scratch load still succeeds under
every new constraint. This runs the loaders against the actual data files in the
test database, which is slower than the rest of the suite and worth it: nothing
else proves the loaders and the constraints agree.
"""

import os
import unittest

from django.core.management import call_command
from django.db import connection
from django.test import TestCase

from api.models import Authorship, Conference, Faculty, Institution, Publication, ResearchArea

DATA_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))),
    'data',
)
REQUIRED_FILES = ['icore_conferences.json', 'faculty.json', 'rankings.json']
HAVE_DATA = all(os.path.exists(os.path.join(DATA_DIR, name)) for name in REQUIRED_FILES)


@unittest.skipUnless(HAVE_DATA, f'pipeline data files not present in {DATA_DIR}')
class FullLoadTests(TestCase):
    """A from-scratch load of the real dataset."""

    @classmethod
    def setUpTestData(cls):
        call_command('load_seed_data', verbosity=0)
        call_command('load_rankings', verbosity=0)

    def test_loaders_populate_every_table(self):
        self.assertGreater(Institution.objects.count(), 0)
        self.assertGreater(Faculty.objects.count(), 0)
        self.assertGreater(Conference.objects.count(), 0)
        self.assertGreater(Publication.objects.count(), 0)
        self.assertGreater(Authorship.objects.count(), 0)

    def test_referential_integrity_holds(self):
        # The check the loaders would previously have had no way to fail.
        connection.check_constraints()

    def test_every_venue_has_a_rank_tier(self):
        self.assertFalse(Conference.objects.filter(core_rank__isnull=True).exists())

    def test_every_venue_area_resolves_to_a_research_area(self):
        codes = set(
            Conference.objects.filter(area__isnull=False).values_list('area', flat=True)
        )
        known = set(ResearchArea.objects.values_list('code', flat=True))
        self.assertEqual(codes - known, set())

    def test_journals_are_typed_as_journals(self):
        mistyped = Conference.objects.filter(
            core_rank_id='Journal',
        ).exclude(venue_type=Conference.VenueType.JOURNAL)
        self.assertEqual(mistyped.count(), 0)

    def test_publications_record_their_author_count(self):
        self.assertFalse(Publication.objects.filter(num_authors__isnull=True).exists())

    def test_doi_column_holds_no_urls(self):
        self.assertFalse(Publication.objects.filter(doi__startswith='http').exists())

    def test_stored_credit_matches_the_author_count(self):
        mismatched = 0
        for credit, num_authors in Authorship.objects.values_list(
            'credit', 'publication__num_authors'
        ).iterator():
            if num_authors and abs(credit - 1.0 / num_authors) > 0.001:
                mismatched += 1
        self.assertEqual(mismatched, 0)

    def test_reload_is_idempotent(self):
        """Loading twice must not duplicate anything — the keys now enforce it."""
        before = (
            Institution.objects.count(),
            Faculty.objects.count(),
            Conference.objects.count(),
            Publication.objects.count(),
            Authorship.objects.count(),
        )
        call_command('load_seed_data', verbosity=0)
        call_command('load_rankings', verbosity=0)
        after = (
            Institution.objects.count(),
            Faculty.objects.count(),
            Conference.objects.count(),
            Publication.objects.count(),
            Authorship.objects.count(),
        )
        self.assertEqual(before, after)
