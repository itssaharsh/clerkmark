# Implementation contract — Clerkmark (LexHack 2026 entry)

Mode: hackathon · channel: direct · deadline: 2026-09-27 17:00 EDT (Devpost) · written 2026-09-26 11:20 EDT.
Upstream: `../hackathon-idea/lexhack-2026/ideas.json` (idea 1), `docs/IDEA-CARD.md`, `docs/UI-SPEC.md` (hackathon-ui, Sprint), `docs/DECISION-RULE.md`, `docs/BUILD-NOTES.md`, `docs/API.md`.

## Intent
Intake staff at a state trial court clerk's office or self-help centre (often not lawyers), or a pro se staff attorney, at the moment a self-represented litigant's filing lands on the docket.
Before: they look up every cited case by hand, and a case that does not come up could be fabricated or just missing from the free database; courts report "large judicial resources" spent this way, and sanctions for AI-fabricated citations reached 2,079 decisions (1,196 pro se) by 2026-09-25.
After: they drop the PDF and get a one-page typed memo: every citation classed with the rule that decided it, red-pen marks on the bad rows, the real case at the cited page one click away, and "not in the free library" kept apart from "likely not a real case". The memo is a triage aid, not a finding.

## Demo script (build only what appears here; UI-SPEC §2 is the source)
| t | On screen | Spoken (numbers read off the screen) |
|---|---|---|
| 0:00 | The populated memo over the sample filing (`?demo=1`), wordmark, TO/FROM/RE block | "When someone without a lawyer files a brief written with a chatbot, court staff look up every case by hand." |
| 0:10 | Charlotin database numbers on a card; source and date visible | "Two thousand seventy-nine decisions; more than half from people representing themselves." |
| 0:20 | Click "Use the sample filing"; status line: four steps, real elapsed timer | "We check the whole filing against a free law library." |
| 0:30 | Memo returns; rows reveal; marks draw down the sheet; stamp lands | "Twenty citations in {elapsed} seconds." |
| 0:45 | Rows 8–9: Miller v. United Airlines circled red with its rule; Shaboon v. Egyptair in pencil "Not in the free library" | "This one is likely not a real case: page 366 belongs to Greenleaf v. Garlock. This one we simply cannot check for free. A naive checker prints the same 'not found' for both." |
| 1:10 | [Show the page] on the Varghese row: the reporter page with the running head naming J.D. v. Azar | "The page it cites is a different case." |
| 1:30 | A quote_not_found row: closest passage with the differing words | "Real case, wrong quote." |
| 1:50 | Evaluation tab: 20 rows, expected vs said, correct count, real cases marked likely-not-real: 0 | "Twenty known citations; {c} of 20 right; zero real cases called fake." |
| 2:15 | How it works: the numbered rule; sources; limits | "Deterministic rule; the model, if any, only advises." |
| 2:35 | Repo README tech-stack table; live URL | "Repo and live link in the description." |

## Scope
MUST (core, main workflow, judged):
- PDF or pasted-text intake → eyecite extraction → Caselaw Access Project lookups → deterministic classes → memo JSON (API.md).
- The memo screen: numbered rows in filing order, plain-word label, rule sentence, marks per class, [Show the page] (running head + excerpt + CAP links) and [Show the shelf] (volume range), "Read these first" tally, CHECKED stamp with real counts and timings, disclaimer and litigant sentence.
- One-click seeded sample (synthetic filing, labelled on the content) that runs live and falls back to the committed cache; `?demo=1` paints it.
- Evaluation tab from `GET /api/eval` (20 citations vs `seed/ground_truth.json`).
- Every state reachable via `?state=`; replay via Alt+Shift+P and `GET /api/replay`; reset via Alt+Shift+R / `?reset=1`.
- Error, empty and partial behaviour with the input kept (UI-SPEC §9 strings).
- Offline mode (`CITEMEMO_OFFLINE=1`) serving the sample from cache; `scripts/verify.sh` printing PASS/FAIL on the seeded demo path without network.
- Deployable zero-config to Vercel (root `main.py`, `requirements.txt`, `vercel.json`); README with the tech-stack table (every API, library, dataset, model) and the live-vs-simulated table; Devpost write-up; 3-minute video script; submission checklist.
SHOULD (after MUSTs verified): CourtListener second pass for not-in-free-corpus rows when `COURTLISTENER_TOKEN` is set; advisory support check via the Anthropic API when `ANTHROPIC_API_KEY` is set (printed "Advisory: not run" otherwise); print stylesheet; keyboard shortcuts; GitHub Actions CI running the offline suite.
COULD (listed, not built): statutes and court rules; pin-cite verification via CourtListener opinion text; batch/docket intake; a litigant-facing correction kit.
WON'T now: accounts or login; storing uploaded filings; OCR; Westlaw/Lexis integration; Transparency Database; multi-tenant anything.

## Journeys (≤3)
- J1 Sample run (the vertical slice): open `/` → click "Use the sample filing" → status line (four named steps, elapsed timer) → `POST /api/memo/sample/sample-motion` → memo with marks; row 8 (Miller) red circle + rule; row 9 (Shaboon) pencil "Not in the free library"; [Show the page] on Varghese shows "925 F.3d 1291 · J.D. v. AZAR"; stamp shows counts and seconds.
- J2 Own filing: drop a PDF or paste text → same pipeline → memo; a scan without a text layer, a non-PDF, an oversize file or a server error each shows its UI-SPEC §9 string and keeps the input.
- J3 Evaluation and How it works: Evaluation tab shows 20 rows expected vs said, correct count, "Real cases marked likely not real: 0 of 11" (the 11 ground-truth rows with a real case at the cited page; the two beyond-coverage rows are real but not page hits); How it works shows the numbered rule, sources, limits and credits.

## Surfaces (UI-SPEC §3 ids)
S1 first-run (drop zone + sample) · S2 loading (status block) · S3 memo · S4 evidence drawer (page / shelf) · S5 evaluation · S6 how it works · states: first-run, loading, partial, error, no-results · print view.
API (docs/API.md): `GET /`, `GET /static/*`, `GET /api/health`, `GET /api/samples`, `POST /api/memo`, `POST /api/memo/sample/{id}`, `GET /api/replay`, `GET /api/eval`.

## States
| Journey | initial | loading | success | error | empty | partial | retry | disabled | permission-denied | offline/degraded |
|---|---|---|---|---|---|---|---|---|---|---|
| J1 | S1 with the sample button | S2 four steps + timer; after 10 s "Still working." | S3 memo + stamp | "The server did not answer… [Try again]" (S1 kept) | n/a: the seed has citations | "{n} unanswered… [Retry n]" rows in pencil | [Retry n] re-runs only failed rows' volumes (v1: re-runs the sample) | sample button aria-disabled while a run is in flight | n/a: public, guest only | cache-only run, stamp notes "cache"; replay banner via Alt+Shift+P |
| J2 | S1 drop zone | S2 | S3 | no_text_layer / unsupported_type / too_large / upstream_timeout strings; file stays selected | "No case citations found in {pages} pages…" | as J1 | as J1 | drop zone aria-disabled in flight | n/a | as J1 |
| J3 | tabs visible | eval computing spinner ≤1 s (from last run or on demand) | table + closing line | "Could not score the sample. [Re-run the sample]" | n/a: seed fixed | stale line "Scored on the run of {date}" | [Re-run the sample] | n/a | n/a | eval from the offline run |

## Data
| Entity | Key fields | Owner | Persistence | Source of truth | PII |
|---|---|---|---|---|---|
| Memo | run_id, results[], counts, timings, sources_used | request (guest) | none (in memory per request); `seed/replay.json` for the recorded seed run | the run | none stored; uploaded PDFs are read in memory and discarded |
| CitationResult | row, cite_text, class, label, reasons[], evidence, source | part of Memo | none | the rule engine | none |
| CAP corpus files | reporters, volumes, cases, opinion text | Harvard LIL (external) | on-disk JSON cache (`seed/cache/cap`, else `CITEMEMO_CACHE_DIR`, else `/tmp`) | static.case.law | none |
| Ground truth | 20 items with expected/accepted classes | repo | `seed/ground_truth.json` | repo | none |
| Samples | id, label, file | repo | `seed/samples.json`, `seed/sample-motion.pdf` | repo | none (synthetic) |

## Interfaces
| Boundary | Contract | Failure mode | Fallback |
|---|---|---|---|
| Browser ↔ API | docs/API.md (pydantic models in citememo/models.py) | 4xx/5xx envelope {error:{code,message,hint}} | UI §9 strings; input kept |
| CAP static files | citememo/cap.py | timeout 20 s, 404 (volume/case missing), 5xx | one retry; cache; per-volume degrade to not_in_free_corpus with "Could not reach the free library." / "Timed out after 20 s."; memo returns partial |
| CourtListener (optional) | citememo/courtlistener.py | 401/429/timeout | skip pass; memo heading "CourtListener: not configured" or "unavailable" |
| Anthropic API (optional) | citememo/advisory.py, model claude-haiku-4-5-20251001, JSON verdict | refusal, malformed JSON, timeout 15 s, quota | advisory None → "Advisory: not run"; never changes a class; ≤ 20 calls per memo |
| pdfplumber / eyecite / reporters_db | citememo/extract.py | no text layer; unknown reporter dropped | no_text_layer envelope; regex catch → unrecognized_reporter |

## Constraints
- Judging (verbatim, https://lexhack-2026.devpost.com/): Real-World Impact & Feasibility 25% "How effectively does the project address a genuine challenge in legal access, civic tech, digital rights, or AI governance?" · Technical Execution & Functionality 25% "How well is the working prototype built? Is the code functional, well-structured, and capable of executing its core workflows?" · User Experience & Design 20% "Is the application intuitive, clear, and easy to navigate? Is the interface accessible and understandable for everyday users, non-lawyers, or non-technical individuals?" · Innovation & Originality 15% "How creative and unique is the concept? Does the project take a novel approach to solving a legal tech or civic problem?" · Presentation & Documentation 15% "How clear and compelling is the 3-minute video demonstration? Does the Devpost write-up clearly state the problem, solution, tech stack?"
- Rules (https://lexhack-2026.devpost.com/rules): video ≤ 3 min; public repo or live URL (live link "highly recommended"); "All primary design and core software code must be created during the official hackathon timeframe"; open-source libraries, public APIs and LLM APIs allowed if "explicitly declared in the submission tech stack"; AI code tools allowed but the team must be able to explain the code.
- Criterion → moment: Impact → 0:10 numbers + 0:45 contrast; Technical → 0:30 live run, 1:10 evidence, 1:50 eval; UX → plain labels, one action, litigant sentence; Innovation → 0:45 fake-vs-not-held with the rule printed; Presentation → the script above and README.
- Platform: Vercel Python function, maxDuration 60 s, request body ≤ 4.5 MB (so uploads are capped at 4 MB; UI-SPEC's 20 MB string is revised, deviation logged), read-only FS except /tmp.
- Abuse limits: POST /api/memo ≤ 4 MB, text ≤ 200,000 chars, ≤ 250 citations processed per memo, in-memory rate limit 10 memos/min per IP (429 envelope), advisory ≤ 20 calls per memo and only with a key; sample endpoint cached.
- Performance: sample run ≤ 15 s live / ≤ 3 s offline; LCP ≤ 2.5 s; no layout shift when the stamp lands.
- Honesty: no invented users, numbers or logos; sample labelled on the content; "likely fabricated" never as a fact; credits to CAP, Free Law Project (CourtListener, eyecite, reporters_db), Princeton CITP, Charlotin.
- No sponsor product is used (none fits; recorded in the idea package).

## Acceptance criteria
- AC-1 [MUST] WHEN the seeded sample runs THE SYSTEM SHALL classify ≥ 18 of 20 citations within `accepted_classes` and mark 0 real cases likely_fabricated. Verify: `.venv/bin/python -m pytest -q tests/test_integration.py -k eval`.
- AC-2 [MUST] WHEN "Varghese v. China Southern Airlines Co., 925 F.3d 1339" is classified THE SYSTEM SHALL return likely_fabricated with evidence.real_case_at_page naming J.D. v. Azar (925 F.3d 1291–1349). Verify: `pytest -q tests/test_rules.py -k varghese`.
- AC-3 [MUST] WHEN a consistent citation to a volume the free library lacks is classified (600 U.S. 477) THE SYSTEM SHALL return not_in_free_corpus (verified only if CourtListener confirms), never likely_fabricated. Verify: `pytest -q tests/test_rules.py -k beyond`.
- AC-4 [MUST] WHEN a quoted passage differs from the opinion text THE SYSTEM SHALL return quote_not_found with similarity and the differing tokens. Verify: `pytest -q tests/test_quotes.py`.
- AC-5 [MUST] IF the PDF has no text layer THEN THE SYSTEM SHALL return the no_text_layer envelope and the UI SHALL show the §9 string with the file still selected. Verify: `pytest -q tests/test_integration.py -k no_text`; observe: qa/qa.mjs `?state=error` screenshot.
- AC-6 [MUST] IF the corpus is unreachable for a volume THEN THE SYSTEM SHALL return the memo with those rows not_in_free_corpus, reason "Could not reach the free library.", and memo.partial counts. Verify: `pytest -q tests/test_integration.py -k unreachable`.
- AC-7 [MUST] WHEN CITEMEMO_OFFLINE=1 THE SYSTEM SHALL run the sample from the committed cache in ≤ 5 s. Verify: `CITEMEMO_OFFLINE=1 bash scripts/verify.sh` prints PASS.
- AC-8 [MUST] WHEN the memo renders THE SYSTEM SHALL show, per row, the plain label, the rule sentence and the class mark, and [Show the page] SHALL open a drawer whose running head names the case at that page. Verify: `node qa/qa.mjs http://localhost:8000` DOM assertions; observe: screenshots.
- AC-9 [MUST] WHEN `?state=first-run|loading|partial|error|no-results` is set THE SYSTEM SHALL render that state at 320/390/1024/1440 with 0 axe violations (wcag2a/2aa/21a/21aa/22aa). Verify: `node qa/qa.mjs http://localhost:8000`.
- AC-10 [MUST] WHEN `?reset=1` or Alt+Shift+R THE SYSTEM SHALL return to S1; WHEN Alt+Shift+P THE SYSTEM SHALL show the replay with the "Replay · run of {date}" banner. Verify: observe (qa.mjs replay route).
- AC-11 [MUST] WHEN `GET /api/eval` is called THE SYSTEM SHALL return an EvalReport with accuracy, per-class counts and real_cases_marked_fabricated. Verify: `bash scripts/verify.sh` (curl + jq-free python check).
- AC-12 [MUST] IF a request body exceeds 4 MB or exceeds 10 memos/min per IP THEN THE SYSTEM SHALL return too_large / rate_limited envelopes. Verify: `pytest -q tests/test_integration.py -k limits`.
- AC-13 [MUST] WHEN the repo is deployed to Vercel THE SYSTEM SHALL answer `/api/health` and run the sample from cache. Verify: `python3 .prod-build/pb.py smoke <url> --routes / /api/health /api/samples` (needs the user's deploy; "not deployed" until then).
- AC-14 [MUST] WHEN README.md is read THE SYSTEM SHALL list every runtime dependency, API, dataset and model in a tech-stack table and a live-vs-simulated table. Verify: `bash scripts/check_readme.sh`.
- AC-15 [SHOULD] WHEN COURTLISTENER_TOKEN is set THE SYSTEM SHALL re-check not_in_free_corpus rows and upgrade confirmed ones to verified with source CourtListener. Verify: `pytest -q tests/test_courtlistener.py` (mocked HTTP).
- AC-16 [SHOULD] WHEN ANTHROPIC_API_KEY is set THE SYSTEM SHALL add an advisory verdict to verified rows with a quote, never changing the class. Verify: `pytest -q tests/test_advisory.py` (mocked client).

## Assumptions
- A-1 [safe] static.case.law stays reachable during the build and the demo; the committed cache covers the sample regardless. Validate: `scripts/verify.sh` offline.
- A-2 [reversible] The Python bundle (eyecite, reporters_db, pdfplumber, rapidfuzz, fastapi, httpx, anthropic) stays under Vercel's 500 MB limit. Validate: `du -sh .venv/lib` before deploy (expect < 200 MB).
- A-3 [reversible] Uploads capped at 4 MB because of the 4.5 MB function body limit; the sample PDF is ~40 KB. Validate: deploy smoke.
- A-4 [safe] No CourtListener token or Anthropic key during the build; both paths are optional and tested with mocks. Validate: unit tests.
- A-5 [safe] The user deploys from their own Vercel account; the build ends "not deployed" with the exact steps. Validate: the smoke test once the URL exists.

## Known deviations from upstream
- UI-SPEC §9 "larger than 20 MB" → "larger than 4 MB" (platform limit).
- UI-SPEC §6 C-04 `GET /api/evidence/{row}` → evidence embedded per row (API.md decision).
