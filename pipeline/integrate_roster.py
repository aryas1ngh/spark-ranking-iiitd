#!/usr/bin/env python3
"""
Merge the resolver's roster (data/resolved_faculty.json) into the site roster
(data/faculty.json) — which the publication pipeline and the backend seed
loader consume. Run automatically by pipeline/refresh.sh; not invoked by hand.

Policy (chosen by the maintainer):
  - EXISTING institutions (matched by institution name): keep every current
    entry and all institution metadata (irins_url, roles) untouched; only
    APPEND faculty the resolver newly found that aren't already present
    (matched by dblp_pid, else normalised name / alias). Existing PIDs are
    never overwritten — hand-curated data and the IRINS pipeline stay safe.
  - NEW institutions: added in full, converted to faculty.json's schema.

Only HIGH/MEDIUM/MANUAL faculty appear in resolved_faculty.json (REVIEW items
live in needs_review.*), so nothing unverified is merged.

Idempotent: re-running matches on pid/name and won't create duplicates.

Usage:
    python pipeline/integrate_roster.py                     # merge every institution
    python pipeline/integrate_roster.py --institution IITK  # merge only this one
    python pipeline/integrate_roster.py --dry-run           # report changes only
"""

import argparse
import json
import os
import re

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(os.path.dirname(SCRIPT_DIR), "data")
FACULTY_FILE = os.path.join(DATA_DIR, "faculty.json")
RESOLVED_FILE = os.path.join(DATA_DIR, "resolved_faculty.json")

INST_META_KEYS = ("name", "short", "country", "website", "state", "city")


def norm(n):
    return re.sub(r"[^a-z0-9]", "", (n or "").lower())


def to_faculty_entry(rf):
    """Resolver entry → faculty.json faculty schema (name, dblp_pid, role, homepage)."""
    return {
        "name": rf["name"],
        "dblp_pid": rf["dblp_pid"],
        "role": "",  # CSRankings carries no role/designation
        "homepage": rf.get("homepage", "") or "",
    }


def parse_codes(values):
    """--institution IITK --institution IITB  ==  --institution IITK,IITB"""
    if not values:
        return None
    return {c.strip().upper() for v in values for c in v.split(",") if c.strip()}


def main():
    ap = argparse.ArgumentParser(description="Merge resolved_faculty.json into faculty.json.")
    ap.add_argument("--dry-run", action="store_true", help="Report changes without writing")
    ap.add_argument("--institution", action="append", metavar="CODE",
                    help="Only merge these short codes (repeatable or comma-separated). "
                         "Default: every institution in resolved_faculty.json.")
    args = ap.parse_args()

    with open(FACULTY_FILE, encoding="utf-8") as f:
        faculty = json.load(f)
    with open(RESOLVED_FILE, encoding="utf-8") as f:
        resolved = json.load(f)

    only = parse_codes(args.institution)
    if only:
        available = {i["short"].upper() for i in resolved["institutions"]}
        unknown = only - available
        if unknown:
            ap.error(f"not in resolved_faculty.json: {', '.join(sorted(unknown))}. "
                     f"Resolve it first: python pipeline/resolve_pids.py --institution "
                     f"{sorted(unknown)[0]}")

    existing_by_name = {i["name"]: i for i in faculty["institutions"]}

    added_faculty = 0
    new_institutions = []
    per_inst = []

    for rinst in resolved["institutions"]:
        name = rinst["name"]
        if only and rinst["short"].upper() not in only:
            continue
        if name in existing_by_name:
            inst = existing_by_name[name]
            existing_pids = {f.get("dblp_pid") for f in inst["faculty"] if f.get("dblp_pid")}
            existing_names = {norm(f["name"]) for f in inst["faculty"]}
            added_here = 0
            for rf in rinst["faculty"]:
                pid = rf.get("dblp_pid")
                names = {norm(rf["name"])} | {norm(a) for a in rf.get("aliases", [])}
                if pid and pid in existing_pids:
                    continue  # already tracked (same PID)
                if names & existing_names:
                    continue  # already tracked (name/alias) — leave existing PID as-is
                inst["faculty"].append(to_faculty_entry(rf))
                if pid:
                    existing_pids.add(pid)
                existing_names.add(norm(rf["name"]))
                added_here += 1
            added_faculty += added_here
            per_inst.append((rinst["short"], name, "merge", added_here, len(inst["faculty"])))
        else:
            block = {k: rinst[k] for k in INST_META_KEYS if k in rinst}
            block["faculty"] = [to_faculty_entry(f) for f in rinst["faculty"]]
            faculty["institutions"].append(block)
            new_institutions.append(name)
            added_faculty += len(block["faculty"])
            per_inst.append((rinst["short"], name, "new", len(block["faculty"]), len(block["faculty"])))

    print("=" * 60)
    scope = f"  [only {', '.join(sorted(only))}]" if only else ""
    print("Integrate resolved roster → faculty.json" + scope
          + ("  (DRY RUN)" if args.dry_run else ""))
    print("=" * 60)
    for short, name, mode, added, total in per_inst:
        print(f"  {short:7s} {name:16s} [{mode:5s}] +{added:3d} faculty  (roster now {total})")
    total_fac = sum(len(i["faculty"]) for i in faculty["institutions"])
    print("-" * 60)
    print(f"  new institutions: {len(new_institutions)}  {new_institutions}")
    print(f"  faculty added:    {added_faculty}")
    print(f"  faculty.json now: {len(faculty['institutions'])} institutions, {total_fac} faculty")
    print("=" * 60)

    if args.dry_run:
        print("Dry run — faculty.json NOT written.")
        return

    with open(FACULTY_FILE, "w", encoding="utf-8") as f:
        json.dump(faculty, f, indent=2, ensure_ascii=False)
    print(f"Wrote {FACULTY_FILE}")


if __name__ == "__main__":
    main()
