# Build state - Clerkmark (cite-intake)
Updated: 2026-09-27 07:05 EDT | mode: hackathon | channel: direct | phase: 12-delivered (T11 deploy pending on the user)

## Now
- Phase / current task: T01–T10 done with canonical evidence (E0001–E0047). T11 (release deploy + live verification) needs the user's Vercel account; steps in docs/SUBMISSION-CHECKLIST.md.
- Last good commit: see `git log -1`            Last good deploy: none yet

## What worked (with evidence IDs)
- Suite 380 passed, 1 skipped (E0040/E0041). Offline demo proof `scripts/verify.sh` PASS 20/20, 0 real red (E0042). Eval 20/20 (E0017). QA gate axe 0, demo ×3 identical (E0039, E0043). Security review 6 blocking fixed (E0044). README check (E0045), DELIVERY report (E0047).
- Key paths: main.py, citememo/{memo,rules,names,extract,quotes,cap,limits}.py, web/static/app.js, seed/replay.json, scripts/verify.sh, qa/qa.mjs, README.md, DEVPOST.md, docs/VIDEO-SCRIPT.md, docs/SUBMISSION-CHECKLIST.md.

## What failed (memory IDs) - do not retry without a new root cause
- F-0001 eyecite span/year overshoot; F-0002 per-volume rescans; F-0003 WSL2 clock; F-0004 lane ledgers share logs/ and ids.

## Not tried yet / open questions
- Live CourtListener and Anthropic paths (mocked only). Sample endpoint uncached (T09 finding 8). Popular-name captions read amber (finding 10).

## Changes that need care
- none (no deploy yet; no secrets committed)

## Exact next step
User: push to GitHub, import into Vercel (zero config), run `python3 .prod-build/pb.py smoke <url> --routes / /api/health /api/samples`, then the incognito checks in docs/SUBMISSION-CHECKLIST.md; record the video from docs/VIDEO-SCRIPT.md; fill DEVPOST.md into the form. Then `pb.py task T11 done` with the smoke evidence.
