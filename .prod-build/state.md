# Build state - Clerkmark (cite-intake)
Updated: 2026-09-27 07:25 EDT | mode: hackathon | channel: direct | phase: 12-delivered (all 12 tasks done; deployed)

## Now
- Phase / current task: T01–T10 done with canonical evidence (E0001–E0047). T11 (release deploy + live verification) needs the user's Vercel account; steps in docs/SUBMISSION-CHECKLIST.md.
- Last good commit: see `git log -1` (pushed to https://github.com/itssaharsh/clerkmark)            Last good deploy: https://clerkmark.vercel.app (E0052, E0056, E0058)

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
User: record the video (docs/VIDEO-SCRIPT.md), paste VIDEO_URL into README.md and DEVPOST.md, fill the Devpost form from DEVPOST.md, incognito check of https://clerkmark.vercel.app. Optional: COURTLISTENER_TOKEN on Vercel (courtlistener.com/profile/api/), then redeploy.