from django.db import models
from django.db.models import Q


class Institution(models.Model):
    # `name` is the key every loader already de-duplicates on
    # (Institution.objects.get_or_create(name=...)), so it is a candidate key in
    # practice. Declaring it here moves that guarantee out of application code
    # and into the schema. `id` stays the primary key because it is part of the
    # public API — it appears in responses and in /api/institutions/{id}/ URLs.
    name = models.CharField(max_length=255, unique=True)
    # Optional text columns are NOT NULL with an empty-string default rather
    # than nullable. A nullable CharField has two ways to say "no value" ('' and
    # NULL) and the loaders wrote both, so queries had to test for both. NULL is
    # reserved here for foreign keys, where it genuinely means "no related row".
    state = models.CharField(max_length=100, blank=True, default='')
    city = models.CharField(max_length=100, blank=True, default='')
    website = models.URLField(blank=True, default='')

    def __str__(self):
        return self.name


class Department(models.Model):
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name='departments')
    name = models.CharField(max_length=255)

    class Meta:
        constraints = [
            # A department name is only unique within its institution — every
            # institution has a "Computer Science and Engineering".
            models.UniqueConstraint(
                fields=['institution', 'name'],
                name='department_unique_name_per_institution',
            ),
        ]

    def __str__(self):
        return f"{self.name} - {self.institution.name}"


class Faculty(models.Model):
    institution = models.ForeignKey(Institution, on_delete=models.CASCADE, related_name='faculty')
    department = models.ForeignKey(Department, on_delete=models.SET_NULL, null=True, blank=True, related_name='faculty')
    name = models.CharField(max_length=255)
    designation = models.CharField(max_length=255, blank=True, default='')
    orcid = models.CharField(max_length=100, blank=True, default='')
    dblp_pid = models.CharField(max_length=100, blank=True, default='')
    irins_id = models.CharField(max_length=100, blank=True, default='')
    homepage = models.URLField(blank=True, default='')

    class Meta:
        constraints = [
            # The roster loaders key on (institution, name); this is the natural
            # key for a faculty row.
            models.UniqueConstraint(
                fields=['institution', 'name'],
                name='faculty_unique_name_per_institution',
            ),
            # A DBLP PID identifies one person globally, so it must not be
            # claimed twice. Partial, because an unresolved roster entry has no
            # PID yet and any number of those may coexist.
            models.UniqueConstraint(
                fields=['dblp_pid'],
                condition=~Q(dblp_pid=''),
                name='faculty_unique_dblp_pid_when_set',
            ),
        ]

    def __str__(self):
        return self.name


class ResearchArea(models.Model):
    """An ANZSRC Field of Research code, e.g. 4602 → Artificial Intelligence.

    This mapping used to be a dict in views.py, which meant the database could
    hold an area code the application had no name for, and the list of valid
    codes was not enforceable. The code is the primary key: it is stable,
    externally defined, and already stored in the conference rows, so making it
    the key means the foreign key column holds the code itself and no join is
    needed to serialise it.
    """

    code = models.CharField(max_length=8, primary_key=True)
    name = models.CharField(max_length=100)
    # The identifier the API exposes as `id`, derived from the name.
    slug = models.SlugField(max_length=100, unique=True)

    class Meta:
        ordering = ['code']

    def __str__(self):
        return f"{self.code} — {self.name}"


class RankTier(models.Model):
    """A CORE rank and the score weight it carries.

    The weights were repeated as literals in five separate Case/When blocks in
    views.py. A weighting scheme is data — moving it here means it can be
    changed without a code deploy, and the scoring queries read it by join.
    """

    code = models.CharField(max_length=10, primary_key=True)  # A*, A, Journal
    weight = models.FloatField()

    class Meta:
        ordering = ['code']

    def __str__(self):
        return self.code


class Conference(models.Model):
    class VenueType(models.TextChoices):
        CONFERENCE = 'conference', 'Conference'
        JOURNAL = 'journal', 'Journal'

    acronym = models.CharField(max_length=50, unique=True)
    full_name = models.CharField(max_length=500)
    dblp_key = models.CharField(max_length=100, blank=True, default='')
    # `core_rank` conflated two things: how highly a venue is ranked, and
    # whether it is a conference at all ('Journal' is not a rank). venue_type
    # carries the second meaning so the rank column can be just a rank.
    venue_type = models.CharField(
        max_length=20, choices=VenueType.choices, default=VenueType.CONFERENCE,
    )
    core_rank = models.ForeignKey(
        RankTier, on_delete=models.PROTECT, related_name='conferences',
        db_column='core_rank',
    )
    # Nullable rather than blank: journals genuinely have no area, and NULL is
    # how a foreign key spells "no related row".
    area = models.ForeignKey(
        ResearchArea, on_delete=models.PROTECT, null=True, blank=True,
        related_name='conferences', db_column='area',
    )

    class Meta:
        constraints = [
            # Venues are matched to DBLP records by this key, so a duplicate
            # would silently split one venue's publications across two rows.
            models.UniqueConstraint(
                fields=['dblp_key'],
                condition=~Q(dblp_key=''),
                name='conference_unique_dblp_key_when_set',
            ),
        ]
        indexes = [
            # Both columns are filtered and grouped on by every scoring query.
            models.Index(fields=['area'], name='conference_area_idx'),
            models.Index(fields=['core_rank'], name='conference_core_rank_idx'),
        ]

    def __str__(self):
        return self.acronym


class Publication(models.Model):
    title = models.TextField()
    year = models.IntegerField()
    conference = models.ForeignKey(Conference, on_delete=models.CASCADE, related_name='publications')
    # A bare DOI ('10.1145/3576915'), never a URL. The column previously held
    # whichever electronic-edition link DBLP happened to publish, so two thirds
    # of the rows were aclanthology/ACM URLs sitting in a column named `doi`.
    doi = models.CharField(max_length=255, blank=True, default='')
    ee_url = models.URLField(
        max_length=500, blank=True, default='',
        help_text="Electronic edition link as published by DBLP",
    )
    # Not `unique=True`: that constraint was satisfied vacuously while every row
    # held NULL. As an empty string it needs the partial constraint below, which
    # enforces uniqueness only over rows that actually carry a key.
    dblp_key = models.CharField(max_length=255, blank=True, default='')
    # The author count belongs to the publication, not to each authorship of it.
    # Authorship.credit is 1/num_authors, identical for every author of a paper,
    # so storing it per authorship made credit transitively dependent on the
    # publication rather than on the (faculty, publication) key. Recording the
    # count here is what makes that dependency explicit and checkable.
    num_authors = models.PositiveSmallIntegerField(
        null=True, blank=True,
        help_text="Total authors on the paper, including those outside the roster",
    )
    page_count = models.IntegerField(null=True, blank=True, help_text="Number of pages in the publication")
    is_workshop = models.BooleanField(
        default=False,
        help_text="Classified as a workshop/adjunct paper rather than a main-track one",
    )

    class Meta:
        constraints = [
            # `dblp_key` is the global identifier but is not populated on every
            # row yet, so it cannot be relied on for de-duplication. This is the
            # key load_rankings actually de-duplicates on, and until every row
            # carries a DBLP key it is what stops the same paper being inserted
            # twice when two co-authors are ingested in turn.
            models.UniqueConstraint(
                fields=['title', 'year', 'conference'],
                name='publication_unique_title_year_venue',
            ),
            models.UniqueConstraint(
                fields=['dblp_key'],
                condition=~Q(dblp_key=''),
                name='publication_unique_dblp_key_when_set',
            ),
            models.CheckConstraint(
                condition=Q(year__gte=1900) & Q(year__lte=2100),
                name='publication_year_range',
            ),
            models.CheckConstraint(
                condition=Q(page_count__isnull=True) | Q(page_count__gt=0),
                name='publication_page_count_positive',
            ),
            models.CheckConstraint(
                condition=Q(num_authors__isnull=True) | Q(num_authors__gte=1),
                name='publication_num_authors_positive',
            ),
            models.CheckConstraint(
                condition=~Q(doi__startswith='http'),
                name='publication_doi_is_not_a_url',
            ),
        ]
        indexes = [
            models.Index(fields=['year'], name='publication_year_idx'),
            # Every scoring query filters is_workshop=False first, then narrows
            # by year.
            models.Index(fields=['is_workshop', 'year'], name='publication_workshop_year_idx'),
        ]

    def __str__(self):
        return self.title


class Authorship(models.Model):
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE, related_name='authorships')
    publication = models.ForeignKey(Publication, on_delete=models.CASCADE, related_name='authorships')
    # Stored rather than derived from Publication.num_authors on read. It is a
    # cached copy of 1/num_authors, written only by the ingestion loaders and
    # verified by the integrity tests, because the values already in the
    # database are rounded to 4 decimal places by the pipeline and recomputing
    # them exactly would shift every published score in the third decimal.
    credit = models.FloatField(default=1.0) # Adjusted count (e.g., 1 / num_authors)

    class Meta:
        constraints = [
            # (faculty, publication) is the candidate key: a person authors a
            # given paper once. `id` remains the primary key because authorship
            # ids are exposed by /api/faculty/ and /api/faculty/{id}/.
            models.UniqueConstraint(
                fields=['faculty', 'publication'],
                name='authorship_unique_faculty_publication',
            ),
            models.CheckConstraint(
                condition=Q(credit__gt=0) & Q(credit__lte=1),
                name='authorship_credit_is_a_fraction',
            ),
        ]

    def __str__(self):
        return f"{self.faculty.name} - {self.publication.title[:30]}"
