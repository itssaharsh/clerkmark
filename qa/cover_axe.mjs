import { chromium } from 'playwright';
import AxeBuilder from '@axe-core/playwright';
const base = process.argv[2] || 'http://localhost:8060';
const b = await chromium.launch();
let bad = 0;
for (const [w, url] of [[1440,'/'],[390,'/'],[320,'/'],[1440,'/?demo=1']]) {
  const ctx = await b.newContext({ viewport:{width:w,height:900} });
  const p = await ctx.newPage();
  await p.goto(base+url, {waitUntil:'load'}); await p.waitForTimeout(url.includes('demo')?9000:2000);
  const { violations } = await new AxeBuilder({ page: p })
    .withTags(['wcag2a','wcag2aa','wcag21a','wcag21aa','wcag22aa']).analyze();
  violations.forEach(v => { bad++; console.log(w, url, 'VIOLATION', v.id, v.nodes.length, v.nodes[0]?.target); });
  console.log(String(w).padEnd(6), url.padEnd(10), violations.length ? 'violations '+violations.length : 'axe clean');
  await ctx.close();
}
await b.close();
process.exit(bad ? 1 : 0);
