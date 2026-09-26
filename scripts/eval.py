"""Print the 20-citation evaluation of the seeded sample (AC-1, AC-11) and gate on it.

Runs the sample through the pipeline (``--offline``: cache only, no network), scores
it against ``seed/ground_truth.json`` with ``citememo.evaluate``, prints the table
(line, citation, expected, memo said, match) and the stage timings, and exits 1 when
``--assert-min N`` (correct < N) or ``--assert-no-real-red`` (a real case predicted
likely_fabricated) fails.

Usage: .venv/bin/python scripts/eval.py --offline --assert-min 18 --assert-no-real-red [--json]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from citememo import evaluate as evaluate_mod  # noqa: E402
from citememo import memo as memo_mod  # noqa: E402
from citememo.cap import CapClient  # noqa: E402
from citememo.models import CLASS_KEY_LEGEND  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sample", default="sample-motion")
    ap.add_argument("--offline", action="store_true", help="serve CAP files from the cache only")
    ap.add_argument("--assert-min", type=int, default=None, help="exit 1 when fewer than N of 20 are correct")
    ap.add_argument("--assert-no-real-red", action="store_true", help="exit 1 when a real case is predicted likely_fabricated")
    ap.add_argument("--json", action="store_true", help="print the EvalReport JSON instead of the table")
    args = ap.parse_args()
    if args.offline:
        os.environ["CITEMEMO_OFFLINE"] = "1"
    os.environ.setdefault("CITEMEMO_QUIET", "1")
    cap = CapClient(offline=True if args.offline else None)
    memo = memo_mod.run_sample(args.sample, cap=cap)
    report = evaluate_mod.evaluate(memo)

    if args.json:
        print(json.dumps(report.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        print(f"EVALUATION — {args.sample} — run {memo.run_id} at {memo.created_at}{' (offline)' if memo.offline else ''}")
        print(f"{'Line':>4}  {'Citation':<74} {'Expected':<24} {'Memo said':<24} Match")
        for row in report.rows:
            exp = row.expected if len(row.accepted) == 1 else " or ".join(row.accepted)
            print(f"{(row.line if row.line is not None else '-')!s:>4}  {row.cite_text[:74]:<74} {exp[:24]:<24} {(row.predicted or '-')[:24]:<24} {'yes' if row.ok else 'NO'}")
        print()
        print(f"Correct classes: {report.correct} of {report.total} (accuracy {report.accuracy:.3f})")
        print(f"Real cases marked likely not real: {report.real_cases_marked_fabricated} of {report.real_total}")
        st = report.stage_timings_ms
        print(
            f"Stages (ms): extract {st.extract:.0f} · lookup {st.lookup:.0f} · classify {st.classify:.0f} · quotes {st.quotes:.0f} · "
            f"advisory {('%.0f' % st.advisory) if st.advisory is not None else 'not run'} · elapsed {report.elapsed_ms:.0f}"
        )
        print("Per class (expected → predicted): " + ", ".join(
            f"{CLASS_KEY_LEGEND.get(k, k)} {report.per_class['expected'].get(k, 0)}→{report.per_class['predicted'].get(k, 0)}"
            for k in sorted(set(report.per_class["expected"]) | set(report.per_class["predicted"]))
        ))
        if memo.warnings:
            print("Warnings: " + " | ".join(memo.warnings))

    rc = 0
    if args.assert_min is not None and report.correct < args.assert_min:
        print(f"FAIL: {report.correct} < {args.assert_min} correct", file=sys.stderr)
        rc = 1
    if args.assert_no_real_red and report.real_cases_marked_fabricated != 0:
        print(f"FAIL: {report.real_cases_marked_fabricated} real case(s) predicted likely_fabricated", file=sys.stderr)
        rc = 1
    if rc == 0 and (args.assert_min is not None or args.assert_no_real_red):
        print("PASS")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
