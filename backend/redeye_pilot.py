"""Isolated one-artefact, existing-key RedEye live value pilot.

No key creation, overwrite, file operation, generic writer or automatic retry.
The vendor contract has no established atomic revision precondition: this pilot
requires a disposable, isolated, single-current-approved-revision target.
"""
import json
import hashlib
import threading
import os
import secrets
import time
from typing import Any
from uuid import uuid4

import httpx
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.integrations import canonical, digest
from backend.parameter_imports import definition, validate_value
from backend.providers import ProviderError, approved_base, auth_headers, resource_collection, read_page

MAX_ID = 9007199254740991


def positive(value):
    return type(value) is int and 0 < value <= MAX_ID


def request_vendor(base, secret, cfg, method, path, payload=None, transport=None):
    headers = auth_headers('redeye', secret, cfg['auth_header'], cfg['auth_prefix'])
    headers['User-Agent'] = 'ORBIT/0.13.0'
    try:
        with httpx.Client(transport=transport, timeout=httpx.Timeout(20, connect=5), follow_redirects=False, trust_env=True) as client:
            with client.stream(method, base + path, headers=headers, json=payload) as response:
                if response.status_code in {401,403}:raise ProviderError('access_denied', 'RedEye rejected the operation or its permissions.')
                if response.status_code == 429:raise ProviderError('rate_limited', 'RedEye rate limit reached. No automatic retry is performed.')
                if response.status_code != 200:raise ProviderError('vendor_response', 'RedEye did not return the documented HTTP 200 response; redirects are refused.')
                parts, size = [], 0
                for part in response.iter_bytes():
                    size += len(part)
                    if size > 1_000_000:raise ProviderError('response_too_large', 'RedEye response exceeds the 1 MB pilot limit.')
                    parts.append(part)
                if method == 'POST':return None
                result = json.loads(b''.join(parts))
                def echoed(value):
                    if isinstance(value,str):return bool(secret and secret in value)
                    if isinstance(value,list):return any(echoed(v) for v in value)
                    if isinstance(value,dict):return any(echoed(k) or echoed(v) for k,v in value.items())
                    return False
                if echoed(result):raise ProviderError('sensitive_echo', 'Response contained credential material; it was discarded.')
                return result
    except (httpx.HTTPError, ValueError):
        raise ProviderError('transport_uncertain' if method=='POST' else 'read_failed', 'RedEye request could not be confirmed. Writes are never retried automatically.')


def snapshot(base, secret, cfg, artefact_id, transport=None):
    keys_raw = request_vendor(base,secret,cfg,'GET','/api/v1/metadata-keys',transport=transport)
    rows, shape = resource_collection('redeye','metadata_keys',keys_raw)
    if len(rows)>2000:raise ProviderError('contract_mismatch','Pilot supports at most 2,000 metadata keys.')
    keys, names = {}, set()
    for row in rows:
        if not isinstance(row,dict) or not positive(row.get('id')) or not isinstance(row.get('name'),str) or not row['name'].strip() or len(row['name'])>250:
            raise ProviderError('contract_mismatch','Metadata keys require positive IDs and nonempty exact names.')
        if row['id'] in keys or row['name'].casefold() in names:raise ProviderError('ambiguous_keys','Duplicate metadata key IDs/names prevent this pilot.')
        keys[row['id']] = {'id':row['id'],'name':row['name']};names.add(row['name'].casefold())
    doc = request_vendor(base,secret,cfg,'GET',f'/api/v1/artefacts/{artefact_id}',transport=transport)
    history = request_vendor(base,secret,cfg,'GET',f'/api/v1/artefacts/{artefact_id}/versionhistory',transport=transport)
    if not isinstance(doc,dict) or doc.get('id')!=artefact_id or not positive(doc.get('id')) or not isinstance(doc.get('metadata'),list) or not isinstance(doc.get('revisions'),list):
        raise ProviderError('contract_mismatch','Artefact detail requires the exact ID, metadata and revisions arrays.')
    for key in ['title','number','modified']:
        if not isinstance(doc.get(key),str) or not doc[key].strip() or len(doc[key])>2000:raise ProviderError('contract_mismatch','Artefact title/number/modified evidence is missing or unsupported.')
    if not isinstance(doc.get('state'),dict):raise ProviderError('contract_mismatch','Artefact state is missing.')
    if not isinstance(history,dict) or 'revision' not in history:raise ProviderError('contract_mismatch','Expected the documented version-history revision wrapper.')
    revisions = history['revision'] if isinstance(history['revision'],list) else [history['revision']]
    def revision(row):
        if not isinstance(row,dict) or not positive(row.get('id')) or type(row.get('version')) is not int or row['version']<0 or not isinstance(row.get('status'),str) or not row['status'].strip():
            raise ProviderError('contract_mismatch','Revision ID/version/status is missing or unsupported.')
        return {key:row[key] for key in ['id','version','status']}
    details = [revision(r) for r in doc['revisions']];historical = [revision(r) for r in revisions]
    if len(details)>100 or len(historical)>100:raise ProviderError('contract_mismatch','Revision response exceeds the pilot limit.')
    values, ids = {}, set()
    if len(doc['metadata'])>1000:raise ProviderError('contract_mismatch','Artefact metadata exceeds the pilot limit.')
    for row in doc['metadata']:
        if not isinstance(row,dict) or not positive(row.get('key_id')) or row['key_id'] not in keys or row.get('key_name')!=keys[row['key_id']]['name'] or not isinstance(row.get('value'),str):
            raise ProviderError('contract_mismatch','Artefact metadata must have known key_id/key_name and string values; no values are silently dropped.')
        if row['key_id'] in values:raise ProviderError('multi_value_metadata','This first pilot requires at most one value per metadata key. Multi-valued metadata needs separate review.')
        if 'id' in row:
            if not positive(row['id']) or row['id'] in ids:raise ProviderError('contract_mismatch','Metadata entry IDs are invalid or duplicated.')
            ids.add(row['id'])
        values[row['key_id']] = row['value']
    blockers = []
    if doc['state'].get('is_modifiable') is not True:blockers.append('RedEye does not report this artefact as modifiable.')
    if len(details)!=1 or len(historical)!=1 or details!=historical:
        blockers.append('Pilot requires one matching visible revision in detail and history. Current-versus-approved targeting is not established for this artefact.')
    guard = {'id':doc['id'],'number':doc['number'],'title':doc['title'],'state':doc['state'],'revisions':details,'history':historical,
             'other_content_digest':digest({k:doc[k] for k in ['groups','workflow','geometry','type','created'] if k in doc})}
    return {'artefact_id':artefact_id,'number':doc['number'],'title':doc['title'],'modified':doc['modified'],'keys':sorted(keys.values(),key=lambda k:k['id']),
            'values':{str(k):v for k,v in sorted(values.items())},'guard':guard,'blockers':blockers,'response_shapes':{'metadata_keys':shape,'history_revision':'array' if isinstance(history['revision'],list) else 'object'}}


class Inspect(BaseModel):
    model_config=ConfigDict(extra='forbid')
    connection_id:str=Field(min_length=1,max_length=100)
    artefact_id:int=Field(gt=0,le=MAX_ID,strict=True)


class Preview(BaseModel):
    model_config=ConfigDict(extra='forbid')
    inspection_id:str=Field(min_length=1,max_length=100)
    property_uri:str=Field(min_length=1,max_length=1000)
    metadata_key_id:int=Field(gt=0,le=MAX_ID,strict=True)
    expected_revision_id:int=Field(gt=0,le=MAX_ID,strict=True)
    approved_status:str=Field(min_length=1,max_length=100)
    unit:str=Field(default='',max_length=100)
    value:Any
    evidence_note:str=Field(min_length=1,max_length=1000)
    disposable_isolated_target:bool=False
    current_approved_revision_confirmed:bool=False
    metadata_contract_confirmed:bool=False
    mapping_type_units_confirmed:bool=False

    @model_validator(mode='after')
    def finite_value(self):
        if len(json.dumps(self.value,allow_nan=False))>10000:raise ValueError('Pilot value is limited to 10 KB')
        if not self.evidence_note.strip():raise ValueError('Record a non-secret test/admin reference')
        return self


class Exact(BaseModel):
    model_config=ConfigDict(extra='forbid')
    digest:str=Field(min_length=64,max_length=64)


class Execute(Exact):
    confirmation:str=Field(max_length=100)


def register_redeye_pilot(app,db,identity,permit,project_check,audit,vault,now):
    # Local UAT permissions are short-lived, session-bound and never survive restart.
    armed = {}
    arm_lock = threading.Lock()

    def session_key(request):
        return hashlib.sha256(request.cookies.get('orbit_session','').encode()).hexdigest()

    def uat_mode():
        return os.getenv('ORBIT_UAT_MODE') == '1'

    def arm_matches(request, row, test):
        with arm_lock:
            for key, grant in list(armed.items()):
                if grant['expires'] <= int(time.time()):
                    del armed[key]
            grant = armed.get(session_key(request))
            return bool(grant and grant['test_id'] == test['id'] and grant['digest'] == test['digest']
                        and grant['connection_id'] == row['id'] and grant['generation'] == row['generation']
                        and grant['target'] == row['id']+'|'+url_host(json.loads(row['configuration'])['base_url'])+'|'+str(test['artefact_id']))

    def connection(c,who,project,ident):
        project_check(c,who,project)
        row=c.execute('SELECT * FROM read_connections WHERE tenant_id=? AND project_id=? AND id=? AND provider=?',(who['tenant_id'],project,ident,'redeye')).fetchone()
        if not row:raise HTTPException(404,'RedEye read connection unavailable in this project')
        return dict(row)

    def schema(c,who,project):
        row=c.execute('SELECT version,configuration FROM bsdd_settings WHERE tenant_id=? AND project_id=?',(who['tenant_id'],project)).fetchone()
        cfg=json.loads(row['configuration']) if row else {}
        if not cfg.get('enabled') or not cfg.get('properties'):raise HTTPException(409,'Enable bSDD and select property definitions for this project first.')
        return {'version':row['version'],'configuration':cfg}

    def access(row):
        cfg=json.loads(row['configuration'])
        if os.getenv('ORBIT_ENABLE_LIVE_READS')!='1':raise HTTPException(409,'Open the local portal using Run-ORBIT.cmd to enable UAT connection reads.')
        if not cfg['vendor_settings_confirmed'] or not cfg['approved_test_access'] or not cfg['evidence_note'].strip():raise HTTPException(409,'Confirm vendor settings, test access and evidence on this saved read connection first.')
        try:
            base=approved_base('redeye',cfg['base_url'],[h.strip().lower() for h in os.getenv('ORBIT_REDEYE_ALLOWED_HOSTS','').split(',') if h.strip()])
            secret=vault.decrypt(row['secret_ciphertext'].encode()).decode() if row['secret_ciphertext'] else ''
            auth_headers('redeye',secret,cfg['auth_header'],cfg['auth_prefix'])
        except ProviderError as e:raise HTTPException(409,e.message)
        except Exception:raise HTTPException(409,'Stored RedEye credential is missing or unreadable; replace it in Read connections.')
        return base,secret,cfg

    def write_gate(row,artefact_id,request=None,test=None):
        if uat_mode() and request is not None and test is not None and arm_matches(request,row,test):return
        host=url_host(json.loads(row['configuration'])['base_url'])
        required=row['id']+'|'+host+'|'+str(artefact_id)
        if os.getenv('ORBIT_ENABLE_REDEYE_WRITE_TESTS')!='1' or os.getenv('ORBIT_REDEYE_WRITE_TEST_TARGET','')!=required:
            raise HTTPException(409,'Enable this exact approved test in the UAT browser first. This does not enable any other target.')

    def current(request,who,project,ident,generation,action='connection'):
        current_who=identity(request)
        if current_who['user_id']!=who['user_id'] or current_who['tenant_id']!=who['tenant_id']:raise HTTPException(409,'Identity changed during the operation; result discarded.')
        permit(current_who,action)
        with db() as c:
            row=connection(c,current_who,project,ident)
            if row['generation']!=generation:raise HTTPException(409,'Connection or credential changed; inspect the intended destination again.')
        return current_who

    def job(c,who,project,ident):
        project_check(c,who,project)
        row=c.execute('SELECT * FROM redeye_import_tests WHERE id=? AND tenant_id=? AND project_id=?',(ident,who['tenant_id'],project)).fetchone()
        if not row:raise HTTPException(404,'RedEye import test unavailable')
        return dict(row)

    def public(row):
        return {k:json.loads(v) if k in {'configuration','preview','receipt'} and v is not None else v for k,v in row.items() if k not in {'tenant_id','schema_digest','before_snapshot'}}

    def check_exact(row,body):
        if not secrets.compare_digest(row['digest'],body.digest):raise HTTPException(409,'Review the exact RedEye test digest.')

    def fresh(c,who,project,row):
        if row['expires']<=int(time.time()):raise HTTPException(409,'Test preview expired; inspect and review a fresh preview.')
        conn=connection(c,who,project,row['connection_id'])
        if conn['generation']!=row['generation'] or digest(schema(c,who,project))!=row['schema_digest']:raise HTTPException(409,'Connection or dictionary changed; create a fresh inspection and preview.')
        if json.loads(row['preview'])['blockers']:raise HTTPException(409,'Resolve every preview blocker before approval or writing.')
        return conn

    def approver(c,who,project,row):
        membership=c.execute('SELECT role FROM memberships WHERE tenant_id=? AND user_id=?',(who['tenant_id'],row['approved_by'])).fetchone()
        if not membership:raise HTTPException(409,'Approver membership was removed.')
        permit({'role':membership['role']},'approve')
        if not c.execute('SELECT 1 FROM project_access WHERE tenant_id=? AND project_id=? AND user_id=?',(who['tenant_id'],project,row['approved_by'])).fetchone():raise HTTPException(409,'Approver project access was removed.')

    def save_receipt(c,who,project,row,status,reason,verified=False,http_ok=False):
        previous=json.loads(row['receipt']) if row['receipt'] else {}
        initial=previous.get('initial_outcome',{'status':status,'reason':reason,'http_200_observed':http_ok})
        receipt={'initial_outcome':initial,'test_id':row['id'],'digest':row['digest'],'status':status,'write_attempt_reserved':True,'read_back_verified':verified,'http_200_observed':http_ok,'reason':reason,'observed':now(),
                 'connection_id':row['connection_id'],'artefact_id':row['artefact_id'],'automatic_retry':False,'scope':'One existing RedEye key on the confirmed disposable artefact; not general import/field creation.'}
        c.execute('UPDATE redeye_import_tests SET status=?,receipt=? WHERE id=?',(status,canonical(receipt),row['id']))
        audit(c,who,'redeye_test.'+status,project,row['id'])
        return receipt

    def verify(row,after):
        before=json.loads(row['before_snapshot']);preview=json.loads(row['preview'])
        expected={**before['values'],str(preview['metadata_key']['id']):preview['encoded_value']}
        if after['blockers'] or after['guard']!=before['guard']:return False,'Revision, identity, state or other content changed; inspect the disposable artefact manually.'
        if after['values']!=expected:return False,'Read-back did not match the proposed value plus every preserved metadata value; inspect manually. No retry or rollback was sent.'
        before_keys={k['id']:k['name'] for k in before['keys']};after_keys={k['id']:k['name'] for k in after['keys']}
        if any(after_keys.get(k)!=name for k,name in before_keys.items()):return False,'Metadata key identities/names changed; inspect manually.'
        return True,'One value and all returned pre-existing metadata values matched on read-back. Current/approved equivalence remains the operator-confirmed isolated-test condition.'

    @app.get('/api/projects/{project}/redeye-import-tests')
    def listing(project:str,request:Request,who=Depends(identity)):
        permit(who,'view')
        with db() as c:
            project_check(c,who,project)
            connections=[]
            for r in c.execute('SELECT id,name,generation,configuration FROM read_connections WHERE tenant_id=? AND project_id=? AND provider=?',(who['tenant_id'],project,'redeye')):
                try:base=approved_base('redeye',json.loads(r['configuration'])['base_url'],[h.strip().lower() for h in os.getenv('ORBIT_REDEYE_ALLOWED_HOSTS','').split(',') if h.strip()])
                except ProviderError:base='Unverified API URL; review Read connections'
                connections.append({'id':r['id'],'name':r['name'],'generation':r['generation'],'base_url':base})
            rows=[public(dict(r)) for r in c.execute('SELECT * FROM redeye_import_tests WHERE tenant_id=? AND project_id=? ORDER BY created DESC,id',(who['tenant_id'],project))]
        import re
        allowed_target=os.getenv('ORBIT_REDEYE_WRITE_TEST_TARGET','')
        if not re.fullmatch(r'[0-9a-fA-F-]{36}\|[a-z0-9.-]+\|[1-9][0-9]*',allowed_target):allowed_target=''
        return {'connections':connections,'tests':rows,'write_opt_in':os.getenv('ORBIT_ENABLE_REDEYE_WRITE_TESTS')=='1','target_allowlist':allowed_target if who['role']=='owner' else '', 'server_version':app.version,'uat_mode':uat_mode(),'armed_test_ids':[r['id'] for r in rows if who['role']=='owner' and uat_mode() and arm_matches(request,{'id':r['connection_id'],'generation':r['generation'],'configuration':canonical({'base_url':r['preview']['base_url']})},r)]}

    @app.get('/api/projects/{project}/redeye-import-tests/candidates/{ident}')
    def candidates(project:str,ident:str,request:Request,who=Depends(identity)):
        permit(who,'connection')
        with db() as c:row=connection(c,who,project,ident)
        base,secret,cfg=access(row)
        try:result=read_page('redeye',base,secret,'artefacts',{},cfg['auth_header'],cfg['auth_prefix'])
        except ProviderError as e:raise HTTPException(502,{'code':e.code,'message':e.message})
        current(request,who,project,ident,row['generation'])
        return result

    @app.post('/api/projects/{project}/redeye-import-tests/inspect')
    def inspect(project:str,request:Request,body:Inspect,who=Depends(identity)):
        permit(who,'connection')
        with db() as c:row=connection(c,who,project,body.connection_id)
        generation=row['generation']
        base,secret,cfg=access(row)
        try:data=snapshot(base,secret,cfg,body.artefact_id)
        except ProviderError as e:raise HTTPException(502,{'code':e.code,'message':e.message})
        current(request,who,project,row['id'],row['generation'])
        ident=str(uuid4());observed=now()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=connection(c,who,project,row['id'])
            if row['generation']!=generation:raise HTTPException(409,'Connection changed during inspection; inspect again.')
            c.execute('INSERT INTO redeye_inspections VALUES(?,?,?,?,?,?,?,?,?)',(ident,who['tenant_id'],project,row['id'],row['generation'],body.artefact_id,canonical(data),observed,int(time.time())+900))
            audit(c,who,'redeye_test.inspected',project,ident)
        return {'id':ident,'snapshot':data,'observed':observed,'connection_id':row['id'],'generation':row['generation']}

    @app.post('/api/projects/{project}/redeye-import-tests')
    def preview(project:str,body:Preview,who=Depends(identity)):
        permit(who,'connection')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');project_check(c,who,project)
            inspection=c.execute('SELECT * FROM redeye_inspections WHERE id=? AND tenant_id=? AND project_id=?',(body.inspection_id,who['tenant_id'],project)).fetchone()
            if not inspection or inspection['expires']<=int(time.time()):raise HTTPException(409,'Inspect a fresh RedEye test artefact first.')
            conn=connection(c,who,project,inspection['connection_id'])
            if conn['generation']!=inspection['generation']:raise HTTPException(409,'Connection changed; inspect again.')
            reference=schema(c,who,project);prop=next((p for p in reference['configuration']['properties'] if p['uri']==body.property_uri),None)
            if not prop:raise HTTPException(422,'Select a property from this project bSDD reference.')
            before=json.loads(inspection['snapshot']);key=next((k for k in before['keys'] if k['id']==body.metadata_key_id),None)
            if not key:raise HTTPException(422,'Choose an existing key returned by this exact RedEye inspection.')
            spec,errors=definition(prop,{'target_name':'PilotValue','unit':body.unit,'required':True})
            if spec['value_kind']!='Single':errors.append('The first live pilot supports a single scalar property value only.')
            problem=validate_value(body.value,spec)
            if problem:errors.append(problem)
            encoded=body.value if isinstance(body.value,str) else canonical(body.value)
            try:credential=vault.decrypt(conn['secret_ciphertext'].encode()).decode()
            except Exception:raise HTTPException(409,'Credential changed or is unreadable; replace it and inspect again.')
            if credential and any(credential in v for v in [encoded,body.evidence_note,body.property_uri,body.approved_status,body.unit]):
                raise HTTPException(422,'Credential material cannot be used as test metadata or evidence; the preview was not stored.')
            if not encoded.strip():errors.append('Use a nonblank test marker value.')
            if before['values'].get(str(key['id']), '')!='':errors.append('The selected key already has a nonempty value on this artefact. Overwrite is disabled; choose an unassigned or blank test key.')
            revisions=before['guard']['revisions']
            if len(revisions)!=1 or revisions[0]['id']!=body.expected_revision_id or revisions[0]['status']!=body.approved_status:
                errors.append('Confirm the exact visible revision ID and status from the inspection; labels are not inferred as approval.')
            for attr,message in [('disposable_isolated_target','Confirm a disposable isolated artefact with no other writers.'),('current_approved_revision_confirmed','Confirm in RedEye that current and approved revisions are the same intended target.'),('metadata_contract_confirmed','Review the complete metadata payload and confirm its current-revision update contract.'),('mapping_type_units_confirmed','Confirm the source type/units/allowed values match this RedEye key.')]:
                if not getattr(body,attr):errors.append(message)
            metadata=[{'name':next(k['name'] for k in before['keys'] if str(k['id'])==ident),'value':[value]} for ident,value in before['values'].items() if ident!=str(key['id'])]
            metadata.append({'name':key['name'],'value':[encoded]})
            if len(canonical(metadata))>100000:errors.append('Metadata preservation payload exceeds the 100 KB pilot limit.')
            plan={'connection_name':conn['name'],'base_url':json.loads(conn['configuration'])['base_url'],'artefact_id':before['artefact_id'],'number':before['number'],'title':before['title'],
                  'dictionary':reference['configuration']['dictionary'],'property_definition':prop,'metadata_key':key,'typed_value':body.value,'encoded_value':encoded,'unit':spec['unit'],
                  'revision_id':body.expected_revision_id,'status_label':body.approved_status,'payload':{'metadata':metadata},'preserved_values':{k:v for k,v in before['values'].items() if k!=str(key['id'])},'before_target_value':before['values'].get(str(key['id'])),'target_action':'fill_blank' if str(key['id']) in before['values'] else 'add',
                  'blockers':before['blockers']+errors,'race_note':'No documented atomic revision/concurrency precondition. Disposable isolated target and operator current/approved confirmation are mandatory.'}
            ident=str(uuid4());expires=int(time.time())+900
            fingerprint=digest({'id':ident,'tenant':who['tenant_id'],'project':project,'connection':conn['id'],'generation':conn['generation'],'schema':reference,'before':before,'configuration':body.model_dump(),'preview':plan,'expires':expires})
            c.execute('INSERT INTO redeye_import_tests VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULL,?,?,?,NULL)',(ident,who['tenant_id'],project,conn['id'],conn['generation'],before['artefact_id'],body.model_dump_json(),canonical(before),digest(reference),canonical(plan),fingerprint,who['user_id'],'preview',now(),expires))
            audit(c,who,'redeye_test.preview_created',project,ident)
            return public(job(c,who,project,ident))

    @app.post('/api/projects/{project}/redeye-import-tests/{ident}/approve')
    def approve(project:str,ident:str,body:Exact,who=Depends(identity)):
        permit(who,'approve')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');row=job(c,who,project,ident);check_exact(row,body)
            if row['status']!='preview' or row['requested_by']==who['user_id']:raise HTTPException(409,'Approval requires another actor and a pending preview.')
            fresh(c,who,project,row)
            c.execute("UPDATE redeye_import_tests SET status='approved',approved_by=? WHERE id=?",(who['user_id'],ident));audit(c,who,'redeye_test.approved',project,ident)
        return {'status':'approved','written':False}

    @app.post('/api/projects/{project}/redeye-import-tests/{ident}/arm')
    def arm(project:str,ident:str,request:Request,body:Exact,who=Depends(identity)):
        permit(who,'connection')
        if not uat_mode():raise HTTPException(409,'Open Run-ORBIT.cmd for browser-based local UAT testing.')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row=job(c,who,project,ident);check_exact(row,body)
            if row['status']!='approved':raise HTTPException(409,'A separately approved preview is required before enabling a test.')
            conn=fresh(c,who,project,row);approver(c,who,project,row)
            access(conn)
            if c.execute('SELECT 1 FROM redeye_import_attempts WHERE connection_id=? AND artefact_id=?',(conn['id'],row['artefact_id'])).fetchone():
                raise HTTPException(409,'This target already has an attempt. Inspect its outcome; use a new disposable target for another test.')
            expires=min(row['expires'],int(time.time())+600)
            audit(c,who,'redeye_test.uat_enabled',project,ident)
        with arm_lock:
            armed[session_key(request)]={'test_id':row['id'],'digest':row['digest'],'connection_id':conn['id'],'generation':conn['generation'],
                                         'target':conn['id']+'|'+url_host(json.loads(conn['configuration'])['base_url'])+'|'+str(row['artefact_id']),'expires':expires}
        return {'status':'enabled','expires':expires,'written':False}

    @app.post('/api/projects/{project}/redeye-import-tests/{ident}/disarm')
    def disarm(project:str,ident:str,request:Request,body:Exact,who=Depends(identity)):
        permit(who,'connection')
        with db() as c:
            row=job(c,who,project,ident);check_exact(row,body)
            audit(c,who,'redeye_test.uat_disabled',project,ident)
        with arm_lock:
            grant=armed.get(session_key(request))
            if grant and grant['test_id']==ident:armed.pop(session_key(request),None)
        return {'status':'disabled','written':False}

    @app.post('/api/projects/{project}/redeye-import-tests/{ident}/execute')
    def execute(project:str,ident:str,request:Request,body:Execute,who=Depends(identity)):
        permit(who,'connection')
        with db() as c:
            row=job(c,who,project,ident);check_exact(row,body)
            if row['status'] in {'verified','needs_review','attempting'}:return json.loads(row['receipt']) if row['receipt'] else {'status':row['status'],'automatic_retry':False,'reason':'An attempt was reserved. Use read-only recheck or inspect RedEye manually; no second POST is permitted.'}
            if row['status']!='approved':raise HTTPException(409,'A separately approved test preview is required.')
            conn=fresh(c,who,project,row);approver(c,who,project,row)
        if body.confirmation!='WRITE '+str(row['artefact_id']):raise HTTPException(409,'Type WRITE followed by the exact artefact ID to execute this one-value test.')
        write_gate(conn,row['artefact_id'],request,row);base,secret,cfg=access(conn)
        try:latest=snapshot(base,secret,cfg,row['artefact_id'])
        except ProviderError as e:raise HTTPException(502,{'code':e.code,'message':e.message})
        current(request,who,project,conn['id'],conn['generation'])
        if digest(latest)!=digest(json.loads(row['before_snapshot'])):raise HTTPException(409,'Artefact, metadata keys, values or revision changed; inspect and preview again. No POST sent.')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');row=job(c,who,project,ident);conn=fresh(c,who,project,row);approver(c,who,project,row);write_gate(conn,row['artefact_id'],request,row)
            if row['status']!='approved':raise HTTPException(409,'Another request already claimed this test.')
            if c.execute('SELECT 1 FROM redeye_import_attempts WHERE connection_id=? AND artefact_id=?',(conn['id'],row['artefact_id'])).fetchone():raise HTTPException(409,'This connection/artefact already has a test attempt. Inspect its result and use a new disposable target; never retry blindly.')
            c.execute('INSERT INTO redeye_import_attempts VALUES(?,?,?,?)',(conn['id'],row['artefact_id'],ident,now()))
            c.execute("UPDATE redeye_import_tests SET status='attempting' WHERE id=?",(ident,));audit(c,who,'redeye_test.attempt_reserved',project,ident)
        # Reservation is durable before any POST. Even a crash cannot trigger replay.
        with db() as c:
            c.execute('BEGIN IMMEDIATE');row=job(c,who,project,ident)
            http_ok=False
            try:
                current(request,who,project,row['connection_id'],row['generation'])
                conn=fresh(c,who,project,row);approver(c,who,project,row);write_gate(conn,row['artefact_id'],request,row);base,secret,cfg=access(conn)
                with arm_lock:armed.pop(session_key(request),None)
                request_vendor(base,secret,cfg,'POST',f"/api/v1/artefacts/{row['artefact_id']}",json.loads(row['preview'])['payload'])
                http_ok=True
                after=snapshot(base,secret,cfg,row['artefact_id']);verified,reason=verify(row,after)
                return save_receipt(c,who,project,row,'verified' if verified else 'needs_review',reason,verified,http_ok)
            except ProviderError as e:return save_receipt(c,who,project,row,'needs_review',e.message,http_ok=http_ok)
            except HTTPException:return save_receipt(c,who,project,row,'needs_review','Local preconditions changed after attempt reservation. No automatic retry is permitted; inspect the exact target.',http_ok=http_ok)
            except Exception:return save_receipt(c,who,project,row,'needs_review','The attempt could not be confirmed. Inspect the artefact before any further action; automatic retry is blocked.',http_ok=http_ok)

    @app.post('/api/projects/{project}/redeye-import-tests/{ident}/recheck')
    def recheck(project:str,ident:str,request:Request,body:Exact,who=Depends(identity)):
        permit(who,'connection')
        with db() as c:
            row=job(c,who,project,ident);check_exact(row,body)
            if row['status']=='verified':return json.loads(row['receipt'])
            if row['status'] not in {'attempting','needs_review'}:raise HTTPException(409,'Recheck is only for an existing uncertain/interrupted attempt.')
            conn=connection(c,who,project,row['connection_id'])
            if conn['generation']!=row['generation']:raise HTTPException(409,'Connection changed; inspect the original destination manually.')
        base,secret,cfg=access(conn)
        try:after=snapshot(base,secret,cfg,row['artefact_id'])
        except ProviderError as e:raise HTTPException(502,{'code':e.code,'message':e.message})
        current(request,who,project,conn['id'],conn['generation']);verified,reason=verify(row,after)
        with db() as c:
            latest=job(c,who,project,ident)
            if latest['status']=='verified':return json.loads(latest['receipt'])
            old_receipt=json.loads(latest['receipt']) if latest['receipt'] else {}
            return save_receipt(c,who,project,latest,'verified' if verified else 'needs_review',reason,verified,old_receipt.get('http_200_observed',False))

    @app.post('/api/projects/{project}/redeye-import-tests/{ident}/cancel')
    def cancel(project:str,ident:str,body:Exact,who=Depends(identity)):
        permit(who,'connection')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');row=job(c,who,project,ident);check_exact(row,body)
            if row['status'] not in {'preview','approved'}:raise HTTPException(409,'An attempted test cannot be cancelled or rolled back automatically.')
            c.execute("UPDATE redeye_import_tests SET status='cancelled' WHERE id=?",(ident,));audit(c,who,'redeye_test.cancelled',project,ident)
        return {'status':'cancelled'}


def url_host(base):
    from urllib.parse import urlsplit
    return (urlsplit(base).hostname or '').lower()
