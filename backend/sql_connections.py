"""Microsoft SQL Server / Azure SQL read adapters and project-scoped mapping previews.

All database statements are generated SELECTs; no SQL or vendor writer is exposed.
Use a SELECT-only database principal: ApplicationIntent is not authorisation.
"""
import datetime
import decimal
import ipaddress
import json
import math
import os
import re
import time
from typing import Literal
from uuid import UUID, uuid4

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend import redeye_pilot
from backend.integrations import canonical, digest
from backend.providers import approved_base, auth_headers, resource_collection, ProviderError

DRIVER = 'ODBC Driver 18 for SQL Server'


class SQLFailure(Exception):
    def __init__(self, code, message):self.code,self.message=code,message


class Config(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=100)
    location:Literal['local','azure']='local'
    server:str=Field(min_length=1,max_length=253)
    port:int=Field(default=1433,ge=1,le=65535,strict=True)
    database:str=Field(min_length=1,max_length=128)
    auth_mode:Literal['sql','windows']='sql'
    username:str=Field(default='',max_length=250)
    approved_test_access:bool=False

    @model_validator(mode='after')
    def valid(self):
        self.server=self.server.strip().lower()
        if not re.fullmatch(r'[a-z0-9][a-z0-9.-]*',self.server) or '..' in self.server or any(c in self.database+self.username+self.name for c in '\r\n\x00'):
            raise ValueError('Use a TCP hostname or IPv4 address, database name and port; no URL, instance suffix or connection string.')
        try:
            addr=ipaddress.ip_address(self.server)
            if addr.is_link_local or addr.is_multicast or addr.is_unspecified:raise ValueError('Link-local, multicast and unspecified destinations are not database endpoints.')
        except ValueError:
            if re.fullmatch(r'[0-9.]+',self.server):
                addr=ipaddress.ip_address(self.server)
                if addr.is_link_local or addr.is_multicast or addr.is_unspecified:raise ValueError('Unsupported database address.')
        if self.location=='azure' and (not self.server.endswith('.database.windows.net') or self.auth_mode!='sql'):
            raise ValueError('This Azure SQL increment uses the logical-server .database.windows.net hostname and SQL authentication.')
        if self.auth_mode=='sql' and not self.username.strip():raise ValueError('Supply the SQL login name.')
        return self


class Credential(BaseModel):
    model_config=ConfigDict(extra='forbid')
    password:str=Field(min_length=1,max_length=4000)

    @model_validator(mode='after')
    def no_null(self):
        if any(c in self.password for c in '\r\n\x00'):raise ValueError('Password cannot contain line breaks or nulls.')
        return self


class ObjectChoice(BaseModel):
    model_config=ConfigDict(extra='forbid')
    schema_name:str=Field(min_length=1,max_length=128)
    object_name:str=Field(min_length=1,max_length=128)


class Target(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Literal['read','additional','sql']
    id:str=Field(min_length=1,max_length=100)


class Rule(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source:str=Field(min_length=1,max_length=128)
    target:str=Field(min_length=1,max_length=250)
    transform:Literal['copy','trim','uppercase','lowercase']='copy'
    required:bool=False
    default:str=Field(default='',max_length=1000)


class Mapping(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=100)
    snapshot_id:str=Field(min_length=1,max_length=100)
    source_key:str=Field(min_length=1,max_length=128)
    target:Target
    target_snapshot_id:str=Field(default='',max_length=100)
    target_match_field:str=Field(min_length=1,max_length=250)
    rules:list[Rule]=Field(min_length=1,max_length=100)

    @model_validator(mode='after')
    def unique(self):
        if len({r.target.casefold() for r in self.rules})!=len(self.rules):raise ValueError('Map each target field once.')
        return self


class SaveMapping(Mapping):
    id:str=Field(default='',max_length=100)
    expected_version:int=Field(default=0,ge=0)


def odbc_value(value):return '{'+str(value).replace('}','}}')+'}'

def connection_string(cfg,password):
    values={'DRIVER':DRIVER,'SERVER':f"tcp:{cfg['server']},{cfg['port']}",'DATABASE':cfg['database'],
            'Encrypt':'yes','TrustServerCertificate':'no','ApplicationIntent':'ReadOnly','APP':'ORBIT SQL reader'}
    if cfg['auth_mode']=='windows':values['Trusted_Connection']='yes'
    else:values.update(UID=cfg['username'],PWD=password)
    return ';'.join(k+'='+odbc_value(v) for k,v in values.items())+';'


def identifier(value):return '['+value.replace(']',']]')+']'


def projection(column):
    name=identifier(column['name']);kind=column['type'].lower()
    if kind in {'binary','varbinary','image','timestamp','rowversion'}:
        return "CAST(N'[binary omitted]' AS nvarchar(30)) AS "+name
    if kind in {'char','varchar','nchar','nvarchar','text','ntext','xml'}:
        return 'CONVERT(nvarchar(2001),'+name+') AS '+name
    if kind in {'date','time','datetime','datetime2','smalldatetime','datetimeoffset'}:
        return 'CONVERT(nvarchar(100),'+name+',127) AS '+name
    if kind in {'bigint','int','smallint','tinyint','decimal','numeric','money','smallmoney','float','real','bit','uniqueidentifier'}:
        return name
    return "CAST(N'[unsupported value omitted]' AS nvarchar(40)) AS "+name


def cell(value):
    if type(value) is int and abs(value)>9007199254740991:return str(value)
    if value is None or isinstance(value,(str,bool,int)):result=value
    elif isinstance(value,float):result=value if math.isfinite(value) else '[nonfinite number omitted]'
    elif isinstance(value,(datetime.datetime,datetime.date,datetime.time,UUID,decimal.Decimal)):result=str(value)
    elif isinstance(value,(bytes,bytearray,memoryview)):result='[binary omitted]'
    else:result='[unsupported value omitted]'
    if isinstance(result,str) and len(result)>2000:result=result[:2000]+' [truncated]'
    return result


def driver_status():
    try:
        import pyodbc
        return {'available':DRIVER in pyodbc.drivers(),'python_package':True,'required_driver':DRIVER}
    except Exception:return {'available':False,'python_package':False,'required_driver':DRIVER}


def query_database(cfg,password,choice=None):
    try:
        import pyodbc
    except ImportError:raise SQLFailure('driver_missing','Install the optional SQL support and Microsoft ODBC Driver 18 on the computer running ORBIT.') from None
    if DRIVER not in pyodbc.drivers():raise SQLFailure('driver_missing','Microsoft ODBC Driver 18 for SQL Server is not installed on this executor.')
    if cfg['auth_mode']=='windows' and os.name!='nt':raise SQLFailure('windows_executor_required','This integrated-authentication option requires ORBIT running on Windows under the authorised Windows identity.')
    conn=None
    try:
        conn=pyodbc.connect(connection_string(cfg,password),timeout=10,autocommit=True)
        conn.timeout=10
        cur=conn.cursor()
        if choice is None:
            cur.execute("SELECT TOP (201) s.name,o.name,o.type_desc FROM sys.objects o JOIN sys.schemas s ON s.schema_id=o.schema_id WHERE o.type IN ('U','V') AND o.is_ms_shipped=0 ORDER BY s.name,o.name")
            rows=cur.fetchmany(201)
            return {'objects':[{'schema_name':r[0],'object_name':r[1],'kind':r[2]} for r in rows[:200]],'truncated':len(rows)>200}
        cur.execute("SELECT o.object_id,o.type_desc FROM sys.objects o JOIN sys.schemas s ON s.schema_id=o.schema_id WHERE s.name=? AND o.name=? AND o.type IN ('U','V') AND o.is_ms_shipped=0",choice['schema_name'],choice['object_name'])
        obj=cur.fetchone()
        if not obj:raise SQLFailure('object_unavailable','The selected table/view is not visible to this database principal.')
        cur.execute("SELECT c.name,t.name,c.is_nullable,c.is_identity,c.is_computed,CASE WHEN pk.column_id IS NULL THEN 0 ELSE 1 END FROM sys.columns c JOIN sys.types t ON t.user_type_id=c.user_type_id LEFT JOIN (SELECT ic.object_id,ic.column_id FROM sys.indexes i JOIN sys.index_columns ic ON ic.object_id=i.object_id AND ic.index_id=i.index_id WHERE i.is_primary_key=1 AND ic.key_ordinal>0) pk ON pk.object_id=c.object_id AND pk.column_id=c.column_id WHERE c.object_id=? ORDER BY c.column_id",obj[0])
        columns=[{'name':r[0],'type':r[1],'nullable':bool(r[2]),'identity':bool(r[3]),'computed':bool(r[4]),'primary_key':bool(r[5])} for r in cur.fetchmany(201)]
        if not columns or len(columns)>200:raise SQLFailure('column_limit','Select an object with 1–200 visible columns.')
        names=[c['name'] for c in columns]
        if len(set(names))!=len(names):raise SQLFailure('ambiguous_columns','Column names are ambiguous.')
        # SQL identifiers come from the selected server object and are always quoted.
        # Sample selection is intentionally not a complete register or stable row order.
        statement='SELECT TOP (26) '+','.join(projection(col) for col in columns)+' FROM '+identifier(choice['schema_name'])+'.'+identifier(choice['object_name'])
        cur.execute(statement)
        raw=cur.fetchmany(26)
        rows=[{name:cell(v) for name,v in zip(names,r)} for r in raw[:25]]
        result={'object':choice,'kind':obj[1],'columns':columns,'rows':rows,'truncated':len(raw)>25,'sample_limit':25,
                'scope':'Bounded unordered sample; binary values omitted, long values truncated, exact decimals/dates represented as text.'}
        if len(canonical(result))>250000:raise SQLFailure('sample_too_large','The sampled object exceeds the 250 KB preview limit; use a narrower database view.')
        def contains(value):
            if isinstance(value,str):return password in value
            if isinstance(value,dict):return any(contains(k) or contains(v) for k,v in value.items())
            if isinstance(value,list):return any(contains(v) for v in value)
            return False
        if password and contains(result):raise SQLFailure('credential_echo','Database response contained credential material and was discarded.')
        return result
    except SQLFailure:raise
    except Exception:raise SQLFailure('sql_read_failed','SQL read failed. Check endpoint/port, database access, login, firewall and certificate trust. Provider details are not returned.') from None
    finally:
        if conn is not None:
            try:conn.close()
            except Exception:pass


def register_sql_connections(app,db,identity,permit,project_check,audit,vault,now):
    def get(c,who,project,ident):
        project_check(c,who,project)
        row=c.execute('SELECT * FROM sql_connections WHERE tenant_id=? AND project_id=? AND id=?',(who['tenant_id'],project,ident)).fetchone()
        if not row:raise HTTPException(404,'SQL connection unavailable.')
        return dict(row)

    def public(row):
        return {'id':row['id'],'name':row['name'],'configuration':json.loads(row['configuration']),'generation':row['generation'],'credential_present':bool(row['secret_ciphertext'])}

    def access(row):
        cfg=json.loads(row['configuration'])
        if os.getenv('ORBIT_ENABLE_LIVE_READS')!='1' or not cfg['approved_test_access']:raise HTTPException(409,'Start Run-ORBIT.cmd and confirm this database is authorised for read testing.')
        password=''
        if cfg['auth_mode']=='sql':
            try:password=vault.decrypt(row['secret_ciphertext'].encode()).decode() if row['secret_ciphertext'] else ''
            except Exception:raise HTTPException(409,'Stored password is unreadable; replace it in SQL connections.')
            if not password:raise HTTPException(409,'Store the SQL password in the encrypted credential form.')
        return cfg,password

    def fresh(request,who,project,row):
        current=identity(request);permit(current,'connection')
        if current!=who:raise HTTPException(409,'Identity changed during the SQL read; result discarded.')
        with db() as c:
            if get(c,current,project,row['id'])['generation']!=row['generation']:raise HTTPException(409,'SQL connection changed during the read; load again.')

    def run(row,choice=None):
        cfg,password=access(row)
        try:return query_database(cfg,password,choice)
        except SQLFailure as e:raise HTTPException(409 if e.code in {'driver_missing','windows_executor_required'} else 502,{'code':e.code,'message':e.message})

    def snapshot(c,who,project,ident):
        project_check(c,who,project)
        row=c.execute('SELECT * FROM sql_snapshots WHERE id=? AND tenant_id=? AND project_id=?',(ident,who['tenant_id'],project)).fetchone()
        if not row:raise HTTPException(404,'SQL sample unavailable in this project.')
        if row['expires']<=int(time.time()):raise HTTPException(409,'Load a fresh SQL table sample; samples expire after 15 minutes.')
        conn=get(c,who,project,row['connection_id'])
        if conn['generation']!=row['generation']:raise HTTPException(409,'SQL configuration changed; reload its table.')
        return dict(row),conn,json.loads(row['snapshot'])

    def target(c,who,project,ref):
        table={'read':'read_connections','additional':'external_connections','sql':'sql_connections'}[ref.kind]
        project_check(c,who,project)
        row=c.execute(f'SELECT * FROM {table} WHERE tenant_id=? AND project_id=? AND id=?',(who['tenant_id'],project,ref.id)).fetchone()
        if not row:raise HTTPException(404,'Destination connection unavailable in this project.')
        return dict(row)

    @app.get('/api/projects/{project}/sql-connections')
    def context(project:str,who=Depends(identity)):
        permit(who,'view')
        with db() as c:
            project_check(c,who,project)
            rows=[public(r) for r in c.execute('SELECT * FROM sql_connections WHERE tenant_id=? AND project_id=? ORDER BY name,id',(who['tenant_id'],project))]
            targets=[]
            for kind,table in [('read','read_connections'),('additional','external_connections'),('sql','sql_connections')]:
                for r in c.execute(f'SELECT id,name FROM {table} WHERE tenant_id=? AND project_id=?',(who['tenant_id'],project)):
                    targets.append({'kind':kind,'id':r['id'],'name':r['name']})
            mappings=[{**dict(r),'configuration':json.loads(r['configuration']),'preview':json.loads(r['preview'])} for r in c.execute('SELECT * FROM sql_mappings WHERE tenant_id=? AND project_id=? ORDER BY created DESC,id',(who['tenant_id'],project))]
            samples=[{'id':r['id'],'connection_id':r['connection_id'],'connection_name':r['name'],'object':json.loads(r['snapshot'])['object'],'observed':r['observed']} for r in c.execute('SELECT s.*,c.name FROM sql_snapshots s JOIN sql_connections c ON c.id=s.connection_id AND c.generation=s.generation WHERE s.tenant_id=? AND s.project_id=? AND s.expires>? ORDER BY s.observed DESC LIMIT 100',(who['tenant_id'],project,int(time.time())))]
        return {'connections':rows,'targets':targets,'mappings':mappings,'samples':samples,'driver':driver_status(),'server_version':app.version}

    @app.get('/api/projects/{project}/sql-connections/snapshots/{ident}')
    def prepared_sample(project:str,ident:str,who=Depends(identity)):
        permit(who,'view')
        with db() as c:row,conn,data=snapshot(c,who,project,ident)
        return {'id':row['id'],'connection_id':conn['id'],'snapshot':data,'observed':row['observed']}


    @app.post('/api/projects/{project}/sql-connections')
    def create(project:str,body:Config,who=Depends(identity)):
        permit(who,'connection');ident=str(uuid4())
        with db() as c:
            project_check(c,who,project)
            c.execute('INSERT INTO sql_connections VALUES(?,?,?,?,?,1,NULL)',(ident,who['tenant_id'],project,body.name,body.model_dump_json()))
            audit(c,who,'sql.connection_created',project,ident)
        return {'id':ident}

    @app.put('/api/projects/{project}/sql-connections/{ident}')
    def edit(project:str,ident:str,body:Config,who=Depends(identity)):
        permit(who,'connection')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');get(c,who,project,ident)
            c.execute('UPDATE sql_connections SET name=?,configuration=?,generation=generation+1,secret_ciphertext=NULL WHERE id=?',(body.name,body.model_dump_json(),ident))
            audit(c,who,'sql.connection_changed',project,ident)
        return {'credential_cleared':True,'snapshots_invalidated':True}

    @app.put('/api/projects/{project}/sql-connections/{ident}/credential')
    def credential(project:str,ident:str,body:Credential,who=Depends(identity)):
        permit(who,'connection')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');get(c,who,project,ident)
            c.execute('UPDATE sql_connections SET secret_ciphertext=?,generation=generation+1 WHERE id=?',(vault.encrypt(body.password.encode()).decode(),ident))
            audit(c,who,'sql.credential_replaced',project,ident)
        return {'stored':True}

    @app.delete('/api/projects/{project}/sql-connections/{ident}/credential')
    def clear(project:str,ident:str,who=Depends(identity)):
        permit(who,'connection')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');get(c,who,project,ident)
            c.execute('UPDATE sql_connections SET secret_ciphertext=NULL,generation=generation+1 WHERE id=?',(ident,))
            audit(c,who,'sql.credential_cleared',project,ident)
        return {'cleared':True}

    @app.post('/api/projects/{project}/sql-connections/{ident}/objects')
    def objects(project:str,ident:str,request:Request,who=Depends(identity)):
        permit(who,'connection')
        with db() as c:row=get(c,who,project,ident)
        result=run(row);fresh(request,who,project,row)
        with db() as c:audit(c,who,'sql.objects_read',project,ident)
        return result

    @app.post('/api/projects/{project}/sql-connections/{ident}/sample')
    def sample(project:str,ident:str,body:ObjectChoice,request:Request,who=Depends(identity)):
        permit(who,'connection')
        with db() as c:row=get(c,who,project,ident)
        result=run(row,body.model_dump());fresh(request,who,project,row)
        ident_snapshot=str(uuid4())
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if get(c,who,project,ident)['generation']!=row['generation']:raise HTTPException(409,'Connection changed; load again.')
            c.execute('INSERT INTO sql_snapshots VALUES(?,?,?,?,?,?,?,?)',(ident_snapshot,who['tenant_id'],project,ident,row['generation'],canonical(result),now(),int(time.time())+900))
            audit(c,who,'sql.sample_read',project,ident)
        return {'id':ident_snapshot,'connection_id':ident,'snapshot':result,'observed':now()}

    @app.get('/api/projects/{project}/sql-connections/target-fields/{kind}/{ident}')
    def prepared_fields(project:str,kind:Literal['read','additional','sql'],ident:str,who=Depends(identity)):
        permit(who,'view')
        with db() as c:
            row=target(c,who,project,Target(kind=kind,id=ident))
            catalog=c.execute('SELECT * FROM sql_field_catalogs WHERE connection_id=? AND tenant_id=? AND project_id=?',(ident,who['tenant_id'],project)).fetchone()
            if not catalog or catalog['generation']!=row['generation'] or catalog['expires']<=int(time.time()):raise HTTPException(409,'Ask the project owner to load current destination fields first.')
        return {'fields':json.loads(catalog['fields']),'scope':'Prepared project field inventory; no new vendor request sent.'}

    @app.post('/api/projects/{project}/sql-connections/target-fields')
    def target_fields(project:str,body:Target,request:Request,who=Depends(identity)):
        permit(who,'connection')
        with db() as c:row=target(c,who,project,body)
        if body.kind!='read' or row.get('provider')!='redeye':
            return {'fields':[],'scope':'Manual destination-field reference; native inventory discovery is currently provided for RedEye only.'}
        cfg=json.loads(row['configuration'])
        if os.getenv('ORBIT_ENABLE_LIVE_READS')!='1' or not cfg['approved_test_access'] or not cfg['vendor_settings_confirmed'] or not cfg['evidence_note'].strip():raise HTTPException(409,'Confirm RedEye settings/test access and enable local UAT reads.')
        try:
            base=approved_base('redeye',cfg['base_url'],[h.strip() for h in os.getenv('ORBIT_REDEYE_ALLOWED_HOSTS','').split(',')])
            secret=vault.decrypt(row['secret_ciphertext'].encode()).decode() if row['secret_ciphertext'] else ''
            auth_headers('redeye',secret,cfg['auth_header'],cfg['auth_prefix'])
            payload=redeye_pilot.request_vendor(base,secret,cfg,'GET','/api/v1/metadata-keys')
            values,_=resource_collection('redeye','metadata_keys',payload)
            if len(values)>2000:raise ProviderError('inventory_limit','RedEye key inventory exceeds 2,000 entries.')
            fields=[]
            for value in values:
                if not isinstance(value,dict) or not redeye_pilot.positive(value.get('id')) or not isinstance(value.get('name'),str) or not value['name'].strip() or len(value['name'])>250:raise ProviderError('contract_mismatch','RedEye key identity/name is invalid.')
                fields.append({'id':str(value['id']),'name':value['name']})
            if len({f['id'] for f in fields})!=len(fields) or len({f['name'].casefold() for f in fields})!=len(fields):raise ProviderError('contract_mismatch','Duplicate RedEye key IDs are ambiguous.')
        except ProviderError as e:raise HTTPException(502,e.message)
        except Exception:raise HTTPException(409,'RedEye credential is missing or unreadable.')
        current=identity(request);permit(current,'connection')
        if current!=who:raise HTTPException(409,'Identity changed during target discovery.')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if target(c,current,project,body)['generation']!=row['generation']:raise HTTPException(409,'Destination changed; reload its fields.')
            c.execute('INSERT OR REPLACE INTO sql_field_catalogs VALUES(?,?,?,?,?,?)',(who['tenant_id'],project,row['id'],row['generation'],canonical(fields),int(time.time())+900))
            audit(c,who,'sql.target_fields_read',project,row['id'])
        return {'fields':fields,'scope':'Existing RedEye metadata keys; this inventory read does not grant write permission.'}

    def compile_mapping(c,who,project,body):
        src,conn,data=snapshot(c,who,project,body.snapshot_id)
        columns={col['name']:col for col in data['columns']}
        if body.source_key not in columns or any(r.source not in columns for r in body.rules):raise HTTPException(422,'Select only columns from this exact SQL sample.')
        dest=target(c,who,project,body.target)
        def has_secret(value,secret):
            if isinstance(value,str):return secret in value
            if isinstance(value,dict):return any(has_secret(k,secret) or has_secret(v,secret) for k,v in value.items())
            if isinstance(value,list):return any(has_secret(v,secret) for v in value)
            return False
        for holder in [conn,dest]:
            if holder.get('secret_ciphertext'):
                try:secret=vault.decrypt(holder['secret_ciphertext'].encode()).decode()
                except Exception:raise HTTPException(409,'A connection credential is unreadable; replace it before mapping.')
                if secret and has_secret(body.model_dump(),secret):raise HTTPException(422,'Credentials cannot be used as mapping names, fields or defaults.')
        destination_fields=None
        dest_object=None
        if body.target.kind=='sql':
            dst,dst_conn,dst_data=snapshot(c,who,project,body.target_snapshot_id)
            if dst_conn['id']!=dest['id']:raise HTTPException(422,'Destination sample belongs to another SQL connection.')
            dest_object=dst_data['object'];destination_fields={col['name'] for col in dst_data['columns']}
            if body.target_match_field not in destination_fields:raise HTTPException(422,'Select a record-matching field from the destination SQL columns.')
            if conn['id']==dest['id'] and data['object']==dest_object:raise HTTPException(422,'Choose a different destination table or connection.')
        elif body.target.kind=='read' and dest['provider']=='redeye':
            catalog=c.execute('SELECT * FROM sql_field_catalogs WHERE connection_id=? AND tenant_id=? AND project_id=?',(dest['id'],who['tenant_id'],project)).fetchone()
            if not catalog or catalog['generation']!=dest['generation'] or catalog['expires']<=int(time.time()):raise HTTPException(409,'Load fresh destination RedEye metadata keys first.')
            destination_fields={f['name'] for f in json.loads(catalog['fields'])}
        if destination_fields is not None and any(r.target not in destination_fields for r in body.rules):raise HTTPException(422,'Choose only fields from the selected destination inventory.')
        output=[];seen=set();issues=[]
        for n,row in enumerate(data['rows']):
            key=row.get(body.source_key);key_text=canonical(key)
            row_errors=[]
            if isinstance(key,str) and (key.startswith(('[binary omitted]','[unsupported value omitted]')) or key.endswith(' [truncated]')):row_errors.append('Source record-matching value is omitted or truncated.')
            if key is None or key=='':row_errors.append('Missing source record-matching value.')
            if key_text in seen:row_errors.append('Duplicate matching value within this sample.')
            seen.add(key_text)
            mapped={}
            for rule in body.rules:
                value=row.get(rule.source)
                if isinstance(value,str) and (value.startswith(('[binary omitted]','[unsupported value omitted]')) or value.endswith(' [truncated]')):row_errors.append('Source value omitted/truncated: '+rule.source)
                value=rule.default if value is None or value=='' else value
                if rule.transform!='copy':
                    value=str(value)
                    value={'trim':str.strip,'uppercase':str.upper,'lowercase':str.lower}[rule.transform](value)
                if rule.required and (value is None or value==''):row_errors.append('Required destination value missing: '+rule.target)
                mapped[rule.target]=value
            output.append({'row':n+1,'match_value':key,'mapped_values':mapped,'issues':row_errors})
        if any(r['issues'] for r in output):issues.append('Resolve the sampled row matching/required-value findings before considering transfer.')
        if not output:issues.append('The selected sample has no rows.')
        preview={'source_connection':conn['name'],'source_object':data['object'],'source_generation':conn['generation'],
                 'target_connection':dest['name'],'target_generation':dest['generation'],'target_object':dest_object,
                 'target_match_field':body.target_match_field,'field_inventory_verified':destination_fields is not None,'rows':output,'issues':issues,
                 'scope':'Local mapping preview only. No destination records were queried/matched or written. Sample uniqueness does not prove table-wide uniqueness. No SQL or platform transfer executed.',
                 'source_snapshot_digest':digest(data),'configuration_digest':digest(body.model_dump())}
        return preview

    @app.post('/api/projects/{project}/sql-connections/mapping-preview')
    def mapping_preview(project:str,body:Mapping,who=Depends(identity)):
        permit(who,'draft')
        with db() as c:return compile_mapping(c,who,project,body)

    @app.post('/api/projects/{project}/sql-connections/mappings')
    def save_mapping(project:str,body:SaveMapping,who=Depends(identity)):
        permit(who,'draft')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');preview=compile_mapping(c,who,project,body)
            ident=body.id or str(uuid4());version=1
            if body.id:
                old=c.execute('SELECT version FROM sql_mappings WHERE id=? AND tenant_id=? AND project_id=?',(body.id,who['tenant_id'],project)).fetchone()
                if not old:raise HTTPException(404,'Mapping unavailable in this project.')
                if old['version']!=body.expected_version:raise HTTPException(409,'Mapping changed; reload before saving.')
                version=old['version']+1
            config=body.model_dump(exclude={'id','expected_version'})
            c.execute('INSERT INTO sql_mappings VALUES(?,?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,configuration=excluded.configuration,preview=excluded.preview,created=excluded.created,updated_by=excluded.updated_by',
                      (ident,who['tenant_id'],project,version,canonical(config),canonical(preview),now(),who['user_id']))
            audit(c,who,'sql.mapping_saved',project,ident)
        return {'id':ident,'version':version,'preview':preview,'written':False}

    app.state.sql_sample = sample
    app.state.sql_objects = objects
