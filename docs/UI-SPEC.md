---
name: Clerkmark
scope: sprint
one_line: "Clerkmark writes the clerk's red-pen memo over a filed brief's citations for court intake staff"
ambition: L1            # Polished. Textual rows and high stakes cap the task flow at L1; one signature motion (marks drawing down the sheet once per run) and one signature surface (the reporter page under the row)
registers: { memo_body: productive, run_complete: celebratory-lite, flagged_rows: serious, disclaimer: serious, errors: system, evaluation: productive, how_it_works: system }
direction: "derived: canvas bond paper #FCFBF7 · ink typewriter black #1B1A17 · accent the clerk's red pen #BE1E2D (marks and stamp only, never buttons) · display Courier Prime 700 (3 candidates: Courier Prime from the bench memo and pleadings typed in Courier 12; Old Standard TT from the reporter's running head, kept only as the reference for the excerpt's small caps; Big Shoulders Display from the reporter spine, rejected because a spine is not what the clerk reads) · body Source Serif 4 for what the book printed"
personality: precise    # a clerk, not a robot: ease-out-quint 120–200 ms; nothing decorative moves
dials: { variance: 3, motion: 3, density: 7 }   # productive register. run_complete overrides motion to 5 for the one mark pass; flagged_rows override nothing (the mark is the register)
stack: { page: "web/index.html + web/static/app.css + web/static/app.js, served by FastAPI GET / (FileResponse) so ?demo=1 and ?state= reach the page", fonts: "Google Fonts: Courier Prime 400/700, Source Serif 4 400/700 with font-display swap", framework: "none (plain HTML, CSS, JS; the whole UI is one typed document and a framework would add more code than the page)", assets: "web/static/*, web/favicon.svg, web/wordmark.svg, web/tokens.css" }
archetype: document-as-result   # B13 skeleton: a typed document that is itself the artifact; table-as-memo, no dashboard chrome
viewports: [320x640, 390x844, 1024x768, 1440x900]
signature: { interaction: "[Show the page] opens the reporter page under the row, whose running head names a different case than the citation above it", visual: "a red-pen circle beside a pencil note on adjacent rows; strike-and-correct on the wrong-page row" }
wow: "POST /api/memo returns (or the sample run returns) → the status line reads 'Done in {elapsed} s' within 100 ms → rows reveal in filing order (30 ms stagger) and the pen goes down the sheet: each mark draws pathLength 0→1, 300 ms, 60 ms stagger, then the CHECKED stamp lands (scale 1.08→1, 180 ms) → residue: marks, stamp, the 'Read these first' paragraph, the browser title 'Memo · {n} citations · {k} likely not real' → record: the rule sentence under every row, [Show the page] / [Show the shelf] with CAP URLs, the Evaluation tab, seed/replay.json"
demo: { seed: "POST /api/memo/sample/{id} (GET /api/samples lists ids; the seed id is sample-motion)", flag: "?demo=1", state_param: "?state=first-run|loading|partial|error|no-results", reset: "alt+shift+r (e.code KeyR) and ?reset=1", replay: "alt+shift+p (e.code KeyP) reads seed/replay.json", guest: true }
live_vs_simulated: [ "PDF text extraction: live (pdfplumber on the server)", "citation extraction: live (eyecite + the unrecognized-reporter regex)", "Caselaw Access Project lookups: live, cached on disk; offline replay serves the same cache", "CourtListener: optional, live only when COURTLISTENER_TOKEN is set; the memo heading says 'CourtListener: not configured' otherwise", "quote matching: live (rapidfuzz)", "advisory support check: live when ANTHROPIC_API_KEY is set, printed 'Advisory: not run' otherwise", "streaming progress: not built; the status line shows four planned steps and a real elapsed timer, nothing counted", "nothing simulated in the core loop" ]
deviations:
  - "Accent not on the primary CTA: red is the pen; a red button would read as a mark. Buttons are ink-filled with paper labels; focus rings are ink."
  - "--danger shares the pen hue: one red exists in this world. Every validation and error sentence is typed in ink on the sheet; --danger is reserved for a confirm step that v1 does not have."
  - "No app header: the memo's TO/FROM block and the folder-tab strip are the header; the browser title carries name and counts."
  - "Monospace as the document face: Courier Prime sets the memo because the artifact is typed in Courier. The rule is 'Courier = what the clerk typed, Source Serif 4 = what the book printed', so the note and rule sentence are Courier too and only the reporter panel is serif."
  - "Line numbers at 12px: the floor, not below it; they are row anchors, not reading text."
  - "Rows in filing order, not grouped by class: a memo follows the filing. The 'Read these first' sentence at the foot gives the triage order and links to each class's first row."
  - "Marks are inline SVG paths per row (ellipse, strike, underline), not CSS borders: a slightly irregular hand path is what a stranger reads as 'a pen did this'. Stroke 1.5px (2px in print), no filter, no handwriting fonts."
  - "No desk blotter: the surround is a flat --surround #E8E5DC at ≥1024 so the house-style count stays at two (paper canvas; a stamp that lands)."
  - "The stamp is static on first paint: the 180 ms scale plays only when a live run completes in this tab; ?demo=1 paints the finished memo with the stamp already on it."
---

## 0. Brief + context profile (A2)

- **One line:** Clerkmark writes the clerk's red-pen memo over a filed brief's citations.
- **User and moment:** clerk's-office intake staff, self-help-centre staff or a pro se staff attorney, at a desk in daylight on a laptop, holding the filed PDF that was just docketed. Several filings a day. Before the judge reads it.
- **Primary action:** drop a filed PDF.
- **Hero object:** the one-page memo sheet: every citation typed as a numbered line with the clerk's mark beside it.
- **Product moment:** the memo returns and the marks go down the sheet row by row.
- **Demo moment:** rows 8 and 9 of the sample: "Miller v. United Airlines, Inc., 174 F.3d 366" circled in red with "Likely not a real case. Page 366 belongs to Greenleaf v. Garlock, Inc., 174 F.3d 352–368." beside it, and directly under it "Shaboon v. Egyptair, 2013 IL App (1st) 111279" in pencil with "Not in the free library. Check Westlaw or Lexis." A naive checker prints the same "not found" for both.
- **Differentiator:** the rule that fired is printed under every row; [Show the page] opens the reporter page at that volume and page, whose running head names a different case than the filing does; [Show the shelf] shows where the free library's volumes stop for rows the library does not hold. Evidence is one click away, on the object.
- **Artifact:** the memo itself, printable to letter size, with a CHECKED stamp carrying the run date and time, citation count, elapsed seconds and the sources used.
- **World inventory:** (1) the bench memo: bond paper, TO/FROM/RE/DATE block, double rule, Courier; (2) pleading paper's numbered left margin; (3) the file stamp: a boxed red rubber stamp with the date, slightly off-square; (4) the reporter volume: the printed page with its running head "925 F.3d 1291 · J.D. v. AZAR", and the row of volumes on the shelf; (5) the clerk's red pen and pencil: circles, strike-and-correct, underlines, checkmarks; (6) the manila folder tab; (7) the docket sheet's numbered entries.
- **Moving truth:** the run's own elapsed timer while waiting; the marks once per run; otherwise none.
- **Judging (verbatim weights):** Real-World Impact & Feasibility 25% · Technical Execution & Functionality 25% · User Experience & Design 20% ("accessible and understandable for everyday users, non-lawyers, or non-technical individuals") · Innovation & Originality 15% · Presentation & Documentation 15% (3-minute video). Async Devpost judging from video, stills and repo; no UI prize.
- **Budget:** 4–6 h UI. Plain HTML/CSS/JS under `web/`, served by FastAPI; Google Fonts; no framework.
- **Backend contract that shapes the UI:** `POST /api/memo` returns one `Memo` JSON; there are no per-citation events. The UI therefore never counts anything while waiting (A0 law 6). One small addition is required from the backend: `GET /api/evidence/{row}` (see §6 C-04) returning the running head, page marker, about 200 characters around the closest passage or the page start, and the CAP URLs used, from the cached CAP file; when it is not built, the drawer shows metadata only and says so.

| Factor | Where this project sits | What it changes |
|---|---|---|
| Task frequency | several times a day, not hundreds | dense rows (density 7), no tours; one payoff on run completion, ≤200 ms everywhere else |
| Data density | 20–40 rows, each with a sentence of evidence | table-as-memo, 56px two-line rows, tabular numerals, line numbers as row anchors |
| Stakes | high: a flagged row can cost a self-represented filer | calm ink, explicit uncertainty wording ("likely", "not in the free library"), never "fabricated" as a fact, L1 task flow |
| Audience | non-lawyers at intake, occasionally lawyers | class labels are plain sentences; the citation is the only jargon; the rule sentence is one line; class keys live in the Evaluation tab |
| Use scene | desk, daylight, laptop; also 720p video | light canvas; 15px memo text; links and stamp lines 14px so they survive video compression |
| Emotional target | careful | nothing decorative moves; every mark is a statement with evidence under it |
| Personality | Precise (a clerk, not a robot) | ease-out-quint 120–200 ms; the one signature: marks drawing on |
| Sponsor / host | Devpost; no sponsor product fits | the video carries the problem number; the page carries the sample label on the content (RE: line) |

## 1. Judge tests (A3)

**5-second test** (first screen = the populated memo over the sample filing; `?demo=1` is the default on the live URL):
- What: a court memo listing a filing's case citations with red-pen marks beside the bad ones.
- Who: "TO: Intake desk · FROM: Clerkmark, citation check" and the disclaimer under the double rule.
- Problem: rows 6–8 circled in red, each with "Likely not a real case. Page {p} belongs to {real case}."; rows 9–11 in pencil, "Not in the free library."
- One primary action: the ink-filled button **Drop your own PDF** at the heading's right, under the stamp; visible at 390×844 without scrolling.

**30-second test:**
- Loop: at 0:00 the finished sample memo is on screen. The narrator clicks **Drop your own PDF**, drops the sample PDF; RE: fills with the file name, the status line shows four hollow steps and a live timer; the memo returns; rows reveal, the pen goes down the sheet, the stamp lands with the run's own seconds.
- Differentiator without narration: red circle (row 8) directly above pencil note (row 9); [Show the page] on row 6 opens a reporter page whose running head reads J.D. v. AZAR under a citation naming Varghese; [Show the shelf] on row 23 shows U.S. Reports volumes 1–572 held and 573–600 outlined.
- Technical depth one click away: the Evaluation tab (20 ground-truth rows, per-class counts, "Real cases marked likely not real: {fp} of {real}", per-stage seconds) and How it works (the 9-step rule, sources, live-vs-optional table, credits).
- Demo-critical screens: S3 populated memo (80% of polish), S4 row expanded with the reporter page, S5 Evaluation sheet.

**The 3 stills** (a stranger names the differentiator from each):
1. **The marked memo at 1440, scrolled so lines 6–11 fill the middle of the frame.** Three red circles with "Likely not a real case. Page 1339 belongs to J.D. v. Azar, 925 F.3d 1291–1349. No case named Varghese in volume 925." and two more like it; directly below, three pencil rows "Not in the free library. Check Westlaw or Lexis." The CHECKED stamp is in the heading at top right. Stranger: "it separates fakes from cases the free library doesn't have."
2. **Line 6 expanded.** Under the circled citation, a reporter-page panel on cooler paper: running head "925 F.3d 1291 · J.D. v. AZAR · D.C. Cir. · June 14, 2019", page marker "1339" at the right, opinion text. Stranger: "that page really belongs to a different case."
3. **The Evaluation sheet.** A typed table: line, citation, expected, memo's class, match; the closing sentence "Real cases marked likely not real: {fp} of {real}. Correct classes: {c} of 20." and per-stage seconds. Stranger: "they measured it against known answers."

## 2. Demo script (3-minute video; numbers spoken are read off the screen, never scripted)

| Time | On screen | Voice |
|---|---|---|
| 0:00–0:08 | the populated sample memo at 1440; the cursor rests on the heading | "This is Clerkmark. It writes the clerk's memo over a filed brief's citations." |
| 0:08–0:25 | cut to the Charlotin database page (https://www.damiencharlotin.com/hallucinations/), the pro se count highlighted | "As of the day we checked, 1,196 of the 2,079 decisions in Damien Charlotin's database of AI-hallucinated citations involve people filing without a lawyer. Court staff find the fake cases by hand." |
| 0:25–0:55 | back to Clerkmark; click **Drop your own PDF**, drop `sample-motion.pdf`; RE: fills; the status line shows the four steps and the timer; the memo returns; rows reveal; marks draw; the stamp lands | "Drop the filing. Clerkmark reads it, pulls every case citation, and checks each one against the Caselaw Access Project's free files. The memo comes back in the time on the stamp." |
| 0:55–1:35 | scroll to lines 6–11; hover row 8 then row 9; click [Show the page] on line 6 (reporter page opens, running head J.D. v. AZAR); close; click [Show the shelf] on line 23 (U.S. Reports strip: 1–572 held, 573–600 outlined) | "Here is the part other checkers get wrong. Line 8 is circled: the page belongs to a different case, and no case by that name exists in the volume. Line 9 is in pencil: the free library just doesn't have that reporter. Both would be 'not found' to a naive lookup. Every row prints the rule that fired, and the evidence is one click away: the actual reporter page, or the shelf showing where the free library stops." |
| 1:35–1:55 | line 15 (Zicherman, 230 struck, 217 above) and line 18 (Iqbal, quote underlined, "closest passage {sim}% similar") | "Real case, wrong page: the memo corrects it. Real case, quote not in the opinion: the memo underlines the words and shows the closest passage." |
| 1:55–2:25 | Evaluation tab; the closing sentence; per-stage seconds; How it works, scroll past the 9-step rule and the credits | "We scored it against twenty citations with known answers. Real cases marked as likely not real: the number on screen. The rule is deterministic and printed in full. The Caselaw Access Project, Free Law Project's eyecite, and Princeton CITP's work on citation verification made this possible." |
| 2:25–2:45 | [Print memo] print preview, one letter page; back to the memo; **Drop your own PDF** | "The memo prints to one page for the file. Try your own PDF at the link." |
| 2:45–3:00 | the disclaimer line, then the "Not checked" rows | "Limits: it checks whether cited cases exist in a free library and whether quoted words appear in them. It does not judge the argument, it skips statutes and short-form cites, it cannot check pin pages, and cases after 2014 in U.S. Reports are outside the free library. It is a triage aid, not a finding." |

## 3. Journey + screen inventory (lite)

| id | route | why it exists | entered from | primary action | states |
|---|---|---|---|---|---|
| S1 | `/` (no query) | the memo sheet with an empty RE: and the drop target typed as the body; the user's first sight when they arrive without the demo flag | direct | drop / Choose a PDF / Use the sample filing | first-run, blocked (not a PDF, >20 MB) |
| S2 | same page | the run: RE: fills, the four planned steps and the live timer show, then the memo returns | S1, S3 | wait; dropping another file cancels and restarts | loading, partial, error |
| S3 | `/?demo=1` (default on the live URL) | the populated memo over the sample; the artifact | S2, direct | Show the page / Show the shelf; Drop your own PDF | ideal, no-results |
| S4 | same page, one row expanded | the reporter page (or the shelf) as evidence under the row | S3 | Hide the page; open another row | loading, error, metadata-only |
| S5 | tab Evaluation | ground truth vs memo, false-positive count, per-stage seconds | tabs | read; click a line number to jump to that memo row | loading, error |
| S6 | tab How it works | the 9-step rule, sources, live-vs-optional table, limits, credits | tabs | read | — |

Demo plumbing: `?state=first-run|loading|partial|error|no-results` renders each state from `web/static/fixtures/*.json`; `?demo=1` runs `POST /api/memo/sample/sample-motion` (from cache when `CITEMEMO_OFFLINE=1`) and paints S3 with the stamp already on it; Alt+Shift+R (`e.code === "KeyR"`) or `?reset=1` clears to S1; Alt+Shift+P (`e.code === "KeyP"`) paints `seed/replay.json` with the replay banner. The tab is in the URL hash (`#memo`, `#evaluation`, `#how`) and survives refresh; an open row is `#line-6`.

## 4. Flow map

```
S1(first-run) --drop / Choose a PDF--> S2(loading) --memo returns--> S3(populated)
S1 --Use the sample filing--> S2 --returns--> S3
S1 --not a PDF / >20 MB--> S1(blocked: sentence under the buttons, input kept)
S2 --server error--> S1(error: sentence in the body, RE: keeps the file name) --Try again--> S2
S2 --some rows timed out--> S3(partial: pencil "Could not reach the free library." + [Retry {n} citations]) --Retry--> S2(those rows only)
S2 --0 citations--> S3(no-results: one typed paragraph, drop target kept)
S3 --[Show the page] / [Show the shelf]--> S4 --[Hide the page]--> S3 ; S4 --another row's link--> S4(content swapped, no re-animation)
S3 --Drop your own PDF--> S2 ; S3 --tab--> S5 | S6 --tab Memo--> S3
any --Alt+Shift+R--> S1 ; any --Alt+Shift+P--> S3(replay banner)
```

## 5. Screens

### S3 The populated memo (demo-critical; S1, S2 and S4 are states of the same sheet)

**Meaning:** a memo the clerk would have written by hand after an afternoon of lookups. The object in the user's head is the sheet on their desk. Feeling: careful.

**Attention inventory:** primary = the citation rows with their marks and margin notes · secondary = the heading block with the CHECKED stamp and the primary button; the "Read these first" foot paragraph · tertiary = pleading line numbers; the rule sentence under each note; the disclaimer; the credits line under the sheet · interactive = [Show the page] / [Show the shelf] per row; **Drop your own PDF**; folder tabs; [Print memo]; the foot paragraph's count links · decorative = the sheet's shadow on the surround (deletable).

**Blueprint and grid at 1440×900:** page background `--surround`; the sheet `--canvas` 816px wide (8.5in at 96dpi), centered, `min-height: 100vh`, `box-shadow: var(--shadow-raised)`, padding 64px 72px 72px 0. Inside the sheet, a two-column grid: the pleading margin 56px (line numbers 12px `--ink-muted`, right-aligned with 12px right padding, one 1px `--line` rule at x=56 running the full sheet height) and the content column. The content column is itself a grid: `grid-template-columns: 1fr 240px; column-gap: 24px` for rows; the heading block and foot paragraph span both columns. Folder tabs (36px tall) sit on the sheet's top edge, left-aligned at x=56, above the sheet's padding, so the active tab is continuous with the paper. The credits line sits 16px under the sheet in 13px `--ink-muted` on `--surround`.

**1024×768:** identical sheet at 816px, surround 104px either side. **≤900:** sheet full width, no surround, no shadow, padding 20px 16px 40px 0, margin 32px (line numbers 12px, 8px right padding), rows collapse to one column (`grid-template-columns: 1fr`) with the margin note under the citation as its first line, 8px gap; the reporter panel spans the full content width. **320:** the citation wraps to two lines; marks follow the wrap rule in C-02.

**First 10 seconds:** the heading block and rows 1–8 are inside the first viewport at 1440×900 (heading 168px + rule 24px + 8 rows at 56–72px); the first red circle (line 6) is visible without scrolling. At 390×844: heading with the stamp and the **Drop your own PDF** button, the disclaimer, and lines 1–3.

**Data:** `POST /api/memo/sample/sample-motion` on `?demo=1` (live, cached); `POST /api/memo` on a drop (live); fixtures under `web/static/fixtures/` for `?state=`. Sample label typed into RE: from `memo.filing.label`.

| Element | Tier | Register | Levers (grayscale first) | States | Transition |
|---|---|---|---|---|---|
| Citation rows (the memo body) | primary | productive | the largest region; each row a numbered typed line: citation 15px/400 Courier Prime `--ink`, then the filing page "p. 4" 13px `--ink-muted`; rows `min-height: 56px`, separated by 12px spacing only, no rules between rows; the marks are the only non-ink marks on the sheet, graded by weight: full red ellipse around the whole citation (likely not real) · red ellipse around the reporter abbreviation only (no reporter by this name) · red strike through the page number with the correct page written above in 13px red (exists, not at this page) · thin red underline under the quoted words (quote not in the opinion) · pencil dashed underline under the citation (not in the free library) · typed ✓ in ink before the note (found) · none, row text in `--ink-muted` (not checked) | loading: no rows; the body shows the status line (see below) · partial: rows that timed out keep the pencil note "Could not reach the free library." and no mark · error: no rows; the body carries the error sentence and keeps the drop target · empty: one paragraph "No case citations found in {pages} pages. …" and the drop target | rows reveal in filing order (opacity 0→1, translate y 6→0, 120 ms, 30 ms stagger, capped at 600 ms total); then marks draw on in row order (pathLength 0→1, 300 ms, 60 ms stagger) once; notes appear with their rows (no typing effect) |
| Margin note (class label + rule sentence) | primary (part of the row) | serious for flagged rows, productive otherwise | first line 14px/700 Courier Prime: `--pen` for the four red-marked classes, `--pencil` for not in the free library / not checked / could not reach, `--ink` for found; under it the rule sentence 14px/400 `--ink-muted`, up to 2 lines with `-webkit-line-clamp: 2`, the full text in the expanded panel; the label always carries a word and a mark shape, never color alone | pin cite present: the rule sentence appends "Pin page not checked." · advisory: appends "Advisory: supports" / "does not support; read this first" / "cannot tell" / "not run" in `--ink-muted` | none (it is the residue) |
| [Show the page] / [Show the shelf] | interactive | productive | typed bracket link 14px Courier Prime `--ink`, at the row's end; underline on hover (fine pointer); focus-visible = 2px `--focus` outline offset 2; toggles to [Hide the page] / [Hide the shelf] | which link: `source == "CAP"` and a case at the page → [Show the page]; `evidence.volume_range` present and no case → [Show the shelf]; WL/LEXIS or unrecognized reporter → no link, and the rule sentence already says why ("no free text exists" / "no reporter by this name") | the panel opens under the row over 200 ms `--ease-out-quint` via `grid-template-rows: 0fr → 1fr`; a second row's link swaps content with no animation |
| Reporter page excerpt (C-04) | secondary when open | productive | a panel on `--surface-1` (cooler reporter paper), 1px inset `--line`, padding 16px 20px, spanning the content column; running head 12px small caps Source Serif 4 `--ink-muted` ("925 F.3d 1291 · J.D. v. AZAR · D.C. Cir. · June 14, 2019"), page marker "1339" 15px/700 Source Serif 4 `--ink` at the right, then 14px/1.6 Source Serif 4 `--ink` text; a footer line 12px Courier `--ink-muted` with the CAP URL(s) | loading: running head first, two skeleton lines in `--surface-2` (1.5 s shimmer; static under reduced motion) · error: "Could not load the opinion text; the details above come from the volume listing." · metadata-only (endpoint absent): name, court, date, pages and the sentence "Opinion text not loaded in this build." | open/close only |
| Shelf strip (C-04, shelf variant) | secondary when open | productive | the same `--surface-1` panel; a 12px-tall strip of volumes drawn from `evidence.volume_range`: held volumes a filled `--ink-muted` band, volumes beyond the library outlined 1px `--line-input` on `--canvas`, the cited volume a 2px `--pen` tick with its number above in 12px Courier; for wrong-page rows the strip is the case's page span with 217 and 230 bracketed; labels 12px Source Serif 4 `--ink-muted` under the strip ("U.S. Reports · volumes 1–572 in the free library · cited: 600") | error: the sentence "Could not load the volume list." | open/close only |
| Heading block (MEMORANDUM · TO · FROM · RE · DATE · CHECKED AGAINST) | secondary | system | Courier Prime 15px; labels 700 uppercase `letter-spacing: 0.10em` ("TO:", "RE:"), values 400 `--ink`; label column 112px; 8px between lines; a 2px double rule (`border-bottom: 1px solid var(--line)` + a second 1px line 3px below) under the block; the disclaimer sentence right under the rule in 14px `--ink`, then the litigant sentence 14px `--ink-muted` | first-run: RE: shows "________" and the body is the drop target · loading: RE: shows the file name and "{pages} pages" once extraction returns, otherwise the file name alone · replay: DATE: carries the recorded date; the replay banner sits above the tabs | none |
| CHECKED stamp | secondary | celebratory-lite | a 2px `--pen` box, radius 2px, rotated −2°, at the heading's right, 176px wide, padding 8px 12px; 4 typed lines Courier Prime 700 uppercase 0.08em in `--pen`: "CHECKED" 18px, then 14px "{DD Mon YYYY HH:MM}", "{n} citations in {elapsed} s", "Caselaw Access Project" (+ " · CourtListener" when used); the only red that isn't a mark | absent before a run; static on `?demo=1` first paint; replay: "REPLAY" replaces "CHECKED" and the date line reads "run of {date time}" | scale 1.08→1 with opacity 0→1 over 180 ms `--ease-out-quint`, only when a live run completes in this tab; no sound |
| **Drop your own PDF** (C-07) | interactive (S3 primary) | productive | the one filled button: `--button-bg` ink, `--button-ink` paper label, Courier Prime 700 15px, h40, padding 0 16px, radius 2px; sits under the stamp at the heading's right, right-aligned; at ≤900 it moves under the heading lines, full width, h44 | hover: `--button-hover` 150 ms · press: scale .97, 120 ms · focus-visible: 2px `--focus` outline offset 2 · in flight: `aria-disabled="true"`, label stays, clicks ignored | none |
| Foot paragraph ("Read these first") | secondary | productive | a typed closing paragraph, not tiles: 15px Courier Prime `--ink`, `max-width: 60ch`; each count a bracket-less underlined link that scrolls to that class's first row and focuses its line number; counts `font-variant-numeric: tabular-nums` | empty: omitted · partial: appends "{n} not answered yet." | none |
| Pleading line numbers + margin rule | tertiary | system | 12px `--ink-muted` Courier Prime, right-aligned in the 56px margin, one per row (the row id "line 7" is what the status region, the eval table and `#line-7` use); a single 1px `--line` rule at x=56 | the focused row's line number is `--ink` 700 | — |
| Folder tabs (Memo · Evaluation · How it works) | interactive | system | 36px tabs on the sheet's top edge; active = `--canvas` continuous with the sheet, 15px/700 `--ink`; inactive = `--tab-inactive`, 15px/400 `--ink-muted`; radius 2px top corners, 0 at the bottom; padding 0 16px; 2px gap between tabs; `role=tablist`, ←/→, Home/End | hover (inactive): `--surface-2` · focus-visible: 2px `--focus` outline inset | content swaps instantly (tens-of-times-a-day rule), no animation |
| Drop target (S1 body) | interactive (S1 primary) | productive | typed on the sheet, not a dashed box: the sentence "Drop a filed PDF here, or" then **Choose a PDF** (the one filled button, h40) then "Use the sample filing" as a tonal `--surface-2` button (h40, `--ink` label, radius 2px) followed by "(synthetic, 6 pages)" in `--ink-muted`; under them the privacy sentence 14px `--ink-muted`; the whole sheet is the drop area | drag-over: the sheet body gets a 2px `--line-input` inset outline, and the sentence reads "Release to check this PDF." · blocked (not a PDF / >20 MB): the sentence under the buttons names the reason in `--ink`; the input keeps its value | none |
| Status line (C-09) | system | system | one typed block at the body's top while loading: four planned steps, each "○ {step name}" 15px Courier `--ink-muted` on its own line, then "Elapsed {t} s" 14px `--ink` updating every 100 ms from `performance.now()`; `role=status aria-live=polite` (the live region announces the start and the end only, not the timer) | done: all four circles become "●" with the real per-stage seconds from `memo.timings` beside each ("● Looking up the free library · 3.1 s"), the block reads "Done in {elapsed} s." for 1 s, then collapses (height via grid 1fr→0fr, 150 ms) as the rows reveal · error: the block is replaced by the error sentence | collapse only |
| [Print memo] | interactive | productive | typed bracket link 14px Courier at the sheet's foot, after the foot paragraph; `@media print` hides surround, tabs, links, buttons, the status line and the replay banner; letter, 0.75in margins; marks stroke 2px | — | — |
| Sheet shadow + surround | decorative | — | `--shadow-raised` on the sheet over `--surround` at ≥1024 only; the sheet is the only raised object; the credits line 13px `--ink-muted` under the sheet | absent below 1024 and in print | — |

**Grouping:** spacing, then tint (reporter paper), then the two rules the memo already has (double rule, margin rule); no shadows inside the sheet; no cards.

**Pacing (one viewport):** heading block (dense typed block) → body (open rows with marks) → foot (paragraph). Neighbors differ in density and layout family.

**Type rule (one decision):** Courier Prime is everything the clerk typed: the memo's heading, citations, notes, rule sentences, the foot paragraph, buttons, tabs, and the Evaluation and How-it-works sheets. Source Serif 4 is only what the book printed: the reporter page panel and the shelf strip labels. Pencil vs pen carries the note's register, not a second typeface.

### S5 Evaluation (secondary screen, same sheet)

The same 816px sheet. Heading: "EVALUATION" (Courier 700 uppercase 0.10em), one line "20 citations with known classes, from seed/ground_truth.json; scored on the last run of the sample." Then C-05 the eval table, then the closing paragraph, then the per-stage seconds as a typed list ("Reading the PDF · {t} s" …), then a line "Class keys: likely_fabricated = Likely not a real case · not_in_free_corpus = Not in the free library · wrong_cite_exists = Exists, but not at this page · quote_not_found = Found, but this quote is not in the opinion · unrecognized_reporter = No reporter by this name · verified = Found · skipped = Not checked". Data: `GET /api/eval`. Loading: table skeleton (rows of `--surface-2` blocks). Error: "Could not load the evaluation. [Try again]".

### S6 How it works (secondary screen, same sheet)

Typed sections in Courier Prime 15px with 700 uppercase run-in headings: What it checks · The rule (the 9 steps, numbered in the pleading margin) · Sources · Live and optional (a two-column typed table) · Limits · Credits. Copy in §9.

## 6. Components

### C-01 DropTarget   (base: native `<input type=file>` + the sheet as drop area, custom)
Purpose: put a filed PDF into the memo.
Tier / register: interactive (S1 primary) · productive
Placement: screen=S1 region=body order=1 align=start sticky=no; the whole sheet is the drop area (`dragover` on the sheet element). Mobile: same; the buttons stack, full width, h44.
Size: sentence 15px Courier `--ink`, `max-width: 60ch`; **Choose a PDF** h40 px16 radius 2px `--button-bg`/`--button-ink` Courier 700 15px; **Use the sample filing** h40 px16 radius 2px `--surface-2` fill `--ink` label Courier 400 15px; 12px gap between the two; the privacy sentence 14px `--ink-muted` 16px below.
Tokens: bg none (the sheet) · drag-over outline 2px `--line-input` inset · focus 2px `--focus` outline offset 2.
States:
  idle ........ "Drop a filed PDF here, or [Choose a PDF]. [Use the sample filing] (synthetic, 6 pages)." + privacy sentence
  hover ....... Choose a PDF: `--button-hover` 150 ms; sample: one state-layer darker (`color-mix(in oklch, var(--surface-2), black 8%)`)
  press ....... scale .97, 120 ms
  focus-visible 2px `--focus` outline, offset 2
  drag-over ... sheet body outline 2px `--line-input` inset; the sentence reads "Release to check this PDF."
  blocked ..... not a PDF: sentence under the buttons "This file is not a PDF. Choose a PDF saved from a word processor, or use the sample filing." in `--ink`; >20 MB: "This PDF is larger than 20 MB. This prototype reads files up to 20 MB."; the input keeps its value; `aria-describedby` points at the sentence
  loading ..... hands off to C-09; the buttons get `aria-disabled="true"` and ignore clicks (no native disabled)
  error ....... the server's sentence replaces the privacy sentence; RE: keeps the file name; "[Try again]" resubmits the same file
Transitions: idle -DRAGENTER-> drag-over -DROP(pdf ≤20 MB)-> loading ; drag-over -DROP(other)-> blocked ; idle -CHOOSE-> loading ; idle -SAMPLE-> loading ; loading -RETURN-> S3 ; loading -FAIL-> error -TRY AGAIN-> loading
Motion: none (T-00)
Responsive: ≤900 the two buttons stack with 8px gap, each full width h44.
Keyboard / a11y: the input is the real `<input type=file accept="application/pdf">` behind **Choose a PDF** (label wraps input); Enter/Space on the sample button; status region announces "Reading {file name}." on start.
Data: `POST /api/memo` multipart `file`; sample = `POST /api/memo/sample/sample-motion`; the sample label is typed into RE: from `memo.filing.label`.
Acceptance: `?state=first-run` and `?state=error` render at 320 and 1440; blocked renders by dropping a .txt; the input keeps its file across blocked.

### C-02 MemoRow   (base: native `<li>` inside `<ol>`, custom marks)
Purpose: one citation from the filing with the clerk's mark and note beside it.
Tier / register: primary · productive (serious when the mark is red)
Placement: screen=S3 region=body order=n (filing order) align=stretch; grid `1fr 240px`, gap 24px; the line number in the pleading margin. Mobile (≤900): one column; the note becomes the first line under the citation, 8px gap.
Size: `min-height: 56px`; row padding 6px 0; 12px between rows; citation 15px/1.55 Courier `--ink`; filing page 13px `--ink-muted` after a 12px gap; the mark is an absolutely positioned inline `<svg>` overlaying the citation span, `pointer-events: none`, `overflow: visible`.
Tokens: text `--ink`; not-checked rows `--ink-muted`; marks `--pen` or `--pencil`; stroke `--mark-stroke` (1.5px; 2px in print); hover (fine pointer) `--surface-2` row background at −8px inset.
Marks (drawn after `document.fonts.ready`, measured with `Range.getBoundingClientRect()` on the target span, redrawn on `resize` via ResizeObserver on the sheet):
  circle-all ...... likely not a real case: a closed cubic path around the citation's box with 6px horizontal and 3px vertical overshoot, rotated −2°, start point at 10 o'clock so the draw-on ends where a pen lifts
  circle-reporter . no reporter by this name: the same path around the reporter abbreviation span only ("Fed. Air Rptr. 3d")
  strike-correct .. exists, not at this page: a 1.5px line through the page-number span with a 2px rise left to right; the correct page in 13px/700 `--pen` Courier positioned 14px above the struck number
  underline-quote . quote not in the opinion: a 1.5px `--pen` line 2px under the quoted words' span in the row (the quote is shown as the row's second line, 14px `--ink-muted`, ≤2 lines)
  underline-pencil  not in the free library / could not reach: `stroke-dasharray: 4 3` `--pencil` 1.5px under the citation span
  check ........... found: the typed glyph "✓" in `--ink` before the note (no SVG)
  none ............ not checked
Wrap rule: if the target span's `getClientRects().length > 1` (the citation wrapped), circle-all draws around the first line's rect only and a 1.5px `--pen` underline runs under the remaining rects; circle-reporter and strike-correct are unaffected (their spans do not wrap; if one does, fall back to the underline).
States:
  idle ........ citation + filing page; note + rule sentence; the link
  hover ....... row background `--surface-2` (fine pointer only), 150 ms
  focus-visible the row's link carries the ring; the line number turns `--ink` 700
  expanded .... `aria-expanded="true"` on the link; the C-04 panel sits under the row inside the same `<li>`
  unresolved .. (partial) pencil note "Could not reach the free library." no mark
  not-checked . text `--ink-muted`, note "Not checked (Id., supra or short form)." or "(statute)"
  target ...... after a foot-paragraph link jump: the line number `--ink` 700 and the row background `--surface-2` for 1.5 s, then normal (color transition 200 ms)
Transitions: hidden -RETURN-> idle (T-01) -MARKS-> marked (T-02) ; idle -LINK-> expanded (T-04) -LINK-> idle
Motion: T-01, T-02, T-04
Responsive: ≤900 one column; the mark overlay re-measures on resize and on font load; 320 wrap rule applies.
Keyboard / a11y: the `<ol>` has `aria-label="Citations in filing order"`; each `<li>` has `id="line-{n}"`; the mark svg is `aria-hidden="true"` (the note carries the meaning in words); the note is `aria-describedby` for the link.
Data: `memo.results[i]` (`class`, `reasons[]`, `evidence{}`, `source`, `links[]`, `quote_check{}`, `pincite_unverified`, `advisory{}`), `citation.span` for the filing page.
Acceptance: the fabricated, wrong-page and unrecognized-reporter marks render at 320, 390, 1024, 1440 (qa/qa.mjs screenshots); no mark overflows the sheet; marks reposition after a viewport resize without a reload.

### C-03 ClassNote   (the memo's status chip; base: custom text block)
Purpose: tell a non-lawyer what the memo found for this row and which rule said so.
Tier / register: primary (part of C-02) · serious (red) | productive (ink, pencil)
Placement: screen=S3 region=row note column (240px) order=2 align=start. Mobile: first line under the citation.
Size: label 14px/700 Courier `letter-spacing: 0`; rule sentence 14px/400 `--ink-muted` `--lh-memo`, `-webkit-line-clamp: 2`; 4px between label and rule; the advisory / pin-cite sentence appended to the rule text.
Tokens: label `--pen` (likely not real · no reporter by this name · exists, not at this page · quote not in the opinion) · `--pencil` (not in the free library · could not reach · not checked) · `--ink` (found).
States (label · mark · rule sentence source):
  found ............... "Found. Quote matches." or "Found." · ✓ · `reasons[0]`
  quote_not_found ..... "Found, but this quote is not in the opinion." · underline-quote · "Closest passage {similarity}% similar."
  wrong_cite_exists ... "Exists, but not at this page." · strike-correct · "{case} begins at {first_page}; page {page} is inside it."
  not_in_free_corpus .. "Not in the free library. Check Westlaw or Lexis." · underline-pencil · "U.S. Reports volumes after 572 are not in the Caselaw Access Project." / "Westlaw-only citation; no free text exists." / "Volume {v} is missing from the free library."
  unrecognized_reporter "No reporter by this name." · circle-reporter · "No reporter called '{R}' in reporters_db or the Caselaw Access Project."
  likely_fabricated ... "Likely not a real case." · circle-all · "Page {p} belongs to {real case}, {v} {R} {first}–{last}. No case named {party} in volume {v}." / "{R} did not publish in {year} (edition runs {start}–{end})." / "Volume {v} ends at page {max}." / "Volume {v} does not exist yet: {R} reached {vmax} by the library's end year."
  skipped ............. "Not checked (Id., supra or short form)." / "Not checked (statute)." · none · —
  checking (partial) .. "Could not reach the free library." · none · "Timed out after 20 s. [Retry {n} citations] at the foot."
Transitions: driven by C-02.
Motion: none.
Responsive: at ≤900 the label sits under the citation; the rule sentence keeps its 2-line clamp.
Keyboard / a11y: the label and rule are plain text; `aria-describedby` from the row's link; the label never relies on color: word + mark shape.
Data: `result.class`, `result.reasons`, `result.quote_check.similarity`, `result.pincite_unverified`, `result.advisory.verdict`.
Acceptance: every class appears at least once in `?demo=1`; a screen reader reads label then rule; label text matches §9 exactly.

### C-04 EvidenceDrawer   (the reporter page and the shelf; base: custom, `grid-template-rows` toggle)
Purpose: show the page the citation points at, or where the free library's shelf stops, without leaving the row.
Tier / register: secondary · productive
Placement: screen=S4 region=inside the row's `<li>`, under the citation and note, spanning the content column (both grid columns) order=3 align=stretch. Mobile: full content width.
Size: panel padding 16px 20px; margin 8px 0 4px; `--surface-1` background; 1px inset `--line`; running head 12px small caps Source Serif 4 `--ink-muted` `letter-spacing: 0.04em`; page marker 15px/700 Source Serif 4 `--ink` right-aligned on the same line; text 14px/1.6 Source Serif 4 `--ink` `max-width: 64ch`; footer 12px Courier `--ink-muted` 12px above the panel's bottom with the CAP URL(s) as links; shelf strip 12px tall, full panel width, 8px above its labels.
Tokens: bg `--surface-1` · border `--line` · red words `--pen` (5.444:1 on surface-1) · skeleton `--surface-2`.
States:
  closed ...... `grid-template-rows: 0fr`; `aria-expanded="false"` on the link; content `inert`
  opening ..... 0fr→1fr, 200 ms `--ease-out-quint`; the running head is in the DOM immediately
  loading ..... running head from `result.evidence.real_case_at_page` at once; two skeleton lines 14px tall in `--surface-2` (1.5 s shimmer; static under reduced motion); `GET /api/evidence/{row}` in flight
  page ........ head "{vol} {R} {first_page} · {NAME_ABBREVIATION uppercase} · {court} · {decision_date}", marker "{page}", about 200 characters around the closest passage (quote rows: the differing words carry a 1.5px `--pen` underline and the head appends "closest passage, {similarity}% similar") or around the page start (fabricated and wrong-page rows: the head appends "begins at {first_page}"); footer: CAP URLs
  shelf ....... for not_in_free_corpus beyond coverage, volume-past-end and wrong-page rows: the strip (held volumes filled `--ink-muted`; beyond the library outlined `--line-input` on `--canvas`; the cited volume a 2px `--pen` tick with its number 12px Courier above); labels: "U.S. Reports · volumes 1–572 in the free library · cited: 600" / for wrong page: "Zicherman ex rel. Estate of Kole v. Korean Air Lines Co. · pages 217–232 · cited: 230" with 217 and 230 bracketed
  metadata-only (endpoint absent or 404) head and marker as above; the sentence "Opinion text not loaded in this build." 14px `--ink-muted`
  error ....... "Could not load the opinion text; the details above come from the volume listing." (page) / "Could not load the volume list." (shelf); the head stays
Transitions: closed -LINK-> opening -200ms-> loading -200 OK-> page|shelf ; loading -FAIL-> error ; open -LINK-> closed ; open(row a) -LINK(row b)-> open(row b) with content swapped and no height animation on b (a closes at 150 ms `--ease-exit`)
Motion: T-04 (open), T-05 (swap)
Responsive: ≤900 full content width; the running head wraps to two lines; the marker stays right-aligned on the first.
Keyboard / a11y: the link is a `<button aria-expanded aria-controls="evidence-{n}">`; on open, focus moves to the panel's heading (`tabindex="-1"`); Esc or [Hide the page] closes and returns focus to the link; the strip has `role="img"` with an `aria-label` equal to its label text.
Data: `GET /api/evidence/{row}` → `{running_head, page_marker, text, highlight:[start,end] | null, urls[]}`; shelf from `result.evidence.volume_range` (`{held_min, held_max, cited}`) or `real_case_at_page` (`{first_page, last_page}`) already in the memo JSON.
Acceptance: `?demo=1#line-6` opens the page on load with J.D. v. Azar in the head; `#line-23` opens the shelf; only one panel animates on a swap; both render at 320 and 1440; the print stylesheet prints an open panel.

### C-05 EvalTable   (base: native `<table>`)
Purpose: show that the memo's classes were measured against known answers.
Tier / register: primary on S5 · productive
Placement: screen=S5 region=body order=2 align=stretch; the line numbers of the memo in the pleading margin as the first column. Mobile: rows collapse to stacked items (`display: grid` per row; the cells labelled with `data-label` pseudo-elements).
Size: rows 40px; cells padding 8px 12px 8px 0; header 13px/700 uppercase 0.08em `--ink-muted` Courier with a 1px `--line` rule under it (the sheet's third rule, justified because a table needs a head); body 14px Courier `--ink`; `font-variant-numeric: tabular-nums`; columns: line (48px) · citation (1fr) · expected (168px) · memo said (168px) · match (64px).
Tokens: bg none · header rule `--line` · match "yes" `--ink`, "no" `--pen` 700 (word + weight, not color alone) · the closing sentence's "0" in `--success` only when it is 0, otherwise `--ink`.
States:
  loading ..... 20 skeleton rows in `--surface-2`
  ideal ....... 20 rows; closing paragraph "Real cases marked likely not real: {fp} of {real}. Correct classes: {c} of 20." then per-stage seconds
  mismatch .... rows with match "no" carry `--pen` 700 on "no" and the memo's rule sentence under the row in 13px `--ink-muted`
  either-accepted rows whose expected class lists two accepted classes (the two beyond-coverage rows) show "not in free library or found" in the expected cell
  error ....... "Could not load the evaluation. [Try again]"
  stale ....... when `/api/eval` reports the last run older than the current memo: one line above the table "Scored on the run of {date time}. [Re-run the sample]"
Transitions: loading -200-> ideal|mismatch ; loading -FAIL-> error
Motion: none (tabs swap instantly)
Responsive: ≤900 stacked rows, 12px between; header hidden, `data-label` prefixes shown.
Keyboard / a11y: `<caption>` "Twenty citations with known classes, scored on the last run"; `scope="col"` headers; each line number is a link to `#line-{n}` on the Memo tab.
Data: `GET /api/eval` → `{items:[{line, cite_text, expected_class, accepted_classes, predicted, match}], accuracy, real_marked_fabricated, real_total, timings{}}`.
Acceptance: the closing numbers equal the JSON's; `grep -E '[0-9]+ of 20' web/index.html` returns nothing (no literal numbers in the built page); renders at 320 and 1440.

### C-06 ReplayBanner   (base: custom, one line above the tabs)
Purpose: say plainly that what is on screen is a recorded run, not a live one.
Tier / register: system · system
Placement: screen=any region=above the folder tabs, on the surround at ≥1024 (13px `--ink-muted` on `--surround`, 5.702:1) and on the sheet's top edge below 1024 (13px `--ink-muted` on `--canvas`) order=0 align=start. Print: hidden.
Size: h28; 13px Courier `--ink-muted`; padding 0 0 6px 56px (aligned with the content column).
Tokens: text `--ink-muted`; link `--ink` underlined.
States:
  hidden ...... default; live runs and `?demo=1`
  replay ...... "Replay · run of {date time} from seed/replay.json. Marks and seconds are from that run. [Run it live]"
  offline ..... when `CITEMEMO_OFFLINE=1`: "Offline · answers come from the cached free-library files of {date}."
  pending ..... when `seed/replay.json` is missing: "No replay recorded yet. Run scripts/record_replay.py."
Transitions: hidden -Alt+Shift+P-> replay -[Run it live]-> hidden (S2 starts) ; hidden -offline env-> offline
Motion: none
Responsive: wraps to two lines below 480.
Keyboard / a11y: `role=status`; the link is a real link; the stamp's first line also changes to "REPLAY", so the state is on the artifact and not only in the banner.
Data: `seed/replay.json` (`recorded_at`, `memo`), `GET /api/health` (`offline: true|false`).
Acceptance: Alt+Shift+P shows the banner and the REPLAY stamp within 100 ms; the banner is not in the print; renders at 320 and 1440.

### C-07 PrimaryButton   (base: native `<button>` / `<label>`)
Purpose: the one filled action per screen (Choose a PDF on S1; Drop your own PDF on S3).
Tier / register: interactive · productive
Placement: S1 body inline after the drop sentence; S3 heading right, under the stamp, right-aligned (≤900: under the heading lines, full width).
Size: h40 (h44 ≤900), padding 0 16px, radius 2px, Courier Prime 700 15px, letter-spacing 0.
Tokens: bg `--button-bg` · label `--button-ink` · hover `--button-hover` · press `--button-press` · focus 2px `--focus` outline offset 2.
States: idle · hover (150 ms, fine pointer) · press (scale .97, 120 ms) · focus-visible · in-flight (`aria-disabled="true"`, label unchanged, clicks ignored; the status line carries progress).
Transitions: idle -CLICK-> in-flight -RETURN|FAIL-> idle
Keyboard / a11y: Enter/Space; on S3 the button opens the file picker directly (it is a `<label for=file>` styled as the button) and drops are accepted anywhere on the sheet.
Acceptance: exactly one filled button exists on S1 and one on S3 (`document.querySelectorAll('.button-primary').length === 1` per state).

### C-08 FolderTabs   (base: native buttons with `role=tablist`)
Purpose: move between the memo and its two supporting sheets.
Tier / register: interactive · system
Placement: on the sheet's top edge, left-aligned at x=56, 2px gap; ≤900 at x=32.
Size: h36; padding 0 16px; 15px Courier; radius 2px 2px 0 0.
Tokens: active `--canvas` + `--ink` 700; inactive `--tab-inactive` + `--ink-muted`; hover `--surface-2`; focus 2px `--focus` outline inset.
States: active · inactive · hover · focus-visible.
Keyboard / a11y: ←/→ move and activate, Home/End; `aria-selected`; panels `role=tabpanel` with `aria-labelledby`; the hash updates (`#memo`, `#evaluation`, `#how`).
Motion: none (content swaps instantly).
Acceptance: refresh on `#evaluation` restores the tab; the active tab has no bottom edge line (it is continuous with the paper).

### C-09 StatusLine   (base: custom, `role=status`)
Purpose: tell the user what the server is doing while one JSON response is pending, without counting anything it cannot know.
Tier / register: system · system
Placement: S2 body top, replacing the drop target; collapses when rows reveal.
Size: four lines 15px Courier `--ink-muted` with "○ " prefix, 4px apart; then "Elapsed {t} s" 14px `--ink` tabular, updated every 100 ms; 24px below the heading rule.
States:
  waiting ..... "○ Reading the PDF" / "○ Finding citations" / "○ Looking up the free library" / "○ Matching quotes" / "Elapsed 2.3 s"
  done ........ every "○" becomes "●" with the real per-stage seconds appended ("● Looking up the free library · {t} s"); the last line reads "Done in {elapsed} s."; held 1 s; then collapses (T-03)
  partial ..... done, plus "The free library did not answer for {n} citations (timed out)." with [Retry {n} citations]
  error ....... replaced by the error sentence (§9) and the drop target
  slow ........ after 10 s: appends "Still working. Large filings take longer; the page stays here." (no counter)
Transitions: waiting -RETURN-> done -1s-> collapsed ; waiting -FAIL-> error ; waiting -RETURN(partial)-> partial
Keyboard / a11y: `role=status aria-live=polite`; announces "Reading {file}." once at start and "Done in {elapsed} seconds. {n} citations." once at the end; the timer is `aria-hidden`.
Data: `performance.now()` for the timer; `memo.timings` for the per-stage seconds; the four step names are fixed copy (they are the pipeline's stages, not progress claims).
Acceptance: `?state=loading` shows the four hollow circles and a running timer; no digit other than the timer appears while waiting.

### C-10 Stamp   (base: custom `<div>`)
Purpose: the run record on the artifact.
Tier / register: secondary · celebratory-lite
Placement: S3 heading, right column, top-aligned with "MEMORANDUM"; ≤900 under the heading lines, left-aligned, 148px wide.
Size: 176px wide, padding 8px 12px, border 2px `--pen`, radius 2px, `transform: rotate(-2deg)`; lines Courier 700 uppercase 0.08em `--pen`: 18px "CHECKED", 14px date, 14px count and seconds, 14px sources.
States: absent (S1, S2) · checked (live or `?demo=1`) · replay ("REPLAY" / "run of {date time}" / count and seconds / sources) · partial ("CHECKED · {n} unanswered" on the count line).
Motion: T-03 only when a live run completes in this tab; static otherwise.
Keyboard / a11y: `aria-label="Checked {date time}, {n} citations in {elapsed} seconds, sources {list}"`.
Data: `memo.checked_at`, `memo.counts.total`, `memo.timings.total_s`, `memo.sources_used`.
Acceptance: no literal date, count or seconds in the HTML; prints in red at 2px stroke on letter.

## 7. Choreography

| id | trigger | from → to | what moves | pattern | timing / token |
|---|---|---|---|---|---|
| T-00 | drop / choose / sample | S1 → S2 | the drop sentence is replaced by the status block; RE: fills with the file name | swap (no animation; the request has started) | 0 ms |
| T-01 | memo JSON returns | S2 status block → S3 rows | rows reveal in filing order: opacity 0→1, translate y 6→0 | staggered enter | `--dur-row` 120 ms, `--stagger-row` 30 ms, capped at 600 ms total (later rows share the last slot) |
| T-02 | last row revealed | rows → marked rows | the pen goes down the sheet: each flagged row's SVG mark draws `stroke-dashoffset` from pathLength to 0 in row order; pencil underlines and checks appear in the same pass | draw-on onto its cause | `--dur-mark` 300 ms `--ease-out-quint`, `--stagger-mark` 60 ms; a 23-row memo with 11 marks finishes in about 0.9 s |
| T-03 | last mark drawn (live run only) | heading → heading with stamp | the stamp lands: scale 1.08→1, opacity 0→1; at the same moment the status block collapses (`grid-template-rows` 1fr→0fr) and the foot paragraph appears (opacity 0→1, 150 ms); the browser title updates | pop | `--dur-stamp` 180 ms `--ease-out-quint`; collapse 150 ms `--ease-exit` |
| T-04 | [Show the page] / [Show the shelf] | row → row + panel | the panel opens under the row: `grid-template-rows` 0fr→1fr; the running head is present at frame 0; skeleton lines shimmer until the fetch returns | expand from its trigger | `--dur-drawer` 200 ms `--ease-out-quint`; skeleton 1.5 s linear loop; static under reduced motion |
| T-05 | a second row's link while one is open | panel a → panel b | a collapses (1fr→0fr, 150 ms `--ease-exit`); b's content is set and its panel opens with no height animation | swap without re-animation | 150 ms exit, 0 ms enter |
| T-06 | a count link in the foot paragraph | foot → that class's first row | `scrollIntoView({block:"center", behavior: prefers-reduced-motion ? "auto" : "smooth"})`; the line number turns `--ink` 700 and the row background `--surface-2`, then fades back after 1.5 s | link highlight | color 200 ms |
| T-07 | tab change | Memo ↔ Evaluation ↔ How it works | content swaps; the active tab's fill changes | instant | 0 ms (tens of times a day) |
| T-08 | Alt+Shift+P | any → replay | banner appears; the stamp's first line changes to REPLAY | swap | 0 ms |

Reduced motion (`prefers-reduced-motion: reduce`): T-01 keeps the opacity fade at 120 ms with no translate; T-02 and T-03 durations are 0 (marks and stamp appear at once); T-04 opens instantly; smooth scroll is off.

## 8. State machines (lite)

**Run:** `first-run → loading → (populated | partial | error | no-results)`; guards: file is `application/pdf` and ≤ 20 MB (client) else `blocked`; timeout 60 s on the fetch → `error` with "The server did not answer."; a new drop during `loading` aborts the in-flight request (`AbortController`) and restarts. `partial` → `loading(rows subset)` on [Retry {n} citations]; the retry response merges into the existing memo and re-runs T-02 for the retried rows only.

**Row:** `collapsed → opening → loading → (page | shelf | metadata-only | error) → collapsed`; only one row is open at a time.

## 9. Copy deck (sentence case; buttons name outcomes; every number in braces is bound to data, never typed)

**Browser title:** first-run "Clerkmark · citation memo" · loading "Reading {file name} · Clerkmark" · populated "Memo · {n} citations · {k} likely not real · Clerkmark" (when {k} is 0: "Memo · {n} citations · none likely not real · Clerkmark") · error "Error: {short reason} · Clerkmark".

**Folder tabs:** Memo · Evaluation · How it works.

**Heading block:**
- "MEMORANDUM"
- "TO: Intake desk"
- "FROM: Clerkmark, citation check"
- "RE: {filing label or file name}, {pages} pages, {n} citations" — on the sample: "RE: Synthetic sample filing — Memorandum in Opposition to Motion to Dismiss, {pages} pages, {n} citations. Not a real court document; modeled on the fabricated citations described in Mata v. Avianca, Inc., 678 F. Supp. 3d 443 (S.D.N.Y. 2023). Party names are fictional." (from `memo.filing.label`)
- "DATE: {DD Mon YYYY}"
- "CHECKED AGAINST: Caselaw Access Project (free files){; CourtListener}" — when no token: "CHECKED AGAINST: Caselaw Access Project (free files). CourtListener: not configured."
- Disclaimer (under the double rule): "Triage aid. Not a finding. Verify flagged rows before relying on them."
- Litigant sentence (under the disclaimer): "This memo checks whether the cases cited in a document exist in a free law library and whether quoted words appear in them. It does not judge the argument."

**Stamp:** "CHECKED" / "{DD Mon YYYY HH:MM}" / "{n} citations in {elapsed} s" / "Caselaw Access Project" (+ " · CourtListener" when used). Replay: "REPLAY" / "run of {DD Mon YYYY HH:MM}" / same / same. Partial: count line "{n} citations in {elapsed} s · {u} unanswered".

**Primary buttons:** "Choose a PDF" (S1) · "Drop your own PDF" (S3). Tonal: "Use the sample filing". Bracket links: [Show the page] / [Hide the page] · [Show the shelf] / [Hide the shelf] · [Print memo] · [Retry {n} citations] · [Try again] · [Run it live] · [Re-run the sample].

**First-run body (S1):** "Drop a filed PDF here, or [Choose a PDF]. [Use the sample filing] (synthetic, {pages} pages)." Privacy sentence: "The PDF is read on this server and not kept. Citations are looked up in the Caselaw Access Project's free files." Drag-over: "Release to check this PDF."

**Blocked (S1, in ink, under the buttons):** "This file is not a PDF. Choose a PDF saved from a word processor, or use the sample filing." · "This PDF is larger than 20 MB. This prototype reads files up to 20 MB."

**Loading (S2 status block):** "○ Reading the PDF" · "○ Finding citations" · "○ Looking up the free library" · "○ Matching quotes" · "Elapsed {t} s". After 10 s: "Still working. Large filings take longer; the page stays here." Done: "● Reading the PDF · {t} s" (and so on) · "Done in {elapsed} s."

**Partial:** "The free library did not answer for {n} citations (timed out). [Retry {n} citations]" · row note: "Could not reach the free library." rule: "Timed out after 20 s."

**Errors (in ink; the body keeps the drop target and RE: keeps the file name):**
- "No text layer in this PDF. It looks like a scan; this prototype does not run OCR. Try a PDF saved from a word processor, or the sample filing."
- "The server did not answer. Your file is still selected. [Try again]"
- "The server could not read this PDF ({server reason}). Your file is still selected. [Try again]"

**No results:** "No case citations found in {pages} pages. Statutes, court rules and Id./supra references are not checked. [Drop another PDF]"

**Row labels (margin note first line · one-line meaning for the How-it-works legend · mark):**
| class key (Evaluation tab only) | Note on the memo | One-line meaning (How it works) | Mark |
|---|---|---|---|
| verified | "Found. Quote matches." / no quote: "Found." / pin cite: "Found. Quote matches. Pin page not checked." | The case exists at this volume and page in the free library, and any quoted words appear in the opinion. | typed ✓ in ink |
| quote_not_found | "Found, but this quote is not in the opinion." rule: "Closest passage {similarity}% similar." | The case exists, but the quoted words are not in its text; the closest passage is shown. | thin red underline under the quoted words |
| wrong_cite_exists | "Exists, but not at this page." rule: "{case} begins at {first_page}; page {page} is inside it." | The case is real; the page cited is not its first page. | the page struck in red, the first page written above |
| not_in_free_corpus | "Not in the free library. Check Westlaw or Lexis." rule (one of): "U.S. Reports volumes after 572 are not in the Caselaw Access Project." / "{R} volumes after {vmax} are not in the Caselaw Access Project." / "Westlaw-only citation; no free text exists." / "Lexis-only citation; no free text exists." / "Volume {v} is missing from the free library." / "State slip citation; not in the free library." | The free library does not hold this reporter or volume, so the memo cannot say whether the case exists. | pencil dashed underline, no red |
| unrecognized_reporter | "No reporter by this name." rule: "No reporter called '{R}' in reporters_db or the Caselaw Access Project." | No law reporter with this abbreviation is known. | red circle around the reporter abbreviation |
| likely_fabricated | "Likely not a real case." rule (one of): "Page {p} belongs to {real case}, {v} {R} {first}–{last}. No case named {party} in volume {v}." / "{R} did not publish in {year} (edition runs {start}–{end})." / "Volume {v} ends at page {max}." / "Volume {v} covers {a}–{b}, not {year}." / "Volume {v} does not exist yet: {R} reached {vmax} by the library's end year." / "No case begins at or spans page {p}." | The volume is real but this page belongs to a different case, or the volume, page or year cannot exist. | red circle around the whole citation |
| skipped | "Not checked (Id., supra or short form)." / "Not checked (statute)." | Short-form references and statutes are outside what this memo checks. | none; row text in pencil |

**Advisory (verified rows with a quote and a proposition):** "Advisory: supports" / "Advisory: does not support; read this first" / "Advisory: cannot tell" / "Advisory: not run (no API key)". Pin cite: "Pin page not checked (the free library has no page breaks)."

**Foot paragraph:** "Read these first: {k} likely not real cases, {u} no reporter by this name, {q} quotes not in the opinion, {w} exists at another page. Then: {f} found; {c} not in the free library; {s} not checked. Of {n} citations." Each count is a link. Zero counts are omitted from the sentence; when every flagged count is zero: "Nothing to read first: {f} found; {c} not in the free library; {s} not checked. Of {n} citations." Partial appends "{u} not answered yet."

**Evaluation sheet:** heading "EVALUATION" · "Twenty citations with known classes, from seed/ground_truth.json, scored on the last run of the sample." · columns "Line · Citation · Expected · Memo said · Match" · match values "yes" / "no" · either-accepted expected cell "not in free library or found" · closing "Real cases marked likely not real: {fp} of {real}. Correct classes: {c} of 20." · stage list "Reading the PDF · {t} s" / "Finding citations · {t} s" / "Looking up the free library · {t} s" / "Matching quotes · {t} s" / "Advisory · {t} s or not run" · stale line "Scored on the run of {date time}. [Re-run the sample]" · class-key legend (§5 S5).

**How it works (S6):**
- WHAT IT CHECKS: "Clerkmark reads the PDF's text, finds every case citation, and looks each one up in the Caselaw Access Project's free files: which reporters exist, which volumes each has, which case sits at each page, and the opinion's text. Quoted words are matched against that text. Each row prints the rule that decided it."
- THE RULE (numbered 1–9 in the pleading margin): "1. The reporter abbreviation is unknown to reporters_db and to the Caselaw Access Project: No reporter by this name." · "2. The citation is Westlaw- or Lexis-only, or a state slip citation: Not in the free library." · "3. The year is outside the reporter edition's years, plus one either side: Likely not a real case." · "4. The volume is beyond the library's last volume: if it is more than the reporter could have printed since then, Likely not a real case; otherwise Not in the free library (checked in CourtListener when a token is configured)." · "5. The volume exists but the page is past its last page, or the year is outside the volume's years: Likely not a real case." · "6. A case begins at the cited page and its name matches: Found. Its quoted words are then matched." · "7. The page falls inside a different case: if the names match that case, Exists, but not at this page; if no case in the volume has this name, Likely not a real case." · "8. Quoted words are matched against the opinion text: 92% or better is a match; lower shows the closest passage." · "9. Advisory (optional, needs an API key): does the quoted passage support the sentence it is cited for? Supports, does not support, or cannot tell. It never changes the class."
- SOURCES: "Caselaw Access Project static files (static.case.law): reporters, volumes, cases and opinion text, no account needed; U.S. Reports through volume 572 (2014), F.3d through volume 935, F. Supp. 2d through volume 999." · "CourtListener citation-lookup API (Free Law Project): optional second source when a token is configured; 60 citations a minute." · "eyecite (Free Law Project) and reporters_db: citation extraction and reporter edition years." · "pdfplumber: PDF text. rapidfuzz: quote matching."
- LIVE AND OPTIONAL (two columns): "PDF reading · live" · "Citation extraction · live" · "Caselaw Access Project lookups · live, cached" · "CourtListener · optional (token)" · "Quote matching · live" · "Advisory · optional (API key); 'not run' otherwise" · "Progress while waiting · one response; the four steps are the pipeline's stages, the timer is real, nothing is counted".
- LIMITS: "Statutes, court rules, Id., supra and short-form citations are listed as not checked. Pin pages cannot be checked: the free library's opinion text has no page breaks. U.S. Reports after volume 572 (2014), F.3d after volume 935 and most state reporters after 2019 are outside the free library, so real cases there read 'Not in the free library'. Scanned PDFs without a text layer are not read. 'Likely not a real case' is an observation about the reporter's pages, not a finding about the filer."
- CREDITS: "Built on the Caselaw Access Project (Harvard Library Innovation Lab) for the free case-law files; Free Law Project for CourtListener, eyecite and reporters_db; and Princeton CITP's work on automatic citation verification (LePhantomCite and the legal-hallucination agent), whose five error classes and whose warning that absence from a free corpus is not proof of fabrication shaped the rule. The sample filing is synthetic and modeled on the citations described in Mata v. Avianca, Inc., 678 F. Supp. 3d 443 (S.D.N.Y. 2023)."

**Credits line under the sheet (≥1024):** "Clerkmark · a LexHack 2026 entry · sources: Caselaw Access Project, Free Law Project · [How it works]".

**Replay banner:** see C-06.

**Print footer (print only):** "Clerkmark · {DD Mon YYYY HH:MM} · Triage aid. Not a finding."

## 10. Brand

**Wordmark:** "Clerkmark" in Courier Prime 700 at −0.02em with one modification: a hand-drawn red ellipse (one closed cubic path, 1.5px `--pen` stroke, rotated −8°) around the "C". In the page it is HTML text (`<span class="wordmark">`) with an inline SVG ellipse positioned over the C after `document.fonts.ready`; the file `web/wordmark.svg` (264×48) is for the README and Devpost and uses `<text>` with Courier Prime and a Courier New fallback. The wordmark appears once, in the credits line and the README; on the memo itself the name lives in "FROM: Clerkmark, citation check".

**Mark / favicon:** the ellipse alone. `web/favicon.svg`: `viewBox="0 0 48 48"`, `role="img"` + `<title>Clerkmark</title>`, two primitives: a background `<rect>` (`#FCFBF7`; `#1B1A17` under `prefers-color-scheme: dark` via a `<style>` inside the file) and one closed cubic `<path>` for the hand-drawn ellipse, `stroke="#BE1E2D"` `stroke-width="6"` (≥6 units on the 48 grid for the 16px test), `fill="none"`, `transform="rotate(-8 24 24)"`. No text in the mark. `<link rel="icon" type="image/svg+xml" href="/static/favicon.svg">`; `<meta name="theme-color" content="#FCFBF7">`. PNG fallbacks (32, 180, 192, 512) are exported from the SVG at build time if time allows; not required for the Sprint.

**OG image and Devpost thumbnail:** a 1200×630 and a 1500×1000 screenshot of the populated memo scrolled to lines 6–11 with the stamp visible, taken by `qa/qa.mjs`; no gradient, no logo tile. Both must pass the 200px thumbnail test (a red circle beside a pencil line is still readable).

## 11. Real-product checks (A4, one line each)

- Guest use: no account; the PDF is read on the server and not stored (say so on S1 and in the README).
- The URL is state: tab in the hash, open row as `#line-{n}`, `?demo=1`, `?state=`; refresh and Back work.
- Every number on screen comes from `memo`, `/api/eval` or the run's timer; `grep -nE '\b(20|8\.4|19)\b' web/index.html` is part of QA and must return nothing but the pleading numbers template.
- Errors sit next to their source, keep the input, name the fix, never say "oops" or "invalid".
- Degrade, don't die: `/api/evidence` missing → metadata-only panel; `/api/eval` failing → the Memo tab still works; no advisory key → "Advisory: not run".
- Rate limits: CourtListener is optional and throttled; the heading says when it is not configured; a 429 shows as a `--warning` sentence above the foot paragraph: "CourtListener throttled this run; the Caselaw Access Project answered for every row shown."
- Keyboard path: Tab to Choose a PDF → Enter → (run) → Tab through rows' links → Enter opens the page → Esc closes and returns focus → ←/→ on tabs.
- Print: one letter page for the sample with panels closed; marks at 2px; no surround, tabs or links.
- Name check (2026-09-26): a web search for "Clerkmark" with legal-software and trademark terms returned no product or mark by that name; the only nearby result was an unrelated "CLERK" trademark listing (trademarks.justia.com). Not a clearance; re-run against a USPTO search before submission. Fallback name: First Page.
- Sample content is labelled on the content (RE: line, from `memo.filing.label`); no invented users, quotes, testimonials or logos anywhere.
- 720p check: export the 1440 still, downscale to 1280×720, read it cold; links, stamp lines and notes are 14px for this reason; line numbers at 12px are anchors only.

## 12. Don'ts (project-specific, on top of B11)

- Never the word "fabricated" as a fact on the memo; the note is "Likely not a real case" and the eval tab shows the class key.
- No red on anything a user can click; no red validation text; red is the pen and the stamp only.
- No legend block, KPI tiles, top bar, app header, sample badge, toast, modal or tour; the memo's own lines carry all of it.
- No counters while waiting ("6 of 20") unless per-citation events exist; the four hollow steps and the real timer are the whole loading UI.
- No handwriting fonts, no rotated text other than the stamp (−2°) and the wordmark ellipse, no filters, no textures, no gradients, no indigo, no hairline grid, no eyebrow labels, no middle-dot metadata strings on the memo (the credits line and stamp source line are the two allowed "·" uses).
- No Source Serif 4 outside the reporter panel and shelf labels; no Courier inside them except the URL footer.
- No third typeface, no icon set (the only glyphs are the typed ✓, ○ and ●).
- No literal dates, counts, seconds or percentages in `web/index.html`.
- No animation on tab change, hover, or a second drawer; the mark pass runs once per run and never on `?demo=1` first paint.
- No desk blotter or decorative surround color; `--surround` stays flat and neutral.

## 13. Acceptance (A8 gates 1–4, Sprint)

1. **Cut pass:** no legend block, no top bar, no KPI tiles, no cards; one filled button per screen; the sheet has exactly two rules (double rule, margin rule) plus the eval table's header rule; the surround is deletable without the layout changing. Self-reviewed by grep and screenshot.
2. **Anti-slop (B11):** `grep -nEi 'gradient|indigo|#6366f1|eyebrow|seamless|empower|streamline|AI-powered|cutting-edge|leverage|unlock' web/` returns nothing; no `transition: all`; no `border-radius` above 2px; fonts are Courier Prime and Source Serif 4 only.
3. **Accessibility:** axe (`@axe-core/playwright`) passes with zero violations on `?demo=1`, `?demo=1#line-6`, `?demo=1#line-23`, `#evaluation`, `#how` and every `?state=`; the keyboard path in §11 completes without a mouse; every mark has a word beside it; contrast pairs in §14 measured; 320px renders the sheet with notes under citations and no horizontal scroll; `prefers-reduced-motion` removes translate, draw-on and stamp motion.
4. **Judge:** `?demo=1` opens populated with the stamp on it in under 2 s from cache; the golden path is one drop to the artifact; Alt+Shift+R three times in a row leaves a clean S1; Alt+Shift+P paints the replay with the banner and REPLAY stamp (pending a recorded `seed/replay.json`); the 1440 still downscaled to 720p is readable cold; 390×844 shows the **Drop your own PDF** button in the heading without scrolling; the print preview is one letter page for the sample with panels closed; the three marks (circle-all, strike-correct, circle-reporter) render at 320, 390, 1024 and 1440 in `qa/qa.mjs` screenshots.

## 14. Tokens

Contrast measured with the B4 node snippet on 2026-09-26, no rounding:

| Pair | Ratio | Gate |
|---|---|---|
| ink `#1B1A17` / canvas `#FCFBF7` | 16.807 | pass 4.5 |
| ink-muted `#5B5750` / canvas `#FCFBF7` | 6.936 | pass 4.5 |
| ink-muted `#5B5750` / surface-1 `#F3F1EA` | 6.355 | pass 4.5 |
| ink-muted `#5B5750` / surface-2 `#ECE9DF` | 5.912 | pass 4.5 |
| ink-muted `#5B5750` / surround `#E8E5DC` (credits line) | 5.702 | pass 4.5 |
| ink-muted `#5B5750` / tab-inactive `#E0DDD3` | 5.285 | pass 4.5 |
| pen `#BE1E2D` as text / canvas `#FCFBF7` | 5.942 | pass 4.5 |
| pen `#BE1E2D` as text / surface-1 `#F3F1EA` | 5.444 | pass 4.5 |
| pen `#BE1E2D` as a mark / surface-2 `#ECE9DF` (hovered row) | 5.065 | pass 3 |
| accent-ink `#FCFBF7` / accent `#BE1E2D` | 5.942 | pass 4.5 |
| button label `#FCFBF7` / button `#1B1A17` | 16.807 | pass 4.5 |
| line-input `#6E6A61` / canvas · surface-1 · surround | 5.204 · 4.768 · 4.278 | pass 3 |
| success `#2F6B3A` / canvas · surface-1 | 6.174 · 5.656 | pass 4.5 |
| warning `#7A4F12` / canvas · surface-1 | 6.864 · 6.289 | pass 4.5 |
| accent text / accent-container (about `#EFD9D5`) | 4.558 | pass 4.5 |

`--pen` is the data token for marks (content, outside the accent budget). `--pencil` is the data token for unresolved and not-checked rows. `--danger` shares the pen hue by design (deviation 2) and has no use in v1.

```css
:root{
  color-scheme: light;
  --ff-display:"Courier Prime",ui-monospace,"Courier New",monospace;   /* what the clerk typed: the memo, its headings, the stamp, buttons, the eval and how-it-works sheets */
  --ff-body:"Source Serif 4",Georgia,serif;                            /* what the book printed: the reporter page excerpt and the shelf strip labels only */
  --ff-mono:"Courier Prime",ui-monospace,"Courier New",monospace;      /* IDs and CAP URLs; same face as display */

  /* surfaces */
  --canvas:#FCFBF7;            /* bond paper: the memo sheet (ink 16.807:1, ink-muted 6.936:1) */
  --surface-1:#F3F1EA;         /* reporter paper: the opened page excerpt and the shelf strip panel (ink-muted 6.355:1) */
  --surface-2:#ECE9DF;         /* row hover, skeleton blocks, the tonal sample button (ink-muted 5.912:1) */
  --surface-sunken: color-mix(in oklch, var(--canvas), black 4%);
  --surround:#E8E5DC;          /* the flat table-top behind the sheet at >=1024; not a text surface except credits (ink-muted 5.702:1) */
  --tab-inactive:#E0DDD3;      /* inactive folder tab; ink-muted on it 5.285:1 */

  /* lines */
  --line:#C9C4B6;              /* the memo's double rule and the pleading margin rule; decorative, exempt from 3:1 */
  --line-input:#6E6A61;        /* file input and drag-over boundary: 5.204:1 on canvas, 4.768:1 on surface-1, 4.278:1 on surround */

  /* ink */
  --ink:#1B1A17;               /* typewriter black */
  --ink-muted:#5B5750;         /* pencil: secondary text, unresolved and not-checked rows */
  --pencil: var(--ink-muted);  /* data token: "Not in the free library", "checking…", skipped rows, dashed underlines */

  /* accent = the clerk's red pen */
  --accent:#BE1E2D;            /* as text on canvas 5.942:1; on surface-1 5.444:1; as a mark on surface-2 5.065:1 */
  --accent-ink:#FCFBF7;        /* 5.942:1 on accent; used only in the rare red fill (confirm step); no red fills exist in v1 */
  --pen: var(--accent);        /* data token: circles, strike-and-correct, underlines, the CHECKED stamp; never a button */
  --accent-hover: oklch(from var(--accent) calc(l - .06) c h);
  --accent-press: oklch(from var(--accent) calc(l - .12) c h);
  --accent-container: color-mix(in oklch, var(--accent) 12%, var(--surface-1));   /* about #EFD9D5; accent text on it 4.558:1 */
  --focus: var(--ink);         /* ink rings everywhere; red never means "focused" */

  /* buttons: ink-filled with paper labels (deviation 1) */
  --button-bg: var(--ink);
  --button-ink: var(--canvas);          /* 16.807:1 */
  --button-hover: color-mix(in oklch, var(--ink), white 8%);
  --button-press: color-mix(in oklch, var(--ink), white 12%);

  /* status (system register only; never used for citation classes) */
  --success:#2F6B3A;           /* 6.174:1 on canvas, 5.656:1 on surface-1; eval "Real cases marked likely not real: 0" */
  --warning:#7A4F12;           /* 6.864:1 on canvas, 6.289:1 on surface-1; CourtListener throttled / partial-run notice */
  --danger: var(--accent);     /* one red in this world; reserved for the confirm step. Validation sentences are ink (see §9) */
  --danger-container: color-mix(in oklch, var(--danger) 10%, var(--surface-1));

  /* shape: paper */
  --r-sm:2px; --r-md:2px; --r-lg:0px;   /* sheet and panels square; stamp box and buttons 2px */
  --shadow-raised: 0 1px 2px rgb(0 0 0/.12), 0 8px 24px -8px rgb(0 0 0/.35);   /* the sheet on the table; the only shadow */
  --shadow-overlay: 0 4px 8px rgb(0 0 0/.06), 0 16px 40px -8px rgb(0 0 0/.22); /* unused in v1; kept for a future dialog */

  /* type scale, density 7, ratio 1.2 */
  --step--2:12px; --step--1:13px; --step-0:14px; --step-1:15px; --step-2:18px;
  --lh-memo:1.55; --lh-body:1.6;
  --track-caps:0.10em; --track-stamp:0.08em; --track-wordmark:-0.02em;

  /* motion: Precise (B6 tokens + this direction's marks) */
  --ease-out:cubic-bezier(.23,1,.32,1); --ease-out-quint:cubic-bezier(.22,1,.36,1);
  --ease-in-out:cubic-bezier(.77,0,.175,1); --ease-drawer:cubic-bezier(.32,.72,0,1);
  --ease-enter:cubic-bezier(.05,.7,.1,1); --ease-exit:cubic-bezier(.3,0,.8,.15);
  --dur-press:120ms; --dur-hover:150ms; --dur-pop:200ms; --dur-modal:280ms; --dur-exit:150ms;
  --dur-drawer:200ms; --dur-sheet:450ms; --dur-route:400ms;
  --dur-mark:300ms; --stagger-mark:60ms; --dur-stamp:180ms; --dur-row:120ms; --stagger-row:30ms;

  /* layout */
  --sheet-w:816px; --margin-w:56px; --note-w:240px; --sheet-pad-top:64px; --sheet-pad-right:72px; --sheet-pad-bottom:72px;
  --row-gap:12px; --row-min:56px; --tab-h:36px; --strip-h:12px;
  --mark-stroke:1.5px;
}
@media (prefers-reduced-motion: reduce){
  :root{--dur-mark:0ms;--stagger-mark:0ms;--dur-stamp:0ms;--dur-row:0ms;--stagger-row:0ms;--dur-drawer:0ms}
}
@media print{
  :root{--surround:#FFFFFF;--canvas:#FFFFFF;--shadow-raised:none;--mark-stroke:2px}
}
```

Type sizes (density 7, ratio 1.2): 12px line numbers, running heads, strip labels, URL footers · 13px filing page, stamp date and source lines are 14px (bumped from 13 for 720p) · 14px notes, rule sentences, links, excerpt text, eval body · 15px memo text, headings (headings differ by weight and caps, not size), buttons, tabs · 18px "CHECKED". `font-variant-numeric: tabular-nums` on every count; curly quotes; a real minus sign; en dashes in page ranges.
