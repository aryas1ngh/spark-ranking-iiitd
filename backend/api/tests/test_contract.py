"""Golden-response contract tests for every public endpoint.

These lock the JSON the frontend consumes. Each request's full response body is
compared byte-for-byte (after a canonical json.dumps) against a file in golden/.
A schema refactor is allowed to change models, queries and serializer internals
freely; it is not allowed to change these files.

Regenerating is deliberate and rare:

    UPDATE_GOLDEN=1 python manage.py test api.tests.test_contract

Only do that when the API is *intentionally* changing, and review the diff — a
regenerated golden is a changed contract, which means a frontend change too.
"""

import json
import os

from django.test import TestCase, override_settings

from . import dataset

GOLDEN_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'golden')
UPDATE = os.environ.get('UPDATE_GOLDEN') == '1'


def canonical(payload):
    return json.dumps(payload, indent=2, sort_keys=True) + '\n'


# SECURE_SSL_REDIRECT defaults to True (see settings.py), which would turn every
# request below into a 301 to https://testserver and make each golden file a
# record of the redirect rather than of the API. These tests assert on response
# bodies, so they opt out of the redirect rather than speak TLS to a test client
# that has no TLS. The setting itself is still exercised by test_ssl_redirect.
@override_settings(SECURE_SSL_REDIRECT=False)
class ContractTestCase(TestCase):
    """Base class providing the dataset and the golden-comparison helper."""

    @classmethod
    def setUpTestData(cls):
        cls.objects = dataset.build()
        cls.alpha = cls.objects['institutions']['alpha']
        cls.beta = cls.objects['institutions']['beta']
        cls.gamma = cls.objects['institutions']['gamma']
        cls.ada = cls.objects['faculty']['ada']
        cls.bob = cls.objects['faculty']['bob']
        cls.cleo = cls.objects['faculty']['cleo']
        cls.eve = cls.objects['faculty']['eve']
        cls.frank = cls.objects['faculty']['frank']

    def assertMatchesGolden(self, name, url):
        """GET url and compare status + body against golden/<name>.json."""
        response = self.client.get(url)
        try:
            body = json.loads(response.content)
        except ValueError:
            body = {'_non_json_body': response.content.decode('utf-8', 'replace')}

        actual = canonical({'url': url, 'status': response.status_code, 'body': body})
        path = os.path.join(GOLDEN_DIR, name + '.json')

        if UPDATE:
            with open(path, 'w') as fh:
                fh.write(actual)
            return

        self.assertTrue(
            os.path.exists(path),
            f'Missing golden file {path}. Run with UPDATE_GOLDEN=1 to create it.',
        )
        with open(path) as fh:
            expected = fh.read()

        self.assertEqual(
            expected, actual,
            f'\nResponse for {url} no longer matches {name}.json.\n'
            'If this change is intentional the frontend must change too.',
        )


class RootAndReferenceTests(ContractTestCase):
    def test_api_root(self):
        self.assertMatchesGolden('api_root', '/api/')

    def test_stats(self):
        self.assertMatchesGolden('stats', '/api/stats/')

    def test_areas(self):
        self.assertMatchesGolden('areas', '/api/areas/')

    def test_conferences(self):
        self.assertMatchesGolden('conferences', '/api/conferences/')


class RankingsTests(ContractTestCase):
    def test_rankings_unfiltered(self):
        self.assertMatchesGolden('rankings', '/api/rankings/')

    def test_rankings_by_area(self):
        self.assertMatchesGolden('rankings_area_4602', '/api/rankings/?area=4602')

    def test_rankings_by_multiple_areas(self):
        self.assertMatchesGolden('rankings_area_multi', '/api/rankings/?area=4602,4611')

    def test_rankings_by_start_year(self):
        self.assertMatchesGolden('rankings_start_2021', '/api/rankings/?start_year=2021')

    def test_rankings_by_year_window(self):
        self.assertMatchesGolden(
            'rankings_window', '/api/rankings/?start_year=2019&end_year=2022'
        )

    def test_rankings_year_and_area(self):
        self.assertMatchesGolden(
            'rankings_window_area', '/api/rankings/?start_year=2018&end_year=2024&area=4613'
        )


class InstitutionTests(ContractTestCase):
    def test_institution_list(self):
        self.assertMatchesGolden('institutions', '/api/institutions/')

    def test_institution_search_hit(self):
        self.assertMatchesGolden('institutions_search', '/api/institutions/?search=institute')

    def test_institution_search_miss(self):
        self.assertMatchesGolden('institutions_search_miss', '/api/institutions/?search=zzz')

    def test_institution_detail(self):
        self.assertMatchesGolden('institution_detail_alpha', f'/api/institutions/{self.alpha.id}/')

    def test_institution_detail_journal_only_area(self):
        # Gamma's only scoring venue is the journal, which has no area — this
        # pins the 'other' bucket behaviour in the geometric mean.
        self.assertMatchesGolden('institution_detail_gamma', f'/api/institutions/{self.gamma.id}/')

    def test_institution_trends(self):
        self.assertMatchesGolden(
            'institution_trends_alpha', f'/api/institutions/{self.alpha.id}/trends/'
        )

    def test_institution_missing(self):
        self.assertMatchesGolden('institution_404', '/api/institutions/999999/')


class PublicationTests(ContractTestCase):
    def test_publications(self):
        self.assertMatchesGolden('publications', '/api/publications/')

    def test_publications_by_institution(self):
        self.assertMatchesGolden(
            'publications_alpha', f'/api/publications/?institution={self.alpha.id}'
        )


class FacultyTests(ContractTestCase):
    def test_faculty_leaderboard(self):
        self.assertMatchesGolden('faculty_list', '/api/faculty/')

    def test_faculty_search(self):
        self.assertMatchesGolden('faculty_search', '/api/faculty/?search=e')

    def test_faculty_filtered(self):
        self.assertMatchesGolden(
            'faculty_filtered', '/api/faculty/?start_year=2021&area=4602'
        )

    def test_faculty_detail(self):
        self.assertMatchesGolden('faculty_detail_ada', f'/api/faculty/{self.ada.id}/')

    def test_faculty_detail_no_publications(self):
        self.assertMatchesGolden('faculty_detail_frank', f'/api/faculty/{self.frank.id}/')

    def test_faculty_detail_no_dblp_pid(self):
        self.assertMatchesGolden('faculty_detail_eve', f'/api/faculty/{self.eve.id}/')

    def test_faculty_missing(self):
        self.assertMatchesGolden('faculty_404', '/api/faculty/999999/')


class MalformedInputTests(ContractTestCase):
    """Malformed query params must stay 400s, never 500s (see _parse_int_param)."""

    def test_non_numeric_year(self):
        self.assertMatchesGolden('bad_start_year', '/api/rankings/?start_year=abc')

    def test_out_of_range_year(self):
        self.assertMatchesGolden('bad_year_range', '/api/rankings/?start_year=1500')

    def test_float_year(self):
        self.assertMatchesGolden('bad_float_year', '/api/rankings/?end_year=2015.5')

    def test_non_numeric_institution(self):
        self.assertMatchesGolden('bad_institution', '/api/publications/?institution=notanint')

    def test_zero_institution(self):
        self.assertMatchesGolden('bad_institution_zero', '/api/publications/?institution=0')

    def test_empty_params_ignored(self):
        self.assertMatchesGolden('empty_params', '/api/rankings/?start_year=&end_year=&area=')


class TransportSecurityTests(TestCase):
    """The HTTPS hardening is env-gated, so pin both sides of the gate.

    Every other test in this file runs with the redirect suppressed; without
    these two, a regression that silently dropped SECURE_SSL_REDIRECT would go
    unnoticed until a scanner caught it.
    """

    @override_settings(SECURE_SSL_REDIRECT=True)
    def test_plain_http_is_redirected_when_enabled(self):
        response = self.client.get('/api/stats/')
        self.assertEqual(response.status_code, 301)
        self.assertTrue(response['Location'].startswith('https://'))

    @override_settings(SECURE_SSL_REDIRECT=False)
    def test_plain_http_is_served_when_disabled(self):
        """DJANGO_HTTPS=False is what keeps the HTTP-only LAN deployment usable."""
        self.assertEqual(self.client.get('/api/stats/').status_code, 200)
