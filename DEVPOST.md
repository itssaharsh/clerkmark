# Devpost write-up — Clerkmark

Fields in the order the Devpost form asks for them, ready to paste. Every number carries its source. Replace the three placeholders under "Links" before submitting.

---

## Project name

Clerkmark

## Tagline

Spot likely fake case citations before the judge reads them

(59 characters.)

## Inspiration

When someone without a lawyer files a brief drafted with a chatbot, court staff look up every cited case by hand. Damien Charlotin's [AI Hallucination Cases database](https://www.damiencharlotin.com/hallucinations/) lists 2,079 court decisions that found hallucinated or misquoted citations in filings, and 1,196 of them involve a self-represented litigant (figures as of the database's 25 September 2026 update). The same database lists September 2026 sanctions of $3,000 to $15,000.

Princeton CITP's researchers ([blog post, 27 May 2026](https://blog.citp.princeton.edu/2026/05/27/can-ai-reduce-burdens-on-courts-by-automatically-verifying-citations/)) describe courts spending "large judicial resources tracking down hallucinations and verifying citations", and warn that free sources "still do not have complete coverage": "Many opinions are only available behind paywalls on Westlaw or Lexis." Their paper ([arXiv 2606.21155](https://arxiv.org/html/2606.21155)) found that weaker models "treat absence from CourtListener as evidence of hallucination".

That last point is the one we built around. A free lookup that says "not found" for a made-up case says the same thing for a real case it does not hold. If intake staff read both as "fake", the person hurt is the filer without a lawyer.

## What it does

Clerkmark is for intake staff at a state trial court clerk's office or self-help centre, or a pro se staff attorney. They drop the filed PDF; Clerkmark returns a one-page typed memo over the filing's case citations:

- every citation in filing order, with a plain-word label: "Found.", "Found, but this quote is not in the opinion.", "Exists, but not at this page.", "Not in the free library. Check Westlaw or Lexis.", "No reporter by this name.", "Likely not a real case.", or "Not checked" for statutes and short forms;
- the rule sentence that decided it, printed under the row: for example "Page 366 belongs to Greenleaf v. Garlock, Inc., 174 F.3d 352–368. No case named Miller in volume 174.";
- red-pen marks on the rows to read first and pencil on the rows the free library cannot answer;
- [Show the page]: the running head of the case the reporter actually prints at that page, an excerpt of its opinion text and the Caselaw Access Project links;
- [Show the shelf]: where the free library's volumes stop, for citations beyond its coverage;
- for quotes, the differing words or the closest passage and its similarity;
- a "Read these first" paragraph, a CHECKED stamp with the run's real counts and seconds, and a disclaimer: "Triage aid. Not a finding. Verify flagged rows before relying on them."

An Evaluation tab scores the seeded sample against 20 citations with known answers, and a How it works tab prints the whole rule, the sources and the limits.

## How we built it

- **Corpus:** the Caselaw Access Project's free static files (static.case.law, Harvard Law School Library Innovation Lab): reporters, volumes, the case list of each volume with first and last pages, and opinion text. No account needed. Files are cached on disk; the sample's files are committed, so the demo also runs offline.
- **Extraction:** pdfplumber for the PDF's text, Free Law Project's eyecite for case citations, reporters-db for reporter editions, and a filtered regex that catches citation-like strings with a reporter nobody knows.
- **The rule:** plain Python, no model. For each citation it checks the reporter, the volume range, who sits at the cited page (a case can begin there or span it), and then searches every case in the volume for the cited party names. Only when the page belongs to another case and no case in the volume carries either name does it say "Likely not a real case". Quotes are matched against the opinion text with rapidfuzz after normalizing curly quotes, hyphenation and bracketed alterations.
- **Optional:** CourtListener's v4 citation-lookup API re-checks rows the free library does not hold when a token is set; the Anthropic Messages API (model claude-haiku-4-5-20251001) adds an advisory "supports / does not support / cannot tell" on found rows with a quote when a key is set. Neither ever changes a class.
- **App:** one FastAPI app (`main.py`) serving a plain HTML, CSS and JavaScript page; no framework, no database. Deployable to Vercel with zero configuration.
- **Proof:** 380 pytest tests, a PASS/FAIL offline demo script, a Playwright and axe-core QA script, and CI on GitHub Actions.
- **AI assistance:** the code was written with AI coding assistants (Claude Code, with Anthropic's Claude models) under human direction during the event. Every module is explained in ARCHITECTURE.md and the design decisions in docs/memory/decisions; the assistants' instructions are committed in AGENTS.md.

## Challenges we ran into

- **Volume years in the data are unreliable, so a year can never decide "fake".** Our first idea was to flag a citation whose year did not fit its volume. The data said no: reporters_db dates U.S. Reports from 1875, yet Marbury v. Madison, 5 U.S. 137 (1803), is real and in the free library; reporters_db ends F. Supp. in 1988, yet the library's volume 999 holds 1996–1998 decisions; the library labels U.S. volumes by October Term (470 U.S. is labelled 1984, its decisions are from 1985); several reporters have no volume years at all. An early estimate built on volume years marked Mata v. Avianca itself, a real 2023 case, as likely fake. A year mismatch is now a printed note and never a class.
- **The same 404 for a fake case and a missing real one.** CourtListener's citation-lookup API answers 404 for a citation that is well formed but not in its database (Free Law Project's API documentation), and a made-up case with a plausible volume and page gets the same 404. Our answer is the deterministic rule: look at the case that sits at the cited page and search the whole volume for the cited names, and say "Not in the free library" whenever the library cannot see the page. West reporters also start a case on the page where the previous one ends (121 of the 145 cases in 174 F.3d do), so "the case at this page" has to consider both the case that begins there and the one that spans it.
- **eyecite overshoots.** eyecite 2.7.8's full citation span ran into the next citation, and its year guess borrowed the next citation's year (Shaboon and Floyd both came out as 2019 on our sample). We now cut the citation text at the party names and read the year from a bounded parenthetical window.

## Accomplishments that we're proud of

- On the seeded 20-citation evaluation, all 20 land in their expected class, and **0 of 11** real cases at their cited page are marked likely not real (`scripts/eval.py --offline`, 27 September 2026).
- The row the demo is built on works: "Miller v. United Airlines, Inc., 174 F.3d 366" is circled red because page 366 belongs to Greenleaf v. Garlock and no case named Miller is in volume 174, while "Shaboon v. Egyptair, 2013 IL App (1st) 111279" sits in pencil as "Not in the free library".
- 380 automated tests pass (1 opt-in live test skipped), and `scripts/verify.sh` proves the demo path offline with PASS/FAIL (27 September 2026).
- A recorded live run checked the sample's 23 citations in 4.1 s with the network on (`seed/replay.json`, 26 September 2026).
- 0 axe-core accessibility violations on 10 views at 1440 px, every state reachable by URL, and a memo that prints on one letter page (QA run, 26 September 2026).

## What we learned

- Absence from a free database is not evidence that a case is fake. Building the whole product around that one sentence from Princeton's paper changed every rule we wrote.
- Trusted datasets carry hand-entered facts that are wrong in places. Every rule had to be tried against real volumes before it could decide a class.
- Printing the rule that fired under each row made the tool easier to trust, and easier for us to debug.
- A memo a clerk would recognise, with a TO/FROM block and red-pen marks, explains itself faster than a dashboard.

## What's next for Clerkmark

- CourtListener as a live second source, with a token, so recent cases beyond the free library's coverage (for example 2023 and 2024 Supreme Court cases) can read "Found".
- Statutes and court rules, which are listed as "Not checked" today.
- Pin-cite checks using CourtListener's opinion text, which keeps page breaks.
- A correction kit for the litigant: the memo's findings in plain words, so a self-represented filer can fix the brief.

## Built with

python, fastapi, uvicorn, pydantic, python-multipart, pdfplumber, eyecite, reporters-db, courts-db, httpx, rapidfuzz, anthropic, claude-haiku-4-5, caselaw-access-project, courtlistener, html5, css3, javascript, google-fonts, pytest, fpdf2, playwright, axe-core, github-actions, vercel

The full table, with versions, purposes and licenses, is in the README's "Tech stack" section.

## Links

- Video (under 3 minutes): VIDEO_URL (add before submitting)
- Live demo: LIVE_URL/?demo=1 (add before submitting)
- Code: REPO_URL (add before submitting)
