"""Gemini provider for the advisory column: duck-typed over the Anthropic-shaped client (mocked HTTP)."""
import json

import httpx

from citememo import advisory
from citememo.models import Advisory


def _gemini_ok(text: str, finish: str = "STOP"):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path.endswith("/v1beta/models/gemini-3.8-flash:generateContent")
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
    resp = client.messages.create(model="gemini-3.8-flash", max_tokens=300, system=advisory.SYSTEM,
                                  messages=[{"role": "user", "content": "Citation: X\n\nQuoted passage"}])
    text = "".join(b.text for b in resp.content)
    verdict = advisory.parse_verdict(text, "gemini-3.8-flash")
    assert isinstance(verdict, Advisory) and verdict.verdict == "supports" and verdict.model == "gemini-3.8-flash"


def test_gemini_safety_block_reads_as_refusal():
    client = advisory.GeminiClient("fake-gemini-key", transport=_gemini_ok("", finish="SAFETY"))
    resp = client.messages.create(model="gemini-3.8-flash", max_tokens=300, system="s", messages=[{"role": "user", "content": "Citation: X"}])
    assert resp.stop_reason == "refusal"


def test_gemini_http_error_leaves_advisory_none():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, json={"error": {"message": "quota"}})
    client = advisory.GeminiClient("fake-gemini-key", transport=httpx.MockTransport(handler))
    assert advisory._ask(client, "gemini-3.8-flash", "prop", "quote", "cite") is None


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
    assert elapsed is not None and out[0].advisory is not None and out[0].advisory.model == "gemini-3.8-flash"
    assert seen["path"].endswith("gemini-3.8-flash:generateContent")
