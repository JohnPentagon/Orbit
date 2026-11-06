import copy
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.meridian import EXPLORER_FIXTURE, explorer_documents
from backend.providers import ProviderError

ROOT = '/api/projects/harbour/connection-plans'


@pytest.fixture
def portal(tmp_path):
    path = tmp_path / 'plans.db'
    c = TestClient(create_app(path, demo=True))
    c.post('/api/demo/session', json={'user_id': 'north-owner'})
    return c, path


def plan(**changes):
    return {'name': 'Meridian Harbour', 'provider': 'meridian', 'interface': 'Explorer Web API (read)', 'deployment': 'on_premises', **changes}


def test_persistence_and_manual_evidence_never_enables_adapter(portal):
    c, path = portal
    ident = c.post(ROOT, json=plan(checks={'edition': {'status': 'blocked', 'evidence': 'Awaiting installed version from admin'}})).json()['id']
    payload = c.get(ROOT).json()
    assert not payload['live_adapter_enabled']
    saved = payload['plans'][0]
    assert saved['id'] == ident and saved['configuration']['checks']['edition']['status'] == 'blocked'
    second = TestClient(create_app(path, demo=True))
    second.post('/api/demo/session', json={'user_id': 'north-owner'})
    assert second.get(ROOT).json()['plans'][0]['id'] == ident
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM schema_migrations WHERE version='005_connection_plans.sql'").fetchone()[0] == 1


def test_scope_roles_and_revoked_grants(portal):
    c, path = portal
    ident = c.post(ROOT, json=plan()).json()['id']
    saved = c.get(ROOT).json()['plans'][0]['configuration']
    for role in ['viewer', 'engineer', 'approver', 'auditor']:
        c.post('/api/demo/session', json={'user_id': 'north-'+role})
        assert c.get(ROOT).status_code == 200
        assert c.post(ROOT, json=plan()).status_code == 403
        assert c.put(ROOT+'/'+ident, json={**saved, 'version': 1}).status_code == 403
        assert c.post(ROOT+'/'+ident+'/fixture-check').status_code == 403
    c.post('/api/demo/session', json={'user_id': 'south-owner'})
    assert c.get(ROOT).status_code == 404
    assert c.put('/api/projects/riverside/connection-plans/'+ident, json={**saved, 'version': 1}).status_code == 404
    c.post('/api/demo/session', json={'user_id': 'north-owner'})
    with sqlite3.connect(path) as db:
        db.execute("DELETE FROM project_access WHERE user_id='north-owner'")
    assert c.get(ROOT).status_code == 404
    assert c.post(ROOT+'/'+ident+'/fixture-check').status_code == 404


def test_optimistic_editing_and_environment_change_invalidates_evidence(portal):
    c,_ = portal
    ident = c.post(ROOT, json=plan(checks={'scope': {'status': 'passed', 'evidence': 'Synthetic test record, not a vendor test'}})).json()['id']
    body = c.get(ROOT).json()['plans'][0]['configuration']
    r = c.put(ROOT+'/'+ident, json={**body, 'version': 1, 'name': 'Rename only'})
    assert r.status_code == 200 and not r.json()['checks_reset']
    assert c.put(ROOT+'/'+ident, json={**body, 'version': 1}).status_code == 409
    r = c.put(ROOT+'/'+ident, json={**body, 'version': 2, 'service_url': 'https://internal.example:8443/BCEnterprise'})
    assert r.json()['checks_reset']
    assert c.get(ROOT).json()['plans'][0]['configuration']['checks'] == {}
    assert c.put(ROOT+'/'+ident, json={**plan(provider='procore', interface='Procore REST API'), 'version': 3}).status_code == 422


@pytest.mark.parametrize('change', [
    {'checks': {'unknown': {'status': 'passed', 'evidence': 'x'}}},
    {'checks': {'scope': {'status': 'passed', 'evidence': ' '}}},
    {'checks': {'scope': {'status': 'not_applicable', 'evidence': ''}}},
    {'interface': 'PowerWeb scraped endpoints'}, {'name': '   '},
    {'service_url': 'http://internal.example'}, {'service_url': 'https://key:secret@internal.example'},
    {'service_url': 'https://internal.example/?token=secret'}, {'service_url': 'https://internal.example/#secret'},
    {'secret': 'should-not-be-accepted'},
])
def test_invalid_or_secret_bearing_configuration_rejected(portal, change):
    c,_ = portal
    assert c.post(ROOT, json=plan(**change)).status_code == 422


def test_fixture_is_offline_and_cannot_mark_manual_checks_passed(portal, monkeypatch):
    import httpx
    def never(*a, **kw):
        raise AssertionError('No provider requests allowed')
    monkeypatch.setattr(httpx, 'get', never)
    ident = portal[0].post(ROOT, json=plan()).json()['id']
    c = portal[0]
    response = c.post(ROOT+'/'+ident+'/fixture-check')
    assert response.status_code == 200
    assert response.json()['synthetic'] and response.json()['files_transferred'] == 0
    assert c.get(ROOT).json()['plans'][0]['configuration']['checks'] == {}
    other = c.post(ROOT, json=plan(provider='procore', interface='Undecided')).json()['id']
    assert c.post(ROOT+'/'+other+'/fixture-check').status_code == 422


def test_explorer_identity_types_bounds_and_untrusted_download_links():
    payload = copy.deepcopy(EXPLORER_FIXTURE)
    payload['Documents'][0]['DownloadUrlSource'] = 'http://untrusted.example/file'
    parsed = explorer_documents(payload)
    row = parsed['resources'][0]
    assert row['document_id'] != row['version_id'] and row['revision'] == 'P01'
    assert row['properties'][1]['value'] is True and row['properties'][2]['value'] == 2
    assert 'DownloadUrlSource' not in str(parsed) and 'untrusted.example' not in str(parsed)
    payload['Documents'] *= 30
    assert explorer_documents(payload)['returned'] == 25
    assert explorer_documents({'PageIndex': 0, 'ActualCount': 0, 'Documents': []})['resources'] == []


@pytest.mark.parametrize('payload', [{}, {'PageIndex': True, 'ActualCount': 1, 'Documents': []}, {'PageIndex': 0, 'ActualCount': 1, 'Documents': [{}]}, {'PageIndex': 0, 'ActualCount': 1, 'Documents': [{**EXPLORER_FIXTURE['Documents'][0], 'Properties': [{'Name': 'Nested', 'Value': {}}]}]}])
def test_explorer_rejects_unknown_contract(payload):
    with pytest.raises(ProviderError):
        explorer_documents(payload)
