import { chromium } from 'playwright';
const base = process.argv[2] || 'http://localhost:8060';
const b = await chromium.launch();
for (const [w,h,name,url] of [[1440,900,'cover-1440','/'],[390,844,'cover-390','/'],[1440,900,'compact-1440','/?demo=1'],[320,640,'cover-320','/']]) {
  const p = await b.newPage({ viewport:{width:w,height:h}, deviceScaleFactor:1, reducedMotion:'reduce' });
  const errs=[]; p.on('console', m=>m.type()==='error'&&errs.push(m.text().slice(0,120)));
  await p.goto(base+url, {waitUntil:'load'});
  await p.waitForTimeout(url.includes('demo')?9000:2000);
  await p.screenshot({path:`qa/out/${name}.png`, fullPage: !url.includes('demo')});
  const sw = await p.evaluate(()=>document.documentElement.scrollWidth);
  console.log(name.padEnd(14), 'scrollW', String(sw).padEnd(6), 'vw', String(w).padEnd(6), errs.length?('ERRORS '+errs.join('|')):'console clean');
  await p.close();
}
await b.close();
