import hashlib
import json
import os
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.main import compare_documents, create_app


@pytest.fixture
def portal(tmp_path):
    path = tmp_path / "test.db"
    return TestClient(create_app(path, demo=True)), path


def sign_in(client, user="north-owner"):
    assert client.post("/api/demo/session", json={"user_id": user}).status_code == 200


def test_production_startup_refuses_demo_identity():
    with pytest.raises(RuntimeError, match="Production startup blocked"):
        create_app(demo=False)


def test_unauthenticated_access_is_denied(portal):
    client, _ = portal
    assert client.get("/api/workspace").status_code == 401
    assert client.post("/api/projects/harbour/comparisons").status_code == 401


def test_scope_and_non_leaking_connection_status(portal):
    client, _ = portal
    sign_in(client)
    data = client.get("/api/workspace").json()
    assert [p["id"] for p in data["projects"]] == ["harbour"]
    assert {c["id"] for c in data["connections"]} == {"north-forma", "north-redeye"}
    assert all(not p["live_writes"] for p in data["providers"])


@pytest.mark.parametrize("route,method", [("comparison", "get"), ("comparisons", "post"), ("audit", "get"), ("proposals", "get")])
def test_cross_tenant_project_access_fails(portal, route, method):
    client, _ = portal
    sign_in(client)
    assert getattr(client, method)(f"/api/projects/riverside/{route}").status_code == 404


def test_read_only_role_cannot_run_or_draft_or_store_secrets(portal):
    client, _ = portal
    sign_in(client, "north-viewer")
    assert client.post("/api/projects/harbour/comparisons").status_code == 403
    assert client.post("/api/projects/harbour/proposals", json={"source_field": "a", "target_field": "b"}).status_code == 403
    assert client.put("/api/connections/north-forma/credential", json={"secret": "test-key-123"}).status_code == 403


def test_synthetic_comparison_has_evidence_and_distinct_outcomes(portal):
    client, _ = portal
    sign_in(client, "north-engineer")
    result = client.post("/api/projects/harbour/comparisons").json()
    assert result["synthetic"] is True
    assert {f["state"] for f in result["findings"]} == {"candidate", "review", "different", "unknown", "unmatched"}
    assert len(result["findings"]) == 5
    assert all(f["reason"] for f in result["findings"])
    assert client.get("/api/projects/harbour/comparison").json()["id"] == result["id"]
    events = client.get("/api/projects/harbour/audit").json()
    assert events[0]["action"] == "comparison.completed"


def test_duplicate_numbers_require_review():
    record = {"number": "A-01", "provider": "forma", "title": "Drawing", "revision": "P01", "status": "approved"}
    assert compare_documents([record, dict(record)])["findings"][0]["state"] == "ambiguous"


def test_membership_and_project_revocation_apply_to_existing_session(portal):
    client, path = portal
    sign_in(client)
    with sqlite3.connect(path) as c:
        c.execute("DELETE FROM project_access WHERE user_id='north-owner'")
    assert client.get("/api/projects/harbour/comparison").status_code == 404
    with sqlite3.connect(path) as c:
        c.execute("DELETE FROM memberships WHERE user_id='north-owner'")
    assert client.get("/api/workspace").status_code == 401


def test_vault_encrypts_and_responses_and_audit_do_not_reveal_secret(portal):
    client, path = portal
    sign_in(client)
    secret = "synthetic-secret-never-return"
    response = client.put("/api/connections/north-redeye/credential", json={"secret": secret})
    assert response.status_code == 200
    assert secret not in response.text
    assert secret not in client.get("/api/workspace").text
    assert secret not in client.get("/api/projects/harbour/audit").text
    with sqlite3.connect(path) as c:
        ciphertext = c.execute("SELECT secret_ciphertext FROM connections WHERE id='north-redeye'").fetchone()[0]
    assert secret not in ciphertext
    if os.name != "nt":
        assert (path.parent / "vault.key").stat().st_mode & 0o777 == 0o600


def test_secret_validation_does_not_echo_input(portal):
    client, _ = portal
    sign_in(client)
    response = client.put("/api/connections/north-forma/credential", json={"secret": "s3cr3t"})
    assert response.status_code == 422
    assert "s3cr3t" not in response.text


def test_cross_tenant_credentials_cannot_be_replaced(portal):
    client, _ = portal
    sign_in(client)
    assert client.put("/api/connections/south-forma/credential", json={"secret": "test-key-123"}).status_code == 404


def test_approval_binds_preview_role_project_and_pending_state(portal):
    client, _ = portal
    sign_in(client, "north-engineer")
    item = client.post("/api/projects/harbour/proposals", json={"source_field": "number", "target_field": "artefact.number"}).json()
    url = f"/api/projects/harbour/proposals/{item['id']}/approve"
    assert client.post(url, json={"digest": item["digest"]}).status_code == 403
    sign_in(client, "south-approver")
    assert client.post(url, json={"digest": item["digest"]}).status_code == 404
    sign_in(client, "north-approver")
    assert client.post(url, json={"digest": "changed"}).status_code == 409
    response = client.post(url, json={"digest": item["digest"]})
    assert response.status_code == 200
    assert response.json()["executed"] is False
    assert client.post(url, json={"digest": item["digest"]}).status_code == 409


def test_expired_and_signed_out_sessions_cannot_be_reused(portal):
    client, path = portal
    sign_in(client)
    with sqlite3.connect(path) as c:
        c.execute("UPDATE sessions SET expires=0")
    assert client.get("/api/workspace").status_code == 401
    sign_in(client)
    token = client.cookies.get("orbit_session")
    client.delete("/api/session")
    client.cookies.set("orbit_session", token)
    assert client.get("/api/workspace").status_code == 401


def test_cross_origin_mutation_and_untrusted_host_are_rejected(portal):
    client, _ = portal
    assert client.post("/api/demo/session", json={"user_id": "north-owner"}, headers={"Origin": "https://evil.example"}).status_code == 403
    assert client.get("/api/health", headers={"Host": "evil.example"}).status_code == 400


def test_database_relationship_cannot_cross_tenants(portal):
    _, path = portal
    with sqlite3.connect(path) as c:
        c.execute("PRAGMA foreign_keys=ON")
        with pytest.raises(sqlite3.IntegrityError):
            c.execute("INSERT INTO project_access VALUES('north','north-owner','riverside')")


def test_restart_preserves_records_and_migrations(portal):
    client, path = portal
    sign_in(client)
    item = client.post("/api/projects/harbour/comparisons").json()
    other = TestClient(create_app(path, demo=True))
    sign_in(other)
    assert other.get("/api/projects/harbour/comparison").json()["id"] == item["id"]
    with sqlite3.connect(path) as c:
        assert c.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 12


def test_admin_grants_revoke_running_session_and_cannot_cross_tenants(portal):
    owner, path = portal
    viewer = TestClient(owner.app)
    sign_in(owner)
    sign_in(viewer, "north-viewer")
    assert viewer.get("/api/admin/members").status_code == 403
    assert owner.put("/api/admin/members/south-viewer", json={"role": "viewer", "projects": []}).status_code == 404
    assert owner.put("/api/admin/members/north-viewer", json={"role": "viewer", "projects": ["riverside"]}).status_code == 404
    assert owner.put("/api/admin/members/north-viewer", json={"role": "viewer", "projects": []}).status_code == 200
    assert viewer.get("/api/projects/harbour/comparison").status_code == 404
    assert owner.put("/api/admin/members/north-owner", json={"role": "viewer", "projects": ["harbour"]}).status_code == 409


def test_role_change_does_not_allow_self_approval(portal):
    client, path = portal
    sign_in(client, "north-engineer")
    item = client.post("/api/projects/harbour/proposals", json={"source_field": "a", "target_field": "b"}).json()
    with sqlite3.connect(path) as c:
        c.execute("UPDATE memberships SET role='approver' WHERE user_id='north-engineer'")
    assert client.post(f"/api/projects/harbour/proposals/{item['id']}/approve", json={"digest": item["digest"]}).status_code == 409
