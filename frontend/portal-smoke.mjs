// Requires backend.portal_fixture, which starts empty and forbids real external transport.
import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
import {mkdir} from 'node:fs/promises';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const base=process.env.ORBIT_TEST_URL||'http://127.0.0.1:8005';
const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[],requests=[];
page.on('pageerror',e=>errors.push(e.message));page.on('request',r=>{if(r.url().includes('/api/'))requests.push(r.url());});
await mkdir('/workspace/Orbit/.local/screenshots',{recursive:true});
async function nav(name){await page.locator('.portal-nav').getByRole('button',{name,exact:true}).click();}
async function platform(name){await page.locator('.platform-card').filter({has:page.getByRole('heading',{name,exact:true})}).click();}
async function width(){assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1),'Page overflows horizontally');}
try{
 await page.goto(base);assert.equal(await page.title(),'ORBIT by Pentagon Solutions');const mark=await page.request.get(base+'/brand/orbit-mark.svg');assert.equal(mark.status(),200);assert.match(await mark.text(),/#69D9FD/);assert.match(await mark.text(),/#FFB64C/);await page.getByRole('heading',{name:'Make this workspace yours',exact:true}).waitFor();
 await page.screenshot({path:'/workspace/Orbit/.local/screenshots/portal-welcome.png',fullPage:true});
 await page.setViewportSize({width:390,height:844});await width();await page.setViewportSize({width:1440,height:1100});
 await page.getByLabel('Workspace name',{exact:true}).fill('Signalworks');await page.getByLabel('First project name',{exact:true}).fill('Central Hospital');await page.getByLabel('Operator name',{exact:true}).fill('Alex');await page.getByRole('button',{name:'Create workspace',exact:true}).click();
 await page.getByRole('heading',{name:/Make project.*data consistent\./}).waitFor();
 assert.equal(await page.locator('.portal-nav button').count(),5);assert.equal(await page.getByLabel('Test identity',{exact:true}).count(),0);
 await page.locator('.portal-stat').filter({hasText:'Saved connections'}).getByText('0',{exact:true}).waitFor();
 await nav('Connections');await page.getByRole('heading',{name:'Connections',exact:true}).waitFor();assert.equal(await page.locator('.platform-card').count(),8);
 await page.screenshot({path:'/workspace/Orbit/.local/screenshots/portal-connections.png',fullPage:true});
 await platform('RedEye');await page.getByLabel('Test connection name',{exact:true}).fill('Project RedEye');assert.equal(await page.getByLabel('Read provider',{exact:true}).count(),0);
 await page.getByLabel('I have confirmed the vendor host and authentication settings',{exact:true}).check();await page.getByLabel('This account and resource scope are authorised for testing',{exact:true}).check();await page.getByRole('button',{name:'Create connection',exact:true}).click();
 await page.getByRole('button',{name:'Add API key',exact:true}).click();await page.locator('#read-secret').fill('synthetic-portal-red-key');await page.getByRole('button',{name:'Save API key',exact:true}).click();
 await page.getByRole('button',{name:'Test connection',exact:true}).click();await page.getByText(/Last successful metadata_keys read:/).waitFor();
 assert.equal(await page.getByRole('button',{name:'Run fixture check',exact:true}).count(),0);
 await page.getByRole('button',{name:'Documents & metadata',exact:true}).click();await page.getByLabel('Metadata artefact ID',{exact:true}).fill('777');await page.getByRole('button',{name:'Load metadata fields',exact:true}).click();await page.getByLabel('Metadata field',{exact:true}).selectOption('10');
 await page.getByRole('button',{name:'Verify selected field',exact:true}).click();await page.getByText('Current value retrieved',{exact:true}).waitFor();
 await page.getByLabel('Metadata action',{exact:true}).selectOption('update');await page.getByLabel('Metadata value',{exact:true}).fill('Portal reviewed update');await page.getByLabel('Replace existing metadata value',{exact:true}).check();await page.getByRole('button',{name:'Preview metadata update',exact:true}).click();
 await page.getByLabel('Confirm metadata change',{exact:true}).check();await page.getByLabel('Confirm metadata revision',{exact:true}).check();await page.getByRole('button',{name:'Confirm and save to RedEye',exact:true}).click();await page.getByText('Selected field and all preserved metadata matched.',{exact:true}).waitFor();
 await nav('Connections');await platform('SQL Server / Azure SQL');await page.getByLabel('SQL connection name',{exact:true}).fill('Project SQL');await page.getByLabel('SQL database',{exact:true}).fill('Fixture');await page.getByLabel('SQL username',{exact:true}).fill('reader');await page.getByLabel('SQL approved test access',{exact:true}).check();await page.getByRole('button',{name:'Save SQL connection',exact:true}).click();
 await page.getByRole('button',{name:'Set SQL password',exact:true}).click();await page.getByLabel('SQL password',{exact:true}).fill('synthetic-portal-sql-password');await page.getByRole('button',{name:'Store encrypted SQL password',exact:true}).click();await page.getByRole('button',{name:'Connect and browse tables',exact:true}).click();await page.getByLabel('SQL object',{exact:true}).selectOption('0');await page.getByRole('button',{name:'Load columns and sample rows',exact:true}).click();
 await page.getByLabel('SQL mapping destination',{exact:true}).selectOption({label:'Project RedEye · read'});await page.getByRole('button',{name:'Load destination field inventory',exact:true}).click();await page.getByLabel('SQL mapping source 0',{exact:true}).selectOption('Title');await page.getByLabel('SQL mapping target 0',{exact:true}).selectOption('Existing Note');await page.getByLabel('SQL mapping transform 0',{exact:true}).selectOption('trim');await page.getByRole('button',{name:'Save SQL mapping',exact:true}).click();await page.getByText('Project/connection mapping saved. No SQL or destination platform write sent.',{exact:true}).waitFor();
 await nav('Mappings');await page.getByRole('heading',{name:'SQL field mapping',exact:true}).waitFor();
 await nav('Overview');await page.locator('.portal-stat').filter({hasText:'Saved connections'}).getByText('2',{exact:true}).waitFor();await page.locator('.portal-stat').filter({hasText:'Saved SQL mappings'}).getByText('1',{exact:true}).waitFor();
 await page.screenshot({path:'/workspace/Orbit/.local/screenshots/portal-overview.png',fullPage:true});
 await nav('Connections');await platform('Procore');assert.equal(await page.getByLabel('Additional provider',{exact:true}).count(),0);await page.getByLabel('Additional connection name',{exact:true}).fill('Project Procore');
 await nav('Connections');await platform('Meridian');await page.getByLabel('Additional API URL',{exact:true}).waitFor();
 await nav('Activity');await page.getByText('redeye metadata · verified',{exact:true}).waitFor();
 await nav('Settings');await page.getByLabel('Settings workspace name',{exact:true}).fill('Signalworks Delivery');await page.getByRole('button',{name:'Save workspace details',exact:true}).click();await page.getByText('Workspace details saved.',{exact:true}).waitFor();
 await page.getByLabel('New project name',{exact:true}).fill('Second project');await page.getByRole('button',{name:'Add project',exact:true}).click();await nav('Overview');await page.locator('.portal-stat').filter({hasText:'Saved connections'}).getByText('0',{exact:true}).waitFor();
 const projects=await (await page.request.get(base+'/api/workspace')).json();const first=projects.projects.find(p=>p.name==='Central Hospital');await page.getByLabel('Project',{exact:true}).selectOption(first.id);
 await page.locator('.portal-stat').filter({hasText:'Saved connections'}).getByText('2',{exact:true}).waitFor();
 await page.setViewportSize({width:390,height:844});await width();await page.screenshot({path:'/workspace/Orbit/.local/screenshots/portal-mobile.png',fullPage:true});await nav('Connections');await width();await platform('RedEye');await width();await page.screenshot({path:'/workspace/Orbit/.local/screenshots/portal-redeye-mobile.png',fullPage:true});
 await page.reload();await page.getByRole('heading',{name:'RedEye',exact:true}).waitFor();await page.getByRole('heading',{name:'Project RedEye',exact:true}).waitFor();
 assert.ok(!requests.some(u=>/\/demo\/|\/comparisons|\/proposals/.test(u)));
 assert.deepEqual(errors,[]);console.log('Local portal passed: empty onboarding, five-area navigation, scoped live connector workspaces, simulated RedEye read/write, SQL mapping, activity, settings, project isolation, reload and desktop/mobile. No real external calls.');
}finally{await browser.close();}
