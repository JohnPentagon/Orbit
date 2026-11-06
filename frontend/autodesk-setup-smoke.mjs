// UI-only auth/discovery fixtures. No vendor OAuth endpoint is contacted.
import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1100}});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
let app=null,selected=null;
await page.route('**/api/projects/harbour/read-connections',async route=>{
 if(route.request().method()==='GET'){const response=await route.fetch();const data=await response.json();await route.fulfill({json:{...data,live_reads_enabled:true}});}else await route.continue();
});
await page.route(/\/api\/projects\/harbour\/read-connections\/[^/]+\/autodesk(?:\/.*)?$/,async route=>{
 const request=route.request(),url=new URL(request.url()),body=request.postDataJSON();
 let data={};
 if(url.pathname.endsWith('/autodesk')&&request.method()==='GET')data={callback_url:'http://127.0.0.1:8000/api/autodesk/callback',app,expires:null,renewal_available:false,scope:'data:read'};
 else if(url.pathname.endsWith('/autodesk')&&request.method()==='PUT'){app={client_id:body.client_id,mode:body.mode};data={configured:true};}
 else if(url.pathname.endsWith('/connect'))data={connected:true};
 else if(url.pathname.endsWith('/discover')){const key={hubs:'hub',projects:'project',folders:'folder'}[body.kind];data={resources:[{id:'SYNTHETIC-'+key,label:'Fixture '+key,kind:body.kind}],coverage:'UI fixture only'};}
 else if(url.pathname.endsWith('/selection')){selected=body;data={saved:true};}
 else throw new Error('Unexpected mocked OAuth UI request');
 await route.fulfill({json:data});
});
try{
 await page.goto('http://127.0.0.1:8000');
 await page.getByLabel('Choose a synthetic identity').selectOption('north-owner');
 await page.getByRole('button',{name:'Enter workspace'}).click();
 await page.getByRole('button',{name:'Read connections',exact:true}).click();
 const name='Autodesk dropdown UI fixture '+Date.now();
 await page.getByLabel('Test connection name').fill(name);
 await page.getByLabel('Non-secret evidence / administrator reference').fill('Synthetic UI test only');
 await page.getByLabel('I have confirmed the vendor host and authentication settings').check();
 await page.getByLabel('This account and resource scope are authorised for testing').check();
 await page.getByRole('button',{name:'Save unverified connection',exact:true}).click();
 const row=page.locator('.read-connection').filter({has:page.getByRole('heading',{name,exact:true})});
 await row.getByLabel('APS client ID',{exact:true}).fill('synthetic-client');
 await row.getByLabel('APS client secret',{exact:true}).fill('synthetic-ui-secret');
 await row.getByLabel('Autodesk authorisation mode').selectOption('two_legged');
 await row.getByRole('button',{name:'Save APS application',exact:true}).click();
 await row.getByRole('button',{name:'Connect application',exact:true}).click();
 await row.getByText('Application token obtained. Load accessible hubs to verify resource access.').waitFor();
 await row.getByRole('button',{name:'Load accessible hubs',exact:true}).click();
 await row.getByLabel('Discovered Autodesk hub').selectOption('SYNTHETIC-hub');
 await row.getByLabel('Discovered Autodesk project').selectOption('SYNTHETIC-project');
 await row.getByLabel('Discovered Autodesk folder').selectOption('SYNTHETIC-folder');
 await row.getByRole('button',{name:'Use selected project and folder',exact:true}).click();
 await row.getByText('Verified selection saved. IDs are retained automatically; no document imported.').waitFor();
 assert.deepEqual(selected,{hub:'SYNTHETIC-hub',project:'SYNTHETIC-project',folder:'SYNTHETIC-folder'});
 await page.setViewportSize({width:390,height:844});
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 assert.deepEqual(errors,[]);
 console.log('Autodesk UI fixture smoke passed: app settings, app-only connect, cascading named hub/project/folder choices and selection; vendor requests intercepted, no live auth verified.');
}finally{await browser.close();}
