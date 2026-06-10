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

# Step 2: Load Seed Data (Institutions, Departments)
python manage.py load_seed_data

# Step 3: Load Faculty from IRINS
python manage.py load_irins

# Step 4: Fetch DBLP publications for all faculty
python manage.py fetch_dblp
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

The backend provides several robust endpoints for the frontend to consume.

### Dynamic Rankings (`GET /api/rankings/`)
Returns a pre-computed array of institutions and their top faculty based on dynamic parameters.
- `area` (str): Comma separated list of FoR Area codes (e.g., `4608`).
- `start_year` (int): Filter publications on or after year.
- `end_year` (int): Filter publications on or before year.
- `top_n` (int): Number of top faculty to return per institution (default: 5).

### Raw Data Endpoints
For detailed drill-downs or client-side aggregations.
- `GET /api/institutions/`
- `GET /api/faculty/` (Includes dynamically annotated total `score` for every faculty member)
- `GET /api/publications/` (Includes `authors` array of Faculty IDs)
- `GET /api/authorships/`
- `GET /api/conferences/`

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
