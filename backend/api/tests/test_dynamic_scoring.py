"""Tests for dynamic area-filtered scoring and CORE rank filtering."""

import json
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, override_settings

from api.models import Conference, ResearchArea
from api.views import (
    CACHE_KEY_ALL_GEO,
    CACHE_KEY_AREA_GEO_PREFIX,
    _compute_all_institution_geo_means,
    _compute_area_institution_geo_means,
)
from . import dataset


@override_settings(SECURE_SSL_REDIRECT=False)
class DynamicScoringTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.objects = dataset.build()
        cls.alpha = cls.objects['institutions']['alpha']
        cls.beta = cls.objects['institutions']['beta']
        cls.gamma = cls.objects['institutions']['gamma']
        cls.ada = cls.objects['faculty']['ada']
        cls.bob = cls.objects['faculty']['bob']

    def setUp(self):
        cache.clear()

    def test_rank_filter_a_star(self):
        """Rankings with ?rank=A* must only include A* conference authorships."""
        response = self.client.get('/api/rankings/?rank=A*')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertIn('results', data)
        # Gamma only has Journal publication, so Gamma score must not appear or be zero/excluded
        gamma_results = [r for r in data['results'] if r['institution']['id'] == self.gamma.id]
        self.assertEqual(len(gamma_results), 0)

    def test_rank_filter_faculty_a_star(self):
        """Faculty leaderboard with ?rank=A* only counts A* points."""
        response = self.client.get('/api/faculty/?rank=A*')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        # Eve only has Journal publication in dataset, so score with A* filter must be 0.0
        eve_data = next((f for f in data if f['id'] == self.objects['faculty']['eve'].id), None)
        self.assertIsNotNone(eve_data)
        self.assertEqual(eve_data['score'], 0.0)

    def test_rank_filter_invalid_value(self):
        """Invalid rank values must return 400 Bad Request with a clear message."""
        response_rankings = self.client.get('/api/rankings/?rank=invalid_rank')
        self.assertEqual(response_rankings.status_code, 400)
        data_rankings = json.loads(response_rankings.content)
        self.assertIn('rank', data_rankings)

        response_faculty = self.client.get('/api/faculty/?rank=XYZ')
        self.assertEqual(response_faculty.status_code, 400)
        data_faculty = json.loads(response_faculty.content)
        self.assertIn('rank', data_faculty)

    def test_rank_filter_all_value(self):
        """?rank=all must behave identically to omitting the rank parameter."""
        resp_unfiltered = self.client.get('/api/rankings/')
        resp_all = self.client.get('/api/rankings/?rank=all')
        self.assertEqual(resp_unfiltered.status_code, 200)
        self.assertEqual(resp_all.status_code, 200)
        self.assertEqual(json.loads(resp_unfiltered.content), json.loads(resp_all.content))

    def test_faculty_list_single_area_institution_rank(self):
        """Single-area filter in FacultyListView should use area-specific institution ranks."""
        response = self.client.get('/api/faculty/?area=4602')
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)

        # In dataset, only Alpha has pubs in area 4602 (AICONF)
        # Alpha should be ranked #1 in institution_rank for area 4602
        ada_item = next((f for f in data if f['id'] == self.ada.id), None)
        self.assertIsNotNone(ada_item)
        self.assertEqual(ada_item['institution_rank'], 1)

    def test_precompute_area_scores_helper(self):
        """_compute_area_institution_geo_means should compute and cache area scores."""
        cache_key = CACHE_KEY_AREA_GEO_PREFIX + '4602'
        self.assertIsNone(cache.get(cache_key))

        scores = _compute_area_institution_geo_means('4602')
        self.assertIn(self.alpha.id, scores)
        self.assertGreater(scores[self.alpha.id], 0.0)

        # Cache should now be warm
        cached_scores = cache.get(cache_key)
        self.assertEqual(cached_scores, scores)

    def test_precompute_area_scores_command(self):
        """Management command precompute_area_scores should warm cache for all active areas."""
        call_command('precompute_area_scores')

        active_areas = (
            Conference.objects.filter(area__isnull=False)
            .values_list('area', flat=True)
            .distinct()
        )
        for code in active_areas:
            cache_key = CACHE_KEY_AREA_GEO_PREFIX + code
            self.assertIsNotNone(cache.get(cache_key), f"Cache key {cache_key} was not populated")

    def test_clear_rankings_cache_command(self):
        """clear_rankings_cache command should clear all cached rankings and geo means."""
        # Precompute and warm caches
        _compute_all_institution_geo_means()
        call_command('precompute_area_scores')
        self.client.get('/api/rankings/')

        # Verify caches are populated
        self.assertIsNotNone(cache.get(CACHE_KEY_ALL_GEO))
        self.assertIsNotNone(cache.get(CACHE_KEY_AREA_GEO_PREFIX + '4602'))

        # Clear caches
        call_command('clear_rankings_cache')
        self.assertIsNone(cache.get(CACHE_KEY_ALL_GEO))
        self.assertIsNone(cache.get(CACHE_KEY_AREA_GEO_PREFIX + '4602'))

    def test_faculty_detail_filters_by_rank(self):
        """Faculty detail page should recompute scores and publications based on ?rank filter."""
        # Unfiltered Ada
        resp_all = self.client.get(f'/api/faculty/{self.ada.id}/')
        self.assertEqual(resp_all.status_code, 200)
        data_all = json.loads(resp_all.content)

        # Filtered to Journal only (Ada only has conference papers in dataset)
        resp_j = self.client.get(f'/api/faculty/{self.ada.id}/?rank=Journal')
        self.assertEqual(resp_j.status_code, 200)
        data_j = json.loads(resp_j.content)
        self.assertEqual(data_j['score'], 0.0)
        self.assertEqual(len(data_j['authorships']), 0)

        # Eve has a Journal publication in dataset
        eve = self.objects['faculty']['eve']
        resp_eve_j = self.client.get(f'/api/faculty/{eve.id}/?rank=Journal')
        self.assertEqual(resp_eve_j.status_code, 200)
        data_eve_j = json.loads(resp_eve_j.content)
        self.assertGreater(data_eve_j['score'], 0.0)
        self.assertEqual(len(data_eve_j['authorships']), 1)

    def test_faculty_detail_filters_by_year_and_area(self):
        """Faculty detail page should filter by start_year, end_year, and area."""
        # Filter by impossible year range
        resp_past = self.client.get(f'/api/faculty/{self.ada.id}/?start_year=1990&end_year=1995')
        self.assertEqual(resp_past.status_code, 200)
        data_past = json.loads(resp_past.content)
        self.assertEqual(data_past['score'], 0.0)
        self.assertEqual(len(data_past['authorships']), 0)

        # Filter by area where Ada has publications (4602) vs area where Ada has none (4612)
        resp_ai = self.client.get(f'/api/faculty/{self.ada.id}/?area=4602')
        self.assertEqual(resp_ai.status_code, 200)
        data_ai = json.loads(resp_ai.content)
        self.assertGreater(data_ai['score'], 0.0)

        resp_se = self.client.get(f'/api/faculty/{self.ada.id}/?area=4612')
        self.assertEqual(resp_se.status_code, 200)
        data_se = json.loads(resp_se.content)
        self.assertEqual(data_se['score'], 0.0)
        self.assertEqual(len(data_se['authorships']), 0)

    def test_faculty_list_filter_by_institution(self):
        """Faculty leaderboard with ?institution=<id> should only return faculty from that institution."""
        resp = self.client.get(f'/api/faculty/?institution={self.alpha.id}')
        self.assertEqual(resp.status_code, 200)
        data = json.loads(resp.content)
        for f in data:
            self.assertEqual(f['institution']['id'], self.alpha.id)
