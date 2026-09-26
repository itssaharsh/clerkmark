"""Fetch every CAP file the seeded sample needs into seed/cache/cap (the committed cache).

Reads ``seed/ground_truth.json`` (``items[].cap_urls`` and ``extra_in_label.cap_urls``),
adds the volume index of every reporter those URLs name, and fetches whatever is
missing from ``seed/cache/cap`` through :class:`citememo.cap.CapClient` (so the files
land in exactly the cache layout the app reads). Files already present are not
re-fetched. A 404 is recorded as a ``.404`` marker (an Absent answer, DECISION-RULE §1.4).

Usage: PYTHONPATH=. .venv/bin/python scripts/warm_cache.py [--dry-run]
Network: static.case.law (allowed for this script). Commit the new files afterwards.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from citememo.cache import DiskCache  # noqa: E402
from citememo.cap import CAP_BASE, CapClient, CorpusUnavailable  # noqa: E402
from citememo.extract import extract_citations  # noqa: E402

SEED_CACHE = ROOT / "seed" / "cache" / "cap"
GROUND_TRUTH = ROOT / "seed" / "ground_truth.json"

_URL = re.compile(r"^https://static\.case\.law/(.+)$")


def needed_paths(cap: CapClient) -> list[str]:
    """Cache-relative paths the seed needs: each cited reporter's volume index, then the cap_urls."""
    gt = json.loads(GROUND_TRUTH.read_text(encoding="utf-8"))
    entries = list(gt.get("items", [])) + ([gt["extra_in_label"]] if gt.get("extra_in_label") else [])
    rels: list[str] = []
    for item in entries:
        reporter = item.get("reporter")
        if not reporter:  # the page-1 label cite carries no reporter field: read it off the cite text
            found = [c for c in extract_citations(item.get("cite_text", "")) if c.kind == "full"]
            reporter = found[0].reporter if found else None
        slug = cap.reporter_slug(reporter) if reporter else None
        if slug and f"{slug}/VolumesMetadata.json" not in rels:
            rels.append(f"{slug}/VolumesMetadata.json")
        for u in item.get("cap_urls") or []:
            m = _URL.match(u)
            if not m or m.group(1) == "ReportersMetadata.json":  # ReportersMetadata is committed under data/cap/
                continue
            rel = m.group(1)
            slug = rel.split("/", 1)[0]
            for r in (f"{slug}/VolumesMetadata.json", rel):
                if r not in rels:
                    rels.append(r)
    return rels


def listed(cap: CapClient, rel: str) -> bool:
    """False when the volume index (already cached) does not list this volume: an Absent answer needing no fetch."""
    parts = rel.split("/")
    if len(parts) < 3:
        return True
    try:
        vols = cap.volumes(parts[0])
    except CorpusUnavailable:
        return True
    return vols is None or int(parts[1]) in vols


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--dry-run", action="store_true", help="list what would be fetched")
    args = ap.parse_args()
    cache = DiskCache(write_dir=SEED_CACHE, read_dirs=[SEED_CACHE])
    cap = CapClient(cache=cache, offline=False)
    rels = needed_paths(cap)
    missing = [r for r in rels if not cache.has(r) and not cache.is_absent(r)]
    print(f"{len(rels)} files needed; {len(rels) - len(missing)} present; {len(missing)} missing")
    for r in missing:
        print(f"  {'would fetch' if args.dry_run else 'fetching'} {CAP_BASE}/{r}")
    if args.dry_run or not missing:
        return 0
    failed = 0
    # volume indexes first, so unlisted volumes (V > Vmax: us/600, us/603) are answered from the index without a fetch
    missing.sort(key=lambda r: (0 if r.endswith("VolumesMetadata.json") else 1))
    for r in missing:
        if not listed(cap, r):
            print(f"  absent per the volume index (no fetch) {r}")
            continue
        parts = r.split("/")
        try:
            if parts[-1] == "VolumesMetadata.json":
                res = cap.volumes(parts[0])
            elif parts[-1] == "CasesMetadata.json":
                res = cap.cases_in_volume(parts[0], int(parts[1]))
            else:
                res = cap.case_json(parts[0], int(parts[1]), parts[-1].removesuffix(".json"))
        except CorpusUnavailable as exc:
            failed += 1
            print(f"  FAILED {r}: {exc.reason}")
            continue
        state = "absent (404 marker)" if res is None else "ok"
        print(f"  {state} {r}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
