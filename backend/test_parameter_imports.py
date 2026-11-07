import copy
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.parameter_imports import definition, validate_value

ROOT='/api/projects/harbour/parameter-imports'
URI='https://identifier.buildingsmart.org/uri/example/test/2024/class/Wall/prop/General/Rating'
PROP={'uri':URI,'propertyUri':'https://identifier.buildingsmart.org/uri/example/test/2024/prop/Rating','propertyCode':'Rating','propertySet':'General','name':'Rating','dataType':'Integer','propertyValueKind':'Single','unit':'minute','allowedValues':[{'value':'30'},{'value':'60'}]}
SCHEMA={'enabled':True,'dictionary':{'uri':'https://identifier.buildingsmart.org/uri/example/test/2024','name':'Synthetic standard','version':'2024'},'class':{'uri':URI.split('/prop/')[0],'name':'Wall'},'properties':[PROP]}


@pytest.fixture
def portal(tmp_path):
    path=tmp_path/'parameters.db';c=TestClient(create_app(path,demo=True))
    with sqlite3.connect(path) as db:db.execute('INSERT INTO bsdd_settings VALUES(?,?,1,?,?,?)',('north','harbour',json.dumps(SCHEMA),'synthetic-time','north-owner'))
    c.post('/api/demo/session',json={'user_id':'north-owner'})
    doc=c.get('/api/projects/harbour/connections/north-redeye/documents').json()[0]['id']
    return c,path,doc


def request(doc=None,**changes):
    return {'target_kind':'synthetic','target_id':'north-redeye','fields':[{'property_uri':URI,'target_name':'General.Rating','required':False,'unit':''}],'value_rows':[{'document_id':doc,'values':{URI:60}}] if doc else [],**changes}


def preview(c,body):
    response=c.post(ROOT,json=body)
    assert response.status_code==200,response.text
    return response.json()


def approve(c,j):
    c.post('/api/demo/session',json={'user_id':'north-approver'})
    r=c.post(ROOT+'/'+j['id']+'/approve',json={'digest':j['digest']})
    assert r.status_code==200,r.text
    c.post('/api/demo/session',json={'user_id':'north-owner'})


def execute(c,j):return c.post(ROOT+'/'+j['id']+'/execute',json={'digest':j['digest']})


def test_definition_value_import_readback_persistence_and_idempotent_replay(portal):
    c,path,doc=portal;j=preview(c,request(doc))
    assert not j['preview']['blockers'] and j['preview']['fields'][0]['action']=='create'
    assert execute(c,j).status_code==409
    approve(c,j);r=execute(c,j)
    assert r.status_code==200,r.text
    receipt=r.json();assert receipt['definitions_created']==1 and receipt['values_written']==1 and receipt['read_back_verified'] and receipt['remote_writes']==0
    assert execute(c,j).json()==receipt
    register=c.get('/api/projects/harbour/parameter-register/north-redeye').json()
    assert len(register['fields'])==1 and register['values'][0]['value']==60
    assert register['fields'][0]['definition']['property_definition']['uri']==URI
    restarted=TestClient(create_app(path,demo=True));restarted.post('/api/demo/session',json={'user_id':'north-owner'})
    assert restarted.get('/api/projects/harbour/parameter-register/north-redeye').json()==register
    assert c.get('/api/projects/harbour/parameter-register/north-forma').json()['fields']==[]
    with sqlite3.connect(path) as db:assert db.execute("SELECT number FROM documents WHERE id=?",(doc,)).fetchone()[0].startswith('C-')


def test_definition_only_import_and_required_quality_findings(portal):
    c,_,_=portal;body=request();body['fields'][0]['required']=True;j=preview(c,body)
    assert j['preview']['values']==[] and not j['preview']['blockers']
    approve(c,j);assert execute(c,j).status_code==200
    q=c.get('/api/projects/harbour/parameter-register/north-redeye/quality').json()
    assert q['issue_count']==q['documents_checked'] and q['issue_count']>0 and q['parameters_checked']==1
    assert 'Required parameter' in q['findings'][0]['issue']


def test_existing_values_preserved_then_explicit_overwrite(portal):
    c,_,doc=portal;j=preview(c,request(doc));approve(c,j);execute(c,j)
    body=request(doc);body['value_rows'][0]['values'][URI]=30
    j=preview(c,body);assert j['preview']['fields'][0]['action']=='reuse' and j['preview']['values'][0]['action']=='skip_existing'
    approve(c,j);r=execute(c,j);assert r.json()['values_written']==0 and r.json()['values_skipped']==1
    j=preview(c,{**body,'overwrite_existing':True});approve(c,j);assert execute(c,j).json()['values_written']==1
    assert c.get('/api/projects/harbour/parameter-register/north-redeye').json()['values'][0]['value']==30


@pytest.mark.parametrize('mutation', ['schema','credential','document','field','value'])
def test_revalidation_rejects_changed_destination_schema_or_document(portal,mutation):
    c,path,doc=portal
    if mutation in {'field','value'}:
        initial=preview(c,request(doc));approve(c,initial);execute(c,initial)
    j=preview(c,request(doc));approve(c,j)
    with sqlite3.connect(path) as db:
        if mutation=='schema':db.execute("UPDATE bsdd_settings SET version=version+1 WHERE tenant_id='north'")
        elif mutation=='credential':db.execute("UPDATE connections SET generation=generation+1 WHERE id='north-redeye'")
        elif mutation=='document':db.execute("UPDATE documents SET revision='CHANGED' WHERE id=?",(doc,))
        elif mutation=='field':db.execute("UPDATE parameter_definitions SET field_key='Changed' WHERE connection_id='north-redeye'")
        else:db.execute("UPDATE parameter_values SET value='30' WHERE connection_id='north-redeye'")
    r=execute(c,j);assert r.status_code==409 and 'changed' in r.text


@pytest.mark.parametrize('value',[True,'60',31,None,{},[60]])
def test_typed_and_allowed_values_reject_invalid_updates(portal,value):
    c,_,doc=portal;body=request(doc);body['value_rows'][0]['values'][URI]=value
    j=preview(c,body);assert j['preview']['blockers']
    c.post('/api/demo/session',json={'user_id':'north-approver'})
    assert c.post(ROOT+'/'+j['id']+'/approve',json={'digest':j['digest']}).status_code==409


def test_required_omission_and_reserved_names_are_blockers(portal):
    c,_,doc=portal;body=request(doc);body['fields'][0]['required']=True;body['value_rows'][0]['values']={}
    assert preview(c,body)['preview']['blockers']
    body=request();body['fields'][0]['target_name']='revision'
    assert preview(c,body)['preview']['blockers']


def test_field_binding_changes_and_aliases_do_not_silently_change_definitions(portal):
    c,_,doc=portal;j=preview(c,request(doc));approve(c,j);execute(c,j)
    body=request();body['fields'][0]['required']=True
    assert preview(c,body)['preview']['blockers']
    body=request();body['fields'][0]['target_name']='Different.Name'
    assert 'already has another' in str(preview(c,body)['preview']['blockers'])


def test_scope_roles_self_approval_and_digest(portal):
    c,_,doc=portal;j=preview(c,request(doc))
    assert c.post(ROOT+'/'+j['id']+'/approve',json={'digest':j['digest']}).status_code==403
    for role in ['viewer','auditor','approver']:
        c.post('/api/demo/session',json={'user_id':'north-'+role})
        assert c.get(ROOT).status_code==200
        assert c.post(ROOT,json=request(doc)).status_code==403
        assert execute(c,j).status_code==403
    c.post('/api/demo/session',json={'user_id':'north-approver'})
    assert c.post(ROOT+'/'+j['id']+'/approve',json={'digest':'0'*64}).status_code==409
    c.post('/api/demo/session',json={'user_id':'south-owner'})
    assert c.get(ROOT).status_code==404
    assert c.get('/api/projects/riverside/parameter-imports/'+j['id']+'/package').status_code==404
    c.post('/api/demo/session',json={'user_id':'north-owner'})
    wrong=c.get('/api/projects/harbour/connections/north-forma/documents').json()[0]['id']
    assert c.post(ROOT,json=request(wrong)).status_code==404
    assert c.post(ROOT,json=request(target_id='south-redeye')).status_code==404


def test_approver_revocation_and_cancel_prevent_execution(portal):
    c,path,doc=portal;j=preview(c,request(doc));approve(c,j)
    with sqlite3.connect(path) as db:db.execute("DELETE FROM project_access WHERE user_id='north-approver'")
    assert execute(c,j).status_code==409
    assert c.post(ROOT+'/'+j['id']+'/cancel',json={'digest':j['digest']}).status_code==200
    assert execute(c,j).status_code==409


def test_expiry_and_dictionary_disabled_prevent_approval(portal):
    c,path,doc=portal;j=preview(c,request(doc))
    with sqlite3.connect(path) as db:db.execute('UPDATE parameter_imports SET expires=0 WHERE id=?',(j['id'],))
    c.post('/api/demo/session',json={'user_id':'north-approver'})
    assert c.post(ROOT+'/'+j['id']+'/approve',json={'digest':j['digest']}).status_code==409
    c.post('/api/demo/session',json={'user_id':'north-owner'})
    with sqlite3.connect(path) as db:db.execute("UPDATE bsdd_settings SET configuration='{}' WHERE tenant_id='north'")
    assert c.post(ROOT,json=request(doc)).status_code==409


def test_unknown_property_and_duplicate_names_rejected(portal):
    c,_,_=portal;body=request();body['fields'][0]['property_uri']='not-selected'
    assert c.post(ROOT,json=body).status_code==422
    body=request();body['fields']*=2
    assert c.post(ROOT,json=body).status_code==422


def test_readback_failure_rolls_back_whole_transaction(portal):
    c,path,doc=portal;j=preview(c,request(doc));approve(c,j)
    with sqlite3.connect(path) as db:
        db.execute("CREATE TRIGGER corrupt_value AFTER INSERT ON parameter_values BEGIN UPDATE parameter_values SET value='30' WHERE field_id=NEW.field_id; END")
    assert execute(c,j).status_code==409
    assert c.get('/api/projects/harbour/parameter-register/north-redeye').json()['fields']==[]
    with sqlite3.connect(path) as db:assert db.execute('SELECT status FROM parameter_imports WHERE id=?',(j['id'],)).fetchone()[0]=='approved'


def test_live_connections_produce_blocked_packages_without_network(portal,monkeypatch):
    import httpx
    c,_,_=portal
    live=c.post('/api/projects/harbour/read-connections',json={'name':'Live RedEye','provider':'redeye','base_url':'https://api.redeyedms.com','auth_header':'Authorization','auth_prefix':'Bearer'}).json()['id']
    def no_transport(*a,**kw):raise AssertionError('No vendor requests expected')
    monkeypatch.setattr(httpx.HTTPTransport,'handle_request',no_transport)
    j=preview(c,request(target_kind='live',target_id=live))
    assert not j['preview']['synthetic'] and j['preview']['blockers'] and not j['preview']['remote_writes_available']
    package=c.get(ROOT+'/'+j['id']+'/package').json()
    assert package['format']=='ORBIT_PARAMETER_IMPORT_REVIEW_V1' and package['vendor_native_format'] is False
    c.post('/api/demo/session',json={'user_id':'north-approver'})
    assert c.post(ROOT+'/'+j['id']+'/approve',json={'digest':j['digest']}).status_code==409


@pytest.mark.parametrize('datatype,value,valid',[('String','Steel',True),('String',60,False),('Boolean',True,True),('Boolean',1,False),('Real',1.2,True),('Real',False,False),('Real',float('inf'),False),('Real',10**400,False),('Integer',1.0,False)])
def test_native_type_validation(datatype,value,valid):
    spec,_=definition({**PROP,'dataType':datatype,'allowedValues':[]},{'target_name':'Test','unit':'','required':False})
    assert (not validate_value(value,spec))==valid


def test_units_lists_and_unsupported_metadata():
    spec,errors=definition({**PROP,'unit':'','units':['mm','m']},{'target_name':'Test','unit':'','required':False});assert errors
    spec,errors=definition(PROP,{'target_name':'Test','unit':'m','required':False});assert errors
    spec,errors=definition({**PROP,'dataType':'Complex'},{'target_name':'Test','unit':'','required':False});assert errors
    spec,errors=definition({**PROP,'propertyValueKind':'List'},{'target_name':'Test','unit':'','required':False});assert not errors
    assert not validate_value([30,60],spec) and validate_value([],spec)


def test_same_actor_cannot_approve_after_role_change(portal):
    c,path,doc=portal;j=preview(c,request(doc))
    with sqlite3.connect(path) as db:db.execute("UPDATE memberships SET role='approver' WHERE user_id='north-owner'")
    assert c.post(ROOT+'/'+j['id']+'/approve',json={'digest':j['digest']}).status_code==409


def test_individual_value_rows_are_distinct_and_optional_omission_is_preserved(portal):
    c,_,doc=portal
    docs=c.get('/api/projects/harbour/connections/north-redeye/documents').json()
    body=request(doc);body['value_rows'].append({'document_id':docs[1]['id'],'values':{URI:30}})
    j=preview(c,body);approve(c,j);assert execute(c,j).json()['values_written']==2
    values=c.get('/api/projects/harbour/parameter-register/north-redeye').json()['values']
    assert sorted(v['value'] for v in values)==[30,60]
    body=request(doc);body['value_rows'][0]['values']={}
    j=preview(c,body);assert not j['preview']['values'] and not j['preview']['blockers']
