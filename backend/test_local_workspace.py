import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app

NAMES={'workspace_name':'Field Systems','project_name':'Station upgrade','operator_name':'Local engineer'}
CONFIG={'name':'Approved RedEye','provider':'redeye','base_url':'https://api.redeyedms.com','auth_header':'Authorization','auth_prefix':'Bearer','vendor_settings_confirmed':True,'approved_test_access':True,'evidence_note':'Authorised local test access'}


@pytest.fixture
def portal(tmp_path):
    path=tmp_path/'local.db'
    c=TestClient(create_app(path,demo=False,local=True))
    return c,path


def create(c):
    r=c.post('/api/local/workspace',json=NAMES);assert r.status_code==200,r.text
    return c.get('/api/workspace').json()


def test_empty_workspace_does_not_seed_sample_records_or_users(portal):
    c,path=portal
    assert c.get('/api/health').json()['mode']=='local-workspace'
    assert c.get('/api/local/status').json()['initialised'] is False
    with sqlite3.connect(path) as db:
        for table in ['tenants','projects','users','documents','connections','read_connections','sql_connections']:
            assert db.execute('SELECT count(*) FROM '+table).fetchone()[0]==0
    w=create(c)
    assert w['tenant']['name']=='Field Systems' and w['projects'][0]['name']=='Station upgrade'
    assert w['identity']['role']=='owner' and not w['synthetic']
    project=w['projects'][0]['id']
    assert c.get('/api/projects/'+project+'/connection-summary').json()['connections']==[]
    with sqlite3.connect(path) as db:assert db.execute('SELECT count(*) FROM documents').fetchone()[0]==0


def test_no_tester_identity_routes_and_no_role_input_in_local_mode(portal):
    c,_=portal;create(c)
    assert c.get('/api/demo/identities').status_code==404
    assert c.post('/api/demo/session',json={'user_id':'north-owner'}).status_code==404
    assert c.post('/api/local/session',json={'owner_id':'unknown','role':'owner'}).status_code==422


def test_open_close_and_cookie_stability(portal):
    c,_=portal;w=create(c);token=c.cookies.get('orbit_session')
    for _ in range(3):assert c.get('/api/workspace').status_code==200
    assert c.cookies.get('orbit_session')==token
    c.delete('/api/session');assert c.get('/api/workspace').status_code==401
    assert c.post('/api/local/session',json={'owner_id':w['identity']['user_id']}).status_code==200
    assert c.cookies.get('orbit_session')!=token


def test_create_cannot_replace_existing_workspace(portal):
    c,path=portal;create(c)
    assert c.post('/api/local/workspace',json={**NAMES,'workspace_name':'Replacement'}).status_code==409
    assert c.get('/api/workspace').json()['tenant']['name']=='Field Systems'


def test_settings_and_new_project_preserve_working_credentials(portal):
    c,path=portal;w=create(c);project=w['projects'][0]['id']
    ident=c.post('/api/projects/'+project+'/read-connections',json=CONFIG).json()['id']
    c.put('/api/projects/'+project+'/read-connections/'+ident+'/credential',json={'secret':'synthetic-preserved-credential'})
    with sqlite3.connect(path) as db:before=db.execute('SELECT secret_ciphertext,generation FROM read_connections WHERE id=?',(ident,)).fetchone()
    r=c.put('/api/local/settings',json={'workspace_name':'Renamed workspace','project_name':'Renamed project','operator_name':'Operator','project_id':project})
    assert r.status_code==200,r.text
    updated=c.get('/api/workspace').json();assert updated['tenant']['name']=='Renamed workspace' and updated['operator_name']=='Operator'
    with sqlite3.connect(path) as db:assert db.execute('SELECT secret_ciphertext,generation FROM read_connections WHERE id=?',(ident,)).fetchone()==before
    summary=c.get('/api/projects/'+project+'/connection-summary').json()
    assert len(summary['connections'])==1 and summary['connections'][0]['credential_present'] and summary['connections'][0]['last_read'] is None
    assert 'synthetic-preserved-credential' not in str(summary)
    new=c.post('/api/local/projects',json={'name':'Second project'}).json()['id']
    assert c.get('/api/projects/'+new+'/connection-summary').json()['connections']==[]
    assert c.put('/api/local/settings',json={**NAMES,'project_id':'unknown'}).status_code==404


def test_legacy_database_preserves_real_connection_and_vault(tmp_path):
    path=tmp_path/'existing.db';old=TestClient(create_app(path,demo=True,local=False))
    old.post('/api/demo/session',json={'user_id':'north-owner'})
    ident=old.post('/api/projects/harbour/read-connections',json=CONFIG).json()['id']
    old.put('/api/projects/harbour/read-connections/'+ident+'/credential',json={'secret':'synthetic-existing-key'})
    vault=(tmp_path/'vault.key').read_bytes()
    modern=TestClient(create_app(path,demo=False,local=True))
    status=modern.get('/api/local/status').json()
    assert status['workspaces'][0]['user_id']=='north-owner' and status['workspaces'][0]['connection_count']==1
    modern.post('/api/local/session',json={'owner_id':'north-owner'})
    assert modern.get('/api/workspace').json()['connections']==[]
    result=modern.get('/api/projects/harbour/read-connections').json()['connections']
    assert result[0]['id']==ident and result[0]['credential_present']
    assert (tmp_path/'vault.key').read_bytes()==vault


def test_local_bootstrap_rejects_remote_peer_and_cross_origin(tmp_path):
    app=create_app(tmp_path/'peer.db',demo=False,local=True)
    remote=TestClient(app,client=('192.0.2.1',40000))
    assert remote.get('/api/local/status').status_code==403
    assert remote.post('/api/local/workspace',json=NAMES).status_code==403
    local=TestClient(app)
    assert local.post('/api/local/workspace',json=NAMES,headers={'Origin':'https://other.example'}).status_code==403


def test_local_routes_unavailable_in_test_mode(tmp_path):
    c=TestClient(create_app(tmp_path/'test.db',demo=True,local=False))
    assert c.get('/api/local/status').status_code==404
    assert c.post('/api/local/workspace',json=NAMES).status_code==404


@pytest.mark.parametrize('field',['workspace_name','project_name','operator_name'])
def test_blank_names_rejected_without_creating_data(portal,field):
    c,path=portal
    assert c.post('/api/local/workspace',json={**NAMES,field:'   '}).status_code==422
    with sqlite3.connect(path) as db:assert db.execute('SELECT count(*) FROM tenants').fetchone()[0]==0


@pytest.mark.parametrize('confirmed',[False,True])
def test_local_additional_origin_authorisation_is_per_confirmed_profile(portal,monkeypatch,confirmed):
    c,_=portal;w=create(c);project=w['projects'][0]['id']
    monkeypatch.setenv('ORBIT_ENABLE_LIVE_READS','1');monkeypatch.delenv('ORBIT_EXTRA_ALLOWED_ORIGINS',raising=False)
    root='/api/projects/'+project+'/additional-connections'
    config={'name':'Approved API','provider':'generic','base_url':'https://api.example.test/service','auth_mode':'bearer','vendor_settings_confirmed':confirmed,'approved_test_access':confirmed,'evidence_note':'Local operator approved this endpoint','scope_reference':'Approved test scope'}
    r=c.post(root,json=config);assert r.status_code==200,r.text
    ident=r.json()['id']
    r=c.put(root+'/'+ident+'/credential',json={'secret':'synthetic-local-api-token','expected_generation':1});assert r.status_code==200,r.text
    row=c.get(root).json()['connections'][0]
    assert row['readiness']['ready'] is confirmed
    assert not any('ORBIT_EXTRA_ALLOWED_ORIGINS' in i for i in row['readiness']['issues'])
    assert any('exact HTTPS origin' in i for i in row['readiness']['issues']) is (not confirmed)


def test_remote_peer_cannot_use_existing_local_owner_cookie(tmp_path):
    app=create_app(tmp_path/'peer-cookie.db',demo=False,local=True)
    c=TestClient(app);w=create(c)
    remote=TestClient(app,client=('192.0.2.5',40000));remote.cookies.update(c.cookies)
    assert remote.get('/api/workspace').status_code==403
    assert remote.get('/api/projects/'+w['projects'][0]['id']+'/connection-summary').status_code==403
