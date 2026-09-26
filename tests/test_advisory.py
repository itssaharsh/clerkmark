"""AC-16: the optional advisory pass (citememo/advisory.py) with a mocked Anthropic client.

The advisory never changes a class, runs only for verified rows with a quote, makes at
most 20 calls per memo, and is None (not run) without an API key or when the model's
reply is not the JSON {verdict, why} it was asked for.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from citememo import advisory
from citememo.models import CitationInput, CitationResult, QuoteCheck

ROOT = Path(__file__).resolve().parents[1]
SAMPLE_TXT = (ROOT / "seed" / "sample-motion.txt").read_text()


class FakeMessages:
    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        reply = self.replies.pop(0) if self.replies else json.dumps({"verdict": "supports", "why": "It says so."})
        if isinstance(reply, Exception):
            raise reply
        return SimpleNamespace(
            content=[SimpleNamespace(type="text", text=reply)],
            stop_reason="end_turn",
            model=kwargs.get("model"),
        )


class FakeClient:
    def __init__(self, replies=()):
        self.messages = FakeMessages(replies)


def verified_row(row: int, quote: str, text: str = "470 U.S. 392") -> CitationResult:
    return CitationResult(
        row=row,
        cite_text=f"Case {row} v. Other, {text} (1985)",
        class_="verified",
        reasons=["Found in the free corpus: Air France v. Saks, 470 U.S. 392 (Supreme Court of the United States, 1985-03-04)."],
        source="CAP",
        quote_check=QuoteCheck(status="verbatim", quote=quote, similarity=100.0),
        citation=CitationInput(text=text, volume=470, reporter="U.S.", page=392, quotes=[quote], span=(100, 112)),
    )


QUOTE = "Any injury is the product of a chain of causes, and we require only that the passenger be able to prove that some link in the chain was an unusual or unexpected event external to the passenger."


def test_not_enabled_without_key(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    assert advisory.advisory_enabled() is False
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    assert advisory.advisory_enabled() is True
    monkeypatch.setenv("ANTHROPIC_API_KEY", "   ")
    assert advisory.advisory_enabled() is False


def test_no_client_means_not_run(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    rows = [verified_row(1, QUOTE)]
    out, elapsed = advisory.run_advisory(rows, SAMPLE_TXT, client=None)
    assert out[0].advisory is None
    assert elapsed is None


def test_verified_rows_with_quotes_get_a_verdict_and_keep_their_class():
    fake = FakeClient([
        json.dumps({"verdict": "supports", "why": "The passage states the chain-of-causes test."}),
        json.dumps({"verdict": "does_not_support", "why": "The passage is about mootness, not the proposition."}),
    ])
    rows = [
        verified_row(1, QUOTE),
        verified_row(2, "Once the district court deems a Rule 23 class valid, the subsequent mootness of individual claims does not terminate litigation.", "925 F.3d 1291"),
        CitationResult(row=3, cite_text="No Quote v. Here, 516 U.S. 217 (1996)", class_="verified", reasons=["Found."], source="CAP"),
        CitationResult(row=4, cite_text="Miller v. United Airlines, Inc., 174 F.3d 366 (2d Cir. 1999)", class_="likely_fabricated", reasons=["Page 366 belongs to Greenleaf."],
                       citation=CitationInput(text="174 F.3d 366", quotes=["a quoted passage that is long enough to count here"])),
    ]
    before = [r.class_ for r in rows]
    out, elapsed = advisory.run_advisory(rows, SAMPLE_TXT, client=fake, model="claude-haiku-4-5-20251001")
    assert [r.class_ for r in out] == before
    assert elapsed is not None and elapsed >= 0
    assert out[0].advisory.verdict == "supports"
    assert out[0].advisory.why.startswith("The passage states")
    assert out[0].advisory.model == "claude-haiku-4-5-20251001"
    assert out[1].advisory.verdict == "does_not_support"
    assert out[1].class_ == "verified"  # never changes the class
    assert out[2].advisory is None  # no quote
    assert out[3].advisory is None  # not verified
    assert len(fake.messages.calls) == 2
    call = fake.messages.calls[0]
    assert call["model"] == "claude-haiku-4-5-20251001"
    assert QUOTE in json.dumps(call["messages"])
    assert call["max_tokens"] >= 100


def test_malformed_json_and_errors_give_none():
    fake = FakeClient([
        "I think it supports the claim.",  # not JSON
        json.dumps({"verdict": "maybe", "why": "?"}),  # verdict outside the literal
        RuntimeError("boom"),  # SDK / network error
        json.dumps({"verdict": "cannot_tell", "why": "The proposition is not stated near the quote."}),
    ])
    rows = [verified_row(i, QUOTE) for i in range(1, 5)]
    out, _ = advisory.run_advisory(rows, SAMPLE_TXT, client=fake)
    assert out[0].advisory is None
    assert out[1].advisory is None
    assert out[2].advisory is None
    assert out[3].advisory.verdict == "cannot_tell"
    assert all(r.class_ == "verified" for r in out)


def test_json_inside_prose_is_parsed():
    fake = FakeClient(['Here is my answer:\n```json\n{"verdict": "supports", "why": "Yes."}\n```'])
    out, _ = advisory.run_advisory([verified_row(1, QUOTE)], SAMPLE_TXT, client=fake)
    assert out[0].advisory.verdict == "supports"


def test_at_most_twenty_calls_per_memo():
    fake = FakeClient()
    rows = [verified_row(i, QUOTE) for i in range(1, 26)]
    out, _ = advisory.run_advisory(rows, SAMPLE_TXT, client=fake)
    assert len(fake.messages.calls) == 20
    assert sum(1 for r in out if r.advisory is not None) == 20
    assert all(r.advisory is None for r in out[20:])


def test_proposition_is_the_filing_sentence_around_the_quote():
    row = verified_row(1, QUOTE)
    span_start = SAMPLE_TXT.index("470 U.S. 392")
    row = row.model_copy(update={"citation": row.citation.model_copy(update={"span": (span_start, span_start + 12)})})
    prop = advisory.proposition_for(row, SAMPLE_TXT)
    assert "accident" in prop.lower()
    assert len(prop) <= 1200


def test_memo_integration_with_mocked_client(monkeypatch):
    monkeypatch.setenv("CITEMEMO_OFFLINE", "1")
    from citememo import memo as memo_mod

    fake = FakeClient()
    text = (
        'The Court said: "Any injury is the product of a chain of causes, and we require only that the passenger be able to '
        'prove that some link in the chain was an unusual or unexpected event external to the passenger." Air France v. Saks, 470 U.S. 392 (1985).'
    )
    memo = memo_mod.run_memo(text=text, filename="pasted-text", advisory_client=fake)
    assert memo.results[0].class_ == "verified"
    assert memo.results[0].advisory is not None
    assert memo.results[0].advisory.verdict == "supports"
    assert memo.sources_used.advisory is True
    assert memo.stage_timings_ms.advisory is not None
    assert len(fake.messages.calls) == 1

    memo2 = memo_mod.run_memo(text=text, filename="pasted-text")
    assert memo2.results[0].advisory is None
    assert memo2.sources_used.advisory is False
    assert memo2.stage_timings_ms.advisory is None
