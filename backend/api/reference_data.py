"""Canonical seed values for the reference tables.

ResearchArea and RankTier describe things defined outside this project (ANZSRC
Field of Research codes and the CORE ranking scheme), so their contents are
fixed vocabulary rather than user data. Keeping them here lets the loaders
top up the tables when new venues introduce a code, while migration 0005 holds
its own inlined copy — a migration must not import application code, because
this module will keep changing and old migrations have to keep replaying.
"""

# ANZSRC Field of Research code → human-readable name.
FOR_DESCRIPTIONS = {
    '4601': 'Applied Computing',
    '4602': 'Artificial Intelligence',
    '4603': 'Computer Vision & Multimedia',
    '4604': 'Cybersecurity and Privacy',
    '4605': 'Data Management and Data Science',
    '4606': 'Distributed Computing',
    '4607': 'Graphics, Augmented Reality and Games',
    '4608': 'Human-Centred Computing',
    '4609': 'Information Systems',
    '4610': 'Library and Information Studies',
    '4611': 'Machine Learning',
    '4612': 'Software Engineering',
    '4613': 'Theory of Computation',
}

# CORE rank → score weight. 'Journal' is not a CORE rank; it is how this
# project has always labelled non-conference venues, and Conference.venue_type
# now carries that distinction properly.
RANK_WEIGHTS = {
    'A*': 4.0,
    'A': 2.0,
    'Journal': 1.0,
}


def area_slug(name):
    """Derive the public `id` the /api/areas/ endpoint exposes for an area.

    Kept verbatim from the expression that used to live in views.py so the
    identifiers the frontend receives do not change.
    """
    return name.lower().replace(' ', '_').replace('&', 'and').replace(',', '')
