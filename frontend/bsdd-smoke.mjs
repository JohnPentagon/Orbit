// Service fixtures only. Backend persistence/isolation and live API reads are checked separately.
import {chromium} from 'playwright-core';
import assert from 'node:assert/strict';
const browser=await chromium.launch({executablePath:process.env.CHROMIUM_PATH||'/usr/bin/chromium',headless:true,args:['--no-sandbox']});
const page=await browser.newPage({viewport:{width:1440,height:1100}}),errors=[];
page.on('pageerror',e=>errors.push(e.message));
const uri='https://identifier.buildingsmart.org/uri/example/test/2024';
const dictionary={uri,name:'Synthetic engineering',version:'2024',organizationNameOwner:'Example',status:'Preview',license:'Synthetic fixture'};
const property={uri:uri+'/class/Wall/prop/General/FireRating',propertyUri:uri+'/prop/FireRating',name:'Fire Rating',propertyCode:'FireRating',propertySet:'General',dataType:'String',definition:'Synthetic fire rating definition',unit:'minute'};
const cls={uri:uri+'/class/Wall',code:'Wall',name:'Wall',properties:[property]};
let saved={version:0,configuration:{enabled:false,dictionary:null,class:null,properties:[]},updated:null,updated_by:null},lookups=0,failLookup=false;
await page.route('**/api/projects/harbour/bsdd**',async route=>{
 const request=route.request(),path=new URL(request.url()).pathname;
 if(path.endsWith('/bsdd')&&request.method()==='GET')return route.fulfill({json:saved});
 if(path.endsWith('/bsdd')&&request.method()==='PUT'){
  const body=request.postDataJSON();saved={version:saved.version+1,configuration:{enabled:body.enabled,dictionary:body.dictionary_uri?dictionary:null,class:body.class_uri?{uri:cls.uri,name:cls.name,code:cls.code}:null,properties:body.property_uris.length?[property]:[]},updated:new Date().toISOString(),updated_by:'north-owner'};
  return route.fulfill({json:saved});
 }
 lookups++;
 if(failLookup)return route.fulfill({status:502,json:{detail:{code:'rate_limited',message:'bSDD rate limit reached. Try again later.'}}});
 if(path.endsWith('/dictionaries'))return route.fulfill({json:{dictionaries:[dictionary],offset:0,count:1,total:1,observed:new Date().toISOString()}});
 if(path.endsWith('/classes'))return route.fulfill({json:{classes:[cls],offset:0,count:1,total:1}});
 if(path.endsWith('/class'))return route.fulfill({json:cls});
 throw new Error('Unexpected fixture route '+path);
});
try{
 await page.goto('http://127.0.0.1:8000');
 await page.getByLabel('Choose a synthetic identity').selectOption('north-owner');
 await page.getByRole('button',{name:'Enter workspace'}).click();
 await page.getByRole('button',{name:'bSDD dictionaries',exact:true}).click();
 await page.getByRole('button',{name:'Connect & browse dictionaries'}).waitFor();assert.equal(lookups,0);
 await page.getByRole('button',{name:'Connect & browse dictionaries'}).click();
 await page.getByLabel('Dictionary version',{exact:true}).selectOption(uri);
 await page.getByRole('button',{name:'Browse classes',exact:true}).click();
 await page.getByLabel('Dictionary class',{exact:true}).selectOption(cls.uri);
 await page.getByLabel('Use property FireRating in General',{exact:true}).check();
 await page.getByLabel('Use bSDD for this project',{exact:true}).check();
 await page.getByRole('button',{name:'Save dictionary selection',exact:true}).click();
 await page.getByText('Dictionary version and selected property definitions saved for this project.',{exact:true}).waitFor();
 assert.equal(saved.configuration.properties[0].dataType,'String');
 await page.reload();await page.getByRole('button',{name:'bSDD dictionaries',exact:true}).click();
 await page.getByText('Wall · 1 selected property definitions · Enabled for mapping reference',{exact:true}).waitFor();
 await page.getByRole('button',{name:'Integration profiles',exact:true}).click();
 await page.getByText('bSDD reference: Synthetic engineering · 2024',{exact:true}).waitFor();
 assert.equal(await page.locator('#bsdd-property-fields option').first().getAttribute('value'),'General.FireRating');
 await page.getByRole('button',{name:'bSDD dictionaries',exact:true}).click();
 await page.getByLabel('Dictionary URL',{exact:true}).fill(uri+'/different-version');
 assert.equal(await page.getByRole('button',{name:'Save dictionary selection',exact:true}).isDisabled(),true);
 failLookup=true;await page.getByRole('button',{name:'Verify dictionary URL',exact:true}).click();
 await page.getByRole('alert').filter({hasText:'bSDD rate limit reached'}).waitFor();assert.equal(saved.configuration.dictionary.uri,uri);
 await page.getByLabel('Test identity',{exact:true}).selectOption('north-viewer');
 await page.getByText('viewer · north-viewer',{exact:true}).waitFor();
 await page.getByText('Synthetic fire rating definition',{exact:true}).waitFor();
 assert.equal(await page.getByRole('button',{name:'Connect & browse dictionaries'}).count(),0);
 await page.setViewportSize({width:390,height:844});
 assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth+1));
 await page.screenshot({path:'/workspace/Orbit/.local/screenshots/bsdd-viewer-mobile.png',fullPage:true});
 assert.deepEqual(errors,[]);
 console.log('bSDD UI smoke passed: explicit dictionary/class lookup, selected properties, reload, mapping suggestions, error preservation and viewer/mobile access; service fixtures only.');
}finally{await browser.close();}
