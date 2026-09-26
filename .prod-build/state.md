# Build state - Clerkmark (cite-intake)
Updated: 2026-09-26 11:35 EDT | mode: hackathon | channel: direct | phase: 5-build (M1 wave 2a)

## Now
- Phase / current task: M1 wave 2a — T02 (corpus client) || T03 (extraction+quotes) || T04 (rule engine) running as parallel single-writer lanes with lane ledgers evidence.T0x.jsonl; no commits from lanes.
- Last good commit: 163f8fb (plan: start T02 T03 T04)            Last good deploy: none (user deploys to Vercel at T11)

## What worked (with evidence IDs)
- T01 contracts: models parse the UI fixture (E0003).
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
When wave 2a reports land: for each of T02/T03/T04 run canonical `python3 .prod-build/pb.py verify Txx --keep-going`, `pb.py intake Txx`, then `task Txx done`, commit "Txx: ...". Then `task start T05 T06`, commit, launch wave 2b (T05 || T06). Then T07 (limits, verify.sh, deploy config, CI), T08 QA gate, T09 review+security, T10 docs, T11 deploy steps.
