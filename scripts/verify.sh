#!/usr/bin/env bash
# scripts/verify.sh — PASS/FAIL proof of the seeded demo path, with no network (AC-7, AC-11).
#
# Starts uvicorn on a free port (first try: $PORT, default 8000) with CITEMEMO_OFFLINE=1,
# waits for GET /api/health, POSTs /api/memo/sample/sample-motion, reads GET /api/eval and
# asserts: 20 scored citations, >= 18 in their accepted classes, 0 real cases marked
# likely_fabricated, the Miller row likely_fabricated, the Shaboon row not_in_free_corpus,
# health.offline and memo.offline true. Prints one table line with the run's own numbers
#   citations 20 · correct N/20 · real cases marked likely-not-real 0 · elapsed X s
# then PASS or FAIL, exits 0 or 1, and always stops the server (trap on EXIT).
# "elapsed" is memo.elapsed_ms (the stamp's number). It is printed, not gated: AC-7's 5 s
# offline budget is asserted by `pytest -k offline`; a run over 5 s adds a NOTE line here.
# Set VERIFY_MAX_ELAPSED_S=5 to make the budget a FAIL as well.
#
# Env (all optional): PORT (first port to try, default 8000), PYTHON (interpreter; default
# .venv/bin/python when present, else python3), VERIFY_MIN_CORRECT (default 18),
# VERIFY_MAX_ELAPSED_S (seconds; unset = no time gate), VERIFY_KEEP=1 keeps the JSON answers.
# Used by CI (.github/workflows/ci.yml), the QA gate, the review and the deploy check.

set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

PY="${PYTHON:-}"
if [ -z "$PY" ]; then
  if [ -x .venv/bin/python ]; then PY=.venv/bin/python; else PY=python3; fi
fi
MIN_CORRECT="${VERIFY_MIN_CORRECT:-18}"
MAX_ELAPSED_S="${VERIFY_MAX_ELAPSED_S:-0}"  # 0 = print the elapsed time, do not gate on it
START_PORT="${PORT:-8000}"
OUT="$(mktemp -d "${TMPDIR:-/tmp}/citememo-verify.XXXXXX")"
SERVER_PID=""
STATUS=1

cleanup() {
  if [ -n "$SERVER_PID" ] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null
    for _ in $(seq 1 50); do
      kill -0 "$SERVER_PID" 2>/dev/null || break
      sleep 0.1
    done
    kill -0 "$SERVER_PID" 2>/dev/null && kill -9 "$SERVER_PID" 2>/dev/null
    wait "$SERVER_PID" 2>/dev/null
    echo "server stopped (pid $SERVER_PID)"
  fi
  if [ "${VERIFY_KEEP:-0}" = "1" ]; then echo "answers kept in $OUT"; else rm -rf "$OUT"; fi
  exit "$STATUS"
}
trap cleanup EXIT

fail() {
  echo "FAIL: $*"
  if [ -s "$OUT/server.log" ]; then echo "--- server log ---"; tail -n 40 "$OUT/server.log"; fi
  STATUS=1
  exit 1
}

command -v curl >/dev/null 2>&1 || fail "curl is required"
"$PY" -c "import uvicorn, fastapi" 2>/dev/null || fail "$PY lacks uvicorn/fastapi (pip install -r requirements.txt)"

# --- a free port, starting at $START_PORT ------------------------------------------------
PORT_CHOSEN="$("$PY" - "$START_PORT" <<'EOF'
import socket, sys
start = int(sys.argv[1])
for port in range(start, start + 100):
    with socket.socket() as s:
        try:
            s.bind(("127.0.0.1", port))
        except OSError:
            continue
    print(port)
    sys.exit(0)
sys.exit(1)
EOF
)" || fail "no free port between $START_PORT and $((START_PORT + 99))"
BASE="http://127.0.0.1:$PORT_CHOSEN"

# --- start the server offline ------------------------------------------------------------
CITEMEMO_OFFLINE=1 CITEMEMO_QUIET=1 "$PY" -m uvicorn main:app --host 127.0.0.1 --port "$PORT_CHOSEN" --log-level warning \
  >"$OUT/server.log" 2>&1 &
SERVER_PID=$!
echo "Clerkmark verify · offline · $BASE (pid $SERVER_PID) · $("$PY" --version 2>&1)"

ready=0
for _ in $(seq 1 120); do  # up to 30 s
  if curl -fsS "$BASE/api/health" -o "$OUT/health.json" 2>/dev/null; then ready=1; break; fi
  kill -0 "$SERVER_PID" 2>/dev/null || break
  sleep 0.25
done
[ "$ready" = 1 ] || fail "the server did not answer GET /api/health within 30 s"

# --- the demo path -----------------------------------------------------------------------
T0="$(date +%s.%N)"
curl -fsS -X POST "$BASE/api/memo/sample/sample-motion" -o "$OUT/memo.json" || fail "POST /api/memo/sample/sample-motion did not answer 200"
T1="$(date +%s.%N)"
curl -fsS "$BASE/api/eval" -o "$OUT/eval.json" || fail "GET /api/eval did not answer 200"

# --- the checks (python: no jq needed) ---------------------------------------------------
"$PY" - "$OUT" "$MIN_CORRECT" "$MAX_ELAPSED_S" "$T0" "$T1" <<'EOF'
import json, sys

out, min_correct, max_elapsed, t0, t1 = sys.argv[1], int(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4]), float(sys.argv[5])
health = json.load(open(f"{out}/health.json", encoding="utf-8"))
memo = json.load(open(f"{out}/memo.json", encoding="utf-8"))
ev = json.load(open(f"{out}/eval.json", encoding="utf-8"))
fails = []

def check(ok, what):
    if not ok:
        fails.append(what)

def row(prefix):
    return next((r for r in memo.get("results", []) if r["cite_text"].startswith(prefix)), None)

miller = row("Miller v. United Airlines")
shaboon = row("Shaboon v. Egyptair")
elapsed = float(memo.get("elapsed_ms", 0.0)) / 1000.0
wall = t1 - t0
c = memo.get("counts", {})

check(health.get("ok") is True and health.get("offline") is True, f"health: ok={health.get('ok')} offline={health.get('offline')} (expected ok, offline)")
check(memo.get("offline") is True, f"memo.offline={memo.get('offline')} (expected true: answers from the committed cache)")
check(memo.get("sample_id") == "sample-motion", f"memo.sample_id={memo.get('sample_id')}")
check(ev.get("total") == 20, f"eval.total={ev.get('total')} (expected 20 scored citations)")
check(ev.get("correct", 0) >= min_correct, f"eval.correct={ev.get('correct')} < {min_correct}")
check(ev.get("real_cases_marked_fabricated") == 0, f"eval.real_cases_marked_fabricated={ev.get('real_cases_marked_fabricated')} (expected 0)")
check(miller is not None and miller["class"] == "likely_fabricated", f"Miller row: {miller and miller['class']} (expected likely_fabricated)")
check(shaboon is not None and shaboon["class"] == "not_in_free_corpus", f"Shaboon row: {shaboon and shaboon['class']} (expected not_in_free_corpus)")
check(elapsed > 0, f"memo.elapsed_ms={memo.get('elapsed_ms')} (expected a measured, positive run time)")
if max_elapsed > 0:
    check(elapsed <= max_elapsed, f"elapsed {elapsed:.1f} s > {max_elapsed:g} s (VERIFY_MAX_ELAPSED_S)")

print(f"citations {ev.get('total')} · correct {ev.get('correct')}/{ev.get('total')} · real cases marked likely-not-real {ev.get('real_cases_marked_fabricated')} · elapsed {elapsed:.1f} s")
print(
    f"rows {c.get('total')} · likely not real {c.get('likely_fabricated')} · no reporter {c.get('unrecognized_reporter')} · "
    f"quote not in opinion {c.get('quote_not_found')} · other page {c.get('wrong_cite_exists')} · found {c.get('verified')} · "
    f"not in free library {c.get('not_in_free_corpus')} · not checked {c.get('not_checked')} · skipped {c.get('skipped')}"
)
print(f"real cases {ev.get('real_total')} · offline {memo.get('offline')} · warnings {len(memo.get('warnings', []))} · POST wall {wall:.1f} s · run {memo.get('run_id')}")
print(f"Miller v. United Airlines → {miller['class'] if miller else 'missing'} · Shaboon v. Egyptair → {shaboon['class'] if shaboon else 'missing'}")
if max_elapsed <= 0 and elapsed > 5.0:
    print(f"NOTE: elapsed {elapsed:.1f} s is over AC-7's 5 s offline budget on this machine (asserted by `pytest -k offline`; the quote stage is the slow part, see .prod-build/reports/T05.md)")
for f in fails:
    print("FAIL:", f)
print("PASS" if not fails else "FAIL")
sys.exit(0 if not fails else 1)
EOF
STATUS=$?
exit "$STATUS"
