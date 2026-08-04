# Database schema

SQLite, managed by the Django ORM (`backend/api/models.py`). Eight tables: three for the
roster, three for the research record, two for controlled vocabulary.

Current contents: 30 institutions, 719 faculty, 228 venues, 4,458 publications, 5,457 authorships.

## Relationships

```
institution ──< department ──┐
     │                       │
     └──< faculty <──────────┘        (department optional)
              │
              └──< authorship >── publication ──> conference ──> ranktier
                                                       └───────> researcharea  (optional)
```

Arrows point from the table holding the foreign key to the table it references.
`authorship` is the junction table for the many-to-many between faculty and publications.

## Tables

### institution

| Column | Type | Notes |
|---|---|---|
| id | integer | primary key |
| name | varchar(255) | unique |
| state, city | varchar(100) | |
| website | varchar(200) | |

### department

| Column | Type | Notes |
|---|---|---|
| id | integer | primary key |
| name | varchar(255) | |
| institution_id | FK → institution | |

Unique: `(institution_id, name)`

### faculty

| Column | Type | Notes |
|---|---|---|
| id | integer | primary key |
| name | varchar(255) | |
| designation | varchar(255) | |
| dblp_pid | varchar(100) | DBLP author id |
| orcid, irins_id | varchar(100) | |
| homepage | varchar(200) | |
| institution_id | FK → institution | |
| department_id | FK → department | nullable |

Unique: `(institution_id, name)`; `dblp_pid` where it is not empty

### conference

Venues — ICORE-ranked conferences and tracked journals.

| Column | Type | Notes |
|---|---|---|
| id | integer | primary key |
| acronym | varchar(50) | unique |
| full_name | varchar(500) | |
| dblp_key | varchar(100) | unique where not empty |
| venue_type | varchar(20) | `conference` or `journal` |
| core_rank | FK → ranktier.code | |
| area | FK → researcharea.code | nullable |

### publication

| Column | Type | Notes |
|---|---|---|
| id | integer | primary key |
| title | text | |
| year | integer | |
| conference_id | FK → conference | |
| num_authors | smallint | total authors on the paper |
| doi | varchar(255) | bare DOI |
| ee_url | varchar(500) | electronic edition link |
| dblp_key | varchar(255) | unique where not empty |
| page_count | integer | nullable |
| is_workshop | bool | excluded from scoring |

Unique: `(title, year, conference_id)`

### authorship

| Column | Type | Notes |
|---|---|---|
| id | integer | primary key |
| faculty_id | FK → faculty | |
| publication_id | FK → publication | |
| credit | real | 1 / num_authors |

Unique: `(faculty_id, publication_id)`

### ranktier

| Column | Type | Notes |
|---|---|---|
| code | varchar(10) | primary key — `A*`, `A`, `Journal` |
| weight | real | 4.0, 2.0, 1.0 |

### researcharea

ANZSRC Field of Research codes.

| Column | Type | Notes |
|---|---|---|
| code | varchar(8) | primary key — e.g. `4602` |
| name | varchar(100) | e.g. Artificial Intelligence |
| slug | varchar(100) | unique; the `id` used by `/api/areas/` |

## Keys

Every table except the two vocabulary tables uses a numeric `id` as its primary key. The
`id` is stable and appears in the public API URLs, so it cannot change. What identifies a
row in the real world is declared separately as a unique constraint:

| Table | Natural key |
|---|---|
| institution | name |
| department | (institution, name) |
| faculty | (institution, name), and dblp_pid |
| conference | acronym, and dblp_key |
| publication | (title, year, conference), and dblp_key |
| authorship | (faculty, publication) |

`ranktier` and `researcharea` use their codes as primary keys directly — the codes come
from outside the project and are already stable.

`dblp_pid` and both `dblp_key` columns use partial unique indexes, so uniqueness applies
only to rows that carry a value. Rows without one are unrestricted.

## Constraints

| Constraint | Rule |
|---|---|
| publication_year_range | 1900 ≤ year ≤ 2100 |
| publication_page_count_positive | page_count > 0 when set |
| publication_num_authors_positive | num_authors ≥ 1 when set |
| publication_doi_is_not_a_url | doi does not start with `http` |
| authorship_credit_is_a_fraction | 0 < credit ≤ 1 |

Optional text columns are `NOT NULL` with a default of `''`, so a missing value has one
representation. NULL is used only for optional foreign keys — `faculty.department_id` and
`conference.area` — where it means there is no related row.

## Indexes

Beyond the primary keys, foreign keys and unique constraints:

- `publication (year)`
- `publication (is_workshop, year)`
- `conference (area)`
- `conference (core_rank)`

## Scoring

Scores are computed by query, not stored:

```
faculty score = Σ ( authorship.credit × ranktier.weight )
```

Each authorship carries a fractional credit — one paper split evenly among its authors.
Following `authorship → publication → conference → ranktier` gives the weight for that
paper. Workshop papers (`is_workshop`) are excluded.

An institution's score is the geometric mean of its per-area totals, grouped by the venue's
`researcharea`.

## Migrations

| Migration | Contents |
|---|---|
| 0001–0002 | initial tables; page_count and is_workshop |
| 0003 | unique constraints, check constraints, indexes |
| 0004 | optional text columns to `NOT NULL DEFAULT ''` |
| 0005 | `ranktier` and `researcharea`; `venue_type` |
| 0006 | `num_authors`; `doi` / `ee_url` split |

All are reversible. `backend/api/tests/` covers the API responses, the constraints, and a
full rebuild from the pipeline JSON.
