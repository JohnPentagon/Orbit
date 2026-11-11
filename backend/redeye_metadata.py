"""User-selected RedEye metadata verification and updates for trusted local UAT."""
import hashlib
import json
import logging
import os
import secrets
import time
from typing import Any
from uuid import uuid4

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend import redeye_pilot as vendor
from backend.integrations import canonical, digest
from backend.parameter_imports import definition, validate_value
from backend.providers import ProviderError, approved_base, auth_headers, read_page, resource_collection


class ConnectionSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    connection_id: str = Field(min_length=1, max_length=100)


class Selection(ConnectionSelection):
    artefact_id: int = Field(gt=0, le=vendor.MAX_ID, strict=True)


class FieldSelection(BaseModel):
    model_config = ConfigDict(extra='forbid')
    inspection_id: str = Field(min_length=1, max_length=100)
    metadata_key_id: int = Field(gt=0, le=vendor.MAX_ID, strict=True)
    values: list[Any] | None = Field(default=None, min_length=1, max_length=100)
    property_uri: str = Field(default='', max_length=1000)
    unit: str = Field(default='', max_length=100)
    overwrite_existing: bool = False

    @model_validator(mode='after')
    def scalar_values(self):
        if self.values is not None:
            if any(type(v) not in {str, int, float, bool} for v in self.values):
                raise ValueError('Use text, numeric or Boolean values; null and nested objects are unsupported.')
            if len(json.dumps(self.values, allow_nan=False)) > 10000:
                raise ValueError('Values are limited to 10 KB.')
        return self


class Confirm(BaseModel):
    model_config = ConfigDict(extra='forbid')
    digest: str = Field(min_length=64, max_length=64)
    confirmed: bool = False
    current_revision_confirmed: bool = False


def read_target(base, secret, cfg, artefact_id):
    """Preserve all returned string values, including repeated metadata-key entries."""
    keys_raw = vendor.request_vendor(base, secret, cfg, 'GET', '/api/v1/metadata-keys')
    rows, _ = resource_collection('redeye', 'metadata_keys', keys_raw)
    keys = {}
    names = set()
    if len(rows) > 2000:
        raise ProviderError('contract_mismatch', 'Metadata key inventory exceeds 2,000 entries.')
    for row in rows:
        if not isinstance(row, dict) or not vendor.positive(row.get('id')) or not isinstance(row.get('name'), str) or not row['name'].strip() or len(row['name']) > 250:
            raise ProviderError('contract_mismatch', 'Metadata keys require exact IDs and names.')
        if row['id'] in keys or row['name'].casefold() in names:
            raise ProviderError('contract_mismatch', 'Duplicate metadata key IDs or names are ambiguous.')
        keys[row['id']] = {'id': row['id'], 'name': row['name']}
        names.add(row['name'].casefold())
    doc = vendor.request_vendor(base, secret, cfg, 'GET', f'/api/v1/artefacts/{artefact_id}')
    if not isinstance(doc, dict) or not vendor.positive(doc.get('id')) or doc['id'] != artefact_id or not isinstance(doc.get('metadata'), list) or len(doc['metadata']) > 1000:
        raise ProviderError('contract_mismatch', 'Expected the selected artefact and its bounded metadata array.')
    if any(not isinstance(doc.get(k), str) for k in ('number', 'title', 'modified')) or not isinstance(doc.get('state'), dict) or not isinstance(doc.get('revisions'), list):
        raise ProviderError('contract_mismatch', 'Artefact identity, modification time, state or revisions are missing.')
    values = {}
    for row in doc['metadata']:
        if not isinstance(row, dict) or not vendor.positive(row.get('key_id')) or row['key_id'] not in keys or row.get('key_name') != keys[row['key_id']]['name'] or not isinstance(row.get('value'), str):
            raise ProviderError('contract_mismatch', 'Metadata must contain known key IDs/names and string values; nothing is silently discarded.')
        values.setdefault(str(row['key_id']), []).append(row['value'])
    return {'artefact_id': artefact_id, 'number': doc['number'], 'title': doc['title'], 'modified': doc['modified'],
            'keys': sorted(keys.values(), key=lambda k: k['id']), 'values': values,
            'modifiable': doc['state'].get('is_modifiable') is True,
            'guard': {k: doc[k] for k in ('id', 'number', 'title', 'state', 'revisions', 'groups', 'workflow', 'geometry', 'type', 'created') if k in doc}}


def register_redeye_metadata(app, db, identity, permit, project_check, audit, vault, now):
    def conflict(code, message, next_action, blockers=None):
        # Fixed reasons only: never log API keys, metadata values or provider bodies.
        logging.getLogger('uvicorn.error').warning('ORBIT RedEye save blocked [%s]: %s', code, next_action)
        raise HTTPException(409, {'code': code, 'message': message, 'next_action': next_action,
                                  'write_sent_by_this_request': False, 'blocking_updates': blockers or []})

    def session(request):
        return hashlib.sha256(request.cookies.get('orbit_session', '').encode()).hexdigest()

    def connection(c, who, project, ident):
        project_check(c, who, project)
        row = c.execute("SELECT * FROM read_connections WHERE tenant_id=? AND project_id=? AND id=? AND provider='redeye'", (who['tenant_id'], project, ident)).fetchone()
        if not row:
            raise HTTPException(404, 'RedEye connection unavailable in this project.')
        return dict(row)

    def access(row):
        if os.getenv('ORBIT_ENABLE_LIVE_READS') != '1':
            raise HTTPException(409, 'Open the local portal using Run-ORBIT.cmd for connection reads.')
        cfg = json.loads(row['configuration'])
        if not cfg['vendor_settings_confirmed'] or not cfg['approved_test_access'] or not cfg['evidence_note'].strip():
            raise HTTPException(409, 'Confirm vendor settings and test access in Read connections.')
        try:
            base = approved_base('redeye', cfg['base_url'], [h.strip() for h in os.getenv('ORBIT_REDEYE_ALLOWED_HOSTS', '').lower().split(',')])
            secret = vault.decrypt(row['secret_ciphertext'].encode()).decode() if row['secret_ciphertext'] else ''
            auth_headers('redeye', secret, cfg['auth_header'], cfg['auth_prefix'])
        except ProviderError as e:
            raise HTTPException(409, e.message)
        except Exception:
            raise HTTPException(409, 'Store a readable encrypted API key in Read connections.')
        return base, secret, cfg

    def read(row, artefact):
        base, secret, cfg = access(row)
        try:
            return read_target(base, secret, cfg, artefact)
        except ProviderError as e:
            raise HTTPException(502, {'code': e.code, 'message': e.message})

    def refresh(request, who, project, row):
        current = identity(request)
        permit(current, 'connection')
        if current != who:
            raise HTTPException(409, 'Identity changed; inspect again.')
        with db() as c:
            latest = connection(c, current, project, row['id'])
            if latest['generation'] != row['generation']:
                raise HTTPException(409, 'Connection changed; inspect again.')

    def inspection(c, who, project, body):
        project_check(c, who, project)
        row = c.execute('SELECT * FROM redeye_metadata_inspections WHERE id=? AND tenant_id=? AND project_id=?', (body.inspection_id, who['tenant_id'], project)).fetchone()
        if not row or row['expires'] <= int(time.time()):
            raise HTTPException(409, 'Inspect the selected artefact again; inspections last 30 minutes.')
        conn = connection(c, who, project, row['connection_id'])
        if conn['generation'] != row['generation']:
            raise HTTPException(409, 'Connection changed; inspect again.')
        before = json.loads(row['snapshot'])
        key = next((k for k in before['keys'] if k['id'] == body.metadata_key_id), None)
        if not key:
            raise HTTPException(422, 'Select an existing metadata field from this inspection.')
        return conn, before, key

    def source(c, who, project, body):
        if not body.property_uri:
            return None, []
        row = c.execute('SELECT version,configuration FROM bsdd_settings WHERE tenant_id=? AND project_id=?', (who['tenant_id'], project)).fetchone()
        cfg = json.loads(row['configuration']) if row else {}
        prop = next((p for p in cfg.get('properties', []) if p['uri'] == body.property_uri), None)
        if not cfg.get('enabled') or not prop:
            raise HTTPException(422, 'Select a saved, enabled project bSDD property, or choose no bSDD validation.')
        spec, errors = definition(prop, {'target_name': 'MetadataValue', 'unit': body.unit, 'required': False})
        if body.values is not None:
            value = body.values if spec['value_kind'] == 'List' else body.values[0]
            if spec['value_kind'] == 'Single' and len(body.values) != 1:
                errors.append('This bSDD property requires one value.')
            problem = validate_value(value, spec)
            if problem:
                errors.append(problem)
        return {'version': row['version'], 'configuration_digest': digest(cfg), 'property': prop, 'unit': spec['unit']}, errors

    def encoded(values):
        return [v if isinstance(v, str) else canonical(v) for v in values]

    def public(row):
        return {k: json.loads(v) if k in {'plan', 'receipt'} and v is not None else v for k, v in dict(row).items() if k not in {'session_hash', 'tenant_id'}}

    def job(c, who, project, ident):
        project_check(c, who, project)
        row = c.execute('SELECT * FROM redeye_metadata_updates WHERE id=? AND tenant_id=? AND project_id=?', (ident, who['tenant_id'], project)).fetchone()
        if not row:
            raise HTTPException(404, 'Metadata update unavailable.')
        return dict(row)

    def exact(row, body):
        if not secrets.compare_digest(row['digest'], body.digest):
            conflict('preview_digest_mismatch', 'The save request does not match this preview.', 'Discard the preview, load metadata again and prepare the intended change.')

    def save(c, who, project, row, status, reason, http_ok=False, verified=False):
        old = json.loads(row['receipt']) if row['receipt'] else {}
        receipt = {'status': status, 'reason': reason, 'read_back_verified': verified, 'http_200_observed': http_ok, 'observed': now(), 'automatic_retry': False,
                   'initial_outcome': old.get('initial_outcome', {'status': status, 'reason': reason, 'http_200_observed': http_ok})}
        c.execute('UPDATE redeye_metadata_updates SET status=?,receipt=? WHERE id=?', (status, canonical(receipt), row['id']))
        audit(c, who, 'redeye_metadata.' + status, project, row['id'])
        return receipt

    def verified(plan, after):
        expected = {**plan['before']['values'], str(plan['key']['id']): plan['values']}
        return after['values'] == expected and after['guard'] == plan['before']['guard'] and after['keys'] == plan['before']['keys']

    @app.get('/api/projects/{project}/redeye-metadata')
    def context(project: str, who=Depends(identity)):
        permit(who, 'view')
        with db() as c:
            project_check(c, who, project)
            connections = []
            if who['role'] == 'owner':
                for r in c.execute("SELECT id,name,configuration FROM read_connections WHERE tenant_id=? AND project_id=? AND provider='redeye'", (who['tenant_id'], project)):
                    try:
                        base = approved_base('redeye', json.loads(r['configuration'])['base_url'], [h.strip() for h in os.getenv('ORBIT_REDEYE_ALLOWED_HOSTS', '').lower().split(',')])
                    except ProviderError:
                        base = 'Unverified host; edit Read connections'
                    connections.append({'id': r['id'], 'name': r['name'], 'base_url': base})
            jobs = [public(r) for r in c.execute('SELECT * FROM redeye_metadata_updates WHERE tenant_id=? AND project_id=? ORDER BY created DESC,rowid DESC', (who['tenant_id'], project))]
            legacy = []
            for r in c.execute("SELECT id,digest,artefact_id,status,connection_id,preview FROM redeye_import_tests WHERE tenant_id=? AND project_id=? AND status IN ('attempting','needs_review')", (who['tenant_id'], project)):
                plan = json.loads(r['preview'])
                try:
                    original_base = approved_base('redeye', plan['base_url'], [h.strip() for h in os.getenv('ORBIT_REDEYE_ALLOWED_HOSTS', '').lower().split(',')])
                except ProviderError:
                    original_base = 'Unverified original host; review the saved setup'
                legacy.append({'id': r['id'], 'digest': r['digest'], 'artefact_id': r['artefact_id'], 'status': r['status'],
                               'connection_name': plan['connection_name'], 'base_url': original_base})
        return {'connections': connections, 'updates': jobs, 'legacy_unresolved': legacy, 'uat_mode': os.getenv('ORBIT_UAT_MODE') == '1', 'server_version': app.version}

    @app.post('/api/projects/{project}/redeye-metadata/candidates')
    def candidates(project: str, body: ConnectionSelection, request: Request, who=Depends(identity)):
        permit(who, 'connection')
        with db() as c:
            row = connection(c, who, project, body.connection_id)
        base, secret, cfg = access(row)
        try:
            result = read_page('redeye', base, secret, 'artefacts', {}, cfg['auth_header'], cfg['auth_prefix'])
        except ProviderError as e:
            raise HTTPException(502, e.message)
        refresh(request, who, project, row)
        return result

    @app.post('/api/projects/{project}/redeye-metadata/inspect')
    def inspect(project: str, body: Selection, request: Request, who=Depends(identity)):
        permit(who, 'connection')
        with db() as c:
            row = connection(c, who, project, body.connection_id)
        data = read(row, body.artefact_id)
        refresh(request, who, project, row)
        ident = str(uuid4())
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            latest = connection(c, who, project, row['id'])
            if latest['generation'] != row['generation']:
                raise HTTPException(409, 'Connection changed; inspect again.')
            c.execute('INSERT INTO redeye_metadata_inspections VALUES(?,?,?,?,?,?,?)', (ident, who['tenant_id'], project, row['id'], row['generation'], canonical(data), int(time.time()) + 1800))
            audit(c, who, 'redeye_metadata.inspected', project, ident)
        return {'id': ident, 'snapshot': data, 'observed': now()}

    @app.post('/api/projects/{project}/redeye-metadata/verify')
    def verify(project: str, body: FieldSelection, request: Request, who=Depends(identity)):
        permit(who, 'connection')
        with db() as c:
            conn, before, key = inspection(c, who, project, body)
            reference, errors = source(c, who, project, body)
            base, secret, _ = access(conn)
            if secret and any(secret in v for v in [*encoded(body.values or []), body.property_uri, body.unit]):
                raise HTTPException(422, 'Credentials cannot be used as expected metadata values.')
        after = read(conn, before['artefact_id'])
        refresh(request, who, project, conn)
        if key not in after['keys']:
            raise HTTPException(409, 'Metadata field identity changed; inspect again.')
        expected = encoded(body.values) if body.values is not None else None
        actual = after['values'].get(str(key['id']), [])
        if reference:
            spec, _ = definition(reference['property'], {'target_name': 'MetadataValue', 'unit': reference['unit'], 'required': False})
            typed = actual
            if reference['property'].get('dataType') != 'String':
                try:
                    typed = [json.loads(v) for v in actual]
                except ValueError:
                    errors.append('Observed native value cannot be interpreted as the selected bSDD type.')
            if spec['value_kind'] == 'Single' and len(typed) != 1:
                errors.append('Observed field does not have exactly one value required by bSDD.')
            elif typed:
                problem = validate_value(typed if spec['value_kind'] == 'List' else typed[0], spec)
                if problem:errors.append('Observed value: ' + problem)
            else:
                errors.append('The selected bSDD property is unassigned on this artefact.')
        with db() as c:
            # Revalidate source selection after the network read, too.
            current_source, current_errors = source(c, who, project, body)
            if current_source != reference:
                raise HTTPException(409, 'bSDD selection changed; verify again.')
            audit(c, who, 'redeye_metadata.verified_read', project, str(key['id']))
        return {'actual': actual, 'expected': expected, 'matches': actual == expected if expected is not None else None,
                'validation_errors': errors + current_errors if current_errors != errors else errors, 'observed': now(), 'written': False,
                'scope': 'Latest approved revision returned by RedEye; no update was sent.'}

    @app.post('/api/projects/{project}/redeye-metadata/preview')
    def preview(project: str, body: FieldSelection, request: Request, who=Depends(identity)):
        permit(who, 'connection')
        if body.values is None:
            raise HTTPException(422, 'Specify the replacement value(s).')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            conn, before, key = inspection(c, who, project, body)
            reference, errors = source(c, who, project, body)
            if errors:
                raise HTTPException(422, '; '.join(errors))
            base, secret, _ = access(conn)
            if secret and any(secret in v for v in [*encoded(body.values or []), body.property_uri, body.unit]):
                raise HTTPException(422, 'Credentials cannot be used as metadata or property references.')
            values = encoded(body.values)
            previous = before['values'].get(str(key['id']), [])
            if values == previous:
                raise HTTPException(409, 'This field already matches. Use Verify only; no update is needed.')
            if any(previous) and not body.overwrite_existing:
                raise HTTPException(409, 'Select Replace existing value to update a populated field.')
            if not before['modifiable']:
                raise HTTPException(409, 'RedEye reports this artefact is not modifiable. Verify only is still available.')
            metadata = [{'name': k['name'], 'value': v} for ident, v in before['values'].items() for k in before['keys'] if str(k['id']) == ident and k['id'] != key['id']]
            metadata.append({'name': key['name'], 'value': values})
            if len(canonical(metadata)) > 100000:
                raise HTTPException(422, 'Metadata body exceeds the 100 KB limit.')
            ident = str(uuid4())
            plan = {'before': before, 'key': key, 'values': values, 'typed_values': body.values, 'source': reference,
                    'previous': previous, 'connection_name': conn['name'], 'base_url': base, 'payload': {'metadata': metadata}}
            expires = int(time.time()) + 1800
            fingerprint = digest({'id': ident, 'tenant': who['tenant_id'], 'project': project, 'connection': conn['id'], 'generation': conn['generation'], 'plan': plan, 'expires': expires})
            c.execute('INSERT INTO redeye_metadata_updates VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULL)', (ident, who['tenant_id'], project, conn['id'], before['artefact_id'], conn['generation'], session(request), canonical(plan), fingerprint, 'preview', now(), expires))
            audit(c, who, 'redeye_metadata.preview', project, ident)
            return public(job(c, who, project, ident))

    @app.post('/api/projects/{project}/redeye-metadata/{ident}/execute')
    def execute(project: str, ident: str, body: Confirm, request: Request, who=Depends(identity)):
        permit(who, 'connection')
        if os.getenv('ORBIT_UAT_MODE') != '1':
            conflict('uat_not_enabled', 'The running server is not in browser UAT mode.', 'Stop the old ORBIT server once and open Run-ORBIT.cmd, then reload the portal.')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = job(c, who, project, ident)
            exact(row, body)
            if row['status'] != 'preview':
                return json.loads(row['receipt']) if row['receipt'] else {'status': row['status'], 'automatic_retry': False}
            if row['session_hash'] != session(request):
                conflict('preview_session_changed', 'The browser session changed after this preview was prepared.', 'Stay signed in as the owner, load metadata again and prepare a fresh preview. Other tabs signing in or changing identities also rotate the session.')
            if row['expires'] <= int(time.time()):
                conflict('preview_expired', 'This metadata preview has expired.', 'Load metadata again and prepare a new preview; previews last 30 minutes.')
            if not body.confirmed or not body.current_revision_confirmed:
                conflict('confirmation_missing', 'The update confirmations are incomplete.', 'Tick both the displayed change confirmation and the current/approved target confirmation before saving.')
            conn = connection(c, who, project, row['connection_id'])
            if conn['generation'] != row['generation']:
                conflict('connection_changed', 'The saved connection or credential changed after preview.', 'Load metadata again using the current saved connection and prepare a fresh preview.')
            blockers = [{'id': r['id'], 'status': r['status'], 'source': source_name}
                        for table, source_name in [('redeye_metadata_updates', 'metadata'), ('redeye_import_tests', 'earlier_pilot')]
                        for r in c.execute(f"SELECT id,status FROM {table} WHERE connection_id=? AND artefact_id=? AND status IN ('attempting','needs_review')", (conn['id'], row['artefact_id']))]
            if blockers:
                conflict('earlier_update_unresolved', 'An earlier attempt on this artefact has an uncertain outcome.',
                         'Use Recheck without writing in the history below. If it remains uncertain, inspect the original target in native RedEye and explicitly close it after manual review. Then prepare a fresh preview.', blockers)
            c.execute("UPDATE redeye_metadata_updates SET status='attempting' WHERE id=?", (ident,))
            audit(c, who, 'redeye_metadata.attempt_reserved', project, ident)
        # A durable per-preview reservation prevents replay, but successful updates do not lock the artefact forever.
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = job(c, who, project, ident)
            http_ok = False
            post_started = False
            try:
                refresh(request, who, project, conn)
                conn = connection(c, who, project, row['connection_id'])
                plan = json.loads(row['plan'])
                if conn['generation'] != row['generation'] or row['expires'] <= int(time.time()):
                    return save(c, who, project, row, 'not_sent', 'Connection or preview changed before writing; inspect again.')
                if plan['source']:
                    src = c.execute('SELECT version,configuration FROM bsdd_settings WHERE tenant_id=? AND project_id=?', (who['tenant_id'], project)).fetchone()
                    if not src or src['version'] != plan['source']['version'] or digest(json.loads(src['configuration'])) != plan['source']['configuration_digest']:
                        return save(c, who, project, row, 'not_sent', 'bSDD reference changed; inspect and preview again.')
                before = read(conn, row['artefact_id'])
                if digest(before) != digest(plan['before']):
                    return save(c, who, project, row, 'not_sent', 'Destination changed since preview. No write sent; inspect again.')
                refresh(request, who, project, conn)
                base, secret, cfg = access(conn)
                post_started = True
                vendor.request_vendor(base, secret, cfg, 'POST', f"/api/v1/artefacts/{row['artefact_id']}", plan['payload'])
                http_ok = True
                after = read(conn, row['artefact_id'])
                ok = verified(plan, after)
                return save(c, who, project, row, 'verified' if ok else 'needs_review', 'Selected field and all preserved metadata matched.' if ok else 'Read-back differs from the reviewed change; inspect RedEye and recheck without writing.', http_ok, ok)
            except Exception:
                return save(c, who, project, row, 'needs_review' if post_started else 'not_sent', 'Update outcome could not be confirmed. Inspect RedEye; no automatic retry was sent.' if post_started else 'Preflight could not be completed. No POST sent; inspect again.', http_ok)

    @app.post('/api/projects/{project}/redeye-metadata/{ident}/recheck')
    def recheck(project: str, ident: str, body: Confirm, request: Request, who=Depends(identity)):
        permit(who, 'connection')
        with db() as c:
            row = job(c, who, project, ident)
            exact(row, body)
            conn = connection(c, who, project, row['connection_id'])
            if row['status'] not in {'attempting', 'needs_review', 'verified'} or conn['generation'] != row['generation']:
                raise HTTPException(409, 'Only an unchanged original destination with an attempted update can be rechecked.')
            if row['status'] == 'verified':
                return json.loads(row['receipt'])
        after = read(conn, row['artefact_id'])
        refresh(request, who, project, conn)
        ok = verified(json.loads(row['plan']), after)
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = job(c, who, project, ident)
            if row['status'] == 'verified':
                return json.loads(row['receipt'])
            if connection(c, who, project, row['connection_id'])['generation'] != row['generation']:
                raise HTTPException(409, 'Connection changed during recheck; inspect the original destination manually.')
            old = json.loads(row['receipt']) if row['receipt'] else {}
            return save(c, who, project, row, 'verified' if ok else 'needs_review', 'Observed selected field and preserved metadata match.' if ok else 'Observed state still differs; inspect RedEye manually.', old.get('http_200_observed', False), ok)

    @app.post('/api/projects/{project}/redeye-metadata/{ident}/resolve')
    def resolve(project: str, ident: str, body: Confirm, who=Depends(identity)):
        permit(who, 'connection')
        if not body.confirmed:
            raise HTTPException(409, 'Confirm that you manually reviewed the original target in RedEye. This does not retry or verify the update.')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            row = job(c, who, project, ident)
            exact(row, body)
            if row['status'] != 'needs_review':
                raise HTTPException(409, 'Only an uncertain attempt can be closed manually.')
            old = json.loads(row['receipt']) if row['receipt'] else {}
            return save(c, who, project, row, 'reviewed', 'Closed after operator manual review. This is not API write verification; no retry or rollback was sent.', old.get('http_200_observed', False), False)

    @app.post('/api/projects/{project}/redeye-metadata/legacy/{ident}/resolve')
    def resolve_legacy(project: str, ident: str, body: Confirm, who=Depends(identity)):
        permit(who, 'connection')
        if not body.confirmed:
            raise HTTPException(409, 'Confirm manual review of the original earlier-pilot target. This does not retry or verify its write.')
        with db() as c:
            c.execute('BEGIN IMMEDIATE')
            project_check(c, who, project)
            raw = c.execute('SELECT * FROM redeye_import_tests WHERE id=? AND tenant_id=? AND project_id=?', (ident, who['tenant_id'], project)).fetchone()
            if not raw:
                raise HTTPException(404, 'Earlier pilot unavailable in this project.')
            row = dict(raw)
            exact(row, body)
            if row['status'] != 'needs_review':
                raise HTTPException(409, 'First recheck an interrupted attempt without writing. Only an uncertain outcome can be closed manually.')
            old = json.loads(row['receipt']) if row['receipt'] else {}
            receipt = {**old, 'status': 'reviewed', 'read_back_verified': False, 'reason': 'Earlier pilot closed after operator manual review. No API write verification, retry or rollback is claimed.',
                       'observed': now(), 'automatic_retry': False, 'initial_outcome': old.get('initial_outcome', {'status': row['status'], 'reason': old.get('reason', 'Earlier uncertain attempt'), 'http_200_observed': old.get('http_200_observed', False)})}
            c.execute('UPDATE redeye_import_tests SET status=?,receipt=? WHERE id=?', ('reviewed', canonical(receipt), ident))
            audit(c, who, 'redeye_metadata.legacy_manually_reviewed', project, ident)
            return receipt

    app.state.metadata_inspect = inspect
