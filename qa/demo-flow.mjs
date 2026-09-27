// demo-flow.mjs — the judged demo flow, three times in a row against a live server, with a reset between runs.
//   node qa/demo-flow.mjs http://localhost:8020        (DEMO_RUNS=n to change the count)
// One run: open ?demo=1 (populated memo) → Alt+Shift+R (clean S1) → "Use the sample filing" → status line → memo with
//   marks and stamp → [Show the page] on the Varghese row (line 6; the running head must name J.D. v. Azar) → Evaluation
//   tab → Alt+Shift+R again so the next run starts from a clean sheet.
// Every run's memo JSON counts (from the page and from the POST /api/memo/sample response) must be identical, and the
//   console must stay clean: page.on('console') and page.on('pageerror') are captured for the whole session.
// Stills for the fresh-eyes evaluator (viewport 1440×900, taken on run 1):
//   qa/out/still-1-demo-top-1440.png       ?demo=1 at the top of the sheet
//   qa/out/still-2-varghese-page-1440.png  line 6 expanded: the reporter page under the circled citation
//   qa/out/still-3-evaluation-1440.png     the Evaluation sheet
// Results go to qa/out/demo-flow.json; exit 1 on any failure.
import { chromium } from 'playwright';
import { mkdirSync, writeFileSync } from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const outDir = path.join(here, 'out');
mkdirSync(outDir, { recursive: true });
const base = (process.argv[2] || 'http://localhost:8020').replace(/\/$/, '');
const RUNS = Math.max(1, Number(process.env.DEMO_RUNS) || 3);
const VARGHESE = 6; // the row whose [Show the page] shows the page belonging to a different case (contract J1)

const failures = [];
const fail = (m) => { failures.push(m); console.log('FAIL', m); };
const ok = (m) => console.log('ok  ', m);
const assert = (c, m) => (c ? ok(m) : fail(m));
const ready = (p) => p.evaluate(() => document.documentElement.dataset.ready);
const waitReady = (p, want, timeout = 60000) => p.waitForFunction((w) => document.documentElement.dataset.ready === w, want, { timeout }).then(() => true).catch(() => false);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const browser = await chromium.launch();
const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'no-preference' });
const p = await ctx.newPage();
const consoleLog = [];
p.on('console', (m) => {
  const entry = { type: m.type(), text: m.text(), url: p.url() };
  consoleLog.push(entry);
  if (m.type() === 'error' && !/fonts\.(googleapis|gstatic)\.com/.test(entry.text)) fail(`console error at ${entry.url}: ${entry.text}`);
});
p.on('pageerror', (e) => fail(`page error at ${p.url()}: ${e.message}`));
const posts = []; // every POST /api/memo/sample answer seen by the page
p.on('response', async (res) => {
  if (!/\/api\/memo\/sample\//.test(res.url()) || res.request().method() !== 'POST') return;
  try { const j = await res.json(); posts.push({ status: res.status(), run_id: j.run_id, counts: j.counts, elapsed_ms: j.elapsed_ms, offline: !!j.offline }); }
  catch { posts.push({ status: res.status() }); }
});

const runs = [];
try {
  for (let i = 1; i <= RUNS; i++) {
    const run = { n: i };
    // 1. ?demo=1 paints the populated memo with the stamp
    await p.goto(`${base}/?demo=1`, { waitUntil: 'load' });
    assert(await waitReady(p, 'populated'), `run ${i}: ?demo=1 reaches the populated memo`);
    await p.evaluate(() => document.fonts.ready); await sleep(400);
    assert(!(await p.locator('#stamp').isHidden()), `run ${i}: the CHECKED stamp is on the demo memo`);
    run.demoCounts = await p.evaluate(() => window.Clerkmark.state.memo && window.Clerkmark.state.memo.counts);
    if (i === 1) { await p.evaluate(() => window.scrollTo(0, 0)); await sleep(100); await p.screenshot({ path: path.join(outDir, 'still-1-demo-top-1440.png'), fullPage: false }); }

    // 2. reset → clean S1
    await p.keyboard.press('Alt+Shift+R'); await sleep(200);
    assert((await ready(p)) === 'first-run', `run ${i}: Alt+Shift+R returns to first-run`);
    assert((await p.locator('#rows .row').count()) === 0 && (await p.locator('#stamp').isHidden()) && (await p.locator('#v-re').innerText()) === '________', `run ${i}: S1 is clean (no rows, no stamp, RE: blank)`);

    // 3. Use the sample filing → status line (four hollow steps, real timer) → memo
    const t0 = Date.now();
    await p.locator('#sample-btn').click();
    const sawLoading = await waitReady(p, 'loading', 3000);
    if (sawLoading) {
      const steps = await p.locator('#status .status-steps li').allInnerTexts();
      assert(steps.length === 4 && steps.every((s) => s.startsWith('○ ')), `run ${i}: status line shows four hollow steps`);
      assert((await p.locator('#sample-btn').count()) === 0 && (await p.locator('#drop-own').getAttribute('aria-disabled')) === 'true', `run ${i}: the drop target is gone and the primary button is aria-disabled while in flight`);
    } else ok(`run ${i}: the sample answered before the loading block could be inspected`);
    assert(await waitReady(p, 'populated'), `run ${i}: the sample run reaches the populated memo`);
    run.wallMs = Date.now() - t0;
    await sleep(300);
    const memo = await p.evaluate(() => { const m = window.Clerkmark.state.memo; return m ? { run_id: m.run_id, counts: m.counts, elapsed_ms: m.elapsed_ms, offline: !!m.offline, warnings: m.warnings || [], classes: (m.results || []).map((r) => r.class) } : null; });
    run.memo = memo;
    assert(memo && memo.counts && memo.counts.total > 0, `run ${i}: memo JSON on the page (${memo ? memo.counts.total : 0} rows, ${run.wallMs} ms wall including the choreography)`);
    run.lastRun = await p.evaluate(() => window.Clerkmark.state.lastRun);
    assert(run.lastRun && run.lastRun.marks > 0, `run ${i}: marks drew on (${run.lastRun ? run.lastRun.marks : 0} marks, animated=${run.lastRun && run.lastRun.animated})`);
    run.stamp = await p.evaluate(() => document.getElementById('stamp').textContent);
    assert(!(await p.locator('#stamp').isHidden()) && /^CHECKED/.test(run.stamp) && /\d+ citations in \d+\.\d s/.test(run.stamp), `run ${i}: stamp landed ("${run.stamp}")`);
    assert((await p.locator('#line-8 svg.mark path[data-mark="circle-all"]').count()) === 1, `run ${i}: line 8 (Miller) circled`);
    assert((await p.locator('#line-9 svg.mark path[data-mark="underline-pencil"]').count()) >= 1, `run ${i}: line 9 (Shaboon) pencil underline`);
    assert((await p.locator('#drop-own').getAttribute('aria-disabled')) === 'false', `run ${i}: the primary button is enabled again`);
    run.title = await p.title();

    // 4. [Show the page] on the Varghese row
    await p.locator(`#line-${VARGHESE} .blink`).click(); await sleep(400);
    run.runningHead = await p.locator(`#evidence-${VARGHESE} .running-head`).innerText().catch(() => '');
    run.pageMarker = await p.locator(`#evidence-${VARGHESE} .page-marker`).innerText().catch(() => '');
    assert(/J\.D\. v\. AZAR/i.test(run.runningHead) && run.pageMarker === '1339', `run ${i}: [Show the page] on line ${VARGHESE}: "${run.runningHead}" · page ${run.pageMarker}`);
    assert((await p.locator(`#line-${VARGHESE} .blink`).innerText()) === '[Hide the page]' && (await p.locator(`#line-${VARGHESE} .blink`).getAttribute('aria-expanded')) === 'true', `run ${i}: the link reads [Hide the page] and is aria-expanded`);
    if (i === 1) {
      await p.evaluate((n) => { const r = document.getElementById(`line-${n}`).getBoundingClientRect(); window.scrollBy(0, r.top - 96); }, VARGHESE);
      await sleep(250);
      await p.screenshot({ path: path.join(outDir, 'still-2-varghese-page-1440.png'), fullPage: false });
    }

    // 5. Evaluation tab
    await p.locator('#tab-evaluation').click();
    await p.waitForSelector('#eval table.eval-table tbody tr', { timeout: 60000 }).catch(() => {});
    run.evalRows = await p.locator('#eval table.eval-table tbody tr').count();
    run.evalClose = await p.locator('.eval-close').innerText().catch(() => '');
    const m = /^Real cases marked likely not real: (\d+) of (\d+)\. Correct classes: (\d+) of (\d+)\.$/.exec(run.evalClose);
    run.eval = m ? { fp: +m[1], real: +m[2], correct: +m[3], total: +m[4] } : null;
    assert(run.evalRows === 20 && run.eval && run.eval.total === 20, `run ${i}: Evaluation shows 20 rows ("${run.evalClose}")`);
    assert(run.eval && run.eval.fp === 0, `run ${i}: real cases marked likely not real = 0`);
    assert((await p.locator('#tab-evaluation').getAttribute('aria-selected')) === 'true' && (await p.locator('#panel-memo').isHidden()), `run ${i}: the Evaluation sheet is the selected tab`);
    if (i === 1) { await p.evaluate(() => window.scrollTo(0, 0)); await sleep(100); await p.screenshot({ path: path.join(outDir, 'still-3-evaluation-1440.png'), fullPage: false }); }

    // 6. reset between runs → clean S1 on the Memo tab
    await p.keyboard.press('Alt+Shift+R'); await sleep(200);
    assert((await ready(p)) === 'first-run' && (await p.locator('#tab-memo').getAttribute('aria-selected')) === 'true' && (await p.locator('#rows .row').count()) === 0 && (await p.locator('#banner').isHidden() || /^Offline/.test(await p.locator('#banner').innerText())), `run ${i}: reset after the run leaves a clean S1 on the Memo tab`);
    runs.push(run);
  }

  // the same classes every run
  const countKeys = runs.map((r) => JSON.stringify(r.memo && r.memo.counts));
  assert(countKeys.every((k) => k === countKeys[0]), `all ${RUNS} runs produced the same memo counts: ${countKeys[0]}`);
  const classKeys = runs.map((r) => JSON.stringify(r.memo && r.memo.classes));
  assert(classKeys.every((k) => k === classKeys[0]), `all ${RUNS} runs produced the same class per row`);
  const demoKeys = runs.map((r) => JSON.stringify(r.demoCounts));
  assert(demoKeys.every((k) => k === countKeys[0]), `?demo=1 painted the same counts as the button runs`);
  const evalKeys = runs.map((r) => JSON.stringify(r.eval));
  assert(evalKeys.every((k) => k === evalKeys[0]), `all ${RUNS} runs scored the same on the Evaluation sheet: ${evalKeys[0]}`);
  const postKeys = posts.map((x) => JSON.stringify(x.counts));
  assert(posts.length >= RUNS * 2 && posts.every((x) => x.status === 200) && postKeys.every((k) => k === postKeys[0]), `${posts.length} POST /api/memo/sample answers, all 200 with identical counts`);
  const consoleErrors = consoleLog.filter((e) => e.type === 'error');
  assert(consoleErrors.length === 0, `console: ${consoleErrors.length} error(s) across ${consoleLog.length} message(s)`);
} catch (e) { fail(`demo flow aborted: ${e.message}`); }
finally { await ctx.close(); await browser.close(); }

const report = { base, runs, posts, console: { total: consoleLog.length, errors: consoleLog.filter((e) => e.type === 'error'), other: consoleLog.filter((e) => e.type !== 'error').slice(0, 20) }, failures, at: new Date().toISOString() };
writeFileSync(path.join(outDir, 'demo-flow.json'), JSON.stringify(report, null, 2));
console.log(`\n${RUNS} run(s): ` + runs.map((r) => `#${r.n} ${r.memo ? r.memo.counts.total : '?'} rows / ${r.wallMs} ms wall / stamp "${(r.stamp || '').replace(/\s+/g, ' ').trim()}"`).join(' | '));
console.log(failures.length ? `${failures.length} failure(s)` : 'all checks passed');
process.exit(failures.length ? 1 : 0);
