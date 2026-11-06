import json
import logging
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app


@pytest.fixture
def portal(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBIT_ENABLE_LIVE_READS", "1")
    path = tmp_path / "readiness.db"
    c = TestClient(create_app(path, demo=True))
    c.post("/api/demo/session", json={"user_id": "north-owner"})
    return c, path


def connection(c, **changes):
    body = {"name": "Diagnostic profile", "provider": "redeye", "base_url": "https://api.redeyedms.com", "auth_header": "Authorization", "auth_prefix": "Bearer", "vendor_settings_confirmed": True, "approved_test_access": True, "evidence_note": "Synthetic test authorisation"}
    ident = c.post("/api/projects/harbour/read-connections", json={**body, **changes}).json()["id"]
    c.put(f"/api/projects/harbour/read-connections/{ident}/credential", json={"secret": "synthetic-diagnostic-key"})
    return ident


def report(c, ident):
    payload = c.get("/api/projects/harbour/read-connections").json()
    return next(r for r in payload["connections"] if r["id"] == ident)


@pytest.mark.parametrize("changes,code", [({"vendor_settings_confirmed":False},"vendor_settings_unconfirmed"),({"approved_test_access":False},"test_access_unconfirmed"),({"evidence_note":" "},"evidence_missing"),({"base_url":"https://unapproved.example"},"host_not_allowed")])
def test_precise_saved_setting_gate_no_vendor_request(portal, monkeypatch, changes, code):
    import backend.read_connections as module
    c,_=portal
    ident=connection(c,**changes)
    def never(*args,**kwargs):raise AssertionError("Blocked reads must not contact a provider")
    monkeypatch.setattr(module,"read_page",never)
    item=report(c,ident)
    assert not item["readiness"]["ready"] and code in [i["code"] for i in item["readiness"]["issues"]]
    r=c.post(f"/api/projects/harbour/read-connections/{ident}/read",json={"operation":"artefacts"})
    assert r.status_code==409 and r.json()["detail"]["code"]==code and r.json()["detail"]["next_action"]


def test_vault_mismatch_is_distinct_from_missing_credential_and_redacted(portal,caplog):
    c,path=portal
    ident=connection(c)
    with sqlite3.connect(path) as db:db.execute("UPDATE read_connections SET secret_ciphertext='broken-ciphertext' WHERE id=?",(ident,))
    item=report(c,ident)
    assert item["credential_present"] and item["readiness"]["issues"][0]["code"]=="credential_unreadable"
    with caplog.at_level(logging.WARNING,logger="uvicorn.error"):
        r=c.post(f"/api/projects/harbour/read-connections/{ident}/read",json={"operation":"artefacts"})
    assert r.status_code==409 and "credential_unreadable" in caplog.text
    assert "broken-ciphertext" not in caplog.text and "synthetic-diagnostic-key" not in caplog.text
    assert "secret_ciphertext" not in json.dumps(item)


def test_runtime_version_and_live_flag_ready_are_reported_without_credentials(portal,monkeypatch):
    c,_=portal
    ident=connection(c)
    assert report(c,ident)["readiness"]=={"ready":True,"issues":[]}
    assert c.get('/api/health').json()["server_version"]==c.app.version
    assert c.get('/api/projects/harbour/read-connections').json()["server_version"]==c.app.version
    monkeypatch.delenv("ORBIT_ENABLE_LIVE_READS")
    assert report(c,ident)["readiness"]["issues"][0]["code"]=="live_reads_disabled"


def test_setup_revision_and_clear_show_required_reentry(portal):
    c,_=portal
    ident=connection(c)
    c.delete(f"/api/projects/harbour/read-connections/{ident}/credential")
    assert report(c,ident)["readiness"]["issues"][0]["code"]=="credential_missing"
