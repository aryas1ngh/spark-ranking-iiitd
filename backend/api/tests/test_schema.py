"""Tests that the schema itself enforces what the loaders used to enforce.

Every constraint here replaces a rule that previously lived only in application
code, so each test is really asking: if a loader gets it wrong, does the
database still stop it?
"""

from django.db import IntegrityError, connection, transaction
from django.test import TestCase

from api.ingest import get_rank_tier, get_research_area, split_ee_url
from api.models import (
    Authorship,
    Conference,
    Department,
    Faculty,
    Institution,
    Publication,
    RankTier,
    ResearchArea,
)

from . import dataset


class ReferenceDataTests(TestCase):
    """The reference tables are populated by migration, not by a fixture."""

    def test_rank_tiers_seeded_with_weights(self):
        self.assertEqual(RankTier.objects.get(code='A*').weight, 4.0)
        self.assertEqual(RankTier.objects.get(code='A').weight, 2.0)
        self.assertEqual(RankTier.objects.get(code='Journal').weight, 1.0)

    def test_research_areas_seeded(self):
        area = ResearchArea.objects.get(code='4602')
        self.assertEqual(area.name, 'Artificial Intelligence')
        self.assertEqual(area.slug, 'artificial_intelligence')

    def test_area_slug_matches_the_expression_it_replaced(self):
        # The frontend keys off these identifiers, so the derivation has to stay
        # exactly as it was when it lived in views.py.
        self.assertEqual(
            ResearchArea.objects.get(code='4603').slug, 'computer_vision_and_multimedia'
        )

    def test_unknown_rank_is_created_on_demand_at_weight_one(self):
        tier = get_rank_tier('Unknown')
        self.assertEqual(tier.weight, 1.0)

    def test_blank_area_code_maps_to_no_row(self):
        self.assertIsNone(get_research_area(''))
        self.assertIsNone(get_research_area(None))

    def test_unnamed_area_code_is_named_after_itself(self):
        area = get_research_area('9999')
        self.assertEqual(area.name, '9999')


class CandidateKeyTests(TestCase):
    """Each of these de-duplication rules used to live in a get_or_create call."""

    @classmethod
    def setUpTestData(cls):
        cls.objects = dataset.build()
        cls.alpha = cls.objects['institutions']['alpha']
        cls.beta = cls.objects['institutions']['beta']
        cls.conf_ai = cls.objects['conferences']['ai']
        cls.ada = cls.objects['faculty']['ada']

    def assertRejected(self, callable_):
        with self.assertRaises(IntegrityError), transaction.atomic():
            callable_()

    def test_institution_name_is_unique(self):
        self.assertRejected(
            lambda: Institution.objects.create(name='Alpha Institute of Technology')
        )

    def test_department_name_is_unique_within_an_institution(self):
        self.assertRejected(
            lambda: Department.objects.create(
                institution=self.alpha, name='Computer Science and Engineering'
            )
        )

    def test_same_department_name_allowed_at_another_institution(self):
        Department.objects.create(
            institution=self.beta, name='Computer Science and Engineering'
        )

    def test_faculty_name_is_unique_within_an_institution(self):
        self.assertRejected(
            lambda: Faculty.objects.create(institution=self.alpha, name='Ada Researcher')
        )

    def test_dblp_pid_is_globally_unique(self):
        self.assertRejected(
            lambda: Faculty.objects.create(
                institution=self.beta, name='Impostor', dblp_pid='111/1111'
            )
        )

    def test_many_faculty_may_have_no_dblp_pid(self):
        # The partial constraint must not collapse unresolved roster entries.
        Faculty.objects.create(institution=self.beta, name='Unresolved One', dblp_pid='')
        Faculty.objects.create(institution=self.beta, name='Unresolved Two', dblp_pid='')

    def test_conference_acronym_is_unique(self):
        self.assertRejected(
            lambda: Conference.objects.create(
                acronym='AICONF', full_name='Impostor', core_rank_id='A',
            )
        )

    def test_conference_dblp_key_is_unique_when_set(self):
        self.assertRejected(
            lambda: Conference.objects.create(
                acronym='OTHER', full_name='Other', dblp_key='aiconf', core_rank_id='A',
            )
        )

    def test_many_conferences_may_have_no_dblp_key(self):
        Conference.objects.create(acronym='NOKEY1', full_name='One', core_rank_id='A')
        Conference.objects.create(acronym='NOKEY2', full_name='Two', core_rank_id='A')

    def test_publication_title_year_venue_is_unique(self):
        self.assertRejected(
            lambda: Publication.objects.create(
                title='Attention Over Graphs', year=2020, conference=self.conf_ai,
            )
        )

    def test_same_title_allowed_in_a_different_year(self):
        Publication.objects.create(
            title='Attention Over Graphs', year=2021, conference=self.conf_ai,
        )

    def test_publication_dblp_key_is_unique_when_set(self):
        Publication.objects.create(
            title='Keyed One', year=2020, conference=self.conf_ai, dblp_key='conf/x/1',
        )
        self.assertRejected(
            lambda: Publication.objects.create(
                title='Keyed Two', year=2020, conference=self.conf_ai, dblp_key='conf/x/1',
            )
        )

    def test_many_publications_may_have_no_dblp_key(self):
        # This is the case the original `unique=True` could not express: every
        # row in the live database has an empty key.
        Publication.objects.create(title='Unkeyed One', year=2020, conference=self.conf_ai)
        Publication.objects.create(title='Unkeyed Two', year=2020, conference=self.conf_ai)

    def test_an_author_appears_on_a_paper_once(self):
        publication = Publication.objects.get(title='Attention Over Graphs')
        self.assertRejected(
            lambda: Authorship.objects.create(
                faculty=self.ada, publication=publication, credit=1.0,
            )
        )


class DomainConstraintTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.objects = dataset.build()
        cls.conf_ai = cls.objects['conferences']['ai']
        cls.ada = cls.objects['faculty']['ada']

    def assertRejected(self, callable_):
        with self.assertRaises(IntegrityError), transaction.atomic():
            callable_()

    def test_year_must_be_plausible(self):
        self.assertRejected(
            lambda: Publication.objects.create(
                title='Time Traveller', year=1300, conference=self.conf_ai,
            )
        )

    def test_page_count_must_be_positive(self):
        self.assertRejected(
            lambda: Publication.objects.create(
                title='Zero Pages', year=2020, conference=self.conf_ai, page_count=0,
            )
        )

    def test_author_count_must_be_positive(self):
        self.assertRejected(
            lambda: Publication.objects.create(
                title='No Authors', year=2020, conference=self.conf_ai, num_authors=0,
            )
        )

    def test_doi_column_rejects_a_url(self):
        # The column held 672 non-DOI URLs before the split; this is what stops
        # that from happening again.
        self.assertRejected(
            lambda: Publication.objects.create(
                title='Url In Doi', year=2020, conference=self.conf_ai,
                doi='https://aclanthology.org/2026.findings-acl.1632/',
            )
        )

    def test_credit_must_be_a_fraction(self):
        publication = Publication.objects.create(
            title='Overcredited', year=2020, conference=self.conf_ai,
        )
        self.assertRejected(
            lambda: Authorship.objects.create(
                faculty=self.ada, publication=publication, credit=1.5,
            )
        )

    def test_venue_rank_must_reference_a_known_tier(self):
        # SQLite defers foreign-key enforcement to the end of the transaction,
        # so the check has to be asked for explicitly rather than waiting for a
        # commit that a test never makes.
        with self.assertRaises(IntegrityError), transaction.atomic():
            Conference.objects.create(
                acronym='BOGUS', full_name='Bogus', core_rank_id='NotARank',
            )
            connection.check_constraints()

    def test_venue_area_must_reference_a_known_area(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Conference.objects.create(
                acronym='BOGUS2', full_name='Bogus', core_rank_id='A', area_id='9999',
            )
            connection.check_constraints()


class DerivedValueTests(TestCase):
    """Authorship.credit is a stored copy of 1/Publication.num_authors.

    Keeping it stored is a deliberate denormalisation — recomputing it exactly
    would move published scores, because the pipeline rounds to four places —
    so its consistency has to be asserted rather than assumed.
    """

    @classmethod
    def setUpTestData(cls):
        dataset.build()

    def test_credit_matches_the_author_count_on_the_publication(self):
        mismatches = []
        for authorship in Authorship.objects.select_related('publication'):
            expected = 1.0 / authorship.publication.num_authors
            if abs(authorship.credit - expected) > 0.001:
                mismatches.append(
                    (authorship.publication.title, authorship.credit, expected)
                )
        self.assertEqual(mismatches, [])

    def test_every_author_of_a_paper_carries_the_same_credit(self):
        for publication in Publication.objects.all():
            credits = set(publication.authorships.values_list('credit', flat=True))
            self.assertLessEqual(
                len(credits), 1,
                f'{publication.title} has authors with differing credit: {credits}',
            )


class EeUrlSplitTests(TestCase):
    def test_doi_org_url_yields_both_halves(self):
        self.assertEqual(
            split_ee_url('https://doi.org/10.1145/3576915'),
            ('10.1145/3576915', 'https://doi.org/10.1145/3576915'),
        )

    def test_dx_doi_org_is_recognised_too(self):
        doi, url = split_ee_url('http://dx.doi.org/10.1109/ABC.2020.1')
        self.assertEqual(doi, '10.1109/ABC.2020.1')

    def test_non_doi_url_is_not_a_doi(self):
        self.assertEqual(
            split_ee_url('https://aclanthology.org/2026.findings-acl.1632/'),
            ('', 'https://aclanthology.org/2026.findings-acl.1632/'),
        )

    def test_bare_doi_gains_a_resolver_link(self):
        self.assertEqual(
            split_ee_url('10.1145/3576915'),
            ('10.1145/3576915', 'https://doi.org/10.1145/3576915'),
        )

    def test_empty_input(self):
        self.assertEqual(split_ee_url(''), ('', ''))
        self.assertEqual(split_ee_url(None), ('', ''))


class NullabilityTests(TestCase):
    """Optional text columns have exactly one empty value, and it is not NULL."""

    OPTIONAL_TEXT = [
        (Institution, ['state', 'city', 'website']),
        (Faculty, ['designation', 'orcid', 'dblp_pid', 'irins_id', 'homepage']),
        (Conference, ['dblp_key']),
        (Publication, ['doi', 'ee_url', 'dblp_key']),
    ]

    def test_optional_text_columns_are_not_nullable(self):
        for model, field_names in self.OPTIONAL_TEXT:
            for field_name in field_names:
                field = model._meta.get_field(field_name)
                self.assertFalse(
                    field.null,
                    f'{model.__name__}.{field_name} is nullable; it should default to ""',
                )
                self.assertEqual(field.default, '')

    def test_foreign_keys_are_still_nullable_where_optional(self):
        # NULL keeps its meaning for relations: no department, no research area.
        self.assertTrue(Faculty._meta.get_field('department').null)
        self.assertTrue(Conference._meta.get_field('area').null)
