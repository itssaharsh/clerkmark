# Submission checklist — Clerkmark (LexHack 2026)

Deadline: 27 September 2026, 17:00 EDT (Devpost). Rules: https://lexhack-2026.devpost.com/rules. Tick each box when it is true for the submitted version, not when it is planned.

## LexHack requirements

| Done | Requirement (from the rules page) | Where it is satisfied |
|---|---|---|
| [ ] | Video of 3 minutes or less, hosted on YouTube, Vimeo or Loom | Script and recording checklist: [docs/VIDEO-SCRIPT.md](VIDEO-SCRIPT.md) (2:45). Paste the link into README.md ("Video") and DEVPOST.md ("Links") |
| [ ] | A public code repository or a live URL (a working live link is "highly recommended") | Repo: make it public on GitHub. Live URL: the Vercel deploy below. Paste both into README.md and DEVPOST.md |
| [x] | Problem and solution summary | [DEVPOST.md](../DEVPOST.md) (Inspiration, What it does); README "What and why" |
| [x] | Every API, framework, library and third-party tool declared in the submission's tech stack | README "Tech stack" table (each package in requirements.txt, the Caselaw Access Project, CourtListener, the Anthropic API and model, Google Fonts, Playwright and axe-core); DEVPOST.md "Built with". `bash scripts/check_readme.sh` prints PASS |
| [x] | All primary design and core software code created during the official hackathon timeframe | Git history: first commit 26 September 2026, 13:49 UTC. State this in the Devpost form if it asks |
| [x] | AI tools disclosed (LLM APIs and AI coding tools are allowed when declared) | README "Built during LexHack 2026" (AI coding assistants under human direction; AGENTS.md committed); README "Tech stack" (Anthropic Messages API, `claude-haiku-4-5-20251001`, optional); DEVPOST.md "How we built it" |
| [ ] | The team can explain the code | Walk through [ARCHITECTURE.md](../ARCHITECTURE.md), [docs/DECISION-RULE.md](DECISION-RULE.md) §2 and [docs/memory/decisions/](memory/decisions/) together before submitting; each person can explain `citememo/rules.py` steps 6–7 and the 0-of-11 evaluation line |

## Before the repo goes public

- [ ] The two README stills are in git. `qa/out/` is listed in `.gitignore`, so add them explicitly: `git add -f qa/out/demo-1440.png qa/out/demo-line-6-open-1440.png`, then check that both render on the GitHub README page.
- [ ] The CI step "README check (AC-14)" in `.github/workflows/ci.yml` still has `continue-on-error: true` (added until the README existed). Remove that line so a README regression fails CI.
- [ ] No secrets in the repo: `.env` is ignored; only `.env.example` (empty values) is committed.
- [ ] LICENSE (MIT) is in the root.

## Deploy (Vercel, zero-config)

1. [ ] Push `main` to GitHub.
2. [ ] In Vercel: Add New, Project, import the repository. Framework preset: leave what Vercel detects (FastAPI / Other). Leave the build command, output directory and install command empty: Vercel reads `requirements.txt`, finds `app` in `main.py`, and `vercel.json` sets `maxDuration` 60 s for `main.py`.
3. [ ] Optional environment variables (Settings, Environment Variables, Production): `COURTLISTENER_TOKEN`, `ANTHROPIC_API_KEY` (steps below). Leave `CITEMEMO_OFFLINE` unset on the live site so it looks up the free library live; the sample's files are cached either way.
4. [ ] Deploy. Then, from the repo root:
   ```bash
   python3 .prod-build/pb.py smoke <url> --routes / /api/health /api/samples
   ```
   All three routes must answer 200.
5. [ ] Open `<url>/?demo=1`: the memo paints with the CHECKED stamp. Then open `<url>/`, click "Use the sample filing" and wait for the stamp; line 8 (Miller) is circled red and line 9 (Shaboon) is in pencil.
6. [ ] Open `<url>/#evaluation`: the closing line reads "Real cases marked likely not real: 0 of 11. Correct classes: 20 of 20." (or whatever the live run says; if it differs from the README, update the README from the screen).
7. [ ] Paste `<url>/?demo=1` into README.md ("Live demo") and DEVPOST.md ("Links").

Rollback: in the Vercel dashboard, open Deployments and roll back to (or promote) the previous deployment. Other hosts: the `Procfile` runs `uvicorn main:app --host 0.0.0.0 --port $PORT`.

## Optional: CourtListener token

Without it the memo heading reads "CourtListener: not configured" and citations beyond the free library read "Not in the free library".

1. [ ] Create or sign in to a CourtListener account (courtlistener.com, Free Law Project) and copy the API token from the account's developer settings.
2. [ ] Add it in Vercel as `COURTLISTENER_TOKEN` (Production), then redeploy.
3. [ ] Check `<url>/api/health`: `"courtlistener": true`. Run the sample: the heading's CHECKED AGAINST line names CourtListener, and Biden v. Nebraska / Loper Bright may read "Found" with source CourtListener.
4. [ ] Note: Free Law Project documents a limit of 60 valid citations a minute for citation lookup; the default limit for new accounts was not stated when we checked (2026-09-26). The code path is tested with mocked HTTP only; watch the first live run.

## Optional: Anthropic API key (advisory column)

Without it every row reads "Advisory: not run". With it, found rows that carry a quote get "Advisory: supports / does not support; read this first / cannot tell". It never changes a class.

1. [ ] Create a key in the Anthropic Console (console.anthropic.com, API keys).
2. [ ] Add it in Vercel as `ANTHROPIC_API_KEY` (Production), then redeploy. The model is `claude-haiku-4-5-20251001` (override with `CITEMEMO_ADVISORY_MODEL`); at most 20 calls per memo, 15 s timeout each.
3. [ ] Check `<url>/api/health`: `"advisory": true`, then run the sample and read the advisory lines.
4. [ ] If you add the key, the README's "Live vs simulated" row for the advisory check stays accurate; the code path was tested with a mocked client only.

## Last hour

- [ ] **Incognito run** of the live URL: `?demo=1`, one live sample run, [Show the page] on line 6, the Evaluation tab, How it works.
- [ ] **Console clean**: DevTools console shows no errors or failed requests on those screens.
- [ ] **Warm-up**: open `<url>/api/health` and run the sample once a few minutes before judges might look, and before recording.
- [ ] **Links**: every link in README.md and DEVPOST.md opens logged out (video, live URL, repo, the Charlotin, Princeton and arXiv sources).
- [ ] **Placeholders gone**: `grep -n "add before submitting" README.md DEVPOST.md` prints nothing.
- [ ] **Numbers match**: the README and DEVPOST numbers (20 of 20, 0 of 11, 334 tests) match the latest run; re-run `.venv/bin/python scripts/eval.py --offline` and `.venv/bin/python -m pytest -q` if code changed after 27 September 2026.
- [ ] **Video** is under 3:00 and plays logged out.
- [ ] **Devpost form**: every optional field filled; the tagline from DEVPOST.md; the tracks that fit (Legal Automation & Workflow Innovation; Access to Justice & Civic Tech) if the form offers tracks.
