// Uses an isolated local test DB seeded with backend.test_parameter_imports.SCHEMA.
// Imports execute against real SQLite test registers; no vendor HTTP is permitted.
import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
const base=process.env.ORBIT_TEST_URL||'http://127.0.0.1:8001';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1100},acceptDownloads:true}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
async function role(id){await page.getByLabel('Test identity',{exact:true}).selectOption(id);await page.getByText(id.split('-').slice(1).join('-')+' · '+id,{exact:true}).waitFor();}
try{
 await page.goto(base);await page.getByLabel('Choose a synthetic identity').selectOption('north-owner');await page.getByRole('button',{name:'Enter workspace'}).click();
 await page.getByRole('button',{name:'Parameter imports',exact:true}).click();
 await page.getByLabel('Parameter destination',{exact:true}).selectOption('synthetic:north-redeye');
 await page.getByLabel('Required parameter 0',{exact:true}).check();
 await page.getByLabel('Set parameter value 0',{exact:true}).check();
 await page.getByLabel('Parameter value 0',{exact:true}).fill('60');
 await page.getByLabel('Parameter document C-001',{exact:true}).check();
 await page.getByRole('button',{name:'Preview parameter import',exact:true}).click();
 await page.getByText('Parameter import preview saved. No fields or values have been changed.',{exact:true}).waitFor();
 let job=page.locator('.parameter-job').first();assert.match(await job.innerText(),/create · General.Rating/);
 assert.equal(await job.getByRole('button',{name:'Apply local parameter import',exact:true}).count(),0);
 await role('north-approver');job=page.locator('.parameter-job').first();
 await job.getByRole('button',{name:'Approve parameter import',exact:true}).click();
 await page.getByText('Exact parameter preview approved. Execution is a separate action.',{exact:true}).waitFor();
 await role('north-owner');job=page.locator('.parameter-job').first();
 await job.getByRole('button',{name:'Apply local parameter import',exact:true}).click();
 await page.getByText('Local test parameters imported and read back. Zero remote platform writes.',{exact:true}).waitFor();
 assert.match(await job.innerText(),/Read-back verified · 1 definitions created · 1 values written/);
 await page.getByLabel('Parameter destination',{exact:true}).selectOption('synthetic:north-redeye');
 await page.getByRole('button',{name:'Check local parameter quality',exact:true}).click();
 await page.getByText('3 parameter quality issues',{exact:true}).waitFor();
 // Reuse the exact definition, preserve the existing value by default.
 await page.getByLabel('Required parameter 0',{exact:true}).check();
 await page.getByLabel('Set parameter value 0',{exact:true}).check();await page.getByLabel('Parameter value 0',{exact:true}).fill('30');
 await page.getByLabel('Parameter document C-001',{exact:true}).check();
 await page.getByRole('button',{name:'Preview parameter import',exact:true}).click();
 await page.getByText('Parameter import preview saved. No fields or values have been changed.',{exact:true}).waitFor();
 job=page.locator('.parameter-job').first();assert.match(await job.innerText(),/skip_existing/);
 const downloadPromise=page.waitForEvent('download');await job.getByRole('button',{name:'Download review package',exact:true}).click();
 const download=await downloadPromise;const stream=await download.createReadStream();let raw='';for await(const chunk of stream)raw+=chunk.toString();
 assert.equal(JSON.parse(raw).format,'ORBIT_PARAMETER_IMPORT_REVIEW_V1');assert.equal(JSON.parse(raw).vendor_native_format,false);
 await job.getByRole('button',{name:'Cancel parameter import',exact:true}).click();await page.getByText('Parameter import cancelled.',{exact:true}).waitFor();
 await page.reload();await page.getByRole('button',{name:'Parameter imports',exact:true}).click();await page.getByLabel('Parameter destination',{exact:true}).selectOption('synthetic:north-redeye');
 await page.getByText('1 imported local definitions · 1 stored document values',{exact:true}).waitFor();
 await role('north-viewer');assert.equal(await page.getByRole('button',{name:'Preview parameter import',exact:true}).count(),0);
 assert.equal(await page.getByRole('button',{name:'Approve parameter import',exact:true}).count(),0);
 await page.setViewportSize({width:390,height:844});assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
 await page.screenshot({path:'/workspace/Orbit/.local/screenshots/parameter-imports-mobile.png',fullPage:true});
 assert.deepEqual(errors,[]);
 console.log('Parameter import browser passed: real local definition/value writes, separate approval, read-back, required-value quality findings, preserved-value preview, cancellation, package download, reload and viewer/mobile checks; no vendor HTTP.');
}finally{await browser.close();}
