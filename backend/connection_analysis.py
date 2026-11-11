"""Provider-independent, read-only mapping, sample comparison and validation.

Snapshots are bounded evidence, never complete-platform or binary-file proof.
All live reads delegate to the existing scoped connector handlers.
"""
import datetime
import json
import time
from collections import defaultdict
from typing import Literal
from uuid import uuid4

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.integrations import canonical, digest
from backend.parameter_imports import definition, validate_value
from backend.record_data import fields, native_metadata, resource_records, OMITTED

Kind=Literal['read','additional','sql','bsdd']
Transform=Literal['copy','trim','uppercase','lowercase','filename_stem']


class Ref(BaseModel):
    model_config=ConfigDict(extra='forbid')
    kind:Kind
    id:str=Field(min_length=1,max_length=100)


class Capture(Ref):
    operation:str=Field(default='',max_length=50)
    schema_name:str=Field(default='',max_length=128)
    object_name:str=Field(default='',max_length=128)
    artefact_ids:list[int]=Field(default_factory=list,max_length=5)
    detail_limit:int=Field(default=5,ge=1,le=5)
    health_only:bool=False

    @model_validator(mode='after')
    def positive_ids(self):
        if self.operation and self.operation not in {'documents','artefacts','resources','companies','projects','field_definitions','metadata_keys','properties'}:raise ValueError('Choose a supported data operation.')
        if any(type(v) is not int or v<=0 or v>9007199254740991 for v in self.artefact_ids):raise ValueError('Use positive artefact IDs.')
        return self


class Rule(BaseModel):
    model_config=ConfigDict(extra='forbid')
    source_field:str=Field(min_length=1,max_length=500)
    target_field:str=Field(min_length=1,max_length=500)
    transform:Transform='copy'
    required:bool=False
    property_uri:str=Field(default='',max_length=1000)
    unit:str=Field(default='',max_length=100)
    interpret_strings:bool=False


class Mapping(BaseModel):
    model_config=ConfigDict(extra='forbid')
    id:str=Field(default='',max_length=100)
    expected_version:int=Field(default=0,ge=0)
    name:str=Field(min_length=1,max_length=100)
    source_snapshot:str=Field(min_length=1,max_length=100)
    target_snapshot:str=Field(min_length=1,max_length=100)
    source_key:str=Field(min_length=1,max_length=500)
    target_key:str=Field(min_length=1,max_length=500)
    key_mode:Literal['text','typed']='text'
    source_key_transform:Transform='trim'
    target_key_transform:Transform='trim'
    rules:list[Rule]=Field(min_length=1,max_length=50)

    @model_validator(mode='after')
    def distinct(self):
        if self.source_snapshot==self.target_snapshot:raise ValueError('Choose two distinct data scopes/snapshots.')
        if len({r.target_field for r in self.rules})!=len(self.rules):raise ValueError('Map each target field once.')
        return self


class Run(BaseModel):
    model_config=ConfigDict(extra='forbid')
    expected_version:int=Field(ge=1)


def transform(value,mode):
    if value is None or mode=='copy':return value
    if isinstance(value,list):return [transform(v,mode) for v in value]
    text=str(value)
    if mode=='trim':return text.strip()
    if mode=='uppercase':return text.upper()
    if mode=='lowercase':return text.lower()
    if mode=='filename_stem':
        name=text.replace('\\','/').rsplit('/',1)[-1]
        return name.rsplit('.',1)[0] if '.' in name and not name.startswith('.') else name
    return value


def unavailable(value):
    if isinstance(value,str):return value==OMITTED or '[REDACTED]' in value or value.startswith(('[binary omitted]','[unsupported value omitted]')) or value.endswith(' [truncated]')
    return isinstance(value,list) and any(unavailable(v) for v in value)


def key_value(record,column,mode,normalise):
    values=record['values']
    if column not in values:return None,'Matching field was not captured.'
    value=values[column]
    if value is None or isinstance(value,(list,dict)) or unavailable(value):return None,'Matching value is missing, multi-valued or unavailable.'
    value=transform(value,normalise)
    if isinstance(value,str) and not value.strip():return None,'Matching value is blank.'
    if mode=='text':return str(value).strip(),None
    return canonical(value),None


def evaluate(source,target,config,definitions):
    """Pure comparison: no I/O, mutations or provider-specific assumptions."""
    indexes=[];quality=[];invalid_records=set();key_problems=[]
    def validation(record,side,rule):
        column=rule[side+'_field'];values=record['values']
        if column not in values or unavailable(values.get(column)):return ['Field value was not captured; validation is unknown.'],True
        value=transform(values[column],rule['transform']);errors=[]
        if rule['required'] and (value is None or value=='' or isinstance(value,str) and not value.strip() or value==[]):errors.append('Required value is missing.')
        if rule.get('property_uri'):
            prop=definitions[rule['property_uri']]
            spec,problems=definition(prop,{'target_name':'ComparisonValue','unit':rule['unit'],'required':rule['required']})
            errors.extend(problems)
            if value is not None:
                typed=value
                if rule.get('interpret_strings') and prop.get('dataType')!='String':
                    try:typed=[json.loads(v) if isinstance(v,str) else v for v in value] if isinstance(value,list) else json.loads(value) if isinstance(value,str) else value
                    except ValueError:errors.append('Native text cannot be interpreted as the selected bSDD type.')
                problem=validate_value(typed,spec)
                if problem:errors.append(problem)
        return errors,False
    for side,snapshot in [('source',source),('target',target)]:
        index=defaultdict(list)
        for record in snapshot['records']:
            key,problem=key_value(record,config[side+'_key'],config['key_mode'],config[side+'_key_transform'])
            if problem:key_problems.append({'side':side,'record_id':record['id'],'reason':problem})
            else:index[key].append(record)
            for rule in config['rules']:
                errors,unknown=validation(record,side,rule)
                if errors:
                    quality.append({'side':side,'record_id':record['id'],'field':rule[side+'_field'],'status':'unknown' if unknown else 'invalid','issues':errors})
                    if not unknown:invalid_records.add((side,record['id']))
        indexes.append(index)
    left,right=indexes;rows=[];counts={k:0 for k in ['matched','different','invalid','unknown','ambiguous','not_in_source_sample','not_in_target_sample']}
    for key in sorted(set(left)|set(right)):
        a,b=left.get(key,[]),right.get(key,[]);checks=[]
        if len(a)>1 or len(b)>1:status='ambiguous'
        elif not a:status='not_in_source_sample'
        elif not b:status='not_in_target_sample'
        else:
            for rule in config['rules']:
                av=a[0]['values'];bv=b[0]['values'];ae,au=validation(a[0],'source',rule);be,bu=validation(b[0],'target',rule)
                va=transform(av.get(rule['source_field']),rule['transform']);vb=transform(bv.get(rule['target_field']),rule['transform'])
                state='invalid' if ae and not au or be and not bu else 'unknown' if au or bu or va is None and vb is None or va=='' and vb=='' or va==[] and vb==[] else 'matched' if canonical(va)==canonical(vb) else 'different'
                checks.append({'source_field':rule['source_field'],'target_field':rule['target_field'],'source_value':va,'target_value':vb,'status':state,'issues':list(dict.fromkeys(ae+be))})
            statuses={c['status'] for c in checks}
            status='invalid' if 'invalid' in statuses else 'different' if 'different' in statuses else 'unknown' if 'unknown' in statuses else 'matched'
        counts[status]+=1
        rows.append({'match_key':key,'status':status,'source_ids':[r['id'] for r in a],'target_ids':[r['id'] for r in b],'fields':checks})
    return {'counts':counts,'rows':rows,'matching_issues':key_problems,'validation_findings':quality,
            'quality':{'invalid_records':len(invalid_records),'invalid_fields':sum(q['status']=='invalid' for q in quality),'unknown_fields':sum(q['status']=='unknown' for q in quality)+sum(f['status']=='unknown' and not f['issues'] for r in rows for f in r['fields'])},
            'record_counts':{'source':len(source['records']),'target':len(target['records'])},
            'outcome':'no_data' if not source['records'] or not target['records'] else 'findings' if any(v for k,v in counts.items() if k!='matched') or key_problems or invalid_records else 'sample_matches',
            'scope':'Captured samples only. A missing counterpart means not in this sample, not absent from the platform. Matching metadata does not prove binary equality or whole-project compliance.',
            'written':False}


def register_connection_analysis(app,db,identity,permit,project_check,audit,vault,now):
    def source(c,who,project,ref):
        project_check(c,who,project)
        if ref.kind=='bsdd':
            row=c.execute('SELECT * FROM bsdd_settings WHERE tenant_id=? AND project_id=?',(who['tenant_id'],project)).fetchone()
            cfg=json.loads(row['configuration']) if row else {}
            if ref.id!='reference' or not cfg.get('enabled') or not cfg.get('properties'):raise HTTPException(404,'Enable a project bSDD property reference first.')
            return {'id':'reference','name':'bSDD property reference','generation':row['version'],'provider':'bsdd','configuration':canonical(cfg)}
        table={'read':'read_connections','additional':'external_connections','sql':'sql_connections'}[ref.kind]
        row=c.execute(f'SELECT * FROM {table} WHERE tenant_id=? AND project_id=? AND id=?',(who['tenant_id'],project,ref.id)).fetchone()
        if not row:raise HTTPException(404,'Connection unavailable in this project.')
        result=dict(row)
        if ref.kind=='sql':result['provider']='sql'
        return result

    def saved(c,who,project,ident):
        project_check(c,who,project)
        row=c.execute('SELECT * FROM connection_snapshots WHERE id=? AND tenant_id=? AND project_id=?',(ident,who['tenant_id'],project)).fetchone()
        if not row:raise HTTPException(404,'Captured sample unavailable in this project.')
        result=dict(row)
        for key in ['scope','records','coverage']:result[key]=json.loads(result[key])
        return result

    def fresh(c,who,project,snap):
        current=source(c,who,project,Ref(kind=snap['kind'],id=snap['connection_id']))
        if current['generation']!=snap['generation']:raise HTTPException(409,'Connection/reference changed; read a new sample before comparing.')
        if snap['expires']<=int(time.time()):raise HTTPException(409,'Sample expired; read fresh data before comparing.')
        return current

    def save_snapshot(c,who,project,ref,row,operation,scope,records,coverage,observed=None,expires=None,schema_fields=None):
        normal=[];notes=[];secret=''
        if row.get('secret_ciphertext'):
            try:secret=vault.decrypt(row['secret_ciphertext'].encode()).decode()
            except Exception:raise HTTPException(409,'Credential changed or is unreadable; reconnect and read again.')
        if len(records)>50:notes.append('Only the first 50 records were captured.')
        for r in records[:50]:
            if len(r['values'])>200:notes.append('Some fields were omitted at the 200-field limit.')
            normal.append({'id':OMITTED if secret and secret in str(r['id']) else str(r['id'])[:500],'values':fields(r['values'],secret,limit=200)})
        while len(canonical(normal))>250000 and normal:
            normal.pop();notes.append('Some records were omitted at the 250 KB capture limit.')
        ident=str(uuid4());observed=observed or now();expires=expires or int(time.time())+(900 if ref.kind=='sql' else 1800)
        cov={'description':coverage,'notes':list(dict.fromkeys(notes)),'complete':False,'fields':schema_fields or []}
        c.execute('INSERT INTO connection_snapshots VALUES(?,?,?,?,?,?,?,?,?,?,?,?)',(ident,who['tenant_id'],project,ref.kind,row['id'],row['generation'],operation,canonical(scope),canonical(normal),observed,expires,canonical(cov)))
        audit(c,who,'analysis.sample_captured',project,ident)
        return saved(c,who,project,ident)

    def check(c,who,project,ref,row,status,code):
        c.execute('INSERT INTO connection_checks VALUES(?,?,?,?,?,?,?,?,?)',(str(uuid4()),who['tenant_id'],project,ref.kind,row['id'],row['generation'],status,code,now()))

    def field_names(snap):return sorted({key for r in snap['records'] for key in r['values']}|set(snap['coverage'].get('fields',[])))

    def descriptor(c,who,project,snap):
        result={k:v for k,v in snap.items() if k not in {'tenant_id','project_id','records'}}
        result.update(fields=field_names(snap),record_count=len(snap['records']))
        try:fresh(c,who,project,snap);result['fresh']=True
        except HTTPException:result['fresh']=False
        return result

    def import_sql(c,who,project):
        # Reuse actual stored SQL samples, never synthetic document registers.
        rows=c.execute('SELECT s.*,p.name,p.configuration,p.generation AS current_generation FROM sql_snapshots s JOIN sql_connections p ON p.id=s.connection_id WHERE s.tenant_id=? AND s.project_id=? ORDER BY s.observed DESC LIMIT 40',(who['tenant_id'],project)).fetchall()
        for r in rows:
            data=json.loads(r['snapshot']);scope=data['object']
            existing=c.execute("SELECT 1 FROM connection_snapshots WHERE tenant_id=? AND project_id=? AND kind='sql' AND connection_id=? AND observed=? AND scope=?",(who['tenant_id'],project,r['connection_id'],r['observed'],canonical(scope))).fetchone()
            if existing:continue
            records=[{'id':str(n+1),'values':v} for n,v in enumerate(data['rows'])]
            save_snapshot(c,who,project,Ref(kind='sql',id=r['connection_id']),{'id':r['connection_id'],'generation':r['generation']},'table_rows',scope,records,data['scope'],r['observed'],r['expires'],[col['name'] for col in data['columns']])

    @app.get('/api/projects/{project}/analysis')
    def context(project:str,who=Depends(identity)):
        permit(who,'view')
        with db() as c:
            project_check(c,who,project);import_sql(c,who,project)
            connections=[]
            for kind,table in [('read','read_connections'),('additional','external_connections'),('sql','sql_connections')]:
                for r in c.execute(f'SELECT * FROM {table} WHERE tenant_id=? AND project_id=? ORDER BY name,id',(who['tenant_id'],project)):
                    row=dict(r);cfg=json.loads(row['configuration']);provider='sql' if kind=='sql' else row['provider']
                    last=c.execute('SELECT * FROM connection_checks WHERE tenant_id=? AND project_id=? AND kind=? AND connection_id=? AND generation=? ORDER BY observed DESC,rowid DESC LIMIT 1',(who['tenant_id'],project,kind,row['id'],row['generation'])).fetchone()
                    age=(datetime.datetime.now(datetime.timezone.utc)-datetime.datetime.fromisoformat(last['observed'])).total_seconds() if last else None
                    state='unverified' if not last else 'needs_setup' if last['status']=='blocked' else 'failed' if last['status']=='failed' else 'stale' if age>1800 else 'read_verified'
                    connections.append({'kind':kind,'id':row['id'],'name':row['name'],'provider':provider,'generation':row['generation'],'health':state,'last_check':last['observed'] if last else None,'last_code':last['code'] if last else None,
                                        'scope_hint':cfg.get('folder_label') or cfg.get('scope_reference') or cfg.get('database') or cfg.get('view_id') or 'Choose a data scope'})
            reference=c.execute('SELECT configuration FROM bsdd_settings WHERE tenant_id=? AND project_id=?',(who['tenant_id'],project)).fetchone()
            cfg=json.loads(reference['configuration']) if reference else {}
            if cfg.get('enabled') and cfg.get('properties'):connections.append({'kind':'bsdd','id':'reference','name':'bSDD property reference','provider':'bsdd','generation':0,'health':'local_reference','last_check':None,'last_code':None,'scope_hint':'Selected project definitions'})
            snaps=[descriptor(c,who,project,saved(c,who,project,r['id'])) for r in c.execute('SELECT id FROM connection_snapshots WHERE tenant_id=? AND project_id=? ORDER BY observed DESC,rowid DESC LIMIT 150',(who['tenant_id'],project))]
            mappings=[{**dict(r),'configuration':json.loads(r['configuration'])} for r in c.execute('SELECT * FROM connection_mappings WHERE tenant_id=? AND project_id=? ORDER BY created DESC,id',(who['tenant_id'],project))]
            reports=[]
            for r in c.execute('SELECT * FROM connection_comparisons WHERE tenant_id=? AND project_id=? ORDER BY created DESC,rowid DESC LIMIT 100',(who['tenant_id'],project)):
                report=json.loads(r['report']);stale=False
                for ident in [r['source_snapshot'],r['target_snapshot']]:
                    try:fresh(c,who,project,saved(c,who,project,ident))
                    except HTTPException:stale=True
                current=next((m for m in mappings if m['id']==r['mapping_id']),None)
                if report['configuration'].get('reference'):
                    try:
                        _,reference_now=definitions(c,who,project,report['configuration']['rules'])
                        stale=stale or reference_now!=report['configuration']['reference']
                    except HTTPException:stale=True
                reports.append({'id':r['id'],'mapping_id':r['mapping_id'],'mapping_version':r['mapping_version'],'name':report['mapping_name'],'counts':report['counts'],'quality':report['quality'],'outcome':report['outcome'],'created':r['created'],'stale':stale or not current or current['version']!=r['mapping_version']})
        health={s:sum(x['health']==s for x in connections) for s in ['read_verified','failed','blocked','needs_setup','stale','unverified']}
        latest={}
        for r in reports:latest.setdefault(r['mapping_id'],r)
        active=[r for r in latest.values() if not r['stale']]
        return {'connections':connections,'snapshots':snaps,'mappings':mappings,'reports':reports,'properties':cfg.get('properties',[]) if cfg.get('enabled') else [],
                'health':health,'validation':{'mappings':len(mappings),'never_compared':sum(m['id'] not in latest for m in mappings),'fresh_reports':len(active),'stale_reports':sum(r['stale'] for r in latest.values()),'invalid_fields':sum(r['quality']['invalid_fields'] for r in active),'unknown_fields':sum(r['quality']['unknown_fields'] for r in active),'differences':sum(r['counts']['different'] for r in active),'unmatched_in_samples':sum(r['counts']['not_in_source_sample']+r['counts']['not_in_target_sample'] for r in active)},'scope':'Recorded checks and sampled validation, not continuous monitoring or whole-platform assurance.'}

    @app.post('/api/projects/{project}/analysis/capture')
    def capture(project:str,body:Capture,request:Request,who=Depends(identity)):
        permit(who,'connection')
        ref=Ref(kind=body.kind,id=body.id)
        with db() as c:row=source(c,who,project,ref)
        cfg=json.loads(row['configuration']);scope={};records=[];coverage='Bounded observed data only.';operation=body.operation;schema_fields=[]
        try:
            if body.kind=='sql':
                if body.health_only:
                    result=app.state.sql_objects(project,row['id'],request,who);operation='objects'
                else:
                    from backend.sql_connections import ObjectChoice
                    if not body.schema_name or not body.object_name:raise HTTPException(409,'Choose a SQL schema/table or use a prepared SQL sample.')
                    result=app.state.sql_sample(project,row['id'],ObjectChoice(schema_name=body.schema_name,object_name=body.object_name),request,who)
                    schema_fields=[col['name'] for col in result['snapshot']['columns']];scope=result['snapshot']['object'];operation='table_rows';records=[{'id':str(i+1),'values':v} for i,v in enumerate(result['snapshot']['rows'])];coverage=result['snapshot']['scope']
            elif body.kind=='bsdd':
                operation='properties';scope={'dictionary':(cfg.get('dictionary') or {}).get('uri'),'class':(cfg.get('class') or {}).get('uri')}
                records=[{'id':p['uri'],'values':fields(p)} for p in cfg['properties']];coverage='Saved, selected project bSDD definitions; not document data.'
            elif body.kind=='read':
                from backend.read_connections import ReadRequest
                if row['provider']=='redeye' and not body.health_only and operation!='metadata_keys':
                    from backend.redeye_metadata import Selection
                    ids=body.artefact_ids
                    if not ids:
                        result=app.state.profile_read(project,row['id'],ReadRequest(operation='artefacts'),who)
                        try:ids=[int(r['id']) for r in result['resources'][:body.detail_limit]]
                        except (ValueError,TypeError):raise HTTPException(502,'Artefact inventory did not return supported numeric IDs.')
                    for ident in ids[:body.detail_limit]:
                        data=app.state.metadata_inspect(project,Selection(connection_id=row['id'],artefact_id=ident),request,who)
                        records.append(native_metadata(data['snapshot']))
                    operation='document_metadata';scope={'artefact_ids':body.artefact_ids,'detail_limit':body.detail_limit,'selection':'explicit_ids' if body.artefact_ids else 'first_bounded_page'}
                    coverage=f'At most {body.detail_limit} artefacts with metadata from explicit IDs or a bounded first artefact page. Not a complete register.'
                else:
                    operation='metadata_keys' if row['provider']=='redeye' else 'documents' if cfg.get('vendor_project') and cfg.get('folder') else 'hubs' if body.health_only else 'documents'
                    result=app.state.profile_read(project,row['id'],ReadRequest(operation=operation,hub=cfg.get('hub',''),project=cfg.get('vendor_project',''),folder=cfg.get('folder','')),who)
                    records=resource_records(result['resources']);scope={k:cfg.get(k,'') for k in ['hub','vendor_project','folder']};coverage=result['coverage']
            else:
                from backend.additional_connections import Read
                operation=body.operation or ('documents' if row['provider']=='meridian' else 'field_definitions' if row['provider']=='procore' and cfg.get('company_id') else 'companies' if row['provider']=='procore' else 'resources')
                result=app.state.additional_read(project,row['id'],request,Read(operation=operation),who)
                records=resource_records(result['resources']);coverage=result['coverage'];scope={k:cfg.get(k) for k in ['company_id','project_id','view_id','filter_name','scope_reference','collection_path','scope_parameters','property_names'] if cfg.get(k)}
        except HTTPException as e:
            with db() as c:
                project_check(c,who,project);check(c,who,project,ref,row,'blocked' if e.status_code in {400,403,409,422} else 'failed',e.detail.get('code','read_failed') if isinstance(e.detail,dict) else 'setup_required' if e.status_code==409 else 'read_failed')
            raise
        current=identity(request);permit(current,'connection')
        if current!=who:raise HTTPException(409,'Identity changed; sample discarded.')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');latest=source(c,current,project,ref)
            if latest['generation']!=row['generation']:raise HTTPException(409,'Connection changed during capture; read again.')
            check(c,current,project,ref,row,'success',operation)
            if body.health_only:return {'checked':True,'operation':operation,'written':False}
            snap=save_snapshot(c,current,project,ref,row,operation,scope,records,coverage,schema_fields=schema_fields)
        return {'snapshot':descriptor_for_response(snap),'written':False}

    def descriptor_for_response(snap):
        return {**snap,'fields':field_names(snap),'record_count':len(snap['records']),'fresh':True}

    def mapping(c,who,project,ident):
        project_check(c,who,project)
        row=c.execute('SELECT * FROM connection_mappings WHERE id=? AND tenant_id=? AND project_id=?',(ident,who['tenant_id'],project)).fetchone()
        if not row:raise HTTPException(404,'Mapping unavailable in this project.')
        return dict(row)

    def definitions(c,who,project,rules):
        requested={r['property_uri'] for r in rules if r.get('property_uri')}
        if not requested:return {},None
        row=c.execute('SELECT version,configuration FROM bsdd_settings WHERE tenant_id=? AND project_id=?',(who['tenant_id'],project)).fetchone();cfg=json.loads(row['configuration']) if row else {}
        props={p['uri']:p for p in cfg.get('properties',[])}
        if not cfg.get('enabled') or not requested.issubset(props):raise HTTPException(409,'Choose currently selected project bSDD definitions, or remove that validation rule.')
        for r in rules:
            if r.get('property_uri'):
                _,errors=definition(props[r['property_uri']],{'target_name':'ComparisonValue','unit':r['unit'],'required':r['required']})
                if errors:raise HTTPException(422,'; '.join(errors))
        return {uri:props[uri] for uri in requested},{'version':row['version'],'digest':digest(cfg)}

    @app.post('/api/projects/{project}/analysis/mappings')
    def save_mapping(project:str,body:Mapping,who=Depends(identity)):
        permit(who,'draft')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');left=saved(c,who,project,body.source_snapshot);right=saved(c,who,project,body.target_snapshot)
            a=fresh(c,who,project,left);b=fresh(c,who,project,right)
            if body.source_key not in field_names(left) or body.target_key not in field_names(right):raise HTTPException(422,'Choose matching fields from both captured samples.')
            if any(r.source_field not in field_names(left) or r.target_field not in field_names(right) for r in body.rules):raise HTTPException(422,'Choose mapping fields from the captured source and target schemas.')
            def contains(value,secret):
                if isinstance(value,str):return secret in value
                if isinstance(value,dict):return any(contains(k,secret) or contains(v,secret) for k,v in value.items())
                if isinstance(value,list):return any(contains(v,secret) for v in value)
                return False
            for holder in [a,b]:
                if holder.get('secret_ciphertext'):
                    try:secret=vault.decrypt(holder['secret_ciphertext'].encode()).decode()
                    except Exception:raise HTTPException(409,'A credential is unreadable; update its connection before mapping.')
                    if secret and contains(body.model_dump(),secret):raise HTTPException(422,'Credentials cannot be used as mapping names or field references.')
            props,reference=definitions(c,who,project,[r.model_dump() for r in body.rules])
            config=body.model_dump(exclude={'id','expected_version'})
            config.update(source={'kind':left['kind'],'id':left['connection_id'],'name':a['name'],'provider':a['provider'],'operation':left['operation'],'scope':left['scope']},target={'kind':right['kind'],'id':right['connection_id'],'name':b['name'],'provider':b['provider'],'operation':right['operation'],'scope':right['scope']},reference=reference)
            ident=body.id or str(uuid4());version=1
            if body.id:
                old=mapping(c,who,project,body.id)
                if old['version']!=body.expected_version:raise HTTPException(409,'Mapping changed; reload before saving.')
                version=old['version']+1
            c.execute('INSERT INTO connection_mappings VALUES(?,?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET version=excluded.version,configuration=excluded.configuration,created=excluded.created,updated_by=excluded.updated_by',(ident,who['tenant_id'],project,version,canonical(config),now(),who['user_id']))
            c.execute('INSERT INTO connection_mapping_history VALUES(?,?,?,?,?)',(ident,version,canonical(config),digest(config),now()))
            audit(c,who,'analysis.mapping_saved',project,ident)
        return {'id':ident,'version':version,'written':False}

    @app.post('/api/projects/{project}/analysis/mappings/{ident}/compare')
    def compare(project:str,ident:str,body:Run,who=Depends(identity)):
        permit(who,'run')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');m=mapping(c,who,project,ident)
            if m['version']!=body.expected_version:raise HTTPException(409,'Mapping changed; reload before comparing.')
            config=json.loads(m['configuration']);snaps=[]
            for side in ['source','target']:
                ref=config[side]
                row=c.execute('SELECT id FROM connection_snapshots WHERE tenant_id=? AND project_id=? AND kind=? AND connection_id=? AND operation=? AND scope=? ORDER BY observed DESC,rowid DESC LIMIT 1',(who['tenant_id'],project,ref['kind'],ref['id'],ref['operation'],canonical(ref['scope']))).fetchone()
                if not row:raise HTTPException(409,'Read the selected data scope again before comparing.')
                snap=saved(c,who,project,row['id']);fresh(c,who,project,snap);snaps.append(snap)
            props,reference=definitions(c,who,project,config['rules'])
            if reference!=config['reference']:raise HTTPException(409,'bSDD reference changed; review/save the mapping again.')
            report=evaluate(snaps[0],snaps[1],config,props)
            report.update(mapping_name=config['name'],configuration=config,source={k:snaps[0][k] for k in ['id','observed','coverage','operation','scope']},target={k:snaps[1][k] for k in ['id','observed','coverage','operation','scope']})
            report['warnings']=[]
            if config['source']['operation']!=config['target']['operation']:report['warnings'].append('The data scopes are different kinds; verify the selected matching fields and semantic meaning.')
            if config['source_key']=='id' and config['target_key']=='id' and config['source']['provider']!=config['target']['provider']:report['warnings'].append('Native IDs from different platforms usually have different namespaces. Confirm this key choice.')
            rid=str(uuid4());created=now()
            if len(canonical(report))>1500000:raise HTTPException(422,'Comparison report exceeds 1.5 MB. Reduce the selected scope or number of mapped fields.')
            c.execute('INSERT INTO connection_comparisons VALUES(?,?,?,?,?,?,?,?,?)',(rid,who['tenant_id'],project,ident,m['version'],snaps[0]['id'],snaps[1]['id'],canonical(report),created))
            audit(c,who,'analysis.comparison_completed',project,rid)
        return {'id':rid,'created':created,'report':report}

    @app.get('/api/projects/{project}/analysis/reports/{ident}')
    def report(project:str,ident:str,who=Depends(identity)):
        permit(who,'view')
        with db() as c:
            project_check(c,who,project)
            row=c.execute('SELECT * FROM connection_comparisons WHERE id=? AND tenant_id=? AND project_id=?',(ident,who['tenant_id'],project)).fetchone()
            if not row:raise HTTPException(404,'Comparison unavailable in this project.')
        return {'id':row['id'],'created':row['created'],'report':json.loads(row['report'])}
