"""bSDD parameter import planning and transactional local test execution.

No remote transport: a real connector must establish definition, revision and
write/verification semantics before it can execute this interface.
"""
import json
import math
import secrets
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from uuid import uuid4

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.integrations import canonical, digest

CAPABILITIES = {
    'procore': {'reason': 'Company-level custom-field definition APIs are documented. Tool/field-set applicability, document or asset value targeting, write permissions, concurrency and read-back still require a verified writer.', 'source': 'https://developers.procore.com/reference/rest/custom-fields?version=2.0'},
    'maintenance_connection': {'reason': 'The configured REST reader does not establish field creation or value-update semantics. Obtain the installed edition/API write contract and sandbox evidence.', 'source': 'https://help.maintenanceconnection.com/'},
    'forma': {'reason': 'ACC custom-attribute creation, folder scope, supported types and version-specific value updates need a verified write adapter and write-scoped OAuth consent.', 'source': 'https://aps.autodesk.com/en/docs/acc/v1/overview/introduction/'},
    'redeye': {'reason': 'Documented POST /api/v1/artefacts/{Id} updates metadata on the current revision; GET describes latest approved revision. No metadata-key creation operation is documented in the reviewed API. The separate RedEye metadata page supports selected-field verification and confirmed existing-key value updates. General key creation, batch imports and revision-safe writes remain unavailable.', 'source': 'https://api.redeyedms.com/#updateartefact'},
    'meridian': {'reason': 'PowerWeb is a client, not a generic write API. Explorer documentation establishes reads; the installed .NET/Connection API, vault privileges and execution bridge need confirmation for writes.', 'source': 'https://help.accruent.com/meridianenterprise/Content/Online_Help/Common/API_LandingPage.htm'},
}


class FieldImport(BaseModel):
    model_config = ConfigDict(extra='forbid')
    property_uri: str = Field(min_length=1, max_length=1000)
    target_name: str = Field(min_length=1, max_length=100, pattern=r'^[A-Za-z][A-Za-z0-9_.]*$')
    required: bool = False
    unit: str = Field(default='', max_length=100)


class ValueRow(BaseModel):
    model_config = ConfigDict(extra='forbid')
    document_id: str = Field(min_length=1, max_length=250)
    values: dict[str, Any] = Field(max_length=100)

    @model_validator(mode='after')
    def bounded_values(self):
        try:
            json.dumps(self.values, allow_nan=False)
        except ValueError:
            raise ValueError('Values must use finite JSON numbers')
        if len(canonical(self.values)) > 25000:
            raise ValueError('Each value row is limited to 25 KB')
        return self


class ImportRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    target_kind: Literal['synthetic', 'live', 'preparation', 'additional']
    target_id: str = Field(min_length=1, max_length=250)
    fields: list[FieldImport] = Field(min_length=1, max_length=100)
    value_rows: list[ValueRow] = Field(default_factory=list, max_length=100)
    overwrite_existing: bool = False

    @model_validator(mode='after')
    def unique_rows(self):
        if len({f.target_name.casefold() for f in self.fields}) != len(self.fields) or len({f.property_uri for f in self.fields}) != len(self.fields):
            raise ValueError('Use unique destination field names and property references')
        if len({r.document_id for r in self.value_rows}) != len(self.value_rows):
            raise ValueError('Select each document once')
        if len(canonical(self.model_dump())) > 250000:
            raise ValueError('Parameter import is limited to 250 KB')
        return self


class ExactPreview(BaseModel):
    model_config = ConfigDict(extra='forbid')
    digest: str = Field(min_length=64, max_length=64)


def allowed_units(prop):
    units = [prop['unit']] if prop.get('unit') else []
    units += prop.get('units', [])
    return list(dict.fromkeys(u for u in units if isinstance(u, str) and u))


def definition(prop, field):
    errors = []
    datatype = prop.get('dataType')
    if datatype not in {'String', 'Boolean', 'Integer', 'Real'}:
        errors.append('Unsupported or unspecified bSDD data type; review the property before importing')
    kind = prop.get('propertyValueKind') or 'Single'
    if kind not in {'Single', 'List'}:
        errors.append('Unsupported property value kind; only Single and List are implemented')
    units = allowed_units(prop)
    unit = field['unit'] or (units[0] if len(units) == 1 else '')
    if field['unit'] and field['unit'] not in units:
        errors.append('Chosen unit is not an exact unit supplied by this property; automatic conversion is unavailable')
    if len(units) > 1 and not unit:
        errors.append('Choose one of the supplied units explicitly')
    if field['target_name'].casefold() in {'number', 'title', 'revision', 'status', 'id'}:
        errors.append('Core document fields are reserved; choose a custom parameter name')
    return {'property_uri': prop['uri'], 'property_definition': prop, 'data_type': datatype, 'value_kind': kind, 'required': field['required'], 'unit': unit}, errors


def validate_value(value, spec):
    if value is None:
        return 'Null is not a value update; omit the property to leave it unchanged'
    values = value if spec['value_kind'] == 'List' else [value]
    if spec['value_kind'] == 'List' and (not isinstance(value, list) or not value or len(value) > 100):
        return 'Expected a nonempty list of at most 100 typed values'
    datatype = spec['data_type']
    for item in values:
        valid = (datatype == 'String' and isinstance(item, str) and len(item) <= 4000 or
                 datatype == 'Boolean' and type(item) is bool or
                 datatype == 'Integer' and type(item) is int and -(2**53) < item < 2**53 or
                 datatype == 'Real' and type(item) in {int, float} and abs(item) < 1e100 and math.isfinite(item))
        if not valid:
            return f'Expected {datatype}; values are not silently coerced'
        if spec['required'] and isinstance(item, str) and not item.strip():
            return 'Required values must not be blank'
        choices = spec['property_definition'].get('allowedValues', [])
        if choices:
            allowed = []
            for choice in choices:
                candidate = choice.get('value') if isinstance(choice, dict) else choice
                if candidate is None:
                    return 'Unsupported allowed-value contract; manual review required'
                if datatype in {'Integer', 'Real'}:
                    try:
                        allowed.append(Decimal(str(candidate)))
                    except InvalidOperation:
                        return 'Unsupported numeric allowed-value contract'
                elif datatype == 'Boolean':
                    if candidate is True or type(candidate) is str and candidate.lower() == 'true':allowed.append(True)
                    elif candidate is False or type(candidate) is str and candidate.lower() == 'false':allowed.append(False)
                    else:return 'Unsupported Boolean allowed-value contract'
                else:
                    allowed.append(candidate)
            probe = Decimal(str(item)) if datatype in {'Integer', 'Real'} else item
            if not any(type(probe) is type(a) and probe == a for a in allowed):
                return 'Value is not one of the supplied bSDD allowed values'
    return ''


def register_parameter_imports(app, db, identity, permit, project_check, audit, now):
    def target(c, who, project, kind, ident):
        table = {'synthetic': 'connections', 'live': 'read_connections', 'preparation': 'connection_plans', 'additional': 'external_connections'}[kind]
        row = c.execute(f'SELECT * FROM {table} WHERE tenant_id=? AND project_id=? AND id=?', (who['tenant_id'], project, ident)).fetchone()
        if not row:
            raise HTTPException(404, 'Destination connection unavailable in this project')
        row = dict(row)
        if kind == 'synthetic' and (row['status'] != 'synthetic' or row['provider'] not in {'forma', 'redeye'}):
            raise HTTPException(422, 'This destination cannot execute a local test import')
        return row

    def schema(c, who, project):
        row = c.execute('SELECT version,configuration FROM bsdd_settings WHERE tenant_id=? AND project_id=?', (who['tenant_id'], project)).fetchone()
        if not row:
            raise HTTPException(409, 'Select and enable bSDD properties for this project first')
        cfg = json.loads(row['configuration'])
        if not cfg.get('enabled') or not cfg.get('properties'):
            raise HTTPException(409, 'Enable a bSDD reference with selected property definitions first')
        return {'version': row['version'], 'configuration': cfg}

    def snapshot(c, who, project, config):
        source = schema(c, who, project)
        dest = target(c, who, project, config['target_kind'], config['target_id'])
        safe_target = {k: dest[k] for k in ['id', 'provider', 'name']}
        safe_target['kind'] = config['target_kind']
        safe_target['generation'] = dest.get('generation', dest.get('version', 0))
        if config['target_kind'] == 'additional':
            cfg = json.loads(dest['configuration'])
            safe_target['scope_reference'] = cfg['scope_reference']
            safe_target['company_id'] = cfg['company_id']
            safe_target['project_id'] = cfg['project_id']
            safe_target['configuration_digest'] = digest(cfg)
            safe_target['manual_field_bindings'] = cfg['bindings']
            safe_target['field_bindings_verified'] = False
        result = {'schema': source, 'target': safe_target, 'fields': [], 'documents': [], 'values': []}
        if config['target_kind'] == 'synthetic':
            params = (who['tenant_id'], project, dest['id'])
            result['fields'] = [dict(r) for r in c.execute('SELECT id,field_key,property_uri,definition FROM parameter_definitions WHERE tenant_id=? AND project_id=? AND connection_id=? ORDER BY id', params)]
            for item in config['value_rows']:
                doc = c.execute('SELECT id,number,title,revision,status FROM documents WHERE tenant_id=? AND project_id=? AND connection_id=? AND id=?', (*params, item['document_id'])).fetchone()
                if not doc:
                    raise HTTPException(404, 'Selected document is not in this exact destination connection')
                result['documents'].append(dict(doc))
                result['values'] += [dict(r) for r in c.execute('SELECT document_id,field_id,value FROM parameter_values WHERE tenant_id=? AND project_id=? AND connection_id=? AND document_id=? ORDER BY field_id', (*params, item['document_id']))]
        return result

    def build(config, state):
        blockers, fields, values = [], [], []
        if config['target_kind'] != 'synthetic':
            blockers.append('No live destination field/document inventory has been verified; proposed names and values are review-only.')
            blockers.append(CAPABILITIES.get(state['target']['provider'], {'reason': 'No verified parameter-write adapter exists for this platform.'})['reason'])
        source = {p['uri']: p for p in state['schema']['configuration']['properties']}
        existing = {f['field_key'].casefold(): f for f in state['fields']}
        planned = {}
        for field in config['fields']:
            if field['property_uri'] not in source:
                raise HTTPException(422, 'Property was not selected in the current project bSDD snapshot')
            spec, errors = definition(source[field['property_uri']], field)
            old = existing.get(field['target_name'].casefold())
            if old and (old['property_uri'] != field['property_uri'] or json.loads(old['definition']) != spec):
                errors.append('Existing field definition differs; renaming, type/unit changes and rebinding need a separate migration')
            # Also stop accidental aliases for the same property in one connection.
            if any(f['property_uri'] == field['property_uri'] and f['field_key'].casefold() != field['target_name'].casefold() for f in state['fields']):
                errors.append('This property already has another field binding in the destination')
            item = {'target_name': field['target_name'], 'property_uri': field['property_uri'], 'definition': spec, 'action': 'reuse' if old else 'create', 'existing_id': old['id'] if old else None, 'errors': errors}
            fields.append(item);planned[field['property_uri']] = item
        old_values = {(v['document_id'], v['field_id']): json.loads(v['value']) for v in state['values']}
        for row in config['value_rows']:
            if set(row['values']) - set(planned):
                raise HTTPException(422, 'Values must refer to properties included in this import')
            for uri, field in planned.items():
                key = (row['document_id'], field['existing_id'])
                exists = key in old_values
                if uri not in row['values']:
                    if field['definition']['required'] and (not exists or validate_value(old_values[key], field['definition'])):
                        blockers.append('A required selected parameter has no valid value for document ' + row['document_id'])
                    continue
                new = row['values'][uri]
                error = validate_value(new, field['definition'])
                old = old_values.get(key)
                action = 'set'
                if exists and canonical(old) == canonical(new):action = 'unchanged'
                elif exists and not config['overwrite_existing']:action = 'skip_existing'
                if action == 'skip_existing':
                    # Retained invalid content cannot be labelled verified quality.
                    retained = validate_value(old, field['definition'])
                    if retained:blockers.append('Retained existing value is invalid: ' + retained)
                values.append({'document_id': row['document_id'], 'property_uri': uri, 'target_name': field['target_name'], 'before': old, 'before_present': exists, 'after': new, 'action': action, 'error': error})
        blockers += [f['target_name'] + ': ' + error for f in fields for error in f['errors']]
        blockers += [v['target_name'] + ': ' + v['error'] for v in values if v['error']]
        native_proposals = []
        if state['target']['provider'] == 'procore' and config['target_kind'] == 'additional' and state['target'].get('company_id'):
            for field in fields:
                spec = field['definition'];prop = spec['property_definition']
                native_type = {'String':'string', 'Boolean':'boolean', 'Real':'decimal'}.get(spec['data_type'])
                reason = ''
                if not native_type or spec['value_kind'] != 'Single' or prop.get('allowedValues') or spec['unit']:
                    reason = 'No automatic equivalent for integer-only, list, enumerated or unit-qualified fields; explicit provider mapping is required.'
                native_proposals.append({'property_uri': field['property_uri'], 'executable': False, 'existing_field_check_required': True, 'method': 'POST' if not reason else None,
                    'path': '/rest/v2.0/companies/' + state['target']['company_id'] + '/custom_field_definitions' if not reason else None,
                    'body': {'custom_field_definition': {'label': field['target_name'], 'data_type': native_type, 'description': 'bSDD reference: ' + prop['propertyUri'], 'active': True}} if not reason else None,
                    'review_note': reason or 'Documented company-level definition proposal only. Verify duplicates, field-set applicability/required rules and permissions; the company definition does not impose project required-value rules or update document/asset values.'})
        return {'native_definition_proposals': native_proposals, 'synthetic': config['target_kind'] == 'synthetic' , 'target': state['target'], 'schema_version': state['schema']['version'], 'dictionary': state['schema']['configuration']['dictionary'], 'class': state['schema']['configuration']['class'], 'fields': fields, 'values': values, 'blockers': blockers, 'overwrite_existing': config['overwrite_existing'], 'coverage': 'Exact selected parameters and documents only; no complete-project quality claim', 'remote_writes_available': False}

    def job(c, who, project, ident):
        project_check(c, who, project)
        row = c.execute('SELECT * FROM parameter_imports WHERE id=? AND tenant_id=? AND project_id=?', (ident, who['tenant_id'], project)).fetchone()
        if not row:raise HTTPException(404, 'Parameter import unavailable')
        return dict(row)

    def public(row):
        return {k: json.loads(v) if k in {'configuration', 'preview', 'receipt'} and v is not None else v for k, v in row.items() if k not in {'tenant_id', 'snapshot_digest'}}

    def exact(row, body):
        if not secrets.compare_digest(row['digest'], body.digest):raise HTTPException(409, 'Review the exact parameter import digest')

    def fresh(c, who, project, row):
        if row['expires'] <= int(time.time()):raise HTTPException(409, 'Parameter import expired; create a new preview')
        state = snapshot(c, who, project, json.loads(row['configuration']))
        if digest(state) != row['snapshot_digest']:raise HTTPException(409, 'Dictionary, destination or selected documents changed; create a new preview')
        if json.loads(row['preview'])['blockers']:raise HTTPException(409, 'Resolve preview blockers before approval or execution')
        return state

    @app.get('/api/projects/{project}/parameter-imports')
    def listing(project: str, who=Depends(identity)):
        permit(who, 'view')
        with db() as c:
            project_check(c, who, project)
            targets = []
            for kind, table in [('synthetic', 'connections'), ('live', 'read_connections'), ('preparation', 'connection_plans'), ('additional', 'external_connections')]:
                for row in c.execute(f'SELECT id,name,provider FROM {table} WHERE tenant_id=? AND project_id=?', (who['tenant_id'], project)):
                    targets.append({**dict(row), 'kind': kind, 'can_execute': kind == 'synthetic'})
            jobs = [public(dict(r)) for r in c.execute('SELECT * FROM parameter_imports WHERE tenant_id=? AND project_id=? ORDER BY created DESC,id', (who['tenant_id'], project))]
            return {'targets': targets, 'imports': jobs, 'capabilities': CAPABILITIES}

    @app.get('/api/projects/{project}/parameter-register/{connection}')
    def register(project: str, connection: str, who=Depends(identity)):
        permit(who, 'view')
        with db() as c:
            project_check(c, who, project);target(c, who, project, 'synthetic', connection)
            params = (who['tenant_id'], project, connection)
            fields = [{**dict(r), 'definition': json.loads(r['definition'])} for r in c.execute('SELECT id,field_key,property_uri,definition FROM parameter_definitions WHERE tenant_id=? AND project_id=? AND connection_id=? ORDER BY field_key', params)]
            values = [{**dict(r), 'value': json.loads(r['value'])} for r in c.execute('SELECT document_id,field_id,value FROM parameter_values WHERE tenant_id=? AND project_id=? AND connection_id=? ORDER BY document_id,field_id', params)]
            return {'synthetic': True, 'fields': fields, 'values': values}

    @app.post('/api/projects/{project}/parameter-imports')
    def preview(project: str, body: ImportRequest, who=Depends(identity)):
        permit(who, 'draft')
        config = body.model_dump()
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            project_check(c, who, project)
            state = snapshot(c, who, project, config);plan = build(config, state)
            ident = str(uuid4());expires = int(time.time()) + 86400
            fingerprint = digest({'id': ident, 'tenant': who['tenant_id'], 'project': project, 'configuration': config, 'preview': plan, 'snapshot': digest(state), 'expires': expires})
            c.execute('INSERT INTO parameter_imports VALUES(?,?,?,?,?,?,?,?,NULL,?,?,?,NULL)', (ident, who['tenant_id'], project, canonical(config), canonical(plan), fingerprint, digest(state), who['user_id'], 'preview', now(), expires))
            audit(c, who, 'parameters.preview_created', project, ident)
            return public(job(c, who, project, ident))

    @app.post('/api/projects/{project}/parameter-imports/{ident}/approve')
    def approve(project: str, ident: str, body: ExactPreview, who=Depends(identity)):
        permit(who, 'approve')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');row = job(c, who, project, ident);exact(row, body)
            if row['status'] != 'preview' or row['requested_by'] == who['user_id']:raise HTTPException(409, 'Approval requires another actor and an unapproved preview')
            fresh(c, who, project, row)
            c.execute("UPDATE parameter_imports SET status='approved',approved_by=? WHERE id=?", (who['user_id'], ident))
            audit(c, who, 'parameters.approved', project, ident)
        return {'status': 'approved', 'executed': False}

    @app.post('/api/projects/{project}/parameter-imports/{ident}/execute')
    def execute(project: str, ident: str, body: ExactPreview, who=Depends(identity)):
        permit(who, 'connection')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');row = job(c, who, project, ident);exact(row, body)
            if row['status'] == 'completed':return json.loads(row['receipt'])
            if row['status'] != 'approved':raise HTTPException(409, 'An approved parameter preview is required')
            approver = c.execute('SELECT role FROM memberships WHERE tenant_id=? AND user_id=?', (who['tenant_id'], row['approved_by'])).fetchone()
            if not approver:raise HTTPException(409, 'Approver membership is no longer valid')
            permit({'role': approver['role']}, 'approve')
            if not c.execute('SELECT 1 FROM project_access WHERE tenant_id=? AND project_id=? AND user_id=?', (who['tenant_id'], project, row['approved_by'])).fetchone():raise HTTPException(409, 'Approver project access was removed')
            state = fresh(c, who, project, row)
            if state['target']['kind'] != 'synthetic':raise HTTPException(409, 'No verified live parameter-write adapter is available')
            plan = json.loads(row['preview']);target_id = state['target']['id'];params = (who['tenant_id'], project, target_id)
            field_ids = {};created = written = 0
            for field in plan['fields']:
                field_id = field['existing_id'] or str(uuid4());field_ids[field['property_uri']] = field_id
                if field['action'] == 'create':
                    c.execute('INSERT INTO parameter_definitions VALUES(?,?,?,?,?,?,?)', (field_id, *params, field['target_name'], field['property_uri'], canonical(field['definition'])))
                    created += 1
            for value in plan['values']:
                if value['action'] == 'set':
                    c.execute('INSERT INTO parameter_values VALUES(?,?,?,?,?,?) ON CONFLICT(tenant_id,project_id,connection_id,document_id,field_id) DO UPDATE SET value=excluded.value', (*params, value['document_id'], field_ids[value['property_uri']], canonical(value['after'])))
                    written += 1
            # Read back from the destination store, including unchanged/skipped values.
            for field in plan['fields']:
                actual = c.execute('SELECT definition FROM parameter_definitions WHERE id=?', (field_ids[field['property_uri']],)).fetchone()
                if not actual or json.loads(actual['definition']) != field['definition']:raise HTTPException(409, 'Definition read-back failed; local transaction rolled back')
            for value in plan['values']:
                expected = value['before'] if value['action'] == 'skip_existing' else value['after']
                actual = c.execute('SELECT value FROM parameter_values WHERE tenant_id=? AND project_id=? AND connection_id=? AND document_id=? AND field_id=?', (*params, value['document_id'], field_ids[value['property_uri']])).fetchone()
                if not actual or canonical(json.loads(actual['value'])) != canonical(expected):raise HTTPException(409, 'Value read-back failed; local transaction rolled back')
            receipt = {'import_id': ident, 'digest': row['digest'], 'synthetic': True, 'status': 'completed', 'definitions_created': created, 'values_written': written, 'values_skipped': sum(v['action'] == 'skip_existing' for v in plan['values']), 'read_back_verified': True, 'verified_at': now(), 'remote_writes': 0, 'scope': 'Selected local test definitions and requested values only', 'quality_note': 'Definition-only imports do not establish that required values exist on all documents'}
            c.execute("UPDATE parameter_imports SET status='completed',receipt=? WHERE id=?", (canonical(receipt), ident))
            audit(c, who, 'parameters.local_import_completed', project, ident)
        return receipt

    @app.post('/api/projects/{project}/parameter-imports/{ident}/cancel')
    def cancel(project: str, ident: str, body: ExactPreview, who=Depends(identity)):
        permit(who, 'draft')
        with db() as c:
            c.execute('BEGIN IMMEDIATE');row = job(c, who, project, ident);exact(row, body)
            if row['requested_by'] != who['user_id']:permit(who, 'connection')
            if row['status'] not in {'preview', 'approved'}:raise HTTPException(409, 'Only pending imports can be cancelled')
            c.execute("UPDATE parameter_imports SET status='cancelled' WHERE id=?", (ident,))
            audit(c, who, 'parameters.cancelled', project, ident)
        return {'status': 'cancelled'}

    @app.get('/api/projects/{project}/parameter-register/{connection}/quality')
    def quality(project: str, connection: str, who=Depends(identity)):
        permit(who, 'view')
        with db() as c:
            project_check(c, who, project);target(c, who, project, 'synthetic', connection)
            params = (who['tenant_id'], project, connection)
            fields = list(c.execute('SELECT id,field_key,definition FROM parameter_definitions WHERE tenant_id=? AND project_id=? AND connection_id=?', params))
            docs = list(c.execute('SELECT id,number FROM documents WHERE tenant_id=? AND project_id=? AND connection_id=?', params))
            if len(docs) > 100 or len(fields) > 200:raise HTTPException(422, 'Local quality checks are limited to 100 documents and 200 parameters per connection')
            values = {(r['document_id'], r['field_id']): json.loads(r['value']) for r in c.execute('SELECT document_id,field_id,value FROM parameter_values WHERE tenant_id=? AND project_id=? AND connection_id=?', params)}
            findings = []
            for doc in docs:
                for field in fields:
                    spec = json.loads(field['definition']);key = (doc['id'], field['id'])
                    problem = validate_value(values[key], spec) if key in values else ('Required parameter has no value' if spec['required'] else '')
                    if problem:findings.append({'document_id': doc['id'], 'document_number': doc['number'], 'field': field['field_key'], 'issue': problem})
        return {'synthetic': True, 'documents_checked': len(docs), 'parameters_checked': len(fields), 'issue_count': len(findings), 'findings': findings[:1000], 'truncated': len(findings) > 1000, 'coverage': 'Local imported parameters only; not an ISO/IDS or vendor-wide compliance result'}

    @app.get('/api/projects/{project}/parameter-imports/{ident}/package')
    def package(project: str, ident: str, who=Depends(identity)):
        permit(who, 'view')
        with db() as c:
            row = job(c, who, project, ident)
        return {'format': 'ORBIT_PARAMETER_IMPORT_REVIEW_V1', 'vendor_native_format': False, 'import': public(row), 'notice': 'Review package only. It is not a native platform import file or an authorisation to execute remote writes.'}
