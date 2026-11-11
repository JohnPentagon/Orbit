import copy
import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from backend import bsdd
from backend.main import create_app
from backend.providers import ProviderError

URI='https://identifier.buildingsmart.org/uri/example/engineering/2024'
CLASS=URI+'/class/Wall'
PROPERTY=CLASS+'/prop/General/FireRating'
DICTIONARY={'uri':URI,'name':'Synthetic engineering','version':'2024','status':'Preview','license':'Synthetic test licence'}
PROP={'uri':PROPERTY,'propertyUri':URI+'/prop/FireRating','name':'Fire Rating','propertyCode':'FireRating','propertySet':'General','dataType':'String','definition':'Synthetic fire rating','units':['minute'],'allowedValues':[{'value':'30'},{'value':'60'}]}
DETAIL={'uri':CLASS,'dictionaryUri':URI,'name':'Wall','code':'Wall','classProperties':[PROP]}


def contract(path,params):
    if path=='/api/Dictionary/v1':
        return {'dictionaries':[DICTIONARY],'offset':int(params.get('Offset',0)),'count':1,'totalCount':1}
    if path=='/api/Dictionary/v1/Classes':
        return {'uri':URI,'classes':[{'uri':CLASS,'name':'Wall','code':'Wall'}],'classesOffset':int(params.get('Offset',0)),'classesCount':1,'classesTotalCount':1}
    if path=='/api/Class/v1':return copy.deepcopy(DETAIL)
    raise AssertionError(path)


@pytest.fixture
def portal(tmp_path,monkeypatch):
    monkeypatch.setattr(bsdd,'fetch',lambda path,params,transport=None:contract(path,params))
    path=tmp_path/'bsdd.db';c=TestClient(create_app(path,demo=True))
    c.post('/api/demo/session',json={'user_id':'north-owner'})
    return c,path


ROOT='/api/projects/harbour/bsdd'
def selection(**changes):return {'version':0,'enabled':True,'dictionary_uri':URI,'class_uri':CLASS,'property_uris':[PROPERTY],**changes}


def test_optional_project_selection_pins_server_definitions_and_survives_restart(portal):
    c,path=portal
    assert c.get(ROOT).json()['configuration']['enabled'] is False
    assert c.get(ROOT+'/dictionaries').status_code==200
    assert c.get(ROOT+'/classes',params={'dictionary_uri':URI}).status_code==200
    assert c.get(ROOT+'/class',params={'dictionary_uri':URI,'class_uri':CLASS}).status_code==200
    saved=c.put(ROOT,json=selection()).json()
    assert saved['version']==1
    cfg=saved['configuration'];assert cfg['dictionary']['version']=='2024'
    assert cfg['properties'][0]['dataType']=='String' and cfg['properties'][0]['allowedValues']==PROP['allowedValues']
    assert cfg['properties'][0]['units']==['minute'] and cfg['verified_at']
    assert 'required' not in cfg['properties'][0]
    other=TestClient(create_app(path,demo=True));other.post('/api/demo/session',json={'user_id':'north-owner'})
    assert other.get(ROOT).json()['configuration']==cfg
    assert c.put(ROOT,json=selection()).status_code==409
    audit=c.get('/api/projects/harbour/audit').json()
    assert any(a['action']=='bsdd.selection_saved' for a in audit)


def test_reads_do_not_save_and_no_network_on_local_load_or_clear(portal,monkeypatch):
    c,_=portal
    c.get(ROOT+'/dictionaries')
    assert c.get(ROOT).json()['version']==0
    assert c.put(ROOT,json=selection()).status_code==200
    def never(*a,**kw):raise AssertionError('No external call expected')
    monkeypatch.setattr(bsdd,'fetch',never)
    assert c.get(ROOT).status_code==200
    cleared=c.put(ROOT,json=selection(version=1,enabled=False,dictionary_uri='',class_uri='',property_uris=[]))
    assert cleared.status_code==200 and cleared.json()['configuration']['dictionary'] is None


@pytest.mark.parametrize('change',[
 {'dictionary_uri':'https://attacker.example/uri/a/b/c'},
 {'class_uri':'https://identifier.buildingsmart.org/uri/other/dictionary/2024/class/Wall'},
 {'property_uris':[URI+'/prop/not-in-class']},
 {'property_uris':[PROPERTY,PROPERTY]},
 {'dictionary_uri':'','class_uri':'','property_uris':[]},
 {'dictionary_uri':'','class_uri':CLASS},
 {'property_uris':[PROPERTY],'class_uri':''},
 {'configuration':{'dictionary':{'uri':'forged'}}},
])
def test_selection_rejects_cross_dictionary_forged_or_incomplete_inputs(portal,change):
    c,_=portal
    assert c.put(ROOT,json=selection(**change)).status_code==422
    assert c.get(ROOT).json()['version']==0


def test_failure_keeps_saved_project_definition(portal,monkeypatch):
    c,_=portal;assert c.put(ROOT,json=selection()).status_code==200
    def failure(*a,**kw):raise ProviderError('bsdd_read_failed','Network unavailable')
    monkeypatch.setattr(bsdd,'fetch',failure)
    assert c.put(ROOT,json=selection(version=1)).status_code==502
    assert c.get(ROOT).json()['version']==1


def test_permissions_tenant_and_project_grants(portal):
    c,path=portal;assert c.put(ROOT,json=selection()).status_code==200
    for role in ['viewer','engineer','approver','auditor']:
        c.post('/api/demo/session',json={'user_id':'north-'+role})
        assert c.get(ROOT).json()['configuration']['enabled']
        assert c.get(ROOT+'/dictionaries').status_code==403
        assert c.put(ROOT,json=selection(version=1)).status_code==403
    c.post('/api/demo/session',json={'user_id':'south-owner'})
    assert c.get(ROOT).status_code==404
    assert c.put(ROOT,json=selection(version=1)).status_code==404
    assert c.get('/api/projects/riverside/bsdd').json()['configuration']['dictionary'] is None
    c.post('/api/demo/session',json={'user_id':'north-owner'})
    with sqlite3.connect(path) as db:db.execute("DELETE FROM project_access WHERE user_id='north-owner'")
    assert c.get(ROOT).status_code==404
    assert c.get(ROOT+'/class',params={'dictionary_uri':URI,'class_uri':CLASS}).status_code==404


def test_permission_revoked_during_network_call_cannot_save(portal,monkeypatch):
    c,path=portal
    def revoke(api,params,transport=None):
        with sqlite3.connect(path) as db:db.execute("UPDATE memberships SET role='viewer' WHERE user_id='north-owner'")
        return contract(api,params)
    monkeypatch.setattr(bsdd,'fetch',revoke)
    assert c.put(ROOT,json=selection()).status_code==403
    assert c.get(ROOT).json()['version']==0


@pytest.mark.parametrize('value',[
 'http://identifier.buildingsmart.org/uri/a/b/c','https://identifier.buildingsmart.org.attacker.example/uri/a/b/c',
 'https://user:secret@identifier.buildingsmart.org/uri/a/b/c','https://identifier.buildingsmart.org:8443/uri/a/b/c',
 URI+'?token=secret',URI+'#fragment','https://identifier.buildingsmart.org/uri/a/b',
 'https://identifier.buildingsmart.org/uri/a/../c','https://identifier.buildingsmart.org/uri/a/%2f/c',
 'https://127.0.0.1/uri/a/b/c','file:///etc/passwd',
])
def test_identifier_is_not_a_general_url_fetcher(value):
    with pytest.raises(ProviderError):bsdd.identifier(value)


def test_fixed_api_host_headers_query_and_no_credentials():
    seen=[]
    def handler(request):
        seen.append(request)
        assert request.url.host=='api.bsdd.buildingsmart.org' and request.url.scheme=='https'
        assert request.headers['user-agent']=='ORBIT/0.13.1'
        assert 'authorization' not in request.headers and 'cookie' not in request.headers
        assert request.url.params['Uri']==URI
        return httpx.Response(200,json={'dictionaries':[DICTIONARY],'offset':0,'count':1,'totalCount':1})
    result=bsdd.dictionaries(uri=URI,transport=httpx.MockTransport(handler))
    assert result['dictionaries'][0]['uri']==URI and len(seen)==1


@pytest.mark.parametrize('status,code',[(302,'bsdd_unavailable'),(401,'access_denied'),(403,'access_denied'),(429,'rate_limited'),(500,'bsdd_unavailable')])
def test_transport_failures_are_safe_and_redirects_not_followed(status,code):
    def handler(request):return httpx.Response(status,headers={'Location':'https://attacker.example'},text='Secret-looking vendor error body')
    with pytest.raises(ProviderError) as raised:bsdd.fetch('/api/Dictionary/v1',{},httpx.MockTransport(handler))
    assert raised.value.code==code and 'vendor error' not in raised.value.message


def test_large_and_malformed_response_rejected():
    for response in [httpx.Response(200,content=b'x'*2_000_001),httpx.Response(200,text='not json'),httpx.Response(200,json=[])]:
        with pytest.raises(ProviderError):bsdd.fetch('/api/Dictionary/v1',{},httpx.MockTransport(lambda _:response))


@pytest.mark.parametrize('payload',[
 {'dictionaries':[],'offset':0,'count':1,'totalCount':1},
 {'dictionaries':[DICTIONARY],'offset':True,'count':1,'totalCount':1},
 {'dictionaries':[{**DICTIONARY,'uri':'https://attacker.example'}],'offset':0,'count':1,'totalCount':1},
])
def test_dictionary_contract_mismatch_is_not_silent_empty(monkeypatch,payload):
    monkeypatch.setattr(bsdd,'fetch',lambda *a:payload)
    with pytest.raises(ProviderError):bsdd.dictionaries()


def test_class_and_properties_must_match_requested_scope(monkeypatch):
    monkeypatch.setattr(bsdd,'fetch',lambda *a:{**DETAIL,'dictionaryUri':'other'})
    with pytest.raises(ProviderError):bsdd.class_details(URI,CLASS)
    monkeypatch.setattr(bsdd,'fetch',lambda *a:{**DETAIL,'classProperties':[PROP,PROP]})
    with pytest.raises(ProviderError):bsdd.class_details(URI,CLASS)


def test_public_cache_reuses_success_not_errors_and_expires(monkeypatch):
    real_client=httpx.Client
    calls=[]
    def handler(request):
        calls.append(request)
        if request.url.params.get('Uri')=='error':return httpx.Response(429)
        return httpx.Response(200,json={'sample':['original']})
    monkeypatch.setattr(bsdd.httpx,'Client',lambda **kwargs:real_client(**{**kwargs,'transport':httpx.MockTransport(handler)}))
    bsdd._CACHE.clear()
    try:
        first=bsdd.fetch('/api/Dictionary/v1',{'Uri':URI})
        first['sample'].append('modified')
        assert bsdd.fetch('/api/Dictionary/v1',{'Uri':URI})['sample']==['original'] and len(calls)==1
        key=('/api/Dictionary/v1',(('Uri',URI),))
        bsdd._CACHE[key]=(0,{'stale':True})
        bsdd.fetch('/api/Dictionary/v1',{'Uri':URI})
        assert len(calls)==2
        for _ in range(2):
            with pytest.raises(ProviderError):bsdd.fetch('/api/Dictionary/v1',{'Uri':'error'})
        assert len(calls)==4
    finally:bsdd._CACHE.clear()
