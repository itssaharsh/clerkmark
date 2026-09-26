"""Record a live run of the seeded sample into seed/replay.json (GET /api/replay, Alt+Shift+P).

Runs ``memo.run_sample`` with the network on (CAP files already in ``seed/cache/cap``
are served from disk, anything else is fetched live), then writes the Memo with
``replay: true`` and ``created_at`` = the recording time. Nothing in the file is
typed by hand: every row, count and timing is what that run produced.

Usage: PYTHONPATH=. .venv/bin/python scripts/record_replay.py [--sample sample-motion] [--out seed/replay.json] [--offline]
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from citememo import memo as memo_mod  # noqa: E402
from citememo.cap import CapClient  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--sample", default="sample-motion")
    ap.add_argument("--out", default=str(ROOT / "seed" / "replay.json"))
    ap.add_argument("--offline", action="store_true", help="record from the cache only (sets memo.offline)")
    args = ap.parse_args()
    if args.offline:
        os.environ["CITEMEMO_OFFLINE"] = "1"
    cap = CapClient(offline=True if args.offline else None)
    memo = memo_mod.run_sample(args.sample, cap=cap)
    memo.replay = True
    memo.notes = list(memo.notes) + [
        f"Recorded run of the seeded sample by scripts/record_replay.py on {memo.created_at}"
        + (" from the on-disk cache (offline)." if memo.offline else " with the network on; CAP files already cached were read from seed/cache/cap.")
    ]
    out = Path(args.out)
    out.write_text(json.dumps(memo.model_dump(by_alias=True, mode="json"), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    c = memo.counts
    print(
        f"wrote {out} — {c.total} citations in {memo.elapsed_ms / 1000:.2f} s; "
        f"red {c.likely_fabricated}, amber {c.quote_not_found + c.wrong_cite_exists}, coverage {c.not_in_free_corpus}, "
        f"found {c.verified}, not_checked {c.not_checked}; offline={memo.offline}; warnings={len(memo.warnings)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
