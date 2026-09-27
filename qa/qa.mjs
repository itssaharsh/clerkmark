// qa.mjs — Playwright + axe loop for the Clerkmark memo page.
//   node qa/qa.mjs --static web --port 8765      (serves web/ with python3 -m http.server, unless the port already answers)
//   node qa/qa.mjs http://localhost:8000          (a live base URL)
// Screenshots go to qa/out/; every axe violation, console error and DOM assertion failure is printed; exit 1 on any.
// Against a live server it also forces the three envelopes the UI must render (a "Truncated:" warning, 413 too_large,
// 429 rate_limited) and screenshots them; the 429 is primed for real, so it runs last (it throttles this client for a minute).
import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';
import { spawn } from 'node:child_process';
import { mkdirSync, writeFileSync } from 'node:fs';
import http from 'node:http';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, '..');
const outDir = path.join(here, 'out');
mkdirSync(outDir, { recursive: true });

// ---------------------------------------------------------------- args
const argv = process.argv.slice(2);
let staticDir = null, port = 8765, base = null;
for (let i = 0; i < argv.length; i++) {
  if (argv[i] === '--static') staticDir = argv[++i];
  else if (argv[i] === '--port') port = Number(argv[++i]);
  else if (/^https?:\/\//.test(argv[i])) base = argv[i].replace(/\/$/, '');
}
if (!base && !staticDir) { console.error('usage: node qa/qa.mjs --static web --port 8765 | node qa/qa.mjs http://host:port'); process.exit(2); }
if (!base) base = `http://127.0.0.1:${port}`;

const ping = (url) => new Promise((resolve) => {
  const req = http.get(url, (res) => { res.resume(); resolve(res.statusCode); });
  req.on('error', () => resolve(0)); req.setTimeout(1500, () => { req.destroy(); resolve(0); });
});

let server = null;
async function ensureServer() {
  if (!staticDir) return;
  if (await ping(base + '/')) { console.log(`[qa] ${base} already answers; not starting a server`); return; }
  const dir = path.resolve(root, staticDir);
  server = spawn('python3', ['-m', 'http.server', String(port), '--bind', '127.0.0.1', '--directory', dir], { stdio: ['ignore', 'ignore', 'pipe'] });
  server.stderr.on('data', () => {});
  for (let i = 0; i < 50; i++) { if (await ping(base + '/')) break; await new Promise((r) => setTimeout(r, 100)); }
  if (!(await ping(base + '/'))) throw new Error('static server did not start on ' + base);
  console.log(`[qa] serving ${dir} at ${base}`);
}
function stopServer() { if (server && !server.killed) { server.kill('SIGTERM'); server = null; } }
process.on('exit', stopServer); process.on('SIGINT', () => { stopServer(); process.exit(130); }); process.on('SIGTERM', () => { stopServer(); process.exit(143); });

// ---------------------------------------------------------------- plan
const widths = [320, 390, 1024, 1440];
const states = ['first-run', 'loading', 'partial', 'error', 'no-results'];
const shots = [
  { name: 'demo', url: '/?demo=1' },
  ...states.map((s) => ({ name: `state-${s}`, url: `/?state=${s}` })),
];
const axeOnly1440 = [
  { name: 'demo-line-6', url: '/?demo=1#line-6' },
  { name: 'demo-line-23', url: '/?demo=1#line-23' },
  { name: 'demo-evaluation', url: '/?demo=1#evaluation' },
  { name: 'demo-how', url: '/?demo=1#how' },
];
const AXE_TAGS = ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa', 'wcag22aa'];

const failures = [];
const fail = (msg) => { failures.push(msg); console.log('FAIL', msg); };
const ok = (msg) => console.log('ok  ', msg);
const assert = (cond, msg) => (cond ? ok(msg) : fail(msg));

// A live ?demo=1 runs the sample (seconds), and app.js marks the page ready at every state change, so 'loading'
// is not a settled state — except on ?state=loading, where the loading block is what we screenshot.
async function settle(p, { loading = false } = {}) {
  await p.waitForFunction((l) => { const r = document.documentElement.dataset.ready; return l ? !!r : !!(r && r !== 'loading'); }, loading, { timeout: 60000 }).catch(() => {});
  await p.evaluate(() => document.fonts.ready);
  await p.waitForTimeout(400);
}
async function open(p, url, w) {
  await p.setViewportSize({ width: w, height: w < 500 ? 844 : (w < 1200 ? 768 : 900) });
  await p.goto(base + url, { waitUntil: 'load' });
  await settle(p, { loading: /[?&]state=loading/.test(url) });
}
const viewportH = (w) => (w < 500 ? 844 : (w < 1200 ? 768 : 900));
// Console capture: any console.error or uncaught exception fails the run. Resource-load errors are counted too,
// except font CDN fetches (the page has system fallbacks; an offline QA box must not fail on them) and, while the
// forced-envelope section deliberately provokes 4xx answers, the "Failed to load resource" lines those produce.
let allowResourceErrors = false;
function watchConsole(p, label) {
  p.on('pageerror', (e) => fail(`${label}: page error: ${e.message}`));
  p.on('console', (m) => {
    if (m.type() !== 'error') return;
    const text = m.text();
    if (/fonts\.(googleapis|gstatic)\.com/.test(text)) return;
    if (allowResourceErrors && /Failed to load resource/.test(text)) return;
    fail(`${label}: console error at ${p.url()}: ${text}`);
  });
}
async function axe(p, label) {
  const { violations } = await new AxeBuilder({ page: p }).withTags(AXE_TAGS).analyze();
  if (!violations.length) ok(`axe ${label}: 0 violations`);
  for (const v of violations) {
    fail(`axe ${label}: ${v.id} (${v.impact}) x${v.nodes.length} — ${v.help}`);
    v.nodes.slice(0, 3).forEach((n) => console.log('       ', n.target.join(' '), '|', (n.failureSummary || '').split('\n')[1] || ''));
  }
}

// ---------------------------------------------------------------- run
await ensureServer();
const proxy = process.env.HTTPS_PROXY;
const browser = await chromium.launch(proxy ? { proxy: { server: proxy } } : {});
try {
  for (const reduced of [false, true]) {
    const ctx = await browser.newContext({ reducedMotion: reduced ? 'reduce' : 'no-preference', ignoreHTTPSErrors: !!proxy });
    const p = await ctx.newPage();
    watchConsole(p, reduced ? 'shots(rm)' : 'shots');
    for (const s of shots) for (const w of widths) {
      const file = `${s.name}-${w}${reduced ? '-rm' : ''}.png`;
      try {
        await open(p, s.url, w);
        await p.screenshot({ path: path.join(outDir, file), fullPage: true });
        const sw = await p.evaluate(() => document.documentElement.scrollWidth);
        assert(sw <= w, `${file}: no horizontal scroll (scrollWidth ${sw} ≤ ${w})`);
        if (w < 500) {
          // one filled primary action, rendered and whole inside the viewport's width (B10 320 px check); at 390×844 it must
          // also sit inside the first viewport without scrolling (A8 gate 4; UI-SPEC §13 gate 4 names 390×844, not 320).
          const box = await p.evaluate(() => { const bs = Array.from(document.querySelectorAll('.button-primary')).filter((x) => x.offsetParent !== null); const b = bs[0]; if (!b) return null; const r = b.getBoundingClientRect(); return { n: bs.length, left: r.left, right: r.right, width: r.width, height: r.height, top: r.top + window.scrollY, bottom: r.bottom + window.scrollY, text: b.textContent.trim() }; });
          const label = box ? box.text : 'none';
          assert(box && box.n === 1 && box.width > 0 && box.height >= 40 && box.left >= 0 && box.right <= w, `${file}: one visible primary action "${label}" within the ${w} px width${box ? ` (${Math.round(box.left)}–${Math.round(box.right)}, ${Math.round(box.height)} px tall)` : ''}`);
          if (w === 390) assert(box && box.bottom <= viewportH(w), `${file}: primary action "${label}" inside the first 390×844 viewport (bottom ${box ? Math.round(box.bottom) : '-'} ≤ ${viewportH(w)})`);
        }
        if (w === 1440 && !reduced) await axe(p, `${s.name}@1440`);
      } catch (e) { fail(`${file}: ${e.message}`); }
    }
    if (!reduced) {
      for (const s of axeOnly1440) {
        try {
          await open(p, s.url, 1440);
          await p.screenshot({ path: path.join(outDir, `${s.name}-1440.png`), fullPage: true });
          await axe(p, `${s.name}@1440`);
        } catch (e) { fail(`${s.name}: ${e.message}`); }
      }
    }
    await ctx.close();
  }

  // ---------------------------------------------------------------- DOM assertions (AC-8, AC-9, AC-10)
  const ctx = await browser.newContext({ reducedMotion: 'no-preference' });
  const p = await ctx.newPage();
  watchConsole(p, 'assertions');
  const live = (await ping(base + '/api/health')) === 200;
  console.log(`[qa] ${base} is ${live ? 'a live API' : 'static (no /api/health)'}`);
  try {

  await open(p, '/?demo=1', 1440);
  const title = await p.title();
  assert(/^Memo · \d+ citations · (\d+|none) likely not real · Clerkmark$/.test(title), `demo title "${title}"`);
  assert((await p.locator('#rows .row').count()) > 0, 'demo: rows rendered');
  assert((await p.locator('#line-8 svg.mark path[data-mark="circle-all"]').count()) === 1, 'line 8 (Miller) carries a circle-all mark path');
  const circleCovers = await p.evaluate(() => {
    const li = document.getElementById('line-8');
    const path = li.querySelector('svg.mark path[data-mark="circle-all"]').getBoundingClientRect();
    const first = Array.from(li.querySelector('.citespan').getClientRects()).sort((a, b) => a.top - b.top)[0];
    const lineRects = Array.from(li.querySelector('.citespan').getClientRects()).filter((r) => Math.abs(r.top - first.top) < 4);
    const right = Math.max(...lineRects.map((r) => r.right));
    return path.left <= first.left && path.right >= right - 1;
  });
  assert(circleCovers, 'line 8 circle encloses the whole first line of the citation');
  assert((await p.locator('#line-9 svg.mark path[data-mark="underline-pencil"]').count()) >= 1, 'line 9 (Shaboon) carries a pencil underline');
  assert((await p.locator('#line-8 .label').innerText()) === 'Likely not a real case.', 'line 8 label is the §9 string');
  assert((await p.locator('#line-9 .label').innerText()) === 'Not in the free library. Check Westlaw or Lexis.', 'line 9 label is the §9 string');
  assert(((await p.locator('#line-8 .rule').innerText()) || '').length > 0, 'line 8 has a rule sentence');
  assert((await p.locator('#line-15 svg.mark path[data-mark="strike-correct"]').count()) === 1, 'line 15 (Zicherman 230) strike-correct mark');
  assert((await p.evaluate(() => { const t = document.querySelector('#line-15 svg.mark text'); return t && t.textContent; })) === '217', 'line 15 correct page written above the struck number');
  assert((await p.locator('#line-20 svg.mark path[data-mark="circle-reporter"]').count()) === 1, 'line 20 (Fed. Air Rptr. 3d) circle-reporter mark');
  assert((await p.locator('#line-18 svg.mark path[data-mark="underline-quote"]').count()) >= 1, 'line 18 (Iqbal) quote underline');
  const stampText = await p.evaluate(() => document.getElementById('stamp').textContent);
  assert(stampText.includes('CHECKED'), 'stamp reads CHECKED');
  assert(/\d+ citations in \d+\.\d s/.test(stampText), `stamp carries count and seconds ("${stampText}")`);
  assert((await p.locator('#v-re').innerText()).includes('pages'), 'RE: carries the page count');
  assert((await p.locator('#disclaimer').innerText()) === 'Triage aid. Not a finding. Verify flagged rows before relying on them.', 'disclaimer text');
  assert((await p.locator('#foot-inner').innerText()).startsWith('Read these first:'), 'foot paragraph present');
  assert((await p.locator('#foot-inner a').count()) > 0, 'foot paragraph has count links');
  assert((await p.locator('.button-primary:visible').count()) === 1, 'exactly one filled button on S3');
  assert((await p.locator('[role="status"]').count()) === 1, 'exactly one role=status region');
  // marks never overflow the sheet
  const overflow = await p.evaluate(() => {
    const sheet = document.getElementById('main').getBoundingClientRect();
    return Array.from(document.querySelectorAll('svg.mark path')).filter((el) => { const r = el.getBoundingClientRect(); return r.left < sheet.left - 1 || r.right > sheet.right + 1; }).length;
  });
  assert(overflow === 0, `no mark overflows the sheet (${overflow} did)`);

  // [Show the page] on line 6 → running head names J.D. v. Azar
  await p.locator('#line-6 .blink').click();
  await p.waitForTimeout(350);
  const rh6 = await p.locator('#evidence-6 .running-head').innerText();
  assert(/J\.D\. v\. AZAR/i.test(rh6), `line 6 drawer running head names the case at the page: "${rh6}"`);
  assert((await p.locator('#evidence-6 .page-marker').innerText()) === '1339', 'line 6 page marker is the cited page');
  assert((await p.locator('#line-6 .blink').getAttribute('aria-expanded')) === 'true', 'line 6 link aria-expanded=true');
  await p.screenshot({ path: path.join(outDir, 'demo-line-6-open-1440.png'), fullPage: false });
  // Esc closes and returns focus
  await p.keyboard.press('Escape');
  await p.waitForTimeout(250);
  assert((await p.locator('#line-6 .blink').getAttribute('aria-expanded')) === 'false', 'Esc closes the drawer');
  assert(await p.evaluate(() => document.activeElement && document.activeElement.closest('#line-6') !== null), 'Esc returns focus to the row link');
  // shelf on line 23
  await p.locator('#line-23 .blink').click();
  await p.waitForTimeout(350);
  assert((await p.locator('#evidence-23 .strip[role="img"]').count()) === 1, 'line 23 opens the shelf strip');
  const shelfLabel = await p.locator('#evidence-23 .strip-label').innerText();
  assert(/volumes 1–572/.test(shelfLabel), `shelf label from evidence: "${shelfLabel}"`);
  // metadata-only drawer on line 7
  await p.locator('#line-7 .blink').click();
  await p.waitForTimeout(350);
  assert((await p.locator('#evidence-7 .excerpt-note').innerText()) === 'Opinion text not loaded in this build.', 'line 7 metadata-only drawer');
  assert((await p.locator('#line-23 .blink').getAttribute('aria-expanded')) === 'false', 'opening line 7 closed line 23 (one panel at a time)');

  // < and & in a citation render as text, never markup
  const injected = await p.evaluate(async () => {
    const memo = JSON.parse(JSON.stringify(window.Clerkmark.state.memo));
    memo.results = memo.results.slice(0, 2);
    memo.results[0].cite_text = 'Doe <b>v.</b> Roe & Co., <img src=x onerror="window.__pwned=1"> 1 F.3d 1';
    memo.results[0].evidence.running_head = '<i>head</i> & tail';
    memo.counts = null;
    await window.Clerkmark.showMemo(memo, { animate: false });
    const li = document.getElementById('line-1');
    return { text: li.querySelector('.citetext').textContent, hasMarkup: !!li.querySelector('.citetext b, .citetext img, .citetext i'), pwned: !!window.__pwned };
  });
  assert(injected.text.includes('<b>v.</b>') && injected.text.includes('&'), 'citation text with < and & rendered as text');
  assert(!injected.hasMarkup && !injected.pwned, 'no markup created from citation text');

  // ---------------------------------------------------------------- states (AC-9)
  await open(p, '/?state=loading', 1440);
  const steps = await p.locator('#status .status-steps li').allInnerTexts();
  assert(steps.length === 4 && steps.every((s) => s.startsWith('○ ')), `loading: four hollow steps (${steps.join(' | ')})`);
  const e1 = await p.locator('#elapsed').innerText(); await p.waitForTimeout(400); const e2 = await p.locator('#elapsed').innerText();
  assert(/^Elapsed \d+\.\d s$/.test(e1) && e1 !== e2, `loading: real elapsed timer ("${e1}" → "${e2}")`);
  assert(!/\d/.test(steps.join('')), 'loading: no counts beside the steps');
  assert(/^Reading .+ · Clerkmark$/.test(await p.title()), 'loading title');

  await open(p, '/?state=error', 1440);
  const err = await p.locator('#drop-note').innerText();
  assert(err.startsWith('No text layer in this PDF.'), `error: §9 sentence ("${err.slice(0, 40)}…")`);
  assert(/\.pdf/.test(await p.locator('#v-re').innerText()), 'error: RE: keeps the file name');
  assert((await p.locator('.button-primary:visible').count()) === 1, 'error: the drop target (one filled button) is kept');
  assert(/^Error: /.test(await p.title()), 'error title prefixed');

  await open(p, '/?state=partial', 1440);
  assert(/did not answer for \d+ citations \(timed out\)\./.test(await p.locator('#notice-inner').innerText()), 'partial: notice with the count');
  assert((await p.locator('#notice-inner .blink').innerText()).startsWith('[Retry '), 'partial: [Retry n citations]');
  assert((await p.locator('.row[data-class="not_checked"] .label').first().innerText()) === 'Could not reach the free library.', 'partial: pencil note on unresolved rows');
  assert(/\d+ unanswered/.test(await p.evaluate(() => document.getElementById('stamp').textContent)), 'partial: stamp notes the unanswered count');
  assert(/not answered yet\.$/.test(await p.locator('#foot-inner').innerText()), 'partial: foot appends "not answered yet."');

  await open(p, '/?state=no-results', 1440);
  assert(/^No case citations found in \d+ pages\./.test(await p.locator('.noresults').innerText()), 'no-results paragraph');
  assert((await p.locator('.noresults .blink').innerText()) === '[Drop another PDF]', 'no-results keeps a drop target');

  await open(p, '/?state=first-run', 1440);
  assert((await p.locator('#drop .button-primary').innerText()).trim() === 'Choose a PDF', 'first-run: Choose a PDF');
  assert((await p.locator('#sample-btn').innerText()) === 'Use the sample filing', 'first-run: sample button');
  assert((await p.locator('#v-re').innerText()) === '________', 'first-run: RE: blank');
  assert((await p.title()) === 'Clerkmark · citation memo', 'first-run title');

  // ---------------------------------------------------------------- keyboard golden path + shortcuts (AC-10)
  await open(p, '/', 1440);
  let hops = 0, focused = '';
  while (hops < 12) { await p.keyboard.press('Tab'); hops++; focused = await p.evaluate(() => document.activeElement && document.activeElement.id); if (focused === 'sample-btn') break; }
  assert(focused === 'sample-btn', `keyboard: Tab reaches the sample button in ${hops} hops`);
  await p.keyboard.press('Enter');
  await p.waitForFunction(() => document.documentElement.dataset.ready === 'populated', null, { timeout: 15000 }).catch(() => {});
  assert(await p.evaluate(() => document.documentElement.dataset.ready === 'populated'), 'keyboard: Enter on the sample runs it to a populated memo');
  assert(await p.evaluate(() => !document.getElementById('stamp').hidden), 'keyboard: stamp landed after the run');
  const lastRun = await p.evaluate(() => window.Clerkmark.state.lastRun);
  assert(lastRun && lastRun.animated && lastRun.marks > 0 && lastRun.marksMs > 0, `choreography: rows revealed and marks drew on after a live run (${JSON.stringify(lastRun)})`);
  await p.screenshot({ path: path.join(outDir, 'after-run-1440.png'), fullPage: true });
  // Tab to the first row link, Enter opens, Esc closes and returns focus
  hops = 0; let onLink = false;
  while (hops < 40) { await p.keyboard.press('Tab'); hops++; onLink = await p.evaluate(() => document.activeElement && document.activeElement.classList.contains('blink') && !!document.activeElement.closest('.row')); if (onLink) break; }
  assert(onLink, `keyboard: Tab reaches a row link (${hops} hops)`);
  const rowId = await p.evaluate(() => document.activeElement.closest('.row').id);
  await p.keyboard.press('Enter'); await p.waitForTimeout(300);
  assert(await p.evaluate((id) => document.querySelector(`#${id} .blink`).getAttribute('aria-expanded') === 'true', rowId), `keyboard: Enter opens ${rowId}'s drawer`);
  assert(await p.evaluate(() => document.activeElement && document.activeElement.classList.contains('running-head')), 'keyboard: focus moved to the running head');
  await p.keyboard.press('Escape'); await p.waitForTimeout(250);
  assert(await p.evaluate((id) => document.activeElement === document.querySelector(`#${id} .blink`), rowId), 'keyboard: Esc returns focus to the link');
  // tabs with arrows
  await p.locator('#tab-memo').focus(); await p.keyboard.press('ArrowRight'); await p.waitForTimeout(200);
  assert((await p.locator('#tab-evaluation').getAttribute('aria-selected')) === 'true', 'tabs: ArrowRight selects Evaluation');
  await p.waitForSelector('#eval table.eval-table', { timeout: 10000 }).catch(() => {});
  assert((await p.locator('#eval table.eval-table tbody tr').count()) > 0, 'evaluation: table rows rendered');
  assert(/^Real cases marked likely not real: \d+ of \d+\. Correct classes: \d+ of \d+\.$/.test(await p.locator('.eval-close').innerText()), 'evaluation: closing line');
  await p.screenshot({ path: path.join(outDir, 'evaluation-1440.png'), fullPage: true });
  await p.keyboard.press('ArrowRight'); await p.waitForTimeout(200);
  assert((await p.locator('#tab-how').getAttribute('aria-selected')) === 'true', 'tabs: ArrowRight selects How it works');
  assert((await p.locator('#how .how-rule li').count()) === 9, 'how it works: the nine-step rule');
  await p.screenshot({ path: path.join(outDir, 'how-1440.png'), fullPage: true });
  await p.keyboard.press('Home'); await p.waitForTimeout(150);
  assert((await p.locator('#tab-memo').getAttribute('aria-selected')) === 'true', 'tabs: Home returns to Memo');
  // Alt+Shift+P → replay banner + REPLAY stamp
  await p.keyboard.press('Alt+Shift+P'); await p.waitForTimeout(800);
  const bannerText = await p.locator('#banner').innerText();
  assert(/^Replay · run of .+ from .+\. Marks and seconds are from that run\./.test(bannerText), 'Alt+Shift+P: replay banner');
  if (live) assert(/ from seed\/replay\.json\./.test(bannerText), `Alt+Shift+P (live): the banner names the recorded run GET /api/replay served ("${bannerText.slice(0, 60)}…")`);
  assert((await p.evaluate(() => document.getElementById('stamp').textContent)).startsWith('REPLAY'), 'Alt+Shift+P: REPLAY stamp');
  await p.screenshot({ path: path.join(outDir, 'replay-1440.png'), fullPage: false });
  // Alt+Shift+R → first-run, three times
  for (let i = 0; i < 3; i++) { await p.keyboard.press('Alt+Shift+R'); await p.waitForTimeout(150); }
  assert(await p.evaluate(() => document.documentElement.dataset.ready === 'first-run'), 'Alt+Shift+R: back to first-run');
  const s1Banner = (await p.locator('#banner').isHidden()) ? '' : await p.locator('#banner').innerText();
  // a live server in CITEMEMO_OFFLINE mode keeps its standing "Offline · …" banner on S1 (app.js hideBanner); nothing else may remain
  assert((await p.locator('#rows .row').count()) === 0 && (await p.locator('#stamp').isHidden()) && (s1Banner === '' || /^Offline · /.test(s1Banner)), `Alt+Shift+R: clean S1 (no rows, no stamp, banner ${s1Banner ? `"${s1Banner.slice(0, 40)}…"` : 'hidden'})`);
  await open(p, '/?reset=1', 1440);
  assert(await p.evaluate(() => document.documentElement.dataset.ready === 'first-run'), '?reset=1: first-run');

  // ---------------------------------------------------------------- print
  await open(p, '/?demo=1', 1440);
  await p.emulateMedia({ media: 'print' });
  const pdf = await p.pdf({ format: 'Letter', printBackground: true });
  writeFileSync(path.join(outDir, 'print-demo.pdf'), pdf);
  const pages = (pdf.toString('latin1').match(/\/Type\s*\/Page[^s]/g) || []).length;
  assert(pages === 1, `print: the sample memo with panels closed fits one letter page (${pages} page(s)) → qa/out/print-demo.pdf`);
  await p.emulateMedia({ media: 'screen' });

  // ---------------------------------------------------------------- forced envelopes (live only): the strings T07 added must render
  if (live) {
    allowResourceErrors = true;
    const samplePdf = path.join(root, 'seed', 'sample-motion.pdf');
    // (a) "Truncated:" warning → the notice under the rows. The sample memo is fetched for real and the warning line is
    //     appended in the wording of citememo/limits.py (cap_citations), so the whole render path runs on a real memo.
    const TRUNC = 'Truncated: the filing has 312 full citations; only the first 250 were checked. Run the rest separately.';
    await p.route('**/api/memo/sample/**', async (route) => {
      const res = await route.fetch(); const json = await res.json();
      json.warnings = [...(json.warnings || []), TRUNC];
      await route.fulfill({ response: res, json });
    });
    await open(p, '/?demo=1', 1440);
    await p.unroute('**/api/memo/sample/**');
    const noticeText = await p.locator('#notice-inner').innerText().catch(() => '');
    assert(await p.locator('#notice').isVisible() && noticeText.includes(TRUNC), `forced Truncated: the warning renders in the notice ("${noticeText.slice(0, 60)}…")`);
    assert((await p.locator('#rows .row').count()) > 0 && !(await p.locator('#stamp').isHidden()), 'forced Truncated: the memo, rows and stamp still render around the warning');
    await p.locator('#notice').scrollIntoViewIfNeeded(); await p.waitForTimeout(150);
    await p.screenshot({ path: path.join(outDir, 'forced-truncated-1440.png'), fullPage: false });
    // (b) 413 too_large — the client blocks > 4 MB before upload, so the server's own envelope is provoked by replaying
    //     the upload with a body over the limit (the middleware answers on Content-Length) and handing that answer to the page.
    let served413 = null;
    await p.route('**/api/memo', async (route) => {
      const res = await route.fetch({ method: 'POST', postData: Buffer.alloc(4 * 1024 * 1024 + 1, 0x20), headers: { 'content-type': 'application/octet-stream' } });
      served413 = res.status();
      await route.fulfill({ response: res });
    });
    await open(p, '/?demo=1', 1440);
    await p.setInputFiles('#file-own', samplePdf);
    await p.waitForFunction(() => document.documentElement.dataset.ready === 'error', null, { timeout: 15000 }).catch(() => {});
    await p.unroute('**/api/memo');
    const note413 = await p.locator('#drop-note').innerText().catch(() => '');
    assert(served413 === 413, `forced 413: the server answered ${served413} to a body over 4 MB`);
    assert(/^This PDF is larger than 4 MB\. This prototype reads files up to 4 MB\. /.test(note413), `forced 413: the §9 sentence with the contract's 4 MB renders in ink under the drop target ("${note413.slice(0, 70)}…")`);
    assert(/sample-motion\.pdf/.test(await p.locator('#v-re').innerText()) && (await p.locator('.button-primary:visible').count()) === 1, 'forced 413: RE: keeps the file name and the drop target is kept');
    assert((await p.title()) === 'Error: File too large · Clerkmark', `forced 413: title "${await p.title()}"`);
    await p.screenshot({ path: path.join(outDir, 'forced-413-1440.png'), fullPage: false });
    // (c) 429 rate_limited — for real: ten attempts at POST /api/memo from this address inside a minute (each counted at
    //     arrival, whatever the body), then the eleventh, a real upload through the page's own button. Runs last.
    await open(p, '/?demo=1', 1440);
    // Attempts are counted per address over a sliding minute, and the 413 replay above (or an earlier qa run inside the
    // minute) already used some, so prime until the limiter answers 429 (at most 11 attempts), then upload through the page.
    const primed = await p.evaluate(async () => { const codes = []; for (let i = 0; i < 11; i++) { const c = (await fetch('/api/memo', { method: 'POST' })).status; codes.push(c); if (c === 429) break; } return codes; });
    await p.setInputFiles('#file-own', samplePdf);
    await p.waitForFunction(() => document.documentElement.dataset.ready === 'error', null, { timeout: 15000 }).catch(() => {});
    const note429 = await p.locator('#drop-note').innerText().catch(() => '');
    assert(primed[primed.length - 1] === 429 && primed.slice(0, -1).every((c) => c !== 429) && primed.length <= 11, `forced 429: the limiter throttles within 10 attempts a minute (primed ${primed.join(',')}; the 413 replay counted as one)`);
    assert(/^Too many checks from this address: this prototype runs 10 memos per minute\. .*Your file is still selected\.$/.test(note429), `forced 429: the rate-limit sentence, its hint and "Your file is still selected." render ("${note429.slice(0, 70)}…")`);
    assert(/sample-motion\.pdf/.test(await p.locator('#v-re').innerText()), 'forced 429: RE: keeps the file name');
    assert((await p.title()) === 'Error: Too many checks · Clerkmark', `forced 429: title "${await p.title()}"`);
    await p.screenshot({ path: path.join(outDir, 'forced-429-1440.png'), fullPage: false });
    allowResourceErrors = false;
  } else console.log('[qa] static mode: forced-envelope checks (Truncated, 413, 429) need a live server; skipped');
  } catch (e) { fail(`assertion block aborted: ${e.message}`); }
  await ctx.close();
} finally {
  await browser.close();
  stopServer();
}

console.log(failures.length ? `\n${failures.length} failure(s)` : '\nall checks passed');
process.exit(failures.length ? 1 : 0);
