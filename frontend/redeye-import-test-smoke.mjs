// Requires an isolated pilot fixture server. The only RedEye POST is simulated.
import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const base=process.env.ORBIT_TEST_URL||'http://127.0.0.1:8003';
const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
async function role(id){await page.getByLabel('Test identity',{exact:true}).selectOption(id);await page.getByText(id.split('-')[1]+' · '+id,{exact:true}).waitFor();}
try{
 await page.goto(base);await page.getByLabel('Choose a synthetic identity').selectOption('north-owner');await page.getByRole('button',{name:'Enter workspace'}).click();
 await page.getByRole('button',{name:'RedEye import test',exact:true}).click();
 await page.getByLabel('RedEye pilot connection',{exact:true}).selectOption('11111111-2222-3333-4444-555555555555');
 await page.getByLabel('RedEye pilot artefact ID',{exact:true}).fill('777');
 await page.getByRole('button',{name:'Inspect RedEye target',exact:true}).click();await page.getByText('Artefact, keys and revision history inspected. No write sent.',{exact:true}).waitFor();
 await page.getByLabel('RedEye pilot bSDD property',{exact:true}).selectOption({label:'Rating · String'});
 await page.getByLabel('RedEye pilot metadata key',{exact:true}).selectOption('20');
 await page.getByLabel('RedEye pilot typed value',{exact:true}).fill('"ORBIT_TEST"');
 await page.getByLabel('RedEye pilot evidence',{exact:true}).fill('Isolated browser fixture; no customer network');
 for(const id of ['disposable_isolated_target','current_approved_revision_confirmed','metadata_contract_confirmed','mapping_type_units_confirmed'])await page.getByLabel(id,{exact:true}).check();
 await page.getByRole('button',{name:'Prepare RedEye write preview',exact:true}).click();await page.getByText('Real RedEye test preview saved. No write has been sent.',{exact:true}).waitFor();
 let job=page.locator('.parameter-job').first();assert.match(await job.innerText(),/Pilot Rating ← Rating/);
 assert.equal(await job.getByRole('button',{name:'Write this one RedEye test value',exact:true}).count(),0);
 await role('north-approver');job=page.locator('.parameter-job').first();await job.getByRole('button',{name:'Approve RedEye test',exact:true}).click();await page.getByText('Test approved; no write sent.',{exact:true}).waitFor();
 await role('north-owner');job=page.locator('.parameter-job').first();
 const button=job.getByRole('button',{name:'Write this one RedEye test value',exact:true});assert.equal(await button.isDisabled(),true);
 await job.getByRole('textbox').fill('WRITE 777');await button.click();
 await page.getByText('RedEye test value and preserved metadata verified by read-back.',{exact:true}).waitFor();assert.match(await job.innerText(),/POST HTTP 200 was observed/);
 const context=await (await page.request.get(base+'/api/projects/harbour/redeye-import-tests')).json();const test=context.tests[0];
 const repeat=await page.request.post(base+'/api/projects/harbour/redeye-import-tests/'+test.id+'/execute',{data:{digest:test.digest,confirmation:'WRITE 777'}});assert.equal((await repeat.json()).status,'verified');
 await page.reload();await page.getByRole('button',{name:'RedEye import test',exact:true}).click();await page.locator('.parameter-job').first().getByText('Read-back verified',{exact:true}).waitFor();
 await role('north-viewer');assert.equal(await page.getByRole('button',{name:'Inspect RedEye target',exact:true}).count(),0);
 assert.equal(await page.getByRole('button',{name:'Write this one RedEye test value',exact:true}).count(),0);
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
 await page.screenshot({path:'/workspace/Orbit/.local/screenshots/redeye-import-test-mobile.png',fullPage:true});
 assert.deepEqual(errors,[]);console.log('RedEye pilot browser passed: real app inspection/preview, separate approval, exact typed target, simulated POST/read-back, replay protection, reload and viewer/mobile boundaries. No customer write or real vendor HTTP.');
}finally{await browser.close();}
