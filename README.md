<p align="center">
  <img src="https://img.shields.io/badge/ICORE-2026-f5a623?style=for-the-badge&labelColor=0c1021" alt="ICORE 2026" />
  <img src="https://img.shields.io/badge/Django-REST_API-092E20?style=for-the-badge&logo=django" alt="Django" />
  <img src="https://img.shields.io/badge/data%20source-DBLP_&_IRINS-34d399?style=for-the-badge&labelColor=0c1021" alt="DBLP & IRINS" />
  <img src="https://img.shields.io/badge/license-MIT-a78bfa?style=for-the-badge&labelColor=0c1021" alt="MIT License" />
</p>

<h1 align="center">🎓 SPARK</h1>
<h3 align="center">Scholarly Publication & Academic Ranking Knowledgebase</h3>

<p align="center">
  Rank CS departments using <strong>all</strong> ICORE A*/A conferences; not just the hand-picked CSRankings subset.
  <br />
  Transparent, data-driven, DBLP & IRINS-sourced. No CSRankings code used.
</p>

---

## Why SPARK?

[CSRankings](https://csrankings.org) is a great initiative, but it only considers **~45 hand-picked conferences** across all of CS. That means departments strong in areas with conferences *not* on that list get systematically undervalued.

[ICORE](http://portal.core.edu.au/conf-ranks/) (formerly CORE) is an international peer-reviewed conference ranking system that evaluates **every major CS conference** — currently rating 825+ venues across all subfields.

**SPARK bridges the gap:**

|                   | CSRankings        | SPARK                              |
| ----------------- | ----------------- | ---------------------------------- |
| Conference source | ~45 hand-picked   | **170 ICORE A\*/A**          |
| A\* conferences   | ~30               | **62**                       |
| Coverage          | Select areas only | **All CS subfields**         |
| Methodology       | Geometric mean    | Adjusted count + Geometric Mean    |
| Data source       | DBLP              | **DBLP + IRINS**                   |
| Faculty roster    | Curated CSV       | **Same CSV, PIDs re-verified against DBLP** |
| Transparency      | Open source       | Open source + open data            |

> **On CSRankings:** SPARK uses CSRankings' public affiliation CSV purely as a **faculty roster** — i.e. which professors belong to which CS department. None of its code, and none of its ~45-venue list, is used. Every DBLP identity is independently re-resolved and verified, and all scoring is computed from ICORE A\*/A venues.

> **Currently tracking 25 institutions** — every IIT present in the CSRankings roster, plus IISc Bangalore, IIIT Delhi and IIIT Hyderabad — 592 faculty, 4,892 publications. Adding another is a single config entry in `pipeline/institutions.py` plus a pipeline run (see [Adding an institution](#adding-an-institution)).

---

## Quick Start

### Prerequisites

- **Node.js** ≥ 18
- **Python** ≥ 3.10
- Internet connection (for scraping ICORE, IRINS, and querying DBLP)

### 1. Install Dependencies

```bash
git clone https://github.com/aryas1ngh/spark-ranking-iiitd.git && cd spark-ranking-iiitd

# Frontend
npm install

# Backend
python3 -m venv backend_venv
source backend_venv/bin/activate
pip install -r backend/requirements.txt
```

### 2. Run the Data Pipeline

The backend is built on Django. You need to migrate the database and run the data pipeline loaders to populate it.

```bash
source backend_venv/bin/activate
cd backend

# Step 1: Migrate database
python manage.py migrate

# Step 2: Load Seed Data (Institutions, Departments, Conferences)
python manage.py load_seed_data

# Step 3: Fast-load Pre-Scraped Publications
# This safely bypasses DBLP API rate limits by loading the pre-merged JSON data
python manage.py load_rankings

# (Optional) If you want to slowly fetch fresh data instead:
# python manage.py load_irins
# python manage.py fetch_dblp
```

### 3. Launch the Development Servers

**Run the Backend API:**
```bash
# In backend directory, with virtual environment activated:
python manage.py runserver
# → API runs at http://localhost:8000/api/
```

**Run the Frontend App:**
```bash
# In root directory:
npm run dev
# → Open http://localhost:5173
```

### 4. Production Configuration

The three security-critical settings read from the environment, with defaults chosen so a bare deploy (`git pull` on the server) boots safely with **`DEBUG` off** and no extra config:

| Env var | Default | Notes |
| --- | --- | --- |
| `DJANGO_DEBUG` | `False` | Set to `True` only for local development. |
| `DJANGO_ALLOWED_HOSTS` | `192.168.3.173,localhost,127.0.0.1` | Comma-separated. |
| `DJANGO_SECRET_KEY` | historical committed key | **Rotate in production** — set a freshly generated key; the fallback is already public in git history. |

Query parameters are validated before use: `start_year`, `end_year` (range 1900–2100) and `institution` must parse as integers, and malformed input returns a clean **HTTP 400** instead of a 500.

---

## Architecture

SPARK uses a **Django REST Framework** backend that handles the heavy lifting of dynamic scoring, and a separate client-side frontend.

```
spark/
├── backend/                     # Django REST Backend
│   ├── api/                     # DRF Models, Views, Serializers
│   │   ├── reference_data.py    # FoR code names, CORE rank weights
│   │   ├── ingest.py            # shared loader helpers
│   │   ├── tests/               # golden API contract + schema integrity tests
│   │   │   └── golden/          # frozen responses — changing one is a contract change
│   │   └── management/commands/ # DB loaders
│   │       ├── load_seed_data.py    # faculty.json + conferences → DB
│   │       ├── load_rankings.py     # rankings.json → DB (fast path)
│   │       ├── load_irins.py
│   │       └── fetch_dblp.py
│   ├── backend/                 # Project Settings, URLs
│   ├── tools/api_snapshot.py    # capture every API response for before/after diffing
│   ├── db.sqlite3               # Auto-generated SQLite Database (gitignored)
│   └── requirements.txt         # Python dependencies
│
├── pipeline/                    # Data pipeline (run offline)
│   ├── refresh.sh               # ★ monthly entry point (resolve → integrate)
│   ├── add_institution.sh       # ★ add ONE college, skipping the rest
│   ├── institutions.py          # ★ tracked institutions (the config to edit)
│   ├── resolve_pids.py          # CSRankings roster → verified DBLP PIDs
│   ├── integrate_roster.py      # resolved roster → faculty.json (add-only)
│   ├── fetch_publications.py    # faculty.json → rankings.json
│   ├── scrape_icore.py          # ICORE A*/A conference list
│   └── scrape_irins.py          # IRINS faculty + publications
│
├── data/
│   ├── faculty.json             # ★ the roster (site source of truth)
│   ├── rankings.json            # ★ computed publications/scores → DB
│   ├── icore_conferences.json   # tracked A*/A venues
│   ├── pid_overrides.csv        # ★ maintainer's manual PID decisions
│   ├── resolved_faculty.json    # resolver output (all institutions)
│   └── needs_review.{md,csv,json}  # items needing a human
│
├── src/                         # Local demo frontend (the production
│   ├── main.js                  # frontend lives in a separate repo and
│   └── index.css                # consumes this backend's REST API)
```

---

## API Endpoints

The backend serves 10 RESTful endpoints. All return JSON and are CORS-enabled. Visit `/api/` for a browsable index.

| # | Endpoint | Description |
|---|---|---|
| 1 | `GET /api/stats/` | Aggregate counts (institutions, faculty, publications) |
| 2 | `GET /api/areas/` | All FoR research areas with codes |
| 3 | `GET /api/rankings/` | Institution rankings with filters |
| 4 | `GET /api/institutions/{id}/` | Institution profile with area breakdown |
| 5 | `GET /api/institutions/{id}/trends/` | Year-over-year score timeline |
| 6 | `GET /api/publications/` | Publications list, filterable by institution |
| 7 | `GET /api/institutions/?search=` | Institution typeahead search |
| 8 | `GET /api/faculty/{id}/` | Faculty profile with all publications |
| 8b | `GET /api/faculty/?search=` | Faculty leaderboard with search & filters |
| 9 | `GET /api/conferences/` | All tracked ICORE A\*/A conferences |

### Filter Parameters (Endpoints 3, 8b)

| Param | Type | Example | Description |
|---|---|---|---|
| `start_year` | int | `2020` | Include publications from this year onwards |
| `end_year` | int | `2026` | Include publications up to this year |
| `area` | string | `4602,4611` | Comma-separated FoR codes |
| `search` | string | `Arani` | Faculty name filter (endpoint 8b only) |

---

## Scoring Methodology

SPARK uses **adjusted counts**, calculating scores on the fly directly in the database.

1. **For each paper** published at an ICORE A\*/A conference, base credit is distributed by: `1.0 / number_of_coauthors`
2. **Conference Weighting**: The fractional credit is then multiplied by the venue's tier, read from the `RankTier` table rather than hardcoded:
   - **A\*** = 4.0 multiplier
   - **A** = 2.0 multiplier
   - **Default** = 1.0 multiplier
3. **Faculty Score**: Sum of weighted credits across all matched papers.
4. **Institution Score**: Calculated using a **Geometric Mean** of its per-area scores. Publications are grouped by their Field of Research (FoR), weighted scores are summed for each area, and the geometric mean across all areas determines the institution's final ranking. This effectively rewards research breadth and volume.

---

## Data Pipeline

```
CSRankings CSV ─→ resolve_pids.py ─→ resolved_faculty.json ─→ integrate_roster.py ─→ faculty.json
                        │                                                                  │
                        └─→ needs_review.{md,csv,json} ──→ maintainer ──→ pid_overrides.csv│
                                                                                           ▼
                                              DB ←── load_rankings ←── rankings.json ←── fetch_publications.py
```

1. **Roster resolution** (`resolve_pids.py`): builds each institution's faculty list from the public **CSRankings CSV** (data only — no CSRankings code) and resolves every person to a DBLP PID. CSRankings names *are* DBLP names (including homonym suffixes like `Amit Kumar 0001`), so it takes the **exact author-string match** from DBLP's search API rather than guessing. Each PID is then verified against the DBLP person record (ORCID, homepage, affiliation, recent publications) and tiered **HIGH / MEDIUM / REVIEW**. An idempotent cache means re-runs only resolve *new* faculty.
2. **Roster integration** (`integrate_roster.py`): merges verified faculty into `faculty.json` **add-only** — existing curated entries, roles and IRINS links are never overwritten.
3. **DBLP Fetcher** (`fetch_publications.py`): retrieves publication XML per faculty PID and matches venues via `dblp_key` (not fuzzy strings), producing `rankings.json`.
4. **IRINS Scraper**: parses the institutional research information system for faculty and publications, merged with three-layer dedup (DOI → exact title → fuzzy title).
5. **Strict Workshop Filtering**: rigorous heuristics drop non-research papers (≤ 5 pages, or "workshop"/"adjunct"/"poster" etc. in the title or proceedings venue).

### Two ways to run the pipeline

Every stage is scoped by institution, so routine maintenance never costs a full rebuild:

| | command | what it touches | cost |
|---|---|---|---|
| **Add one college** | `bash pipeline/add_institution.sh IITK` | that college only — everyone else is carried over verbatim | one college's DBLP calls (minutes) |
| **Monthly roster refresh** | `bash pipeline/refresh.sh` | all rosters; publication scores untouched | cached PIDs, mostly fast |
| **Full overnight refresh** | `bash pipeline/refresh.sh --with-publications` | rosters **and** re-fetches publications older than 30 days | hours against a throttled DBLP |

The two compose: add a college during the day and let the overnight job run later — it picks up the new college's fresh data as already-cached and spends its time looking for new papers everywhere else.

### Monthly refresh & the review loop

```bash
bash pipeline/refresh.sh                          # resolve → integrate
bash pipeline/refresh.sh --with-publications      # …then rescore publications
bash pipeline/refresh.sh --with-publications --max-age 7   # stricter staleness
```

This is the cron entry point. It exits **0** when everything is triaged, **2** when items need a human, and **1** if the run failed — so cron can alert. Anything the resolver can't verify lands in `data/needs_review.csv`; the maintainer resolves it by adding a row to **`data/pid_overrides.csv`**, which the resolver reads *before* the cache and any DBLP call, so manual fixes survive every re-run:

| action | effect |
|---|---|
| `set` | force a DBLP PID → person joins the roster as tier `MANUAL` |
| `drop` | exclude a duplicate name variant / non-CS entry |
| `ack` | leave unresolved, but stop alerting on it |

Publication scoring is opt-in because it's the slow half. `data/dblp_fetch_cache.json` keys raw DBLP results by PID with a fetch timestamp, and `--max-age DAYS` re-fetches only entries older than that — which is what surfaces new papers by existing faculty. Without `--max-age`, cached faculty are replayed for free. After any run that changes scores, reload the DB with `load_seed_data` + `load_rankings`.

### Adding an institution

Add one entry to `INSTITUTIONS` in `pipeline/institutions.py` — the exact CSRankings affiliation string plus keywords that confirm identity in a DBLP affiliation note:

```python
"IITK": {
    "name": "IIT Kanpur", "affiliation": "IIT Kanpur",
    "country": "India", "website": "https://www.iitk.ac.in",
    "state": "Uttar Pradesh", "city": "Kanpur",
    "affiliation_keywords": ["indian institute of technology kanpur", "iit kanpur"],
},
```

The dict key is the short code and also names the PID cache (`IITK` → `data/iitk_pid_cache.json`), so keep it stable once added. `affiliation` must match the CSRankings string **verbatim** — a typo silently yields zero faculty. Keywords are matched as substrings on punctuation-stripped text, so avoid ones that nest inside another tracked institution's name (`iit hyderabad` is a substring of `iiit hyderabad`).

That config entry is the only manual step. Then:

```bash
bash pipeline/add_institution.sh IITK
```

which resolves, integrates and scores **just that college** — the institutions already tracked are neither re-resolved nor re-fetched. Finish by reloading the DB (`load_seed_data` + `load_rankings`). No other code changes.

Under the hood it's three scoped commands, each usable on its own:

```bash
python pipeline/resolve_pids.py       --institution IITK   # → resolved_faculty.json
python pipeline/integrate_roster.py   --institution IITK   # → faculty.json (add-only)
python pipeline/fetch_publications.py --institution IITK   # → rankings.json (spliced)
```

Each folds its result into the shared file and leaves every other institution's data byte-identical, so the combined roster, `needs_review.*` counts and the rankings stay whole-project even after a single-college run. `resolve_pids.py --affiliation` (ad-hoc probe of an untracked string) stays out of the shared files unless you pass `--merge`.

### Known caveat

IIIT Delhi is currently the **only** institution with IRINS data scraped, so it alone receives journal and IRINS-only conference papers while the other 24 are DBLP-conference-only. This advantages IIIT Delhi for reasons unrelated to research output. Closing the gap requires either scraping IRINS for every institution or excluding IRINS-only papers from scoring.
