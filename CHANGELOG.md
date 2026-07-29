# SPARK Update Log

This document systematically tracks the major improvements and architectural changes implemented in the backend and data pipeline.

## Unreleased

### Five non-IIT institutions added to `pipeline/institutions.py` (25 → 30)
Config only — the roster and rankings update on the next pipeline run.

| Code | CSRankings affiliation | Rows | People |
|---|---|---:|---:|
| `TIFR` | `Tata Inst. of Fundamental Research` | 18 | 17 |
| `CMI` | `CMI` | 14 | 11 |
| `ISI` | `ISI Kolkata` | 49 | 45 |
| `BITSP` | `BITS Pilani` | 28 | 24 |
| `BITSG` | `BITS Pilani-Goa` | 46 | 37 |

- **+134 people** over the current 592-person roster. ISI Kolkata (45) would be the 5th-largest tracked department; BITS Goa (37) is larger in the roster than BITS Pilani itself (24).
- **Only two BITS campuses exist in CSRankings.** Hyderabad and Dubai have no rows under any spelling, and no BITS homepage URL in the CSV points at either. Pilani and Goa are cleanly separated — 27 Pilani rows sit under `bits-pilani.ac.in/pilani/`, 27 Goa rows under `/goa/` — so the two rosters don't overlap.
- **The two BITS entries deliberately share broad keywords**, which the substring rule in the module docstring would normally forbid (`bits pilani` nests inside a Goa-campus note). The cost is inverted here: tiering sends anyone *with* a DBLP affiliation note that fails the keyword check to `REVIEW`, not `MEDIUM`, so a campus-specific keyword would push most of both rosters out of the roster and into manual triage. Rosters are selected by exact affiliation string, so the keyword only verifies an already-correct selection.
- `CMI`'s affiliation is the bare acronym. Safe as an affiliation (rows are matched exactly), far too short as a keyword — only the expanded name confirms identity.
- Scoring note recorded next to the research institutes: `geo_mean_score` is a geometric mean over the areas a department publishes in, so a one- or two-area institute is scored on those alone while a broad department is pulled toward its weaker areas. IIT Bhubaneswar already shows the effect — 2 faculty, `total_score` 1.65, `geo_mean_score` **2.51**.

## v1.7.0 — 2026-07-28

### 1. Adding a college no longer re-runs the pipeline for everybody
Every stage is now scoped by institution, so the cost of adding the 26th college is one college's worth of DBLP calls instead of twenty-six.

- **`pipeline/add_institution.sh IITK`** — new one-command path: resolve → integrate → score, all `--institution`-scoped. Refuses before any network traffic if the code isn't in `institutions.py`, and mirrors `refresh.sh`'s exit codes (0 / 2 untriaged / 1 failed) so the same cron alerting works.
- **`resolve_pids.py --institution`** now folds its result into `data/resolved_faculty.json` and the shared `needs_review.*` files instead of only writing per-institution drafts — replacing that institution's blocks and rows, carrying the other 24 over verbatim. Previously the single-institution mode left the combined roster stale, so `integrate_roster.py` had nothing new to merge and only `--all` actually fed the site. An ad-hoc `--affiliation` probe still stays out of the shared files unless `--merge` is passed.
- **`integrate_roster.py --institution`** — scopes the add-only merge into `faculty.json`.
- **`fetch_publications.py --institution`** — fetches only those institutions and splices them into the existing `rankings.json`; untouched institutions are reused byte-for-byte and the list is re-sorted so ranks stay consistent. Verified: a scoped `--institution IITK` run leaves all 24 other blocks byte-identical, and an unscoped run still reproduces the previous `rankings.json` exactly.

### 2. Refresh can now find new publications without discarding the cache
- **`fetch_publications.py --max-age DAYS`** re-fetches only faculty whose cached DBLP data is older than `DAYS`. Cache entries carry a `fetched_at` stamp; entries written before this change have no stamp and are treated as stale, which is the safe direction. Previously the only way to pick up a new paper by an existing faculty member was to delete `dblp_fetch_cache.json` and re-fetch all 592 authors from scratch. `--refresh` is the explicit "ignore the cache entirely" form.
- **`refresh.sh --with-publications [--max-age DAYS]`** (default 30) continues past the roster stage into rescoring, making the overnight job a single command. Bare `refresh.sh` is unchanged — still roster-only, still the cheap cron entry point.

### 3. Two ranking bugs found while making the above verifiable
- **`data_sources` was reported from a leaked loop variable** — the IRINS check inspected whichever institution happened to be processed *last*, so `rankings.json` advertised `["DBLP"]` even though IIIT Delhi's IRINS papers were merged in. Now derived from the per-institution IRINS files actually present.
- **Institutions were sorted before the IRINS merge, not after**, so the stored order didn't reflect final scores: IIIT Delhi (10.69 post-merge) sat below IIIT Hyderabad (10.02). The sort now runs after the merge.
- `rankings.json` is written atomically (tmp + `os.replace`), so an interrupted write can't leave a truncated file, and each institution block carries an `updated_at` stamp showing when it was last scored.

## v1.6.0 — 2026-07-21

### 1. Coverage: every IIT in the CSRankings roster (8 → 25 institutions)
- Added the **17 remaining IITs**: Hyderabad, Guwahati, Jodhpur, Gandhinagar, Bhilai, Ropar, Mandi, Dharwad, (BHU) Varanasi, Tirupati, Roorkee, Patna, Palakkad, Jammu, Indore, Goa and Bhubaneswar.
- **Result**: `faculty.json` 378 → **592 faculty** across 25 institutions (+214). Resolver roster: 578 verified people — 208 HIGH, 370 MEDIUM — with 53 flagged for review.
- **Rankings rebuilt**: 3,325 → **4,892 publications** (2,816 A\*, 2,028 A). Top of the table is unchanged (IIT Bombay, IIT Kharagpur, IIT Delhi, IISc Bangalore); the new institutions enter from #9 (IIT Jodhpur, 8.42) downward.
- Each institution's affiliation string was checked against the CSRankings CSV before the run: a typo silently yields zero faculty, so all 25 were confirmed to match real rows (742 roster rows, up from 478).

### 2. `pipeline/institutions.py` — institutions are now config, not code
- The `INSTITUTIONS` dict moved out of `resolve_pids.py` into its own module, with a header documenting the schema and the two things that silently break a new entry (the `affiliation` string must match CSRankings **verbatim**; the short key names the PID cache and must stay stable).
- `IIT Hyderabad` deliberately carries **no short keyword**: matching is substring-based on punctuation-stripped text, and `iit hyderabad` is a substring of `iiit hyderabad`, which would confirm an IIIT Hyderabad homonym as IIT Hyderabad faculty.

### 3. Pipeline resilience under DBLP throttling
- **`DELAY_SECONDS` 3.0 → 8.0**. At 3s a bulk run (100+ uncached people) slid into a 503 spiral where nearly every call burned the retry ladder, measured at **~60s/person**. Backing off to 8s roughly halved that (~40s/person) and made the retry ladder markedly shallower (depth distribution 21/11/3/1, versus 48/30/12/8 at 3s) — the slower gap finishes a large batch *sooner* than fighting the throttle.
- **`save_cache` now writes after every person**, not once per institution. The per-institution window cost a killed run ~18 already-resolved people; with 25 institutions and DBLP able to stretch one over hours, an interrupted run now loses at most the person in flight.
- **`fetch_publications.py` is now resumable** (`data/dblp_fetch_cache.json`, written atomically after every faculty member). A 592-faculty run is multi-hour and `rankings.json` is only written at the very end, so a failure at hour two previously lost everything. The checkpoint stores the *raw DBLP fetch*, not the scored result — venue matching is cheap and depends on `icore_conferences.json`, so scores are recomputed every run and an ICORE refresh takes effect without re-fetching 592 authors.
- Its `DELAY_SECONDS` moved to 8.0 as well, and the inter-call sleep is now skipped on cache hits so a resumed run replays instantly. Measured effect: **~9.2s/faculty with one rate-limit hit across the whole run**, versus the 40–60s/person the resolver averaged fighting 503s at 3s.

## v1.5.0 — 2026-07-15

### 1. Reproducible Roster Pipeline (replaces the one-off PID script)
- **`pipeline/resolve_pids.py`**: builds an institution's roster from the public **CSRankings CSV** (data only — no CSRankings code) and resolves each person to a DBLP PID. CSRankings names *are* DBLP names (including homonym suffixes like `Amit Kumar 0001`), so resolution scans the DBLP author-search API for an **exact author-string match** rather than guessing — e.g. `Amit Kumar 0001` → `k/AmitKumar1`.
- **Multi-signal verification**: each PID is checked against the DBLP person record (ORCID, homepage, affiliation note, publications since 2015) and tiered **HIGH / MEDIUM / REVIEW**.
- **Alias collapsing**: CSRankings lists spelling variants as separate rows sharing a Scholar id; these are merged into one person before resolution (e.g. 55 IIT Delhi rows → 46 people).
- **Idempotent cache** (`data/{short}_pid_cache.json`): re-runs skip already-resolved faculty and only resolve newly-added ones, so a monthly refresh is cheap.
- **`--all`** writes one combined roster (`data/resolved_faculty.json`) plus one shared needs-review file for every tracked institution.

### 2. Human-in-the-Loop Review (works in production, without an operator present)
- **`data/pid_overrides.csv`** — durable, maintainer-editable source of truth, read *before* the cache and any DBLP call, so manual fixes survive every re-run:
  - `set` — force a PID → person joins the roster as tier **MANUAL**
  - `drop` — exclude a duplicate variant / non-CS entry
  - `ack` — leave unresolved but mute it from the alert
- **`pipeline/refresh.sh`** — monthly entry point (cron). Runs resolve → integrate, tees a timestamped log to `pipeline/logs/`, appends history to `data/review_log.md`, and **exits 2 when untriaged review items exist** (1 = run failed, 0 = all triaged) so cron can alert. Alerts fire only on *untriaged* items, so the standing hard cases don't cry wolf.
- **Review artifacts**: `data/needs_review.md` (self-documenting), `.json`, and `.csv` — the CSV's first five columns match `pid_overrides.csv` so a maintainer can fill in `action` and paste rows straight across.

### 3. New Institutions: IIT Delhi, IIT Kanpur, IIT Kharagpur & IIIT Hyderabad
- SPARK now ranks **8 institutions** (up from 4). Adding one is a single config entry in `INSTITUTIONS` plus a pipeline run — no other code changes.
- **`pipeline/integrate_roster.py`** merges the resolved roster into `data/faculty.json` **add-only**: existing institutions keep their curated entries, roles and `irins_url` links; only genuinely-new faculty are appended (matched by PID, then name/alias). New institutions are added whole. Idempotent, and wired into `refresh.sh` so it is never run by hand.
- **Result**: `faculty.json` 175 → **378 faculty** across 8 institutions (additions only); rankings rebuilt to **3,325 publications / 4,003 authorships**.

### 4. Data Quality
- **IRINS double-counting fix**: `merge_irins_into_faculty` matched names with a strict letters-only normalisation, so a middle initial broke the match and IRINS re-added the *same person* as new — e.g. `Gautam Shroff` alongside `Gautam M. Shroff` (10 overlapping papers), and `V. Raghava Mutharaju` alongside `Raghava Mutharaju` (4 overlapping). Name matching now also compares an **initials-stripped key** (only when ≥2 real tokens remain, so `S. Kumar` / `R. Kumar` never collapse). IRINS papers now merge into the existing person and pass through the existing DOI/title/fuzzy dedup. This corrected IIIT Delhi from an inflated 11.00 (double-counted) / understated 10.59 (papers dropped) to **10.69**, and removed the `Faculty not found` warnings from `load_rankings`.
- **DBLP affiliation noise**: DBLP records `ERNET, India` as the affiliation for many senior Indian faculty (scraped from legacy `*.ernet.in` e-mail domains). It is now treated as *no affiliation* rather than a mismatch, which stopped 5 genuine IISc/IITM faculty being wrongly pushed into review.
- **Affiliation matching** normalises punctuation, so DBLP's `Indian Institute of Technology, Delhi` matches the keyword `indian institute of technology delhi`.
- **DBLP rate-limit resilience**: the search API throttles hard; requests are now spaced 3s apart with exponential backoff and a cooldown after exhausted retries. The cache makes any interrupted run resumable.
- **Cross-check vs the hand-curated roster**: of 157 overlapping faculty, 153 PIDs agreed and only 4 differed — with the resolver more accurate on those (e.g. `faculty.json`'s `J. Lakshmi` PID pointed at an unrelated author).

### ⚠️ Known methodological caveat
IIIT Delhi is currently the **only** institution with IRINS data scraped, so it alone receives journal and IRINS-only conference papers; the other seven are DBLP-conference-only. This advantages IIIT Delhi for reasons unrelated to research output. Closing it requires either scraping IRINS for every institution or excluding IRINS-only papers from scoring. Relatedly, the #6/#7 gap (IIIT Delhi 10.69 vs IIT Kanpur 10.66) is far smaller than the noise in the data and should be read as a tie.

## v1.4.0 — 2026-07-07

### 1. New Institutions: IIT Madras & IISc Bangalore
- **IIT Madras**: Added 41 CSE faculty from CSRankings source data. Auto-resolved 38/41 DBLP PIDs via DBLP search API; 3 faculty remain unresolved (C. Chandra Sekhar, D. Janakiram, Kamakoti Veezhinathan).
- **IISc Bangalore**: Already present in seed data but had severe duplicate entries (75 entries for ~56 unique faculty). Deduplicated by keeping one entry per unique `dblp_pid`, removing 19 duplicate name variants.
- **Result**: SPARK now ranks **4 institutions** (up from 2): IIT Bombay (#1), IISc Bangalore (#2), IIT Madras (#3), IIIT Delhi (#4).

### 2. DBLP PID Auto-Resolution
- Built a DBLP search API integration to automatically resolve faculty names to DBLP author PIDs for institutions where only names are available.
- Uses exact match first, then falls back to word-overlap heuristics for fuzzy matching.
- Successfully resolved 38/41 IIT Madras faculty PIDs from name-only draft data.

### 3. Data Quality
- **IISc deduplication**: Removed 19 duplicate faculty entries that would have caused double-counted publications (e.g., "Chiranjib Bhattacharyya" / "Chiru Bhattacharyya", 3× Matthew Thazhuthaveetil variants, 4× Venkatesh Babu variants).
- **Pipeline re-run**: Full DBLP fetch for all 187 faculty across 4 institutions. Generated 1,765 publications and 1,947 authorships.

## v1.3.0 — 2026-06-22

### 1. Geometric Mean Institution Scoring
- **Scoring Overhaul**: Transitioned institution scoring from a simple sum to a geometric mean of per-area scores. This rewards institutional breadth—universities strong across multiple computer science subfields now rank higher than those dominant in only one.
- **Area Grouping**: Publications are dynamically grouped by their respective ICORE FoR (Field of Research) areas before computing the weighted score per area.
- **API Updates**: Updated `/api/rankings/`, `/api/institutions/{id}/`, and `/api/faculty/` to compute and display ranks based on the new geometric mean calculation.

### 2. Bulletproof Workshop & Adjunct Filtering
- **IRINS Merger Fix**: Addressed a critical data leak where workshop papers discarded by the DBLP pipeline were being incorrectly re-added by the IRINS scraper.
- **Title Heuristics**: Added strict regex checks for 'workshop', 'adjunct', and other non-research proceeding indicators directly against DBLP `booktitle` and IRINS `venue_full`.
- **Result**: Successfully pruned 49 false-positive workshop/short papers (like *PerCom Workshops*) from the backend database across all faculty profiles.

## v1.2.0 — 2026-06-17

### 1. API Overhaul — Frontend Spec Compliance
- **Replaced DRF Router** with 10 explicit `APIView`-based endpoints matching the frontend specification exactly.
- **New endpoints added**:
  - `GET /api/stats/` — aggregate institution/faculty/publication counts
  - `GET /api/areas/` — all FoR research area codes with human-readable names
  - `GET /api/institutions/{id}/` — institution profile with area breakdown and top faculty
  - `GET /api/institutions/{id}/trends/` — year-over-year score timeline for Chart.js
  - `GET /api/institutions/?search=` — typeahead institution search
  - `GET /api/faculty/{id}/` — full faculty profile with publications, authorships, A\*/A score split
  - `GET /api/faculty/?search=&area=&start_year=&end_year=` — faculty leaderboard with filtering
- **Refactored existing endpoints** (`/api/rankings/`, `/api/publications/`, `/api/conferences/`) to return exact response schemas the frontend expects.
- **Browsable API root** at `/api/` lists all available endpoints.

### 2. Serializer Rewrite
- Replaced generic `ModelSerializer` with purpose-built serializers for each endpoint.
- Added nested serializers (`InstitutionMiniSerializer`, `ConferenceMiniSerializer`, `FacultyMiniSerializer`) for consistent embedded objects.
- Faculty profile now includes `a_star_score`, `a_score`, `dblp_url`, `areas`, and both `publications` and `authorships` arrays.
- Fixed frontend compatibility by restoring all missing detailed fields (`department`, `authorships`, `designation`, `orcid`, `dblp_pid`, `irins_id`, `homepage`) to the `GET /api/faculty/` leaderboard endpoint without breaking its new filtering/scoring capabilities.

### 3. Data Pipeline Robustness & Workshop Filtering
- **Workshop Filtering**: Added a rigorous <= 5 page cap heuristic to `fetch_dblp.py` to automatically identify and exclude short abstracts, posters, and workshop papers from all rankings and scores. Added `is_workshop` and `page_count` fields to the `Publication` model.
- **DBLP Rate-Limit Bypass**: Implemented a new `load_rankings` management command that instantly repopulates the database from the pre-computed `data/rankings.json` file. This safely bypasses DBLP API blocks and avoids hours of throttling.
- **Duplicate Prevention**: Removed redundant publication arrays from the API payload to prevent duplicate-looking entries on the frontend.

### 4. Branding
- Renamed project from CAPS to **SPARK** (Scholarly Publication & Academic Ranking Knowledgebase) across all files.

## v1.1.0 — 2026-06-14

### 1. Journal Matching Expansion
- **New journals**: Added IMWUT, TNSM, TCCN, and Computer Communications to the curated journal list (`ieee_acm_journals.json`).
- **Name variant fixes**: Fixed IEEE/ACM → IEEE ACM slash mismatch for TON and TCBB, which caused IRINS venue text to fail matching.
- **Result**: Arani Bhattacharya's journal count went from 3 → 9 (matching IRINS's displayed count).

### 2. Three-Layer Cross-Source Deduplication
- **DOI matching**: Extract and normalize DOIs from both DBLP (`url` field) and IRINS (`doi` field) for exact-match dedup (~89% coverage).
- **Exact title matching**: Existing normalized title comparison (strip non-alphanumeric, lowercase).
- **Fuzzy title matching**: Word-set Jaccard similarity (≥0.80) plus substring containment check for same-year papers. Catches DBLP suffixes like "(Student Abstract)" and minor title differences across sources.
- **Result**: 173 cross-source duplicates caught; 0 remaining duplicates across all faculty.

### 3. Within-IRINS Deduplication
- Added DOI-based dedup in `fetch_all_publications()` to prevent IRINS from returning duplicate entries across paginated API responses.

### 4. Frontend Journal Support
- Added journal paper counts, timeline bars, and venue badges to the faculty detail page.
- Added IRINS profile links alongside DBLP links.
- Updated methodology page to document journal and IRINS data sources.

## v1.0.0 - 2026-06-10

### 1. IRINS Data Collection & Deduplication
- **Data Scraping**: Built `scrape_irins.py` to systematically crawl the IIITD IRINS portal and extract structured faculty profiles and publication lists.
- **Name Normalization**: Improved the pipeline's name-matching logic to resolve formatting inconsistencies (e.g., merging "Md. Shad Akhtar" from DBLP and "Md Shad Akhtar" from IRINS into a single entity).
- **Faculty Expansion**: Successfully identified and integrated 12 new Computer Science/CSE faculty members exclusively found in the IRINS database.
- **Title Deduplication**: Implemented robust string normalization and fuzzy matching to prevent duplicate publication entries between DBLP and IRINS datasets.

### 2. Django REST API Restructure
- **Framework Migration**: Transitioned the backend from isolated Python scripts to a fully relational Django project backed by a SQLite database.
- **Relational Modeling**: Designed robust database models (`Institution`, `Department`, `Faculty`, `Conference`, `Publication`, `Authorship`) to store hierarchical data efficiently.
- **Data Loaders**: Developed custom Django management commands (`load_seed_data`, `fetch_dblp`, `load_irins`) for reproducible database seeding.
- **Data Recovery**: Fixed a discrepancy between DBLP `venue_key` and conference `acronym` by explicitly mapping `dblp_key`, successfully recovering 44 previously missing DBLP publications.

### 3. Frontend API Integration
- **Dynamic Rankings Endpoint**: Implemented `GET /api/rankings/` to compute fractional authorship scores on the fly.
  - Added support for frontend query filters: `area`, `start_year`, `end_year`, and `top_n`.
  - Implemented dynamic CORE rank weighting (A* = 4, A = 2, Journal/Other = 1).
- **Faculty Endpoints**: Added a pre-calculated, properly rounded `score` field to the `GET /api/faculty/` response, utilizing Django's `Coalesce` and `Sum` annotations. This ensures every faculty member receives a 0.0 baseline or properly aggregated score.
- **Raw Data Endpoints**: Registered robust fallback REST endpoints (`/api/institutions/`, `/api/faculty/`, `/api/publications/`, `/api/authorships/`) perfectly adhering to the frontend team's JSON schema requirements.
- **Query Optimization**: Implemented `prefetch_related` on the publications endpoint to serve the embedded `authors` array efficiently without triggering N+1 database queries.
- **Configuration**: Set up CORS headers and generated a clean `requirements.txt` environment file for seamless frontend-backend development.
