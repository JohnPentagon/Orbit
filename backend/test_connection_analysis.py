import json
import sqlite3
import time
import pytest
from fastapi.testclient import TestClient
from backend.main import create_app
from backend.connection_analysis import evaluate
from backend.record_data import fields
from backend.test_read_connections import setup

def configuration():
    return dict(source_key='number',target_key='name',key_mode='text',source_key_transform='trim',target_key_transform='filename_stem',rules=[dict(source_field='discipline',target_field='properties.Discipline',transform='trim',required=True,property_uri='',unit='',interpret_strings=False)])
def records(*rows):return {'records':[{'id':str(i),'values':v} for i,v in enumerate(rows)]}
def test_shared_business_key_and_reverse():
    a=records({'number':'D-001','discipline':' Civil '});b=records({'name':'D-001.pdf','properties.Discipline':'Civil'})
    c=configuration();assert evaluate(a,b,c,{})['counts']['matched']==1
    c.update(source_key='name',target_key='number',source_key_transform='filename_stem',target_key_transform='trim');c['rules'][0].update(source_field='properties.Discipline',target_field='discipline')
    assert evaluate(b,a,c,{})['counts']['matched']==1
@pytest.mark.parametrize('value,status',[(None,'invalid'),('','invalid'),('Mechanical','different')])
def test_required_and_different(value,status):
    r=evaluate(records({'number':'D','discipline':value}),records({'name':'D.pdf','properties.Discipline':'Civil'}),configuration(),{})
    assert r['counts'][status]==1

def test_duplicate_unknown_and_unmatched():
    a=records({'number':'D','discipline':'Civil'},{'number':'D','discipline':'Civil'},{'number':'E'})
    b=records({'name':'D.pdf','properties.Discipline':'Civil'},{'name':'F.pdf'})
    r=evaluate(a,b,configuration(),{})
    assert r['counts']['ambiguous']==1 and r['counts']['not_in_target_sample']==1 and r['counts']['not_in_source_sample']==1
    assert r['quality']['unknown_fields']==2
    assert evaluate(records(),b,configuration(),{})['outcome']=='no_data'

def test_extraction_omits_secrets_and_preserves_false_zero():
    v=fields({'password':'bad','nested':{'value':0,'enabled':False},'raw':'synthetic-key'},'synthetic-key')
    assert 'password' not in v and v['nested.value']==0 and v['nested.enabled'] is False and v['raw']=='[not captured]'

def test_endpoints_scope_freshness_and_roles(tmp_path):
    path=tmp_path/'analysis.db';app=create_app(path,demo=True);client=TestClient(app);client.post('/api/demo/session',json={'user_id':'north-owner'})
    left=setup(client);right=setup(client)
    app.state.profile_read=lambda project,ident,body,who: {'resources':[{'id':'native','label':'D.pdf','kind':'document','fields':{'number':'D','discipline':'Civil'}}],'coverage':'Bounded simulated adapter data'}
    url='/api/projects/harbour/analysis'
    captures=[]
    for ident in [left,right]:
        r=client.post(url+'/capture',json={'kind':'read','id':ident});assert r.status_code==200,r.text;captures.append(r.json()['snapshot']['id'])
    body=dict(name='Pair',source_snapshot=captures[0],target_snapshot=captures[1],source_key='number',target_key='number',rules=[dict(source_field='discipline',target_field='discipline',required=True)])
    m=client.post(url+'/mappings',json=body);assert m.status_code==200,m.text
    mid=m.json()['id'];r=client.post(url+f'/mappings/{mid}/compare',json={'expected_version':1});assert r.status_code==200,r.text
    assert r.json()['report']['counts']['matched']==1 and r.json()['report']['written'] is False
    report_id=r.json()['id'];assert client.get(url).json()['validation']['fresh_reports']==1
    with sqlite3.connect(path) as c:c.execute('UPDATE connection_snapshots SET expires=?',(int(time.time())-1,))
    assert client.post(url+f'/mappings/{mid}/compare',json={'expected_version':1}).status_code==409
    assert client.get(url).json()['validation']['stale_reports']==1
    client.post('/api/demo/session',json={'user_id':'north-viewer'})
    assert client.get(url+f'/reports/{report_id}').status_code==200
    assert client.post(url+'/capture',json={'kind':'read','id':left}).status_code==403
    assert client.post(url+'/mappings',json=body).status_code==403
    client.post('/api/demo/session',json={'user_id':'south-owner'})
    assert client.get(url+f'/reports/{report_id}').status_code in {403,404}

@pytest.mark.parametrize('reverse',[False,True])
def test_autodesk_meridian_adapter_capture_and_reverse(tmp_path,reverse):
    from backend.test_additional_connections import create
    app=create_app(tmp_path/'pair.db',demo=True);client=TestClient(app);client.post('/api/demo/session',json={'user_id':'north-owner'})
    a=setup(client);b=create(client,'meridian')
    app.state.profile_read=lambda *args: {'resources':[{'id':'aps-1','label':'D.pdf','kind':'document','fields':{'attributes.Number':'D','attributes.Discipline':'Civil'}}],'coverage':'Simulated first page'}
    app.state.additional_read=lambda *args: {'resources':[{'id':'mer-1','label':'Drawing','kind':'document','fields':{'properties.Number':'D','properties.Discipline':'Civil'}}],'coverage':'Simulated Explorer view'}
    base='/api/projects/harbour/analysis'
    samples=[]
    for kind,ident in [('read',a),('additional',b)]:
        r=client.post(base+'/capture',json={'kind':kind,'id':ident});assert r.status_code==200,r.text;samples.append(r.json()['snapshot']['id'])
    columns=['attributes','properties']
    if reverse:samples.reverse();columns.reverse()
    r=client.post(base+'/mappings',json={'name':'Platform pair','source_snapshot':samples[0],'target_snapshot':samples[1],'source_key':columns[0]+'.Number','target_key':columns[1]+'.Number','rules':[{'source_field':columns[0]+'.Discipline','target_field':columns[1]+'.Discipline'}]})
    assert r.status_code==200,r.text
    r=client.post(base+'/mappings/'+r.json()['id']+'/compare',json={'expected_version':1})
    assert r.status_code==200 and r.json()['report']['counts']['matched']==1


def test_saved_profile_edit_delete_retains_report(tmp_path):
    path=tmp_path/'profiles.db';app=create_app(path,demo=True);client=TestClient(app);client.post('/api/demo/session',json={'user_id':'north-owner'})
    connections=[setup(client),setup(client)]
    app.state.profile_read=lambda *args: {'resources':[{'id':'D-001','label':'Drawing','kind':'document','fields':{'number':'D-001','title':'Floor plan'}}],'coverage':'Profile fixture only'}
    base='/api/projects/harbour/analysis'
    snapshots=[client.post(base+'/capture',json={'kind':'read','id':ident}).json()['snapshot']['id'] for ident in connections]
    body=dict(name='Reusable parameters',source_snapshot=snapshots[0],target_snapshot=snapshots[1],rules=[dict(source_field='title',target_field='title')])
    saved=client.post(base+'/mappings',json=body);assert saved.status_code==200,saved.text;ident=saved.json()['id']
    assert client.post(base+f'/mappings/{ident}/compare',json={'expected_version':1}).status_code==409
    body.update(id=ident,expected_version=1,source_key='number',target_key='number',name='Edited parameters')
    edited=client.post(base+'/mappings',json=body);assert edited.status_code==200,edited.text;assert edited.json()['version']==2
    assert client.post(base+'/mappings',json=body).status_code==409
    report=client.post(base+f'/mappings/{ident}/compare',json={'expected_version':2});assert report.status_code==200,report.text;rid=report.json()['id']
    assert client.request('DELETE',base+f'/mappings/{ident}',json={'expected_version':1,'confirmed':True}).status_code==409
    assert client.request('DELETE',base+f'/mappings/{ident}',json={'expected_version':2,'confirmed':False}).status_code==422
    deleted=client.request('DELETE',base+f'/mappings/{ident}',json={'expected_version':2,'confirmed':True});assert deleted.status_code==200,deleted.text
    context=client.get(base).json();assert not context['mappings'];assert context['reports'][0]['mapping_deleted'];assert context['validation']['fresh_reports']==0 and context['validation']['stale_reports']==0
    assert client.get(base+'/reports/'+rid).status_code==200
    assert client.post(base+f'/mappings/{ident}/compare',json={'expected_version':3}).status_code==404
    with sqlite3.connect(path) as c:assert c.execute('SELECT count(*) FROM connection_mapping_history WHERE mapping_id=?',(ident,)).fetchone()[0]==3


def test_profile_schema_can_be_saved_after_data_expiry(tmp_path):
    path=tmp_path/'expired-profile.db';app=create_app(path,demo=True);client=TestClient(app);client.post('/api/demo/session',json={'user_id':'north-owner'})
    connections=[setup(client),setup(client)]
    app.state.profile_read=lambda *args: {'resources':[{'id':'D','label':'Drawing','kind':'document','fields':{'number':'D'}}],'coverage':'Fixture'}
    base='/api/projects/harbour/analysis';samples=[client.post(base+'/capture',json={'kind':'read','id':ident}).json()['snapshot']['id'] for ident in connections]
    with sqlite3.connect(path) as c:c.execute('UPDATE connection_snapshots SET expires=1')
    saved=client.post(base+'/mappings',json=dict(name='Saved field rules',source_snapshot=samples[0],target_snapshot=samples[1],source_key='number',target_key='number',rules=[dict(source_field='number',target_field='number')]))
    assert saved.status_code==200,saved.text
    assert client.post(base+'/mappings/'+saved.json()['id']+'/compare',json={'expected_version':1}).status_code==409
