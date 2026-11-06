import hashlib
import json
import logging
import sqlite3
import time
from urllib.parse import parse_qs, urlsplit

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.autodesk_auth import CALLBACK, RedactCallback, token_request
from backend.main import create_app
from backend.providers import ProviderError


@pytest.fixture
def portal(tmp_path, monkeypatch):
    monkeypatch.setenv("ORBIT_ENABLE_LIVE_READS", "1")
    path = tmp_path / "oauth.db"
    c = TestClient(create_app(path, demo=True), base_url="http://127.0.0.1:8000")
    c.post("/api/demo/session", json={"user_id": "north-owner"})
    body = {"name": "APS", "provider": "forma", "base_url": "https://developer.api.autodesk.com", "vendor_settings_confirmed": True, "approved_test_access": True, "evidence_note": "Approved synthetic test"}
    ident = c.post("/api/projects/harbour/read-connections", json=body).json()["id"]
    root = f"/api/projects/harbour/read-connections/{ident}/autodesk"
    return c, path, ident, root


def configure(c, root, mode="three_legged"):
    r = c.put(root, json={"client_id": "test-client", "client_secret": "synthetic-client-secret", "mode": mode})
    assert r.status_code == 200, r.text


def begin(c, root):
    r = c.post(root + "/connect")
    assert r.status_code == 200, r.text
    return parse_qs(urlsplit(r.json()["authorize_url"]).query)


def mock_exchange(monkeypatch):
    import backend.autodesk_auth as module
    calls = []
    def exchange(client, secret, data):
        calls.append(data)
        return {"access_token": "synthetic-access-token", "refresh_token": "synthetic-refresh-token", "expires": int(time.time()) + 3600}
    monkeypatch.setattr(module, "token_request", exchange)
    return calls


def test_app_configuration_is_encrypted_and_callback_fixed(portal):
    c, path, ident, root = portal
    configure(c, root)
    r = c.get(root)
    assert r.json()["callback_url"] == CALLBACK and "synthetic-client-secret" not in r.text
    with sqlite3.connect(path) as db:
        value = db.execute("SELECT client_secret_ciphertext FROM autodesk_apps").fetchone()[0]
        assert "synthetic-client-secret" not in value


def test_consent_pkce_callback_and_replay_protection(portal, monkeypatch):
    c, path, ident, root = portal
    configure(c, root)
    query = begin(c, root)
    assert query["scope"] == ["data:read"] and query["code_challenge_method"] == ["S256"]
    assert "synthetic-client-secret" not in str(query)
    calls = mock_exchange(monkeypatch)
    url = "/api/autodesk/callback?code=synthetic-code&state=" + query["state"][0]
    r = c.get(url, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/?autodesk=connected"
    assert calls[0]["grant_type"] == "authorization_code" and len(calls[0]["code_verifier"]) >= 43
    assert "synthetic-access-token" not in r.text
    assert c.get(url, follow_redirects=False).headers["location"] == "/?autodesk=failed"
    assert len(calls) == 1
    assert c.get(root).json()["renewal_available"] is True


@pytest.mark.parametrize("change", ["browser", "expiry", "role", "scope", "generation", "logout", "identity", "denied"])
def test_callback_revalidates_browser_session_and_connection(portal, monkeypatch, change):
    c, path, ident, root = portal
    configure(c, root)
    query = begin(c, root)
    calls = mock_exchange(monkeypatch)
    with sqlite3.connect(path) as db:
        if change == "expiry": db.execute("UPDATE autodesk_states SET expires=0")
        elif change == "role": db.execute("UPDATE memberships SET role='viewer' WHERE user_id='north-owner'")
        elif change == "scope": db.execute("DELETE FROM project_access WHERE user_id='north-owner'")
        elif change == "generation": db.execute("UPDATE read_connections SET generation=generation+1")
    if change == "browser": c.cookies.delete("orbit_oauth")
    elif change == "logout": c.delete("/api/session")
    elif change == "identity": c.post("/api/demo/session", json={"user_id": "north-viewer"})
    url = "/api/autodesk/callback?state=" + query["state"][0] + ("&error=access_denied" if change == "denied" else "&code=synthetic-code")
    assert c.get(url, follow_redirects=False).headers["location"] == "/?autodesk=failed"
    assert calls == []


def test_two_legged_and_explicit_refresh_never_return_tokens(portal, monkeypatch):
    c, path, ident, root = portal
    configure(c, root, "two_legged")
    calls = mock_exchange(monkeypatch)
    r = c.post(root + "/connect")
    assert r.status_code == 200 and "access_token" not in r.text
    assert calls[-1]["grant_type"] == "client_credentials"
    assert c.post(root + "/renew").status_code == 200
    assert calls[-1]["scope"] == "data:read"
    assert c.delete(root).json()["vendor_revoked"] is False
    assert c.get(root).json()["app"] is None
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT secret_ciphertext FROM read_connections WHERE id=?", (ident,)).fetchone()[0] is None


def test_authorisation_and_discovery_role_and_tenant_gates(portal):
    c, path, ident, root = portal
    c.post("/api/demo/session", json={"user_id": "north-viewer"})
    assert c.get(root).status_code == 403
    c.post("/api/demo/session", json={"user_id": "south-owner"})
    assert c.get(root.replace("harbour", "riverside")).status_code == 404


def test_dropdown_discovery_parent_selection_generation_and_scope_save(portal, monkeypatch):
    import backend.autodesk_auth as module
    c, path, ident, root = portal
    c.put(root.rsplit('/autodesk',1)[0] + "/credential", json={"secret": "synthetic-access-token"})
    def read(provider,base,secret,kind,scope):
        key = {"hubs": "hub", "projects": "project", "folders": "folder"}[kind]
        return {"resources": [{"id": key+"-id", "label": key.title()+" name", "kind": kind}], "returned": 1, "coverage": "fixture", "imported": 0}
    monkeypatch.setattr(module,"read_page",read)
    assert c.post(root+"/discover",json={"kind":"projects","hub":"fake"}).status_code == 409
    for body in [{"kind":"hubs"},{"kind":"projects","hub":"hub-id"},{"kind":"folders","hub":"hub-id","project":"project-id"}]:
        assert c.post(root+"/discover",json=body).status_code == 200
    assert c.put(root+"/selection",json={"hub":"hub-id","project":"other-id"}).status_code == 409
    result=c.put(root+"/selection",json={"hub":"hub-id","project":"project-id","folder":"folder-id"})
    assert result.status_code == 200 and result.json()["project"] == "Project name"
    cfg=c.get("/api/projects/harbour/read-connections").json()["connections"][0]["configuration"]
    assert cfg["vendor_project"] == "project-id" and cfg["project_label"] == "Project name"
    assert c.put(root+"/selection",json={"hub":"hub-id","project":"project-id"}).status_code == 409


@pytest.mark.parametrize("failure", ["expired", "generation"])
def test_discovery_cache_expires_and_is_credential_bound(portal, failure):
    c,path,ident,root=portal
    with sqlite3.connect(path) as db:
        db.execute("UPDATE read_connections SET secret_ciphertext='not-used'")
        db.execute("INSERT INTO autodesk_choices VALUES(?,?,?,?,?,?)",(ident,"hubs","",json.dumps([{"id":"hub","label":"Hub"}]),999 if failure=="generation" else 1,0 if failure=="expired" else int(time.time())+600))
    assert c.post(root+"/discover",json={"kind":"projects","hub":"hub"}).status_code == 409


def test_callback_log_redacts_query_parameters():
    record=logging.LogRecord("uvicorn.access",logging.INFO,"",0,"%s %s %s %s %s",("client","GET","/api/autodesk/callback?code=private&state=private","1.1",200),None)
    RedactCallback().filter(record)
    assert "code=private" not in record.getMessage() and "[REDACTED]" in record.getMessage()


def test_token_request_fixed_endpoint_basic_auth_and_validation():
    calls=[]
    def handler(r):
        calls.append(r)
        assert r.url == "https://developer.api.autodesk.com/authentication/v2/token"
        assert r.headers["authorization"].startswith("Basic ")
        assert "grant_type=client_credentials" in r.content.decode()
        return httpx.Response(200,json={"access_token":"synthetic-access","expires_in":3600,"token_type":"Bearer"})
    token=token_request("client","synthetic-secret",{"grant_type":"client_credentials","scope":"data:read"},transport=httpx.MockTransport(handler))
    assert token["access_token"] == "synthetic-access" and len(calls)==1
    with pytest.raises(ProviderError):
        token_request("client","synthetic-secret",{},transport=httpx.MockTransport(lambda r:httpx.Response(302,headers={"Location":"https://evil.example"})))


def test_refresh_uses_encrypted_refresh_token_and_never_exposes_it(portal, monkeypatch):
    c, path, ident, root = portal
    configure(c, root)
    query = begin(c, root)
    calls = mock_exchange(monkeypatch)
    c.get("/api/autodesk/callback?code=test-code&state="+query["state"][0])
    response = c.post(root+"/renew")
    assert response.status_code == 200
    assert calls[-1]["grant_type"] == "refresh_token" and calls[-1]["refresh_token"] == "synthetic-refresh-token"
    assert "synthetic-refresh-token" not in response.text
    assert "synthetic-access-token" not in c.get(root).text


def test_project_pagination_keeps_previous_choices_bound_to_hub(portal, monkeypatch):
    import backend.autodesk_auth as module
    c, path, ident, root = portal
    c.put(root.rsplit('/autodesk',1)[0]+"/credential",json={"secret":"synthetic-access-token"})
    def read(provider, base, secret, kind, scope):
        key="hub" if kind=="hubs" else "project-"+str(scope["page"])
        return {"resources":[{"id":key,"label":key,"kind":kind}],"returned":1}
    monkeypatch.setattr(module,"read_page",read)
    c.post(root+"/discover",json={"kind":"hubs"})
    for page in [0,1]:
        assert c.post(root+"/discover",json={"kind":"projects","hub":"hub","page":page}).status_code == 200
    with sqlite3.connect(path) as db:
        data=json.loads(db.execute("SELECT resources FROM autodesk_choices WHERE kind='projects'").fetchone()[0])
        assert {r["id"] for r in data} == {"project-0","project-1"}
    assert c.put(root+"/selection",json={"hub":"hub","project":"project-0"}).status_code == 200


def test_setup_revision_clears_existing_tokens_and_pending_consent(portal):
    c, path, ident, root=portal
    configure(c,root)
    begin(c,root)
    r=c.put(root.rsplit('/autodesk',1)[0]+"/configuration",json={"name":"Revised setup","provider":"forma","base_url":"https://developer.api.autodesk.com"})
    assert r.status_code == 200 and r.json()["reauthorisation_required"] is True
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT count(*) FROM autodesk_states").fetchone()[0] == 0
        assert db.execute("SELECT secret_ciphertext FROM read_connections WHERE id=?",(ident,)).fetchone()[0] is None
