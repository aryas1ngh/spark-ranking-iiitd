# ICSRank Update Log

This document systematically tracks the major improvements and architectural changes implemented in the backend and data pipeline.

## v1.1.0 - 2026-06-14

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
