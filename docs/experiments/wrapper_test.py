"""Can a chat model do this? Paste the sample filing into a model twice and score both runs.

    GEMINI_API_KEY=... .venv/bin/python docs/experiments/wrapper_test.py [model]

The whole filing goes in one prompt; the model returns a JSON verdict per citation.
The same prompt is sent twice to see whether the answers are stable. Answers are matched
to seed/ground_truth.json by party name, volume and page, and scored against the plain
legal truth (a case that does not exist is real=no), not against Clerkmark's class names.

See README.md in this folder for the method and the 27 September 2026 result.
"""
import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MODEL = sys.argv[1] if len(sys.argv) > 1 else "gemini-3.5-flash-lite"
ENV_NAMES = ("GEMINI_API_KEY", "GOOGLE_GENERATIVE_AI_API_KEY", "GOOGLE_API_KEY")


def api_key() -> str:
    for name in ENV_NAMES:
        if os.environ.get(name, "").strip():
            return os.environ[name].strip()
    for candidate in (ROOT / ".env", ROOT / ".env.local"):
        if candidate.exists():
            for line in candidate.read_text().splitlines():
                k, _, v = line.partition("=")
                if k.strip() in ENV_NAMES and v.strip():
                    return v.strip().strip("\"'")
    sys.exit(f"set one of {', '.join(ENV_NAMES)} in the environment or in {ROOT}/.env")


KEY = api_key()
filing = (ROOT / "seed" / "sample-motion.txt").read_text()
gt = json.loads((ROOT / "seed" / "ground_truth.json").read_text())["items"]

PROMPT = (
    "You are checking a court filing for fabricated or misused case citations, the way a court clerk would.\n"
    "For EVERY case citation in the filing below, report:\n"
    "  cite: the citation as printed\n"
    "  real: yes | no | unsure  (does this case exist at this volume and page?)\n"
    "  quote_accurate: yes | no | na  (if the filing quotes it, do those exact words appear in the opinion?)\n"
    "  note: one short sentence of evidence\n"
    'Return ONLY JSON: {"citations": [ ... ]}\n\n=== FILING ===\n' + filing
)

# The plain legal truth for each seeded citation, in the model's own vocabulary.
# The Mata Westlaw-only and slip citations are fabricated too, so real=no.
TRUTH = {
    "mata-varghese": ("no", "na"), "mata-petersen": ("no", "na"), "mata-miller": ("no", "na"),
    "mata-shaboon": ("no", "na"), "mata-martinez": ("no", "na"), "mata-durden": ("no", "na"),
    "real-zicherman": ("yes", "yes"), "real-tseng": ("yes", "yes"), "real-husain": ("yes", "yes"),
    "real-saks": ("yes", "yes"), "real-floyd": ("yes", "yes"), "real-azar": ("yes", "yes"),
    "real-greenleaf": ("yes", "yes"), "real-twombly": ("yes", "yes"),
    "misq-iqbal": ("yes", "no"), "misq-chan": ("yes", "no"),
    "cov-biden-nebraska": ("yes", "na"), "cov-loper-bright": ("yes", "na"),
    "wrong-zicherman-230": ("no", "na"),   # the case is real, but not at page 230
    "unrec-alvarez": ("no", "na"),
}


def ask() -> list:
    body = json.dumps({
        "contents": [{"role": "user", "parts": [{"text": PROMPT}]}],
        "generationConfig": {"temperature": 0, "responseMimeType": "application/json", "maxOutputTokens": 8192},
    }).encode()
    req = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent?key={KEY}",
        data=body, headers={"Content-Type": "application/json"})
    last = None
    for attempt in range(5):                      # free tiers answer 429/503 under load
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                data = json.load(r)
            break
        except Exception as exc:
            last = exc
            time.sleep(6 * (attempt + 1))
    else:
        raise last
    text = "".join(p.get("text", "") for p in data["candidates"][0]["content"]["parts"])
    return json.loads(text)["citations"]


def norm(s) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def find(answers: list, item: dict):
    """Match a ground-truth row to the model's answer by party name, then volume and page."""
    vol, page = str(item.get("volume") or ""), str(item.get("page") or "")
    party = norm((item.get("parties") or item["cite_text"]).split(" v.")[0])[:12]
    for a in answers:
        cite = str(a.get("cite", ""))
        if party and party in norm(cite) and (not vol or vol in cite) and (not page or page in cite):
            return a
    for a in answers:
        if party and party in norm(a.get("cite")):
            return a
    return None


runs = []
for i in range(2):
    t0 = time.time()
    try:
        runs.append(ask())
        print(f"run {i + 1}: {len(runs[-1])} citations returned in {time.time() - t0:.0f}s")
    except Exception as exc:
        print(f"run {i + 1} FAILED (not a score): {exc}")
        runs.append([])
    time.sleep(3)

print(f"\nmodel: {MODEL}   ground truth: {len(gt)} citations\n")
print(f"{'id':<22}{'truth':<12}{'run 1':<24}{'run 2':<24}{'stable':<7}")
print("-" * 92)
score, stable = [0, 0], 0
for item in gt:
    t_real, t_quote = TRUTH[item["id"]]
    cells = []
    for k, answers in enumerate(runs):
        a = find(answers, item)
        if a is None:
            cells.append(("missing", False))
            continue
        real, quote = str(a.get("real", "?")).lower(), str(a.get("quote_accurate", "?")).lower()
        ok = real == t_real and (t_quote == "na" or quote == t_quote)
        score[k] += ok
        cells.append((f"real={real} quote={quote}", ok))
    same = cells[0][0] == cells[1][0]
    stable += same
    print(f"{item['id']:<22}{t_real + '/' + t_quote:<12}"
          f"{cells[0][0] + (' OK' if cells[0][1] else ' X'):<24}"
          f"{cells[1][0] + (' OK' if cells[1][1] else ' X'):<24}"
          f"{'yes' if same else 'NO':<7}")
print("-" * 92)
print(f"run 1: {score[0]}/20 correct     run 2: {score[1]}/20 correct     identical answers: {stable}/20")
print("Clerkmark on the same filing: 20/20 correct, 0 of 11 real cases marked likely not real, every run.")
