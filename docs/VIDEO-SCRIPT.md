# Video script — Clerkmark (2:45)

Follows the contract's demo script (`.prod-build/contract.md`, "Demo script"; UI-SPEC §2 is its source). Target length 2:45, hard limit 3:00 (LexHack rule).

**Numbers are read off the screen, never from this page.** Where a line below contains a number, it is the number the sample showed on 27 September 2026 (for example "23 citations"; the Evaluation tab's "20 of 20" and "0 of 11"). If the screen shows something else on recording day, say what the screen shows. `{elapsed}` is always read from the stamp.

Setup for every take: the live URL in an incognito window at 1920×1080, browser zoom so the memo sheet fills the frame, the tab opened at `LIVE_URL/?demo=1`.

## Shot list

| # | Time | On screen (action) | Spoken |
|---|---|---|---|
| 1 | 0:00–0:10 | The populated memo over the sample filing (`?demo=1`): the Clerkmark wordmark, the MEMORANDUM heading and the TO / FROM / RE block. The cursor rests on "TO: Intake desk". | "When someone without a lawyer files a brief written with a chatbot, court staff look up every case by hand." |
| 2 | 0:10–0:20 | Title card made in the editor (or the database page in a browser tab): "2,079 court decisions on AI-hallucinated citations · 1,196 involve self-represented filers" with the source line "Damien Charlotin, AI Hallucination Cases database, damiencharlotin.com/hallucinations · as of 25 Sep 2026". Check the page on recording day and update the card and the line if the numbers have moved. | "Two thousand seventy-nine decisions; more than half from people representing themselves." |
| 3 | 0:20–0:30 | Press Alt+Shift+R (cut the keypress): the empty sheet. Click **Use the sample filing**. RE: fills; the status line shows the four steps ("Reading the PDF", "Finding citations", "Looking up the free library", "Matching quotes") and the elapsed timer counting. | "We check the whole filing against a free law library." |
| 4 | 0:30–0:45 | The memo returns: rows reveal in filing order, the red marks draw down the sheet, the CHECKED stamp lands ("23 citations in {elapsed} s"). Hold on the stamp for a second. | "Twenty-three citations in {elapsed} seconds." (read both numbers off the stamp) |
| 5 | 0:45–1:10 | Scroll to lines 8 and 9. Hover line 8: "Miller v. United Airlines, Inc., 174 F.3d 366" circled in red, note "Likely not a real case.", rule "Page 366 belongs to Greenleaf v. Garlock, Inc., 174 F.3d 352–368. No case named Miller in volume 174." Move to line 9: "Shaboon v. Egyptair, 2013 IL App (1st) 111279" in pencil, "Not in the free library. Check Westlaw or Lexis." | "This one is likely not a real case: page 366 belongs to Greenleaf v. Garlock. This one we simply cannot check for free. A naive checker prints the same 'not found' for both." |
| 6 | 1:10–1:30 | Scroll up to line 6 (Varghese v. China Southern Airlines Co., 925 F.3d 1339). Click **[Show the page]**: the drawer opens with the running head "925 F.3d 1291 · J.D. v. AZAR · D.C. Cir. · June 14, 2019", the page number 1339 and the Caselaw Access Project links. Hold two seconds, then **[Hide the page]**. | "The page it cites is a different case. The evidence is the reporter's own record, one click from the row." |
| 7 | 1:30–1:50 | Line 16 (Chan v. Korean Air Lines, Ltd., 490 U.S. 122): the quote underlined, the differing words in red, note "Found, but this quote is not in the opinion." and the rule naming the three words ("authority" for "power", "add" for "insert", "exception" for "amendment"). Optional pass over line 15: Zicherman "230" struck, "217" written above. | "Real case, wrong quote: three words differ from the opinion, and the memo shows which." |
| 8 | 1:50–2:15 | Click the **Evaluation** tab: 20 rows, Expected vs Memo said, the Match column; scroll to the closing line "Real cases marked likely not real: 0 of 11. Correct classes: 20 of 20." and the per-stage seconds. | "Twenty citations with known answers; twenty of twenty right; zero real cases called fake." (read both counts off the closing line) |
| 9 | 2:15–2:35 | Click **How it works**: scroll past the numbered rule (1–9), SOURCES, LIVE AND OPTIONAL, LIMITS and CREDITS. | "The rule is deterministic and printed in full; the model, if any, only advises. It skips statutes and short-form cites and cannot check pin pages. Built on the Caselaw Access Project and Free Law Project's eyecite, with credit to Princeton's work on citation checking. A triage aid, not a finding." |
| 10 | 2:35–2:45 | The GitHub README scrolled to the "Tech stack" table, then the live URL in the address bar. | "Repo and live link in the description." |

The spoken lines total under 200 words, which fits 2:45 at a calm pace. If a take runs long, cut the optional pass over line 15 in shot 7 and the second sentence of shot 6.

## Recording checklist

- [ ] **1080p.** Record at 1920×1080; export 1080p. Hide the bookmarks bar and other browser chrome that is not the address bar.
- [ ] **Captions.** Upload the spoken lines above as captions (an SRT from the editor, or YouTube's editor), checked against the final cut; numbers in the captions match the screen.
- [ ] **Incognito.** A fresh incognito window: no extensions, no autofill, nothing personal on screen; notifications off at the OS level.
- [ ] **Warm the URL.** 1–2 minutes before each take, open `LIVE_URL/api/health` and run the sample once, so the serverless function is not cold on camera.
- [ ] **Replay fallback.** If the live run fails or stalls on camera, press Alt+Shift+P: the recorded run (`seed/replay.json`) paints under a "Replay · run of {date}" banner and a REPLAY stamp. Say "this is the recorded run" if that take is used; never present it as live.
- [ ] **Reset between takes.** `?reset=1` or Alt+Shift+R returns to the empty sheet; reload `?demo=1` before shot 1.
- [ ] **Console clean.** DevTools console shows no errors before the take (then close DevTools).
- [ ] **Numbers on the day.** Re-check the Charlotin database numbers and the stamp's counts on recording day; the script's numbers follow the screen.
- [ ] **Length.** Final cut under 3:00 (target 2:45). Upload to YouTube (unlisted is fine), Vimeo or Loom, open the link logged out, then paste it into README.md and DEVPOST.md.
