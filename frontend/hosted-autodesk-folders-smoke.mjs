// Hosted UI contract fixtures; no Microsoft or Autodesk service is contacted.
import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
const base=process.env.ORBIT_TEST_URL||'http://127.0.0.1:8014';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1100}});const errors=[];page.on('pageerror',e=>errors.push(e.message));
let profile=null,app=null,expires=null,selected=null,read=false;
const rootFolder='urn:fixture:root',childFolder='urn:fixture:structural',leafFolder='urn:fixture:drawings';
const trail=[{id:rootFolder,label:'Project Files'},{id:childFolder,label:'Structural'},{id:leafFolder,label:'GA drawings'}];
const path='/api/projects/uat-project/read-connections';
function readiness(){return {ready:!!profile?.credential_present,issues:profile?.credential_present?[]:[{code:'setup_required',message:'Save the APS application below, then select Sign in with Autodesk. An API key is not required.',next_action:'Use the APS controls below.'}]};}
await page.route('**/api/**',async route=>{
 const req=route.request(),url=new URL(req.url()),p=url.pathname,method=req.method(),body=req.postData()?req.postDataJSON():{};let data;
 if(!['GET','HEAD'].includes(method))assert.equal(req.headers()['x-orbit-csrf'],'fixture-csrf');
 if(p==='/api/health')data={mode:'hosted-workspace',version:'0.16.0',runtime:'ASP.NET Core 10'};
 else if(p==='/api/session')data={authenticated:true,csrf_token:'fixture-csrf'};
 else if(p==='/api/workspace')data={identity:{user_id:'fixture-owner',tenant_id:'fixture-tenant',role:'owner'},operator_name:'Fixture operator',tenant:{name:'APS UI fixture'},permissions:['view','connection','draft','run','administer'],projects:[{id:'uat-project',name:'APS test project'}]};
 else if(p.endsWith('/connection-summary'))data={connections:profile?[{...profile,kind:'read',binding_count:0,last_read:null}]:[],mapping_count:0,dictionary:{enabled:false,name:null,property_count:0},observed:new Date().toISOString()};
 else if(p.endsWith('/analysis'))data={connections:[],snapshots:[],mappings:[],reports:[],properties:[],health:{},validation:{mappings:0,fresh_reports:0},scope:'UI fixture only'};
 else if(p===path&&method==='POST'){profile={id:'fixture-aps',name:body.name,provider:'forma',generation:1,configuration:body,credential_present:false,last_result:null};data={id:profile.id};}
 else if(p===path){if(profile)profile.readiness=readiness();data={server_version:'0.16.0',live_reads_enabled:true,connections:profile?[profile]:[]};}
 else if(p===path+'/fixture-aps/autodesk'&&method==='GET')data={callback_url:'https://orbit.example/api/autodesk/callback',app,expires,renewal_available:!!expires,scope:'data:read',folder_browser:true};
 else if(p===path+'/fixture-aps/autodesk'&&method==='PUT'){app={client_id:body.client_id,mode:body.mode};profile.generation++;data={configured:true};}
 else if(p.endsWith('/autodesk/connect'))data={authorize_url:'https://developer.api.autodesk.com/authentication/v2/authorize?state=fixture-ui-state'};
 else if(p==='/api/autodesk/callback'){profile.credential_present=true;profile.generation++;expires=Math.floor(Date.now()/1000)+3600;await route.fulfill({status:302,headers:{location:base+'/?autodesk=connected&autodesk_project=uat-project'}});return;}
 else if(p.endsWith('/autodesk/discover')){
  if(body.kind==='contents'){
   let resources=[];let path=[];
   if(body.folder===rootFolder){resources=[{id:childFolder,label:'Structural',kind:'folders'}];path=trail.slice(0,1);}
   else if(body.folder===childFolder){resources=[{id:leafFolder,label:'GA drawings',kind:'folders'}];path=trail.slice(0,2);}
   else if(body.folder===leafFolder){resources=Array.from({length:body.page?5:25},(_,i)=>({id:'fixture-file-'+(i+1+(body.page?25:0)),label:'GA-'+String(i+1+(body.page?25:0)).padStart(3,'0')+'.pdf',kind:'items'}));path=trail;}
   else throw new Error('Unexpected folder');
   data={resources,folder:{...path.at(-1),path},page:body.page||0,has_more:body.folder===leafFolder&&!body.page,loaded_count:body.page?30:resources.length,coverage:'Simulated current folder'};
  }else data={resources:body.kind==='hubs'?[{id:'b.fixture-hub',label:'Example ACC account',kind:'hubs'}]:body.kind==='projects'?[{id:'b.fixture-project',label:'Example construction project',kind:'projects'}]:[{id:rootFolder,label:'Project Files',kind:'folders'}]};
 }
 else if(p.endsWith('/autodesk/selection')){selected=body;Object.assign(profile.configuration,{hub:body.hub,vendor_project:body.project,folder:body.folder,hub_label:'Example ACC account',project_label:'Example construction project',folder_label:'Project Files / Structural / GA drawings',folder_path:trail,file_ids:body.file_ids,document_limit:body.document_limit});profile.generation++;data={saved:true};}
 else if(p.endsWith('/read')){assert.deepEqual(body,{operation:'documents',hub:selected.hub,project:selected.project,folder:selected.folder});read=true;data={synthetic:false,operation:'documents',resources:[{id:'fixture-document',label:'GA-030.pdf',kind:'items'}],returned:1,coverage:'One simulated folder response'};}
 else if(p.endsWith('/autodesk/renew')){profile.generation++;expires=Math.floor(Date.now()/1000)+3600;data={renewed:true};}
 else throw new Error('Unexpected fixture request '+method+' '+p);
 await route.fulfill({json:data});
});
await page.route('https://developer.api.autodesk.com/authentication/v2/authorize**',async route=>{await route.fulfill({contentType:'text/html',body:`<h1>Simulated APS consent</h1><a href="${base}/api/autodesk/callback?state=fixture-ui-state&code=fixture-ui-code">Approve simulated Autodesk consent</a>`});});
try{
 await page.goto(base);await page.locator('.portal-nav').getByRole('button',{name:'Connections',exact:true}).click();await page.locator('.platform-card').filter({has:page.getByRole('heading',{name:'Autodesk',exact:true})}).click();
 await page.getByLabel('Test connection name',{exact:true}).fill('Autodesk hosted UAT');await page.getByLabel('I have confirmed the vendor host and authentication settings').check();await page.getByLabel('This account and resource scope are authorised for testing').check();await page.getByRole('button',{name:'Create connection',exact:true}).click();
 await page.getByLabel('APS client ID',{exact:true}).fill('fixture-ui-client');await page.getByLabel('APS client secret',{exact:true}).fill('fixture-ui-secret');await page.getByLabel('Autodesk callback URL',{exact:true}).inputValue().then(v=>assert.equal(v,'https://orbit.example/api/autodesk/callback'));await page.getByRole('button',{name:'Save APS application',exact:true}).click();
 await page.getByText('APS application saved. The Client Secret is stored encrypted on the ORBIT server. Sign in with Autodesk next.',{exact:true}).waitFor();await page.getByRole('button',{name:'Sign in with Autodesk',exact:true}).click();await page.getByRole('link',{name:'Approve simulated Autodesk consent',exact:true}).click();
 await page.getByRole('heading',{name:'Autodesk',exact:true}).waitFor();await page.getByRole('button',{name:'Load accessible hubs',exact:true}).click();await page.getByLabel('Discovered Autodesk hub').selectOption('b.fixture-hub');await page.getByLabel('Discovered Autodesk project').selectOption('b.fixture-project');await page.getByLabel('Discovered Autodesk folder').selectOption(rootFolder);
 await page.getByRole('button',{name:'Open folder Structural',exact:true}).click();await page.getByRole('button',{name:'Open folder GA drawings',exact:true}).click();
 await page.getByRole('button',{name:'Load more entries',exact:true}).click();await page.getByRole('checkbox',{name:'Select file GA-030.pdf',exact:true}).check();await page.getByRole('button',{name:'Use 1 selected file',exact:true}).click();
 await page.getByText(/Saved selection:.*GA drawings.*1 selected files/).waitFor();assert.deepEqual(selected.file_ids,['fixture-file-30']);assert.equal(selected.folder,leafFolder);assert.equal(selected.document_limit,100);
 await page.getByRole('button',{name:'Read document sample',exact:true}).click();await page.getByRole('cell',{name:'GA-030.pdf',exact:true}).waitFor();assert.ok(read);
 await page.getByRole('button',{name:'Browse saved folder',exact:true}).click();await page.getByRole('button',{name:'Load more entries',exact:true}).click();assert.equal(await page.getByRole('checkbox',{name:'Select file GA-030.pdf',exact:true}).isChecked(),true);
 await page.getByRole('button',{name:'Up one folder',exact:true}).click();await page.getByRole('button',{name:'Open folder GA drawings',exact:true}).waitFor();
 await page.screenshot({path:'/workspace/Orbit/.local/screenshots/hosted-autodesk-folders.png',fullPage:true});await page.getByRole('button',{name:'Renew authorisation',exact:true}).click();await page.getByText('Authorisation renewed. Refresh discovery to use the current permissions.',{exact:true}).waitFor();assert.equal(await page.locator('[role=alert]').count(),0);
 await page.setViewportSize({width:390,height:844});assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);assert.deepEqual(errors,[]);console.log('Hosted Autodesk folder browser passed: nested folders, breadcrumbs, paging beyond 25, file checkbox selection, saved scope reopening, selected document read, renewal and mobile layout. External responses simulated.');
}finally{await browser.close();}
