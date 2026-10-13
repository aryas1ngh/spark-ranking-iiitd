"""Query-count regression tests for the faculty endpoints.

/api/faculty/ used to issue two extra queries per authorship (an N+1 on
publication → conference) and /api/faculty/{id}/ one per authorship (on
conference → core_rank) — ~15,700 queries per leaderboard request against the
real data. These tests pin the fix by asserting the query count does not grow
with the number of publications, which is the property that matters, rather
than an exact count that any harmless refactor would break.
"""

import io

from django.core.cache import cache
from django.core.management import call_command
from django.db import connection
from django.test import TestCase, override_settings
from django.test.utils import CaptureQueriesContext

from api.models import Authorship, Conference, Publication
from . import dataset

# These tests fill the cache from a mutated dataset (extra publications), so
# they get a private in-memory cache. On the shared file cache in settings the
# inflated scores would outlive the test transaction and leak into the next
# run's golden tests, which read the cache without clearing it.
ISOLATED_CACHE = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


@override_settings(SECURE_SSL_REDIRECT=False, CACHES=ISOLATED_CACHE)
class FacultyQueryCountTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.objects = dataset.build()
        cls.alpha = cls.objects['institutions']['alpha']
        cls.ada = cls.objects['faculty']['ada']
        cls.bob = cls.objects['faculty']['bob']

    def setUp(self):
        cache.clear()

    def _count_queries(self, url):
        cache.clear()
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        return len(ctx.captured_queries)

    def _add_publications(self, n=10):
        """Give ada and bob n more papers each, spread across venues."""
        venues = list(Conference.objects.order_by('id'))
        for i in range(n):
            pub = Publication.objects.create(
                title=f'Extra paper {i}', year=2022,
                conference=venues[i % len(venues)], num_authors=2,
            )
            Authorship.objects.create(faculty=self.ada, publication=pub, credit=0.5)
            Authorship.objects.create(faculty=self.bob, publication=pub, credit=0.5)

    def assertQueriesDoNotScale(self, url_fn, max_queries):
        before = self._count_queries(url_fn())
        self._add_publications()
        after = self._count_queries(url_fn())
        self.assertEqual(
            before, after,
            f'{url_fn()} issued {before} queries, then {after} after adding '
            f'publications — the query count must not grow with the data.',
        )
        self.assertLessEqual(after, max_queries, url_fn())

    def test_faculty_leaderboard_query_count_is_constant(self):
        self.assertQueriesDoNotScale(lambda: '/api/faculty/', max_queries=3)

    def test_faculty_leaderboard_filtered_query_count_is_constant(self):
        self.assertQueriesDoNotScale(
            lambda: f'/api/faculty/?institution={self.alpha.id}&rank=A*&search=a',
            max_queries=3,
        )

    def test_faculty_detail_query_count_is_constant(self):
        self.assertQueriesDoNotScale(lambda: f'/api/faculty/{self.ada.id}/', max_queries=2)

    def test_compare_faculty_query_count_is_constant(self):
        # One query per compared faculty is expected; one per paper is not.
        self.assertQueriesDoNotScale(
            lambda: f'/api/compare/?faculty={self.ada.id},{self.bob.id}', max_queries=3,
        )


@override_settings(SECURE_SSL_REDIRECT=False, CACHES=ISOLATED_CACHE)
class FacultyLeaderboardCacheTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.objects = dataset.build()

    def setUp(self):
        cache.clear()

    def _queries_for(self, url):
        with CaptureQueriesContext(connection) as ctx:
            response = self.client.get(url)
        self.assertEqual(response.status_code, 200, url)
        return response, len(ctx.captured_queries)

    def test_repeat_request_is_served_from_cache(self):
        first, _ = self._queries_for('/api/faculty/?rank=A*')
        second, n = self._queries_for('/api/faculty/?rank=A*')
        self.assertEqual(n, 0)
        self.assertEqual(first.content, second.content)
        self.assertEqual(second['Cache-Control'], 'no-store')

    def test_cache_key_ignores_unknown_and_reordered_params(self):
        # Junk params must not mint their own cache entries (cache flooding),
        # and the same filters in a different order are the same request.
        self._queries_for('/api/faculty/?start_year=2020&rank=A')
        _, n = self._queries_for('/api/faculty/?rank=A&junk=1&start_year=2020')
        self.assertEqual(n, 0)

    def test_search_requests_are_not_cached(self):
        self._queries_for('/api/faculty/?search=ada')
        _, n = self._queries_for('/api/faculty/?search=ada')
        self.assertGreater(n, 0)

    def test_clear_rankings_cache_evicts_leaderboard(self):
        self._queries_for('/api/faculty/')
        call_command('clear_rankings_cache', stdout=io.StringIO())
        _, n = self._queries_for('/api/faculty/')
        self.assertGreater(n, 0)
