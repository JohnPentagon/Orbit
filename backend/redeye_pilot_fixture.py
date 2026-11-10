"""Disposable browser-test factory only. Never uses a customer's DB or network.

Run on loopback: uvicorn backend.redeye_pilot_fixture:create_fixture_app --factory
--host 127.0.0.1 --port 8003; then frontend/redeye-import-test-smoke.mjs.
"""
import copy
import json
import os
import sqlite3
import tempfile
from pathlib import Path

import httpx
from cryptography.fernet import Fernet

from backend.main import create_app
from backend import redeye_pilot as pilot
from backend.test_redeye_pilot import DOC, KEYS, REV
from backend.test_parameter_imports import SCHEMA


def create_fixture_app():
    ident='11111111-2222-3333-4444-555555555555'
    os.environ['ORBIT_ENABLE_LIVE_READS']='1'
    os.environ['ORBIT_UAT_MODE']='1'
    os.environ.pop('ORBIT_ENABLE_REDEYE_WRITE_TESTS',None)
    os.environ.pop('ORBIT_REDEYE_WRITE_TEST_TARGET',None)
    path=Path(tempfile.mkdtemp(prefix='orbit-redeye-pilot-browser-'))/'portal.db'
    app=create_app(path,demo=True)
    source=copy.deepcopy(SCHEMA)
    source['properties'][0].update(dataType='String',unit='',allowedValues=[])
    config={'name':'RedEye browser fixture','provider':'redeye','base_url':'https://api.redeyedms.com','auth_header':'Authorization','auth_prefix':'Bearer','vendor_settings_confirmed':True,'approved_test_access':True,'evidence_note':'Browser fixture: no real vendor calls'}
    secret=Fernet((path.parent/'vault.key').read_bytes()).encrypt(b'synthetic-browser-pilot-key').decode()
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO bsdd_settings VALUES(?,?,1,?,?,?)',('north','harbour',json.dumps(source),'fixture','north-owner'))
        db.execute('INSERT INTO read_connections(id,tenant_id,project_id,name,provider,configuration,secret_ciphertext) VALUES(?,?,?,?,?,?,?)',(ident,'north','harbour',config['name'],'redeye',json.dumps(config),secret))
    state=copy.deepcopy(DOC)
    def fixture(base,secret,cfg,method,api_path,payload=None,transport=None):
        if method=='POST':
            assert api_path=='/api/v1/artefacts/777'
            state['metadata']=[{'id':100+i*100+n,'key_id':next(k['id'] for k in KEYS if k['name']==row['name']),'key_name':row['name'],'value':value} for i,row in enumerate(payload['metadata']) for n,value in enumerate(row['value'])]
            state['modified']='2026-11-09T10:00:00Z'
            return None
        if api_path=='/api/v1/metadata-keys':return copy.deepcopy(KEYS)
        if api_path.endswith('/versionhistory'):return {'revision':copy.deepcopy(REV)}
        return copy.deepcopy(state)
    pilot.request_vendor=fixture
    def forbidden(*a,**kw):raise AssertionError('Real vendor network is forbidden in browser fixtures')
    httpx.HTTPTransport.handle_request=forbidden
    # Also block the optional requests/SSPI transport if this fixture is run on Windows.
    from backend import additional_connections
    additional_connections.read_json=forbidden
    return app
