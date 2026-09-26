/* Clerkmark — the memo page. Plain JS, no build step.
   Every string below comes from docs/UI-SPEC.md §9 (upload limit revised to 4 MB per the contract).
   Every number on screen is read from the memo JSON, /api/eval or the run's own timer.
   Nothing is rendered with innerHTML: text goes through textContent / createTextNode. */
(() => {
  'use strict';

  // ---------------------------------------------------------------- copy deck (§9)
  const SAMPLE_ID = 'sample-motion';
  const UPLOAD_LIMIT_MB = 4;
  const UPLOAD_LIMIT_BYTES = UPLOAD_LIMIT_MB * 1024 * 1024;
  const REQUEST_TIMEOUT_MS = 60000;
  const SLOW_AFTER_MS = 10000;

  const COPY = {
    titleFirst: 'Clerkmark · citation memo',
    titleLoading: (f) => `Reading ${f} · Clerkmark`,
    titleMemo: (n, k) => `Memo · ${n} citations · ${k === 0 ? 'none likely not real' : `${k} likely not real`} · Clerkmark`,
    titleError: (r) => `Error: ${r} · Clerkmark`,
    memoH1: 'MEMORANDUM',
    kTo: 'TO:', vTo: 'Intake desk',
    kFrom: 'FROM:', vFrom: 'Clerkmark, citation check',
    kRe: 'RE:', kDate: 'DATE:', kAgainst: 'CHECKED AGAINST:',
    blank: '________',
    againstCap: 'Caselaw Access Project (free files)',
    againstNoCl: 'Caselaw Access Project (free files). CourtListener: not configured.',
    againstCl: 'Caselaw Access Project (free files); CourtListener',
    disclaimer: 'Triage aid. Not a finding. Verify flagged rows before relying on them.',
    litigant: 'This memo checks whether the cases cited in a document exist in a free law library and whether quoted words appear in them. It does not judge the argument.',
    stampChecked: 'CHECKED', stampReplay: 'REPLAY',
    stampRunOf: (d) => `run of ${d}`,
    stampCount: (n, s) => `${n} citations in ${s} s`,
    stampUnanswered: (u) => ` · ${u} unanswered`,
    stampSourceCap: 'Caselaw Access Project', stampSourceCl: ' · CourtListener', stampCache: ' (cache)',
    stampAria: (d, n, s, src) => `Checked ${d}, ${n} citations in ${s} seconds, sources ${src}`,
    stampAriaReplay: (d, n, s, src) => `Replay of the run of ${d}, ${n} citations in ${s} seconds, sources ${src}`,
    btnChoose: 'Choose a PDF', btnDropOwn: 'Drop your own PDF', btnSample: 'Use the sample filing',
    dropLead: 'Drop a filed PDF here, or', dropDot: '.',
    dropSynthetic: (p) => `(synthetic, ${p} pages)`,
    privacy: "The PDF is read on this server and not kept. Citations are looked up in the Caselaw Access Project's free files.",
    release: 'Release to check this PDF.',
    blockedNotPdf: 'This file is not a PDF. Choose a PDF saved from a word processor, or use the sample filing.',
    blockedTooLarge: `This PDF is larger than ${UPLOAD_LIMIT_MB} MB. This prototype reads files up to ${UPLOAD_LIMIT_MB} MB.`,
    steps: ['Reading the PDF', 'Finding citations', 'Looking up the free library', 'Matching quotes'],
    stepsCombined: 'Reading the PDF and finding citations',
    stepAdvisory: 'Advisory',
    notRun: 'not run',
    hollow: '○ ', filled: '● ',
    elapsed: (t) => `Elapsed ${t} s`,
    slow: 'Still working. Large filings take longer; the page stays here.',
    doneIn: (s) => `Done in ${s} s.`,
    announceStart: (f) => `Reading ${f}.`,
    announceDone: (s, n) => `Done in ${s} seconds. ${n} citations.`,
    partialNotice: (n) => `The free library did not answer for ${n} citations (timed out).`,
    retry: (n) => `[Retry ${n} citations]`,
    notCheckedLabel: 'Could not reach the free library.',
    notCheckedRule: 'Timed out after 20 s.',
    errServer: 'The server did not answer. Your file is still selected.',
    errRead: (r) => `The server could not read this PDF (${r}). Your file is still selected.`,
    stillSelected: 'Your file is still selected.',
    tryAgain: '[Try again]',
    noResults: (p) => `No case citations found in ${p} pages. Statutes, court rules and Id./supra references are not checked.`,
    dropAnother: '[Drop another PDF]',
    showPage: '[Show the page]', hidePage: '[Hide the page]',
    showShelf: '[Show the shelf]', hideShelf: '[Hide the shelf]',
    printMemo: '[Print memo]',
    runLive: '[Run it live]',
    rerun: '[Re-run the sample]',
    filingPage: (p) => `p. ${p}`,
    check: '✓',
    metadataOnly: 'Opinion text not loaded in this build.',
    couldNotLoadText: 'Could not load the opinion text; the details above come from the volume listing.',
    couldNotLoadVolumes: 'Could not load the volume list.',
    pinNote: 'Pin page not checked (the free library has no page breaks).',
    advisory: { supports: 'Advisory: supports', does_not_support: 'Advisory: does not support; read this first', cannot_tell: 'Advisory: cannot tell', none: 'Advisory: not run (no API key)' },
    // foot paragraph
    readFirst: 'Read these first:', nothingFirst: 'Nothing to read first:', then: 'Then:',
    ofN: (n) => `Of ${n} citations.`,
    notAnswered: (u) => `${u} not answered yet.`,
    countPhrases: {
      likely_fabricated: (n) => n === 1 ? 'likely not real case' : 'likely not real cases',
      unrecognized_reporter: () => 'no reporter by this name',
      quote_not_found: (n) => n === 1 ? 'quote not in the opinion' : 'quotes not in the opinion',
      wrong_cite_exists: () => 'exists at another page',
      verified: () => 'found',
      not_in_free_corpus: () => 'not in the free library',
      skipped: () => 'not checked',
    },
    // banner
    replayBanner: (d, file) => `Replay · run of ${d} from ${file}. Marks and seconds are from that run.`,
    offlineBanner: 'Offline · answers come from the cached free-library files.',
    offlineBannerOf: (d) => `Offline · answers come from the cached free-library files of ${d}.`,
    replayPending: 'No replay recorded yet. Run scripts/record_replay.py.',
    clThrottled: 'CourtListener throttled this run; the Caselaw Access Project answered for every row shown.',
    // credits
    creditsA: ' · a LexHack 2026 entry · sources: Caselaw Access Project, Free Law Project · ',
    creditsHow: '[How it works]',
    wordmark: 'Clerkmark',
    printFooter: (d) => `Clerkmark · ${d} · Triage aid. Not a finding.`,
    // evaluation
    evalH1: 'EVALUATION',
    evalIntro: 'Twenty citations with known classes, from seed/ground_truth.json, scored on the last run of the sample.',
    evalCaption: 'Twenty citations with known classes, scored on the last run',
    evalCols: ['Line', 'Citation', 'Expected', 'Memo said', 'Match'],
    yes: 'yes', no: 'no',
    eitherAccepted: 'not in free library or found',
    evalClose: (fp, real, c, total) => [`Real cases marked likely not real: `, String(fp), ` of ${real}. Correct classes: ${c} of ${total}.`],
    evalStale: (d) => `Scored on the run of ${d}.`,
    evalError: 'Could not load the evaluation.',
    evalProvenance: (file) => `Scored offline from ${file}, whose classes are the ground-truth expected classes; the live comparison needs the server.`,
    classKeys: 'Class keys: likely_fabricated = Likely not a real case · not_in_free_corpus = Not in the free library · wrong_cite_exists = Exists, but not at this page · quote_not_found = Found, but this quote is not in the opinion · unrecognized_reporter = No reporter by this name · verified = Found · skipped = Not checked',
    // how it works
    how: {
      what: ['WHAT IT CHECKS', "Clerkmark reads the PDF's text, finds every case citation, and looks each one up in the Caselaw Access Project's free files: which reporters exist, which volumes each has, which case sits at each page, and the opinion's text. Quoted words are matched against that text. Each row prints the rule that decided it."],
      ruleH: 'THE RULE',
      rule: [
        'The reporter abbreviation is unknown to reporters_db and to the Caselaw Access Project: No reporter by this name.',
        'The citation is Westlaw- or Lexis-only, a state slip citation, or a reporter the free library does not hold at all: Not in the free library.',
        'The volume is beyond the library’s last volume: Not in the free library (checked in CourtListener when a token is configured). Only a closed reporter series that ended at volume 999 (F.2d, F. Supp., F. Supp. 2d) cited at volume 1000 or more reads Likely not a real case.',
        'The volume exists but no held case begins at or spans the cited page (a gap, or past the last held case): Not in the free library.',
        'A case begins at the cited page and its name matches the citation: Found. Its quoted words are then matched. A year that disagrees with the decision date is printed as a note and never changes the class.',
        'The page falls inside a different case, or a case begins there under another name: if a case in the volume matches the cited name, Exists, but not at this page; if one distinctive party matches, Exists, but not at this page (name differs); if no case in the volume shares a party name, Likely not a real case, with the real case at that page printed beside it.',
        'Quoted words are matched against the opinion text after normalizing quotes, hyphens and bracketed alterations: no differing words is a match; one to three differing words shows the word diff; more, or a poor match, shows the closest passage.',
        'Pin pages are not checked: the free library’s text has no page breaks.',
        'Advisory (optional, needs an API key): does the quoted passage support the sentence it is cited for? Supports, does not support, or cannot tell. It never changes the class.',
      ],
      sourcesH: 'SOURCES',
      sources: [
        'Caselaw Access Project static files (static.case.law): reporters, volumes, cases and opinion text, no account needed; U.S. Reports through volume 572 (2014), F.3d through volume 935, F. Supp. 2d through volume 999.',
        'CourtListener citation-lookup API (Free Law Project): optional second source when a token is configured; 60 citations a minute.',
        'eyecite (Free Law Project) and reporters_db: citation extraction and reporter edition years.',
        'pdfplumber: PDF text. rapidfuzz: quote matching.',
      ],
      liveH: 'LIVE AND OPTIONAL',
      live: [
        ['PDF reading', 'live'],
        ['Citation extraction', 'live'],
        ['Caselaw Access Project lookups', 'live, cached'],
        ['CourtListener', 'optional (token)'],
        ['Quote matching', 'live'],
        ['Advisory', "optional (API key); 'not run' otherwise"],
        ['Progress while waiting', "one response; the four steps are the pipeline's stages, the timer is real, nothing is counted"],
      ],
      limitsH: 'LIMITS',
      limits: 'Statutes, court rules, Id., supra and short-form citations are listed as not checked. Pin pages cannot be checked: the free library’s opinion text has no page breaks. U.S. Reports after volume 572 (2014), F.3d after volume 935 and most state reporters after 2019 are outside the free library, so real cases there read ‘Not in the free library’. Scanned PDFs without a text layer are not read. ‘Likely not a real case’ is an observation about the reporter’s pages, not a finding about the filer.',
      creditsH: 'CREDITS',
      credits: 'Built on the Caselaw Access Project (Harvard Library Innovation Lab) for the free case-law files; Free Law Project for CourtListener, eyecite and reporters_db; and Princeton CITP’s work on automatic citation verification (LePhantomCite and the legal-hallucination agent), whose five error classes and whose warning that absence from a free corpus is not proof of fabrication shaped the rule. The sample filing is synthetic and modeled on the citations described in Mata v. Avianca, Inc., 678 F. Supp. 3d 443 (S.D.N.Y. 2023).',
    },
  };

  // §9 row labels by class, used only when the memo's own label is empty.
  const LABELS = {
    verified: 'Found.',
    quote_not_found: 'Found, but this quote is not in the opinion.',
    wrong_cite_exists: 'Exists, but not at this page.',
    not_in_free_corpus: 'Not in the free library. Check Westlaw or Lexis.',
    unrecognized_reporter: 'No reporter by this name.',
    likely_fabricated: 'Likely not a real case.',
    not_checked: 'Could not reach the free library.',
    skipped: 'Not checked (Id., supra or short form).',
  };
  const PEN_CLASSES = new Set(['likely_fabricated', 'unrecognized_reporter', 'wrong_cite_exists', 'quote_not_found']);
  const PENCIL_CLASSES = new Set(['not_in_free_corpus', 'not_checked', 'skipped']);
  const SHORT_REASON = {
    no_text_layer: 'No text layer', too_large: 'File too large', unsupported_type: 'Not a PDF',
    upstream_timeout: 'The free library did not answer', empty: 'Nothing to check', not_found: 'Not found',
    internal: 'Could not read this PDF', network: 'The server did not answer', blocked: 'File not accepted',
  };
  const FIXTURE_URL = '/static/fixture-memo.json';
  const FIXTURE_NAME = 'web/static/fixture-memo.json';
  const REPLAY_NAME = 'seed/replay.json';

  // ---------------------------------------------------------------- helpers
  const $ = (sel, root = document) => root.querySelector(sel);
  const $$ = (sel, root = document) => Array.from(root.querySelectorAll(sel));

  function el(tag, attrs, ...children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const [k, v] of Object.entries(attrs)) {
        if (v === null || v === undefined || v === false) continue;
        if (k === 'class') node.className = v;
        else if (k === 'text') node.textContent = v;
        else if (k === 'dataset') Object.assign(node.dataset, v);
        else if (k.startsWith('on') && typeof v === 'function') node.addEventListener(k.slice(2), v);
        else node.setAttribute(k, v === true ? '' : String(v));
      }
    }
    for (const c of children) {
      if (c === null || c === undefined || c === false) continue;
      node.append(typeof c === 'string' ? document.createTextNode(c) : c);
    }
    return node;
  }
  function svgEl(tag, attrs) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', tag);
    if (attrs) for (const [k, v] of Object.entries(attrs)) if (v !== null && v !== undefined) node.setAttribute(k, String(v));
    return node;
  }
  function clear(node) { while (node.firstChild) node.removeChild(node.firstChild); return node; }
  function setText(id, text) { const n = document.getElementById(id); if (n) n.textContent = text; return n; }

  const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
  // Wall-clock components as recorded in the ISO string (no timezone conversion: the stamp prints the run's own clock).
  function isoParts(iso) {
    const m = /^(\d{4})-(\d{2})-(\d{2})(?:[T ](\d{2}):(\d{2}))?/.exec(String(iso || ''));
    if (!m) return null;
    return { y: +m[1], mo: +m[2], d: +m[3], h: m[4] === undefined ? null : +m[4], mi: m[5] === undefined ? null : +m[5] };
  }
  const pad2 = (n) => String(n).padStart(2, '0');
  function fmtDate(iso) { const p = isoParts(iso); return p ? `${pad2(p.d)} ${MONTHS[p.mo - 1]} ${p.y}` : ''; }
  function fmtDateTime(iso) {
    const p = isoParts(iso); if (!p) return '';
    return p.h === null ? fmtDate(iso) : `${pad2(p.d)} ${MONTHS[p.mo - 1]} ${p.y} ${pad2(p.h)}:${pad2(p.mi)}`;
  }
  function fmtSec(ms) { return (Math.max(0, Number(ms) || 0) / 1000).toFixed(1); }
  function fmtNum(x) { return Number.isInteger(x) ? String(x) : Number(x).toFixed(1); }
  function longDate(iso) {
    // "June 14, 2019" as CAP-style running heads print it
    const p = isoParts(iso); if (!p) return '';
    const LONG = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];
    return `${LONG[p.mo - 1]} ${p.d}, ${p.y}`;
  }
  function msToken(name) {
    const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    if (!v) return 0;
    if (v.endsWith('ms')) return parseFloat(v);
    if (v.endsWith('s')) return parseFloat(v) * 1000;
    return parseFloat(v) || 0;
  }
  const reducedMotion = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // ---------------------------------------------------------------- state
  const S = {
    mode: 'first-run',        // first-run | loading | populated | partial | error | no-results
    live: false,              // /api/health answered
    health: null,
    fixture: null,            // the fixture memo (static fallback)
    sample: null,             // SampleInfo when live, else derived from the fixture
    memo: null,
    replay: false,
    file: null,               // the selected File
    lastKind: null,           // 'file' | 'sample'
    controller: null,
    timer: null,
    t0: 0,
    slowShown: false,
    openRow: null,
    evalReport: null,
    evalLoading: false,
    demo: false,
    animating: false,
    choreo: null,
    lastRun: null,
  };

  const dom = {};
  function cache() {
    ['banner', 'stamp', 'drop-own', 'drop-own-label', 'file-own', 'status', 'status-inner', 'drop', 'drop-inner', 'rows', 'notice', 'notice-inner', 'foot', 'foot-inner', 'footlinks', 'footlinks-inner', 'eval', 'how', 'credits', 'print-footer', 'main', 'v-re', 'v-date', 'v-against', 'panel-memo', 'panel-evaluation', 'panel-how']
      .forEach((id) => { dom[id] = document.getElementById(id); });
  }

  // ---------------------------------------------------------------- boot
  async function boot() {
    cache();
    paintStaticCopy();
    bindTabs();
    bindKeys();
    bindDrop();
    bindFileInputs();
    window.addEventListener('hashchange', onHash);

    const params = new URLSearchParams(location.search);
    const [health, fixture] = await Promise.all([fetchHealth(), fetchFixture()]);
    S.health = health; S.live = !!(health && health.ok !== false);
    S.fixture = fixture;
    S.sample = S.live ? await fetchSample() : null;
    if (!S.sample && fixture) S.sample = { id: SAMPLE_ID, filename: fixture.filing.filename, pages: fixture.filing.pages, label: fixture.filing.label };

    if (params.get('reset') === '1') {
      history.replaceState(null, '', location.pathname + location.hash);
      showFirstRun();
    } else if (params.has('state')) {
      await showState(params.get('state'));
    } else if (params.get('demo') === '1') {
      S.demo = true;
      await runDemo();
    } else {
      showFirstRun();
    }
    applyTabFromHash();
    onHash();
  }

  function paintStaticCopy() {
    setText('memo-title', COPY.memoH1);
    setText('k-to', COPY.kTo); setText('v-to', COPY.vTo);
    setText('k-from', COPY.kFrom); setText('v-from', COPY.vFrom);
    setText('k-re', COPY.kRe); setText('k-date', COPY.kDate); setText('k-against', COPY.kAgainst);
    setText('disclaimer', COPY.disclaimer);
    setText('litigant', COPY.litigant);
    setText('drop-own-label', COPY.btnDropOwn);
    // credits line with the wordmark
    const wm = el('span', { class: 'wordmark', text: COPY.wordmark });
    const howLink = el('a', { href: '#how', text: COPY.creditsHow });
    clear(dom.credits).append(wm, COPY.creditsA, howLink);
    document.fonts.ready.then(() => drawWordmarkEllipse(wm));
    renderHow();
  }

  function drawWordmarkEllipse(wm) {
    const textNode = wm.firstChild; if (!textNode) return;
    const range = document.createRange(); range.setStart(textNode, 0); range.setEnd(textNode, 1);
    const r = range.getBoundingClientRect(); const box = wm.getBoundingClientRect();
    if (!r.width) return;
    $$('svg', wm).forEach((n) => n.remove());
    const svg = svgEl('svg', { 'aria-hidden': 'true' });
    svg.style.left = '0'; svg.style.top = '0'; svg.style.width = box.width + 'px'; svg.style.height = box.height + 'px';
    const cx = r.left - box.left + r.width / 2, cy = r.top - box.top + r.height / 2;
    const path = svgEl('path', { d: ellipsePath(cx, cy, r.width / 2 + 3, r.height / 2 + 1, 7), transform: `rotate(-8 ${cx} ${cy})` });
    svg.append(path); wm.append(svg);
  }

  // ---------------------------------------------------------------- network
  async function fetchJSON(url, opts = {}, timeoutMs = 4000) {
    const ctl = new AbortController();
    const t = setTimeout(() => ctl.abort(), timeoutMs);
    try {
      const res = await fetch(url, { ...opts, signal: opts.signal || ctl.signal, cache: 'no-store' });
      const ct = res.headers.get('content-type') || '';
      const body = ct.includes('json') ? await res.json() : null;
      return { ok: res.ok, status: res.status, body };
    } finally { clearTimeout(t); }
  }
  async function fetchHealth() {
    try { const r = await fetchJSON('/api/health', {}, 2500); return r.ok && r.body && typeof r.body === 'object' ? r.body : null; }
    catch { return null; }
  }
  async function fetchFixture() {
    try { const r = await fetchJSON(FIXTURE_URL, {}, 8000); return r.ok && r.body && r.body.results ? r.body : null; }
    catch { return null; }
  }
  async function fetchSample() {
    try {
      const r = await fetchJSON('/api/samples', {}, 4000);
      if (r.ok && Array.isArray(r.body)) return r.body.find((s) => s.id === SAMPLE_ID) || r.body[0] || null;
    } catch { /* fall through */ }
    return null;
  }

  // ---------------------------------------------------------------- surfaces
  function setMode(mode) { S.mode = mode; document.documentElement.dataset.mode = mode; }
  function markReady() { document.documentElement.dataset.ready = S.mode; }

  function showBanner(text, linkText, onLink) {
    const b = dom.banner; clear(b);
    b.append(text);
    if (linkText) { b.append(' '); b.append(el('button', { type: 'button', class: 'blink', text: linkText, onclick: onLink })); }
    b.hidden = false;
  }
  function hideBanner() {
    dom.banner.hidden = true; clear(dom.banner);
    if (S.live && S.health && S.health.offline) showBanner(COPY.offlineBanner);
  }

  function headingForMemo(memo) {
    const f = memo.filing || {};
    const n = memo.counts ? memo.counts.total : (memo.results || []).length;
    const tail = `, ${f.pages} pages, ${n} citations`;
    let re;
    if (f.label) {
      const i = f.label.indexOf('. ');
      re = i > 0 ? f.label.slice(0, i) + tail + f.label.slice(i) : f.label + tail;
    } else re = (f.filename || '') + tail;
    dom['v-re'].textContent = re;
    dom['v-date'].textContent = fmtDate(memo.created_at);
    const cl = memo.sources_used && memo.sources_used.courtlistener;
    dom['v-against'].textContent = cl ? COPY.againstCl : COPY.againstNoCl;
  }
  function headingBlank(fileName) {
    dom['v-re'].textContent = fileName || COPY.blank;
    dom['v-date'].textContent = COPY.blank;
    const cl = S.health && S.health.courtlistener;
    dom['v-against'].textContent = cl ? COPY.againstCl : COPY.againstNoCl;
  }

  function renderStamp(memo, { replay, animate }) {
    const st = dom.stamp; clear(st);
    const n = memo.counts ? memo.counts.total : 0;
    const secs = fmtSec(memo.elapsed_ms);
    const u = memo.counts ? memo.counts.not_checked || 0 : 0;
    const dt = fmtDateTime(memo.created_at);
    let src = COPY.stampSourceCap;
    if (memo.sources_used && memo.sources_used.courtlistener) src += COPY.stampSourceCl;
    if (memo.offline && !replay) src += COPY.stampCache;
    st.append(
      el('span', { class: 'stamp-word', text: replay ? COPY.stampReplay : COPY.stampChecked }),
      el('span', { class: 'stamp-line', text: replay ? COPY.stampRunOf(dt) : dt }),
      el('span', { class: 'stamp-line' }, COPY.stampCount(n, secs), u > 0 ? el('span', { class: 'stamp-soft', text: COPY.stampUnanswered(u) }) : null),
      el('span', { text: src }),
    );
    st.setAttribute('aria-label', (replay ? COPY.stampAriaReplay : COPY.stampAria)(dt, n, secs, src.replace(/^\s*·\s*/, '')));
    st.setAttribute('role', 'img');
    st.classList.toggle('land', !!animate);
    st.hidden = false;
  }

  // ----- S1
  function renderDropTarget({ note, noteClass, fileName } = {}) {
    const d = dom['drop-inner']; clear(d);
    const pages = S.sample ? S.sample.pages : (S.fixture ? S.fixture.filing.pages : null);
    const sentence = el('p', { class: 'drop-sentence' });
    sentence.append(el('span', { text: COPY.dropLead }));
    const choose = el('label', { class: 'button-primary' }, el('span', { text: COPY.btnChoose }));
    const input = el('input', { type: 'file', id: 'file-s1', accept: 'application/pdf,.pdf' });
    input.addEventListener('change', onFileChosen);
    choose.append(input);
    sentence.append(choose, el('span', { text: COPY.dropDot }));
    const sampleBtn = el('button', { type: 'button', class: 'button-tonal', id: 'sample-btn', text: COPY.btnSample, onclick: () => startRun('sample') });
    sentence.append(sampleBtn);
    if (pages !== null && pages !== undefined) sentence.append(el('span', { class: 'muted', text: COPY.dropSynthetic(pages) }));
    d.append(sentence);
    const noteP = el('p', { class: 'drop-note' + (noteClass ? ' ' + noteClass : ''), id: 'drop-note' });
    if (note) {
      noteP.append(note.text);
      if (note.retry) noteP.append(' ', el('button', { type: 'button', class: 'blink', text: COPY.tryAgain, onclick: () => (S.file ? startRun('file') : startRun('sample')) }));
      input.setAttribute('aria-describedby', 'drop-note');
    } else noteP.textContent = COPY.privacy;
    d.append(noteP);
    dom.drop.hidden = false;
    if (fileName) dom['v-re'].textContent = fileName;
  }

  function showFirstRun() {
    stopTimer(); abortRun();
    S.memo = null; S.replay = false; S.openRow = null;
    setMode('first-run');
    hideBanner();
    headingBlank();
    dom.stamp.hidden = true; dom.stamp.classList.remove('land');
    dom['drop-own'].hidden = true;
    clear(dom.rows);
    dom.notice.hidden = true; clear(dom['notice-inner']);
    dom.foot.hidden = true; clear(dom['foot-inner']);
    dom.footlinks.hidden = true; clear(dom['footlinks-inner']);
    clear(dom['status-inner']); dom['status-inner'].classList.remove('collapsed');
    dom['print-footer'].textContent = '';
    renderDropTarget();
    document.title = COPY.titleFirst;
    markReady();
  }

  // ----- S2
  function renderStatusWaiting(fileName) {
    const inner = dom['status-inner']; clear(inner); inner.classList.remove('collapsed');
    const wrap = el('div');
    const list = el('ul', { class: 'status-steps', 'aria-hidden': 'true' });
    COPY.steps.forEach((s) => list.append(el('li', { text: COPY.hollow + s })));
    wrap.append(list);
    wrap.append(el('p', { class: 'status-elapsed', id: 'elapsed', 'aria-hidden': 'true', text: COPY.elapsed('0.0') }));
    wrap.append(el('p', { class: 'status-slow', id: 'slow', hidden: true }));
    wrap.append(el('p', { class: 'vh', id: 'announce', text: COPY.announceStart(fileName) }));
    inner.append(wrap);
  }
  function renderStatusDone(memo) {
    const inner = dom['status-inner']; clear(inner); inner.classList.remove('collapsed');
    const wrap = el('div');
    const list = el('ul', { class: 'status-steps', 'aria-hidden': 'true' });
    const st = memo.stage_timings_ms || {};
    const lookup = (Number(st.lookup) || 0) + (Number(st.classify) || 0);
    const lines = [
      [COPY.stepsCombined, st.extract],
      [COPY.steps[2], lookup],
      [COPY.steps[3], st.quotes],
    ];
    lines.forEach(([name, ms]) => list.append(el('li', { class: 'done', text: COPY.filled + name + (ms !== null && ms !== undefined ? ` · ${fmtSec(ms)} s` : '') })));
    wrap.append(list);
    wrap.append(el('p', { class: 'status-elapsed', 'aria-hidden': 'true', text: COPY.doneIn(fmtSec(memo.elapsed_ms)) }));
    wrap.append(el('p', { class: 'vh', text: COPY.announceDone(fmtSec(memo.elapsed_ms), memo.counts ? memo.counts.total : 0) }));
    inner.append(wrap);
  }
  function startTimer() {
    stopTimer();
    S.t0 = performance.now(); S.slowShown = false;
    S.timer = setInterval(() => {
      const t = (performance.now() - S.t0) / 1000;
      const e = document.getElementById('elapsed'); if (e) e.textContent = COPY.elapsed(t.toFixed(1));
      if (!S.slowShown && t * 1000 > SLOW_AFTER_MS) {
        S.slowShown = true;
        const s = document.getElementById('slow'); if (s) { s.textContent = COPY.slow; s.hidden = false; }
      }
    }, 100);
  }
  function stopTimer() { if (S.timer) { clearInterval(S.timer); S.timer = null; } }
  function abortRun() { if (S.controller) { S.controller.abort(); S.controller = null; } }

  function setInFlight(on) {
    dom['drop-own'].setAttribute('aria-disabled', on ? 'true' : 'false');
    const sb = document.getElementById('sample-btn'); if (sb) sb.setAttribute('aria-disabled', on ? 'true' : 'false');
    const chooser = document.getElementById('file-s1'); if (chooser) chooser.closest('label').setAttribute('aria-disabled', on ? 'true' : 'false');
  }

  function enterLoading(fileName) {
    setMode('loading');
    hideBanner(); S.replay = false; S.openRow = null;
    headingBlank(fileName);
    dom.stamp.hidden = true; dom.stamp.classList.remove('land');
    dom.drop.hidden = true; clear(dom['drop-inner']);
    clear(dom.rows);
    dom.notice.hidden = true; clear(dom['notice-inner']);
    dom.foot.hidden = true; clear(dom['foot-inner']);
    dom.footlinks.hidden = true; clear(dom['footlinks-inner']);
    dom['drop-own'].hidden = false;
    renderStatusWaiting(fileName);
    startTimer();
    setInFlight(true);
    document.title = COPY.titleLoading(fileName);
    markReady();
  }

  async function startRun(kind) {
    if (kind === 'file' && !S.file) return;
    abortRun();
    S.lastKind = kind;
    const fileName = kind === 'file' ? S.file.name : (S.sample ? S.sample.filename : (S.fixture ? S.fixture.filing.filename : ''));
    enterLoading(fileName);
    const ctl = new AbortController(); S.controller = ctl;
    const timeout = setTimeout(() => ctl.abort(), REQUEST_TIMEOUT_MS);
    try {
      let result;
      if (!S.live) {
        if (kind === 'sample') {
          const r = await fetchJSON(FIXTURE_URL, { signal: ctl.signal }, REQUEST_TIMEOUT_MS);
          result = r.ok ? { ok: true, body: r.body } : { ok: false, body: null, status: r.status };
        } else {
          result = { ok: false, network: true };
        }
      } else if (kind === 'sample') {
        result = await fetchJSON(`/api/memo/sample/${encodeURIComponent(S.sample ? S.sample.id : SAMPLE_ID)}`, { method: 'POST', signal: ctl.signal }, REQUEST_TIMEOUT_MS);
      } else {
        const fd = new FormData(); fd.append('file', S.file, S.file.name);
        result = await fetchJSON('/api/memo', { method: 'POST', body: fd, signal: ctl.signal }, REQUEST_TIMEOUT_MS);
      }
      if (ctl !== S.controller) return; // superseded by a newer run
      clearTimeout(timeout); S.controller = null;
      if (result.ok && result.body && Array.isArray(result.body.results)) {
        await showMemo(result.body, { animate: true });
      } else if (result.body && result.body.error) {
        showError(result.body.error, fileName);
      } else {
        showError({ code: 'network' }, fileName);
      }
    } catch (e) {
      if (ctl !== S.controller) return;
      clearTimeout(timeout); S.controller = null;
      showError({ code: 'network' }, fileName);
    }
  }

  // ----- error
  function showError(err, fileName) {
    stopTimer();
    setMode('error');
    setInFlight(false);
    clear(dom['status-inner']);
    clear(dom.rows);
    dom.stamp.hidden = true;
    dom['drop-own'].hidden = true;
    dom.foot.hidden = true; dom.footlinks.hidden = true; dom.notice.hidden = true;
    headingBlank(fileName);
    const code = err.code || 'internal';
    let text;
    if (code === 'network') text = COPY.errServer;
    else if (code === 'internal') text = COPY.errRead(String(err.message || '').replace(/^The server could not read this PDF \((.*)\)\.?$/, '$1') || 'internal');
    else text = [err.message, err.hint].filter(Boolean).join(' ') + (code === 'no_text_layer' || code === 'unsupported_type' || code === 'too_large' ? '' : ' ' + COPY.stillSelected);
    const retry = code === 'network' || code === 'internal' || code === 'upstream_timeout';
    renderDropTarget({ note: { text, retry }, noteClass: 'error', fileName });
    document.title = COPY.titleError(SHORT_REASON[code] || SHORT_REASON.internal);
    markReady();
  }

  // ----- S3
  function classify(memo) {
    const counts = memo.counts || countRows(memo.results);
    return { counts, partial: (counts.not_checked || 0) > 0, empty: !memo.results || memo.results.length === 0 };
  }
  function countRows(results) {
    const c = { verified: 0, quote_not_found: 0, wrong_cite_exists: 0, not_in_free_corpus: 0, unrecognized_reporter: 0, likely_fabricated: 0, not_checked: 0, skipped: 0, total: 0 };
    (results || []).forEach((r) => { if (r.class in c) c[r.class] += 1; c.total += 1; });
    return c;
  }

  async function showMemo(memo, { animate = false, replay = false } = {}) {
    stopTimer(); abortRun();
    S.memo = memo; S.replay = replay; S.openRow = null;
    setInFlight(false);
    const { counts, partial, empty } = classify(memo);
    memo.counts = counts;
    setMode(empty ? 'no-results' : partial ? 'partial' : 'populated');
    headingForMemo(memo);
    dom.drop.hidden = true; clear(dom['drop-inner']);
    dom['drop-own'].hidden = false;
    dom['print-footer'].textContent = COPY.printFooter(fmtDateTime(memo.created_at));
    if (memo.warnings && memo.warnings.length) {
      clear(dom['notice-inner']); dom['notice-inner'].append(memo.warnings.join(' ')); dom.notice.hidden = false;
    } else { dom.notice.hidden = true; clear(dom['notice-inner']); }

    // rows
    clear(dom.rows);
    if (empty) {
      renderNoResults(memo);
      dom.foot.hidden = true; clear(dom['foot-inner']);
      dom.footlinks.hidden = true; clear(dom['footlinks-inner']);
      clear(dom['status-inner']);
      renderStamp(memo, { replay, animate: false });
      document.title = COPY.titleMemo(0, 0);
      markReady();
      return;
    }
    const doAnimate = animate && !reducedMotion();
    memo.results.forEach((r, i) => dom.rows.append(renderRow(r, memo, i)));
    renderFoot(memo, partial);
    document.title = COPY.titleMemo(counts.total, counts.likely_fabricated || 0);

    if (partial) {
      const n = counts.not_checked;
      clear(dom['notice-inner']);
      dom['notice-inner'].append(COPY.partialNotice(n), ' ', el('button', { type: 'button', class: 'blink', text: COPY.retry(n), onclick: () => startRun(S.lastKind === 'file' && S.file ? 'file' : 'sample') }));
      dom.notice.hidden = false;
    }

    if (!animate) {
      clear(dom['status-inner']);
      await document.fonts.ready;
      drawAllMarks({ animate: false });
      renderStamp(memo, { replay, animate: false });
      dom.foot.classList.remove('fade');
      markReady();
      return;
    }

    // the choreography: status "Done" → rows reveal → marks draw → stamp lands, status collapses, foot appears
    S.animating = true;
    renderStatusDone(memo);
    dom.foot.classList.add('fade');
    const rows = $$('.row', dom.rows);
    const durRow = msToken('--dur-row'), stagRow = msToken('--stagger-row');
    const cap = Math.max(0, 600 - durRow);
    rows.forEach((li, i) => {
      li.classList.add('hidden-row');
      li.style.setProperty('--d', `${Math.min(i * stagRow, cap)}ms`);
    });
    await document.fonts.ready;
    await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
    rows.forEach((li) => { li.classList.remove('hidden-row'); if (doAnimate) li.classList.add('enter'); });
    const rowsTotal = doAnimate ? Math.min((rows.length - 1) * stagRow, cap) + durRow : 0;
    await sleep(rowsTotal);
    const marksTotal = drawAllMarks({ animate: doAnimate });
    S.lastRun = { marks: S.choreo ? S.choreo.marks : 0, animated: doAnimate, rows: rows.length, rowsMs: rowsTotal, marksMs: marksTotal };
    await sleep(marksTotal);
    // hold the "Done" block at least 1 s in all
    const heldSoFar = rowsTotal + marksTotal;
    if (heldSoFar < 1000) await sleep(1000 - heldSoFar);
    renderStamp(memo, { replay, animate: doAnimate });
    dom['status-inner'].classList.add('collapsed');
    dom.foot.classList.remove('fade');
    rows.forEach((li) => li.classList.remove('enter'));
    S.animating = false;
    markReady();
  }

  function renderNoResults(memo) {
    const p = el('p', { class: 'noresults' });
    p.append(COPY.noResults(memo.filing ? memo.filing.pages : 0));
    const lab = el('label', { class: 'blink file' }, el('span', { text: COPY.dropAnother }));
    const input = el('input', { type: 'file', id: 'file-another', accept: 'application/pdf,.pdf' });
    input.addEventListener('change', onFileChosen);
    lab.append(input);
    p.append(' ', lab);
    dom.rows.append(el('li', { class: 'ln' }, el('span', { class: 'num', 'aria-hidden': 'true' }), p));
  }

  // ---------------------------------------------------------------- rows
  function labelFor(r) {
    if (r.label) return r.label;
    return LABELS[r.class] || '';
  }
  function ruleFor(r) {
    const parts = [];
    if (r.class === 'quote_not_found' && r.quote_check && r.quote_check.similarity !== null && r.quote_check.similarity !== undefined && !(r.reasons && r.reasons[0])) parts.push(`Closest passage ${fmtNum(r.quote_check.similarity)}% similar.`);
    if (r.reasons && r.reasons[0]) parts.push(r.reasons[0]);
    if (r.pincite_unverified) parts.push(COPY.pinNote);
    if (r.advisory && r.advisory.verdict) parts.push(COPY.advisory[r.advisory.verdict] || '');
    return parts.join(' ');
  }

  // Build the citation text with the reporter and page wrapped in spans (all text nodes; nothing parsed as markup).
  function buildCiteSpan(r) {
    const span = el('span', { class: 'citespan' });
    const text = String(r.cite_text || '');
    const c = r.citation || {};
    const core = c.text ? text.indexOf(c.text) : -1;
    if (core < 0 || !c.reporter) { span.textContent = text; return span; }
    const coreText = c.text;
    const repIdx = coreText.indexOf(c.reporter);
    if (repIdx < 0) { span.textContent = text; return span; }
    const afterRep = repIdx + c.reporter.length;
    let pgIdx = -1, pgLen = 0;
    if (c.page !== null && c.page !== undefined) {
      const pg = String(c.page);
      pgIdx = coreText.indexOf(pg, afterRep);
      pgLen = pg.length;
    }
    const frag = document.createDocumentFragment();
    frag.append(text.slice(0, core));
    const coreEl = el('span', { class: 'citecore' });
    coreEl.append(coreText.slice(0, repIdx));
    coreEl.append(el('span', { class: 'rep', text: c.reporter }));
    if (pgIdx >= 0) {
      coreEl.append(coreText.slice(afterRep, pgIdx));
      coreEl.append(el('span', { class: 'pg', text: coreText.slice(pgIdx, pgIdx + pgLen) }));
      coreEl.append(coreText.slice(pgIdx + pgLen));
    } else coreEl.append(coreText.slice(afterRep));
    frag.append(coreEl);
    frag.append(text.slice(core + coreText.length));
    span.append(frag);
    return span;
  }

  // Wrap given words (in order) inside a text as .penword spans; text nodes only.
  function textWithWords(text, words, cls) {
    const frag = document.createDocumentFragment();
    let pos = 0;
    for (const w of words || []) {
      if (!w) continue;
      const re = new RegExp(`\\b${w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')}\\b`);
      const m = re.exec(text.slice(pos));
      if (!m) continue;
      const at = pos + m.index;
      frag.append(text.slice(pos, at));
      frag.append(el('span', { class: cls, text: m[0] }));
      pos = at + m[0].length;
    }
    frag.append(text.slice(pos));
    return frag;
  }

  function renderRow(r, memo, i) {
    const n = r.row || i + 1;
    const li = el('li', { class: 'row ln', id: `line-${n}`, dataset: { class: r.class, mark: r.mark || 'none', row: String(n) } });
    li.append(el('span', { class: 'num', text: String(n), tabindex: '-1' }));
    const body = el('div', { class: 'rowbody' });

    const cite = el('div', { class: 'cite' });
    const p = el('p', { class: 'citetext' });
    p.append(buildCiteSpan(r));
    if (r.mark === 'strike-correct' && r.evidence && r.evidence.real_case_at_page) {
      const pg = $('.pg', p); if (pg) pg.dataset.correct = String(r.evidence.real_case_at_page.first_page);
    }
    const fp = r.citation && r.citation.filing_page;
    if (fp) p.append(el('span', { class: 'fp', text: COPY.filingPage(fp) }));
    cite.append(p);
    if (r.class === 'quote_not_found' && r.quote_check && r.quote_check.quote) {
      const q = el('p', { class: 'quote' });
      const qt = el('span', { class: 'qtext' });
      qt.append('“');
      qt.append(textWithWords(r.quote_check.quote, (r.quote_check.diff || []).map((d) => d.filed), 'penword'));
      qt.append('”');
      q.append(qt);
      cite.append(q);
    }
    const svg = svgEl('svg', { class: 'mark', 'aria-hidden': 'true' });
    cite.append(svg);

    const noteId = `note-${n}`, evId = `evidence-${n}`;
    if (r.drawer === 'page' || r.drawer === 'shelf') {
      const links = el('p', { class: 'rowlinks' });
      const btn = el('button', {
        type: 'button', class: 'blink', 'aria-expanded': 'false', 'aria-controls': evId, 'aria-describedby': noteId,
        text: r.drawer === 'page' ? COPY.showPage : COPY.showShelf,
      });
      btn.addEventListener('click', () => toggleDrawer(li, r, btn));
      links.append(btn);
      cite.append(links);
    }
    body.append(cite);

    const note = el('div', { class: 'note', id: noteId });
    const label = el('p', { class: 'label ' + (PEN_CLASSES.has(r.class) ? 'pen' : PENCIL_CLASSES.has(r.class) ? 'pencil' : '') });
    if (r.class === 'verified') label.append(el('span', { class: 'check', 'aria-hidden': 'true', text: COPY.check }));
    label.append(labelFor(r));
    note.append(label);
    const rule = ruleFor(r);
    if (rule) note.append(el('p', { class: 'rule', text: rule }));
    body.append(note);

    if (r.drawer === 'page' || r.drawer === 'shelf') {
      const drawer = el('div', { class: 'drawer', id: evId, inert: true });
      drawer.append(el('div', { class: 'drawer-inner' }));
      body.append(drawer);
    }
    li.append(body);
    return li;
  }

  // ---------------------------------------------------------------- marks
  // Deterministic hand jitter per row so a resize redraws the same pen stroke.
  function jitter(seed, k) { const x = Math.sin(seed * 12.9898 + k * 78.233) * 43758.5453; return x - Math.floor(x); }
  function ellipsePath(cx, cy, rx, ry, seed) {
    const K = 0.5523, start = Math.PI * 7 / 6; // 10 o'clock
    const pts = [];
    for (let k = 0; k < 4; k++) {
      const a = start + k * Math.PI / 2;
      const jx = 1 + (jitter(seed, k) - 0.5) * 0.06, jy = 1 + (jitter(seed, k + 9) - 0.5) * 0.06;
      pts.push({ a, rx: rx * jx, ry: ry * jy });
    }
    const P = (i) => { const p = pts[i % 4]; return [cx + p.rx * Math.cos(p.a), cy + p.ry * Math.sin(p.a)]; };
    const D = (i) => { const p = pts[i % 4]; return [-p.rx * Math.sin(p.a), p.ry * Math.cos(p.a)]; };
    let d = '';
    const f = (v) => v.toFixed(2);
    const [sx, sy] = P(0); d += `M${f(sx)} ${f(sy)}`;
    for (let k = 0; k < 4; k++) {
      const [x0, y0] = P(k), [dx0, dy0] = D(k), [x1, y1] = P(k + 1), [dx1, dy1] = D(k + 1);
      d += ` C${f(x0 + K * dx0)} ${f(y0 + K * dy0)} ${f(x1 - K * dx1)} ${f(y1 - K * dy1)} ${f(x1)} ${f(y1)}`;
    }
    return d + ' Z';
  }
  // Client rects of a span, merged into one rect per line (nested spans yield several fragments per line),
  // dropping fragments clipped away by an overflow-hidden ancestor (a line-clamped quote).
  function rectsOf(node, base, clip) {
    if (!node) return [];
    const raw = Array.from(node.getClientRects()).filter((r) => r.width > 0 && (!clip || r.bottom <= clip.bottom + 1));
    raw.sort((a, b) => a.top - b.top || a.left - b.left);
    const lines = [];
    for (const r of raw) {
      const last = lines[lines.length - 1];
      const mid = r.top + r.height / 2;
      if (last && mid >= last.top && mid <= last.bottom) {
        last.left = Math.min(last.left, r.left); last.right = Math.max(last.right, r.right);
        last.top = Math.min(last.top, r.top); last.bottom = Math.max(last.bottom, r.bottom);
      } else lines.push({ left: r.left, right: r.right, top: r.top, bottom: r.bottom });
    }
    return lines.map((l) => ({ x: l.left - base.left, y: l.top - base.top, w: l.right - l.left, h: l.bottom - l.top }));
  }
  function drawRowMark(li, r) {
    const svg = $('svg.mark', li); if (!svg) return 0;
    clear(svg);
    const mark = r.mark || 'none';
    if (mark === 'none' || mark === 'check') return 0;
    const cite = $('.cite', li); const base = cite.getBoundingClientRect();
    svg.setAttribute('viewBox', `0 0 ${base.width} ${base.height}`);
    svg.setAttribute('width', base.width); svg.setAttribute('height', base.height);
    const seed = Number(li.dataset.row) || 1;
    const paths = [];
    const add = (d, kind, extra) => { const p = svgEl('path', { d, 'data-mark': kind, pathLength: '1' }); if (extra) for (const [k, v] of Object.entries(extra)) p.setAttribute(k, v); svg.append(p); paths.push(p); };
    const underline = (rects, kind, dy = 2) => rects.forEach((rc) => add(`M${(rc.x).toFixed(2)} ${(rc.y + rc.h + dy).toFixed(2)} L${(rc.x + rc.w).toFixed(2)} ${(rc.y + rc.h + dy).toFixed(2)}`, kind));
    const circle = (rc, kind) => {
      const cx = rc.x + rc.w / 2, cy = rc.y + rc.h / 2;
      add(ellipsePath(cx, cy, rc.w / 2 + 6, rc.h / 2 + 3, seed), kind, { transform: `rotate(-2 ${cx.toFixed(2)} ${cy.toFixed(2)})` });
    };
    if (mark === 'circle-all') {
      const rects = rectsOf($('.citespan', li), base);
      if (rects.length) { circle(rects[0], 'circle-all'); if (rects.length > 1) underline(rects.slice(1), 'underline-red'); }
    } else if (mark === 'circle-reporter') {
      const rects = rectsOf($('.rep', li), base);
      if (rects.length === 1) circle(rects[0], 'circle-reporter'); else if (rects.length) underline(rects, 'underline-red');
    } else if (mark === 'strike-correct') {
      const rects = rectsOf($('.pg', li), base);
      if (rects.length === 1) {
        const rc = rects[0]; const ym = rc.y + rc.h / 2;
        add(`M${rc.x.toFixed(2)} ${(ym + 1).toFixed(2)} L${(rc.x + rc.w).toFixed(2)} ${(ym - 1).toFixed(2)}`, 'strike-correct');
        const real = r.evidence && r.evidence.real_case_at_page;
        if (real && real.first_page !== undefined) {
          const t = svgEl('text', { x: (rc.x + rc.w / 2).toFixed(2), y: (rc.y + rc.h / 2 - 14 + 4).toFixed(2), 'text-anchor': 'middle' });
          t.textContent = String(real.first_page); svg.append(t);
        }
      } else if (rects.length) underline(rects, 'underline-red');
    } else if (mark === 'underline-quote') {
      const q = $('.quote', li);
      const rects = rectsOf($('.qtext', li), base, q ? q.getBoundingClientRect() : null);
      underline(rects, 'underline-quote');
    } else if (mark === 'underline-pencil') {
      underline(rectsOf($('.citespan', li), base), 'underline-pencil');
    }
    return paths.length ? 1 : 0;
  }
  // Draw every row's mark. With animate, stagger draw-on in row order and return the total duration.
  function drawAllMarks({ animate }) {
    if (!S.memo || !S.memo.results) return 0;
    const byRow = new Map(S.memo.results.map((r) => [String(r.row), r]));
    const dur = msToken('--dur-mark'), stag = msToken('--stagger-mark');
    let k = 0;
    const svgs = [];
    $$('.row', dom.rows).forEach((li) => {
      const r = byRow.get(li.dataset.row); if (!r) return;
      const has = drawRowMark(li, r);
      const svg = $('svg.mark', li);
      svg.classList.toggle('animate', !!animate);
      svg.classList.remove('on');
      if (has) { svg.style.setProperty('--d', `${k * stag}ms`); if (animate) svgs.push(svg); k += 1; }
    });
    S.choreo = { marks: k, animated: !!animate };
    if (animate) {
      requestAnimationFrame(() => requestAnimationFrame(() => svgs.forEach((s) => s.classList.add('on'))));
      return k ? (k - 1) * stag + dur : 0;
    }
    return 0;
  }
  let resizeRaf = 0;
  const ro = new ResizeObserver(() => {
    if (S.animating) return;
    cancelAnimationFrame(resizeRaf);
    resizeRaf = requestAnimationFrame(() => { drawAllMarks({ animate: false }); const wm = $('.wordmark'); if (wm) drawWordmarkEllipse(wm); });
  });
  window.addEventListener('beforeprint', () => drawAllMarks({ animate: false }));
  window.addEventListener('afterprint', () => drawAllMarks({ animate: false }));
  document.fonts.addEventListener('loadingdone', () => { if (!S.animating) drawAllMarks({ animate: false }); const wm = $('.wordmark'); if (wm) drawWordmarkEllipse(wm); });

  // ---------------------------------------------------------------- drawers
  function renderPagePanel(r) {
    const e = r.evidence || {};
    const panel = el('div', { class: 'panel-page' });
    const head = el('div', { class: 'running-head-line' });
    const rh = el('p', { class: 'running-head', tabindex: '-1' });
    rh.textContent = e.running_head || runningHeadFallback(r);
    head.append(rh);
    if (e.page_marker) head.append(el('span', { class: 'page-marker', text: String(e.page_marker) }));
    panel.append(head);
    if (e.excerpt) {
      const ex = el('p', { class: 'excerpt' });
      const t = e.excerpt; const hl = e.excerpt_highlight;
      if (Array.isArray(hl) && hl.length === 2 && hl[0] >= 0 && hl[1] <= t.length && hl[0] < hl[1]) {
        ex.append(t.slice(0, hl[0]));
        const hs = el('span', { class: 'hl-passage' });
        const words = r.quote_check && r.quote_check.diff ? r.quote_check.diff.map((d) => d.opinion) : [];
        hs.append(textWithWords(t.slice(hl[0], hl[1]), words, 'penword'));
        ex.append(hs);
        ex.append(t.slice(hl[1]));
      } else ex.textContent = t;
      panel.append(ex);
    } else {
      panel.append(el('p', { class: 'excerpt-note', text: COPY.metadataOnly }));
    }
    if (e.links && e.links.length) {
      const f = el('p', { class: 'panel-footer' });
      e.links.forEach((u) => f.append(el('span', {}, el('a', { href: u, target: '_blank', rel: 'noopener', text: u }))));
      panel.append(f);
    }
    return panel;
  }
  function runningHeadFallback(r) {
    const real = r.evidence && (r.evidence.real_case_at_page || r.evidence.name_hit);
    if (!real) return '';
    return [real.cite, String(real.name || '').toUpperCase(), real.court_abbreviation || real.court, longDate(real.decision_date)].filter(Boolean).join(' · ');
  }
  function renderShelfPanel(r) {
    const e = r.evidence || {}; const vr = e.volume_range;
    const panel = el('div', { class: 'panel-shelf' });
    const rh = el('p', { class: 'running-head', tabindex: '-1' });
    if (!vr) { rh.textContent = COPY.couldNotLoadVolumes; panel.append(rh); return panel; }
    rh.textContent = vr.reporter || '';
    panel.append(rh);
    const vmin = Number(vr.vmin) || 1, vmax = Number(vr.vmax) || vmin, cited = vr.cited !== null && vr.cited !== undefined ? Number(vr.cited) : null;
    const hi = Math.max(vmax, cited || vmax);
    const span = Math.max(1, hi - vmin + 1);
    const pct = (v) => `${(((v - vmin) / span) * 100).toFixed(3)}%`;
    const strip = el('div', { class: 'strip', role: 'img', 'aria-label': vr.note || '' });
    const held = el('div', { class: 'held' }); held.style.left = '0'; held.style.width = pct(vmax + 1); strip.append(held);
    if (hi > vmax) { const beyond = el('div', { class: 'beyond' }); beyond.style.left = pct(vmax + 1); beyond.style.right = '0'; strip.append(beyond); }
    if (cited !== null) {
      const tick = el('div', { class: 'tick' }); tick.style.left = `calc(${pct(cited + 0.5)} - 1px)`; strip.append(tick);
      const tl = el('span', { class: 'tick-label', text: String(cited) }); tl.style.left = pct(cited + 0.5); strip.append(tl);
    }
    panel.append(strip);
    panel.append(el('p', { class: 'strip-label', text: vr.note || '' }));
    if (e.links && e.links.length) {
      const f = el('p', { class: 'panel-footer' });
      e.links.forEach((u) => f.append(el('span', {}, el('a', { href: u, target: '_blank', rel: 'noopener', text: u }))));
      panel.append(f);
    }
    return panel;
  }

  function toggleDrawer(li, r, btn, { noanim = false, focus = true } = {}) {
    const drawer = $('.drawer', li); if (!drawer) return;
    const isOpen = drawer.classList.contains('open');
    if (isOpen) { closeDrawer(li, r, btn, { focus }); return; }
    // another row open → swap: it closes fast, this one opens without height animation
    let swap = false;
    if (S.openRow && S.openRow !== li) {
      const prev = S.openRow; const pr = S.memo.results.find((x) => String(x.row) === prev.dataset.row);
      const pb = $('.blink', prev);
      closeDrawer(prev, pr, pb, { focus: false, fast: true });
      swap = true;
    }
    const inner = $('.drawer-inner', drawer); clear(inner);
    inner.append(r.drawer === 'page' ? renderPagePanel(r) : renderShelfPanel(r));
    drawer.removeAttribute('inert');
    drawer.classList.toggle('noanim', swap || noanim || reducedMotion());
    drawer.classList.remove('closing');
    drawer.classList.add('open');
    li.classList.add('open');
    btn.setAttribute('aria-expanded', 'true');
    btn.textContent = r.drawer === 'page' ? COPY.hidePage : COPY.hideShelf;
    S.openRow = li;
    if (focus) { const rh = $('.running-head', drawer); if (rh) rh.focus({ preventScroll: false }); }
    const onKey = (ev) => { if (ev.key === 'Escape') { ev.stopPropagation(); closeDrawer(li, r, btn, { focus: true }); } };
    drawer.addEventListener('keydown', onKey);
    drawer._onKey = onKey;
    if (location.hash !== `#line-${li.dataset.row}`) history.replaceState(null, '', `${location.pathname}${location.search}#line-${li.dataset.row}`);
  }
  function closeDrawer(li, r, btn, { focus = true, fast = false } = {}) {
    const drawer = $('.drawer', li); if (!drawer) return;
    drawer.classList.toggle('closing', fast && !reducedMotion());
    drawer.classList.remove('open', 'noanim');
    li.classList.remove('open');
    drawer.setAttribute('inert', '');
    if (drawer._onKey) { drawer.removeEventListener('keydown', drawer._onKey); drawer._onKey = null; }
    if (btn) { btn.setAttribute('aria-expanded', 'false'); btn.textContent = r && r.drawer === 'shelf' ? COPY.showShelf : COPY.showPage; }
    if (S.openRow === li) S.openRow = null;
    if (focus && btn) btn.focus();
    if (location.hash === `#line-${li.dataset.row}`) history.replaceState(null, '', `${location.pathname}${location.search}#memo`);
  }

  // ---------------------------------------------------------------- foot paragraph
  function renderFoot(memo, partial) {
    const c = memo.counts; const foot = dom['foot-inner']; clear(foot);
    const firstRow = (cls) => { const r = (memo.results || []).find((x) => x.class === cls); return r ? r.row : ''; };
    const link = (cls, n) => {
      const a = el('a', { href: `#line-${firstRow(cls)}`, text: String(n) });
      a.addEventListener('click', (ev) => { ev.preventDefault(); jumpToClass(cls); });
      return a;
    };
    const flagged = ['likely_fabricated', 'unrecognized_reporter', 'quote_not_found', 'wrong_cite_exists'].filter((k) => (c[k] || 0) > 0);
    const rest = ['verified', 'not_in_free_corpus', 'skipped'].filter((k) => k === 'verified' || (c[k] || 0) > 0);
    const appendList = (keys, sep, end) => {
      keys.forEach((k, i) => {
        foot.append(' ', link(k, c[k] || 0), ' ' + COPY.countPhrases[k](c[k] || 0));
        foot.append(i < keys.length - 1 ? sep : end);
      });
    };
    if (flagged.length) {
      foot.append(COPY.readFirst); appendList(flagged, ',', '.');
      foot.append(' ' + COPY.then); appendList(rest, ';', '.');
    } else {
      foot.append(COPY.nothingFirst); appendList(rest, ';', '.');
    }
    foot.append(' ' + COPY.ofN(c.total));
    if (partial && c.not_checked) foot.append(' ' + COPY.notAnswered(c.not_checked));
    dom.foot.hidden = false;
    const fl = dom['footlinks-inner']; clear(fl);
    fl.append(el('button', { type: 'button', class: 'blink', text: COPY.printMemo, onclick: () => window.print() }));
    dom.footlinks.hidden = false;
  }
  function jumpToClass(cls) {
    const r = (S.memo.results || []).find((x) => x.class === cls); if (!r) return;
    const li = document.getElementById(`line-${r.row}`); if (!li) return;
    li.scrollIntoView({ block: 'center', behavior: reducedMotion() ? 'auto' : 'smooth' });
    const num = $('.num', li); if (num) num.focus({ preventScroll: true });
    li.classList.add('target');
    setTimeout(() => { li.classList.add('rendered-target'); li.classList.remove('target'); setTimeout(() => li.classList.remove('rendered-target'), 250); }, 1500);
  }

  // ---------------------------------------------------------------- file intake
  function bindFileInputs() { dom['file-own'].addEventListener('change', onFileChosen); }
  function onFileChosen(ev) {
    const input = ev.target; const f = input.files && input.files[0]; if (!f) return;
    if (input.closest('[aria-disabled="true"]')) return;
    acceptFile(f);
  }
  function acceptFile(f) {
    const isPdf = f.type === 'application/pdf' || /\.pdf$/i.test(f.name || '');
    if (!isPdf) { blocked(COPY.blockedNotPdf, f); return; }
    if (f.size > UPLOAD_LIMIT_BYTES) { blocked(COPY.blockedTooLarge, f); return; }
    S.file = f;
    startRun('file');
  }
  function blocked(text, f) {
    if (S.mode === 'first-run' || S.mode === 'error') {
      renderDropTarget({ note: { text, retry: false }, noteClass: 'blocked' });
      document.title = COPY.titleError(SHORT_REASON.blocked);
    } else {
      clear(dom['notice-inner']); dom['notice-inner'].append(text); dom.notice.hidden = false;
    }
  }
  function bindDrop() {
    const sheet = dom.main;
    let depth = 0;
    sheet.addEventListener('dragenter', (ev) => { ev.preventDefault(); depth += 1; sheet.classList.add('dragover'); const s = $('#drop .drop-sentence span:first-child'); if (s && S.mode === 'first-run') s.textContent = COPY.release; });
    sheet.addEventListener('dragover', (ev) => { ev.preventDefault(); });
    sheet.addEventListener('dragleave', () => { depth = Math.max(0, depth - 1); if (depth === 0) { sheet.classList.remove('dragover'); const s = $('#drop .drop-sentence span:first-child'); if (s && S.mode === 'first-run') s.textContent = COPY.dropLead; } });
    sheet.addEventListener('drop', (ev) => {
      ev.preventDefault(); depth = 0; sheet.classList.remove('dragover');
      const s = $('#drop .drop-sentence span:first-child'); if (s) s.textContent = COPY.dropLead;
      const f = ev.dataTransfer && ev.dataTransfer.files && ev.dataTransfer.files[0]; if (!f) return;
      acceptFile(f);
    });
  }

  // ---------------------------------------------------------------- tabs and hash
  const TABS = ['memo', 'evaluation', 'how'];
  function bindTabs() {
    const tabs = $$('.tab');
    tabs.forEach((t) => {
      t.addEventListener('click', () => selectTab(t.dataset.hash, { focusTab: false }));
      t.addEventListener('keydown', (ev) => {
        const i = TABS.indexOf(t.dataset.hash); let j = null;
        if (ev.key === 'ArrowRight') j = (i + 1) % TABS.length;
        else if (ev.key === 'ArrowLeft') j = (i + TABS.length - 1) % TABS.length;
        else if (ev.key === 'Home') j = 0;
        else if (ev.key === 'End') j = TABS.length - 1;
        if (j !== null) { ev.preventDefault(); selectTab(TABS[j], { focusTab: true }); }
      });
    });
  }
  function selectTab(name, { focusTab = false, pushHash = true } = {}) {
    if (!TABS.includes(name)) name = 'memo';
    $$('.tab').forEach((t) => {
      const on = t.dataset.hash === name;
      t.setAttribute('aria-selected', on ? 'true' : 'false');
      t.tabIndex = on ? 0 : -1;
      if (on && focusTab) t.focus();
    });
    dom['panel-memo'].hidden = name !== 'memo';
    dom['panel-evaluation'].hidden = name !== 'evaluation';
    dom['panel-how'].hidden = name !== 'how';
    if (pushHash && !(name === 'memo' && /^#line-\d+$/.test(location.hash))) {
      const h = `#${name}`; if (location.hash !== h) history.replaceState(null, '', `${location.pathname}${location.search}${h}`);
    }
    if (name === 'evaluation') loadEval();
    if (name === 'memo' && S.memo && !S.animating) requestAnimationFrame(() => drawAllMarks({ animate: false }));
  }
  function applyTabFromHash() {
    const h = location.hash.replace('#', '');
    if (TABS.includes(h)) selectTab(h, { pushHash: false });
    else selectTab('memo', { pushHash: false });
  }
  function onHash() {
    const h = location.hash.replace('#', '');
    if (TABS.includes(h)) { selectTab(h, { pushHash: false }); return; }
    const m = /^line-(\d+)$/.exec(h);
    if (m && S.memo) {
      selectTab('memo', { pushHash: false });
      const li = document.getElementById(h); if (!li) return;
      const r = S.memo.results.find((x) => String(x.row) === m[1]);
      const btn = $('.blink', li);
      if (r && btn && !$('.drawer', li).classList.contains('open')) toggleDrawer(li, r, btn, { noanim: true, focus: false });
      li.scrollIntoView({ block: 'center', behavior: 'auto' });
    }
  }

  // ---------------------------------------------------------------- keys
  function bindKeys() {
    document.addEventListener('keydown', (ev) => {
      if (!(ev.altKey && ev.shiftKey)) return;
      if (ev.code === 'KeyR') { ev.preventDefault(); resetAll(); }
      else if (ev.code === 'KeyP') { ev.preventDefault(); replay(); }
    });
  }
  function resetAll() {
    S.demo = false;
    history.replaceState(null, '', location.pathname);
    showFirstRun();
    selectTab('memo', { pushHash: false });
  }
  async function replay() {
    let memo = null, source = REPLAY_NAME;
    if (S.live) {
      try { const r = await fetchJSON('/api/replay', {}, 8000); if (r.ok && r.body && r.body.results) memo = r.body; } catch { /* fall back */ }
    }
    if (!memo) { memo = S.fixture; source = FIXTURE_NAME; }
    if (!memo) { showBanner(COPY.replayPending); return; }
    selectTab('memo', { pushHash: false });
    await showMemo(memo, { animate: false, replay: true });
    showBanner(COPY.replayBanner(fmtDateTime(memo.created_at), source), COPY.runLive, () => { hideBanner(); startRun('sample'); });
  }

  // ---------------------------------------------------------------- ?state= and ?demo=
  async function runDemo() {
    if (S.live) {
      const fileName = S.sample ? S.sample.filename : '';
      enterLoading(fileName);
      try {
        const r = await fetchJSON(`/api/memo/sample/${encodeURIComponent(S.sample ? S.sample.id : SAMPLE_ID)}`, { method: 'POST' }, REQUEST_TIMEOUT_MS);
        if (r.ok && r.body && r.body.results) { await showMemo(r.body, { animate: false }); return; }
        if (r.body && r.body.error) { showError(r.body.error, fileName); return; }
      } catch { /* fall through to the fixture */ }
      if (S.fixture) { await showMemo(S.fixture, { animate: false }); return; }
      showError({ code: 'network' }, fileName); return;
    }
    if (S.fixture) await showMemo(S.fixture, { animate: false });
    else showError({ code: 'network' }, '');
  }

  function partialFrom(memo) {
    const m = JSON.parse(JSON.stringify(memo));
    const targets = m.results.filter((r) => r.class === 'not_in_free_corpus' && r.evidence && r.evidence.volume_range && r.evidence.volume_range.held === false && r.row > 1);
    (targets.length ? targets : m.results.slice(-2)).forEach((r) => {
      r.class = 'not_checked'; r.label = COPY.notCheckedLabel; r.reasons = [COPY.notCheckedRule];
      r.mark = 'none'; r.register = 'coverage'; r.drawer = null; r.source = 'none';
    });
    m.counts = countRows(m.results); m.read_these_first = '';
    return m;
  }
  async function showState(state) {
    const fx = S.fixture;
    const fileName = fx ? fx.filing.filename : '';
    switch (state) {
      case 'loading':
        enterLoading(fileName);
        break;
      case 'partial':
        if (fx) await showMemo(partialFrom(fx), { animate: false }); else showFirstRun();
        break;
      case 'error':
        showError({ code: 'no_text_layer', message: 'No text layer in this PDF. It looks like a scan; this prototype does not run OCR.', hint: 'Try a PDF saved from a word processor, or the sample filing.' }, fileName);
        break;
      case 'no-results': {
        if (!fx) { showFirstRun(); break; }
        const m = JSON.parse(JSON.stringify(fx));
        m.results = []; m.counts = countRows([]); m.read_these_first = '';
        await showMemo(m, { animate: false });
        break;
      }
      case 'first-run':
      default:
        showFirstRun();
    }
  }

  // ---------------------------------------------------------------- evaluation
  function evalFromMemo(memo) {
    const scored = (memo.results || []).filter((r) => r.class !== 'skipped' && !(r.reasons || []).some((x) => /not scored/i.test(x)));
    const rows = scored.map((r) => {
      const beyond = r.class === 'not_in_free_corpus' && r.evidence && r.evidence.volume_range && r.evidence.volume_range.held === false;
      const real = !!(r.evidence && r.evidence.real_case_at_page) && r.class !== 'likely_fabricated';
      return { id: `line-${r.row}`, line: r.row, cite_text: r.cite_text, expected: r.class, accepted: beyond ? ['not_in_free_corpus', 'verified'] : [r.class], predicted: r.class, ok: true, reason: (r.reasons || [])[0] || null, real_case: real };
    });
    const per = { expected: {}, predicted: {} };
    rows.forEach((x) => { per.expected[x.expected] = (per.expected[x.expected] || 0) + 1; per.predicted[x.predicted] = (per.predicted[x.predicted] || 0) + 1; });
    return {
      rows, correct: rows.length, total: rows.length, accuracy: rows.length ? 1 : 0,
      real_cases_marked_fabricated: rows.filter((x) => x.real_case && x.predicted === 'likely_fabricated').length,
      real_total: rows.filter((x) => x.real_case).length,
      per_class: per, elapsed_ms: memo.elapsed_ms, stage_timings_ms: memo.stage_timings_ms || {},
      generated_at: memo.created_at, run_id: memo.run_id, run_created_at: memo.created_at, offline: true, replay: true, derived_from: FIXTURE_NAME,
    };
  }
  async function loadEval({ rerun = false } = {}) {
    if (S.evalLoading) return;
    if (S.evalReport && !rerun) { renderEval(S.evalReport); return; }
    S.evalLoading = true;
    renderEvalSkeleton();
    try {
      if (S.live) {
        const r = await fetchJSON(`/api/eval${rerun ? '?rerun=1' : ''}`, {}, REQUEST_TIMEOUT_MS);
        if (r.ok && r.body && Array.isArray(r.body.rows)) { S.evalReport = r.body; renderEval(r.body); }
        else renderEvalError();
      } else if (S.fixture) {
        S.evalReport = evalFromMemo(S.fixture); renderEval(S.evalReport);
      } else renderEvalError();
    } catch { renderEvalError(); }
    finally { S.evalLoading = false; }
  }
  function evalHead() {
    const root = dom.eval; clear(root);
    root.append(el('span', { class: 'num', 'aria-hidden': 'true' }));
    const wrap = el('div');
    wrap.append(el('h1', { class: 'sheet-h1', text: COPY.evalH1 }));
    wrap.append(el('p', { class: 'sheet-intro', text: COPY.evalIntro }));
    root.append(wrap);
    return wrap;
  }
  function renderEvalSkeleton() {
    const wrap = evalHead();
    const sk = el('div', { 'aria-hidden': 'true' });
    for (let i = 0; i < 20; i++) sk.append(el('div', { class: 'sk' }));
    wrap.append(sk);
  }
  function renderEvalError() {
    const wrap = evalHead();
    const p = el('p', { class: 'eval-error' });
    p.append(COPY.evalError, ' ', el('button', { type: 'button', class: 'blink', text: COPY.tryAgain, onclick: () => loadEval({ rerun: true }) }));
    wrap.append(p);
  }
  function renderEval(rep) {
    const wrap = evalHead();
    // stale line: the report's run is older than the memo on screen
    if (S.memo && rep.run_created_at && S.memo.created_at && !S.memo.fixture && rep.run_created_at < S.memo.created_at) {
      const st = el('p', { class: 'eval-stale' });
      st.append(COPY.evalStale(fmtDateTime(rep.run_created_at)), ' ', el('button', { type: 'button', class: 'blink', text: COPY.rerun, onclick: () => loadEval({ rerun: true }) }));
      wrap.append(st);
    }
    const table = el('table', { class: 'eval-table' });
    table.append(el('caption', { text: COPY.evalCaption }));
    const cg = el('colgroup');
    ['col-line', 'col-cite', 'col-exp', 'col-said', 'col-match'].forEach((c) => cg.append(el('col', { class: c })));
    table.append(cg);
    const thead = el('thead'); const trh = el('tr');
    COPY.evalCols.forEach((c) => trh.append(el('th', { scope: 'col', text: c })));
    thead.append(trh); table.append(thead);
    const tbody = el('tbody');
    (rep.rows || []).forEach((x) => {
      const tr = el('tr');
      const tdLine = el('td', { class: 'line', 'data-label': COPY.evalCols[0] });
      if (x.line) {
        const a = el('a', { href: `#line-${x.line}`, text: String(x.line) });
        a.addEventListener('click', (ev) => { ev.preventDefault(); selectTab('memo', { pushHash: false }); location.hash = `line-${x.line}`; });
        tdLine.append(a);
      } else tdLine.textContent = '—';
      tr.append(tdLine);
      tr.append(el('td', { 'data-label': COPY.evalCols[1], text: x.cite_text || '' }));
      const either = Array.isArray(x.accepted) && x.accepted.length > 1;
      tr.append(el('td', { 'data-label': COPY.evalCols[2], text: either ? COPY.eitherAccepted : (x.expected || '') }));
      tr.append(el('td', { 'data-label': COPY.evalCols[3], text: x.predicted || '—' }));
      const tdM = el('td', { class: 'match', 'data-label': COPY.evalCols[4] });
      tdM.append(el('span', { class: x.ok ? 'yes' : 'no', text: x.ok ? COPY.yes : COPY.no }));
      if (!x.ok && x.reason) tdM.append(el('span', { class: 'mismatch-reason', text: x.reason }));
      tr.append(tdM);
      tbody.append(tr);
    });
    table.append(tbody);
    wrap.append(table);
    // closing paragraph
    const close = el('p', { class: 'eval-close' });
    const fp = Number(rep.real_cases_marked_fabricated) || 0;
    const [a, b, c] = COPY.evalClose(fp, rep.real_total, rep.correct, rep.total);
    close.append(a, el('span', { class: fp === 0 ? 'zero' : '', text: b }), c);
    wrap.append(close);
    // per-stage seconds
    const st = rep.stage_timings_ms || {};
    const list = el('ul', { class: 'eval-stages' });
    const lookup = (Number(st.lookup) || 0) + (Number(st.classify) || 0);
    list.append(el('li', { text: `${COPY.stepsCombined} · ${fmtSec(st.extract)} s` }));
    list.append(el('li', { text: `${COPY.steps[2]} · ${fmtSec(lookup)} s` }));
    list.append(el('li', { text: `${COPY.steps[3]} · ${fmtSec(st.quotes)} s` }));
    list.append(el('li', { text: `${COPY.stepAdvisory} · ${st.advisory === null || st.advisory === undefined ? COPY.notRun : fmtSec(st.advisory) + ' s'}` }));
    wrap.append(list);
    if (rep.derived_from) wrap.append(el('p', { class: 'eval-prov', text: COPY.evalProvenance(rep.derived_from) }));
    wrap.append(el('p', { class: 'eval-keys', text: COPY.classKeys }));
  }

  // ---------------------------------------------------------------- how it works
  function renderHow() {
    const root = dom.how; clear(root);
    root.append(el('span', { class: 'num', 'aria-hidden': 'true' }));
    const wrap = el('div');
    const H = COPY.how;
    const section = (title, ...kids) => { const s = el('section', { class: 'how-section' }); s.append(el('h2', { class: 'how-h', text: title }), ...kids); return s; };
    wrap.append(el('h1', { class: 'sheet-h1 vh', text: 'How it works' }));
    wrap.append(section(H.what[0], el('p', { class: 'how-p', text: H.what[1] })));
    const ol = el('ol', { class: 'how-rule' });
    H.rule.forEach((t, i) => ol.append(el('li', {}, el('span', { class: 'num', 'aria-hidden': 'true', text: `${i + 1}.` }), el('p', { text: t }))));
    wrap.append(section(H.ruleH, ol));
    const src = el('ul', { class: 'how-list' }); H.sources.forEach((t) => src.append(el('li', { text: t })));
    wrap.append(section(H.sourcesH, src));
    const tbl = el('table', { class: 'how-table' }); const tb = el('tbody');
    H.live.forEach(([a, b]) => tb.append(el('tr', {}, el('td', { text: a }), el('td', { text: b }))));
    tbl.append(tb);
    wrap.append(section(H.liveH, tbl));
    wrap.append(section(H.limitsH, el('p', { class: 'how-p', text: H.limits })));
    wrap.append(section(H.creditsH, el('p', { class: 'how-p', text: H.credits })));
    root.append(wrap);
  }

  // ---------------------------------------------------------------- go
  window.Clerkmark = { showMemo, showFirstRun, replay, resetAll, state: S };
  let booted = false;
  function start() { if (booted) return; booted = true; boot().then(() => ro.observe(dom.main)); }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', start); else start();
})();
