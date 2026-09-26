# DECISION RULE — final, implementable spec for `citememo/rules.py` and its inputs

Status: supersedes BUILD-NOTES §3 (and the parts of §1 it depended on). Every number below comes from CAP static files, reporters_db 2.x, eyecite 2.7.8 or the seed (`seed/ground_truth.json`), checked 2026-09-26. The classifier is deterministic: no model runs inside it. The optional advisory LLM step (BUILD-NOTES §2, `advisory.py`) never changes a class.

The one promise the rule is built around: **a real case is never labelled `likely_fabricated`.** Where two adversarial fixes conflicted, the spec picks the one that keeps that promise and says so in a `Why` note. Where the promise conflicts with a red row on the demo, the promise wins.

Classes (final): `verified`, `quote_not_found`, `wrong_cite_exists`, `not_in_free_corpus`, `unrecognized_reporter`, `likely_fabricated`, `not_checked` (new), `skipped`.
Registers on the memo: green = `verified`; amber = `quote_not_found`, `wrong_cite_exists`; coverage = `not_in_free_corpus`, `not_checked`; unknown reporter = `unrecognized_reporter` (its own register, not the red one); red = `likely_fabricated`; grey = `skipped`.

Every `CitationResult` carries `class`, `reasons: list[str]` (plain sentences, the first one is printed under the row), `evidence: dict`, `source: "CAP"|"CourtListener"|"none"`, `links: list[str]` (CAP URLs used), `quote_check: dict|None`, `pincite_unverified: bool`, `parallel_cites: list[str]`.

---

> Wording note (2026-09-26, after T04): where this document's §7 "contains" column and docs/UI-SPEC.md §9's rule sentences differ, the §9 sentences are what `citememo/rules.py` prints; §7 fragments are asserted case-insensitively in tests/test_rules.py. Row 46's court for Griffith v. United States is the Eleventh Circuit per CAP, not the Federal Circuit.

## 1. Inputs and normalization (`extract.py`, `cap.py`)

### 1.1 Text
`pdfplumber` page text joined with `\n`; then `eyecite.clean_text(text, ["all_whitespace"])`. Keep the offset map so spans printed in the memo point at the PDF text. Before quote matching only (not before eyecite), also undo PDF line-break hyphenation: `re.sub(r"(\w)-\s*\n\s*(\w)", r"\1\2", text)`.

### 1.2 eyecite fields used per `FullCaseCitation` `c`
| Field | Use | Trap and fix |
|---|---|---|
| `c.groups["volume"]` | V (int) | string → `int()` |
| `c.edition_guess.short_name` | R (canonical reporter string) | Use this, **not** `groups["reporter"]`: `groups` gives `F.Supp.2d`, `Fed. Appx.`, `So.3d` spellings that miss the CAP map; `edition_guess` gives `F. Supp. 2d`, `F. App'x`, `So. 3d` |
| `c.edition_guess.start/.end` | reporters_db edition dates (note only, §2 step 3) | `end is None` = edition open in reporters_db |
| `c.edition_guess.reporter.cite_type` | `specialty_west`, `specialty_lexis`, `neutral`, `federal`, `state`, ... (step 2) | |
| `c.edition_guess.reporter.editions` | sibling editions (successor detection, §3) | reporters_db is keyed by the base reporter: `REPORTERS["F."]` holds `F., F.2d, F.3d, F.4th`; `REPORTERS["F. Supp."]` holds `F. Supp., F. Supp. 2d, F. Supp. 3d` |
| `c.groups["page"]` | P (int) | string → `int()`; `IL App (1st) 111279` is a neutral cite and never reaches the page logic |
| `c.metadata.pin_cite` | pin page (note only) | |
| `c.metadata.year` | Y (fallback only) | **Unreliable**: eyecite reported 2019 for `Eastern Airlines v. Floyd, 499 U.S. 530 (1991)` on the seed. Primary source for Y: regex on the 60 chars after the citation span: `r"\(([^()]*?)\b((?:1[7-9]|20)\d{2})\)"` → group 2 (year), group 1 (court text). Fall back to `metadata.year`. Coerce: `int(m.group()) if (m := re.match(r"\d{4}", str(y or ""))) else None` |
| `c.metadata.court` | court (soft check only) | `None` for `(3d Cir. 1999)` although `2d Cir.` resolves; use the regex group 1 above as the court text when `metadata.court` is None |
| `c.metadata.plaintiff`, `c.metadata.defendant` | party names | eyecite drops "of": `Estate of Durden` → `Estate  Durden` (double space). Normalize whitespace; §5 handles prefixes. Either may be `None` (`In re ...` gives plaintiff `None`) |
| `c.span()` | character offsets | for grouping, quote attachment, unrecognized-reporter catch |
| `c.metadata.parenthetical` / text after span | quote attachment | unchanged from BUILD-NOTES §2 (`≥ 25 chars` quoted string within 400 chars before the cite, or after "quoting") |

### 1.3 Reporter → CAP slug (`cap.reporter_slug`)
Build once at startup from `data/cap/ReportersMetadata.json` (401 reporters):
```
key(s) = s.replace(" ", "").replace("'", "").lower()
slug_by_key[key(short_name)] -> slug
```
Only two keys collide (`mass.app.div.` → `mass-app-div`, `mass-app-div-annual`; `ct.cl.` → `us-ct-cl`, `wv-ct-cl`); resolve `mass.app.div.` to `mass-app-div` and leave `ct.cl.` unmapped (Ct. Cl. cites → `not_in_free_corpus` with the "ambiguous CAP slug" reason). Verified keys: `so.3d` → `so3d` (eyecite `So. 3d`), `f.appx` → `f-appx` (eyecite `F. App'x`), `f.supp.2d` → `f-supp-2d`, `u.s.` → `us`, `f.3d` → `f3d`. **Never slugify an unknown reporter and probe the network**: `F.4th`, `N.Y.S.3d`, `IL App (1st)`, `WL` have no CAP slug and stop at step 3b. eyecite's `5 U.S. (1 Cranch) 137` carries `reporter_nominative="Cranch"` and a corrected reporter `U.S.` → slug `us`.

Also keep from ReportersMetadata: `start_year`, `end_year` per slug (e.g. `us` 1754–2014, `f3d` 1990–2019, `f-supp` 1839–1998, `f-supp-2d` 1982–2014, `f-supp-3d` 1968–2019 label, `s-ct` 2013–2020, `l-ed-2d` 2010–2012, `f-appx` 1996–2018).

### 1.4 CAP fetch contract (`cap.py`)
Every CAP call returns one of three things, and the classifier only ever sees these:
- `Present(data)`: HTTP 200 **and** body starts with `[` or `{` **and** `json.loads` succeeds.
- `Absent`: HTTP 404 (CAP answers 404 with a 27 KB HTML page, e.g. `us/600/CasesMetadata.json`, `f4th/VolumesMetadata.json`). Cached like a positive result.
- `Failed(reason)`: timeout (20 s, 1 retry), connection error, HTTP 5xx/429/403, or 200 with a non-JSON body. Not cached.

Concurrency bound 6; one volume's `CasesMetadata.json` is 0.5–6.5 MB (us/540: 6.45 MB, 3.6 s cold; us/516: 5.78 MB; f3d/174: 1.95 MB, 4.7 s), so the seed's 12 volumes ship warmed in `seed/cache/cap/` and `scripts/eval.py` times the cold path once and writes the number the memo's timing panel shows.

### 1.5 Volume and case indexes
`VolumesMetadata.json` may list the same `volume_number` more than once (a3d: 41 duplicates). Build `volumes: dict[str, list[VolumeEntry]]`; the volume "exists" if the list is non-empty; its cases are the union of every entry's `CasesMetadata` (dedupe by case `id`). `Vmax = max(int(v) for v in volumes)`.

Per volume, from `CasesMetadata.json`, for each case compute:
```
digits(s) = [int(x) for x in re.findall(r"\d+", s or "")]
first = min(digits(first_page)) if digits(first_page) else None
last  = max(digits(last_page))  if digits(last_page)  else first
if first is None: exclude the case from page lookups (keep it for name search)
if last < first: last = first          # us/525 'United States v. Louisiana' first '1' last '0'
```
(`174 F.3d`: last_page `'377-391'` → 391, `'1227-1235'` → 1235.) Then:
- `by_first[P] -> list[case]` (516 U.S. has 373 pages where more than one case begins, up to 15 orders per page).
- `by_official_cite["V R P"] -> list[case]` from `citations[].cite` (516 U.S.: `Holder v. Harlem Men's Shelter` has official cite `516 U.S. 545` but first_page 803; three cases have official cite `516 U.S. 1003` and first_page 1004).
- `spans`: cases with `first < P <= last`.
- `covered`: the set union of `range(first, last+1)`; `max_last = max(last)`.
- `decision_year(case) = int(decision_date[:4])`; `volume_years = (min, max)` over cases (always populated; `VolumesMetadata.start_year/end_year` are 0 or None for 100% of F.2d, F. Supp., F. Supp. 2d, 94% of F.3d and 92 U.S. volumes and are **never used for a year test**).
- `court_name = case["court"]["name"]`, `name = name_abbreviation`.

### 1.6 Pre-classification passes over the extracted citations (in this order)
1. **Skip classes.** `IdCitation`, `SupraCitation`, `ShortCaseCitation` → `skipped` ("short-form citation (Id./supra/short form); the full citation it points to is checked instead"). `FullLawCitation`, `FullJournalCitation` → `skipped` ("statute, regulation or journal citation; out of scope"). A `FullCaseCitation` followed within 40 chars by `slip op.` → `not_in_free_corpus` ("slip opinion; not held by the free corpus").
2. **Subsequent history.** If the 40 chars before a `FullCaseCitation` match `r"cert\.\s*(denied|granted|dismissed)|aff'd|rev'd|vacated|reh'g|denying cert"` → `skipped` ("subsequent-history citation (cert. denied etc.); not checked"). These carry no party names and land on U.S. orders pages CAP holds unevenly (us/550 has nothing past page 661; us/556 nothing between 961 and 1401).
3. **Parallel groups.** Consecutive `FullCaseCitation`s whose spans are separated by ≤ 3 characters (`, `) and whose normalized `plaintiff`, `defendant` and Y are equal form one group → one memo row, counted once. Order members: the one whose reporter has a CAP slug and a present volume first; then by cite_type `federal` before `state` before others. The first member is the **primary**; the others go to `parallel_cites` and are handled in step 10.
4. **Unrecognized-reporter catch** on spans no eyecite citation covers (§2 step 1).
5. **Run limit.** At most 60 distinct (slug, volume) pairs per memo, in order of first appearance; citations in later volumes → `not_checked` ("run limit: more than 60 volumes in one filing; run the rest separately").

---

## 2. The ordered rule (`rules.classify(cite, ctx) -> CitationResult`)

`ctx` holds the already-fetched objects from §1.4–1.5 for the citation's slug/volume (pure function; tests build `ctx` from `seed/cache`). Steps run in order; the first `return` wins. "Note" means append to `reasons`/`evidence` and continue.

**Step 1 — Unrecognized reporter.**
Applies to strings the catch regex found that eyecite did not parse:
```
r"\b(\d{1,4})\s+((?:[A-Z][A-Za-z.']*\.?\s){1,5}(?:\d(?:st|d|nd|rd|th)\s)?)(\d{1,5})\b"
```
Accept a match only if **all** hold: (a) the reporter group contains a period or an ordinal series token (`2d`, `3d`, `4th`, `5th`); (b) no reporter token is a month name or one of `Page, Gate, Entry, Chapter, Section, Article, Exhibit, Docket, No., Line, Paragraph, Seat, Flight, Statement, Deposition, Through, Requires, Lines` and none is `U.S.C., C.F.R., Civ., Cr., Tr., Stat., Fed. Reg.`; (c) the 6 tokens before the match are not `No., Docket, ECF, Rule, Exhibit, Page, Flight, Boeing, Article, Section, Chapter`; (d) ` v. ` or `In re` occurs within 120 chars before, **or** `(` … 4-digit year `)` occurs within 40 chars after. If the normalized reporter group (§1.3 key) resolves in reporters_db or CAP after all, run it through steps 2–11 as a normal citation instead.
→ `unrecognized_reporter`; reasons `["citation-like string with a reporter this tool does not know: 'R'. Check the reporter abbreviation by hand."]`; evidence `{"matched_text": ...}`; source `none`.
Verified on the seed: `88 Fed. Air Rptr. 3d 412 (2018)` matches (tokens `Fed. Air Rptr. 3d`, year parenthetical after); `3 May 2019`, `12 June 2020`, `Exhibit 3 Page 4`, `17 Montreal Convention 1999`, `Boeing 737 MAX 8`, `22 Civ. 1461`, `28 U.S.C. 1332`, `Rule 56 Statement 3` produce no row.

**Step 2 — Citations no free corpus holds, by `cite_type`.**
- `specialty_west`, `specialty_lexis` (`WL`, `LEXIS`, `U.S. Dist. LEXIS`) → `not_in_free_corpus`; reasons `["proprietary citation (Westlaw/Lexis); not checkable in a free corpus"]`.
- `neutral` (`IL App (1st)`, other public-domain formats) → `not_in_free_corpus`; reasons `["public-domain neutral citation; the free corpus does not index this format; check the court's own site"]`.
Evidence `{"cite_type": ...}`, source `none`.

**Step 3 — Edition-year note (never a class).**
If Y is known: `edition = [min(reporters_db start year, CAP start_year for the slug) − 1, max(reporters_db end year or 9999, CAP end_year) + 1]`. If Y is outside → note `"the filing's year Y is outside the years both sources give for R (A–B)"`, `evidence.edition_range = "A–B"`. Continue.
Why not a class: reporters_db dates `U.S.` from 1875 (Marbury, 5 U.S. 137 (1803) is real and in CAP at us/5 first_page 137) and ends `F. Supp.` in 1988 (CAP's f-supp/999 holds 1996–1998 decisions). The class is decided by what sits at the page.

**Step 3b — Resolve the CAP slug.**
No slug for `R` (§1.3) → `not_in_free_corpus`; reasons `["R is not held by the Caselaw Access Project (its federal coverage ends 2019–2020; F.4th began 2021); check CourtListener or Westlaw"]`; evidence `{"reporter": R, "reporters_db_edition": "START–END|open"}`; source `none`. (`60 F.4th 1`, `123 N.Y.S.3d 456`.)

**Step 4 — Volume range** (`VolumesMetadata` for the slug).
- `Failed` → `not_checked` (reason wording in §6). `Absent` for a slug ReportersMetadata lists → `not_in_free_corpus` ("R is listed by the free corpus but its volume index is not published").
- `V > Vmax` → §3 decides: `likely_fabricated` only for a closed West series at its ceiling; otherwise `not_in_free_corpus` with reasons `["R volumes after Vmax (the free corpus ends CAP_END for R) are not in the free corpus; check CourtListener/Westlaw"]` plus the plausibility note when it fires. With `COURTLISTENER_TOKEN` and a CL status 200 for this citation → `verified`, source `CourtListener`, no quote check (v1), note "confirmed by CourtListener; opinion text not fetched".
- `V ≤ Vmax` and `V` not in `volumes` → `not_in_free_corpus`; reasons `["volume V of R is not in the free corpus; check CourtListener/Westlaw"]` (F. Supp. 3d 183–184, 203–206 are real volumes CAP lacks).
- Evidence always: `{"vmax": Vmax, "cap_end_year": ..., "volume_present": bool}`.

**Step 5 — Cases in the volume** (`CasesMetadata` for slug/V).
`Failed` → `not_checked`. `Absent` → `not_in_free_corpus` ("volume V of R is listed but its cases are not in the free corpus"). Otherwise build the §1.5 index. No class is set here: **page-beyond-end and year tests no longer set a class at this step** (they were the source of every false red in the adversary runs).

**Step 6 — Locate the page** (ordered; §5 defines `match(case) ∈ {full, partial, none, no_names}`).
6a. `candidates = by_official_cite["V R P"] ∪ by_first[P]` (deduped). If non-empty, evaluate `match` for every candidate:
  - any `full` → **`verified`** (pick the full match with the longest span; others → `evidence.other_entries`). Go to step 8.
  - none full, any `partial` → **`wrong_cite_exists`**; reasons `["the case that begins at V R P is <name> (<court>, <decision_date>); the filing calls it <plaintiff> v. <defendant> (one party name matches)"]`; evidence `real_case_at_page`. Go to step 8 (year note), skip quote check.
  - `no_names` (eyecite gave neither party) → **`verified`** with reasons `["the filing gives no party names; the case that begins at V R P is <name>"]` (if several candidates, list them; `verified` still). Go to step 8.
  - all `none` → **step 7 with context `page_hit`**.
6b. No candidates; `spans` non-empty (P inside one or more cases; West reporters start a case on the page where the previous one ends, so 6a runs first — 121 of 145 cases in 174 F.3d begin on the previous case's last page):
  - any `full` → **`wrong_cite_exists`**; reasons `["<name> begins at V R first_page; page P is inside it (first–last)"]`; evidence `real_case_at_page`, `first_page`. Step 8.
  - `partial` → **`wrong_cite_exists`**; reasons `["page P is inside <name> (first–last), which begins at first_page; one party name differs from the filing's <plaintiff> v. <defendant>"]`. Step 8.
  - `no_names` → **`wrong_cite_exists`**; reasons `["page P is inside <name> (first–last), which begins at first_page"]`.
  - all `none` → **step 7 with context `inside_span`**.
6c. P not in `covered` → **step 7 with context `gap`** and `gap_kind = "beyond_end" if P > max_last else "hole"`.

**Step 7 — Name search across the volume** (§5 scoring, all cases incl. those without page digits).
Rank hits by `(last − first)` descending, then `first` ascending, so an opinion outranks its order entries (Olympic Airways v. Husain sits in 540 U.S. at 644 (opinion), 807 and 964 (orders)). A hit with `first == last` is never the primary location when a longer entry exists; extra hits → `evidence.other_entries`.
- any `full` hit → **`wrong_cite_exists`**; reasons `["<name> is in this volume at V R first_page, not page P"]` (+ from `page_hit`/`inside_span`: `"page P belongs to <real case at page> (first–last)"`). Step 8.
- no `full`, any `partial` hit whose court is consistent (§5.4; when either side has no court, it is consistent) → **`wrong_cite_exists`**; reasons `["only one party name matches a case in this volume: <name> at V R first_page"]`. Step 8.
- no hit:
  - context `gap`, `hole`: → **`not_in_free_corpus`**; reasons `["page P of V R is not in the free corpus (it holds pages A–B of this volume with gaps); no case named <A> or <B> in the pages it holds"]`.
  - context `gap`, `beyond_end`: → **`not_in_free_corpus`**; reasons `["the last case the free corpus holds in V R ends at page max_last; page P is beyond it; no case named <A> or <B> in the volume"]`. Why not red: table decisions and orders sit past CAP's last held case (us/550 ends at 661 in CAP; real orders sit at 550 U.S. 9xx).
  - context `page_hit` or `inside_span`, reporter `U.S.` and (P ≥ 801 **or** every candidate/spanning case at P is a one-page entry `first == last`) → **`not_in_free_corpus`**; reasons `["orders pages of U.S. Reports are not fully held by the free corpus; the entries it holds at page P are <names>"]`.
  - context `page_hit` or `inside_span` otherwise → **`likely_fabricated`**; reasons `["page P of V R belongs to <name> (first–last); no case in volume V R is named <plaintiff> or <defendant>"]` (for `page_hit`: `"page P is where <name> begins"`); evidence `{"real_case_at_page": {...}, "searched_names": [...], "nearest_caption": <best-scoring name and its scores>}`. The year note (step 8) is added if it also disagrees.
  - eyecite gave **no party names** and context is `page_hit`/`inside_span` → cannot happen (6a/6b return `verified`/`wrong_cite_exists` on `no_names`); in `gap` → `not_in_free_corpus` with `"the filing gives no party names and no case text sits at this page in the free corpus"`.

**Step 8 — Year note against the matched case (never changes the class).**
For every `verified`/`wrong_cite_exists` with a matched case and a known Y: if `|Y − decision_year(case)| > 1` → note `"the filing gives year Y; the opinion is dated <decision_date>"`, `evidence.year_mismatch = {"cited": Y, "decided": decision_date}`. CAP's U.S. volume labels are October Term years (470 U.S. → 1984, decisions 1985), which is why volume years are never compared.
Why the class stays: two of the three findings on this point ask for a note, and the row already names the real case at the right page; moving a one-digit slip to amber would print "exists at ..., not ..." for a citation whose volume and page are right.

**Step 9 — Quote check** (`verified` only, when a quoted passage is attached): §4. May change the class to `quote_not_found`. Pin cites: `pincite_unverified = True` with note `"pin page P′ not verifiable: the free corpus text has no page numbers"` (never a class).

**Step 10 — Parallel citations** (group primary is `verified`): for each other member, look for its `V R P` in the matched case's `citations[].cite` (CAP record for 516 U.S. 217 lists `133 L. Ed. 2d 596`, `116 S. Ct. 629`, `1996 U.S. LEXIS 469`). Exact match → `parallel_cites` entry `"116 S. Ct. 629 — confirmed by the CAP record"`. Same reporter, different page/volume → the row stays `verified`, reasons add `"the filing's parallel cite 116 S. Ct. 926 differs from the record's 116 S. Ct. 629"`, `evidence.parallel_mismatch`. Reporter absent from the record → `"116 S. Ct. 629 — not listed in the CAP record; not checked"`. Steps 4–7 run on a non-primary member only when no member verified; the group's class is then the best class in the order `verified > quote_not_found > wrong_cite_exists > not_in_free_corpus > not_checked > unrecognized_reporter > likely_fabricated`.
Why one row: the row describes the case; a fabricated parallel attached to a real case is a discrepancy the reason line shows, not a second case.

**Step 11 — Advisory** (unchanged from BUILD-NOTES; `verified` with a quote and a proposition, key present): never changes the class.

---

## 3. Volume beyond coverage (`V > Vmax`): the rule, the plausibility note, worked examples

Inputs per reporter: `Vmax`, `cap_end` = max non-zero `end_year` in VolumesMetadata, else ReportersMetadata `end_year`; `edition` = eyecite `edition_guess` (`start`, `end`, sibling editions); `today.year` = 2026.

**3.1 Class.** `likely_fabricated` fires from volume arithmetic in exactly one situation:
```
edition.end is not None            # reporters_db says the edition is closed
and Vmax == 999                    # CAP holds the series to its last volume (West restarts numbering at 1000)
and V >= 1000
```
reasons `["R ended at volume 999 (reporters_db closes the edition on END; the free corpus holds volumes to 999); volume V does not exist in this series"]`. Applies today to `F.2d` (end 1993-12-31, Vmax 999), `F. Supp.` (end 1988-12-31 in reporters_db; CAP 1839–1998; Vmax 999), `F. Supp. 2d` (end 2014-08-21, Vmax 999). Every other `V > Vmax` → `not_in_free_corpus`.
Why this and not the wider "closed **or** has a successor edition" ceiling: reporters_db leaves `F.3d` open (`end None`) while listing `F.4th` from 2021-01-01, and CAP's f3d stops at 935; that F.3d ended at 999 is knowledge outside both data sources. Hard-coding it is the same kind of hand-entered fact that made reporters_db end `F. Supp.` in 1988. So `1100 F.3d` stays amber with a plain note (below). Flip `SERIES_CEILING_REQUIRES_CLOSED = False` in `rules.py` once a source for F.3d's last volume is added to BUILD-NOTES §1.

**3.2 Plausibility note (evidence only, `evidence.plausibility`).**
```
rate  = count of volumes whose start_year == cap_end or end_year == cap_end (ignore 0/None)
if rate == 0: rate = Vmax / (cap_end − edition.start.year)         # whole-series fallback
bound = Vmax + (today.year − cap_end + 2) × rate × 3
```
If `V > bound` → note `"volume V is improbable: R reached Vmax by cap_end; about rate volumes were labelled cap_end; even at three times that pace the series would be near bound today"`. If `V ≥ 1000` and a sibling edition starts after this one (`F.3d` → `F.4th` 2021-01-01) → note `"volume V is above 999, the last volume of the West series held by the free corpus for F.2d, F. Supp. and F. Supp. 2d; reporters_db lists F.4th from 2021-01-01"`. Neither note changes the class.

**3.3 Worked examples (values measured 2026-09-26).**

| Input | Slug / Vmax / cap_end | rate | bound | Class | Row wording |
|---|---|---|---|---|---|
| `1000 F.3d 1 (2021)` | f3d / 935 / 2019 | 25 volumes touch 2019 | 935 + 9×25×3 = **1610** | `not_in_free_corpus` | "F.3d volumes after 935 (the free corpus ends 2019 for F.3d) are not in the free corpus" + note "volume 1000 is above 999 … F.4th from 2021-01-01" |
| `1100 F.3d 50 (2023)` | f3d / 935 / 2019 | 25 | 1610 | `not_in_free_corpus` | same, note names volume 1100 |
| `60 F.4th 1 (2d Cir. 2023)` | no CAP slug | — | — | `not_in_free_corpus` (step 3b) | "F.4th is not held by the Caselaw Access Project (…F.4th began 2021); check CourtListener or Westlaw" |
| `700 F. Supp. 3d 10 (2024)` | f-supp-3d / 392 / 2019 | 43 | 392 + 9×43×3 = **1553** | `not_in_free_corpus` | "F. Supp. 3d volumes after 392 (…ends 2019) are not in the free corpus" (no plausibility note: 700 < 1553) |
| `600 U.S. 477 (2023)` (Biden v. Nebraska, seed) | us / 572 / 2014 | 2 | 572 + 14×2×3 = **656** | `not_in_free_corpus` (or `verified` via CourtListener) | "U.S. volumes after 572 (the free corpus ends 2014 for U.S.) are not in the free corpus; check CourtListener/Westlaw" |
| `678 F. Supp. 3d 443 (S.D.N.Y. 2023)` (Mata, page-1 label) | f-supp-3d / 392 / 2019 | 43 | 1553 | `not_in_free_corpus` | as F. Supp. 3d row; excluded from the eval count by cite_text |
| `1005 F.2d 1 (1994)` | f2d / 999 / (0-years → ReportersMetadata 1993); edition closed 1993-12-31 | — | — | **`likely_fabricated`** | "F.2d ended at volume 999 …; volume 1005 does not exist in this series" |
| `1050 F. Supp. 2d 45 (2015)` | f-supp-2d / 999 / 2014; closed 2014-08-21 | — | — | **`likely_fabricated`** | as above for F. Supp. 2d |
| `146 S. Ct. 100 (2026)` | s-ct / 140 / 2020 | 1 | 140 + 8×1×3 = 164 | `not_in_free_corpus` | "S. Ct. volumes after 140 …" |
| `210 L. Ed. 2d 1 (2021)` | l-ed-2d / 181 / (years None → ReportersMetadata 2012) | fallback 181/(2012−1956)≈3.2 | 181 + 16×3.2×3 ≈ 335 | `not_in_free_corpus` | "L. Ed. 2d volumes after 181 …" |

The old BUILD-NOTES estimate ("last 10 volumes' years", ×1.5) gave 2.5–3.3 volumes/year for F.3d and F. Supp. 3d (thresholds 980 and 426–437) and undefined arithmetic for every reporter whose volume years are 0/None; it labelled Mata v. Avianca red. It is removed.

---

## 4. Quote matcher (`quotes.py`)

Input: quoted passage `q` (≥ 25 chars) attached to a `verified` citation; opinion text `t` = concatenation of `casebody.opinions[].text` of the matched case file (`cases/{file_name}.json`), majority first.

**4.1 Normalize both sides** (`norm_quote`): NFKC; curly quotes → straight (`“”„` → `"`, `‘’` → `'`); dashes `–—` → `-`; remove soft hyphens `­`; join hyphenated line breaks `(\w)-\s*\n\s*(\w)` → `\1\2` and `(\w)- (\w)` → `\1\2` only when the joined word appears elsewhere in `t` (otherwise keep the hyphen); unwrap bracket alterations on single words `\[(\w)\](\w+)` → `\1\2` and `\[(\w+)\]` → `\1`; drop `(citation omitted)`, `(internal quotation marks omitted)`, `(emphasis added)`, `(footnote omitted)` parentheticals inside the quote; collapse whitespace; lowercase; strip punctuation except the ellipsis marker. Tokens = `re.findall(r"[a-z0-9]+", s)`.

**4.2 Segment.** Split `q` on ellipses (`. . .`, `...`, `…`) into ordered segments; drop segments with fewer than 4 tokens after normalization (they cannot be located reliably; note `"short quote fragment not checked"`).

**4.3 Locate and compare each segment.**
```
ratio, dest_start, dest_end = rapidfuzz.fuzz.partial_ratio_alignment(seg, t_norm)   # score + span in t
window = t_norm[dest_start : dest_end] widened to token boundaries and by 2 tokens each side
diff   = difflib.SequenceMatcher(None, tokens(seg), tokens(window), autojunk=False).get_opcodes()
n_diff = sum(max(i2 − i1, j2 − j1) for tag, i1, i2, j1, j2 in diff if tag != "equal")  # widened tokens beyond the aligned ends do not count
```
Segments must also appear in `t` in the same order as in `q` (each `dest_start` ≥ the previous segment's `dest_end`); otherwise treat the passage as `n_diff > 3`.

**4.4 Decision (whole passage).**
| Condition | Class | `quote_check.status` | Row wording |
|---|---|---|---|
| exact substring of `t_norm` for every segment, or `n_diff == 0` for every segment | stays `verified` | `verbatim` | "quoted passage found in the opinion text" (+ "with an omission marked by ellipsis" when segmented) |
| total `n_diff` in 1–3 and min segment `ratio ≥ 70` | `quote_not_found` | `differs` | "the quoted passage differs from the opinion text in N word(s): 'X' → 'Y'; the opinion's passage is shown" |
| total `n_diff > 3`, or any `ratio < 70`, or order violated | `quote_not_found` | `not_found` | "the quoted passage was not found in the opinion text; the closest passage is R% similar and is shown" |

`quote_check` always carries `{"status", "similarity": min ratio, "closest_passage": window ±200 chars of raw text, "diff": [("X","Y"),...], "segments": n}`. Never write "misquoted" as a fact; the row says "differs from the opinion text".

Measured on 516 U.S. 217 text (26,490 chars): verbatim 100 → `verbatim`; one word swapped 95.3–97.0 and `not` inserted 97.0 → `differs` (1 word) — under the old ≥ 92 rule these were `verified`; two words changed 91.5 → `differs` (2); three 89.1 → `differs` (3); Bluebook `. . .` omission 89.0 and unicode ellipsis 87.0 → `verbatim` by segments (old rule: `quote_not_found_verbatim`); `[T]he` 98.6 and hyphenated line breaks 95.8–98.6 → `verbatim` after normalization; generic phrases 75–78 → `not_found`. Seed rows: Iqbal (4 words changed, 90.5) → `quote_not_found`/`not_found`; Chan (3 words changed, 81.2) → `quote_not_found`/`differs`. Speed: 160-char quote vs 179,251-char Azar text 0.002 s.

---

## 5. Name matching (`rules.match`, `rules.name_search`)

**5.1 Normalize a party or caption** (`norm_name`): lowercase; NFKC; `&` → `and`; collapse whitespace (eyecite's `Estate  Durden`); expand Bluebook T6 abbreviations from a fixed table (`servs.→services, serv.→service, enters.→enterprises, ass'n→association, atl.→atlantic, sec'y→secretary, dep't→department, comm'r→commissioner, corp.→corporation, ins.→insurance, int'l→international, nat'l→national, mfg.→manufacturing, bd.→board, univ.→university, hosp.→hospital, r.r.→railroad, ry.→railway, co.→company, inc.→incorporated, ltd.→limited, bros.→brothers, indus.→industries, tech.→technology, transp.→transportation, ctr.→center, auth.→authority`); drop leading procedural phrases `in re, in the matter of, matter of, ex parte, ex rel., estate of, on behalf of, petition of, application of, marriage of`; drop trailing suffixes `incorporated, company, corporation, limited, llc, llp, lp, plc, gmbh, s.a., n.v., et al., et al` (repeat until none); strip remaining punctuation.

**5.2 Generic parties (stoplist, after normalization).** `united states, state, people, commonwealth, city, county, town, village, board, department, secretary, attorney general, commissioner, administrator, director, warden, superintendent, government, doe, roe, estate, in re, ex parte, matter, plaintiff, defendant, petitioner, respondent, appellant, appellee, ins, co, corp, inc, ltd, llc` and any party that, after normalization, has fewer than 5 letters (`doe`, `roe`, `iran`, `saks`, `j d`). A generic party can **confirm** a match (as the second half of a full match) but can never **carry** one alone. Counts behind this: 37 of 145 cases in 174 F.3d, 30 of 116 in 925 F.3d and 30 in 516 U.S. are `United States v. …`; 516 U.S. has 44 `Williams`, 40 `Jones`, 36 `Smith` cases.

**5.3 Score a filed party `a` against a CAP caption `name`.**
```
parts  = [norm_name(x) for x in name.split(" v. ", 1)]        # 1 part when the caption has no " v. " (In re, MDL, Ex parte: 181 of 4704 captions in 516 U.S.)
whole  = norm_name(name)
score(a, cand) = max(token_set_ratio(norm_name(a), cand), token_sort_ratio(norm_name(a), cand))
pl_score = max(score(pl, parts[0]), score(pl, whole))  if pl else None
df_score = max(score(df, parts[1]), score(df, whole))  if df and len(parts) == 2 else (max(score(df, whole)) if df else None)
```
`match(case)`:
- **`no_names`**: `pl` and `df` both `None`.
- **`full`**: both present and `pl_score ≥ 80 and df_score ≥ 80`; **or** exactly one present, it is not generic, and its score ≥ 85.
- **`partial`**: not full, and at least one **non-generic** party has `token_sort_ratio ≥ 90` against `parts` or `whole`.
- **`none`**: otherwise.
Measured: `Garlock` vs `Garlock, Inc.` → 100 after suffix drop (raw token_set_ratio was 70); `ISS Marine Servs.` vs `ISS Marine Services, Inc.` → 100 after the T6 expansion `servs.→services` plus the suffix drop (91.4 with the suffix drop alone; raw 76); `Bell Atl. Corp.` vs `Bell Atlantic Corp.` → 100; `Papst Licensing GmbH & Co. KG Litigation` vs whole `In re Papst Licensing GmbH & Co. KG Litigation` → 100 (raw against the empty second part: 0); `United States` vs `United States` → 100 but generic, so `United States v. Varghese` at 905 F. Supp. 2d 121 (real: `United States v. ISS Marine Services, Inc.`, `Varghese` vs `ISS Marine Services` 24) → `none`, not `verified`; `Iran Air` vs `ISS Marine Services, Inc.` 24 → `none`; `Doe` vs `J.D.` 28.6 and `Becerra` vs `Azar` 18.2 → `none`.

**5.4 Court consistency (soft; step 7 partial hits only).** Extract an ordinal circuit from the filing's court text (`r"(\d+)(?:st|d|nd|rd|th)\s+Cir\."` → `Second`, `Third`, … `Eleventh`; `D.C. Cir.` → `District of Columbia`; `Fed. Cir.` → `Federal`) and from CAP `court.name` (`… for the Third Circuit`; the D.C. Circuit appears as `Court of Appeals of the District of Columbia`). Inconsistent only when both extract and differ. District courts and state courts: no check in v1. The seed's `Miller v. United Airlines, Inc., 174 F.3d 366 (2d Cir. 1999)` gets partial hits `Miller v. City of Philadelphia` (368, Third Circuit) and `Miller v. Woodharbor Molding & Millworks, Inc.` (948, Eighth Circuit); the circuit check drops both (Third and Eighth ≠ Second), and `Woodharbor` fails the `United Airlines` score (22.9) regardless, and the `page_hit`/`inside_span` context yields `likely_fabricated`. Year is **not** a hit filter in step 7 (a wrong page plus a wrong year on a real case must still resolve to `wrong_cite_exists`); it is noted by step 8.

**5.5 Why a page hit with zero matching parties can still be red.** One finding asked that "a real page hit is never `fabricated`" and would route `Petersen v. Iran Air, 905 F. Supp. 2d 121` (a Mata fabrication whose page is exactly where `United States v. ISS Marine Services` begins) to `wrong_cite_exists`. Another finding asks that a match carried only by a generic party or by nothing be `likely_fabricated` with the nearest caption named. The spec takes the middle: a real case cited by a filer keeps at least one distinctive party name somewhere in the volume (Doe v. Garlock → `partial` → `wrong_cite_exists`, name differs); a citation in which **neither** party appears anywhere in the volume's captions, at a page that belongs to a differently named case, is the Mata pattern, and the reason line names the real case so staff can check it in one look. A real case with both party names wrong and a wrong page is indistinguishable from a fabrication by any deterministic rule; the memo wording stays an observation for that reason.

---

## 6. Failure handling and user-facing wording

**6.1 Failures → `not_checked`** (never counted in the red or coverage registers; own line in the counts panel): any `Failed` from §1.4 (timeout after 1 retry, connection error, HTTP 5xx, 429, 200 with a non-JSON body); CourtListener 429/400 or text not fetched (the CAP result still decides when CAP answered; `not_checked` only when CAP also failed); run limit (§1.6 item 5); any exception inside `classify` (caught per citation, logged with the citation text; the memo never 500s because of one row). Wording: "could not be checked: the free corpus did not answer for V R (timeout | server error | unreadable reply). Run again or check by hand." CourtListener: chunk at 250 citations per request, stop on the first 429 and mark the rest "CourtListener throttled; CAP result shown" (class from CAP unchanged).

**6.2 Data shapes** (all handled in §1.5, listed for the test writer): non-integer `first_page`/`last_page` (`'377-391'`, `'1227-1235'`, `'385-393'`); `last_page < first_page` (`'1'`/`'0'`); cases with no page digits (excluded from page lookups, kept for name search); several cases beginning on one page (373 pages in 516 U.S.; up to 15 orders per page); official cite ≠ first_page (`516 U.S. 545` → 803); duplicate `volume_number` rows (a3d: 41); `start_year`/`end_year` 0 or None; eyecite year as a string and wrong; eyecite court `None` for `3d Cir.`; eyecite `Estate  Durden`; `In re` captions with no `v.`; 404 bodies that are HTML; volumes CAP skips (F. Supp. 3d 183–184, 203–206); CAP's `us` slug holding nominative-era volumes 1–90 with 0/None years.

**6.3 Row wording per class (first `reasons[]` sentence; observations, never verdicts).**
| Class | Label on the row | Wording pattern |
|---|---|---|
| `verified` | Found | "Found in the free corpus: <name>, V R first_page (<court>, <decision_date>)." Optional notes: "the filing gives year Y; the opinion is dated D"; "pin page P′ not verifiable: the free corpus text has no page numbers"; "the filing gives no party names; the case at this page is <name>"; "confirmed by CourtListener; opinion text not fetched" |
| `quote_not_found` | Quote differs / Quote not found | `differs`: "The quoted passage differs from the opinion text in N word(s): 'X' → 'Y'. The opinion's passage is shown." `not_found`: "The quoted passage was not found in the opinion text; the closest passage is R% similar and is shown." |
| `wrong_cite_exists` | Exists, cited differently | pin page: "<name> begins at V R first_page; page P is inside it (first–last)." wrong page: "<name> is in this volume at V R first_page, not page P." name differs: "The case that begins at V R P is <name>; the filing calls it <A> v. <B>." |
| `not_in_free_corpus` | Not in the free corpus | one of: "R volumes after Vmax (the free corpus ends CAP_END for R) are not in the free corpus; check CourtListener/Westlaw." · "Volume V of R is not in the free corpus." · "Page P of V R is not in the free corpus (it holds pages A–B of this volume with gaps)." · "The last case the free corpus holds in V R ends at page N; page P is beyond it." · "Orders pages of U.S. Reports are not fully held by the free corpus." · "Proprietary citation (Westlaw/Lexis); not checkable in a free corpus." · "Public-domain neutral citation; the free corpus does not index this format." · "R is not held by the Caselaw Access Project (…); check CourtListener or Westlaw." |
| `unrecognized_reporter` | Reporter not known | "Citation-like string with a reporter this tool does not know: 'R'. Check the reporter abbreviation by hand." |
| `likely_fabricated` | Likely fabricated | "Page P of V R belongs to <name> (first–last). No case in volume V R is named <A> or <B>. Verify before relying on this." · ceiling: "R ended at volume 999; volume V does not exist in this series." |
| `not_checked` | Not checked | "Could not be checked: the free corpus did not answer for V R (<reason>). Run again or check by hand." |
| `skipped` | Skipped | "Short-form citation (Id./supra); the full citation it points to is checked instead." · "Statute or regulation; out of scope." · "Subsequent-history citation (cert. denied etc.); not checked." |

Memo header (unchanged): "Triage aid. Not a finding. Verify flagged rows before relying on them." The word "fabricated" appears on screen only inside the label "likely fabricated".

---

## 7. Test matrix (`tests/test_rules.py` parametrizations)

Columns: id · input text as it appears in a filing · fixture data needed (all `seed/cache/cap/**` unless noted; `+` marks a fixture to add with `scripts/warm_cache.py`) · expected class · `reasons[0]` must contain · notes (quote status, evidence keys). "Seed" rows are the 20 scored items of `seed/ground_truth.json` (Greenleaf reads `3d Cir.` in the filing, as corrected there).

| # | id | Input (filing text) | Fixture | Expected class | reasons[0] contains | Notes |
|---|---|---|---|---|---|---|
| 1 | seed mata-varghese | `Varghese v. China Southern Airlines Co., 925 F.3d 1339 (11th Cir. 2019)` | f3d/925 | `likely_fabricated` | `belongs to J.D. v. Azar (1291–1349)` | 6b none → 7 no hit, context inside_span |
| 2 | seed mata-petersen | `Petersen v. Iran Air, 905 F. Supp. 2d 121 (D.D.C. 2012)` | f-supp-2d/905 | `likely_fabricated` | `United States v. ISS Marine Services, Inc.` | 6a candidate, match none (`Iran` <5 letters, `Petersen` 0 hits); §5.5 |
| 3 | seed mata-miller | `Miller v. United Airlines, Inc., 174 F.3d 366 (2d Cir. 1999)` | f3d/174 | `likely_fabricated` | `belongs to Greenleaf v. Garlock, Inc. (352–368)` | partial hit Miller v. City of Philadelphia dropped by circuit check (Third ≠ Second); requires page parsing of `'377-391'` |
| 4 | seed mata-shaboon | `Shaboon v. Egyptair, 2013 IL App (1st) 111279` | none | `not_in_free_corpus` | `public-domain neutral citation` | step 2 (cite_type neutral) |
| 5 | seed mata-martinez | `Martinez v. Delta Air Lines, Inc., 2019 WL 4639462 (Tex. App. 2019)` | none | `not_in_free_corpus` | `proprietary citation` | step 2 |
| 6 | seed mata-durden | `Estate of Durden v. KLM Royal Dutch Airlines, 2017 WL 2418825 (Ga. Ct. App. 2017)` | none | `not_in_free_corpus` | `proprietary citation` | eyecite pl `Estate  Durden`; step 2 before any name logic |
| 7 | seed real-zicherman | `"Absent such legislation, however, Articles 17 and 24(2) provide nothing more than a pass-through, authorizing us to apply the law that would govern in absence of the Warsaw Convention." Zicherman v. Korean Air Lines Co., 516 U.S. 217 (1996)` | us/516 + 0217-01 | `verified` | `Zicherman ex rel. Estate of Kole v. Korean Air Lines Co.` | `ex rel.`/`Estate of` dropped by norm; quote `verbatim` |
| 8 | seed real-tseng | `El Al Israel Airlines, Ltd. v. Tsui Yuan Tseng, 525 U.S. 155 (1999)` + seed quote | us/525 + 0155-01 | `verified` | `525 U.S. 155` | also appears at 958 (order): step 6a picks the 155 opinion |
| 9 | seed real-husain | `Olympic Airways v. Husain, 540 U.S. 644 (2004)` + seed quote | us/540 + 0644-01 | `verified` | `540 U.S. 644` | entries at 807 and 964 → `evidence.other_entries` |
| 10 | seed real-saks | `Air France v. Saks, 470 U.S. 392 (1985)` + seed quote | us/470 + 0392-01 | `verified` | `470 U.S. 392` | volume label 1984–1984 ignored; `Saks` <5 letters but both parties match → full |
| 11 | seed real-floyd | `Eastern Airlines, Inc. v. Floyd, 499 U.S. 530 (1991)` + seed quote | us/499 + 0530-01 | `verified` | `499 U.S. 530` | eyecite `metadata.year` says 2019; regex year 1991; no year note |
| 12 | seed real-azar | `J.D. v. Azar, 925 F.3d 1291 (D.C. Cir. 2019)` + seed quote | f3d/925 + 1291-01 | `verified` | `925 F.3d 1291` | 6a before 6b: United Steel v. MSHA ends at 1291 and must not win |
| 13 | seed real-greenleaf | `Greenleaf v. Garlock, Inc., 174 F.3d 352 (3d Cir. 1999)` + seed quote | f3d/174 + 0352-01 | `verified` | `174 F.3d 352` | volume years 0/0 ignored; New Castle County ends at 352 and must not win |
| 14 | seed real-twombly | `Bell Atlantic Corp. v. Twombly, 550 U.S. 544 (2007)` + seed quote | us/550 + 0544-01 | `verified` | `550 U.S. 544` | |
| 15 | seed misq-iqbal | `"A claim has facial plausibility when the plaintiff alleges factual content that permits the court to draw a reasonable inference that the defendant is responsible for the misconduct alleged." Ashcroft v. Iqbal, 556 U.S. 662 (2009)` | us/556 + 0662-01 | `quote_not_found` | `was not found in the opinion text; the closest passage is 9` | 4 tokens differ → status `not_found`, similarity ≈ 90.5 |
| 16 | seed misq-chan | `"But where the text is clear, as it is here, we have no authority to add an exception." Chan v. Korean Air Lines, Ltd., 490 U.S. 122 (1989)` | us/490 + 0122-01 | `quote_not_found` | `differs from the opinion text in 3 word(s)` | status `differs`; diff `power→authority, insert→add, amendment→exception` |
| 17 | seed cov-biden-nebraska | `Biden v. Nebraska, 600 U.S. 477 (2023)` | us/VolumesMetadata | `not_in_free_corpus` (accept `verified` with CL) | `U.S. volumes after 572` | §3 row; no network probe of us/600 needed |
| 18 | seed cov-loper-bright | `Loper Bright Enterprises v. Raimondo, 603 U.S. 369 (2024)` | us/VolumesMetadata | `not_in_free_corpus` (accept `verified` with CL) | `U.S. volumes after 572` | |
| 19 | seed wrong-zicherman-230 | `Zicherman v. Korean Air Lines Co., 516 U.S. 230 (1996)` | us/516 | `wrong_cite_exists` | `begins at 516 U.S. 217; page 230 is inside it (217–232)` | 6b full |
| 20 | seed unrec-alvarez | `See Alvarez v. Skyline Cargo, 88 Fed. Air Rptr. 3d 412 (2018).` | ReportersMetadata | `unrecognized_reporter` | `'Fed. Air Rptr. 3d'` | eyecite returns nothing; catch regex + conditions (a)(d) |
| 21 | label-mata | `Mata v. Avianca, Inc., 678 F. Supp. 3d 443 (S.D.N.Y. 2023)` | + f-supp-3d/VolumesMetadata | `not_in_free_corpus` | `F. Supp. 3d volumes after 392` | shown in the memo, excluded from the eval by cite_text |
| 22 | marbury | `Marbury v. Madison, 5 U.S. 137 (1803)` | + us/5 | `verified` | `5 U.S. 137` | step 3 note only (reporters_db U.S. from 1875); Turner v. Fendall ends at 137 and must not win |
| 23 | marbury-nominative | `Marbury v. Madison, 5 U.S. (1 Cranch) 137 (1803)` | + us/5 | `verified` | `5 U.S. 137` | eyecite corrected reporter `U.S.` |
| 24 | papst-in-re | `In re Papst Licensing GmbH & Co. KG Litigation, 905 F. Supp. 2d 43 (D.D.C. 2012)` | f-supp-2d/905 | `verified` | `In re Papst Licensing` | pl None; df vs whole caption → full |
| 25 | us-v-varghese | `United States v. Varghese, 905 F. Supp. 2d 121 (D.D.C. 2012)` | f-supp-2d/905 | `likely_fabricated` | `United States v. ISS Marine Services` | generic `United States` cannot carry; `Varghese` no hits |
| 26 | us-v-iran-air | `United States v. Iran Air, 905 F. Supp. 2d 121 (D.D.C. 2012)` | f-supp-2d/905 | `likely_fabricated` | `United States v. ISS Marine Services` | as 25 |
| 27 | doe-v-garlock | `Doe v. Garlock, 174 F.3d 352 (3d Cir. 1999)` | f3d/174 | `wrong_cite_exists` | `the case that begins at 174 F.3d 352 is Greenleaf v. Garlock, Inc.` | 6a partial (`Garlock` ≥ 90 after suffix drop; `Doe` generic) |
| 28 | saks-year-typo | `Air France v. Saks, 470 U.S. 392 (1986)` | us/470 | `verified` | `470 U.S. 392` | reasons include `the filing gives year 1986; the opinion is dated 1985-03-04` |
| 29 | iqbal-year-2010 | `Ashcroft v. Iqbal, 556 U.S. 662 (2010)` (no quote) | us/556 | `verified` | `556 U.S. 662` | year note; never red |
| 30 | husain-wrong-page-year | `Olympic Airways v. Husain, 540 U.S. 700 (2007)` | us/540 | `wrong_cite_exists` | `Olympic Airways v. Husain is in this volume at 540 U.S. 644, not page 700` | step 7 ranks 644 (opinion) over 807/964 (orders); year not a filter, noted |
| 31 | cert-denied-550 | `Smith v. Jones, 100 F.3d 1 (2d Cir. 1996), cert. denied, 550 U.S. 901 (2007)` | us/550 | second cite `skipped` | `subsequent-history citation` | first cite runs normally (+ f3d/100 if asserted) |
| 32 | bare-orders-page | `556 U.S. 1104 (2009)` (no names, no history words) | us/556 | `not_in_free_corpus` | `page 1104 of 556 U.S. is not in the free corpus` | gap hole 962–1400 |
| 33 | holder-official-cite | `Holder v. Harlem Men's Shelter, 516 U.S. 545 (1996)` | us/516 | `verified` | `516 U.S. 545` | found via `by_official_cite` (first_page 803); `evidence.real_case_at_page.first_page == 803` |
| 34 | orders-shared-page | `Ruyle v. Continental Oil Co., 516 U.S. 1003 (1996)` | us/516 | `verified` | `516 U.S. 1003` | three cases share the official cite; names tested against each |
| 35 | orders-unknown-name | `Nobody v. Anyone, 516 U.S. 801 (1996)` | us/516 | `not_in_free_corpus` | `orders pages of U.S. Reports are not fully held` | 5 one-page entries at 801, no match; U.S. P ≥ 801 rule |
| 36 | f4th | `Smith v. Jones, 60 F.4th 1 (2d Cir. 2023)` | none | `not_in_free_corpus` | `F.4th is not held by the Caselaw Access Project` | step 3b; no network call made (assert on the fake client) |
| 37 | f3d-1000 | `Smith v. Jones, 1000 F.3d 1 (9th Cir. 2021)` | f3d/VolumesMetadata | `not_in_free_corpus` | `F.3d volumes after 935` | evidence.plausibility note mentions 999 and F.4th |
| 38 | f3d-1100 | `Smith v. Jones, 1100 F.3d 50 (9th Cir. 2023)` | f3d/VolumesMetadata | `not_in_free_corpus` | `F.3d volumes after 935` | same |
| 39 | f2d-1005 | `Smith v. Jones, 1005 F.2d 1 (9th Cir. 1994)` | + f2d/VolumesMetadata | `likely_fabricated` | `F.2d ended at volume 999` | §3.1 ceiling |
| 40 | fsupp2d-1050 | `Doe v. Roe, 1050 F. Supp. 2d 45 (S.D.N.Y. 2015)` | f-supp-2d/VolumesMetadata | `likely_fabricated` | `F. Supp. 2d ended at volume 999` | all volume years 0 → no arithmetic error |
| 41 | fsupp3d-700 | `Doe v. Roe, 700 F. Supp. 3d 10 (S.D.N.Y. 2024)` | + f-supp-3d/VolumesMetadata | `not_in_free_corpus` | `F. Supp. 3d volumes after 392` | |
| 42 | fsupp-1998 | `Smith v. Jones, 999 F. Supp. 1 (S.D.N.Y. 1998)` | + f-supp/999 | not `likely_fabricated` (assert class ∈ {verified, wrong_cite_exists, not_in_free_corpus}) | — | step 3 note only; `reasons` contain `outside the years both sources give` is **false** here (CAP says 1839–1998) |
| 43 | fsupp3d-missing-vol | `Doe v. Roe, 183 F. Supp. 3d 1 (2016)` | + f-supp-3d/VolumesMetadata | `not_in_free_corpus` | `volume 183 of F. Supp. 3d is not in the free corpus` | V ≤ Vmax, volume absent |
| 44 | so3d-spelling | `Doe v. Roe, 123 So. 3d 456 (Fla. 2013)` | + so3d/VolumesMetadata | any class except `unrecognized_reporter`/`not_in_free_corpus`-by-slug | — | assert `reporter_slug` resolves to `so3d` |
| 45 | miller-real-368 | `Miller v. City of Philadelphia, 174 F.3d 368 (3d Cir. 1999)` | f3d/174 | `verified` | `174 F.3d 368` | last_page `'377-391'` → 391; Greenleaf ends at 368 and must not win |
| 46 | griffith-real-1222 | `Griffith v. United States, 174 F.3d 1222 (Fed. Cir. 1999)` | f3d/174 | `verified` | `174 F.3d 1222` | last_page `'1227-1235'`; `United States` generic but both match → full |
| 47 | louisiana-inverted | `United States v. Louisiana, 525 U.S. 1 (1998)` | us/525 | `verified` | `525 U.S. 1` | first `'1'` last `'0'` → last = 1 |
| 48 | parallel-confirmed | `Zicherman v. Korean Air Lines Co., 516 U.S. 217, 116 S. Ct. 629, 133 L. Ed. 2d 596 (1996)` | us/516 + 0217-01 | one row, `verified` | `516 U.S. 217` | `parallel_cites` = 2 entries, both "confirmed by the CAP record"; counts +1 not +3 |
| 49 | parallel-mismatch | `Zicherman v. Korean Air Lines Co., 516 U.S. 217, 116 S. Ct. 926 (1996)` | us/516 + 0217-01 | one row, `verified` | `516 U.S. 217` | reasons include `parallel cite 116 S. Ct. 926 differs from the record's 116 S. Ct. 629` |
| 50 | prose-no-rows | `filed on 3 May 2019 and served 12 June 2020. See Exhibit 3 Page 4 and Docket No. 22 Civ. 1461. Boeing 737 MAX 8. Under Article 17 Montreal Convention 1999 and 28 U.S.C. 1332.` | none | no rows at all | — | catch regex conditions (a)–(d) |
| 51 | quote-one-word | seed Zicherman sentence with `petitioners`→`respondents`, cite `516 U.S. 217` | us/516 + 0217-01 | `quote_not_found` | `differs from the opinion text in 1 word(s): 'petitioners' → 'respondents'` | status `differs` |
| 52 | quote-not-inserted | seed Husain sentence with `not` inserted before `creates`, cite `540 U.S. 644` | us/540 + 0644-01 | `quote_not_found` | `differs from the opinion text in 1 word(s)` | meaning reversed; old rule verified it at 97 |
| 53 | quote-ellipsis | seed Saks sentence with the middle clause replaced by `. . .` | us/470 + 0392-01 | `verified` | `quoted passage found` | segments 2, status `verbatim` |
| 54 | quote-hyphenation | seed Twombly sentence with `plausi-\nble` and curly quotes | us/550 + 0544-01 | `verified` | `quoted passage found` | normalization |
| 55 | quote-generic | `"the district court erred in"` (short) attached to `516 U.S. 217` | us/516 + 0217-01 | `verified` | — | < 4 tokens after the 25-char attach rule fails → no quote attached; or if attached, `not_found` at ≈ 78 — pick one in `extract` tests |
| 56 | not-checked-timeout | any citation whose `CasesMetadata` fetch returns `Failed("timeout")` | fake client | `not_checked` | `did not answer for` | not counted in red/coverage registers |
| 57 | not-checked-html-200 | `Present` impossible: 200 with `<!doctype html>` body | fake client | `not_checked` | `unreadable reply` | §1.4 |
| 58 | absent-404-volume | `us/600/CasesMetadata.json` → 404 HTML | fake client | `not_in_free_corpus` | `U.S. volumes after 572` | 404 is an answer, not a failure |
| 59 | dup-volume-rows | a3d VolumesMetadata with volume `138` listed twice | + a3d/VolumesMetadata, a3d/138 | cases from both rows searched | — | assert `len(cases) == len(set(ids))` and both rows' cases present |
| 60 | run-limit | 61 distinct volumes in one text | fake client | 61st → `not_checked` | `run limit` | §1.6 item 5 |
| 61 | id-skipped | `Id. at 230.` | none | `skipped` | `short-form citation` | seed `skipped_expected` |
| 62 | statute-skipped | `28 U.S.C. § 1332` | none | `skipped` | `statute` | `FullLawCitation` |

Integration assertion (unchanged target, now reachable): seed 20 → ≥ 18 correct against `accepted_classes`; rows with `real_case_at_page.first_page == page` predicted `likely_fabricated` = 0; additionally rows 22–24, 27–30, 33–34, 42, 45–47 (real cases) are never `likely_fabricated`.
