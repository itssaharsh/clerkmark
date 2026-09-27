// qa/make_crops.mjs — real UI crops for the cover sheet (node qa/make_crops.mjs http://localhost:8050)
import { chromium } from 'playwright';
const base = process.argv[2] || 'http://localhost:8050';
const out = 'web/static/cover';
const b = await chromium.launch();
const ctx = await b.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2, reducedMotion: 'reduce' });
const p = await ctx.newPage();
await p.goto(base + '/?demo=1', { waitUntil: 'load' });
await p.waitForSelector('#stamp:not([hidden])', { timeout: 60000 });
await p.waitForSelector('#line-9');
await p.waitForTimeout(1200);
const shot = async (name, clip) => p.screenshot({ path: `${out}/${name}.jpg`, type: 'jpeg', quality: 88, clip });
const box = async (sel) => (await p.locator(sel).first().boundingBox());
const pad = (r, x = 12, y = 10) => ({ x: Math.max(0, r.x - x), y: Math.max(0, r.y - y), width: r.width + 2 * x, height: r.height + 2 * y });
// step 3 first (no drawer open yet): the likely-not-real row beside the not-held row
await p.locator('#line-8').scrollIntoViewIfNeeded();
const a = await box('#line-8'), c = await box('#line-9');
await shot('step-3-rows', pad({ x: a.x, y: a.y, width: Math.max(a.width, c.width), height: c.y + c.height - a.y }));
// step 1: the memo heading with the stamp
await p.evaluate(() => window.scrollTo(0, 0));
const h = await box('#panel-memo .heading-grid');
await shot('step-1-heading', pad(h));
// step 2: the reporter page under the Varghese row
await p.locator('#line-6').scrollIntoViewIfNeeded();
await p.locator('#line-6').getByText('[Show the page]').click();
await p.waitForSelector('#line-6 >> text=[Hide the page]');
await p.waitForTimeout(600);
await p.locator('#line-6').scrollIntoViewIfNeeded();
await shot('step-2-page', pad(await box('#line-6')));
await b.close();
console.log('crops written to', out);
