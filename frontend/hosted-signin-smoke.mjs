import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1000}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 const base=process.env.ORBIT_TEST_URL||'http://127.0.0.1:8010';await page.goto(base);
 await page.getByRole('heading',{name:'ORBIT UAT',exact:true}).waitFor();
 assert.equal(await page.getByRole('link',{name:'Sign in with Microsoft',exact:true}).getAttribute('href'),'/auth/login');
 assert.equal(await page.getByRole('button',{name:'Open workspace',exact:true}).count(),0);
 assert.equal(await page.getByRole('button',{name:'Create workspace',exact:true}).count(),0);
 const health=await (await page.request.get(base+'/api/health')).json();assert.equal(health.runtime,'ASP.NET Core 10');
 assert.equal((await page.request.get(base+'/api/workspace')).status(),401);
 assert.equal((await page.request.get(base+'/api/local/status')).status(),501);
 assert.deepEqual(errors,[]);
 await page.screenshot({path:'/workspace/Orbit/.local/screenshots/hosted-dotnet-signin.png',fullPage:true});
 console.log('Native .NET signed-out portal passed: Microsoft sign-in, no local owner-opening form, anonymous workspace denial. Live Entra sign-in is not tested.');
}finally{await browser.close();}
