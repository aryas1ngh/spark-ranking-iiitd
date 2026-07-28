#!/usr/bin/env bash
#
# SPARK — add ONE institution without re-running the pipeline for everybody.
#
#   bash pipeline/add_institution.sh IITK
#
# Does the same three steps refresh.sh does, scoped to a single short code:
#
#   1. resolve_pids.py --institution CODE   → PIDs for that college only, folded
#                                             into resolved_faculty.json
#   2. integrate_roster.py --institution CODE → appended to faculty.json (add-only)
#   3. fetch_publications.py --institution CODE → its block spliced into
#                                             rankings.json, others carried over
#
# The 24 institutions already in the roster are never re-resolved and never
# re-fetched, so this is minutes of DBLP calls instead of hours. It is *not* a
# refresh: existing colleges keep whatever publication data they already had.
# For "add this college AND look for new papers everywhere", run the overnight
# job instead:  bash pipeline/refresh.sh --with-publications
#
# The short code must already exist in pipeline/institutions.py — that config
# entry is still the one manual step (see README, "Adding an institution").
#
# Exit code (matches refresh.sh so the same cron alerting works):
#   0  — added, nothing needs a human
#   2  — added, but untriaged items exist in data/needs_review.md
#   1  — the run failed
#
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

PY="pipeline/.venv/bin/python"
LOG_DIR="pipeline/logs"
REVIEW_MD="data/needs_review.md"
CSV_OVERRIDES="data/pid_overrides.csv"

if [[ $# -lt 1 ]]; then
  echo "usage: bash pipeline/add_institution.sh <SHORT_CODE>   (e.g. IITK)" >&2
  exit 1
fi
CODE="$(echo "$1" | tr '[:lower:]' '[:upper:]')"
shift

if [[ ! -x "$PY" ]]; then
  echo "ERROR: $PY not found. Create it first:" >&2
  echo "  python3 -m venv pipeline/.venv && pipeline/.venv/bin/pip install -r pipeline/requirements.txt" >&2
  exit 1
fi

# Fail before any DBLP traffic if the config entry is missing — the one thing
# this script can't do for you.
if ! "$PY" - "$CODE" <<'PYEOF'
import sys, os
sys.path.insert(0, os.path.join(os.getcwd(), "pipeline"))
from institutions import INSTITUTIONS
code = sys.argv[1]
if code not in INSTITUTIONS:
    print(f"ERROR: '{code}' is not in pipeline/institutions.py.", file=sys.stderr)
    print("Add its entry there first (exact CSRankings affiliation string + "
          "affiliation_keywords), then re-run.", file=sys.stderr)
    print(f"Known codes: {', '.join(sorted(INSTITUTIONS))}", file=sys.stderr)
    sys.exit(1)
print(f"{code} → {INSTITUTIONS[code]['name']}  (affiliation: \"{INSTITUTIONS[code]['affiliation']}\")")
PYEOF
then
  exit 1
fi

mkdir -p "$LOG_DIR"
TS="$(date -u +%Y-%m-%dT%H-%M-%SZ)"
LOG="$LOG_DIR/add_$(echo "$CODE" | tr '[:upper:]' '[:lower:]')_${TS}.log"

echo "SPARK add-institution: $CODE @ ${TS}" | tee "$LOG"

# 1. resolve — folds into resolved_faculty.json + needs_review.* by default.
#    Exit 2 means "resolved fine, but some people need a human"; that's not a
#    reason to stop, so it's captured rather than allowed to kill the script.
set +e
"$PY" pipeline/resolve_pids.py --institution "$CODE" "$@" 2>&1 | tee -a "$LOG"
RESOLVE_RC=${PIPESTATUS[0]}
set -e
if [[ "$RESOLVE_RC" -ne 0 && "$RESOLVE_RC" -ne 2 ]]; then
  echo "ERROR: resolver exited $RESOLVE_RC — see $LOG" | tee -a "$LOG" >&2
  exit 1
fi

# 2. integrate into faculty.json — scoped, add-only, idempotent
echo "" | tee -a "$LOG"
"$PY" pipeline/integrate_roster.py --institution "$CODE" 2>&1 | tee -a "$LOG"

# 3. score it and splice into rankings.json
echo "" | tee -a "$LOG"
"$PY" pipeline/fetch_publications.py --institution "$CODE" 2>&1 | tee -a "$LOG"

echo ""
echo "──────────────────────────────────────────────"
echo "  added         : $CODE"
echo "  run log       : $LOG"
echo "  next          : reload the DB —"
echo "                    source backend_venv/bin/activate && cd backend"
echo "                    python manage.py load_seed_data && python manage.py load_rankings"
echo "──────────────────────────────────────────────"

if [[ "$RESOLVE_RC" -eq 2 ]]; then
  echo "REVIEW NEEDED: untriaged item(s) in the shared review file (may include"
  echo "               institutions other than $CODE). Open $REVIEW_MD and update $CSV_OVERRIDES."
  exit 2
fi
exit 0
