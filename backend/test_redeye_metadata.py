import copy
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend import redeye_pilot as vendor
from backend.test_redeye_pilot import portal
from backend.test_parameter_imports import URI
from backend.providers import ProviderError

ROOT='/api/projects/harbour/redeye-metadata'


@pytest.fixture
def editor(portal,monkeypatch):
    c,path,ident,state=portal
    monkeypatch.setenv('ORBIT_UAT_MODE','1')
    def transport(base,secret,cfg,method,api_path,payload=None,transport=None):
        state['calls'].append((method,api_path))
        if method=='POST':
            state['posts']+=1
            if state['post_mode']=='reject':raise ProviderError('access_denied','fixture denial')
            state['payload']=payload
            if state['post_mode']!='no_change':
                state['doc']['metadata']=[{'id':100+i*100+n,'key_id':next(k['id'] for k in state['keys'] if k['name']==r['name']),'key_name':r['name'],'value':v} for i,r in enumerate(payload['metadata']) for n,v in enumerate(r['value'])]
                state['doc']['modified']='2026-11-10T10:00:00Z'
            if state['post_mode']=='damage':state['doc']['metadata'][0]['value']='wrong'
            if state['post_mode']=='timeout':raise ProviderError('transport_uncertain','fixture timeout')
            return None
        if state['read_mode']=='fail':raise ProviderError('read_failed','fixture read failed')
        if api_path=='/api/v1/metadata-keys':return copy.deepcopy(state['keys'])
        return copy.deepcopy(state['doc'])
    monkeypatch.setattr(vendor,'request_vendor',transport)
    return c,path,ident,state


def inspect(c,ident):
    r=c.post(ROOT+'/inspect',json={'connection_id':ident,'artefact_id':777});assert r.status_code==200,r.text
    return r.json()['id']


def preview(c,ident,key=10,values=None,**extra):
    r=c.post(ROOT+'/preview',json={'inspection_id':inspect(c,ident),'metadata_key_id':key,'values':['new'] if values is None else values,'overwrite_existing':True,**extra})
    assert r.status_code==200,r.text
    return r.json()


def execute(c,j,**extra):
    return c.post(ROOT+'/'+j['id']+'/execute',json={'digest':j['digest'],'confirmed':True,'current_revision_confirmed':True,**extra})


def test_verify_any_field_without_bsdd_or_writes(editor):
    c,path,ident,state=editor
    with sqlite3.connect(path) as db:db.execute('DELETE FROM bsdd_settings')
    inspection=inspect(c,ident)
    for values,match in [(None,None),(['keep exactly'],True),(['different'],False)]:
        r=c.post(ROOT+'/verify',json={'inspection_id':inspection,'metadata_key_id':10,'values':values})
        assert r.status_code==200,r.text
        assert r.json()['matches'] is match and r.json()['actual']==['keep exactly'] and not r.json()['written']
    assert state['posts']==0


def test_update_existing_field_without_role_switch_or_arm_and_repeat_fresh_edit(editor):
    c,path,ident,state=editor
    with sqlite3.connect(path) as db:db.execute('DELETE FROM bsdd_settings')
    first=preview(c,ident)
    assert first['plan']['previous']==['keep exactly'] and state['posts']==0
    r=execute(c,first);assert r.status_code==200,r.text
    assert r.json()['read_back_verified'] and state['posts']==1
    assert execute(c,first).json()==r.json() and state['posts']==1
    second=preview(c,ident,values=['second change'])
    assert execute(c,second).json()['read_back_verified'] and state['posts']==2
    restarted=TestClient(create_app(path,demo=True));restarted.cookies.update(c.cookies)
    assert execute(restarted,second).json()['status']=='verified' and state['posts']==2


def test_multiple_values_preserved_and_target_replaced(editor):
    c,_,ident,state=editor
    state['doc']['metadata'].append({'key_id':10,'key_name':'Existing Note','value':'another'})
    j=preview(c,ident,key=20,values=['a','b'])
    assert j['plan']['payload']['metadata']==[{'name':'Existing Note','value':['keep exactly','another']},{'name':'Pilot Rating','value':['a','b']}]
    assert execute(c,j).json()['read_back_verified']
    j=preview(c,ident,key=20,values=['c','d'])
    assert execute(c,j).json()['read_back_verified'] and state['posts']==2


@pytest.mark.parametrize('values',[[''],[True],[60],['a','b']])
def test_user_specified_scalar_or_multiple_values(editor,values):
    c,_,ident,state=editor;j=preview(c,ident,key=20,values=values)
    assert execute(c,j).json()['status']=='verified'
    assert state['payload']['metadata'][-1]['value']==[v if isinstance(v,str) else json.dumps(v,separators=(',',':')) for v in values]


@pytest.mark.parametrize('change',['no_overwrite','same','invalid_key','invalid_values','no_bsdd_property','invalid_bsdd_value','not_modifiable'])
def test_invalid_preview_sends_no_write(editor,change):
    c,_,ident,state=editor
    if change=='not_modifiable':state['doc']['state']['is_modifiable']=False
    body={'inspection_id':inspect(c,ident),'metadata_key_id':10,'values':['new'],'overwrite_existing':True}
    if change=='no_overwrite':body['overwrite_existing']=False
    if change=='same':body['values']=['keep exactly']
    if change=='invalid_key':body['metadata_key_id']=999
    if change=='invalid_values':body['values']=[{'nested':'object'}]
    if change=='no_bsdd_property':body['property_uri']='https://example.com/unknown'
    if change=='invalid_bsdd_value':body['property_uri']=URI
    r=c.post(ROOT+'/preview',json=body);assert r.status_code in {409,422},r.text
    assert state['posts']==0


def test_optional_bsdd_validates_typed_proposal_and_observed_value(editor):
    c,_,ident,state=editor
    j=preview(c,ident,key=20,values=[60],property_uri=URI)
    assert execute(c,j).json()['status']=='verified'
    r=c.post(ROOT+'/verify',json={'inspection_id':inspect(c,ident),'metadata_key_id':20,'property_uri':URI})
    assert r.status_code==200,r.text
    assert r.json()['validation_errors']==[]
    state['doc']['metadata'][-1]['value']='wrong type'
    r=c.post(ROOT+'/verify',json={'inspection_id':inspect(c,ident),'metadata_key_id':20,'property_uri':URI})
    assert r.json()['validation_errors'] and state['posts']==1


@pytest.mark.parametrize('change',['confirmation','revision_confirmation','uat','session','expired','generation','role','project','digest','changed_destination','source','origin'])
def test_execute_checks_scope_and_freshness(editor,monkeypatch,change):
    c,path,ident,state=editor
    j=preview(c,ident,**({'property_uri':URI,'values':[60]} if change=='source' else {}))
    extra={}
    if change=='confirmation':extra['confirmed']=False
    if change=='revision_confirmation':extra['current_revision_confirmed']=False
    if change=='uat':monkeypatch.delenv('ORBIT_UAT_MODE')
    if change=='session':c.post('/api/demo/session',json={'user_id':'north-owner'})
    if change=='expired':
        with sqlite3.connect(path) as db:db.execute('UPDATE redeye_metadata_updates SET expires=0')
    if change=='generation':
        with sqlite3.connect(path) as db:db.execute('UPDATE read_connections SET generation=generation+1')
    if change=='role':c.post('/api/demo/session',json={'user_id':'north-viewer'})
    if change=='project':c.post('/api/demo/session',json={'user_id':'south-owner'})
    if change=='digest':j['digest']='0'*64
    if change=='changed_destination':state['doc']['metadata'][0]['value']='another editor'
    if change=='source':
        with sqlite3.connect(path) as db:db.execute('UPDATE bsdd_settings SET version=version+1')
    if change=='origin':
        r=c.post(ROOT+'/'+j['id']+'/execute',json={'digest':j['digest'],'confirmed':True,'current_revision_confirmed':True},headers={'Origin':'https://other.example'})
    else:r=execute(c,j,**extra)
    assert r.status_code in {403,404,409} or r.json().get('status')=='not_sent',r.text
    assert state['posts']==0


@pytest.mark.parametrize('mode',['timeout','no_change','damage','reject'])
def test_uncertain_outcomes_never_replay_or_allow_blind_new_write(editor,mode):
    c,_,ident,state=editor;j=preview(c,ident,key=20)
    state['post_mode']=mode;r=execute(c,j)
    assert r.json()['status']=='needs_review' and state['posts']==1
    assert execute(c,j).json()==r.json() and state['posts']==1
    another=preview(c,ident,key=20,values=['next'])
    assert execute(c,another).status_code==409 and state['posts']==1
    if mode=='timeout':
        recheck=c.post(ROOT+'/'+j['id']+'/recheck',json={'digest':j['digest']})
        assert recheck.json()['read_back_verified'] and not recheck.json()['http_200_observed']
        assert recheck.json()['initial_outcome']==r.json()['initial_outcome']
        state['post_mode']='normal'
        assert execute(c,another).json()['read_back_verified'] and state['posts']==2


def test_verification_not_blocked_by_many_revisions_or_unmodifiable_state(editor):
    c,_,ident,state=editor
    state['doc']['state']['is_modifiable']=False
    state['doc']['revisions'].append({'id':102,'status':'Draft','version':2})
    r=c.post(ROOT+'/verify',json={'inspection_id':inspect(c,ident),'metadata_key_id':10})
    assert r.status_code==200 and state['posts']==0


def test_existing_history_does_not_block_selected_update(editor):
    c,_,ident,state=editor
    state['doc']['revisions'].append({'id':102,'status':'Historic','version':0})
    assert execute(c,preview(c,ident)).json()['read_back_verified']


def test_verification_reads_fresh_not_cached_inspection(editor):
    c,_,ident,state=editor;old=inspect(c,ident)
    state['doc']['metadata'][0]['value']='changed'
    r=c.post(ROOT+'/verify',json={'inspection_id':old,'metadata_key_id':10,'values':['changed']})
    assert r.json()['matches'] is True and state['posts']==0


@pytest.mark.parametrize('route',['verify','preview'])
def test_secret_cannot_be_used_as_value(editor,route):
    c,path,ident,state=editor
    r=c.post(ROOT+'/'+route,json={'inspection_id':inspect(c,ident),'metadata_key_id':10,'values':['synthetic-pilot-key'],'overwrite_existing':True})
    assert r.status_code==422 and state['posts']==0
    with sqlite3.connect(path) as db:assert db.execute('SELECT count(*) FROM redeye_metadata_updates').fetchone()[0]==0


def test_fresh_inspection_is_needed_after_another_local_update(editor):
    c,_,ident,state=editor
    first=preview(c,ident,values=['first']);stale=preview(c,ident,key=20)
    assert execute(c,first).json()['status']=='verified'
    assert execute(c,stale).json()['status']=='not_sent' and state['posts']==1
    assert execute(c,preview(c,ident,key=20)).json()['status']=='verified' and state['posts']==2


def test_failed_preflight_does_not_permanently_lock_target(editor):
    c,_,ident,state=editor;j=preview(c,ident)
    state['read_mode']='fail'
    assert execute(c,j).json()['status']=='not_sent' and state['posts']==0
    state['read_mode']='normal'
    assert execute(c,preview(c,ident)).json()['status']=='verified' and state['posts']==1


@pytest.mark.parametrize('change',['missing_key_name','duplicate_key_name','unknown_key','null_value','incorrect_id'])
def test_unreliable_vendor_metadata_is_not_silently_discarded(editor,change):
    c,_,ident,state=editor
    if change=='missing_key_name':state['doc']['metadata'][0].pop('key_name')
    if change=='duplicate_key_name':state['keys'][1]['name']=state['keys'][0]['name']
    if change=='unknown_key':state['doc']['metadata'][0]['key_id']=999
    if change=='null_value':state['doc']['metadata'][0]['value']=None
    if change=='incorrect_id':state['doc']['id']=778
    r=c.post(ROOT+'/inspect',json={'connection_id':ident,'artefact_id':777})
    assert r.status_code==502 and state['posts']==0


def test_missing_credential_never_leaks_provider_or_key(editor):
    c,path,ident,state=editor
    with sqlite3.connect(path) as db:db.execute('UPDATE read_connections SET secret_ciphertext=NULL WHERE id=?',(ident,))
    r=c.post(ROOT+'/inspect',json={'connection_id':ident,'artefact_id':777})
    assert r.status_code==409 and state['posts']==0
    assert 'synthetic-pilot-key' not in r.text


def test_readback_failure_after_http200_is_reconciled_without_replay(editor,monkeypatch):
    c,_,ident,state=editor;j=preview(c,ident,key=20)
    original=vendor.request_vendor
    def transport(*args,**kwargs):
        result=original(*args,**kwargs)
        if args[3]=='POST':state['read_mode']='fail'
        return result
    monkeypatch.setattr(vendor,'request_vendor',transport)
    receipt=execute(c,j).json()
    assert receipt['status']=='needs_review' and receipt['http_200_observed'] and state['posts']==1
    state['read_mode']='normal'
    r=c.post(ROOT+'/'+j['id']+'/recheck',json={'digest':j['digest']})
    assert r.json()['read_back_verified'] and r.json()['http_200_observed']
    assert r.json()['initial_outcome']==receipt['initial_outcome'] and state['posts']==1


def test_interrupted_attempt_is_never_reposted(editor):
    c,path,ident,state=editor;j=preview(c,ident,key=20)
    with sqlite3.connect(path) as db:db.execute("UPDATE redeye_metadata_updates SET status='attempting' WHERE id=?",(j['id'],))
    assert execute(c,j).json()['status']=='attempting' and state['posts']==0
    r=c.post(ROOT+'/'+j['id']+'/recheck',json={'digest':j['digest']})
    assert r.json()['status']=='needs_review' and state['posts']==0


def test_stale_recheck_does_not_replace_a_verified_receipt(editor,monkeypatch):
    c,path,ident,state=editor;j=preview(c,ident,key=20)
    with sqlite3.connect(path) as db:db.execute("UPDATE redeye_metadata_updates SET status='attempting' WHERE id=?",(j['id'],))
    original=vendor.request_vendor
    final={'status':'verified','reason':'Concurrent completed update','read_back_verified':True,'http_200_observed':True}
    def transport(*args,**kwargs):
        result=original(*args,**kwargs)
        if args[4]=='/api/v1/artefacts/777':
            with sqlite3.connect(path) as db:db.execute("UPDATE redeye_metadata_updates SET status='verified',receipt=? WHERE id=?",(json.dumps(final),j['id']))
        return result
    monkeypatch.setattr(vendor,'request_vendor',transport)
    r=c.post(ROOT+'/'+j['id']+'/recheck',json={'digest':j['digest']})
    assert r.json()==final and state['posts']==0


def test_manual_review_closes_uncertainty_without_claiming_write_verification(editor):
    c,_,ident,state=editor;j=preview(c,ident,key=20)
    state['post_mode']='reject';receipt=execute(c,j).json()
    assert receipt['status']=='needs_review'
    assert c.post(ROOT+'/'+j['id']+'/resolve',json={'digest':j['digest']}).status_code==409
    r=c.post(ROOT+'/'+j['id']+'/resolve',json={'digest':j['digest'],'confirmed':True})
    assert r.json()['status']=='reviewed' and not r.json()['read_back_verified'] and not r.json()['http_200_observed']
    assert r.json()['initial_outcome']==receipt['initial_outcome'] and state['posts']==1
    assert execute(c,j).json()['status']=='reviewed' and state['posts']==1
    state['post_mode']='normal'
    assert execute(c,preview(c,ident,key=20)).json()['status']=='verified' and state['posts']==2


def test_manual_resolution_requires_current_owner_and_exact_job(editor):
    c,_,ident,state=editor;j=preview(c,ident,key=20)
    state['post_mode']='reject';execute(c,j)
    c.post('/api/demo/session',json={'user_id':'north-viewer'})
    assert c.post(ROOT+'/'+j['id']+'/resolve',json={'digest':j['digest'],'confirmed':True}).status_code==403
    c.post('/api/demo/session',json={'user_id':'south-owner'})
    assert c.post(ROOT+'/'+j['id']+'/resolve',json={'digest':j['digest'],'confirmed':True}).status_code==404
    assert state['posts']==1
