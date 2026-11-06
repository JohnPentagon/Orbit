import json
import sqlite3

import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.providers import FIXTURES, ProviderError, approved_base, auth_headers, read_page


@pytest.fixture
def portal(tmp_path):
    path = tmp_path / "read.db"
    c = TestClient(create_app(path, demo=True))
    c.post("/api/demo/session", json={"user_id": "north-owner"})
    return c, path


def setup(c, provider="forma", confirmed=True):
    body = {"name": "Read test", "provider": provider, "base_url": "https://developer.api.autodesk.com" if provider == "forma" else "https://vendor.example", "auth_header": "X-Test-Key", "vendor_settings_confirmed": confirmed, "approved_test_access": confirmed, "evidence_note": "Synthetic administrator test approval", "hub": "hub-1", "vendor_project": "project-1", "folder": "folder-1"}
    r = c.post("/api/projects/harbour/read-connections", json=body)
    assert r.status_code == 200, r.text
    ident = r.json()["id"]
    assert c.put(f"/api/projects/harbour/read-connections/{ident}/credential", json={"secret": "synthetic-key-123"}).status_code == 200
    return ident


def test_fixture_check_does_not_require_or_verify_live_access(portal):
    c, _ = portal
    ident = setup(c)
    r = c.post(f"/api/projects/harbour/read-connections/{ident}/fixture-check")
    assert r.status_code == 200 and r.json()["synthetic"] is True and r.json()["live_verified"] is False
    data = c.get("/api/projects/harbour/read-connections").json()
    assert data["connections"][0]["last_result"] is None
    assert "synthetic-key-123" not in json.dumps(data)


def test_default_live_gate_and_role_tenant_boundaries(portal):
    c, _ = portal
    ident = setup(c)
    url = f"/api/projects/harbour/read-connections/{ident}/read"
    assert c.post(url, json={"operation": "hubs"}).status_code == 409
    c.post("/api/demo/session", json={"user_id": "north-engineer"})
    assert c.get("/api/projects/harbour/read-connections").status_code == 403
    assert c.post(url, json={"operation": "hubs"}).status_code == 403
    c.post("/api/demo/session", json={"user_id": "south-owner"})
    assert c.post(url.replace('harbour','riverside'), json={"operation": "hubs"}).status_code == 404


@pytest.mark.parametrize("base", ["http://vendor.example", "https://vendor.example/path", "https://vendor.example:8080", "https://user:pass@vendor.example", "https://127.0.0.1", "https://evil.example", "https://vendor.example?x=1", "https://[bad"])
def test_host_policy_rejects_unsafe_or_unapproved_destinations(base):
    with pytest.raises(ProviderError):
        approved_base("redeye", base, ["vendor.example", "127.0.0.1"])


def test_exact_hosts_not_suffixes_and_no_credential_headers_to_proxy():
    assert approved_base("redeye", "https://vendor.example/", ["vendor.example"]) == "https://vendor.example"
    with pytest.raises(ProviderError):
        approved_base("redeye", "https://vendor.example.evil.example", ["vendor.example"])
    for header in ["Host", "Cookie", "Proxy-Authorization", "X-Key\r\nInjected", "Content-Type"]:
        with pytest.raises(ProviderError):
            auth_headers("redeye", "synthetic-secret", header)


@pytest.mark.parametrize("status,code", [(401,"access_denied"),(403,"access_denied"),(429,"rate_limited"),(302,"redirect_refused"),(500,"provider_error")])
def test_provider_errors_never_return_raw_body_or_follow_redirects(status, code):
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text="sensitive vendor error", headers={"Location":"https://evil.example"})
    with pytest.raises(ProviderError) as e:
        read_page("forma", "https://vendor.example", "synthetic-secret", "hubs", {}, transport=httpx.MockTransport(handler))
    assert e.value.code == code and "sensitive" not in e.value.message and len(calls) == 1


def test_adapters_get_only_minimal_resources_and_no_link_following():
    calls=[]
    def handler(request):
        calls.append(request)
        assert request.method == "GET"
        assert request.headers["authorization"] == "Bearer synthetic-secret"
        return httpx.Response(200,json={**FIXTURES["forma"],"links":{"next":{"href":"https://evil.example"}}})
    result=read_page("forma","https://vendor.example","synthetic-secret","hubs",{},transport=httpx.MockTransport(handler))
    assert result["returned"]==1 and result["imported"]==0 and len(calls)==1
    assert set(result["resources"][0])=={"id","label","kind"}


def test_resource_list_validation_and_size_limit():
    for payload, code in [({"unexpected":[]},"contract_mismatch"),({"data":[{"id":None}]},"contract_mismatch"),({"data":[],"extra":"a"*1_000_001},"response_too_large")]:
        with pytest.raises(ProviderError) as e:
            read_page("forma","https://vendor.example","synthetic-secret","hubs",{},transport=httpx.MockTransport(lambda r:httpx.Response(200,json=payload)))
        assert e.value.code==code


def test_live_read_fixture_transport_and_scope_gate(portal,monkeypatch):
    import backend.read_connections as module
    c,path=portal
    monkeypatch.setenv("ORBIT_ENABLE_LIVE_READS","1")
    ident=setup(c)
    original=module.read_page
    calls=[]
    def fake(*args,**kwargs):
        def handler(r):
            calls.append(r)
            return httpx.Response(200,json=FIXTURES["forma"])
        return original(*args,**kwargs,transport=httpx.MockTransport(handler))
    monkeypatch.setattr(module,"read_page",fake)
    url=f"/api/projects/harbour/read-connections/{ident}/read"
    assert c.post(url,json={"operation":"projects","hub":"other-hub"}).status_code==409
    assert calls==[]
    r=c.post(url,json={"operation":"projects","hub":"hub-1"})
    assert r.status_code==200 and r.json()["imported"]==0 and len(calls)==1
    saved=c.get("/api/projects/harbour/read-connections").json()["connections"][0]["last_result"]
    assert "resources" not in saved


def test_unconfirmed_settings_and_missing_host_allowlist_block(portal,monkeypatch):
    c,_=portal
    monkeypatch.setenv("ORBIT_ENABLE_LIVE_READS","1")
    ident=setup(c,confirmed=False)
    assert c.post(f"/api/projects/harbour/read-connections/{ident}/read",json={"operation":"hubs"}).status_code==409
    ident=setup(c,provider="redeye")
    assert c.post(f"/api/projects/harbour/read-connections/{ident}/read",json={"operation":"artefacts"}).status_code==409


def test_rotation_during_read_discards_result(portal,monkeypatch):
    import backend.read_connections as module
    c,path=portal
    monkeypatch.setenv("ORBIT_ENABLE_LIVE_READS","1")
    ident=setup(c)
    def changed(*args,**kwargs):
        with sqlite3.connect(path) as db:db.execute("UPDATE read_connections SET generation=generation+1")
        return {"resources":[],"returned":0}
    monkeypatch.setattr(module,"read_page",changed)
    assert c.post(f"/api/projects/harbour/read-connections/{ident}/read",json={"operation":"hubs"}).status_code==409


def test_redaction_of_echoed_credential():
    data={"data":[{"id":"synthetic-secret","attributes":{"name":"echo synthetic-secret"}}]}
    r=read_page("forma","https://vendor.example","synthetic-secret","hubs",{},transport=httpx.MockTransport(lambda r:httpx.Response(200,json=data)))
    assert "synthetic-secret" not in json.dumps(r)


def test_clear_credential_invalidates_last_result_without_claiming_revocation(portal):
    c,path=portal
    ident=setup(c)
    with sqlite3.connect(path) as db:db.execute("UPDATE read_connections SET last_result='{}' WHERE id=?",(ident,))
    r=c.delete(f"/api/projects/harbour/read-connections/{ident}/credential")
    assert r.status_code==200 and r.json()["vendor_revoked"] is False
    item=c.get("/api/projects/harbour/read-connections").json()["connections"][0]
    assert not item["credential_present"] and item["last_result"] is None and item["generation"]==3


def test_documented_qa_bearer_preset_does_not_imply_production_host():
    assert approved_base("redeye","https://qa-api.redeyedms.com",[]) == "https://qa-api.redeyedms.com"
    assert auth_headers("redeye","synthetic-api-key","Authorization","Bearer")["Authorization"] == "Bearer synthetic-api-key"
    with pytest.raises(ProviderError):
        approved_base("redeye","https://api.redeyedms.com",[])
