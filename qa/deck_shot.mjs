import { chromium } from 'playwright';
const b = await chromium.launch();
const ctx = await b.newContext({ viewport:{width:1600,height:900}, deviceScaleFactor:1, reducedMotion:'reduce' });
const p = await ctx.newPage();
const errs=[]; p.on('console', m=>m.type()==='error'&&errs.push(m.text().slice(0,100)));
p.on('requestfailed', r=>errs.push('FAILED '+r.url().slice(-40)));
for (const n of [1,2,3,4,6,7]) {
  await p.goto('http://localhost:8070/#' + n, {waitUntil:'load'});
  await p.reload({waitUntil:'load'});   // same-document hash change would not re-run the script
  await p.waitForTimeout(700);
  await p.screenshot({path:`qa/out/deck-${n}.png`});
}
console.log(errs.length ? 'ERRORS: '+[...new Set(errs)].join(' | ') : 'deck clean, 9 slides');
await b.close();
