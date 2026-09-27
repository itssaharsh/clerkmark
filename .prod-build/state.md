# Build state - Clerkmark (cite-intake)
Updated: 2026-09-26 11:35 EDT | mode: hackathon | channel: direct | phase: 5-build (M2: T08 resume || T09)

## Now
- Phase / current task: Sunday 05:50 EDT, deadline 17:00 EDT. T08 QA gate RESUMED (first agent hit the Fable usage limit mid-task; partial diffs kept in qa/qa.mjs, app.js, qa/demo-flow.mjs; server on 8020) || T09 review+security restricted to backend files (server 8030); lane ledgers evidence.T08/T09.jsonl; subagents on opus to avoid the limit.
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
When both report: canonical `pb.py verify T08` (server on 8020 must be up) and `pb.py verify T09`, intake, task done, commit per task (T08: qa/ web/; T09: citememo main.py tests scripts). Then `task start T10`, run the docs/submission agent (README, DEVPOST.md, VIDEO-SCRIPT.md, SUBMISSION-CHECKLIST.md, LICENSE, DELIVERY.md; fix docs/API.md 15 MB→4 MB and UI-SPEC 20 MB→4 MB, add rate_limited to API.md). Then the T11 handoff to the user (deploy steps, smoke). Hard stop for my work: 10:00 EDT so the user has 7 h for deploy, video and the form.