#!/usr/bin/env bash
#
# SPARK — monthly roster refresh (cron entry point).
#
# Runs the DBLP PID resolver across every tracked institution, regenerates the
# combined roster + shared needs-review file, tees a timestamped run log, and
# appends a one-line summary to data/review_log.md.
#
#   bash pipeline/refresh.sh
#       roster only: resolve → integrate. Publication scores are left alone.
#
#   bash pipeline/refresh.sh --with-publications [--max-age DAYS]
#       the full overnight job: roster, then re-fetch every faculty member whose
#       cached DBLP data is older than DAYS (default 30) and rewrite
#       rankings.json. This is what picks up new papers, new faculty, and any
#       institution added since the last run — hours against a throttled API.
#
# To add a single college WITHOUT re-running everyone, use the scoped path:
#   bash pipeline/add_institution.sh IITK
#
# Exit code:
#   0  — nothing needs a human (all review items are set/drop/ack'd)
#   2  — untriaged review items exist; a maintainer should open the review file
#         and add rows to data/pid_overrides.csv
#   1  — the run itself failed (CSV download, DBLP, etc.)
#
# Suggested cron (1st of each month, 03:00):
#   0 3 1 * * cd /path/to/spark && bash pipeline/refresh.sh >> pipeline/logs/cron.out 2>&1
#
set -euo pipefail

WITH_PUBS=0
MAX_AGE=30
while [[ $# -gt 0 ]]; do
  case "$1" in
    --with-publications) WITH_PUBS=1; shift ;;
    --max-age) MAX_AGE="$2"; shift 2 ;;
    -h|--help) sed -n '2,28p' "${BASH_SOURCE[0]}"; exit 0 ;;
    *) echo "unknown option: $1" >&2; exit 1 ;;
  esac
done

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PY="pipeline/.venv/bin/python"
CSV_OVERRIDES="data/pid_overrides.csv"
REVIEW_JSON="data/needs_review.json"
REVIEW_MD="data/needs_review.md"
REVIEW_LOG="data/review_log.md"
LOG_DIR="pipeline/logs"
TS="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
LOG="$LOG_DIR/refresh_${TS}.log"

mkdir -p "$LOG_DIR"

# 1. venv guard
if [[ ! -x "$PY" ]]; then
  echo "ERROR: $PY not found. Create it first:" >&2
  echo "  python3 -m venv pipeline/.venv && pipeline/.venv/bin/pip install -r pipeline/requirements.txt" >&2
  exit 1
fi

# 2. ensure the maintainer's overrides file exists (create a template once)
if [[ ! -f "$CSV_OVERRIDES" ]]; then
  cat > "$CSV_OVERRIDES" <<'EOF'
# SPARK manual PID overrides — the human-in-the-loop source of truth.
# The resolver reads this FIRST and it survives every re-run.
#   action=set  → force dblp_pid for this person (roster, tier MANUAL)
#   action=drop → exclude this person entirely (duplicate variant / not CS)
#   action=ack  → leave unresolved but stop alerting (stays in the review file)
# Lines starting with '#' and blank lines are ignored. Match by CSRankings name.
institution,csrankings_name,dblp_pid,action,note
EOF
  echo "Created template $CSV_OVERRIDES"
fi

# 3. resolve all institutions (fresh CSV, keep PID cache), tee to the run log
echo "SPARK refresh @ ${TS}" | tee "$LOG"
set +e
"$PY" pipeline/resolve_pids.py --all --refresh-csv 2>&1 | tee -a "$LOG"
RESOLVER_RC=${PIPESTATUS[0]}
set -e
if [[ "$RESOLVER_RC" -ne 0 ]]; then
  echo "ERROR: resolver exited $RESOLVER_RC — see $LOG" | tee -a "$LOG" >&2
  exit 1
fi

# 3b. merge the resolved roster into data/faculty.json (add-only, idempotent).
#     New/verified faculty flow into the site roster; existing curated entries
#     and IRINS links are left untouched.
echo "" | tee -a "$LOG"
"$PY" pipeline/integrate_roster.py 2>&1 | tee -a "$LOG"

# 3c. (opt-in) rescore publications. Off by default so the monthly cron stays a
#     fast roster-only job; --with-publications turns this into the full
#     overnight run that also picks up new papers for existing faculty.
if [[ "$WITH_PUBS" -eq 1 ]]; then
  echo "" | tee -a "$LOG"
  echo "Fetching publications (re-fetch anything older than ${MAX_AGE}d)…" | tee -a "$LOG"
  set +e
  "$PY" pipeline/fetch_publications.py --max-age "$MAX_AGE" 2>&1 | tee -a "$LOG"
  FETCH_RC=${PIPESTATUS[0]}
  set -e
  if [[ "$FETCH_RC" -ne 0 ]]; then
    echo "ERROR: fetch_publications exited $FETCH_RC — see $LOG" | tee -a "$LOG" >&2
    exit 1
  fi
fi

# 4. read the review status the resolver just wrote
read -r ROSTER FLAGGED UNTRIAGED < <("$PY" - "$REVIEW_JSON" <<'PYEOF'
import json, os, sys
review = json.load(open(sys.argv[1]))
roster = json.load(open(os.path.join(os.path.dirname(sys.argv[1]), "resolved_faculty.json")))
total = sum(i["faculty_count"] for i in roster["institutions"])
print(total, review["count"], review["untriaged"])
PYEOF
)

# 5. append one-line history row
if [[ ! -f "$REVIEW_LOG" ]]; then
  printf '# SPARK refresh history\n\n| Date (UTC) | Roster | Flagged | Untriaged |\n|---|---|---|---|\n' > "$REVIEW_LOG"
fi
printf '| %s | %s | %s | %s |\n' "$TS" "$ROSTER" "$FLAGGED" "$UNTRIAGED" >> "$REVIEW_LOG"

# 6. banner + exit signal
echo ""
echo "──────────────────────────────────────────────"
echo "  roster faculty : $ROSTER"
echo "  flagged        : $FLAGGED  (untriaged: $UNTRIAGED)"
if [[ "$WITH_PUBS" -eq 1 ]]; then
  echo "  publications   : rescored (max-age ${MAX_AGE}d) → data/rankings.json"
else
  echo "  publications   : not rescored (pass --with-publications)"
fi
echo "  run log        : $LOG"
echo "  review file    : $REVIEW_MD"
echo "  act here       : $CSV_OVERRIDES"
echo "──────────────────────────────────────────────"

if [[ "$UNTRIAGED" -gt 0 ]]; then
  echo "REVIEW NEEDED: $UNTRIAGED untriaged item(s). Open $REVIEW_MD and update $CSV_OVERRIDES."
  exit 2
fi
echo "All flagged items are triaged (set/drop/ack). Nothing to review."
exit 0
