"""Empty local-workspace browser fixture; all external reads/writes are simulated."""
import copy
import os
import tempfile
from pathlib import Path

import httpx

from backend.main import create_app
from backend import read_connections, redeye_metadata, redeye_pilot, sql_connections
from backend.test_redeye_pilot import DOC, KEYS, REV
from backend.test_sql_connections import SAMPLE, OBJECT


def create_fixture_app():
    os.environ['ORBIT_ENABLE_LIVE_READS']='1';os.environ['ORBIT_UAT_MODE']='1'
    path=Path(tempfile.mkdtemp(prefix='orbit-portal-local-browser-'))/'portal.db'
    app=create_app(path,demo=False,local=True)
    state=copy.deepcopy(DOC)
    def vendor(base,secret,cfg,method,api_path,payload=None,transport=None):
        if method=='POST':
            assert api_path=='/api/v1/artefacts/777'
            state['metadata']=[{'id':100+i*100+n,'key_id':next(k['id'] for k in KEYS if k['name']==row['name']),'key_name':row['name'],'value':value} for i,row in enumerate(payload['metadata']) for n,value in enumerate(row['value'])]
            state['modified']='2026-11-11T10:00:00Z';return None
        if api_path=='/api/v1/metadata-keys':return copy.deepcopy(KEYS)
        if api_path.endswith('/versionhistory'):return {'revision':copy.deepcopy(REV)}
        assert api_path=='/api/v1/artefacts/777'
        return copy.deepcopy(state)
    redeye_pilot.request_vendor=vendor
    def read_page(provider,base,secret,operation,scope,header='',prefix='',transport=None):
        resources=[{'id':str(k['id']),'label':k['name'],'kind':'metadata_key'} for k in KEYS] if operation=='metadata_keys' else [{'id':'777','label':'TEST-777 · Disposable test artefact','kind':'artefact'}]
        return {'synthetic':False,'live_verified':True,'operation':operation,'resources':resources,'returned':len(resources),'coverage':'Simulated browser-fixture response; no customer HTTP.','response_shape':'raw_array'}
    read_connections.read_page=read_page;redeye_metadata.read_page=read_page
    def sql_query(cfg,password,choice=None):
        if choice is None:return {'objects':[{**OBJECT,'kind':'USER_TABLE'}],'truncated':False}
        return copy.deepcopy(SAMPLE)
    sql_connections.query_database=sql_query
    sql_connections.driver_status=lambda:{'available':True,'python_package':True,'required_driver':sql_connections.DRIVER}
    def forbidden(*a,**kw):raise AssertionError('Real vendor transport is forbidden by this browser fixture.')
    httpx.HTTPTransport.handle_request=forbidden
    from backend import additional_connections
    additional_connections.read_json=forbidden
    return app
