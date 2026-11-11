import json
import sqlite3

import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.integrations import apply_mapping


@pytest.fixture
def portal(tmp_path):
    path = tmp_path / "integrations.db"
    return TestClient(create_app(path, demo=True)), path


def login(c, user="north-engineer"):
    assert c.post("/api/demo/session", json={"user_id": user}).status_code == 200


def config():
    return {"name": "Handover", "source_connection": "north-forma", "target_connection": "north-redeye", "source_scope": "Synthetic selected source", "target_scope": "Synthetic selected destination", "mappings": [{"source": "number", "target": "number", "required": True}, {"source": "title", "target": "title", "required": True}, {"source": "revision", "target": "revision", "required": True}]}


def setup(c, approve=True):
    login(c)
    response = c.post("/api/projects/harbour/profiles", json=config())
    assert response.status_code == 200, response.text
    p = response.json()
    if approve:
        login(c, "north-approver")
        assert c.post(f"/api/projects/harbour/profiles/{p['profile_id']}/approve", json={"digest": p["digest"]}).status_code == 200
        login(c)
    return p


def preview(c, p, number="C-005"):
    docs = c.get("/api/projects/harbour/connections/north-forma/documents").json()
    selected = next(d["id"] for d in docs if d["number"] == number)
    r = c.post(f"/api/projects/harbour/profiles/{p['profile_id']}/handovers", json={"document_ids": [selected]})
    assert r.status_code == 200, r.text
    return r.json()


def approve(c, h):
    login(c, "north-approver")
    return c.post(f"/api/projects/harbour/handovers/{h['id']}/approve", json={"digest": h["digest"]})


def test_profile_history_and_optimistic_versioning(portal):
    c, _ = portal
    p = setup(c)
    body = {**config(), "expected_version": 1, "name": "Revised"}
    url = f"/api/projects/harbour/profiles/{p['profile_id']}/versions"
    r = c.post(url, json=body)
    assert r.status_code == 200 and r.json()["version"] == 2 and r.json()["status"] == "draft"
    assert c.post(url, json=body).status_code == 409
    history = c.get(url).json()
    assert [v["version"] for v in history] == [2, 1]
    assert history[1]["status"] == "approved" and history[1]["digest"] == p["digest"]


def test_tenant_project_connection_and_role_boundaries(portal):
    c, path = portal
    p = setup(c)
    login(c, "south-engineer")
    assert c.get("/api/projects/harbour/profiles").status_code == 404
    assert c.post("/api/projects/riverside/profiles", json=config()).status_code == 404
    login(c, "north-viewer")
    assert c.post("/api/projects/harbour/profiles", json=config()).status_code == 403
    assert c.post(f"/api/projects/harbour/profiles/{p['profile_id']}/handovers", json={"document_ids": ["fake"]}).status_code == 403
    login(c)
    with sqlite3.connect(path) as db:
        db.execute("INSERT INTO projects VALUES('other','north','Other project')")
        db.execute("INSERT INTO project_access VALUES('north','north-engineer','other')")
    assert c.post("/api/projects/other/profiles", json=config()).status_code == 404


def test_invalid_mapping_targets_and_self_connections_rejected(portal):
    c, _ = portal
    login(c)
    body = config()
    body["mappings"].append(body["mappings"][0])
    assert c.post("/api/projects/harbour/profiles", json=body).status_code == 422
    body = {**config(), "target_connection": "north-forma"}
    assert c.post("/api/projects/harbour/profiles", json=body).status_code == 422


def test_mapping_defaults_transforms_and_value_conversions():
    rules = [{"source": "title", "target": "name", "transform": "trim", "required": True, "default": "", "value_map": {"Pump": "PUMP"}}, {"source": "revision", "target": "revision", "transform": "uppercase", "required": True, "default": "p00", "value_map": {}}]
    values, errors = apply_mapping({"title": " Pump ", "revision": None}, rules)
    assert values == {"name": "PUMP", "revision": "P00"} and errors == []


def test_manifest_freezes_selected_revision_and_never_executes(portal):
    c, _ = portal
    p = setup(c)
    h = preview(c, p)
    assert h["manifest"]["items"][0]["revision"] == "P01"
    assert h["manifest"]["items"][0]["mapped_metadata"]["number"] == "C-005"
    assert h["manifest"]["blockers"] == []
    r = approve(c, h)
    assert r.status_code == 200 and r.json()["files_transferred"] == 0 and r.json()["executed"] is False
    assert approve(c, h).status_code == 409


@pytest.mark.parametrize("number", ["C-001", "C-002", "C-004"])
def test_conflicts_draft_and_missing_revision_block_approval(portal, number):
    c, _ = portal
    p = setup(c)
    h = preview(c, p, number)
    assert h["manifest"]["blockers"]
    assert approve(c, h).status_code == 409


def test_draft_profile_and_self_approval_are_not_allowed(portal):
    c, path = portal
    p = setup(c, approve=False)
    h = preview(c, p)
    assert approve(c, h).status_code == 409
    login(c)
    with sqlite3.connect(path) as db:
        db.execute("UPDATE memberships SET role='approver' WHERE user_id='north-engineer'")
    assert c.post(f"/api/projects/harbour/profiles/{p['profile_id']}/approve", json={"digest": p["digest"]}).status_code == 409


@pytest.mark.parametrize("change", ["source", "destination", "connection", "expiry", "profile"])
def test_approval_revalidates_frozen_context(portal, change):
    c, path = portal
    p = setup(c)
    h = preview(c, p)
    with sqlite3.connect(path) as db:
        if change == "source":
            db.execute("UPDATE documents SET revision='P02' WHERE id=?", (h["manifest"]["items"][0]["source_id"],))
        elif change == "destination":
            db.execute("UPDATE documents SET revision='P99' WHERE connection_id='north-redeye'")
        elif change == "connection":
            db.execute("UPDATE connections SET generation=generation+1 WHERE id='north-forma'")
        elif change == "expiry":
            db.execute("UPDATE handovers SET expires=0")
    if change == "profile":
        c.post(f"/api/projects/harbour/profiles/{p['profile_id']}/versions", json={**config(), "expected_version": 1})
    assert approve(c, h).status_code == 409


def test_document_selection_cannot_escape_exact_connection(portal):
    c, path = portal
    p = setup(c)
    with sqlite3.connect(path) as db:
        foreign = db.execute("SELECT id FROM documents WHERE connection_id='south-forma' LIMIT 1").fetchone()[0]
    url = f"/api/projects/harbour/profiles/{p['profile_id']}/handovers"
    assert c.post(url, json={"document_ids": [foreign]}).status_code == 404
    target = c.get("/api/projects/harbour/connections/north-redeye/documents").json()[0]["id"]
    assert c.post(url, json={"document_ids": [target]}).status_code == 404


def test_new_connections_are_separate_even_for_same_provider(portal):
    c, _ = portal
    login(c, "north-owner")
    r = c.post("/api/projects/harbour/connections", json={"provider": "forma", "name": "Second account"})
    assert r.status_code == 200 and r.json()["live_access"] is False
    ident = r.json()["id"]
    assert c.get(f"/api/projects/harbour/connections/{ident}/documents").json() == []
    cfg = {**config(), "source_connection": ident}
    p = c.post("/api/projects/harbour/profiles", json=cfg).json()
    docs = c.get("/api/projects/harbour/connections/north-forma/documents").json()
    assert c.post(f"/api/projects/harbour/profiles/{p['profile_id']}/handovers", json={"document_ids": [docs[0]["id"]]}).status_code == 404
    login(c, "north-engineer")
    assert c.post("/api/projects/harbour/connections", json={"provider": "forma", "name": "Denied"}).status_code == 403


def test_mapped_destination_number_drives_conflict_check(portal):
    c, _ = portal
    login(c)
    cfg = config()
    cfg["mappings"][0]["value_map"] = {"C-005": "C-001"}
    p = c.post("/api/projects/harbour/profiles", json=cfg).json()
    assert preview(c, p)["manifest"]["blockers"]


def test_existing_database_upgrades_without_losing_records(tmp_path):
    from backend.main import ROOT
    path = tmp_path / "old.db"
    with sqlite3.connect(path) as db:
        db.executescript((ROOT / "backend/migrations/001_foundation.sql").read_text())
        db.execute("CREATE TABLE schema_migrations(version TEXT PRIMARY KEY)")
        db.execute("INSERT INTO schema_migrations VALUES('001_foundation.sql')")
        db.execute("INSERT INTO tenants VALUES('legacy','Legacy customer')")
        db.execute("INSERT INTO projects VALUES('legacy-project','legacy','Existing project')")
        db.execute("INSERT INTO connections VALUES('legacy-forma','legacy','legacy-project','forma','Existing','synthetic',NULL)")
        db.execute("INSERT INTO documents VALUES('legacy-doc','legacy','legacy-project','forma','OLD-1','Existing drawing','P01','approved')")
    create_app(path, demo=True)
    with sqlite3.connect(path) as db:
        assert db.execute("SELECT connection_id FROM documents WHERE id='legacy-doc'").fetchone()[0] == "legacy-forma"
        assert db.execute("SELECT count(*) FROM schema_migrations").fetchone()[0] == 12
