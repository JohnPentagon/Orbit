import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const mappingName='Cross-platform verification '+Date.now();
const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
try{
 await page.goto('http://127.0.0.1:8005');await page.getByRole('button',{name:'Open workspace',exact:true}).click();
 await page.getByRole('heading',{name:'Connection health',exact:true}).waitFor();
 await page.locator('.portal-nav').getByRole('button',{name:'Mappings',exact:true}).click();await page.getByRole('button',{name:'Create mapping',exact:true}).click();
 const sides=page.locator('.analysis-sides>div');
 await sides.nth(0).getByLabel('Connection',{exact:true}).selectOption({label:'Project RedEye · redeye'});
 await sides.nth(0).getByRole('button',{name:'Read sample',exact:true}).click();
 await sides.nth(0).locator('label').filter({hasText:/^Matching key/}).locator('select').selectOption('number');
 await sides.nth(1).getByLabel('Connection',{exact:true}).selectOption({label:'Project SQL · sql'});
 await sides.nth(1).getByLabel('Captured dataset',{exact:true}).selectOption({index:1});
 const choices=await sides.nth(1).locator('label').filter({hasText:/^Matching key/}).locator('select').locator('option').allTextContents();
 await sides.nth(1).locator('label').filter({hasText:/^Matching key/}).locator('select').selectOption(choices[1]);
 await page.getByLabel('Mapping name',{exact:true}).fill(mappingName);
 await page.locator('.analysis-rule').locator('label').filter({hasText:/^Source field/}).locator('select').selectOption('title');
 await page.locator('.analysis-rule').locator('label').filter({hasText:/^Target field/}).locator('select').selectOption('Title');
 await page.getByRole('button',{name:'Save mapping',exact:true}).click();await page.locator('.analysis-saved').filter({hasText:mappingName}).getByRole('button',{name:'Compare data',exact:true}).click();
 await page.getByRole('heading',{name:mappingName,exact:true,level:2}).waitFor();assert.equal(await page.locator('[role=alert]').count(),0);
 await page.screenshot({path:'/workspace/Orbit/.local/screenshots/portal-comparison.png',fullPage:true});
 await page.locator('.portal-nav').getByRole('button',{name:'Overview',exact:true}).click();await page.getByRole('heading',{name:'Data validation',exact:true}).waitFor();
 await page.locator('.portal-stat').filter({hasText:'fresh reports'}).getByText(/^[1-9][0-9]*$/).waitFor();assert.deepEqual(errors,[]);console.log('Shared mapping, simulated metadata capture, SQL sample reuse, comparison and validation dashboard passed.');
}finally{await browser.close();}
