"""Explicit loopback-only local operator bootstrap and real connector summaries.

This is a local workspace, not production login. Hosted use requires Entra.
"""
import hashlib
import json
import secrets
import time
from uuid import uuid4

from fastapi import Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, model_validator


class Names(BaseModel):
    model_config=ConfigDict(extra='forbid')
    workspace_name:str=Field(min_length=1,max_length=100)
    project_name:str=Field(min_length=1,max_length=100)
    operator_name:str=Field(default='Local operator',min_length=1,max_length=100)

    @model_validator(mode='after')
    def nonblank(self):
        for key in ('workspace_name','project_name','operator_name'):
            value=getattr(self,key).strip()
            if not value:raise ValueError('Names must not be blank.')
            setattr(self,key,value)
        return self


class OpenWorkspace(BaseModel):
    model_config=ConfigDict(extra='forbid')
    owner_id:str=Field(min_length=1,max_length=100)


class Rename(Names):
    project_id:str=Field(min_length=1,max_length=100)


class ProjectName(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name:str=Field(min_length=1,max_length=100)


def register_local_workspace(app,db,identity,permit,project_check,audit,now,local_mode):
    def local(request):
        if not local_mode:raise HTTPException(404,'Local workspace is not enabled.')
        if not request.client or request.client.host not in {'127.0.0.1','::1','testclient'}:
            raise HTTPException(403,'Local workspace access is restricted to this computer.')

    def sign_in(c,row,response,request):
        c.execute('DELETE FROM sessions WHERE token_hash=?',(hashlib.sha256(request.cookies.get('orbit_session','').encode()).hexdigest(),))
        token=secrets.token_urlsafe(32)
        c.execute('INSERT INTO sessions VALUES(?,?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),row['user_id'],row['tenant_id'],int(time.time())+28800))
        audit(c,row,'local.workspace_opened')
        response.set_cookie('orbit_session',token,httponly=True,samesite='strict',max_age=28800)

    @app.get('/api/local/status')
    def status(request:Request):
        local(request)
        with db() as c:
            workspaces=[]
            for row in c.execute("SELECT m.user_id,m.tenant_id,t.name,u.name AS operator_name FROM memberships m JOIN tenants t ON t.id=m.tenant_id JOIN users u ON u.id=m.user_id WHERE m.role='owner' ORDER BY t.id,m.user_id"):
                count=sum(c.execute(f'SELECT count(*) FROM {table} WHERE tenant_id=?',(row['tenant_id'],)).fetchone()[0] for table in ['read_connections','external_connections','sql_connections'])
                workspaces.append({**dict(row),'connection_count':count})
            workspaces.sort(key=lambda w:w['connection_count'],reverse=True)
            initialised=bool(c.execute('SELECT 1 FROM tenants').fetchone())
        return {'local_mode':True,'initialised':initialised,'workspaces':workspaces,'server_version':app.version}

    @app.post('/api/local/workspace')
    def create(body:Names,request:Request,response:Response):
        local(request)
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            if c.execute('SELECT 1 FROM tenants').fetchone():raise HTTPException(409,'An existing workspace is available; open it rather than replacing its connections.')
            tenant='workspace-'+str(uuid4());project='project-'+str(uuid4());user='operator-'+str(uuid4())
            c.execute('INSERT INTO tenants VALUES(?,?)',(tenant,body.workspace_name))
            c.execute('INSERT INTO projects VALUES(?,?,?)',(project,tenant,body.project_name))
            c.execute('INSERT INTO users VALUES(?,?)',(user,body.operator_name))
            c.execute('INSERT INTO memberships VALUES(?,?,?)',(tenant,user,'owner'))
            c.execute('INSERT INTO project_access VALUES(?,?,?)',(tenant,user,project))
            who={'tenant_id':tenant,'user_id':user,'role':'owner'}
            sign_in(c,who,response,request);audit(c,who,'local.workspace_created',project)
        return {'created':True,'project_id':project}

    @app.post('/api/local/session')
    def open_workspace(body:OpenWorkspace,request:Request,response:Response):
        local(request)
        with db() as c:
            row=c.execute("SELECT * FROM memberships WHERE user_id=? AND role='owner'",(body.owner_id,)).fetchone()
            if not row:raise HTTPException(404,'Local workspace owner is unavailable.')
            sign_in(c,dict(row),response,request)
        return {'opened':True}

    @app.put('/api/local/settings')
    def settings(body:Rename,request:Request,who=Depends(identity)):
        local(request);permit(who,'administer')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');project_check(c,who,body.project_id)
            c.execute('UPDATE tenants SET name=? WHERE id=?',(body.workspace_name,who['tenant_id']))
            c.execute('UPDATE projects SET name=? WHERE id=? AND tenant_id=?',(body.project_name,body.project_id,who['tenant_id']))
            c.execute('UPDATE users SET name=? WHERE id=?',(body.operator_name,who['user_id']))
            audit(c,who,'local.settings_updated',body.project_id)
        return {'saved':True}

    @app.post('/api/local/projects')
    def create_project(body:ProjectName,request:Request,who=Depends(identity)):
        local(request);permit(who,'connection')
        if not body.name.strip():raise HTTPException(422,'Enter a project name.')
        ident='project-'+str(uuid4())
        with db() as c:
            c.execute('INSERT INTO projects VALUES(?,?,?)',(ident,who['tenant_id'],body.name.strip()))
            c.execute('INSERT INTO project_access VALUES(?,?,?)',(who['tenant_id'],who['user_id'],ident))
            audit(c,who,'local.project_created',ident)
        return {'id':ident}

    @app.get('/api/projects/{project}/connection-summary')
    def summary(project:str,who=Depends(identity)):
        permit(who,'view')
        with db() as c:
            project_check(c,who,project);items=[]
            for table,kind in [('read_connections','read'),('external_connections','additional'),('sql_connections','sql')]:
                for row in c.execute(f'SELECT * FROM {table} WHERE tenant_id=? AND project_id=? ORDER BY name,id',(who['tenant_id'],project)):
                    row=dict(row);provider='sql' if kind=='sql' else row['provider']
                    last=json.loads(row['last_result']) if row.get('last_result') else None
                    if kind=='sql':
                        snap=c.execute('SELECT observed,snapshot FROM sql_snapshots WHERE connection_id=? AND generation=? ORDER BY observed DESC,rowid DESC LIMIT 1',(row['id'],row['generation'])).fetchone()
                        if snap:last={'observed':snap['observed'],'returned':len(json.loads(snap['snapshot'])['rows']),'operation':'SQL sample'}
                    items.append({'id':row['id'],'name':row['name'],'provider':provider,'kind':kind,'credential_present':bool(row['secret_ciphertext']),
                                  'last_read':last.get('observed') if last else None,'last_operation':last.get('operation') if last else None,
                                  'last_returned':last.get('returned') if last else None,'binding_count':len(json.loads(row['configuration']).get('bindings',[]))})
            reference=c.execute('SELECT configuration FROM bsdd_settings WHERE tenant_id=? AND project_id=?',(who['tenant_id'],project)).fetchone()
            bsdd=json.loads(reference['configuration']) if reference else {}
            mappings=c.execute('SELECT count(*) FROM sql_mappings WHERE tenant_id=? AND project_id=?',(who['tenant_id'],project)).fetchone()[0]
        return {'connections':items,'mapping_count':mappings,'dictionary':{'enabled':bool(bsdd.get('enabled')),'name':(bsdd.get('dictionary') or {}).get('name'),'property_count':len(bsdd.get('properties',[]))},'observed':now()}
