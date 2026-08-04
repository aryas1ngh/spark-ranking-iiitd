"""Helpers shared by the data loaders.

The loaders all need the same three things now that venues point at reference
tables: a RankTier for a rank code, a ResearchArea for a FoR code, and a way to
tell a DOI from the electronic-edition URL it was mixed in with.
"""

from .reference_data import FOR_DESCRIPTIONS, RANK_WEIGHTS, area_slug

DOI_URL_PREFIXES = (
    'https://doi.org/',
    'http://doi.org/',
    'https://dx.doi.org/',
    'http://dx.doi.org/',
)


def get_rank_tier(code):
    """Return the RankTier for a rank code, creating it if the code is new.

    Unknown codes get weight 1.0, which is what the old hardcoded scoring
    expression fell back to for anything that was not A* or A.
    """
    from .models import RankTier

    tier, _ = RankTier.objects.get_or_create(
        code=code, defaults={'weight': RANK_WEIGHTS.get(code, 1.0)},
    )
    return tier


def get_research_area(code):
    """Return the ResearchArea for a FoR code, or None when there is no code.

    Journals carry no area, and None — not '' — is how a missing foreign key is
    spelled. A code with no published name is named after itself, matching what
    the API used to do when the code was missing from its lookup dict.
    """
    from .models import ResearchArea

    code = (code or '').strip()
    if not code:
        return None

    name = FOR_DESCRIPTIONS.get(code, code)
    area, _ = ResearchArea.objects.get_or_create(
        code=code, defaults={'name': name, 'slug': area_slug(name)},
    )
    return area


def venue_type_for(rank_code):
    """Whether a venue with this rank code is a journal or a conference."""
    from .models import Conference

    if rank_code == 'Journal':
        return Conference.VenueType.JOURNAL
    return Conference.VenueType.CONFERENCE


def split_ee_url(value):
    """Split DBLP's electronic-edition value into (doi, ee_url).

    DBLP's <ee> element is a DOI URL for some venues and a publisher or
    anthology link for others, which is why the `doi` column used to hold both.
    """
    value = (value or '').strip()
    if not value:
        return '', ''

    for prefix in DOI_URL_PREFIXES:
        if value.startswith(prefix):
            return value[len(prefix):], value

    if value.startswith('http'):
        return '', value

    # Already a bare DOI: record the link it resolves through as well.
    return value, f'https://doi.org/{value}'
