"""Gemini provider for the advisory column: duck-typed over the Anthropic-shaped client (mocked HTTP)."""
import json

import httpx

from citememo import advisory
from citememo.models import Advisory


def _gemini_ok(text: str, finish: str = "STOP"):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1beta/models/gemini-3.5-flash-lite:generateContent")
        assert request.url.params.get("key") == "fake-gemini-key"
        body = json.loads(request.content)
        assert body["generationConfig"]["responseMimeType"] == "application/json"
        assert "thinkingConfig" not in body["generationConfig"]
        assert "Citation:" in body["contents"][0]["parts"][0]["text"]
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": text}]}, "finishReason": finish}]})
    return httpx.MockTransport(handler)


def test_provider_prefers_gemini_then_anthropic():
    assert advisory.provider({"GEMINI_API_KEY": "x"}) == "gemini"
    assert advisory.provider({"GOOGLE_GENERATIVE_AI_API_KEY": "x"}) == "gemini"
    assert advisory.provider({"ANTHROPIC_API_KEY": "x"}) == "anthropic"
    assert advisory.provider({"GEMINI_API_KEY": " ", "ANTHROPIC_API_KEY": ""}) is None
    assert advisory.advisory_enabled({"GOOGLE_API_KEY": "k"}) is True


def test_gemini_client_returns_a_verdict():
    client = advisory.GeminiClient("fake-gemini-key", transport=_gemini_ok('{"verdict": "supports", "why": "It says so."}'))
    resp = client.messages.create(model="gemini-3.5-flash-lite", max_tokens=300, system=advisory.SYSTEM,
                                  messages=[{"role": "user", "content": "Citation: X\n\nQuoted passage"}])
    text = "".join(b.text for b in resp.content)
    verdict = advisory.parse_verdict(text, "gemini-3.5-flash-lite")
    assert isinstance(verdict, Advisory) and verdict.verdict == "supports" and verdict.model == "gemini-3.5-flash-lite"


def test_gemini_safety_block_reads_as_refusal():
    client = advisory.GeminiClient("fake-gemini-key", transport=_gemini_ok("", finish="SAFETY"))
    resp = client.messages.create(model="gemini-3.5-flash-lite", max_tokens=300, system="s", messages=[{"role": "user", "content": "Citation: X"}])
    assert resp.stop_reason == "refusal"


def test_gemini_http_error_leaves_advisory_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "quota"}})
    client = advisory.GeminiClient("fake-gemini-key", transport=httpx.MockTransport(handler))
    assert advisory._ask(client, "gemini-3.5-flash-lite", "prop", "quote", "cite") is None


def test_run_advisory_uses_the_gemini_default_model(monkeypatch):
    from citememo.models import CitationResult
    seen = {}
    def handler(request: httpx.Request) -> httpx.Response:
        seen["path"] = request.url.path
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"verdict":"cannot_tell","why":"short"}'}]}, "finishReason": "STOP"}]})
    client = advisory.GeminiClient("fake-gemini-key", transport=httpx.MockTransport(handler))
    row = CitationResult.model_validate({
        "row": 1, "cite_text": "Air France v. Saks, 470 U.S. 392 (1985)", "class": "verified", "label": "Found.",
        "reasons": [], "evidence": {}, "source": "CAP", "pincite_unverified": False, "advisory": None,
        "citation": {"kind": "full", "text": "Air France v. Saks, 470 U.S. 392 (1985)", "span": [0, 10], "volume": "470",
                     "reporter": "U.S.", "page": "392", "quotes": ["an unexpected or unusual event"]},
    })
    out, elapsed = advisory.run_advisory([row], "Air France v. Saks, 470 U.S. 392 (1985)", client=client)
    assert elapsed is not None and out[0].advisory is not None and out[0].advisory.model == "gemini-3.5-flash-lite"
    assert seen["path"].endswith("gemini-3.5-flash-lite:generateContent")


def test_gemini_retries_on_429_then_succeeds(monkeypatch):
    monkeypatch.setattr(advisory, "RETRY_DELAYS_S", (0.0, 0.0))
    calls = {"n": 0}
    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] < 3:
            return httpx.Response(429 if calls["n"] == 1 else 503, json={"error": {"message": "quota"}})
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"verdict":"supports","why":"ok"}'}]}, "finishReason": "STOP"}]})
    client = advisory.GeminiClient("fake-gemini-key", transport=httpx.MockTransport(handler))
    v = advisory._ask(client, "gemini-3.5-flash-lite", "prop", "quote", "cite")
    assert v is not None and v.verdict == "supports" and calls["n"] == 3


def test_run_advisory_caps_calls_and_keeps_order():
    from citememo.models import CitationResult
    seen = []
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(1)
        return httpx.Response(200, json={"candidates": [{"content": {"parts": [{"text": '{"verdict":"cannot_tell","why":"x"}'}]}, "finishReason": "STOP"}]})
    client = advisory.GeminiClient("fake-gemini-key", transport=httpx.MockTransport(handler))
    def row(i):
        return CitationResult.model_validate({
            "row": i, "cite_text": f"Case {i}, 470 U.S. 392 (1985)", "class": "verified", "label": "Found.", "reasons": [],
            "evidence": {}, "source": "CAP", "pincite_unverified": False, "advisory": None,
            "citation": {"kind": "full", "text": f"Case {i}", "span": [0, 5], "volume": "470", "reporter": "U.S.", "page": "392", "quotes": ["a quoted passage of some length"]}})
    rows = [row(i) for i in range(1, 9)]
    out, elapsed = advisory.run_advisory(rows, "text", client=client, max_calls=3)
    assert len(seen) == 3 and [r.row for r in out] == list(range(1, 9))
    assert [r.advisory is not None for r in out] == [True, True, True, False, False, False, False, False]
