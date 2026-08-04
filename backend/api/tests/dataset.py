"""A small, deterministic dataset that exercises every branch the API has.

Hand-built rather than dumped from the real database so that it survives schema
changes: when a migration moves a column, this builder is updated alongside the
models and the golden responses in golden/ stay frozen. That is the whole point
— the goldens are the contract, this file is just the input that produces them.

Coverage that matters:
  * all three core ranks (A*, A, Journal) so every scoring weight is hit
  * a venue with no area, so the 'other' bucket in the geometric mean is used
  * a workshop paper, which every endpoint must exclude
  * a paper co-authored across two institutions, so credit splitting is visible
  * a faculty member with no publications, one with no department, one with no
    dblp_pid, and blank vs populated designation
"""

from api.models import (
    Authorship,
    Conference,
    Department,
    Faculty,
    Institution,
    Publication,
)


def build():
    """Create the dataset. Returns a dict of the objects tests need by name."""
    alpha = Institution.objects.create(
        name='Alpha Institute of Technology',
        state='Karnataka',
        city='Bengaluru',
        website='https://alpha.example.edu',
    )
    beta = Institution.objects.create(
        name='Beta Institute of Science',
        state='Maharashtra',
        city='Mumbai',
        website='https://beta.example.edu',
    )
    gamma = Institution.objects.create(
        name='Gamma University',
        state='Delhi',
        city='New Delhi',
        website='https://gamma.example.edu',
    )

    alpha_cse = Department.objects.create(institution=alpha, name='Computer Science and Engineering')

    # Venues: two A* in different areas, two A, one journal with no area.
    conf_ai = Conference.objects.create(
        acronym='AICONF', full_name='Conference on Artificial Intelligence',
        dblp_key='aiconf', core_rank_id='A*', area_id='4602',
    )
    conf_ml = Conference.objects.create(
        acronym='MLCONF', full_name='Conference on Machine Learning',
        dblp_key='mlconf', core_rank_id='A*', area_id='4611',
    )
    conf_se = Conference.objects.create(
        acronym='SECONF', full_name='Conference on Software Engineering',
        dblp_key='seconf', core_rank_id='A', area_id='4612',
    )
    conf_th = Conference.objects.create(
        acronym='THCONF', full_name='Conference on Theory of Computation',
        dblp_key='thconf', core_rank_id='A', area_id='4613',
    )
    journal = Conference.objects.create(
        acronym='TJOUR', full_name='Transactions on Computing',
        core_rank_id='Journal',
    )

    # Faculty: varied optional fields, including one with no department anywhere
    # and one with no publications at all.
    ada = Faculty.objects.create(
        institution=alpha, department=alpha_cse, name='Ada Researcher',
        designation='Professor', dblp_pid='111/1111',
        homepage='https://alpha.example.edu/~ada',
    )
    bob = Faculty.objects.create(
        institution=alpha, name='Bob Scientist',
        designation='', dblp_pid='222/2222', homepage='',
    )
    cleo = Faculty.objects.create(
        institution=beta, name='Cleo Engineer',
        designation='Associate Professor', dblp_pid='333/3333',
        homepage='https://beta.example.edu/~cleo',
    )
    dev = Faculty.objects.create(
        institution=beta, name='Dev Theorist',
        designation='Assistant Professor', dblp_pid='444/4444', homepage='',
    )
    eve = Faculty.objects.create(
        institution=gamma, name='Eve Analyst',
        designation='Professor', dblp_pid='', homepage='',
    )
    frank = Faculty.objects.create(
        institution=gamma, name='Frank Nopubs',
        designation='Lecturer', dblp_pid='555/5555', homepage='',
    )

    def pub(title, year, conference, authors, num_authors, is_workshop=False, page_count=12):
        slug = title.lower().replace(' ', '-')
        publication = Publication.objects.create(
            title=title, year=year, conference=conference,
            doi=f'10.1000/{slug}', ee_url=f'https://doi.org/10.1000/{slug}',
            num_authors=num_authors, page_count=page_count, is_workshop=is_workshop,
        )
        for faculty in authors:
            Authorship.objects.create(
                faculty=faculty, publication=publication,
                credit=round(1.0 / num_authors, 4),
            )
        return publication

    # Single-author A* papers.
    pub('Attention Over Graphs', 2020, conf_ai, [ada], 1)
    pub('Neural Program Repair', 2021, conf_ml, [ada], 2)
    # Cross-institution co-authorship: credit splits, both institutions score.
    pub('Federated Optimisation At Scale', 2022, conf_ai, [ada, cleo], 4)
    pub('Contrastive Pretraining Revisited', 2023, conf_ml, [bob, cleo], 3)
    # A-ranked papers.
    pub('Refactoring Legacy Monoliths', 2019, conf_se, [bob], 2)
    pub('Type Inference For Dynamic Languages', 2024, conf_se, [cleo], 1)
    pub('Lower Bounds For Streaming', 2018, conf_th, [dev], 1)
    pub('Approximation Schemes For Packing', 2022, conf_th, [dev, eve], 2)
    # Journal paper: contributes at weight 1.0 and lands in the 'other' area.
    pub('A Survey Of Everything', 2021, journal, [eve], 1)
    # Workshop paper: must be excluded from every score and listing.
    pub('Workshop Position Paper', 2023, conf_ai, [ada], 1, is_workshop=True, page_count=4)

    return {
        'institutions': {'alpha': alpha, 'beta': beta, 'gamma': gamma},
        'faculty': {
            'ada': ada, 'bob': bob, 'cleo': cleo,
            'dev': dev, 'eve': eve, 'frank': frank,
        },
        'conferences': {
            'ai': conf_ai, 'ml': conf_ml, 'se': conf_se,
            'th': conf_th, 'journal': journal,
        },
        'department': alpha_cse,
    }
