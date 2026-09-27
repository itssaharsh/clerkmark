// T09 browser check: HTML in a filing renders as text, never markup; the page's CSP breaks nothing.
// Usage: node tests/browser/xss_no_dialog.mjs http://127.0.0.1:8030   (a running `uvicorn main:app`)
// 1) ?demo=1 and a sample run under the server's CSP: 0 CSP violations, 0 console errors.
// 2) The sample response rewritten so every text field the memo prints carries <img src=x onerror=alert(1)>:
//    no dialog opens, no <img src="x"> exists in the DOM, the payload is visible as text.
// 3) A real upload whose file name is the payload: same assertions on the server's own answer.
// Exit 1 on any failure.
import { chromium } from 'playwright';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const BASE = (process.argv[2] || 'http://127.0.0.1:8030').replace(/\/$/, '');
const PAYLOAD = '<img src=x onerror=alert(1)>';
const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
let failures = 0;
const ok = (m) => console.log(`PASS ${m}`);
const fail = (m) => { failures += 1; console.log(`FAIL ${m}`); };

function poison(memo) {
  const m = structuredClone(memo);
  m.filing.filename = `${PAYLOAD}.pdf`;
  m.warnings = [...(m.warnings || []), `Note ${PAYLOAD}`];
  for (const r of m.results) {
    r.cite_text = `${PAYLOAD} ${r.cite_text}`;
    r.reasons = r.reasons.map((s) => `${s} ${PAYLOAD}`);
    if (r.citation) { r.citation.plaintiff = PAYLOAD; }
    if (r.quote_check && r.quote_check.quote) r.quote_check.quote = `${PAYLOAD} ${r.quote_check.quote}`;
    const e = r.evidence || {};
    if (e.running_head) e.running_head = `${e.running_head} ${PAYLOAD}`;
    if (e.excerpt) e.excerpt = `${PAYLOAD} ${e.excerpt}`;
    if (e.real_case_at_page) e.real_case_at_page.name = `${PAYLOAD} ${e.real_case_at_page.name}`;
  }
  return m;
}

async function page(browser, label) {
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 1000 } });
  const p = await ctx.newPage();
  const log = { dialogs: [], csp: [], errors: [] };
  p.on('dialog', async (d) => { log.dialogs.push(d.message()); await d.dismiss(); });
  p.on('console', (msg) => {
    const t = msg.text();
    if (/Content Security Policy|Refused to/i.test(t)) log.csp.push(t);
    else if (msg.type() === 'error' && !/fonts\.(googleapis|gstatic)\.com|ERR_NAME_NOT_RESOLVED|ERR_INTERNET_DISCONNECTED/.test(t)) log.errors.push(t);
  });
  p.on('pageerror', (e) => log.errors.push(String(e)));
  return { ctx, p, log, label };
}

async function assertInert({ p, log, label }) {
  await p.waitForTimeout(800);
  const imgs = await p.locator('img[src="x"]').count();
  const text = await p.evaluate(() => document.body.innerText);
  const executed = await p.evaluate(() => window.__xss === true);
  if (log.dialogs.length) fail(`${label}: dialog opened (${log.dialogs.join(' | ')})`); else ok(`${label}: no dialog`);
  if (imgs || executed) fail(`${label}: payload became markup (${imgs} <img src=x>)`); else ok(`${label}: no <img src=x> in the DOM`);
  if (!text.includes(PAYLOAD)) fail(`${label}: payload text not visible`); else ok(`${label}: payload shown as text`);
  if (log.csp.length) fail(`${label}: CSP violations: ${log.csp.slice(0, 3).join(' | ')}`); else ok(`${label}: 0 CSP violations`);
  if (log.errors.length) fail(`${label}: console errors: ${log.errors.slice(0, 3).join(' | ')}`); else ok(`${label}: 0 console errors`);
}

const browser = await chromium.launch();
try {
  // 0) the header is really there
  const head = await fetch(`${BASE}/`);
  const csp = head.headers.get('content-security-policy') || '';
  if (!/script-src 'self'/.test(csp)) fail(`GET / has no script-src 'self' CSP (${csp})`); else ok('GET / carries the CSP');

  // 1) the page works under the CSP
  {
    const s = await page(browser, 'demo=1 under CSP');
    await s.p.goto(`${BASE}/?demo=1`, { waitUntil: 'networkidle' });
    await s.p.waitForSelector('#rows li', { timeout: 15000 });
    const rows = await s.p.locator('#rows li').count();
    rows >= 20 ? ok(`${s.label}: ${rows} rows`) : fail(`${s.label}: ${rows} rows`);
    const btn = s.p.getByRole('button', { name: '[Show the page]' }).first();
    if (await btn.count()) { await btn.click(); await s.p.waitForTimeout(500); ok(`${s.label}: drawer opened`); }
    for (const tab of ['#tab-evaluation', '#tab-how', '#tab-memo']) { await s.p.click(tab); await s.p.waitForTimeout(300); }
    if (s.log.csp.length) fail(`${s.label}: CSP violations: ${s.log.csp.slice(0, 3).join(' | ')}`); else ok(`${s.label}: 0 CSP violations`);
    if (s.log.errors.length) fail(`${s.label}: console errors: ${s.log.errors.slice(0, 3).join(' | ')}`); else ok(`${s.label}: 0 console errors`);
    await s.ctx.close();
  }

  // 2) every printed field poisoned
  {
    const real = await (await fetch(`${BASE}/api/memo/sample/sample-motion`, { method: 'POST' })).json();
    const s = await page(browser, 'poisoned memo');
    await s.p.route('**/api/memo/sample/**', (route) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(poison(real)) }));
    await s.p.goto(`${BASE}/`, { waitUntil: 'networkidle' });
    await s.p.evaluate(() => { window.alert = () => { window.__xss = true; }; });
    await s.p.getByRole('button', { name: 'Use the sample filing' }).first().click();
    await s.p.waitForSelector('#rows li', { timeout: 20000 });
    const btns = s.p.getByRole('button', { name: '[Show the page]' });
    const n = Math.min(await btns.count(), 3);
    for (let i = 0; i < n; i++) { await btns.nth(i).click(); await s.p.waitForTimeout(300); }
    await assertInert(s);
    await s.ctx.close();
  }

  // 3) the server's own answer to an upload named with the payload
  {
    const s = await page(browser, 'upload named with the payload');
    await s.p.goto(`${BASE}/`, { waitUntil: 'networkidle' });
    const input = s.p.locator('input[type=file]').first();
    await input.setInputFiles({ name: `${PAYLOAD}.pdf`, mimeType: 'application/pdf', buffer: readFileSync(path.join(ROOT, 'seed', 'sample-motion.pdf')) });
    await s.p.waitForSelector('#rows li', { timeout: 30000 });
    await assertInert(s);
    await s.ctx.close();
  }
} finally {
  await browser.close();
}
console.log(failures ? `FAIL (${failures})` : 'PASS');
process.exit(failures ? 1 : 0);
