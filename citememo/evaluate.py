"""The 20-citation evaluation (AC-1, AC-11): a Memo against ``seed/ground_truth.json``.

``evaluate(memo, ground_truth=None) -> EvalReport``
    Matches every scored ground-truth item (``items[]``; the page-1 label cite in
    ``extra_in_label`` and skipped rows are not scored) to a memo row by
    ``cite_text`` (whitespace-normalised; falls back to volume/reporter/page), and
    counts a row correct when its class is in the item's ``accepted_classes``.
    ``real_cases_marked_fabricated`` counts rows that cite a real case (ground
    truth has ``real_case_at_page`` and the item is not itself a known
    fabrication) yet were predicted ``likely_fabricated``. The target is 0.

``load_ground_truth(path=None) -> dict``
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Optional

from .models import CitationResult, EvalReport, EvalRow, Memo

ROOT = Path(__file__).resolve().parents[1]
GROUND_TRUTH_PATH = ROOT / "seed" / "ground_truth.json"


def load_ground_truth(path: Optional[Path] = None) -> dict:
    return json.loads((path or GROUND_TRUTH_PATH).read_text(encoding="utf-8"))


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "")).strip().lower()


def is_real_case(item: dict) -> bool:
    """The cited case is real: ground truth names a case at the cited page and the item is not a known fabrication.

    A fabricated citation that happens to land on another case's first page (Petersen,
    905 F. Supp. 2d 121) is not a real case; counting it would make the target of 0
    contradict its own expected class.
    """
    return item.get("real_case_at_page") is not None and item.get("expected_class") != "likely_fabricated"


def _match(item: dict, rows: list[CitationResult]) -> Optional[CitationResult]:
    want = _norm(item["cite_text"])
    for r in rows:
        if _norm(r.cite_text) == want:
            return r
    for r in rows:
        c = r.citation
        if c is not None and c.volume == item.get("volume") and c.page == item.get("page") and _norm(c.reporter or "") == _norm(item.get("reporter", "")):
            return r
    return None


def evaluate(memo: Memo, ground_truth: Optional[dict] = None) -> EvalReport:
    gt = ground_truth or load_ground_truth()
    items = [i for i in gt["items"] if i.get("expected_class")]
    rows: list[EvalRow] = []
    expected: Counter = Counter()
    predicted: Counter = Counter()
    correct = 0
    real_total = 0
    real_red = 0
    for item in items:
        accepted = list(item.get("accepted_classes") or [item["expected_class"]])
        hit = _match(item, memo.results)
        pred = hit.class_ if hit is not None else None
        ok = pred is not None and pred in accepted
        real = is_real_case(item)
        real_total += int(real)
        if real and pred == "likely_fabricated":
            real_red += 1
        correct += int(ok)
        expected[item["expected_class"]] += 1
        if pred is not None:
            predicted[pred] += 1
        rows.append(
            EvalRow(
                id=item["id"],
                line=hit.row if hit is not None else None,
                cite_text=item["cite_text"],
                expected=item["expected_class"],
                accepted=accepted,
                predicted=pred,
                ok=ok,
                reason=(hit.reasons[0] if hit is not None and hit.reasons else None),
                real_case=real,
            )
        )
    total = len(rows)
    return EvalReport(
        rows=rows,
        correct=correct,
        total=total,
        accuracy=(correct / total) if total else 0.0,
        real_cases_marked_fabricated=real_red,
        real_total=real_total,
        per_class={"expected": dict(expected), "predicted": dict(predicted)},
        elapsed_ms=memo.elapsed_ms,
        stage_timings_ms=memo.stage_timings_ms,
        run_id=memo.run_id,
        run_created_at=memo.created_at,
        offline=memo.offline,
        replay=memo.replay,
    )


__all__ = ["GROUND_TRUTH_PATH", "evaluate", "is_real_case", "load_ground_truth"]
