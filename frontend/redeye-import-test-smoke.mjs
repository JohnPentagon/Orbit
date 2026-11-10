// Isolated transport fixture only: never sends a real vendor HTTP request.
import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const base=process.env.ORBIT_TEST_URL||'http://127.0.0.1:8003';
const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
async function load(){await page.getByRole('button',{name:'Load metadata fields',exact:true}).click();await page.getByText('Metadata loaded. No write sent.',{exact:true}).waitFor();}
async function save(){await page.getByRole('button',{name:'Preview metadata update',exact:true}).click();await page.getByText('Before/after preview ready. No write sent.',{exact:true}).waitFor();const button=page.getByRole('button',{name:'Confirm and save to RedEye',exact:true});assert.equal(await button.isDisabled(),true);await page.getByLabel('Confirm metadata change',{exact:true}).check();await page.getByLabel('Confirm metadata revision',{exact:true}).check();await button.click();await page.getByText('Selected field and all preserved metadata matched.',{exact:true}).waitFor();}
try{
 await page.goto(base);await page.getByLabel('Choose a synthetic identity').selectOption('north-owner');await page.getByRole('button',{name:'Enter workspace'}).click();
 await page.getByRole('button',{name:'RedEye metadata',exact:true}).click();
 await page.getByLabel('Metadata connection',{exact:true}).selectOption('11111111-2222-3333-4444-555555555555');
 await page.getByLabel('Metadata artefact ID',{exact:true}).fill('777');await load();
 await page.getByLabel('Metadata field',{exact:true}).selectOption('10');
 await page.getByRole('button',{name:'Verify selected field',exact:true}).click();await page.getByText('Current value retrieved',{exact:true}).waitFor();
 await page.getByLabel('Compare expected metadata value',{exact:true}).check();await page.getByLabel('Metadata value',{exact:true}).fill('keep exactly');
 await page.getByRole('button',{name:'Verify selected field',exact:true}).click();await page.getByText('Expected value matches',{exact:true}).waitFor();
 await page.getByLabel('Metadata value',{exact:true}).fill('different');await page.getByRole('button',{name:'Verify selected field',exact:true}).click();await page.getByText('Expected value differs',{exact:true}).waitFor();
 await page.getByLabel('Metadata action',{exact:true}).selectOption('update');await page.getByLabel('Metadata value',{exact:true}).fill('User chosen new value');
 await page.getByRole('button',{name:'Preview metadata update',exact:true}).click();await page.getByRole('alert').getByText('Select Replace existing value to update a populated field.',{exact:true}).waitFor();
 await page.getByLabel('Replace existing metadata value',{exact:true}).check();await save();
 assert.equal(await page.getByRole('button',{name:'Approve RedEye test',exact:true}).count(),0);
 let ctx=await (await page.request.get(base+'/api/projects/harbour/redeye-metadata')).json();const first=ctx.updates[0];assert.equal(first.status,'verified');assert.equal(first.plan.source,null);
 const replay=await page.request.post(base+'/api/projects/harbour/redeye-metadata/'+first.id+'/execute',{data:{digest:first.digest,confirmed:true,current_revision_confirmed:true}});assert.equal((await replay.json()).status,'verified');
 await load();await page.getByLabel('Metadata field',{exact:true}).selectOption('20');
 await page.getByLabel('Metadata value format',{exact:true}).selectOption('json');await page.getByLabel('Metadata value',{exact:true}).fill('["first", "second"]');await save();
 ctx=await (await page.request.get(base+'/api/projects/harbour/redeye-metadata')).json();assert.equal(ctx.updates.filter(j=>j.status==='verified').length,2);
 await load();await page.getByLabel('Metadata field',{exact:true}).selectOption('20');await page.getByLabel('Metadata action',{exact:true}).selectOption('verify');
 await page.getByLabel('Metadata value',{exact:true}).fill('["first", "second"]');await page.getByRole('button',{name:'Verify selected field',exact:true}).click();await page.getByText('Expected value matches',{exact:true}).waitFor();
 await page.reload();await page.getByRole('button',{name:'RedEye metadata',exact:true}).click();await page.locator('.parameter-job').first().waitFor();
 await page.getByLabel('Test identity',{exact:true}).selectOption('north-viewer');await page.getByText('viewer · north-viewer',{exact:true}).waitFor();
 assert.equal(await page.getByRole('button',{name:'Load metadata fields',exact:true}).count(),0);
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
 await page.screenshot({path:'/workspace/Orbit/.local/screenshots/redeye-metadata-mobile.png',fullPage:true});assert.deepEqual(errors,[]);
 console.log('Metadata browser UAT passed: inspect any field, fresh verify/match/mismatch, explicit overwrite, no role switching/arming, two simulated updates on the same artefact, multi-values, read-back, replay, reload, viewer/mobile. No customer writes.');
}finally{await browser.close();}
