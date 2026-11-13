import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const mappingName='Cross-platform verification '+Date.now();
const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto('http://127.0.0.1:8005');await page.getByRole('button',{name:'Open workspace',exact:true}).click();
 await page.getByRole('heading',{name:'Connection health',exact:true}).waitFor();
 await page.locator('.portal-nav').getByRole('button',{name:'Mappings',exact:true}).click();await page.getByRole('button',{name:'Create mapping profile',exact:true}).click();
 const sides=page.locator('.mapping-connection');
 await page.getByLabel('Source connection',{exact:true}).selectOption({label:'Project RedEye · RedEye'});
 await sides.nth(0).getByRole('button',{name:/Load parameters|Refresh parameters/,exact:true}).click();

 await page.getByLabel('Target connection',{exact:true}).selectOption({label:'Project SQL · SQL Server'});

 await page.locator('.mapping-matching>summary').click();
 await page.getByLabel('Document identifier on A',{exact:true}).selectOption('number');
 await page.getByLabel('Document identifier on B',{exact:true}).selectOption('DocumentNumber');
 await page.getByLabel('Profile name',{exact:true}).fill(mappingName);
 await page.getByLabel('Source parameter 1',{exact:true}).selectOption('title');
 await page.getByLabel('Target parameter 1',{exact:true}).selectOption('Title');
 await page.getByRole('button',{name:'Save profile',exact:true}).click();await page.locator('.analysis-saved').filter({hasText:mappingName}).getByRole('button',{name:'Compare data',exact:true}).click();
 await page.getByRole('heading',{name:mappingName,exact:true,level:2}).waitFor();assert.equal(await page.locator('[role=alert]').count(),0);
 await page.screenshot({path:'/workspace/Orbit/.local/screenshots/portal-comparison.png',fullPage:true});
 await page.locator('.portal-nav').getByRole('button',{name:'Overview',exact:true}).click();await page.getByRole('heading',{name:'Data validation',exact:true}).waitFor();
 await page.locator('.portal-stat').filter({hasText:'fresh reports'}).getByText(/^[1-9][0-9]*$/).waitFor();assert.deepEqual(errors,[]);console.log('Shared mapping, simulated metadata capture, SQL sample reuse, comparison and validation dashboard passed.');
}finally{await browser.close();}
