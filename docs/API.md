# API — the HTTP contract of the citation memo (Clerkmark)

Status: the contract every other module builds against. Models live in `citememo/models.py` (pydantic v2; `__version__` in `citememo/__init__.py`). Front-end fixture: `web/static/fixture-memo.json` (a complete 23-row `Memo` for the seed sample, marked `"replay": true, "fixture": true`). Wording sources: DECISION-RULE §6.3 (`reasons[]`), UI-SPEC §9 (`label`). Nothing in a response is typed by hand: every name, page, date and URL is read from CAP files, every count from the run.

One FastAPI app in `main.py` (module-level `app`), JSON under `/api/*`, the page and its assets from `web/`. All JSON is UTF-8; en dashes and curly quotes appear inside opinion excerpts as CAP printed them.

## 0. Decisions that shape the contract

1. **Evidence is embedded, not fetched.** Each `CitationResult.evidence` carries `running_head`, `page_marker`, `excerpt` (about 200 characters of opinion text around the closest passage, or around the case's start), `excerpt_highlight` and `links[]` (the CAP URLs used). The front end therefore needs **no `GET /api/evidence/{row}`**. This deviates from UI-SPEC §6 C-04, which planned that endpoint with `{running_head, page_marker, text, highlight, urls[]}`: the same five values are now `evidence.running_head`, `evidence.page_marker`, `evidence.excerpt`, `evidence.excerpt_highlight`, `evidence.links`. C-04's "loading" state (skeleton lines while the fetch is in flight) does not occur; its "metadata-only" state occurs when `evidence.excerpt` is `null` (the case text is not cached and could not be fetched in time; the row still has `real_case_at_page`). C-04's shelf variant reads `evidence.volume_range` (`vmin`, `vmax`, `held`, `cited`, `note`) or `evidence.real_case_at_page` (`first_page`, `last_page`) as before.
2. **`class` is the JSON key**, `class_` the Python attribute (alias). Serialise with `model_dump(by_alias=True)`; input accepts both.
3. **Derived display fields are sent**, so the UI never re-derives the rule: `label` (UI-SPEC §9 words), `mark` (which pen mark), `register` (DECISION-RULE §0), `drawer` (`"page"`, `"shelf"` or `null` = no bracket link).
4. **`links` live in `evidence.links`** (DECISION-RULE §0 lists `links` at the row's top level; the models put it inside `evidence` with the rest of what the drawer prints). `quote_check`, `pincite_unverified` and `parallel_cites` stay at the row's top level as DECISION-RULE says.
5. **Eight classes.** The seven of BUILD-NOTES plus `not_checked` (DECISION-RULE §6.1: timeouts, server errors, run limit). `not_checked` is never counted in the red or coverage registers; the tally sentence prints it as "{n} not answered yet."
6. **Rows are in filing order**, 1-based, one row per citation group (parallel cites collapse into one row, DECISION-RULE step 10). Skipped cites (Id., supra, statutes) are rows too, so the UI can list them; they count in `counts.skipped` and `counts.total`.
7. **Every timing is measured** (`elapsed_ms`, `stage_timings_ms`, per-row `timings_ms`). A fixture or replay says so in `notes[]` and via `replay`/`fixture`.

## 1. Routes

| Method | Path | Request | Response | Notes |
|---|---|---|---|---|
| GET | `/` | — | `web/index.html` (FileResponse) | Query params (`?demo=1`, `?state=…`, `?reset=1`) and the hash reach the page unchanged. |
| GET | `/static/*` | — | files under `web/static/` | `app.css`, `app.js`, `fixture-memo.json`, `fixtures/*.json`, `favicon.svg`, fonts if self-hosted. Immutable caching is fine; the fixture changes only with a deploy. |
| GET | `/api/health` | — | `Health` | `{"ok": true, "version": "0.1.0", "offline": false, "courtlistener": false, "advisory": false, "replay_available": true, "cache_dir": "seed/cache"}`. `offline` mirrors `CITEMEMO_OFFLINE=1`; `courtlistener` = token configured; `advisory` = `ANTHROPIC_API_KEY` set. |
| GET | `/api/samples` | — | `list[SampleInfo]` | The seeded samples. v1 has one: `id: "sample-motion"`. |
| POST | `/api/memo` | multipart `file` (PDF, ≤ 15 MB) **or** form field `text` | `Memo` | Live run. 60 s budget on Vercel (`maxDuration`). `filing.filename` is the upload's name (or `"pasted-text"`); `filing.label` is `null` for uploads. |
| POST | `/api/memo/sample/{id}` | — | `Memo` | Runs the seeded sample live, with CAP calls served from `seed/cache` when present. When `CITEMEMO_OFFLINE=1`, or when the network fails for a cached file, the cache answers and `memo.offline = true`. Unknown id → 404 `not_found`. `memo.sample_id = id`. |
| GET | `/api/replay` | — | `Memo` | The recorded run `seed/replay.json` (`replay: true`; `created_at` is the recording time). 404 `not_found` with hint "Run scripts/record_replay.py." when the file is missing. |
| GET | `/api/eval` | optional `?rerun=1` | `EvalReport` | Runs the seed sample through the pipeline (from cache when offline), compares each of the 20 scored items of `seed/ground_truth.json` with its `accepted_classes`, and reports accuracy, the count of real cases predicted `likely_fabricated`, per-class counts and timings. Matches memo rows to items by `cite_text`. The page-1 Mata label citation and skipped rows are not scored. Implementations may serve the last run's report and set `run_created_at`; `?rerun=1` forces a fresh run. |

Content types: requests `multipart/form-data` (file) or `application/x-www-form-urlencoded` (`text`); every response `application/json; charset=utf-8` except `/` and `/static/*`.

CORS: not needed (same origin). The page never calls CAP or CourtListener directly.

### 1.1 Errors

Every non-2xx JSON body is an `ErrorEnvelope`:

```json
{"error": {"code": "no_text_layer", "message": "No text layer in this PDF. It looks like a scan; this prototype does not run OCR.", "hint": "Try a PDF saved from a word processor, or the sample filing."}}
```

| HTTP | `code` | When | `message` (UI-SPEC §9 wording) |
|---|---|---|---|
| 422 | `no_text_layer` | pdfplumber returns no text (or < 40 characters) for every page | "No text layer in this PDF. It looks like a scan; this prototype does not run OCR." hint: "Try a PDF saved from a word processor, or the sample filing." |
| 413 | `too_large` | upload > 15 MB (the UI blocks at 20 MB client-side; the server's limit is the smaller one and the message names it) | "This PDF is larger than 15 MB. This prototype reads files up to 15 MB." |
| 415 | `unsupported_type` | not `application/pdf` (sniffed: `%PDF-` magic), and no `text` field | "This file is not a PDF." hint: "Choose a PDF saved from a word processor, or use the sample filing." |
| 504 | `upstream_timeout` | the whole run exceeded its budget before any row was classified (per-row timeouts become `not_checked` rows, never an error) | "The free library did not answer in time." hint: "Run again; large filings take longer." |
| 400 | `empty` | no `file` and no `text`, or `text` is blank | "Nothing to check: send a PDF as `file` or text as `text`." |
| 404 | `not_found` | unknown sample id; `/api/replay` without a recording | "No sample called '{id}'." / "No replay recorded yet." hint: "Run scripts/record_replay.py." |
| 500 | `internal` | anything else (logged with the run id) | "The server could not read this PDF ({reason})." |

A run with zero citations is **not** an error: `POST /api/memo` returns 200 with `results: []`, `counts.total: 0` and `read_these_first: "Nothing to read first: 0 found. Of 0 citations."`; the UI renders its no-results paragraph from `filing.pages`.

## 2. Models

Field lists below are generated from `citememo/models.py`; that file wins if they differ. `Optional[X]` = `X | null`.

### CitationInput — one citation as extracted
| Field | Type | Notes |
|---|---|---|
| `text` | `str` | required. The matched text of the core cite, e.g. '925 F.3d 1339'. |
| `span` | `Optional[tuple[int, int]]` | default `None`. [start, end) character offsets in the cleaned filing text. |
| `filing_page` | `Optional[int]` | default `None`. 1-based PDF page the span starts on. |
| `volume` | `Optional[int]` | default `None`.  |
| `reporter` | `Optional[str]` | default `None`. Canonical reporter string (eyecite edition_guess.short_name), e.g. 'F. Supp. 2d'; the raw string for unrecognized reporters. |
| `page` | `Optional[int]` | default `None`.  |
| `pin_cite` | `Optional[str]` | default `None`. e.g. 'at 230' or '1340-41'; note only, never verified. |
| `year` | `Optional[int]` | default `None`. Year from the parenthetical regex, falling back to eyecite metadata.year. |
| `court` | `Optional[str]` | default `None`. eyecite court id ('scotus', 'ca2') or the parenthetical's court text. |
| `plaintiff` | `Optional[str]` | default `None`.  |
| `defendant` | `Optional[str]` | default `None`.  |
| `quotes` | `list[str]` | default: computed. Quoted passages (>= 25 chars) attached to this citation. |
| `kind` | `Literal['full', 'id', 'supra', 'short', 'statute', 'unrecognized']` | default `'full'`.  |

### RealCase — a CAP case record (`evidence.real_case_at_page`, `other_entries[]`)
| Field | Type | Notes |
|---|---|---|
| `name` | `str` | required. CAP name_abbreviation, e.g. 'J.D. v. Azar'. |
| `first_page` | `int` | required.  |
| `last_page` | `int` | required.  |
| `decision_date` | `str` | required. ISO date as CAP gives it, e.g. '2019-06-14'. |
| `court` | `str` | required. CAP court.name, e.g. 'Court of Appeals of the District of Columbia'. |
| `court_abbreviation` | `Optional[str]` | default `None`. CAP court.name_abbreviation, e.g. 'D.C. Cir.'. |
| `cite` | `str` | required. Official cite, e.g. '925 F.3d 1291'. |
| `file_name` | `Optional[str]` | default `None`. CAP case file stem, e.g. '1291-01'. |
| `id` | `Optional[int]` | default `None`. CAP case id. |
| `parallel_cites` | `list[str]` | default: computed. Other cites the CAP record lists. |

`NameHit` = `RealCase` + `score: float` (0–100), `match: "full"|"partial"|"none"`, `court_consistent: bool|null`.

### VolumeRange — the shelf
| Field | Type | Notes |
|---|---|---|
| `reporter` | `str` | required.  |
| `vmin` | `int` | required. Lowest volume number CAP lists. |
| `vmax` | `int` | required. Highest volume number CAP lists. |
| `held` | `bool` | required. True when the cited volume is present in CAP. |
| `cited` | `Optional[int]` | default `None`. The cited volume. |
| `cap_end_year` | `Optional[int]` | default `None`. Last year CAP covers for this reporter. |
| `max_last_page` | `Optional[int]` | default `None`. Last page of the last case CAP holds in the cited volume. |
| `note` | `Optional[str]` | default `None`. Shelf label, e.g. 'U.S. Reports · volumes 1–572 in the free library · cited: 600'. |

### ClosestPassage
| Field | Type | Notes |
|---|---|---|
| `text` | `str` | required. Raw opinion text around the aligned window (about ±200 chars). |
| `similarity` | `float` | required. rapidfuzz partial_ratio (min over segments), 0-100. |
| `diff_tokens` | `list[DiffToken]` | default: computed.  |
| `status` | `Literal['verbatim', 'differs', 'not_found', 'not_checked']` | default `'not_checked'`.  |
| `highlight` | `Optional[tuple[int, int]]` | default `None`. [start, end) offsets inside `text` of the opinion's passage. |

`DiffToken` = `{"filed": str, "opinion": str}`. `EditionRange` = `{"reporter", "start", "end", "note"}`. `YearMismatch` = `{"cited": int, "decided": str}`.

### Evidence (all optional; extra keys allowed for diagnostics)
| Field | Type | Notes |
|---|---|---|
| `real_case_at_page` | `Optional[RealCase]` | default `None`. The case that begins at, or spans, the cited page. |
| `name_hit` | `Optional[NameHit]` | default `None`. Step-7 name search result, when one was found. |
| `other_entries` | `list[RealCase]` | default: computed. Other CAP entries for the same case (orders pages, duplicates). |
| `volume_range` | `Optional[VolumeRange]` | default `None`.  |
| `edition_range` | `Optional[EditionRange]` | default `None`.  |
| `closest_passage` | `Optional[ClosestPassage]` | default `None`.  |
| `running_head` | `Optional[str]` | default `None`. Reporter running head for the drawer, e.g. '925 F.3d 1291 · J.D. v. AZAR · D.C. Cir. · June 14, 2019'. |
| `page_marker` | `Optional[str]` | default `None`. The cited page as the drawer prints it at the right, e.g. '1339'. |
| `excerpt` | `Optional[str]` | default `None`. About 200 chars of opinion text around the closest passage (quote rows) or the case's start (other rows). None when the case text is not in the cache and could not be fetched. |
| `excerpt_highlight` | `Optional[tuple[int, int]]` | default `None`. [start, end) inside `excerpt` to underline. |
| `links` | `list[str]` | default: computed. CAP static URLs used for this row, in fetch order. |
| `cite_type` | `Optional[str]` | default `None`. reporters_db cite_type for step-2 rows ('specialty_west', 'neutral'). |
| `matched_text` | `Optional[str]` | default `None`. The regex match for unrecognized_reporter rows. |
| `searched_names` | `list[str]` | default: computed. Party names searched across the volume in step 7. |
| `nearest_caption` | `Optional[NameHit]` | default `None`. Best-scoring caption when no hit carried a match. |
| `year_mismatch` | `Optional[YearMismatch]` | default `None`.  |
| `plausibility` | `Optional[str]` | default `None`. DECISION-RULE §3.2 note for volumes beyond coverage. |
| `parallel_mismatch` | `Optional[str]` | default `None`.  |

### QuoteCheck
| Field | Type | Notes |
|---|---|---|
| `status` | `Literal['verbatim', 'differs', 'not_found', 'not_checked']` | required.  |
| `quote` | `Optional[str]` | default `None`. The quoted passage as filed. |
| `similarity` | `Optional[float]` | default `None`.  |
| `segments` | `int` | default `1`. Ellipsis-separated segments compared. |
| `diff` | `list[DiffToken]` | default: computed.  |

### Advisory
| Field | Type | Notes |
|---|---|---|
| `verdict` | `Literal['supports', 'does_not_support', 'cannot_tell']` | required.  |
| `why` | `str` | required.  |
| `model` | `str` | required.  |

### CitationResult — one memo row
| Field | Type | Notes |
|---|---|---|
| `row` | `int` | required. 1-based line number in filing order; the UI's `#line-{row}`. |
| `cite_text` | `str` | required. The citation as printed on the memo, e.g. 'Varghese v. China Southern Airlines Co., 925 F.3d 1339 (11th Cir. 2019)'. |
| `class` | `Literal['verified', 'quote_not_found', 'wrong_cite_exists', 'not_in_free_corpus', 'unrecognized_reporter', 'likely_fabricated', 'not_checked', 'skipped']` | required.  |
| `label` | `str` | default `''`. UI-SPEC §9 label; filled from the class when empty. |
| `reasons` | `list[str]` | default: computed. Plain sentences; reasons[0] is printed under the row. |
| `evidence` | `Evidence` | default: computed.  |
| `source` | `Literal['CAP', 'CourtListener', 'none']` | default `'none'`.  |
| `pincite_unverified` | `bool` | default `False`.  |
| `quote_check` | `Optional[QuoteCheck]` | default `None`.  |
| `parallel_cites` | `list[str]` | default: computed. e.g. '116 S. Ct. 629 — confirmed by the CAP record'. |
| `advisory` | `Optional[Advisory]` | default `None`.  |
| `timings_ms` | `dict[str, float]` | default: computed. Per-row stage timings, e.g. {'lookup': 12.4, 'quotes': 2.1}. |
| `citation` | `Optional[CitationInput]` | default `None`. The extracted input (span, filing page, parties, quotes). |
| `mark` | `Literal['circle-all', 'circle-reporter', 'strike-correct', 'underline-quote', 'underline-pencil', 'check', 'none']` | default `'none'`. Derived from the class unless given. |
| `register` | `Literal['green', 'amber', 'coverage', 'unknown_reporter', 'red', 'grey']` | default `'grey'`. Derived from the class unless given (DECISION-RULE §0 register). |
| `drawer` | `Optional[Literal['page', 'shelf']]` | default `None`. Which evidence drawer the row's link opens; None = no link. |

Derivations (done by the model when the field is omitted): `label` from `class` via `label_for()` (verified + quote → "Found. Quote matches."; + pin cite → "… Pin page not checked."; skipped statute → "Not checked (statute)."); `mark` and `register` from the tables `MARKS`/`REGISTERS`; `drawer` = `"page"` when `evidence.real_case_at_page` or `name_hit` is set, `"shelf"` when only `volume_range` is set, `null` otherwise and always for `skipped`, `not_checked`, `unrecognized_reporter`.

| class | label (UI-SPEC §9) | mark | register | drawer |
|---|---|---|---|---|
| `verified` | Found. | `check` | `green` | page |
| `quote_not_found` | Found, but this quote is not in the opinion. | `underline-quote` | `amber` | page |
| `wrong_cite_exists` | Exists, but not at this page. | `strike-correct` | `amber` | page |
| `not_in_free_corpus` | Not in the free library. Check Westlaw or Lexis. | `underline-pencil` | `coverage` | shelf or null |
| `unrecognized_reporter` | No reporter by this name. | `circle-reporter` | `unknown_reporter` | null |
| `likely_fabricated` | Likely not a real case. | `circle-all` | `red` | page |
| `not_checked` | Could not reach the free library. | `none` | `coverage` | null |
| `skipped` | Not checked (Id., supra or short form). | `none` | `grey` | null |

### Counts
`{"verified", "quote_not_found", "wrong_cite_exists", "not_in_free_corpus", "unrecognized_reporter", "likely_fabricated", "not_checked", "skipped": int, "total": int}` — computed from `results` when omitted.

### Memo — the response of every memo route
| Field | Type | Notes |
|---|---|---|
| `run_id` | `str` | required.  |
| `created_at` | `str` | default: computed. ISO 8601 with offset; the stamp's date and time. |
| `app_version` | `str` | default `'0.1.0'`.  |
| `filing` | `Filing` | required.  |
| `sources_used` | `SourcesUsed` | default: computed.  |
| `results` | `list[CitationResult]` | default: computed.  |
| `counts` | `Counts` | default: computed. Filled from results when omitted. |
| `read_these_first` | `str` | default `''`. UI-SPEC §9 tally sentence; filled from counts when empty. |
| `elapsed_ms` | `float` | default `0.0`.  |
| `stage_timings_ms` | `StageTimings` | default: computed.  |
| `offline` | `bool` | default `False`. True when answers came from the on-disk CAP cache only. |
| `replay` | `bool` | default `False`. True for seed/replay.json and for the front-end fixture. |
| `fixture` | `bool` | default `False`. True only for web/static/fixture-memo.json (hand-built from the seed, not a recorded run). |
| `sample_id` | `Optional[str]` | default `None`.  |
| `warnings` | `list[str]` | default: computed. Run-level notices, e.g. 'CourtListener throttled this run; the Caselaw Access Project answered for every row shown.' |
| `notes` | `list[str]` | default: computed. Provenance notes (where a fixture's numbers came from). |

`read_these_first` (UI-SPEC §9, built by `read_these_first_sentence(counts)`): "Read these first: {k} likely not real cases, {u} no reporter by this name, {q} quotes not in the opinion, {w} exists at another page. Then: {f} found; {c} not in the free library; {s} not checked. Of {n} citations." Zero counts are omitted ("{f} found" always stays); singulars are handled ("1 likely not real case", "1 quote not in the opinion"); when every flagged count is zero the sentence starts "Nothing to read first:"; when `counts.not_checked > 0` it ends with " {u} not answered yet." The UI links each count to that class's first row.

Stamp and heading mapping: `created_at` → the stamp's date/time and the DATE line (UI-SPEC calls it `checked_at`); `counts.total` → "{n} citations"; `elapsed_ms / 1000` → "in {elapsed} s"; `sources_used` → the stamp's source line and "CHECKED AGAINST:" (`courtlistener: false` → "CourtListener: not configured"); `stage_timings_ms` → the status line's four "●" values (`extract` = "Reading the PDF" + "Finding citations" combined, `lookup` = "Looking up the free library", `quotes` = "Matching quotes"; `classify` is added to `lookup` for display); `filing.label` or `filing.filename` + `filing.pages` → RE:. Browser title uses `counts.total` and `counts.likely_fabricated`.

### SampleInfo
| Field | Type | Notes |
|---|---|---|
| `id` | `str` | required. Route key: POST /api/memo/sample/{id}. |
| `title` | `str` | required.  |
| `label` | `str` | required. The synthetic label printed on the content and typed into RE:. |
| `filename` | `str` | required.  |
| `pages` | `int` | required.  |
| `words` | `Optional[int]` | default `None`.  |
| `citations` | `int` | required. Rows the memo will show (scored + label + skipped). |
| `scored` | `int` | required. Rows with a ground-truth class (20 for the seed). |
| `synthetic` | `bool` | default `True`.  |
| `cached` | `bool` | default `True`. Every CAP file the sample needs is in seed/cache, so it runs offline. |

### EvalRow / EvalReport
| Field | Type | Notes |
|---|---|---|
| `id` | `str` | required. ground_truth item id, e.g. 'mata-varghese'. |
| `line` | `Optional[int]` | default `None`. Memo row this item matched (by cite_text), or None if the memo lacked it. |
| `cite_text` | `str` | required.  |
| `expected` | `Literal['verified', 'quote_not_found', 'wrong_cite_exists', 'not_in_free_corpus', 'unrecognized_reporter', 'likely_fabricated', 'not_checked', 'skipped']` | required.  |
| `accepted` | `list[Literal['verified', 'quote_not_found', 'wrong_cite_exists', 'not_in_free_corpus', 'unrecognized_reporter', 'likely_fabricated', 'not_checked', 'skipped']]` | required.  |
| `predicted` | `Optional[Literal['verified', 'quote_not_found', 'wrong_cite_exists', 'not_in_free_corpus', 'unrecognized_reporter', 'likely_fabricated', 'not_checked', 'skipped']]` | default `None`.  |
| `ok` | `bool` | default `False`.  |
| `reason` | `Optional[str]` | default `None`. The memo's reasons[0] for this row. |
| `real_case` | `bool` | default `False`. True when ground truth has a real case beginning at the cited page. |

| Field | Type | Notes |
|---|---|---|
| `rows` | `list[EvalRow]` | required.  |
| `correct` | `int` | required.  |
| `total` | `int` | required.  |
| `accuracy` | `float` | required. correct / total. |
| `real_cases_marked_fabricated` | `int` | required. Real cases (real_case=True) predicted likely_fabricated. Target 0. |
| `real_total` | `int` | required. How many rows are real cases. |
| `per_class` | `dict[str, dict[str, int]]` | default: computed. {'expected': {class: n}, 'predicted': {class: n}}. |
| `elapsed_ms` | `float` | required.  |
| `stage_timings_ms` | `StageTimings` | default: computed.  |
| `generated_at` | `str` | default: computed.  |
| `run_id` | `Optional[str]` | default `None`.  |
| `run_created_at` | `Optional[str]` | default `None`.  |
| `offline` | `bool` | default `False`.  |
| `replay` | `bool` | default `False`.  |

`accuracy` is a fraction (0–1); the UI prints `correct` "of" `total`. `real_cases_marked_fabricated` must be 0 for the seed. `per_class` = `{"expected": {class: n}, "predicted": {class: n}}` over the scored rows only.

### Health / ErrorEnvelope
| Field | Type | Notes |
|---|---|---|
| `ok` | `bool` | default `True`.  |
| `version` | `str` | default `'0.1.0'`.  |
| `offline` | `bool` | default `False`.  |
| `courtlistener` | `bool` | default `False`.  |
| `advisory` | `bool` | default `False`.  |
| `replay_available` | `bool` | default `False`.  |
| `cache_dir` | `Optional[str]` | default `None`.  |

`ErrorEnvelope` = `{"error": {"code": ErrorCode, "message": str, "hint": str|null}}`, codes: `no_text_layer`, `too_large`, `unsupported_type`, `upstream_timeout`, `empty`, `not_found`, `internal`.

## 3. Example: `POST /api/memo/sample/sample-motion` → Memo (three rows)

Three rows lifted from `web/static/fixture-memo.json` (there rows 21, 8 and 10), renumbered 1–3: a verified row with a verbatim quote (J.D. v. Azar), the Miller/Greenleaf `likely_fabricated` row, and a Westlaw-only `not_in_free_corpus` row. Names, pages, dates, ids, cites, excerpts and URLs are the values in `seed/ground_truth.json` and `seed/cache/cap/**`; `elapsed_ms` and `stage_timings_ms` are the fixture's measured numbers.

```json
{
  "run_id": "7f3c2a9e-5d1b-4e0a-9c6f-2b8d1e4a7c10",
  "created_at": "2026-09-26T14:37:51+00:00",
  "app_version": "0.1.0",
  "filing": {
    "filename": "sample-motion.pdf",
    "pages": 6,
    "words": 1933,
    "label": "Synthetic sample filing — Memorandum in Opposition to Motion to Dismiss. Not a real court document; modeled on the fabricated citations described in Mata v. Avianca, Inc., 678 F. Supp. 3d 443 (S.D.N.Y. 2023). Party names are fictional.",
    "bytes": 10175
  },
  "sources_used": {
    "cap": true,
    "courtlistener": false,
    "advisory": false
  },
  "results": [
    {
      "row": 1,
      "cite_text": "J.D. v. Azar, 925 F.3d 1291 (D.C. Cir. 2019)",
      "class": "verified",
      "label": "Found. Quote matches.",
      "reasons": [
        "Found in the free corpus: J.D. v. Azar, 925 F.3d 1291 (Court of Appeals of the District of Columbia, 2019-06-14).",
        "Quoted passage found in the opinion text."
      ],
      "evidence": {
        "real_case_at_page": {
          "name": "J.D. v. Azar",
          "first_page": 1291,
          "last_page": 1349,
          "decision_date": "2019-06-14",
          "court": "Court of Appeals of the District of Columbia",
          "court_abbreviation": "D.C. Cir.",
          "cite": "925 F.3d 1291",
          "file_name": "1291-01",
          "id": 12521273,
          "parallel_cites": []
        },
        "name_hit": null,
        "other_entries": [],
        "volume_range": {
          "reporter": "F.3d",
          "vmin": 1,
          "vmax": 935,
          "held": true,
          "cited": 925,
          "cap_end_year": 2019,
          "max_last_page": 1384,
          "note": "Federal Reporter, 3d Series · volumes 1–935 in the free library · cited: 925"
        },
        "edition_range": null,
        "closest_passage": {
          "text": "epends on whether the claim is potentially fleeting, we must determine what qualifies as too brief. Once the district court deems a Rule 23 class valid, the subsequent mootness of individual claims does not terminate litigation. See Sosna , 419 U.S. at 399, 402, 95 S.Ct. 553 ; see also Genesis Healthcare , 569 U.S. at 75, 133 ",
          "similarity": 100.0,
          "diff_tokens": [],
          "status": "verbatim",
          "highlight": [
            100,
            228
          ]
        },
        "running_head": "925 F.3d 1291 · J.D. v. AZAR · D.C. Cir. · June 14, 2019",
        "page_marker": "1291",
        "excerpt": "epends on whether the claim is potentially fleeting, we must determine what qualifies as too brief. Once the district court deems a Rule 23 class valid, the subsequent mootness of individual claims does not terminate litigation. See Sosna , 419 U.S. at 399, 402, 95 S.Ct. 553 ; see also Genesis Healthcare , 569 U.S. at 75, 133 ",
        "excerpt_highlight": [
          100,
          228
        ],
        "links": [
          "https://static.case.law/f3d/VolumesMetadata.json",
          "https://static.case.law/f3d/925/CasesMetadata.json",
          "https://static.case.law/f3d/925/cases/1291-01.json"
        ],
        "cite_type": null,
        "matched_text": null,
        "searched_names": [],
        "nearest_caption": null,
        "year_mismatch": null,
        "plausibility": null,
        "parallel_mismatch": null
      },
      "source": "CAP",
      "pincite_unverified": false,
      "quote_check": {
        "status": "verbatim",
        "quote": "Once the district court deems a Rule 23 class valid, the subsequent mootness of individual claims does not terminate litigation.",
        "similarity": 100.0,
        "segments": 1,
        "diff": []
      },
      "parallel_cites": [],
      "advisory": null,
      "timings_ms": {},
      "citation": {
        "text": "925 F.3d 1291",
        "span": [
          10174,
          10187
        ],
        "filing_page": 5,
        "volume": 925,
        "reporter": "F.3d",
        "page": 1291,
        "pin_cite": null,
        "year": 2019,
        "court": "D.C. Cir.",
        "plaintiff": "J.D.",
        "defendant": "Azar",
        "quotes": [
          "Once the district court deems a Rule 23 class valid, the subsequent mootness of individual claims does not terminate litigation."
        ],
        "kind": "full"
      },
      "mark": "check",
      "register": "green",
      "drawer": "page"
    },
    {
      "row": 2,
      "cite_text": "Miller v. United Airlines, Inc., 174 F.3d 366 (2d Cir. 1999)",
      "class": "likely_fabricated",
      "label": "Likely not a real case.",
      "reasons": [
        "Page 366 of 174 F.3d belongs to Greenleaf v. Garlock, Inc. (352–368). No case in volume 174 F.3d is named Miller v. United Airlines, Inc.; the nearest caption, Miller v. City of Philadelphia (3d Cir., 174 F.3d 368), fails the filing's court (2d Cir.) and its second party. Verify before relying on this.",
        "Nearest caption in the volume: Miller v. City of Philadelphia, 174 F.3d 368 (best name score 100.0 of 100; a match needs 80 on both parties)."
      ],
      "evidence": {
        "real_case_at_page": {
          "name": "Greenleaf v. Garlock, Inc.",
          "first_page": 352,
          "last_page": 368,
          "decision_date": "1999-04-26",
          "court": "United States Court of Appeals for the Third Circuit",
          "court_abbreviation": "3d Cir.",
          "cite": "174 F.3d 352",
          "file_name": "0352-01",
          "id": 11620144,
          "parallel_cites": []
        },
        "name_hit": null,
        "other_entries": [],
        "volume_range": {
          "reporter": "F.3d",
          "vmin": 1,
          "vmax": 935,
          "held": true,
          "cited": 174,
          "cap_end_year": 2019,
          "max_last_page": 1382,
          "note": "Federal Reporter, 3d Series · volumes 1–935 in the free library · cited: 174"
        },
        "edition_range": null,
        "closest_passage": null,
        "running_head": "174 F.3d 352 · GREENLEAF v. GARLOCK, INC. · 3d Cir. · April 26, 1999 · begins at 352",
        "page_marker": "366",
        "excerpt": "OPINION OF THE COURT\nSTAPLETON, Circuit Judge:\nGarlock, Inc. (“Garlock”) and Owens Corning Fiberglas Corp. (“Owens”) appeal the District Court’s orders denying their motions to alter or amend a ’judgment holding them liable- for Charles Greenleaf, Jr.’s injuri",
        "excerpt_highlight": null,
        "links": [
          "https://static.case.law/f3d/VolumesMetadata.json",
          "https://static.case.law/f3d/174/CasesMetadata.json"
        ],
        "cite_type": null,
        "matched_text": null,
        "searched_names": [
          "Miller",
          "United Airlines, Inc."
        ],
        "nearest_caption": {
          "name": "Miller v. City of Philadelphia",
          "first_page": 368,
          "last_page": 391,
          "decision_date": "1999-04-26",
          "court": "United States Court of Appeals for the Third Circuit",
          "court_abbreviation": "3d Cir.",
          "cite": "174 F.3d 368",
          "file_name": "0368-01",
          "id": 11620269,
          "parallel_cites": [],
          "score": 100.0,
          "match": "partial",
          "court_consistent": false
        },
        "year_mismatch": null,
        "plausibility": null,
        "parallel_mismatch": null
      },
      "source": "CAP",
      "pincite_unverified": false,
      "quote_check": null,
      "parallel_cites": [],
      "advisory": null,
      "timings_ms": {},
      "citation": {
        "text": "174 F.3d 366",
        "span": [
          4915,
          4927
        ],
        "filing_page": 3,
        "volume": 174,
        "reporter": "F.3d",
        "page": 366,
        "pin_cite": null,
        "year": 1999,
        "court": "2d Cir.",
        "plaintiff": "Miller",
        "defendant": "United Airlines, Inc.",
        "quotes": [],
        "kind": "full"
      },
      "mark": "circle-all",
      "register": "red",
      "drawer": "page"
    },
    {
      "row": 3,
      "cite_text": "Martinez v. Delta Air Lines, Inc., 2019 WL 4639462 (Tex. App. 2019)",
      "class": "not_in_free_corpus",
      "label": "Not in the free library. Check Westlaw or Lexis.",
      "reasons": [
        "Proprietary citation (Westlaw/Lexis); not checkable in a free corpus.",
        "Westlaw-only citation; no free text exists. Check Westlaw or Lexis for the case."
      ],
      "evidence": {
        "real_case_at_page": null,
        "name_hit": null,
        "other_entries": [],
        "volume_range": null,
        "edition_range": null,
        "closest_passage": null,
        "running_head": null,
        "page_marker": null,
        "excerpt": null,
        "excerpt_highlight": null,
        "links": [],
        "cite_type": "specialty_west",
        "matched_text": null,
        "searched_names": [],
        "nearest_caption": null,
        "year_mismatch": null,
        "plausibility": null,
        "parallel_mismatch": null
      },
      "source": "none",
      "pincite_unverified": false,
      "quote_check": null,
      "parallel_cites": [],
      "advisory": null,
      "timings_ms": {},
      "citation": {
        "text": "2019 WL 4639462",
        "span": [
          5272,
          5287
        ],
        "filing_page": 3,
        "volume": 2019,
        "reporter": "WL",
        "page": 4639462,
        "pin_cite": null,
        "year": 2019,
        "court": "Tex. App.",
        "plaintiff": "Martinez",
        "defendant": "Delta Air Lines, Inc.",
        "quotes": [],
        "kind": "full"
      },
      "mark": "underline-pencil",
      "register": "coverage",
      "drawer": null
    }
  ],
  "counts": {
    "verified": 1,
    "quote_not_found": 0,
    "wrong_cite_exists": 0,
    "not_in_free_corpus": 1,
    "unrecognized_reporter": 0,
    "likely_fabricated": 1,
    "not_checked": 0,
    "skipped": 0,
    "total": 3
  },
  "read_these_first": "Read these first: 1 likely not real case. Then: 1 found; 1 not in the free library. Of 3 citations.",
  "elapsed_ms": 2323.2,
  "stage_timings_ms": {
    "extract": 1241.6,
    "lookup": 672.4,
    "classify": 333.1,
    "quotes": 76.0,
    "advisory": null
  },
  "offline": false,
  "replay": false,
  "fixture": false,
  "sample_id": "sample-motion",
  "warnings": [],
  "notes": [
    "Example for docs/API.md: three rows lifted from web/static/fixture-memo.json (rows 21, 8 and 10 there), renumbered 1-3; counts and the tally sentence are recomputed for these three rows."
  ]
}
```

## 4. Fixture and states for the front end

- `GET /static/fixture-memo.json` — the full 23-row sample memo (`replay: true, fixture: true, offline: true`). Row order is filing order: 1 Mata label cite (not in free corpus, shelf), 2 statute (skipped), 3–5 found with quotes, 6–8 likely not real, 9–11 not in the free library (neutral cite, two WL), 12–13 found, 14 Id. (skipped), 15 wrong page (Zicherman 230 → 217), 16 quote differs (Chan, 3 words), 17 found, 18 quote not found (Iqbal, 90.5%), 19 found, 20 no reporter by this name (Fed. Air Rptr. 3d), 21 found (Azar), 22–23 beyond coverage (Loper Bright, Biden; shelf 1–572, cited 603/600). `#line-6` opens the page whose running head reads J.D. v. AZAR; `#line-23` opens the shelf. Row 7 (Petersen) has `excerpt: null` and shows the metadata-only drawer state.
- `?state=` fixtures (`web/static/fixtures/*.json`) are the front-end agent's; they should be `Memo` or `ErrorEnvelope` bodies so the same renderer draws them. Suggested: `loading` (no body; the UI shows the status line), `partial` (the fixture memo with rows 22–23 changed to `class: "not_checked"`, `reasons[0]: "Could not be checked: the free corpus did not answer for 603 U.S. (timeout). Run again or check by hand."`), `error` (`ErrorEnvelope` `no_text_layer`), `no-results` (`results: []`, `filing.pages: 3`).

## 5. Environment (all optional)

`COURTLISTENER_TOKEN` (adds CourtListener as a source for volumes beyond CAP), `ANTHROPIC_API_KEY` (advisory rows), `CITEMEMO_OFFLINE=1` (cache only; `memo.offline = true`; the UI banner reads "Offline · answers come from the cached free-library files of {date}"), `CITEMEMO_CACHE_DIR` (writable cache; default `seed/cache` when writable, else `/tmp/citememo-cache`).
