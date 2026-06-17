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
| Methodology       | Geometric mean    | Adjusted count (per-author credit) |
| Data source       | DBLP              | **DBLP + IRINS**                               |
| Transparency      | Open source       | Open source + open data            |

> **Example:** IIIT Delhi faculty publish extensively in conferences like COMAD, ISEC, IndoCrypt, ICDCN, and many ICORE A-ranked venues that CSRankings ignores entirely. SPARK counts them all.

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

---

## Architecture

SPARK uses a **Django REST Framework** backend that handles the heavy lifting of dynamic scoring, and a separate client-side frontend.

```
spark/
├── backend/                     # Django REST Backend
│   ├── api/                     # DRF Models, Views, Serializers
│   │   └── management/commands/ # Data Pipeline scripts
│   │       ├── load_seed_data.py
│   │       ├── load_irins.py
│   │       └── fetch_dblp.py
│   ├── backend/                 # Project Settings, URLs
│   ├── db.sqlite3               # Auto-generated SQLite Database
│   └── requirements.txt         # Python dependencies
│
├── data/                        # Local data and checkpoints
│
├── src/                         # Frontend source
│   ├── main.js                  # App logic, rendering, filters
│   └── index.css                # Design system (dark mode, glassmorphism)
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
2. **Conference Weighting**: The fractional credit is then multiplied by the venue's tier:
   - **A\*** = 4.0 multiplier
   - **A** = 2.0 multiplier
   - **Default** = 1.0 multiplier
3. **Faculty Score**: Sum of weighted credits across all matched papers.
4. **Institution Score**: Sum of all its faculty scores.

---

## Data Pipeline

SPARK fetches academic data automatically from two primary sources:

1. **IRINS Scraper**: Parses the institutional research information system to automatically discover and import faculty lists for CS/CSE departments.
2. **DBLP Fetcher**: Retrieves XML dumps of publications from the DBLP API via `dblp_key` match (preventing string-matching fuzzy errors), resolving exact venue and author matches.
