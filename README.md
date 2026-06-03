<p align="center">
  <img src="https://img.shields.io/badge/ICORE-2026-f5a623?style=for-the-badge&labelColor=0c1021" alt="ICORE 2026" />
  <img src="https://img.shields.io/badge/conferences-170%20A%2FA*-6384ff?style=for-the-badge&labelColor=0c1021" alt="170 A/A* Conferences" />
  <img src="https://img.shields.io/badge/data%20source-DBLP-34d399?style=for-the-badge&labelColor=0c1021" alt="DBLP" />
  <img src="https://img.shields.io/badge/license-MIT-a78bfa?style=for-the-badge&labelColor=0c1021" alt="MIT License" />
</p>

<h1 align="center">🎓 SPARK</h1>
<h3 align="center">Scholarly Publication & Academic Ranking Knowledgebase</h3>

<p align="center">
  Rank CS departments using <strong>all</strong> ICORE A*/A conferences; not just the hand-picked CSRankings subset.
  <br />
  Transparent, data-driven, DBLP-sourced. No CSRankings code used.
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
| Data source       | DBLP              | DBLP                               |
| Transparency      | Open source       | Open source + open data            |

> **Example:** IIIT Delhi faculty publish extensively in conferences like COMAD, ISEC, IndoCrypt, ICDCN, and many ICORE A-ranked venues that CSRankings ignores entirely. SPARK counts them all.

---

## Quick Start

### Prerequisites

- **Node.js** ≥ 18
- **Python** ≥ 3.10
- Internet connection (for scraping ICORE and querying DBLP)

### 1. Install dependencies

```bash
git clone <your-repo-url> && cd spark

# Frontend
npm install

# Data pipeline
python3 -m venv pipeline/.venv
source pipeline/.venv/bin/activate
pip install -r pipeline/requirements.txt
```

### 2. Run the data pipeline

```bash
source pipeline/.venv/bin/activate

# Step 1: Scrape ICORE2026 conference rankings (~40 seconds)
python pipeline/scrape_icore.py

# Step 2: Fetch DBLP publications & compute scores (~1-3 minutes)
python pipeline/fetch_publications.py
```

### 3. Launch the website

```bash
npm run dev
# → Open http://localhost:5173
```

That's it. The website loads `data/rankings.json` and renders everything client-side.

---

## Architecture

```
spark/
├── pipeline/                    # Python data collection scripts
│   ├── scrape_icore.py          # Scrapes ICORE portal for A*/A conferences
│   ├── fetch_publications.py    # Fetches DBLP pubs, matches venues, scores
│   ├── requirements.txt         # Python dependencies
│   └── .venv/                   # Python virtual environment (gitignored)
│
├── data/                        # Generated + curated data
│   ├── faculty.json             # Manually curated faculty list
│   ├── icore_conferences.json   # Auto-generated: 170 A*/A conferences
│   └── rankings.json            # Auto-generated: final scores + publications
│
├── src/                         # Frontend source
│   ├── main.js                  # App logic, rendering, filters
│   └── index.css                # Design system (dark mode, glassmorphism)
│
├── public/data/                 # Symlink to data/ for Vite serving
├── index.html                   # Entry point
├── vite.config.js               # Vite configuration
└── package.json
```

### Data flow

```
ICORE Portal ──scrape──→ icore_conferences.json ──┐
                                                   ├──→ rankings.json ──→ Frontend
faculty.json (manual) ──→ DBLP API ──fetch_pubs───┘
```

No database, no backend server. The pipeline produces static JSON; the frontend is pure client-side JS.

---

## Scoring Methodology

SPARK uses **adjusted counts**, the same method CSRankings uses:

1. **For each paper** published at an ICORE A\*/A conference:

   - Credit = `1.0 / number_of_coauthors`
   - This prevents gaming via large author lists
2. **Faculty score** = sum of adjusted counts across all matched papers
3. **Institution score** = sum of all faculty scores
4. **Year range**: 2015–2025 (configurable in `fetch_publications.py`)

### Conference matching

Each ICORE conference entry includes a DBLP venue URL. We extract the DBLP venue key (e.g., `aaai`, `chi`, `mm`) and match it against the venue key in each DBLP publication record. This ensures exact matching — no fuzzy string comparison.

---

## Adding Institutions

SPARK is designed to be easily extensible. To add a new institution:

### 1. Edit `data/faculty.json`

Add a new entry to the `institutions` array:

```json
{
  "name": "IIT Delhi",
  "short": "IITD",
  "country": "India",
  "website": "https://www.cse.iitd.ac.in",
  "faculty": [
    {
      "name": "Faculty Name",
      "dblp_pid": "123/4567",
      "role": "Professor",
      "homepage": "https://..."
    }
  ]
}
```

### 2. Find DBLP PIDs

Search for a faculty member's DBLP PID:

```
https://dblp.org/search/author/api?q=Faculty+Name&format=json&h=5
```

The PID is the path after `https://dblp.org/pid/` — e.g., `85/6670` or `j/PankajJalote`.

> **Common names**: DBLP uses disambiguation suffixes (e.g., `55/1719-1`). Check the affiliation field to pick the right one.

### 3. Re-run the pipeline

```bash
source pipeline/.venv/bin/activate
python pipeline/fetch_publications.py
```

The ICORE scrape only needs to be re-run if the ICORE rankings are updated.

### 4. Refresh the browser

The dev server picks up data changes automatically via the symlink.

---

## Frontend Features

| Feature                  | Description                                                    |
| ------------------------ | -------------------------------------------------------------- |
| **🏆 Rankings**    | Sortable institution table with expandable faculty drill-down  |
| **📊 Areas**       | Visual bar chart of publications per FoR research area         |
| **📚 Conferences** | Browse all 170 A\*/A conferences; highlights those with papers |
| **📋 Methodology** | Scoring explanation + SPARK vs CSRankings comparison table     |
| **🔍 Search**      | Filter by faculty name or institution                          |
| **⚡ Filters**     | Toggle A\* only / A only / both; filter by research area       |
| **🌙 Dark Mode**   | Premium dark UI with glassmorphism and micro-animations        |

---

## Configuration

Key parameters in `pipeline/fetch_publications.py`:

| Variable          | Default  | Description                                 |
| ----------------- | -------- | ------------------------------------------- |
| `YEAR_START`    | `2015` | First year to include                       |
| `YEAR_END`      | `2025` | Last year to include                        |
| `DELAY_SECONDS` | `3.0`  | Delay between DBLP requests (rate limiting) |
| `MAX_RETRIES`   | `4`    | Retry count for DBLP 429 errors             |

To switch to a different ICORE source (e.g., CORE2023), change `PARAMS_BASE["source"]` in `scrape_icore.py`.

---

## Rate Limiting

Both the ICORE portal and DBLP enforce rate limits:

- **ICORE**: 2-second delay between page fetches (20 pages total)
- **DBLP**: 3-second delay between author lookups, with exponential backoff on 429 errors

The pipeline is intentionally slow to be a good citizen. First run takes ~2–4 minutes depending on the number of faculty. Subsequent runs with the same ICORE data only need `fetch_publications.py`.

---

## Tech Stack

| Layer         | Technology                              |
| ------------- | --------------------------------------- |
| Data pipeline | Python 3, requests, BeautifulSoup, lxml |
| Frontend      | Vanilla JS, Vanilla CSS, Vite           |
| Data format   | Static JSON (no database)               |
| Fonts         | Inter, JetBrains Mono (Google Fonts)    |
| Data sources  | ICORE Portal, DBLP API                  |


---

<p align="center">
  <sub>
    Built for transparent academic ranking · Data from <a href="https://dblp.org">DBLP</a> and <a href="http://portal.core.edu.au/conf-ranks/">ICORE</a>
  </sub>
</p>
