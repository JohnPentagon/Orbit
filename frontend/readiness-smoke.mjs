// Diagnostic UI regression: 409 and version mismatch are intercepted fixtures.
import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1100}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
let older=false;
await page.route('**/api/projects/harbour/read-connections',async route=>{
 if(route.request().method()==='GET'){const response=await route.fetch();const data=await response.json();await route.fulfill({json:{...data,live_reads_enabled:true,...(older?{server_version:'0.4.0'}:{})}});}else await route.continue();
});
await page.route('**/api/projects/harbour/read-connections/*/read',route=>route.fulfill({status:409,json:{detail:{code:'vendor_settings_unconfirmed',message:'This saved connection has not confirmed vendor settings.',next_action:'Edit setup on this same card and save.'}}}));
try{
 await page.goto('http://127.0.0.1:8000');
 await page.getByLabel('Choose a synthetic identity').selectOption('north-owner');
 await page.getByRole('button',{name:'Enter workspace'}).click();
 await page.getByRole('button',{name:'Read connections',exact:true}).click();
 await page.getByLabel('Read provider').selectOption('redeye');
 await page.getByLabel('Test connection name').fill('Diagnostic UI fixture '+Date.now());
 await page.getByRole('button',{name:'Create connection',exact:true}).click();
 await page.getByText('Configuration saved as unverified. No vendor request occurred.').waitFor();
 const card=page.locator('.read-connection').last();
 await card.getByRole('button',{name:'Set test credential',exact:true}).click();
 await page.getByLabel(/Approved test API key/).fill('synthetic-ui-diagnostic-key');
 await card.getByRole('button',{name:'Store test credential',exact:true}).click();
 await page.getByText('Encrypted credential replaced. No authentication request was made.').waitFor();
 await card.getByRole('button',{name:'Read artefacts',exact:true}).click();
 const alert=card.getByRole('alert');
 await alert.waitFor();
 assert.match(await alert.innerText(),/vendor_settings_unconfirmed/);
 assert.match(await alert.innerText(),/same card/);
 assert.match(await card.innerText(),/Saved confirmations: vendor settings NOT confirmed/);
 older=true;
 await page.reload();
 await page.getByRole('button',{name:'Read connections',exact:true}).click();
 await page.getByText(/The running backend is 0.4.0/).waitFor();
 assert.deepEqual(errors,[]);
 console.log('Readiness UI smoke passed: saved settings, card-local structured 409, and stale-backend version warning; no vendor calls.');
}finally{await browser.close();}
