// Run after portal-smoke against the same isolated fixture (it creates two projects).
import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1100,height:900}}),base=process.env.ORBIT_TEST_URL||'http://127.0.0.1:8005';
try{
 await page.goto(base);await page.getByRole('button',{name:'Open workspace',exact:true}).click();await page.getByRole('heading',{name:/Your information.*Connected\./}).waitFor();
 const options=await page.getByLabel('Project',{exact:true}).locator('option').evaluateAll(nodes=>nodes.map(n=>n.value));assert.ok(options.length>=2);
 const selected=options.at(-1);await page.getByLabel('Project',{exact:true}).selectOption(selected);await page.reload();await page.getByRole('heading',{name:/Your information.*Connected\./}).waitFor();assert.equal(await page.getByLabel('Project',{exact:true}).inputValue(),selected);
 await page.locator('.portal-nav').getByRole('button',{name:'Settings',exact:true}).click();await page.getByRole('button',{name:'Close workspace session',exact:true}).click();await page.getByRole('heading',{name:'Welcome back',exact:true}).waitFor();await page.getByRole('button',{name:'Open workspace',exact:true}).click();await page.getByRole('heading',{name:/Your information.*Connected\./}).waitFor();assert.equal(await page.getByLabel('Project',{exact:true}).inputValue(),selected);
 console.log('Local portal session passed: chosen project survives reload and explicit close/reopen without background sign-in or synthetic identity routes.');
}finally{await browser.close();}
