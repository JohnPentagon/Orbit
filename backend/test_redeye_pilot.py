import copy
import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend import redeye_pilot as pilot
from backend.providers import ProviderError
from backend.test_parameter_imports import SCHEMA, URI

ROOT='/api/projects/harbour/redeye-import-tests'
KEYS=[{'id':10,'name':'Existing Note'},{'id':20,'name':'Pilot Rating'}]
REV={'id':101,'version':1,'status':'Approved','timestamp':'2026-11-09T09:00:00Z'}
DOC={'id':777,'number':'TEST-777','title':'Disposable test artefact','modified':'2026-11-09T09:00:00Z','metadata':[{'id':1,'key_id':10,'key_name':'Existing Note','value':'keep exactly'}], 'revisions':[REV], 'state':{'is_modifiable':True,'name':'Approved'},'groups':[{'id':7,'name':'Disposable test group'}], 'geometry':'Feature'}


@pytest.fixture
def portal(tmp_path,monkeypatch):
    path=tmp_path/'pilot.db';c=TestClient(create_app(path,demo=True));c.post('/api/demo/session',json={'user_id':'north-owner'})
    monkeypatch.setenv('ORBIT_ENABLE_LIVE_READS','1')
    with sqlite3.connect(path) as db:db.execute('INSERT INTO bsdd_settings VALUES(?,?,1,?,?,?)',('north','harbour',json.dumps(SCHEMA),'fixture','north-owner'))
    result=c.post('/api/projects/harbour/read-connections',json={'name':'RedEye pilot fixture','provider':'redeye','base_url':'https://api.redeyedms.com','auth_header':'Authorization','auth_prefix':'Bearer','vendor_settings_confirmed':True,'approved_test_access':True,'evidence_note':'Synthetic test administrator approval'})
    ident=result.json()['id'];c.put('/api/projects/harbour/read-connections/'+ident+'/credential',json={'secret':'synthetic-pilot-key'})
    state={'doc':copy.deepcopy(DOC),'keys':copy.deepcopy(KEYS),'history':{'revision':copy.deepcopy(REV)},'posts':0,'calls':[],'post_mode':'normal','read_mode':'normal'}
    def request(base,secret,cfg,method,api_path,payload=None,transport=None):
        state['calls'].append((method,api_path));assert base=='https://api.redeyedms.com' and secret=='synthetic-pilot-key'
        if method=='POST':
            assert api_path=='/api/v1/artefacts/777';state['posts']+=1;state['payload']=payload
            if state['post_mode']=='reject':raise ProviderError('access_denied','Synthetic rejection')
            if state['post_mode']!='no_change':
                state['doc']['metadata']=[{'id':100+n,'key_id':next(k['id'] for k in state['keys'] if k['name']==row['name']),'key_name':row['name'],'value':row['value'][0]} for n,row in enumerate(payload['metadata'])]
                state['doc']['modified']='2026-11-09T10:00:00Z'
            if state['post_mode']=='timeout_after_write':raise ProviderError('transport_uncertain','Synthetic timeout after acceptance')
            if state['post_mode']=='damage':state['doc']['metadata'][0]['value']='unexpected'
            return None
        if state['read_mode']=='fail':raise ProviderError('read_failed','Synthetic read failure')
        if api_path=='/api/v1/metadata-keys':return copy.deepcopy(state['keys'])
        if api_path.endswith('/versionhistory'):return copy.deepcopy(state['history'])
        return copy.deepcopy(state['doc'])
    monkeypatch.setattr(pilot,'request_vendor',request)
    return c,path,ident,state


def inspect(c,ident):
    r=c.post(ROOT+'/inspect',json={'connection_id':ident,'artefact_id':777});assert r.status_code==200,r.text
    return r.json()


def preview(c,inspection,**changes):
    body={'inspection_id':inspection['id'],'property_uri':URI,'metadata_key_id':20,'expected_revision_id':101,'approved_status':'Approved','value':60,'evidence_note':'Synthetic disposable single-revision test evidence', 'disposable_isolated_target':True,'current_approved_revision_confirmed':True,'metadata_contract_confirmed':True,'mapping_type_units_confirmed':True,**changes}
    r=c.post(ROOT,json=body);assert r.status_code==200,r.text
    return r.json()


def approve(c,test):
    c.post('/api/demo/session',json={'user_id':'north-approver'})
    r=c.post(ROOT+'/'+test['id']+'/approve',json={'digest':test['digest']});assert r.status_code==200,r.text
    c.post('/api/demo/session',json={'user_id':'north-owner'})


def enable(monkeypatch,ident):
    monkeypatch.setenv('ORBIT_ENABLE_REDEYE_WRITE_TESTS','1');monkeypatch.setenv('ORBIT_REDEYE_WRITE_TEST_TARGET',ident+'|api.redeyedms.com|777')


def execute(c,test,confirmation='WRITE 777'):
    return c.post(ROOT+'/'+test['id']+'/execute',json={'digest':test['digest'],'confirmation':confirmation})


def test_read_inspection_and_preview_do_not_write_or_enable_write(portal):
    c,_,ident,state=portal;inspection=inspect(c,ident);test=preview(c,inspection)
    assert state['posts']==0 and not test['preview']['blockers']
    assert test['preview']['payload']=={'metadata':[{'name':'Existing Note','value':['keep exactly']},{'name':'Pilot Rating','value':['60']}]}
    assert test['preview']['property_definition']['uri']==URI
    assert not c.get(ROOT).json()['write_opt_in']
    approve(c,test);assert execute(c,test).status_code==409 and state['posts']==0


def test_single_live_test_post_preserves_values_and_verifies_readback(portal,monkeypatch):
    c,path,ident,state=portal;test=preview(c,inspect(c,ident));approve(c,test);enable(monkeypatch,ident)
    r=execute(c,test);assert r.status_code==200,r.text
    assert r.json()['status']=='verified' and r.json()['read_back_verified'] and r.json()['http_200_observed'] and state['posts']==1
    assert execute(c,test).json()==r.json() and state['posts']==1
    with sqlite3.connect(path) as db:assert db.execute('SELECT count(*) FROM redeye_import_attempts').fetchone()[0]==1
    assert state['doc']['metadata'][0]['value']=='keep exactly'
    assert all(api_path.startswith('/api/v1/') for _,api_path in state['calls'])


@pytest.mark.parametrize('mode',['timeout_after_write','reject','no_change','damage'])
def test_uncertain_or_incorrect_result_never_replays_post(portal,monkeypatch,mode):
    c,_,ident,state=portal;test=preview(c,inspect(c,ident));approve(c,test);enable(monkeypatch,ident);state['post_mode']=mode
    r=execute(c,test);assert r.status_code==200 and r.json()['status']=='needs_review'
    assert state['posts']==1
    execute(c,test);assert state['posts']==1
    checked=c.post(ROOT+'/'+test['id']+'/recheck',json={'digest':test['digest']})
    assert checked.status_code==200 and state['posts']==1
    assert checked.json()['read_back_verified']==(mode=='timeout_after_write')
    assert checked.json()['initial_outcome']['reason']==r.json()['reason']


@pytest.mark.parametrize('target',['wrong|api.redeyedms.com|777','CONNECTION|qa-api.redeyedms.com|777','CONNECTION|api.redeyedms.com|778'])
def test_exact_target_allowlist_and_typed_confirmation(portal,monkeypatch,target):
    c,_,ident,state=portal;test=preview(c,inspect(c,ident));approve(c,test);enable(monkeypatch,ident)
    monkeypatch.setenv('ORBIT_REDEYE_WRITE_TEST_TARGET',target.replace('CONNECTION',ident));assert execute(c,test).status_code==409
    enable(monkeypatch,ident);assert execute(c,test,'WRITE 778').status_code==409 and state['posts']==0


@pytest.mark.parametrize('change',[{'disposable_isolated_target':False},{'current_approved_revision_confirmed':False},{'metadata_contract_confirmed':False},{'mapping_type_units_confirmed':False},{'expected_revision_id':999},{'approved_status':'Draft'},{'value':'60'},{'value':True},{'value':31},{'metadata_key_id':10}])
def test_missing_evidence_revision_mismatch_existing_value_and_type_errors_block(portal,change):
    c,_,ident,state=portal;test=preview(c,inspect(c,ident),**change);assert test['preview']['blockers']
    c.post('/api/demo/session',json={'user_id':'north-approver'})
    assert c.post(ROOT+'/'+test['id']+'/approve',json={'digest':test['digest']}).status_code==409 and state['posts']==0


@pytest.mark.parametrize('mutation',['metadata','revision','key','generation','schema','expiry'])
def test_fresh_preconditions_prevent_changed_target_write(portal,monkeypatch,mutation):
    c,path,ident,state=portal;test=preview(c,inspect(c,ident));approve(c,test);enable(monkeypatch,ident)
    if mutation=='metadata':state['doc']['metadata'][0]['value']='another change'
    if mutation=='revision':state['doc']['revisions'][0]['id']=202
    if mutation=='key':state['keys'][1]['name']='Renamed'
    with sqlite3.connect(path) as db:
        if mutation=='generation':db.execute('UPDATE read_connections SET generation=generation+1 WHERE id=?',(ident,))
        if mutation=='schema':db.execute("UPDATE bsdd_settings SET version=version+1 WHERE tenant_id='north'")
        if mutation=='expiry':db.execute('UPDATE redeye_import_tests SET expires=0 WHERE id=?',(test['id'],))
    assert execute(c,test).status_code==409 and state['posts']==0


def test_multiple_visible_revisions_block_the_first_pilot(portal):
    c,_,ident,state=portal;state['doc']['revisions'].append({**REV,'id':202,'status':'Draft'})
    test=preview(c,inspect(c,ident));assert test['preview']['blockers'] and state['posts']==0


def test_unsupported_multivalued_or_unknown_metadata_fails_closed(portal):
    c,_,ident,state=portal;state['doc']['metadata'].append({'id':2,'key_id':10,'key_name':'Existing Note','value':'second'})
    assert c.post(ROOT+'/inspect',json={'connection_id':ident,'artefact_id':777}).status_code==502
    state['doc']=copy.deepcopy(DOC);state['doc']['metadata'][0]['key_name']='unexpected'
    assert c.post(ROOT+'/inspect',json={'connection_id':ident,'artefact_id':777}).status_code==502


def test_roles_tenants_self_approval_and_approver_grants(portal,monkeypatch):
    c,path,ident,state=portal;test=preview(c,inspect(c,ident))
    for role in ['viewer','engineer','auditor','approver']:
        c.post('/api/demo/session',json={'user_id':'north-'+role});assert c.get(ROOT).status_code==200
        assert c.post(ROOT+'/inspect',json={'connection_id':ident,'artefact_id':777}).status_code==403
        assert execute(c,test).status_code==403
    c.post('/api/demo/session',json={'user_id':'south-owner'});assert c.get(ROOT).status_code==404
    c.post('/api/demo/session',json={'user_id':'north-owner'});approve(c,test);enable(monkeypatch,ident)
    with sqlite3.connect(path) as db:db.execute("DELETE FROM project_access WHERE user_id='north-approver'")
    assert execute(c,test).status_code==409 and state['posts']==0


def test_persisted_attempt_blocks_another_preview_and_interrupted_replay(portal,monkeypatch):
    c,path,ident,state=portal;inspection=inspect(c,ident);first=preview(c,inspection);second=preview(c,inspection)
    approve(c,first);approve(c,second);enable(monkeypatch,ident)
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO redeye_import_attempts VALUES(?,?,?,?)',(ident,777,first['id'],'fixture-interruption'))
        db.execute("UPDATE redeye_import_tests SET status='attempting' WHERE id=?",(first['id'],))
    assert execute(c,first).json()['automatic_retry'] is False and state['posts']==0
    assert execute(c,second).status_code==409 and state['posts']==0


def test_normal_read_gate_and_cancel_do_not_write(portal,monkeypatch):
    c,_,ident,state=portal;test=preview(c,inspect(c,ident));approve(c,test);enable(monkeypatch,ident)
    monkeypatch.delenv('ORBIT_ENABLE_LIVE_READS')
    assert execute(c,test).status_code==409 and state['posts']==0
    assert c.post(ROOT+'/'+test['id']+'/cancel',json={'digest':test['digest']}).status_code==200
    assert execute(c,test).status_code==409


def test_fixed_vendor_transport_headers_no_redirect_retry_or_secret_echo():
    cfg={'auth_header':'Authorization','auth_prefix':'Bearer'};seen=[]
    def handler(request):
        seen.append(request);assert request.url.host=='api.redeyedms.com' and request.headers['authorization']=='Bearer synthetic-key'
        assert request.headers['user-agent']=='ORBIT/0.10.0'
        if request.method=='POST':assert json.loads(request.content)=={'metadata':[]};return httpx.Response(200)
        return httpx.Response(200,json={'value':'public'})
    t=httpx.MockTransport(handler)
    assert pilot.request_vendor('https://api.redeyedms.com','synthetic-key',cfg,'GET','/api/v1/metadata-keys',transport=t)=={'value':'public'}
    pilot.request_vendor('https://api.redeyedms.com','synthetic-key',cfg,'POST','/api/v1/artefacts/777',{'metadata':[]},t)
    assert len(seen)==2
    with pytest.raises(ProviderError):pilot.request_vendor('https://api.redeyedms.com','synthetic-key',cfg,'GET','/api/v1/metadata-keys',transport=httpx.MockTransport(lambda _:httpx.Response(200,json={'echo':'synthetic-key'})))


@pytest.mark.parametrize('status',[301,401,403,429,500])
def test_vendor_failures_and_response_limits(status):
    cfg={'auth_header':'Authorization','auth_prefix':'Bearer'}
    with pytest.raises(ProviderError):pilot.request_vendor('https://api.redeyedms.com','synthetic-key',cfg,'POST','/api/v1/artefacts/777',{},httpx.MockTransport(lambda _:httpx.Response(status,headers={'Location':'https://other.example'})))
    with pytest.raises(ProviderError):pilot.request_vendor('https://api.redeyedms.com','synthetic-key',cfg,'GET','/api/v1/metadata-keys',transport=httpx.MockTransport(lambda _:httpx.Response(200,content=b'x'*1000001)))


def test_credential_material_is_not_persisted_as_metadata_or_evidence(portal):
    c,path,ident,state=portal;inspection=inspect(c,ident)
    r=c.post(ROOT,json={'inspection_id':inspection['id'],'property_uri':URI,'metadata_key_id':20,'expected_revision_id':101,'approved_status':'Approved','value':60,'evidence_note':'synthetic-pilot-key'})
    assert r.status_code==422 and 'synthetic-pilot-key' not in r.text
    with sqlite3.connect(path) as db:assert db.execute('SELECT count(*) FROM redeye_import_tests').fetchone()[0]==0


def test_permission_change_during_prewrite_network_read_blocks_post(portal,monkeypatch):
    c,path,ident,state=portal;test=preview(c,inspect(c,ident));approve(c,test);enable(monkeypatch,ident)
    original=pilot.request_vendor
    def revoke(*args,**kwargs):
        result=original(*args,**kwargs)
        if args[4].endswith('/versionhistory'):
            with sqlite3.connect(path) as db:db.execute("UPDATE memberships SET role='viewer' WHERE user_id='north-owner'")
        return result
    monkeypatch.setattr(pilot,'request_vendor',revoke)
    assert execute(c,test).status_code==403 and state['posts']==0


def test_readback_failure_after_http_200_and_get_only_recheck(portal,monkeypatch):
    c,_,ident,state=portal;test=preview(c,inspect(c,ident));approve(c,test);enable(monkeypatch,ident)
    original=pilot.request_vendor
    def fail_after_post(*args,**kwargs):
        result=original(*args,**kwargs)
        if args[3]=='POST':state['read_mode']='fail'
        return result
    monkeypatch.setattr(pilot,'request_vendor',fail_after_post)
    r=execute(c,test);assert r.json()['status']=='needs_review' and r.json()['http_200_observed'] and state['posts']==1
    state['read_mode']='normal';r=c.post(ROOT+'/'+test['id']+'/recheck',json={'digest':test['digest']})
    assert r.json()['read_back_verified'] and r.json()['http_200_observed'] and state['posts']==1


def test_self_approval_after_role_change_and_wrong_digest_fail(portal):
    c,path,ident,_=portal;test=preview(c,inspect(c,ident))
    with sqlite3.connect(path) as db:db.execute("UPDATE memberships SET role='approver' WHERE user_id='north-owner'")
    assert c.post(ROOT+'/'+test['id']+'/approve',json={'digest':test['digest']}).status_code==409
    c.post('/api/demo/session',json={'user_id':'north-approver'})
    assert c.post(ROOT+'/'+test['id']+'/approve',json={'digest':'0'*64}).status_code==409


def test_unverified_profile_url_credentials_are_not_exposed_in_pilot_listing(portal):
    c,path,ident,_=portal
    with sqlite3.connect(path) as db:
        config=json.loads(db.execute('SELECT configuration FROM read_connections WHERE id=?',(ident,)).fetchone()[0])
        config['base_url']='https://private-user:private-password@api.redeyedms.com'
        db.execute('UPDATE read_connections SET configuration=? WHERE id=?',(json.dumps(config),ident))
    assert 'private-password' not in c.get(ROOT).text
    assert 'Unverified API URL' in c.get(ROOT).text


def test_blank_target_is_filled_once_without_duplicate_payload_entries(portal,monkeypatch):
    c,_,ident,state=portal
    state['doc']['metadata'].append({'id':2,'key_id':20,'key_name':'Pilot Rating','value':''})
    test=preview(c,inspect(c,ident));assert not test['preview']['blockers'] and test['preview']['target_action']=='fill_blank'
    assert sum(m['name']=='Pilot Rating' for m in test['preview']['payload']['metadata'])==1
    approve(c,test);enable(monkeypatch,ident)
    assert execute(c,test).json()['read_back_verified'] and state['posts']==1


def arm(c,test):
    return c.post(ROOT+'/'+test['id']+'/arm',json={'digest':test['digest']})


def test_uat_browser_enable_disable_and_execute_without_terminal_target(portal,monkeypatch):
    c,_,ident,state=portal;monkeypatch.setenv('ORBIT_UAT_MODE','1')
    test=preview(c,inspect(c,ident));approve(c,test)
    assert execute(c,test).status_code==409
    assert arm(c,test).json()['written'] is False
    ctx=c.get(ROOT).json();assert ctx['uat_mode'] and ctx['armed_test_ids']==[test['id']] and not ctx['write_opt_in']
    assert state['posts']==0
    assert c.post(ROOT+'/'+test['id']+'/disarm',json={'digest':test['digest']}).json()['written'] is False
    assert execute(c,test).status_code==409
    assert arm(c,test).status_code==200
    assert execute(c,test).json()['status']=='verified' and state['posts']==1
    assert c.get(ROOT).json()['armed_test_ids']==[]
    assert arm(c,test).status_code==409


@pytest.mark.parametrize('change',['no_uat','unapproved','viewer','wrong_digest'])
def test_uat_enable_requires_exact_approval_scope_and_mode(portal,monkeypatch,change):
    c,_,ident,state=portal;monkeypatch.setenv('ORBIT_UAT_MODE','1')
    test=preview(c,inspect(c,ident))
    if change!='unapproved':approve(c,test)
    if change=='no_uat':monkeypatch.delenv('ORBIT_UAT_MODE')
    if change=='viewer':c.post('/api/demo/session',json={'user_id':'north-viewer'})
    if change=='wrong_digest':test['digest']='0'*64
    assert arm(c,test).status_code in {403,409} and state['posts']==0


@pytest.mark.parametrize('change',['session','expiry','restart','generation','dictionary','cross_origin'])
def test_uat_enable_does_not_bypass_existing_controls(portal,monkeypatch,change):
    c,path,ident,state=portal;monkeypatch.setenv('ORBIT_UAT_MODE','1')
    test=preview(c,inspect(c,ident));approve(c,test);assert arm(c,test).status_code==200
    if change=='session':c.post('/api/demo/session',json={'user_id':'north-owner'})
    if change=='expiry':
        original=pilot.time.time;at=original()+601
        monkeypatch.setattr(pilot.time,'time',lambda:at)
    if change=='restart':
        newer=TestClient(create_app(path,demo=True));newer.cookies.update(c.cookies);c=newer
    if change=='generation':
        with sqlite3.connect(path) as db:db.execute('UPDATE read_connections SET generation=generation+1 WHERE id=?',(ident,))
    if change=='dictionary':
        with sqlite3.connect(path) as db:db.execute('UPDATE bsdd_settings SET version=version+1')
    if change=='cross_origin':
        r=c.post(ROOT+'/'+test['id']+'/execute',json={'digest':test['digest'],'confirmation':'WRITE 777'},headers={'Origin':'https://other.example'})
        assert r.status_code==403 and state['posts']==0;return
    assert execute(c,test).status_code==409 and state['posts']==0


def test_uat_permission_is_only_for_one_exact_preview(portal,monkeypatch):
    c,_,ident,state=portal;monkeypatch.setenv('ORBIT_UAT_MODE','1')
    inspection=inspect(c,ident);first=preview(c,inspection);second=preview(c,inspection)
    approve(c,first);approve(c,second)
    assert arm(c,first).status_code==200
    assert execute(c,second).status_code==409 and state['posts']==0
    assert arm(c,second).status_code==200
    assert execute(c,first).status_code==409 and state['posts']==0
    assert execute(c,second).json()['status']=='verified' and state['posts']==1
