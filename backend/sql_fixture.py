"""Isolated SQL browser fixture. No real database or vendor transport is used."""
import copy
import json
import os
import sqlite3
import tempfile
from pathlib import Path

import httpx
from cryptography.fernet import Fernet

from backend.main import create_app
from backend import sql_connections as sql
from backend import redeye_pilot
from backend.test_sql_connections import OBJECT, SAMPLE


def create_fixture_app():
    os.environ['ORBIT_ENABLE_LIVE_READS']='1';os.environ['ORBIT_UAT_MODE']='1'
    path=Path(tempfile.mkdtemp(prefix='orbit-sql-browser-'))/'portal.db'
    app=create_app(path,demo=True)
    secret=Fernet((path.parent/'vault.key').read_bytes()).encrypt(b'synthetic-redeye-key').decode()
    cfg={'name':'RedEye SQL mapping fixture','provider':'redeye','base_url':'https://api.redeyedms.com','auth_header':'Authorization','auth_prefix':'Bearer','vendor_settings_confirmed':True,'approved_test_access':True,'evidence_note':'Isolated browser fixture only'}
    with sqlite3.connect(path) as db:
        db.execute('INSERT INTO read_connections(id,tenant_id,project_id,name,provider,configuration,secret_ciphertext) VALUES(?,?,?,?,?,?,?)',('11111111-2222-3333-4444-555555555555','north','harbour',cfg['name'],'redeye',json.dumps(cfg),secret))
    def query(cfg,password,choice=None):
        if password!='synthetic-sql-password':raise sql.SQLFailure('fixture_auth','Synthetic fixture password mismatch.')
        if choice is None:return {'objects':[{**OBJECT,'kind':'USER_TABLE'}],'truncated':False}
        if choice!=OBJECT:raise sql.SQLFailure('fixture_object','Unknown fixture SQL object.')
        return copy.deepcopy(SAMPLE)
    sql.query_database=query
    sql.driver_status=lambda:{'available':True,'python_package':True,'required_driver':sql.DRIVER}
    def vendor(base,secret,cfg,method,path,payload=None,transport=None):
        if method!='GET' or path!='/api/v1/metadata-keys':raise AssertionError('Only simulated key inventory reads are permitted.')
        return [{'id':20,'name':'Document Title'},{'id':21,'name':'Reference'}]
    redeye_pilot.request_vendor=vendor
    def forbidden(*a,**kw):raise AssertionError('Real vendor network is forbidden by this fixture.')
    httpx.HTTPTransport.handle_request=forbidden
    from backend import additional_connections
    additional_connections.read_json=forbidden
    return app
