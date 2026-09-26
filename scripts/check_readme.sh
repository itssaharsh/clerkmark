#!/usr/bin/env bash
# scripts/check_readme.sh — fails unless README.md declares the tech stack (AC-14).
#
# Requires, in README.md (or the file given as $1):
#   * a "Tech stack" table (a markdown table within 40 lines after the phrase) that names
#     every package in requirements.txt, by package name or import name
#     (python-multipart → multipart, fpdf2 → fpdf, courts-db → courts_db, ...);
#   * the words "Caselaw Access Project", "CourtListener", "eyecite" and the model id
#     "claude-haiku-4-5-20251001";
#   * a "Live vs simulated" table (also accepts "Live vs. simulated").
# Exit 0 with PASS when everything is present; exit 1 listing each missing item.
# T10 writes the README; until then this script fails (CI runs it with continue-on-error).

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

README="${1:-README.md}"
REQ="requirements.txt"
missing=0

miss() {
  echo "MISSING: $*"
  missing=$((missing + 1))
}

if [ ! -f "$README" ]; then
  echo "MISSING: $README does not exist"
  echo "FAIL: README check (1 missing)"
  exit 1
fi
[ -f "$REQ" ] || { echo "MISSING: $REQ does not exist"; echo "FAIL: README check (1 missing)"; exit 1; }

# Print the first markdown table that follows the phrase (case-insensitive), within 40 lines.
table_after() {
  awk -v pat="$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]')" '
    BEGIN { n = -1; intable = 0 }
    {
      if (n < 0) { if (index(tolower($0), pat) > 0) n = 0; next }
      if ($0 ~ /^[ \t]*\|/) { intable = 1; print; n++; next }
      if (intable) exit
      n++; if (n > 40) exit
    }' "$README"
}

# --- the tech-stack table names every requirement ----------------------------------------
TECH="$(table_after "tech stack")"
if [ -z "$TECH" ]; then
  miss "a \"Tech stack\" table (a markdown table within 40 lines after the words \"Tech stack\")"
else
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%%#*}"
    line="$(printf '%s' "$line" | tr -d '[:space:]')"
    [ -z "$line" ] && continue
    pkg="${line%%[=<>~!;\[]*}"
    [ -z "$pkg" ] && continue
    imp="${pkg//-/_}"
    case "$pkg" in
      python-multipart) imp="multipart" ;;
      fpdf2) imp="fpdf" ;;
    esac
    if ! printf '%s\n' "$TECH" | grep -qiF -- "$pkg" && ! printf '%s\n' "$TECH" | grep -qiF -- "$imp"; then
      miss "the Tech stack table does not name requirements.txt package '$pkg' (or its import name '$imp')"
    fi
  done <"$REQ"
fi

# --- the sources and the model, by name ---------------------------------------------------
grep -qF -- "Caselaw Access Project" "$README" || miss "the words \"Caselaw Access Project\""
grep -qF -- "CourtListener" "$README" || miss "the word \"CourtListener\""
grep -qiF -- "eyecite" "$README" || miss "the word \"eyecite\""
grep -qF -- "claude-haiku-4-5-20251001" "$README" || miss "the model id \"claude-haiku-4-5-20251001\""

# --- the live-vs-simulated table ---------------------------------------------------------
LIVE="$(table_after "live vs simulated")"
[ -n "$LIVE" ] || LIVE="$(table_after "live vs. simulated")"
[ -n "$LIVE" ] || miss "a \"Live vs simulated\" table (a markdown table within 40 lines after the words \"Live vs simulated\")"

if [ "$missing" -gt 0 ]; then
  echo "FAIL: README check ($missing missing) — $README"
  exit 1
fi
echo "PASS: $README names every requirements.txt package in its Tech stack table, the Caselaw Access Project, CourtListener, eyecite, claude-haiku-4-5-20251001, and has a Live vs simulated table"
exit 0
