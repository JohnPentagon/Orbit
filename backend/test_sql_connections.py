import copy
import datetime
import decimal
import json
import sqlite3
import sys
import types
from unittest.mock import Mock

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend import sql_connections as sql
from backend import redeye_pilot

ROOT='/api/projects/harbour/sql-connections'
CONFIG={'name':'SQL fixture','server':'localhost','database':'OrbitFixture','auth_mode':'sql','username':'orbit_reader','approved_test_access':True}
OBJECT={'schema_name':'dbo','object_name':'Documents'}
COLUMNS=[{'name':'DocumentNumber','type':'nvarchar','nullable':False,'identity':False,'computed':False,'primary_key':True},{'name':'Title','type':'nvarchar','nullable':True,'identity':False,'computed':False,'primary_key':False}]
SAMPLE={'object':OBJECT,'kind':'USER_TABLE','columns':COLUMNS,'rows':[{'DocumentNumber':'D-001','Title':'  Drawing A  '},{'DocumentNumber':'D-002','Title':None}], 'truncated':False,'sample_limit':25,'scope':'Hand-authored SQL sample fixture'}


@pytest.fixture
def portal(tmp_path,monkeypatch):
    path=tmp_path/'sql.db';c=TestClient(create_app(path,demo=True));c.post('/api/demo/session',json={'user_id':'north-owner'})
    monkeypatch.setenv('ORBIT_ENABLE_LIVE_READS','1');monkeypatch.setattr(sql,'driver_status',lambda:{'available':True,'python_package':True,'required_driver':sql.DRIVER})
    state={'sample':copy.deepcopy(SAMPLE),'calls':[]}
    def query(cfg,password,choice=None):
        state['calls'].append((cfg,choice))
        assert password=='synthetic-sql-password'
        return {'objects':[{**OBJECT,'kind':'USER_TABLE'}],'truncated':False} if choice is None else copy.deepcopy(state['sample'])
    monkeypatch.setattr(sql,'query_database',query)
    ident=c.post(ROOT,json=CONFIG).json()['id'];c.put(ROOT+'/'+ident+'/credential',json={'password':'synthetic-sql-password'})
    target=c.post('/api/projects/harbour/read-connections',json={'name':'RedEye target','provider':'redeye','base_url':'https://api.redeyedms.com','auth_header':'Authorization','auth_prefix':'Bearer','vendor_settings_confirmed':True,'approved_test_access':True,'evidence_note':'Synthetic approved test target'}).json()['id']
    c.put('/api/projects/harbour/read-connections/'+target+'/credential',json={'secret':'synthetic-redeye-key'})
    monkeypatch.setattr(redeye_pilot,'request_vendor',lambda *a,**k:[{'id':20,'name':'Document Title'},{'id':21,'name':'Reference'}])
    return c,path,ident,target,state


def sample(c,ident):
    r=c.post(ROOT+'/'+ident+'/sample',json=OBJECT);assert r.status_code==200,r.text
    return r.json()


def body(snapshot,target_id,**changes):
    return {'name':'SQL to RedEye mapping','snapshot_id':snapshot['id'],'source_key':'DocumentNumber','target':{'kind':'read','id':target_id},'target_match_field':'number','rules':[{'source':'Title','target':'Document Title','transform':'trim','required':True,'default':'Untitled'}],**changes}


def fields(c,target):
    r=c.post(ROOT+'/target-fields',json={'kind':'read','id':target});assert r.status_code==200,r.text


def test_connect_sample_map_save_and_revise_without_any_writer(portal):
    c,path,ident,target,state=portal
    assert c.post(ROOT+'/'+ident+'/objects').json()['objects'][0]['object_name']=='Documents'
    s=sample(c,ident);fields(c,target)
    b=body(s,target);preview=c.post(ROOT+'/mapping-preview',json=b)
    assert preview.status_code==200,preview.text
    p=preview.json();assert p['rows'][0]['mapped_values']=={'Document Title':'Drawing A'}
    assert p['rows'][1]['mapped_values']=={'Document Title':'Untitled'} and p['field_inventory_verified']
    r=c.post(ROOT+'/mappings',json=b);assert r.status_code==200,r.text
    assert r.json()['written'] is False
    j=r.json();b.update(id=j['id'],expected_version=j['version'],name='Revised mapping')
    assert c.post(ROOT+'/mappings',json=b).json()['version']==2
    assert c.post(ROOT+'/mappings',json=b).status_code==409
    ctx=c.get(ROOT).json();assert ctx['mappings'][0]['version']==2
    assert 'synthetic-sql-password' not in json.dumps(ctx) and 'synthetic-redeye-key' not in json.dumps(ctx)
    with sqlite3.connect(path) as db:
        ciphertext=db.execute('SELECT secret_ciphertext FROM sql_connections').fetchone()[0]
        assert 'synthetic-sql-password' not in ciphertext
        assert db.execute('SELECT count(*) FROM redeye_metadata_updates').fetchone()[0]==0


@pytest.mark.parametrize('change',['bad_source','bad_target_field','source_generation','expired','target_generation','catalog_missing','catalog_expired','bad_key'])
def test_mapping_requires_current_scoped_snapshot_and_inventory(portal,change):
    c,path,ident,target,_=portal;s=sample(c,ident);fields(c,target);b=body(s,target)
    if change=='bad_source':b['rules'][0]['source']='Unknown'
    if change=='bad_target_field':b['rules'][0]['target']='Unknown'
    if change=='bad_key':b['source_key']='Unknown'
    with sqlite3.connect(path) as db:
        if change=='source_generation':db.execute('UPDATE sql_connections SET generation=generation+1')
        if change=='expired':db.execute('UPDATE sql_snapshots SET expires=0')
        if change=='target_generation':db.execute('UPDATE read_connections SET generation=generation+1')
        if change=='catalog_missing':db.execute('DELETE FROM sql_field_catalogs')
        if change=='catalog_expired':db.execute('UPDATE sql_field_catalogs SET expires=0')
    assert c.post(ROOT+'/mapping-preview',json=b).status_code in {409,422}


def test_sample_duplicate_null_and_omitted_matching_values_are_findings(portal):
    c,_,ident,target,state=portal
    state['sample']['rows']=[{'DocumentNumber':None,'Title':''},{'DocumentNumber':None,'Title':None},{'DocumentNumber':'[binary omitted]','Title':'[unsupported value omitted]'}]
    s=sample(c,ident);fields(c,target)
    p=c.post(ROOT+'/mapping-preview',json=body(s,target)).json()
    assert p['issues'] and p['rows'][0]['issues'] and p['rows'][1]['issues'] and p['rows'][2]['issues']


@pytest.mark.parametrize('user',['north-viewer','south-owner'])
def test_sql_connection_reads_credentials_and_mapping_mutations_are_scoped(portal,user):
    c,_,ident,target,_=portal;s=sample(c,ident);fields(c,target)
    c.post('/api/demo/session',json={'user_id':user})
    for route,method,data in [(ROOT,'post',CONFIG),(ROOT+'/'+ident+'/objects','post',None),(ROOT+'/'+ident+'/sample','post',OBJECT),(ROOT+'/'+ident+'/credential','put',{'password':'other'}),(ROOT+'/mapping-preview','post',body(s,target)),(ROOT+'/mappings','post',body(s,target))]:
        assert getattr(c,method)(route,json=data).status_code in {403,404}


def test_engineer_can_draft_from_scoped_existing_sample_but_cannot_contact_db(portal):
    c,_,ident,target,_=portal;s=sample(c,ident);fields(c,target)
    c.post('/api/demo/session',json={'user_id':'north-engineer'})
    assert c.post(ROOT+'/'+ident+'/objects').status_code==403
    assert c.post(ROOT+'/mappings',json=body(s,target)).status_code==200


@pytest.mark.parametrize('what',['credential','config'])
def test_changes_invalidate_samples_and_config_clears_credential(portal,what):
    c,_,ident,_,_=portal;sample(c,ident)
    if what=='credential':r=c.put(ROOT+'/'+ident+'/credential',json={'password':'replacement-password'})
    else:r=c.put(ROOT+'/'+ident,json={**CONFIG,'database':'OtherDatabase'})
    assert r.status_code==200
    row=c.get(ROOT).json()['connections'][0]
    assert row['generation']==3
    if what=='config':assert not row['credential_present']


@pytest.mark.parametrize('change',['role','generation'])
def test_read_rechecks_identity_and_generation_before_storing(portal,monkeypatch,change):
    c,path,ident,_,state=portal
    original=sql.query_database
    def query(*args,**kwargs):
        result=original(*args,**kwargs)
        with sqlite3.connect(path) as db:
            if change=='generation':db.execute('UPDATE sql_connections SET generation=generation+1')
            else:db.execute("UPDATE memberships SET role='viewer' WHERE tenant_id='north' AND user_id='north-owner'")
        return result
    monkeypatch.setattr(sql,'query_database',query)
    r=c.post(ROOT+'/'+ident+'/sample',json=OBJECT)
    assert r.status_code in {403,409}
    with sqlite3.connect(path) as db:assert db.execute('SELECT count(*) FROM sql_snapshots').fetchone()[0]==0


@pytest.mark.parametrize('settings',[{'server':'host;UID=admin'},{'server':'https://host'},{'server':'localhost\\SQLEXPRESS'},{'server':'169.254.169.254'},{'server':'0.0.0.0'},{'location':'azure','server':'localhost'},{'location':'azure','server':'name.database.windows.net','auth_mode':'windows'},{'port':0},{'username':''}])
def test_invalid_sql_profile_cannot_add_connection_options(portal,settings):
    c,_,_,_,_=portal
    assert c.post(ROOT,json={**CONFIG,**settings}).status_code==422


def test_odbc_options_are_escaped_tls_verified_and_no_write_intent():
    cfg=sql.Config(**{**CONFIG,'database':'a};UID=other;{','username':'reader};PWD=other'}).model_dump()
    text=sql.connection_string(cfg,'pass};TrustServerCertificate=yes;{')
    assert 'DATABASE={a}};UID=other;{}' in text
    assert 'PWD={pass}};TrustServerCertificate=yes;{}' in text
    assert 'Encrypt={yes}' in text and 'TrustServerCertificate={no}' in text and 'ApplicationIntent={ReadOnly}' in text


def test_projection_quotes_server_identifiers_and_bounds_large_types():
    assert sql.identifier('odd]name')=='[odd]]name]'
    assert sql.projection({'name':'big','type':'nvarchar'})=='CONVERT(nvarchar(2001),[big]) AS [big]'
    assert '[binary omitted]' in sql.projection({'name':'File','type':'varbinary'})
    assert '[unsupported value omitted]' in sql.projection({'name':'geo','type':'geography'})
    assert sql.cell(b'private binary')=='[binary omitted]'
    assert sql.cell(decimal.Decimal('123456789.123456789'))=='123456789.123456789'
    assert sql.cell(datetime.date(2026,11,10))=='2026-11-10'


def test_fixed_select_adapter_uses_bound_metadata_parameters_and_closes(monkeypatch):
    cursor=Mock();conn=Mock();conn.cursor.return_value=cursor
    cursor.fetchone.return_value=(42,'USER_TABLE')
    cursor.fetchmany.side_effect=[[(c['name'],c['type'],c['nullable'],c['identity'],c['computed'],c['primary_key']) for c in COLUMNS],[('D-001','Drawing')]]
    driver=types.SimpleNamespace(drivers=lambda:[sql.DRIVER],connect=Mock(return_value=conn))
    monkeypatch.setitem(sys.modules,'pyodbc',driver)
    choice={'schema_name':'dbo','object_name':'Docs]; DROP TABLE users;--'}
    result=sql.query_database(sql.Config(**CONFIG).model_dump(),'password',choice)
    calls=cursor.execute.call_args_list
    assert all(call.args[0].startswith('SELECT') for call in calls)
    assert calls[0].args[1:]==('dbo','Docs]; DROP TABLE users;--')
    assert 'FROM [dbo].[Docs]]; DROP TABLE users;--]' in calls[-1].args[0]
    assert result['rows'][0]['DocumentNumber']=='D-001' and conn.close.called
    assert driver.connect.call_args.kwargs=={'timeout':10,'autocommit':True}


def test_sql_exceptions_never_relay_raw_credentials(monkeypatch):
    driver=types.SimpleNamespace(drivers=lambda:[sql.DRIVER],connect=Mock(side_effect=RuntimeError('PWD=synthetic-secret; server detail')))
    monkeypatch.setitem(sys.modules,'pyodbc',driver)
    with pytest.raises(sql.SQLFailure) as err:sql.query_database(sql.Config(**CONFIG).model_dump(),'synthetic-secret')
    assert 'synthetic-secret' not in err.value.message and err.value.code=='sql_read_failed'


def test_sql_to_sql_fields_belong_to_selected_target_table(portal):
    c,_,ident,_,_=portal;s=sample(c,ident)
    other=c.post(ROOT,json={**CONFIG,'name':'Destination','database':'OtherDB'}).json()['id']
    c.put(ROOT+'/'+other+'/credential',json={'password':'synthetic-sql-password'})
    dst=sample(c,other)
    b=body(s,other,target={'kind':'sql','id':other},target_snapshot_id=dst['id'],target_match_field='DocumentNumber',rules=[{'source':'Title','target':'Title'}])
    r=c.post(ROOT+'/mapping-preview',json=b);assert r.status_code==200,r.text
    assert r.json()['field_inventory_verified'] and r.json()['target_object']==OBJECT
    b['target_snapshot_id']=s['id']
    assert c.post(ROOT+'/mapping-preview',json=b).status_code==422


def test_prepared_samples_are_project_data_without_new_sql_reads(portal):
    c,_,ident,_,state=portal;s=sample(c,ident);count=len(state['calls'])
    c.post('/api/demo/session',json={'user_id':'north-engineer'})
    assert c.get(ROOT).json()['samples'][0]['id']==s['id']
    assert c.get(ROOT+'/snapshots/'+s['id']).json()['snapshot']['rows']==s['snapshot']['rows']
    assert len(state['calls'])==count
    c.post('/api/demo/session',json={'user_id':'south-owner'})
    assert c.get('/api/projects/riverside/sql-connections/snapshots/'+s['id']).status_code==404


def test_read_opt_out_and_unconfirmed_profiles_do_not_contact_sql(portal,monkeypatch):
    c,_,ident,_,state=portal;monkeypatch.delenv('ORBIT_ENABLE_LIVE_READS')
    assert c.post(ROOT+'/'+ident+'/objects').status_code==409 and not state['calls']


def test_missing_driver_returns_actionable_status(portal,monkeypatch):
    c,_,ident,_,_=portal
    def query(*args,**kwargs):raise sql.SQLFailure('driver_missing','Install optional SQL support and ODBC Driver 18.')
    monkeypatch.setattr(sql,'query_database',query)
    r=c.post(ROOT+'/'+ident+'/objects');assert r.status_code==409
    assert r.json()['detail']['code']=='driver_missing'


def test_large_sql_integer_precision_is_preserved_as_text():
    assert sql.cell(9223372036854775807)=='9223372036854775807'
    assert sql.cell(123)==123


def test_credential_material_cannot_be_mapping_default(portal):
    c,_,ident,target,_=portal;s=sample(c,ident);fields(c,target)
    b=body(s,target);b['rules'][0]['default']='synthetic-sql-password'
    assert c.post(ROOT+'/mappings',json=b).status_code==422
