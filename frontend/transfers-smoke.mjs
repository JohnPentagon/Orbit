// Transfer UI contract fixture. No file reaches a real Autodesk or RedEye service.
import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];page.on('pageerror',e=>errors.push(e.message));
const base=process.env.ORBIT_TEST_URL||'http://127.0.0.1:8014';
let enabled=false,viewer=false,runs=[],copies=0,failUpload=false,rechecks=0;
const connections=[{id:'aps',name:'Autodesk drawings',provider:'forma'},{id:'re',name:'RedEye handover',provider:'redeye'}];
await page.route('**/api/**',async route=>{const req=route.request(),p=new URL(req.url()).pathname,body=req.postData()?req.postDataJSON():{},method=req.method();let data;
 if(method!=='GET')assert.equal(req.headers()['x-orbit-csrf'],'transfer-csrf');
 if(p==='/api/health')data={mode:'hosted-workspace',version:'0.21.0'};
 else if(p==='/api/session')data={authenticated:true,csrf_token:'transfer-csrf'};
 else if(p==='/api/workspace')data={identity:{user_id:'fixture',tenant_id:'fixture',role:viewer?'viewer':'owner'},tenant:{name:'Transfer UAT'},permissions:viewer?['view']:['view','connection','run','draft'],projects:[{id:'test',name:'Harbour Exchange'},{id:'empty',name:'Empty project'}]};
 else if(p.endsWith('/transfers'))data={enabled,connections,mappings:[{id:'map',name:'Handover properties',source_id:'aps',target_id:'re'}],runs:p.includes('/empty/')?[]:runs};
 else if(p.endsWith('/sources/aps'))data={id:'sample',coverage:'Two fixture files from the selected recursive folder',files:[{id:'f1',name:'Plan.pdf',path:'Civil/Plan.pdf'},{id:'f2',name:'Spec.pdf',path:'Specs/Spec.pdf'}]};
 else if(p.endsWith('/targets/re'))data={keys:[{id:1,name:'Discipline'},{id:2,name:'Source path'}],groups:[{id:7,name:'Civil handover'},{id:8,name:'Specifications'}]};
 else if(p.endsWith('/preview')){
  assert.equal(copies,0);assert.ok(body.rules_confirmed);assert.deepEqual(body.file_ids,['f1']);assert.equal(body.mapping_id,'map');assert.equal(body.structure,'group_map');assert.equal(body.group_map.Civil,7);assert.equal(body.quality_mode,'skip');
  data={id:'run-'+runs.length,source_name:'Autodesk drawings',target_name:'RedEye handover',created:new Date().toISOString(),expires:Math.floor(Date.now()/1000)+1800,quality_mode:body.quality_mode,structure:body.structure,items:[{id:'item',name:'Plan.pdf',path:'Civil/Plan.pdf',status:'ready',issues:[],message:'',preview_digest:'preview-digest',groups:[7],group_labels:['Civil handover'],payload:{type:'document',metadata:[{name:'Discipline',value:['Civil']}]}}]};runs.unshift(data);
 }
 else if(p.endsWith('/execute')){assert.equal(body.confirmed,true);assert.equal(body.preview_digest,'preview-digest');copies++;data=runs[0].items[0];data.status=failUpload?'uncertain':'completed';data.message=failUpload?'Upload response lost; recheck before copying again.':'File hash and metadata verified';}
 else if(p.endsWith('/recheck')){rechecks++;assert.equal(body.artefact_id,777);data=runs[0].items[0];data.status='completed';data.artefact_id=777;data.message='Destination file verified without another upload';}
 else throw new Error('Unexpected transfer fixture request '+method+' '+p);
 await route.fulfill({json:data});});
try{
 await page.goto(base+'/#transfers');await page.getByRole('heading',{name:'File transfers',exact:true}).waitFor();await page.getByText(/Previews are available/).waitFor();
 await page.getByLabel('Transfer source',{exact:true}).selectOption('aps');await page.getByRole('button',{name:'Load source files',exact:true}).click();await page.getByRole('checkbox',{name:'Copy Civil/Plan.pdf',exact:true}).check();
 await page.getByLabel('Transfer destination',{exact:true}).selectOption('re');await page.getByRole('button',{name:'Load destination options',exact:true}).click();await page.getByLabel('Transfer mapping profile').selectOption('map');await page.getByLabel('Transfer validation').selectOption('skip');await page.getByLabel('Transfer folder handling').selectOption('group_map');await page.getByLabel('Destination group for Civil',{exact:true}).selectOption('7');await page.getByLabel('Confirm destination upload rules').check();await page.getByRole('button',{name:'Prepare transfer preview',exact:true}).click();
 await page.getByRole('heading',{name:'3. Review and confirm',exact:true}).waitFor();assert.equal(copies,0);await page.getByLabel('Confirm reviewed file copies').check();assert.equal(await page.getByRole('button',{name:'Confirm and copy ready files',exact:true}).isDisabled(),true);
 enabled=true;await page.getByRole('button',{name:'Refresh history',exact:true}).click();assert.equal(await page.getByRole('button',{name:'Confirm and copy ready files',exact:true}).isDisabled(),false);failUpload=true;await page.getByRole('button',{name:'Confirm and copy ready files',exact:true}).click();await page.getByText('Batch paused. Recheck this item before any further upload.',{exact:true}).waitFor();assert.equal(copies,1);assert.equal(await page.getByRole('button',{name:'Confirm and copy ready files',exact:true}).isDisabled(),true);
 const history=page.locator('.transfer-history').first();await history.locator('summary').first().click();await history.getByLabel('Destination artefact ID for Plan.pdf').fill('777');await history.getByRole('button',{name:'Recheck destination — no upload',exact:true}).click();await page.getByText('Destination recheck finished. Inspect the recorded result.',{exact:true}).waitFor();assert.equal(copies,1);assert.equal(rechecks,1);
 await page.screenshot({path:'/workspace/Orbit/.local/screenshots/transfers-desktop.png',fullPage:true});await page.reload();await page.getByRole('heading',{name:'File transfers',exact:true}).waitFor();await page.locator('.transfer-history').first().locator('summary').first().click();await page.getByText('Copy verified',{exact:true}).waitFor();
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);await page.screenshot({path:'/workspace/Orbit/.local/screenshots/transfers-mobile.png',fullPage:true});
 await page.getByLabel('Project',{exact:true}).selectOption('empty');await page.getByText('No transfer previews yet.',{exact:true}).waitFor();assert.equal(await page.getByText('Copy verified',{exact:true}).count(),0);
 viewer=true;await page.reload();await page.getByRole('heading',{name:'File transfers',exact:true}).waitFor();await page.getByText('Your role can view transfer history. A connection owner prepares and confirms file copies.',{exact:true}).waitFor();assert.equal(await page.getByRole('button',{name:'Load source files',exact:true}).count(),0);assert.equal(copies,1);assert.deepEqual(errors,[]);
 console.log('Transfers passed: file selection, mapping/quality options, folder-to-group mapping, preview without writes, disabled execution setting, explicit confirmation, uncertain pause, destination recheck without reupload, persisted history, project switch, viewer access and mobile layout. All vendor responses simulated.');
}finally{await browser.close();}
