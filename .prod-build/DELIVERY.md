# Delivery report — Clerkmark (hackathon, 2026-09-27)

Evidence ids (E0xxx) refer to the canonical ledger `.prod-build/evidence.jsonl`. This task (T10) ran its checks on the lane ledger `.prod-build/evidence.T10.jsonl`, whose ids restart at E0001; lane runs are written as "T10 lane #n" so they are not mistaken for canonical ids. The orchestrator's canonical `pb.py verify T10` will give them canonical ids.

## Built
- J1 sample run: `/` with "Use the sample filing" and `?demo=1` → `POST /api/memo/sample/sample-motion` → the memo: 23 rows in filing order with plain labels, rule sentences, red-pen and pencil marks, [Show the page] (running head, excerpt, CAP links) and [Show the shelf], "Read these first", CHECKED stamp with real counts and seconds; replay (Alt+Shift+P, `seed/replay.json`), reset (Alt+Shift+R, `?reset=1`), every state via `?state=`.
- J2 own filing: PDF upload or pasted text through the same pipeline; no_text_layer, unsupported_type, too_large (4 MB, 200,000 characters), rate_limited (10 memos a minute per address) and upstream failures each return an envelope, and the UI keeps the input.
- J3 Evaluation tab (`GET /api/eval`: 20 citations against `seed/ground_truth.json`) and How it works (the numbered rule, sources, live and optional parts, limits, credits).
- Optional paths: CourtListener second pass (`COURTLISTENER_TOKEN`) and the advisory column (`ANTHROPIC_API_KEY`, `claude-haiku-4-5-20251001`), both tested with mocks.
- Offline mode (`CITEMEMO_OFFLINE=1`), `scripts/verify.sh` PASS/FAIL proof, `scripts/eval.py`, CI workflow, `vercel.json` and `Procfile`.
- Submission kit (T10): README.md, DEVPOST.md, docs/VIDEO-SCRIPT.md, docs/SUBMISSION-CHECKLIST.md, LICENSE (MIT); docs/API.md now gives the 4 MB cap and the 429 `rate_limited` envelope; docs/UI-SPEC.md §9 says "larger than 4 MB".
- Cut (COULD, listed not built): statutes and court rules, pin-cite checks via CourtListener opinion text, batch or docket intake, the litigant correction kit. WON'T: accounts, stored filings, OCR, Westlaw/Lexis.

## Architecture
- One FastAPI deployable (`main.py`) serving a plain HTML/CSS/JS page and JSON under `/api/*` (ADR-0003); no database: two-level JSON cache, committed seed cache and a recorded replay (ADR-0004).
- Corpus: the Caselaw Access Project's static files, no account; CourtListener only as an optional second pass (ADR-0001).
- A deterministic classifier in `citememo/rules.py`; the LLM is advisory only, off by default, and never changes a class (ADR-0002).
- 4 MB upload cap and a 10-per-minute in-memory rate limit for the Vercel function (ADR-0005). Not built on purpose: accounts, persistence, a front-end framework.

## Verification
- T01 contracts: the pydantic models validate the front-end fixture memo (E0003).
- T02 corpus client, cache and CourtListener client (mocked HTTP): 75 passed, 1 skipped (E0010).
- T03 extraction and quote matching: 53 passed (E0012).
- T04 rule engine, including AC-2 (Varghese → likely_fabricated naming J.D. v. Azar) and AC-3 (600 U.S. 477 → not_in_free_corpus): 164 passed (E0014).
- T05 integration and advisory tests: 31 passed (E0016); offline evaluation with `--assert-min 18 --assert-no-real-red`: 20 of 20 correct, real cases marked likely not real 0 of 11, PASS (E0017). T10 lane #2 re-ran `scripts/eval.py --offline` on 2026-09-27: same 20 of 20 and 0 of 11, elapsed 4091 ms.
- T06 UI QA against the static page: axe-core 0 violations on 10 views at 1440 px, screenshots at 320/390/1024/1440, keyboard, replay, reset and print (one letter page) checks all passed (E0019); `?demo=1` at 1440 and 390 observed with the marks on the Miller and Shaboon rows and J.D. v. AZAR in the line-6 drawer (E0021).
- T07 abuse limits and outage degrade: RED first (E0022, expected failure: 9 failed, 4 passed), then 13 passed (E0023); deploy files and CI shape checked (E0027).
- Offline demo proof `scripts/verify.sh`: PASS, 20/20, 0 real cases red (E0029, E0034). T10 lane #3 re-ran `env CITEMEMO_OFFLINE=1 PORT=8040 bash scripts/verify.sh` on 2026-09-27: PASS, "citations 20 · correct 20/20 · real cases marked likely-not-real 0 · elapsed 4.0 s".
- Full suite: 334 passed, 1 skipped (E0035). T10 lane #4 re-ran `.venv/bin/python -m pytest -q` on 2026-09-27: 334 passed, 1 skipped in 90 s.
- README check (AC-14): RED while README.md did not exist (E0026, expected failure; also T10 lane #1), PASS once written (T10 lane #5).
- T08 QA gate against the running server: its first run failed (E0036, failed with 4 failures: demo title, rows rendered, the line-8 mark, an aborted assertion block); the resumed QA gate had not reported when this was written, so its result is not verified here.
- T09 fresh review and security pass: not run to completion when this report was written (pending).
- Lighthouse / LCP ≤ 2.5 s: not run (no deployed URL); command once deployed: `npx @lhci/cli autorun --collect.url=<url>/?demo=1`.

## Deployment
- Not deployed. The user deploys from their own Vercel account; the steps, the optional token and key, and the smoke command (`python3 .prod-build/pb.py smoke <url> --routes / /api/health /api/samples`) are in docs/SUBMISSION-CHECKLIST.md. AC-13 stays not verified until that smoke passes.

## Bugs found and fixed
- eyecite 2.7.8's full span ran into the next citation and its year borrowed the next citation's year (Shaboon and Floyd read 2019); fixed by anchoring on party names and a bounded year window (F-0001); extraction tests pass (E0012).
- Whole-volume rule sweeps rescanned volume data per citation (rules tests took 52 s); memoized per-volume indexes (F-0002); 164 rule tests in 34 s (E0014).
- `POST /api/memo` had no size or rate limits: RED run (E0022, expected failure) then fixed with `citememo/limits.py` (E0023).
- `scripts/verify.sh` printed a false "FAIL: elapsed 5.3 s > 5 s" on WSL2, whose monotonic clock ran fast (F-0003; that failing run was outside the ledger); the time gate is now opt-in and the script passes with a NOTE line (E0029).
- UI: the partial-state stamp overflowed at 320 and 390 px, print took 2 pages, and drawer links failed axe's target-size rule; all fixed before the passing QA run (E0019; the RED runs are #1–#4 in `.prod-build/evidence.T06.jsonl`).
- T08 QA and T09 review findings: pending, not run to completion when this report was written.
<!-- ORCHESTRATOR: fill T08/T09 findings -->

## Known limitations
- Checks case citations only: statutes, court rules, Id., supra and short forms are listed as "Not checked"; pin cites are never verified (CAP text has no page breaks).
- Westlaw-only, Lexis-only and neutral citations read "Not in the free library" (three of the six Mata v. Avianca names in the sample are cited this way). CAP coverage ends around 2019–2020 (U.S. Reports to volume 572, F.3d to 935), so recent real cases read "Not in the free library" without a CourtListener token.
- No OCR; scanned PDFs get the no_text_layer message. Misrepresented propositions are covered only by the optional advisory column.
- The rate limit is in memory per process: on serverless it applies per running instance.
- The 20-citation evaluation was written by the team that wrote the rule; it shows the rule matches its specification on known inputs, not accuracy on real filings. Timings come from a WSL2 laptop (F-0003).
- The README stills live in `qa/out/`, which `.gitignore` excludes; they must be force-added (`git add -f qa/out/demo-1440.png qa/out/demo-line-6-open-1440.png`) or the README images will not render.
- The CI README step still has `continue-on-error: true`; remove it now that README.md passes.
- Evidence missing: deploy smoke of the live URL (AC-13); T08 QA gate against the running server (AC-8, AC-9, AC-10 on the live page) and T09 review, both pending; Lighthouse / LCP; a live CourtListener call and a live Anthropic call (no token or key during the build); Vercel bundle size (assumption A-2, `du -sh .venv/lib` not recorded); the video (not recorded yet); a live-network sample run in T10 (the last one is the 2026-09-26 recording in `seed/replay.json`, 4.1 s).

## Cleanup
- T10 changed documentation only (README.md, DEVPOST.md, docs/VIDEO-SCRIPT.md, docs/SUBMISSION-CHECKLIST.md, LICENSE, this report, docs/API.md, docs/UI-SPEC.md); no code, tests or configs touched. `qa/out/` (57 PNGs and a PDF, about 6 MB per the T06 report) stays ignored apart from the two README stills.

## Optimization
- None in T10. Measured: the offline sample runs in 4.0 s by the stamp's clock (T10 lane #3); the recorded live run took 4.1 s for 23 citations (`seed/replay.json`). The contract's budgets are ≤ 15 s live and ≤ 3 s offline for the sample; the offline figure is over 3 s on this machine, where the quote stage is the slowest (1674 ms in T10 lane #2).

## Memory
- ADR-0001, ADR-0002, ADR-0003, ADR-0004, ADR-0005 (decisions), F-0001 (eyecite span/year), F-0002 (memoize per-volume data), F-0003 (WSL2 clock; global candidate), L-0001 (PYTHONPATH for scripts). No new record from T10.

## Next steps
- Fill the T08/T09 lines above from their reports, then run the canonical `python3 .prod-build/pb.py verify T10` and `python3 .prod-build/pb.py report .prod-build/DELIVERY.md`.
- Force-add the two README stills and remove `continue-on-error` from the CI README step.
- Deploy to Vercel, run the smoke command, paste the live URL into README.md and DEVPOST.md.
- Record the video from docs/VIDEO-SCRIPT.md, upload it, paste the link.
- Optional: set `COURTLISTENER_TOKEN` and watch one live run.
- After T08/T09 land, re-run `.venv/bin/python -m pytest -q` and update the test count in README.md ("Quality" and the evidence table) and DEVPOST.md: new test files were being added while this report was written.
