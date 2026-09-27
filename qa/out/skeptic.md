# Skeptical evaluator (A8 gate 2 / AC-10)

Method: a fresh `claude -p --model sonnet` process (no spec, no code, no repo; run in an empty scratch directory holding only the two PNGs, tools limited to Read), shown only:
- still 1: `qa/out/still-1-demo-top-1440.png` (`?demo=1`, top of the sheet, 1440x900)
- still 2: `qa/out/still-2-varghese-page-1440.png` (line 6, Varghese, with [Show the page] open)

The Agent tool was not available in this session, so a separate headless Claude process stood in for the subagent. The prompt it received is below, followed by its answers verbatim. Round 1 ran on the stills as they were when T08 resumed. Round 2 was a new process, run on the stills after the round-1 fixes.

## Prompt (both rounds)

```
You are a skeptical first-time viewer. You have NOT seen any spec, code or pitch for this product. Look ONLY at the two screenshots in this directory: still-1.png (the first screen of a web product at 1440x900, top of the page) and still-2.png (the same page scrolled down, after the viewer clicked a link on one row). Use the Read tool to open both images. Spend the equivalent of 5 seconds on still 1 before answering 1-3, then use still 2.

Answer plainly and critically; do not flatter. Format your answer as numbered answers:
1. What is this product? (one sentence, as you'd tell a stranger)
2. Who is it for (the user)?
3. What does it do that a simpler tool would not (the differentiator)? Answer from still 1 first, then say what still 2 adds or changes.
4. From still 2 alone: what is the difference between a row marked "Likely not a real case" and a row marked "Not in the free library"? What does the opened panel prove, if anything?
5. List every element in either still that looks generic, templated, confusing, cramped, broken or unfinished (be specific: which element, where, why).
6. Which house-style traits do you see (typography, palette, layout metaphor, marks), and does the style help or hurt comprehension?
7. The single change that would most improve the 5-second read of still 1.
```

## Round 1: answers, verbatim

1. **What is this product?** A web tool that scans a legal document's citations and checks each one against a free public case-law database, flagging citations that look fabricated or that it simply can't verify.

2. **Who is it for?** Legal staff who vet filings before they go out — the copy literally says "Intake desk" and "Clerkmark, citation check" — so paralegals, law clerks, or attorneys doing a pre-filing sanity pass, not consumers.

3. **Differentiator vs. a simpler tool:**
   - *Still 1:* A dumb "does this citation string exist" checker would just say found/not‑found. This one gives a reason per row (e.g., "Page 1339 belongs to a different case," "statute — out of scope"), timestamps and counts the check ("23 citations in 3.1 s"), and explicitly hedges itself ("Triage aid. Not a finding. Verify flagged rows"). That's more epistemically careful than a binary pass/fail badge.
   - *Still 2 adds:* Actual receipts. Clicking a row doesn't just expand text — it pulls the real page content from the archive at that exact reporter/volume/page, shows it doesn't match the cited case, and links out to the raw source JSON. That's the difference between "trust our label" and "here's the primary source, judge for yourself."

4. **"Likely not a real case" vs. "Not in the free library," and what the panel proves:**
   - "Likely not a real case" = positive disproof — the reporter/volume exists in the library, the tool looked up that exact page, and found a *different* case sitting there. Contradicting evidence.
   - "Not in the free library" = absence of evidence — the citation simply isn't covered by this free corpus (too recent, wrong reporter type, etc.), so the tool can't say real or fake either way.
   - The opened panel (row 6) does prove something concrete: page 1339 of vol. 925 F.3d is shown to actually contain *J.D. v. Azar*, not "Varghese v. China Southern Airlines." That's a real, checkable mismatch — assuming the underlying archive is accurate, which the tool never verifies for the user, it just cites it.

5. **Generic / cramped / confusing / unfinished elements:**
   - The red "CHECKED" stamp box (still 1) reads as a decorative rubber-stamp cliché rather than functional UI — it doesn't clearly connect to anything below it.
   - Monospace "memo" template (TO/FROM/RE/DATE) is a very familiar AI-generated-document trope; feels like a costume rather than a considered layout.
   - "Drop your own PDF" button is a different visual language (solid black block) dropped next to the stamp with no shared alignment — looks bolted on.
   - "[Show the page]" / "[Hide the page]" toggle is just bracketed text, no icon or visual affordance that it's interactive — easy to miss entirely on first pass.
   - Row 6 in still 2 combines underline *and* strikethrough on the same citation text — visually noisy, unclear which styling is doing the work.
   - The expanded panel exposes raw `static.case.law/.../*.json` links — that's developer/debug plumbing, out of place for a stated audience of "intake desk" staff.
   - Truncated explanations ("begins at page…", "the free corpus doe…") cut off with no expand affordance, unlike row 6 — inconsistent, feels cramped/broken.
   - Thin left gray margin column with row numbers (1–10) floats disconnected from the content — reads like unstyled leftover table scaffolding.

6. **House-style traits:** monospace/typewriter type, cream paper background, black text with a single red accent (stamps, warnings, strikethrough), hairline rules, a "legal memo" layout metaphor, underline-as-link. It mostly helps — it signals "verbatim/quote-accurate, don't trust my prose" which suits a citation-checking tool — but it also hurts where the metaphor is applied decoratively (the stamp graphic, the memo header) rather than functionally, and where monospace paragraphs of explanatory text get harder to scan than the citation rows themselves.

7. **Single highest-impact change for the 5-second read of still 1:** Add one plain-language summary line at the very top (e.g., "3 of 23 citations likely fabricated, 5 unverifiable") — right now a first-time viewer has to read into the row list to learn the tool's actual verdict; the stamp and header just say *that* a check happened, not *what it found*.


## Round 2 (after the round-1 fixes; new process): answers, verbatim

## Answers

**1. What is this product?**
A tool that scans a legal document's citations and checks each one against a free case-law database to flag citations that look fabricated, misquoted, or unverifiable.

**2. Who is it for?**
Someone in a legal workflow who has to vet a brief or memo before it's filed or relied on — a paralegal, clerk, or "intake desk" reviewer — likely worried about AI-hallucinated citations sneaking into filings.

**3. Differentiator:**
- *Still 1 alone:* A simple citation formatter or spell-checker just validates format (does this look like "678 F. Supp. 3d 443"?). This tool claims to check whether the case actually exists and whether quoted text is actually in it — that's a factual/existence check, not a style check.
- *Still 2 adds:* It backs that claim with evidence rather than a bare label. Clicking a flagged row pulls up the real case that occupies that exact reporter/volume/page, complete with case name, date, and a text excerpt — proving the cited case is a mismatch rather than just asserting "fake." That's a meaningfully stronger differentiator than still 1 alone conveys.

**4. "Likely not a real case" vs. "Not in the free library" (from still 2 alone):**
- "Likely not a real case" = the tool positively resolved that address (e.g., 925 F.3d 1339) and found a *different*, real case sitting there — active, checkable evidence of fabrication.
- "Not in the free library" = the tool has no data for that citation at all (e.g., a state reporter format the free corpus doesn't index) — an absence of information, not evidence of anything. It's inconclusive, and the row 9 note ("Check the court's own site") admits as much.
- The opened panel (row 6) does prove something: it shows the actual case, date, dissent note, and links to raw source JSON, so the "likely not real" verdict isn't a black box — you can see exactly what it found instead.

**5. Rough/unfinished/confusing elements:**
- The lead paragraph "Read these first: 3 likely not real cases, 1 no reporter by this name, 2 quotes not in the opinion, 1 exists at another page. Then: 8 found; 6 not in the free library; 2 not checked" is a dense run-on with inline underlined numbers — reads like a mail-merge template, not a designed summary. This is the single worst offender for a "memo" meant to be skimmed.
- "CourtListener: not configured" sitting right in the header of a finished-looking memo reads as an exposed debug/config message, not user-facing copy.
- "Drop your own PDF" button is placed oddly next to the tilted red "CHECKED" stamp — unclear at a glance whether it's a live control or part of the stamp graphic.
- "[Show the shelf]" / "[Show the page]" bracket-link styling looks like unstyled placeholder markdown links, not a finished UI affordance.
- In the expanded panel (still 2, row 6), the excerpt text is truncated mid-word: "Unaccompanie" — looks like a broken string cut, not intentional truncation (no ellipsis).
- "Evaluation" as a tab label is vague — no way to guess its contents from still 1.
- Every citation is both underlined and followed by "p. 3" and a red circle annotation — three separate emphasis treatments stacked on the same short line, which is visually busy for something meant to be scanned fast.

**6. House-style traits:**
Monospace/typewriter type, cream paper background, black rule lines, folder-style tabs, and a red rubber-stamp/hand-markup motif (the "CHECKED" stamp, red circles and strikeout-style underlines on flagged citations). It commits to a "legal case file" metaphor consistently. It helps set tone (feels appropriately institutional/legal) but hurts comprehension: monospace body text at paragraph length is slower to read than a sans-serif UI font, and mixing a "precise stamped verdict" motif with "hand-circled annotation" motif sends mixed signals about whether this is an automated report or someone's manual markup — that tension undercuts trust in the automation.

**7. Single highest-leverage change for the 5-second read of still 1:**
Replace the run-on summary sentence with a simple numeric scorecard (e.g., four or five big labeled counts: Found / Likely fake / Not in library / Not checked) so the verdict is legible in one glance instead of requiring the reader to parse a sentence full of inline numbers.


## What was done with the findings (web/ only)

Both rounds named the product (a citation checker for legal filings), the user (intake desk, paralegal or clerk) and the differentiator from still 2 (a "likely not real" row is positive disproof: that page belongs to a different case, J.D. v. Azar; "not in the free library" means no evidence either way). That meets AC-10.

Fixed:
- Round 1, #7 (the verdict is not on the first screen): "Read these first: …" now sits at the top of the memo body, above the rows (index.html). It was a foot paragraph under line 23. It is still the §9 sentence with its count links. Round 2, #5/#7 (it reads as a run-on): "Then:" now starts its own line (app.js renderFoot).
- Round 1, #5 (explanations cut off with no way to expand them): a row with no [Show the page]/[Show the shelf] had its rule sentence clamped to 2 lines and could never show the rest. It is now left unclamped on screen (app.css). Print still clamps it.
- Round 1, #5 (row 6 has an underline and a strike-through): the red ellipse was tilted a full 2°, so on a 400 px citation its ends dropped about 7 px into the first and last letters and read as a strike-through. The tilt is now reduced on wide ellipses so the ends move no more than 2.5 px (app.js drawRowMark).
- Round 2, #5 (the excerpt is cut mid-word, "Unaccompanie"): the excerpt now ends at its last whole word, with an ellipsis unless that word ends a sentence. The highlighted passage is never cut (app.js tidyExcerpt).
- Found while reviewing the stills: RE: was squeezed into a 220 px column beside the stamp. The stamp and button now float, so RE: wraps under them (about 140 px shorter at 1440). Rows now keep the sheet's 72 px right margin: notes had run to the paper edge. The reporter span no longer breaks across lines, so circle-reporter stays a single ellipse. At 320 px the tabs fit on one line. In the one-column drop target, the full stop that sat alone between the two buttons is hidden.

Declined, with reasons:
- Numeric scorecard or big counts (round 2, #7): UI-SPEC §13 gate 1 rules out KPI tiles and cards. Moving the "Read these first" sentence to the top covers the same need inside the memo metaphor.
- "CourtListener: not configured" in the heading: this is the CHECKED AGAINST line, which states the sources honestly. It is §9 copy, and it changes when a token is set.
- Raw static.case.law JSON links in the panel: UI-SPEC C-04 asks for them. They are the receipts a clerk can open.
- Bracketed [Show the page] links, the stamp, the typewriter memo head and the line-number margin: this is the decided Clerkmark direction (pleading paper). The brief says "Decided already".
- The "Evaluation" tab label: this is §9 copy, and the tab is one click away. Left as is.
