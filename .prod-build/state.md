# Build state - Clerkmark (cite-intake)
Updated: 2026-09-26 11:35 EDT | mode: hackathon | channel: direct | phase: 5-build (M2: T07)

## Now
- Phase / current task: M2 — T07 (limits, degrade, scripts/verify.sh, vercel.json, Procfile, CI) running as a single lane on the main ledger.
- Last good commit: 99ff133 (plan: start T07); M1 complete: T05 (E0016–E0018: 31 tests, eval 20/20, 0 real red), T06 (E0019–E0021: axe 0, observed stills)            Last good deploy: none (user deploys at T11)

## What worked (with evidence IDs)
- T01 contracts: models parse the UI fixture (E0003).
- T02 corpus client (E0010/E0011), T03 extraction+quotes (E0012/E0013), T04 rule engine (E0014/E0015): 292 passed, 1 skipped.
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
When T07 reports: `pb.py verify T07`, intake, `task T07 done`, commit "T07: …". Then `task start T08` and run the QA gate brief (server on 8020); then T09 review+security; T10 docs + DELIVERY.md; T11 = user deploys (steps in docs/SUBMISSION-CHECKLIST.md), then `pb.py smoke <url>`.
Known doc debt: DECISION-RULE §7 "contains" column vs UI-SPEC §9 sentences (T04 concern); contract J3 says "0 of 12" but the eval counts 11 real cases (T05 ruling 3) — fix the contract line in T10.