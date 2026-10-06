# Experiments

## wrapper_test.py — can a chat model do this?

The fair objection to Clerkmark is that a user could paste the same filing into a chat
model and get the same answers. This test measures that instead of arguing about it.

**Method.** The whole synthetic sample filing (`seed/sample-motion.txt`, 20 scored
citations) goes into the model in one prompt, which asks for a JSON verdict per
citation: `real` (yes / no / unsure) and `quote_accurate` (yes / no / na). The same
prompt is sent twice, unchanged, at temperature 0, to see whether the answers are
stable. Each answer is matched to its ground-truth row in `seed/ground_truth.json` by
party name, volume and page.

The ground truth here is the plain legal truth, not Clerkmark's class vocabulary. A case
that does not exist is `real=no`, including the three Westlaw-only and slip citations
that Clerkmark can only report as "not in the free library".

**Run it:**

```
GEMINI_API_KEY=... .venv/bin/python docs/experiments/wrapper_test.py gemini-3.5-flash-lite
```

A heavier model may answer 429 or 503 on a free tier. The script retries with backoff and
reports a failed call as a failure, never as a score.

**Result, 27 September 2026, `gemini-3.5-flash-lite`, temperature 0:**

| | Correct of 20 |
|---|---|
| Model, run 1 | 16 |
| Model, run 2 | 15 |
| Answers identical across the two runs | 15 of 20 |
| Clerkmark (`scripts/eval.py --offline`) | 20 of 20, unchanged every run |

What the model got wrong matters more than the score:

- It called the fabricated *Miller v. United Airlines, Inc.*, 174 F.3d 366 a real case in
  both runs, and in run 1 said its quote was accurate.
- It called *Varghese v. China Southern Airlines Co.*, 925 F.3d 1339 fake in run 1 and
  real in run 2, from an identical prompt at temperature 0.
- It confirmed both deliberately altered quotes (*Iqbal*, *Chan*) as accurate. It cannot
  compare words against an opinion it has not read.
- It missed that page 230 is not where *Zicherman* begins.

Where the model beat Clerkmark: it correctly called the three Westlaw-only and slip
citations fabricated, which Clerkmark can only report as "not in the free library",
because its corpus does not index them. That gap is stated on the site and in the README.

**Caveat.** This model had no web search or tool use. A grounded model would score
higher. The differences that survive grounding are determinism, evidence the reader can
open, and the one judgement no model can make from training data: whether a citation is
missing because it was invented or because the free corpus stops in 2019. That is a fact
about corpus coverage, not about law.
