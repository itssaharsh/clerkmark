"""Memo-level: when the advisory provider answers only some quoted rows, the memo says so in warnings."""
import os

import pytest

from citememo import memo as memo_mod


class _Text:
    type = "text"

    def __init__(self, text):
        self.text = text


class _Resp:
    def __init__(self, text):
        self.content = [_Text(text)]
        self.stop_reason = None


class _FlakyMessages:
    def __init__(self):
        self.n = 0

    def create(self, **kwargs):
        self.n += 1
        if self.n == 1:
            return _Resp('{"verdict": "supports", "why": "first row answered"}')
        raise RuntimeError("429 quota")


class _FlakyClient:
    default_model = "fake-model"
    max_calls = 6

    def __init__(self):
        self.messages = _FlakyMessages()


@pytest.fixture(autouse=True)
def _offline(monkeypatch):
    monkeypatch.setenv("CITEMEMO_OFFLINE", "1")
    monkeypatch.setenv("CITEMEMO_ADVISORY_CONCURRENCY", "1")


def test_partial_advisory_adds_a_warning_and_never_changes_classes():
    text = open(os.path.join("seed", "sample-motion.txt"), encoding="utf-8").read()
    plain = memo_mod.run_memo(text=text, filename="sample-motion.txt")
    flaky = memo_mod.run_memo(text=text, filename="sample-motion.txt", advisory_client=_FlakyClient())
    assert [r.class_ for r in plain.results] == [r.class_ for r in flaky.results]
    answered = [r for r in flaky.results if r.advisory is not None]
    assert len(answered) == 1 and answered[0].advisory.verdict == "supports"
    assert flaky.sources_used.advisory is True
    assert any(w.startswith("Advisory answered 1 of") for w in flaky.warnings), flaky.warnings
    assert flaky.counts.likely_fabricated == plain.counts.likely_fabricated == 3
