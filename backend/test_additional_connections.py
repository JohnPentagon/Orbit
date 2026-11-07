import copy
import json
import sqlite3
import sys
import types

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend import additional_connections as extra
from backend.providers import ProviderError
from backend.test_parameter_imports import SCHEMA, URI

ROOT='/api/projects/harbour/additional-connections'


def cfg(provider='procore',**changes):
    base={'name':'Additional test','provider':provider,'base_url':'https://api.procore.com','auth_mode':'bearer','approved_test_access':True,'vendor_settings_confirmed':True,'evidence_note':'Synthetic admin contract','scope_reference':'Synthetic approved scope'}
    if provider=='meridian':base.update(base_url='https://meridian.internal.example:8443/BCEnterprise',auth_mode='windows_integrated',view_id='DOC_TEST',filter_name='OnlyTest',execution='local_network')
    if provider in {'generic','maintenance_connection'}:base.update(base_url='https://custom.example/api',collection_path='/documents')
    return {**base,**changes}


@pytest.fixture
def portal(tmp_path,monkeypatch):
    path=tmp_path/'extra.db';c=TestClient(create_app(path,demo=True));c.post('/api/demo/session',json={'user_id':'north-owner'})
    monkeypatch.setenv('ORBIT_ENABLE_LIVE_READS','1')
    monkeypatch.setenv('ORBIT_EXTRA_ALLOWED_ORIGINS','https://api.procore.com,https://custom.example,https://meridian.internal.example:8443')
    with sqlite3.connect(path) as db:db.execute('INSERT INTO bsdd_settings VALUES(?,?,1,?,?,?)',('north','harbour',json.dumps(SCHEMA),'fixture','north-owner'))
    return c,path


def create(c,provider='procore',**changes):
    r=c.post(ROOT,json=cfg(provider,**changes));assert r.status_code==200,r.text
    return r.json()['id']


def item(c,ident):return next(r for r in c.get(ROOT).json()['connections'] if r['id']==ident)


def credential(c,ident):
    generation=item(c,ident)['generation']
    r=c.put(ROOT+'/'+ident+'/credential',json={'expected_generation':generation,'secret':'synthetic-additional-key'});assert r.status_code==200,r.text


def test_encrypted_credential_persistence_redaction_and_revision_invalidation(portal):
    c,path=portal;ident=create(c);credential(c,ident)
    data=item(c,ident);assert data['credential_present'] and data['readiness']['ready'] and not data['readiness']['remote_writes_enabled']
    assert 'synthetic-additional-key' not in json.dumps(data) and 'secret_ciphertext' not in json.dumps(data)
    with sqlite3.connect(path) as db:assert 'synthetic-additional-key' not in db.execute('SELECT secret_ciphertext FROM external_connections WHERE id=?',(ident,)).fetchone()[0]
    other=TestClient(create_app(path,demo=True));other.post('/api/demo/session',json={'user_id':'north-owner'});assert item(other,ident)['credential_present']
    r=c.put(ROOT+'/'+ident,json={**data['configuration'],'expected_generation':data['generation']});assert r.status_code==200
    assert not item(c,ident)['credential_present']
    assert c.put(ROOT+'/'+ident,json={**data['configuration'],'expected_generation':data['generation']}).status_code==409


@pytest.mark.parametrize('change,env', [({'approved_test_access':False},None),({'vendor_settings_confirmed':False},None),({'evidence_note':' '},None),({},'ORBIT_ENABLE_LIVE_READS'),({},'ORBIT_EXTRA_ALLOWED_ORIGINS')])
def test_read_gates_prevent_network(portal,monkeypatch,change,env):
    c,_=portal;ident=create(c,**change);credential(c,ident)
    if env:monkeypatch.delenv(env)
    monkeypatch.setattr(extra,'read_resources',lambda *a,**kw:(_ for _ in ()).throw(AssertionError('Gated read must not call transport')))
    assert c.post(ROOT+'/'+ident+'/read',json={'operation':'companies'}).status_code==409
    assert not item(c,ident)['readiness']['ready']


def test_windows_mode_and_fixture_never_claim_credentials_or_access(portal,monkeypatch):
    c,_=portal;ident=create(c,'meridian')
    monkeypatch.setattr(extra,'windows_auth_available',lambda:False)
    assert not item(c,ident)['readiness']['ready']
    assert c.put(ROOT+'/'+ident+'/credential',json={'expected_generation':1,'secret':'NeverStoreWindowsPassword'}).status_code==422
    r=c.post(ROOT+'/'+ident+'/fixture-check');assert r.status_code==200 and r.json()['synthetic']
    assert item(c,ident)['last_result'] is None


@pytest.mark.parametrize('url',['http://custom.example','https://user:password@custom.example','https://custom.example?token=abc','https://custom.example/#frag','https://custom.example/a/../b','https://custom.example/a%2fb','https://127.0.0.1','https://169.254.169.254','https://[::1]','https://[::ffff:127.0.0.1]'])
def test_invalid_origins_and_application_paths_rejected(portal,url):
    c,_=portal;assert c.post(ROOT,json=cfg('generic',base_url=url)).status_code==422


@pytest.mark.parametrize('change',[{'collection_path':'//evil.example'},{'collection_path':'/../secret'},{'scope_parameters':{'api_key':'not-in-query'}},{'scope_parameters':{'scope':'a\nb'}},{'collection_pointer':'data'},{'auth_mode':'api_key','auth_header':'Host'},{'auth_mode':'windows_integrated'}])
def test_generic_contract_limits(portal,change):
    assert portal[0].post(ROOT,json=cfg('generic',**change)).status_code==422


def test_procore_contract_headers_scope_and_paging():
    config=extra.ExternalConfig(**cfg(company_id='123')).model_dump()
    seen=[]
    def handler(request):
        seen.append(request);assert request.method=='GET' and request.url.host=='api.procore.com'
        assert request.headers['authorization']=='Bearer synthetic-key'
        assert request.url.params['page']=='2' and request.url.params['per_page']=='25'
        if request.url.path.endswith('/companies'):
            assert 'procore-company-id' not in request.headers and request.url.params['view']=='compact'
            return httpx.Response(200,json=[{'id':123,'name':'Example company'}])
        assert request.headers['procore-company-id']=='123'
        if request.url.path.endswith('/custom_field_definitions'):
            assert request.url.params['tool_name']=='admin'
            return httpx.Response(200,json={'data':[{'id':'f-1','label':'Rating','company_id':'123','data_type':'string'}]})
        assert request.url.params['company_id']=='123' and request.url.params['serializer_view']=='compact'
        return httpx.Response(200,json=[{'id':456,'name':'Example project'}])
    for op in ['companies','projects','field_definitions']:
        r=extra.read_resources(config,'synthetic-key',op,2,httpx.MockTransport(handler));assert r['returned']==1 and not r['synthetic']
    assert len(seen)==3


def test_meridian_contract_preserves_document_and_version_identity(monkeypatch):
    config=extra.ExternalConfig(**cfg('meridian',property_names=['Custom.Discipline'])).model_dump()
    def fake(url,params,cfg,secret,transport):
        assert url=='https://meridian.internal.example:8443/BCEnterprise/api/GetDocuments.ashx'
        assert params=={'VIEWID':'DOC_TEST','DOCFILTER':'OnlyTest','PAGEINDEX':0,'PAGESIZE':25,'pn':'Custom.Discipline'}
        assert secret=='';return copy.deepcopy(extra.EXPLORER_FIXTURE)
    monkeypatch.setattr(extra,'read_json',fake)
    r=extra.read_resources(config,'','documents');assert r['resources'][0]['id']!=r['resources'][0]['version_id'] and r['files_transferred']==0


def test_configured_rest_mapping_basic_header_and_redaction():
    config=extra.ExternalConfig(**cfg('maintenance_connection',auth_mode='basic',collection_pointer='/data/items',id_pointer='/resource_id',label_pointer='/title',scope_parameters={'project_id':'approved'})).model_dump()
    def handler(request):
        assert request.url.path=='/api/documents' and request.url.params['project_id']=='approved'
        assert request.headers['authorization'].startswith('Basic ')
        return httpx.Response(200,json={'data':{'items':[{'resource_id':'r-1','title':'Example secret-password'}]}})
    r=extra.read_resources(config,'user:secret-password','resources',transport=httpx.MockTransport(handler))
    assert r['resources'][0]['label']=='Example [REDACTED]'
    with pytest.raises(ProviderError):extra.pointer({'data':{}},'/data/items')


def test_field_inventory_rejects_other_company_and_missing_wrapper():
    config=extra.ExternalConfig(**cfg(company_id='123')).model_dump()
    for payload in [{'data':[{'id':'1','label':'Other','company_id':'999','data_type':'string'}]},[]]:
        with pytest.raises(ProviderError):extra.read_resources(config,'key','field_definitions',transport=httpx.MockTransport(lambda req:httpx.Response(200,json=payload)))


@pytest.mark.parametrize('status',[301,401,403,429,500])
def test_transport_fails_closed_and_never_follows_redirects(status):
    config=extra.ExternalConfig(**cfg()).model_dump()
    with pytest.raises(ProviderError):extra.read_resources(config,'key','companies',transport=httpx.MockTransport(lambda req:httpx.Response(status,headers={'Location':'https://other.example'})))


def test_response_byte_limit_and_shape_rejection():
    config=extra.ExternalConfig(**cfg()).model_dump()
    for response in [httpx.Response(200,content=b'x'*1_000_001),httpx.Response(200,json={}),httpx.Response(200,json=[{'id':True,'name':'Wrong'}])]:
        with pytest.raises(ProviderError):extra.read_resources(config,'key','companies',transport=httpx.MockTransport(lambda req:response))


def test_procore_named_selection_parent_generation_expiry(portal,monkeypatch):
    c,path=portal;ident=create(c);credential(c,ident)
    def fake(config,secret,operation,page):return {'operation':operation,'returned':1,'resources':[{'id':'123' if operation=='companies' else '456','label':'Company' if operation=='companies' else 'Project','kind':operation}],'synthetic':False,'coverage':'Transport fixture'}
    monkeypatch.setattr(extra,'read_resources',fake)
    assert c.post(ROOT+'/'+ident+'/read',json={'operation':'companies'}).status_code==200
    generation=item(c,ident)['generation']
    assert c.post(ROOT+'/'+ident+'/scope',json={'expected_generation':generation,'company_id':'999'}).status_code==409
    assert c.post(ROOT+'/'+ident+'/scope',json={'expected_generation':generation,'company_id':'123'}).status_code==200
    assert item(c,ident)['credential_present']
    assert c.post(ROOT+'/'+ident+'/read',json={'operation':'projects'}).status_code==200
    generation=item(c,ident)['generation']
    with sqlite3.connect(path) as db:db.execute('UPDATE external_discovery SET expires=0')
    assert c.post(ROOT+'/'+ident+'/scope',json={'expected_generation':generation,'company_id':'123','project_id':'456'}).status_code==409
    c.post(ROOT+'/'+ident+'/read',json={'operation':'projects'})
    assert c.post(ROOT+'/'+ident+'/scope',json={'expected_generation':generation,'company_id':'123','project_id':'456'}).status_code==200
    assert item(c,ident)['configuration']['project_name']=='Project'


def test_role_grant_and_connection_changes_during_read_discard_results(portal,monkeypatch):
    c,path=portal;ident=create(c);credential(c,ident)
    def changed(*args):
        with sqlite3.connect(path) as db:db.execute('UPDATE external_connections SET generation=generation+1 WHERE id=?',(ident,))
        return {'resources':[],'returned':0,'operation':'companies'}
    monkeypatch.setattr(extra,'read_resources',changed)
    assert c.post(ROOT+'/'+ident+'/read',json={'operation':'companies'}).status_code==409
    def revoked(*args):
        with sqlite3.connect(path) as db:db.execute("UPDATE memberships SET role='viewer' WHERE user_id='north-owner'")
        return {'resources':[],'returned':0,'operation':'companies'}
    monkeypatch.setattr(extra,'read_resources',revoked)
    assert c.post(ROOT+'/'+ident+'/read',json={'operation':'companies'}).status_code==403


def test_permissions_isolation_and_field_binding_snapshot_for_imports(portal):
    c,_=portal
    binding={'property_uri':URI,'external_field_id':'native-rating','external_field_name':'Rating','external_type':'integer','evidence':'Synthetic admin reference'}
    ident=create(c,'generic',bindings=[binding],desired_values=True)
    for role in ['viewer','engineer','approver','auditor']:
        c.post('/api/demo/session',json={'user_id':'north-'+role});assert c.get(ROOT).status_code==403
    c.post('/api/demo/session',json={'user_id':'south-owner'});assert c.get(ROOT).status_code==404
    c.post('/api/demo/session',json={'user_id':'north-owner'})
    r=c.post('/api/projects/harbour/parameter-imports',json={'target_kind':'additional','target_id':ident,'fields':[{'property_uri':URI,'target_name':'General.Rating'}]})
    assert r.status_code==200,r.text
    preview=r.json()['preview'];assert preview['blockers'] and preview['target']['manual_field_bindings'][0]['external_field_id']=='native-rating'
    assert preview['target']['field_bindings_verified'] is False
    assert any(t['id']==ident for t in c.get('/api/projects/harbour/parameter-imports').json()['targets'])


def test_native_procore_proposals_are_nonexecutable_and_do_not_erase_constraints(portal):
    c,path=portal;ident=create(c,company_id='123')
    # Integer with units/enumeration must not be silently projected as decimal.
    body={'target_kind':'additional','target_id':ident,'fields':[{'property_uri':URI,'target_name':'General.Rating'}]}
    r=c.post('/api/projects/harbour/parameter-imports',json=body).json();assert r['preview']['native_definition_proposals'][0]['body'] is None
    source=copy.deepcopy(SCHEMA);source['properties'][0].update(dataType='String',unit='',allowedValues=[])
    with sqlite3.connect(path) as db:db.execute('UPDATE bsdd_settings SET configuration=?,version=version+1 WHERE tenant_id=?',(json.dumps(source),'north'))
    r=c.post('/api/projects/harbour/parameter-imports',json=body).json();candidate=r['preview']['native_definition_proposals'][0]
    assert candidate['body']['custom_field_definition']['data_type']=='string' and '/123/' in candidate['path'] and candidate['executable'] is False


def test_windows_auth_transport_keeps_tls_redirect_and_delegation_guards(monkeypatch):
    calls={}
    class Response:
        status_code=200
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def iter_content(self,size):return iter([b'{"value":"fixture"}'])
    class Session:
        def __enter__(self):return self
        def __exit__(self,*a):pass
        def get(self,url,**kwargs):calls.update(kwargs);return Response()
    def auth(**kwargs):calls['delegate']=kwargs['delegate'];return object()
    monkeypatch.setattr(extra,'windows_auth_available',lambda:True)
    monkeypatch.setitem(sys.modules,'requests',types.SimpleNamespace(Session=Session))
    monkeypatch.setitem(sys.modules,'requests_negotiate_sspi',types.SimpleNamespace(HttpNegotiateAuth=auth))
    result=extra.read_json('https://meridian.example/api',{},extra.ExternalConfig(**cfg('meridian')).model_dump(),'')
    assert result['value']=='fixture' and calls['verify'] is True and calls['allow_redirects'] is False and calls['delegate'] is False
