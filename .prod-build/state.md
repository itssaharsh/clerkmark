# Build state - Clerkmark (cite-intake)
Updated: 2026-09-26 11:35 EDT | mode: hackathon | channel: direct | phase: 5-build (M1 wave 2b)

## Now
- Phase / current task: M1 wave 2b — T05 (orchestrator, FastAPI, demo world; port 8000) || T06 (Clerkmark memo UI; static on 8765) as parallel lanes with lane ledgers; no commits from lanes.
- Last good commit: cba68fe (plan: start T05 T06); T02 T03 T04 done (E0010–E0015, 292 tests)            Last good deploy: none (user deploys to Vercel at T11)

## What worked (with evidence IDs)
- T01 contracts: models parse the UI fixture (E0003).
- T02 corpus client (E0010/E0011), T03 extraction+quotes (E0012/E0013), T04 rule engine (E0014/E0015): 292 passed, 1 skipped.
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
When wave 2b reports land: canonical `pb.py verify T05` / `T06` (T06 verify needs the static server; the observe item needs `pb.py evidence add --method observed`), intake, `task done`, commit per task. Then write the T07 brief (limits, verify.sh, check_readme.sh, vercel.json, Procfile, CI), `task start T07`, run it; then T08 QA gate, T09 review+security, T10 docs, T11 deploy steps.