# Build state - Clerkmark (cite-intake)
Updated: 2026-09-26 11:35 EDT | mode: hackathon | channel: direct | phase: 5-build (M2: T08 QA gate)

## Now
- Phase / current task: M2 — T08 QA gate (server on 8020; qa.mjs live; demo flow ×3; skeptical evaluator) running as a single lane.
- Last good commit: T07 committed (E0033–E0035: 334 tests; verify.sh PASS 20/20, 0 real red)            Last good deploy: none (user deploys at T11)

## What worked (with evidence IDs)
- T01 contracts: models parse the UI fixture (E0003).
- T02 corpus client (E0010/E0011), T03 extraction+quotes (E0012/E0013), T04 rule engine (E0014/E0015): 292 passed, 1 skipped.
- T07 limits/degrade/verify.sh/vercel.json/Procfile/CI (E0033–E0035). Known: docs/API.md says 15 MB and UI-SPEC 20 MB (contract: 4 MB) → T10; models.ErrorCode lacks rate_limited (envelope built by hand) → T09 may add it.
- T05 orchestrator/API/demo world: live sample 3.9 s, offline eval 20/20, seed/replay.json recorded 2026-09-26T16:28Z (E0016–E0018, 323 tests). T06 memo UI: qa.mjs static PASS, axe 0, print 1 page (E0019–E0021). Key paths: main.py, citememo/memo.py, web/static/app.js, qa/qa.mjs, seed/replay.json.
- Upstream: docs/UI-SPEC.md, docs/DECISION-RULE.md, seed/ (20 verified citations, PDF, CAP cache) from the design workflow.

## What failed (memory IDs) - do not retry without a new root cause
- E0002: whole-suite pytest exits 5 with no tests; T01 opted out of the suite (suite:false). Not a bug.
- Earlier build workflow (wf_c2a47723-c6b) died with the session after the contracts agent; rebuilt as pb.py tasks.

## Not tried yet / open questions
- CourtListener token (optional; user's account). Anthropic key (optional).
- Deploy account: the user runs `vercel deploy` (T11).

## Changes that need care (migrations applied, deploys, destructive ops)
- none

## Exact next step
When T08 reports: `pb.py verify T08` needs the server on 8020 (start it: CITEMEMO_OFFLINE=1 .venv/bin/python -m uvicorn main:app --port 8020), intake, `task T08 done`, commit "T08: …". Then `task start T09` (review + security + adversarial; may add models.ErrorCode rate_limited), then T10 docs + DELIVERY.md, then T11 handoff (user deploys; pb.py smoke).