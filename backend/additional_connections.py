"""Additional scoped metadata readers. No remote field/value writer is exposed."""
import importlib.util
import base64
import ipaddress
import json
import os
import re
import time
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

import httpx
from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.meridian import EXPLORER_FIXTURE, explorer_documents
from backend.providers import ProviderError, auth_headers

PROCORE_BASE = 'https://api.procore.com'


def approved_url(value):
    try:
        url = urlsplit(value)
        if url.scheme != 'https' or not url.hostname or url.username or url.password or url.query or url.fragment or any(c.isspace() for c in value) or '%' in url.path or '\\' in value:
            raise ValueError()
        _ = url.port
        if any(p in {'.', '..'} for p in url.path.split('/')) or '//' in url.path:
            raise ValueError()
        try:
            address = ipaddress.ip_address(url.hostname)
        except ValueError:
            address = None
        if address and getattr(address, 'ipv4_mapped', None):address = address.ipv4_mapped
        if url.hostname.lower() in {'localhost', 'metadata.google.internal'} or address and (address.is_loopback or address.is_link_local or address.is_unspecified or address.is_multicast):
            raise ValueError()
    except ValueError:
        raise ProviderError('invalid_base', 'Use an approved HTTPS API application URL without credentials, query, fragments or traversal. Loopback/link-local destinations are not supported.')
    host = url.hostname.lower()
    netloc = ('[' + host + ']') if ':' in host else host
    if url.port and url.port != 443:netloc += ':' + str(url.port)
    origin = 'https://' + netloc
    return origin + url.path.rstrip('/'), origin


def pointer(value, path):
    if path == '':return value
    if not path.startswith('/') or len(path) > 250:
        raise ProviderError('contract_mismatch', 'Use a JSON Pointer starting with /, or empty for the whole response.')
    for part in path[1:].split('/'):
        part = part.replace('~1', '/').replace('~0', '~')
        if not isinstance(value, dict) or part not in value:
            raise ProviderError('contract_mismatch', 'A configured JSON Pointer was not present in the response.')
        value = value[part]
    return value


def read_headers(cfg, secret):
    mode = cfg['auth_mode']
    if mode == 'bearer':return auth_headers('forma', secret)
    if mode == 'api_key':return auth_headers('redeye', secret, cfg['auth_header'], cfg['auth_prefix'])
    if mode == 'basic':
        if ':' not in secret or any(c in secret for c in '\r\n'):
            raise ProviderError('invalid_credential', 'Store a Basic credential as username:password without line breaks.')
        user, password = secret.split(':', 1)
        if not user or not password:raise ProviderError('invalid_credential', 'Basic authentication needs both a username and password.')
        return {'Accept': 'application/json', 'Authorization': 'Basic ' + base64.b64encode(secret.encode()).decode()}
    return {'Accept': 'application/json'}


def windows_auth_available():
    return os.name == 'nt' and importlib.util.find_spec('requests_negotiate_sspi') is not None


def read_json(url, params, cfg, secret, transport=None):
    headers = read_headers(cfg, secret)
    headers['User-Agent'] = 'ORBIT/0.8.0'
    if cfg.get('_company_header'):
        headers['Procore-Company-Id'] = cfg['_company_header']
    def consume(response, chunks):
        if response.status_code in {401, 403}:raise ProviderError('access_denied', 'Authentication or resource permission was rejected. No records imported.')
        if response.status_code == 429:raise ProviderError('rate_limited', 'Provider rate limit reached; retry later.')
        if response.status_code != 200:raise ProviderError('read_rejected', 'Provider did not return HTTP 200. Redirects are not followed.')
        content, size = [], 0
        for chunk in chunks:
            size += len(chunk)
            if size > 1_000_000:raise ProviderError('response_too_large', 'Response exceeds the bounded 1 MB metadata-read limit.')
            content.append(chunk)
        return json.loads(b''.join(content))
    try:
        if cfg['auth_mode'] == 'windows_integrated':
            if not windows_auth_available():
                raise ProviderError('windows_auth_unavailable', 'Windows integrated authentication requires a local Windows executor and the optional Windows auth package. No Windows password is stored by ORBIT.')
            try:
                import requests
                from requests_negotiate_sspi import HttpNegotiateAuth
                with requests.Session() as session:
                    session.auth = HttpNegotiateAuth(delegate=False)
                    with session.get(url, params=params, headers=headers, timeout=(5, 15), stream=True, allow_redirects=False, verify=True) as response:
                        return consume(response, response.iter_content(65536))
            except ProviderError:
                raise
            except Exception:
                raise ProviderError('read_failed', 'Windows-authenticated read failed. Verify the API, current Windows identity, private route and CA trust.')
        with httpx.Client(transport=transport, timeout=httpx.Timeout(15, connect=5), follow_redirects=False, trust_env=True) as client:
            with client.stream('GET', url, params=params, headers=headers) as response:
                return consume(response, response.iter_bytes())
    except (httpx.HTTPError, ValueError):
        raise ProviderError('read_failed', 'Metadata read failed. Verify network access, certificate trust and the documented response contract.')


def read_resources(cfg, secret, operation, page=1, transport=None):
    base, _ = approved_url(cfg['base_url'])
    provider = cfg['provider']
    if provider == 'procore':
        if operation not in {'companies', 'projects', 'field_definitions'}:raise ProviderError('unsupported_operation', 'Select companies, projects or field definitions for Procore.')
        if operation in {'projects','field_definitions'} and not cfg['company_id']:raise ProviderError('scope_required', 'Read companies and save a company before loading projects.')
        path = '/rest/v1.0/' + operation
        params = {'page': page, 'per_page': 25}
        if operation == 'companies':params['view'] = 'compact'
        if operation == 'field_definitions':
            path = '/rest/v2.0/companies/' + cfg['company_id'] + '/custom_field_definitions'
            params['tool_name'] = cfg['procore_tool']
        if operation == 'projects':
            params['company_id'] = cfg['company_id']
            params['serializer_view'] = 'compact'
        read_cfg = dict(cfg)
        # Company header is required for project requests; do not send it to list companies.
        if operation in {'projects','field_definitions'}:
            read_cfg = {**cfg, '_company_header': cfg['company_id']}
        payload = read_json(base + path, params, read_cfg, secret, transport)
        if operation == 'field_definitions' and not isinstance(payload, dict):
            raise ProviderError('contract_mismatch', 'Expected the documented Procore field-definition data wrapper.')
        rows = payload.get('data') if operation == 'field_definitions' else payload
        if not isinstance(rows, list):raise ProviderError('contract_mismatch', 'Expected Procore resource array, or the documented data wrapper for field definitions.')
    elif provider == 'meridian':
        if operation != 'documents':raise ProviderError('unsupported_operation', 'Meridian Explorer supports the bounded documents read.')
        params = {'VIEWID': cfg['view_id'], 'DOCFILTER': cfg['filter_name'], 'PAGEINDEX': 0, 'PAGESIZE': 25}
        if cfg['property_names']:params['pn'] = '|'.join(cfg['property_names'])
        payload = read_json(base + '/api/GetDocuments.ashx', params, cfg, secret, transport)
        parsed = explorer_documents(payload)
        return {**parsed, 'resources': [{'id': r['document_id'], 'label': r['name'], 'kind': 'document', 'version_id': r['version_id'], 'revision': r['revision']} for r in parsed['resources']], 'operation': operation, 'synthetic': False, 'coverage': 'First bounded Explorer response; repository freshness and paging semantics are not established.'}
    else:
        if operation != 'resources':raise ProviderError('unsupported_operation', 'This configured REST connection supports resources only.')
        payload = read_json(base + cfg['collection_path'], cfg['scope_parameters'], cfg, secret, transport)
        rows = pointer(payload, cfg['collection_pointer'])
        if not isinstance(rows, list):raise ProviderError('contract_mismatch', 'Configured collection pointer did not identify an array.')
    resources = []
    redactions = [secret] if secret else []
    if cfg['auth_mode'] == 'basic' and ':' in secret:redactions.append(secret.split(':', 1)[1])
    def safe(value, maximum):
        value = str(value)
        for item in redactions:
            if item:value = value.replace(item, '[REDACTED]')
        return value[:maximum]
    for row in rows[:25]:
        if not isinstance(row, dict):raise ProviderError('contract_mismatch', 'Expected JSON resource objects.')
        ident = row.get('id') if provider == 'procore' else pointer(row, cfg['id_pointer'])
        label = row.get('label' if operation == 'field_definitions' else 'name') if provider == 'procore' else pointer(row, cfg['label_pointer'])
        if type(ident) not in {str, int} or not str(ident).strip() or not isinstance(label, str):raise ProviderError('contract_mismatch', 'Resource ID or name has an unsupported type.')
        if provider == 'procore' and operation != 'field_definitions' and (not str(ident).isdigit() or int(ident) <= 0):raise ProviderError('contract_mismatch', 'Expected a positive Procore resource ID.')
        if provider == 'procore' and operation == 'field_definitions' and str(row.get('company_id', '')) != cfg['company_id']:
            raise ProviderError('scope_mismatch', 'Field definition did not belong to the saved company.')
        resource = {'id': safe(ident, 500), 'label': safe(label, 250), 'kind': operation.rstrip('s') if provider == 'procore' else 'resource'}
        if provider == 'procore' and operation == 'field_definitions':
            if not isinstance(row.get('data_type'), str):raise ProviderError('contract_mismatch', 'Field definition data type is missing.')
            resource['field_type'] = safe(row['data_type'], 100)
        resources.append(resource)
    return {'operation': operation, 'synthetic': False, 'resources': resources, 'returned': len(resources), 'coverage': 'At most 25 resources displayed; this is not a complete register.', 'imported': 0, 'files_transferred': 0, 'page': page if provider == 'procore' else None}



class Binding(BaseModel):
    model_config = ConfigDict(extra='forbid')
    property_uri: str = Field(min_length=1, max_length=1000)
    external_field_id: str = Field(min_length=1, max_length=250)
    external_field_name: str = Field(min_length=1, max_length=250)
    external_type: str = Field(default='', max_length=100)
    unit: str = Field(default='', max_length=100)
    evidence: str = Field(min_length=1, max_length=500)


class ExternalConfig(BaseModel):
    model_config = ConfigDict(extra='forbid')
    name: str = Field(min_length=1, max_length=100)
    provider: Literal['procore', 'meridian', 'maintenance_connection', 'generic']
    base_url: str = Field(max_length=500)
    auth_mode: Literal['bearer', 'api_key', 'basic', 'windows_integrated', 'none'] = 'bearer'
    auth_header: str = Field(default='', max_length=64)
    auth_prefix: Literal['', 'Bearer'] = ''
    approved_test_access: bool = False
    vendor_settings_confirmed: bool = False
    evidence_note: str = Field(default='', max_length=1000)
    product_version: str = Field(default='', max_length=100)
    execution: Literal['local_network', 'private_route', 'public_https'] = 'public_https'
    procore_tool: Literal['admin','home','timesheets'] = 'admin'
    company_id: str = Field(default='', max_length=20, pattern=r'^([1-9][0-9]*)?$')
    project_id: str = Field(default='', max_length=20, pattern=r'^([1-9][0-9]*)?$')
    company_name: str = Field(default='', max_length=250)
    project_name: str = Field(default='', max_length=250)
    view_id: str = Field(default='', max_length=250)
    filter_name: str = Field(default='', max_length=250)
    property_names: list[str] = Field(default_factory=list, max_length=25)
    collection_path: str = Field(default='/api/resources', max_length=500, pattern=r'^/[A-Za-z0-9_./-]*$')
    collection_pointer: str = Field(default='', max_length=250)
    id_pointer: str = Field(default='/id', max_length=250)
    label_pointer: str = Field(default='/name', max_length=250)
    scope_parameters: dict[str, str] = Field(default_factory=dict, max_length=10)
    scope_reference: str = Field(default='', max_length=500)
    desired_definitions: bool = False
    desired_values: bool = False
    bindings: list[Binding] = Field(default_factory=list, max_length=100)

    @model_validator(mode='after')
    def valid_contract(self):
        self.name = self.name.strip()
        if not self.name:raise ValueError('Enter a connection name')
        try:self.base_url, _ = approved_url(self.base_url)
        except ProviderError as e:raise ValueError(e.message)
        if self.provider == 'procore' and (self.base_url != PROCORE_BASE or self.auth_mode != 'bearer'):
            raise ValueError('This Procore adapter uses the production api.procore.com endpoint with an OAuth bearer token. Other regions/sandboxes need a reviewed preset.')
        if self.provider == 'meridian' and self.auth_mode != 'windows_integrated':raise ValueError('The Meridian Explorer adapter uses the executor Windows identity. Other Meridian interfaces remain preparation-only.')
        if self.auth_mode == 'windows_integrated' and self.provider != 'meridian':raise ValueError('Windows integrated auth is available only for Meridian Explorer.')
        if self.auth_mode == 'api_key':
            try:auth_headers('redeye', 'synthetic-header-validation', self.auth_header, self.auth_prefix)
            except ProviderError as e:raise ValueError(e.message)
        for path in [self.collection_path]:
            if '//' in path or any(p in {'.', '..'} for p in path.split('/')):raise ValueError('Collection path must remain inside the approved API application.')
        for path in [self.collection_pointer, self.id_pointer, self.label_pointer]:
            if path and not path.startswith('/'):raise ValueError('Use a JSON Pointer starting with /, or empty for the response itself.')
        if any(not re.fullmatch(r'[A-Za-z0-9_.]+', p) for p in self.property_names):raise ValueError('Property names must be property-set/name identifiers.')
        for key, value in self.scope_parameters.items():
            if not re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]{0,63}', key) or any(c in value for c in '\r\n') or len(value) > 500 or key.casefold() in {'authorization','password','secret','token','access_token','api_key','apikey','key'}:
                raise ValueError('Use non-secret scope/filter query parameters only. Credentials belong in encrypted storage and HTTP headers.')
        if len({b.property_uri for b in self.bindings}) != len(self.bindings) or len({b.external_field_id.casefold() for b in self.bindings}) != len(self.bindings):raise ValueError('Use distinct source properties and destination field IDs.')
        return self


class Revision(ExternalConfig):
    expected_generation: int = Field(ge=1)


class Credential(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_generation: int = Field(ge=1)
    secret: str = Field(min_length=8, max_length=8192)


class Read(BaseModel):
    model_config = ConfigDict(extra='forbid')
    operation: Literal['companies', 'projects', 'field_definitions', 'documents', 'resources']
    page: int = Field(default=1, ge=1, le=40)


class Scope(BaseModel):
    model_config = ConfigDict(extra='forbid')
    expected_generation: int = Field(ge=1)
    company_id: str = Field(min_length=1, max_length=20, pattern=r'^[1-9][0-9]*$')
    project_id: str = Field(default='', max_length=20, pattern=r'^([1-9][0-9]*)?$')


def register_additional_connections(app, db, identity, permit, project_check, audit, vault, now):
    def scoped(c, who, project, ident):
        project_check(c, who, project)
        row = c.execute('SELECT * FROM external_connections WHERE tenant_id=? AND project_id=? AND id=?', (who['tenant_id'], project, ident)).fetchone()
        if not row:raise HTTPException(404, 'Additional connection unavailable in this project')
        return dict(row)

    def bindings(c, who, project, body):
        if not body.bindings:return
        row = c.execute('SELECT configuration FROM bsdd_settings WHERE tenant_id=? AND project_id=?', (who['tenant_id'], project)).fetchone()
        selected = {p['uri'] for p in json.loads(row['configuration']).get('properties', [])} if row else set()
        if any(b.property_uri not in selected for b in body.bindings):raise HTTPException(422, 'Choose field bindings from the selected project bSDD properties.')

    def readiness(row):
        cfg = json.loads(row['configuration']);issues = []
        if os.getenv('ORBIT_ENABLE_LIVE_READS') != '1':issues.append('Live metadata reads are not enabled in this server process.')
        _, origin = approved_url(cfg['base_url'])
        allowed = {v.strip().rstrip('/') for v in os.getenv('ORBIT_EXTRA_ALLOWED_ORIGINS', '').split(',') if v.strip()}
        local_approved = getattr(app.state, 'local_workspace', False) and cfg['vendor_settings_confirmed'] and cfg['approved_test_access'] and bool(cfg['evidence_note'].strip())
        if origin not in allowed and not local_approved:
            issues.append('Confirm this profile’s vendor endpoint and authorised access to approve its exact HTTPS origin.' if getattr(app.state, 'local_workspace', False) else 'Operator must allow this exact HTTPS origin (including any non-default port) in ORBIT_EXTRA_ALLOWED_ORIGINS.')
        if not cfg['vendor_settings_confirmed'] or not cfg['approved_test_access'] or not cfg['evidence_note'].strip():issues.append('Confirm vendor settings, authorised test access and a non-secret administrator reference.')
        if cfg['provider'] == 'meridian' and (not cfg['view_id'].strip() or not cfg['filter_name'].strip()):issues.append('Meridian Explorer requires a documented view ID and internal filter name.')
        if cfg['auth_mode'] == 'windows_integrated':
            if not windows_auth_available():issues.append('Use a Windows executor with optional Windows integrated authentication installed; no Windows passwords are accepted.')
        elif cfg['auth_mode'] != 'none':
            if not row['secret_ciphertext']:issues.append('Store the authorised token/API key/Basic credential.')
            else:
                try:read_headers(cfg, vault.decrypt(row['secret_ciphertext'].encode()).decode())
                except Exception:issues.append('Stored credential is invalid or unreadable with this installation vault key; replace it.')
        return {'ready': not issues, 'issues': issues, 'remote_writes_enabled': False, 'write_note': 'Desired operations and manual field bindings do not enable a writer or verify field inventory.'}

    @app.get('/api/projects/{project}/additional-connections')
    def listing(project: str, who=Depends(identity)):
        permit(who, 'connection')
        with db() as c:
            project_check(c, who, project)
            rows = c.execute('SELECT * FROM external_connections WHERE tenant_id=? AND project_id=? ORDER BY name,id', (who['tenant_id'], project)).fetchall()
            return {'server_version': app.version, 'connections': [{**{k: r[k] for k in ['id','name','provider','generation']}, 'configuration': json.loads(r['configuration']), 'credential_present': bool(r['secret_ciphertext']), 'last_result': json.loads(r['last_result']) if r['last_result'] else None, 'readiness': readiness(dict(r))} for r in rows]}

    @app.post('/api/projects/{project}/additional-connections')
    def create(project: str, body: ExternalConfig, who=Depends(identity)):
        permit(who, 'connection')
        with db() as c:
            project_check(c, who, project);bindings(c, who, project, body)
            ident = str(uuid4());c.execute('INSERT INTO external_connections(id,tenant_id,project_id,provider,name,configuration) VALUES(?,?,?,?,?,?)', (ident, who['tenant_id'], project, body.provider, body.name, body.model_dump_json()))
            audit(c, who, 'additional_connection.created', project, ident)
        return {'id': ident, 'generation': 1, 'live_verified': False}

    @app.put('/api/projects/{project}/additional-connections/{ident}')
    def revise(project: str, ident: str, body: Revision, who=Depends(identity)):
        permit(who, 'connection')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');row = scoped(c, who, project, ident);bindings(c, who, project, body)
            if row['provider'] != body.provider or row['generation'] != body.expected_generation:raise HTTPException(409, 'Provider cannot change and the generation must be current. Reload before editing.')
            c.execute('UPDATE external_connections SET name=?,configuration=?,generation=generation+1,secret_ciphertext=NULL,last_result=NULL WHERE id=?', (body.name, body.model_dump_json(exclude={'expected_generation'}), ident))
            c.execute('DELETE FROM external_discovery WHERE connection_id=?', (ident,))
            audit(c, who, 'additional_connection.revised', project, ident)
        return {'generation': body.expected_generation + 1, 'credential_cleared': True}

    @app.put('/api/projects/{project}/additional-connections/{ident}/credential')
    def credential(project: str, ident: str, body: Credential, who=Depends(identity)):
        permit(who, 'connection')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');row = scoped(c, who, project, ident);cfg = json.loads(row['configuration'])
            if row['generation'] != body.expected_generation:raise HTTPException(409, 'Connection changed; reload before storing a credential.')
            if cfg['auth_mode'] in {'windows_integrated','none'}:raise HTTPException(422, 'This mode does not accept stored credentials.')
            try:read_headers(cfg, body.secret)
            except ProviderError as e:raise HTTPException(422, e.message)
            c.execute('UPDATE external_connections SET secret_ciphertext=?,generation=generation+1,last_result=NULL WHERE id=?', (vault.encrypt(body.secret.encode()).decode(), ident))
            c.execute('DELETE FROM external_discovery WHERE connection_id=?', (ident,));audit(c, who, 'additional_connection.credential_replaced', project, ident)
        return {'generation': body.expected_generation + 1}

    @app.delete('/api/projects/{project}/additional-connections/{ident}/credential')
    def clear(project: str, ident: str, who=Depends(identity)):
        permit(who, 'connection')
        with db() as c:
            scoped(c, who, project, ident)
            c.execute('UPDATE external_connections SET secret_ciphertext=NULL,generation=generation+1,last_result=NULL WHERE id=?', (ident,))
            c.execute('DELETE FROM external_discovery WHERE connection_id=?', (ident,));audit(c, who, 'additional_connection.credential_cleared', project, ident)
        return {'cleared': True, 'vendor_revocation': False}

    @app.post('/api/projects/{project}/additional-connections/{ident}/fixture-check')
    def fixture(project: str, ident: str, who=Depends(identity)):
        permit(who, 'connection')
        with db() as c:
            row = scoped(c, who, project, ident);cfg = json.loads(row['configuration']);audit(c, who, 'additional_connection.fixture_checked', project, ident)
        resources = [{'id': 'SYNTHETIC-RESOURCE', 'label': 'Hand-authored connection fixture', 'kind': 'fixture'}]
        if row['provider'] == 'meridian':
            parsed = explorer_documents(EXPLORER_FIXTURE);resources = [{'id': p['document_id'], 'label': p['name'], 'kind': 'fixture'} for p in parsed['resources']]
        return {'synthetic': True, 'resources': resources, 'returned': len(resources), 'coverage': 'Hand-authored example only; no network call, credential verification or readiness status change.'}

    @app.post('/api/projects/{project}/additional-connections/{ident}/read')
    def read(project: str, ident: str, request: Request, body: Read, who=Depends(identity)):
        permit(who, 'connection')
        with db() as c:
            row = scoped(c, who, project, ident);report = readiness(row)
            if not report['ready']:raise HTTPException(409, ' '.join(report['issues']))
            cfg = json.loads(row['configuration']);secret = vault.decrypt(row['secret_ciphertext'].encode()).decode() if row['secret_ciphertext'] else ''
            audit(c, who, 'additional_connection.read_requested', project, ident + ':' + body.operation)
        try:result = read_resources(cfg, secret, body.operation, body.page)
        except ProviderError as e:
            with db() as c:audit(c, who, 'additional_connection.read_failed', project, e.code)
            raise HTTPException(502, {'code': e.code, 'message': e.message})
        current = identity(request)
        if current['user_id'] != who['user_id'] or current['tenant_id'] != who['tenant_id']:raise HTTPException(409, 'Identity changed during read; response discarded.')
        permit(current, 'connection')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');latest = scoped(c, current, project, ident)
            if latest['generation'] != row['generation']:raise HTTPException(409, 'Connection or credential changed during read; response discarded.')
            result['observed'] = now()
            if cfg['provider'] == 'procore' and body.operation in {'companies','projects'}:
                parent = cfg['company_id'] if body.operation == 'projects' else ''
                cached = c.execute('SELECT * FROM external_discovery WHERE connection_id=? AND kind=? AND parent=?', (ident, body.operation, parent)).fetchone()
                items = {r['id']: r for r in json.loads(cached['resources'])} if cached and cached['generation'] == row['generation'] and cached['expires'] > int(time.time()) else {}
                items.update({r['id']: r for r in result['resources']})
                c.execute('INSERT OR REPLACE INTO external_discovery VALUES(?,?,?,?,?,?)', (ident, body.operation, parent, row['generation'], json.dumps(list(items.values())[:1000]), int(time.time())+1800))
            summary = {k: v for k, v in result.items() if k != 'resources'}
            c.execute('UPDATE external_connections SET last_result=? WHERE id=?', (json.dumps(summary), ident));audit(c, current, 'additional_connection.read_completed', project, ident + ':' + body.operation)
        return result

    @app.get('/api/projects/{project}/additional-connections/{ident}/discovery')
    def discovery(project: str, ident: str, who=Depends(identity)):
        permit(who, 'connection')
        with db() as c:
            row = scoped(c, who, project, ident);cfg = json.loads(row['configuration'])
            if row['provider'] != 'procore':raise HTTPException(422, 'Named company/project discovery is for Procore.')
            rows = c.execute('SELECT * FROM external_discovery WHERE connection_id=? AND generation=? AND expires>?', (ident, row['generation'], int(time.time()))).fetchall()
        return {'companies': next((json.loads(r['resources']) for r in rows if r['kind']=='companies'), []), 'projects': next((json.loads(r['resources']) for r in rows if r['kind']=='projects' and r['parent']==cfg['company_id']), [])}

    @app.post('/api/projects/{project}/additional-connections/{ident}/scope')
    def scope(project: str, ident: str, body: Scope, who=Depends(identity)):
        permit(who, 'connection')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');row = scoped(c, who, project, ident);cfg = json.loads(row['configuration'])
            if row['provider'] != 'procore' or row['generation'] != body.expected_generation:raise HTTPException(409, 'Reload the current Procore connection before selecting scope.')
            def choice(kind, parent, selected):
                found = c.execute('SELECT resources FROM external_discovery WHERE connection_id=? AND kind=? AND parent=? AND generation=? AND expires>?', (ident, kind, parent, row['generation'], int(time.time()))).fetchone()
                items = json.loads(found['resources']) if found else []
                match = next((r for r in items if r['id']==selected), None)
                if not match:raise HTTPException(409, 'Load fresh accessible resources for this exact connection and parent before choosing scope.')
                return match['label']
            if body.company_id == cfg['company_id']:company_name = cfg['company_name']
            else:company_name = choice('companies', '', body.company_id)
            project_name = choice('projects', body.company_id, body.project_id) if body.project_id else ''
            cfg.update(company_id=body.company_id, company_name=company_name, project_id=body.project_id, project_name=project_name, bindings=[])
            c.execute('UPDATE external_connections SET configuration=?,generation=generation+1,last_result=NULL WHERE id=?', (json.dumps(cfg), ident));c.execute('DELETE FROM external_discovery WHERE connection_id=?', (ident,))
            audit(c, who, 'additional_connection.scope_selected', project, ident)
        return {'generation': body.expected_generation+1, 'credential_preserved': True, 'bindings_cleared': True}
