"""Explicit local test-access gate; no live calls are made by fixture checks."""
import json
import os
from typing import Literal
from uuid import uuid4

import httpx
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field

from backend.providers import FIXTURES, ProviderError, approved_base, auth_headers, read_page


class ReadConnection(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    provider: Literal["forma", "redeye"]
    base_url: str = Field(max_length=250)
    auth_header: str = Field(default="", max_length=64)
    auth_prefix: Literal["", "Bearer"] = ""
    vendor_settings_confirmed: bool = False
    approved_test_access: bool = False
    evidence_note: str = Field(default="", max_length=500)
    hub: str = Field(default="", max_length=250)
    vendor_project: str = Field(default="", max_length=250)
    folder: str = Field(default="", max_length=500)


class ReadRequest(BaseModel):
    operation: Literal["hubs", "projects", "folders", "documents", "artefacts", "groups", "metadata_keys"]
    hub: str = Field(default="", max_length=250)
    project: str = Field(default="", max_length=250)
    folder: str = Field(default="", max_length=500)


class Secret(BaseModel):
    secret: str = Field(min_length=8, max_length=8192)


def register_read_connections(app, db, identity, permit, project_check, audit, vault, now):
    def scoped(c, who, project, connection):
        project_check(c, who, project)
        row = c.execute("SELECT * FROM read_connections WHERE id=? AND tenant_id=? AND project_id=?", (connection, who["tenant_id"], project)).fetchone()
        if not row:
            raise HTTPException(404, "Read-test connection unavailable")
        return dict(row)

    @app.get("/api/projects/{project}/read-connections")
    def list_connections(project: str, who=Depends(identity)):
        permit(who, "connection")
        with db() as c:
            project_check(c, who, project)
            rows = c.execute("SELECT id,name,provider,configuration,generation,last_result,(secret_ciphertext IS NOT NULL) AS credential_present FROM read_connections WHERE tenant_id=? AND project_id=?", (who["tenant_id"], project)).fetchall()
        return {"live_reads_enabled": os.getenv("ORBIT_ENABLE_LIVE_READS") == "1", "connections": [{**dict(r), "configuration": json.loads(r["configuration"]), "last_result": json.loads(r["last_result"]) if r["last_result"] else None} for r in rows]}

    @app.post("/api/projects/{project}/read-connections")
    def create(project: str, body: ReadConnection, who=Depends(identity)):
        permit(who, "connection")
        # Save unverified configuration without asserting that a header/host is vendor-supported.
        if body.provider == "forma" and body.base_url != "https://developer.api.autodesk.com":
            raise HTTPException(422, "Use the documented Autodesk API host")
        try:
            auth_headers(body.provider, "synthetic-validation-only", body.auth_header, body.auth_prefix)
        except ProviderError as e:
            raise HTTPException(422, e.message)
        with db() as c:
            project_check(c, who, project)
            ident = str(uuid4())
            c.execute("INSERT INTO read_connections(id,tenant_id,project_id,name,provider,configuration) VALUES(?,?,?,?,?,?)", (ident, who["tenant_id"], project, body.name, body.provider, body.model_dump_json()))
            audit(c, who, "read_connection.configured", project, ident)
        return {"id": ident, "live_verified": False}

    @app.put("/api/projects/{project}/read-connections/{connection}/credential")
    def credential(project: str, connection: str, body: Secret, who=Depends(identity)):
        permit(who, "connection")
        with db() as c:
            scoped(c, who, project, connection)
            c.execute("DELETE FROM autodesk_tokens WHERE connection_id=?", (connection,))
            c.execute("DELETE FROM autodesk_states WHERE connection_id=?", (connection,))
            c.execute("DELETE FROM autodesk_choices WHERE connection_id=?", (connection,))
            c.execute("UPDATE read_connections SET secret_ciphertext=?,generation=generation+1,last_result=NULL WHERE id=?", (vault.encrypt(body.secret.encode()).decode(), connection))
            audit(c, who, "read_connection.credential_replaced", project, connection)
        return {"credential_present": True}

    @app.put("/api/projects/{project}/read-connections/{connection}/configuration")
    def update_configuration(project: str, connection: str, body: ReadConnection, who=Depends(identity)):
        permit(who, "connection")
        if body.provider == "forma" and body.base_url != "https://developer.api.autodesk.com":
            raise HTTPException(422, "Use the documented Autodesk API host")
        try:
            auth_headers(body.provider, "synthetic-validation-only", body.auth_header, body.auth_prefix)
        except ProviderError as e:
            raise HTTPException(422, e.message)
        with db() as c:
            row = scoped(c, who, project, connection)
            if row["provider"] != body.provider:
                raise HTTPException(409, "Create a separate connection to change provider")
            for table in ["autodesk_tokens", "autodesk_states", "autodesk_choices"]:
                c.execute(f"DELETE FROM {table} WHERE connection_id=?", (connection,))
            c.execute("UPDATE read_connections SET name=?,configuration=?,secret_ciphertext=NULL,generation=generation+1,last_result=NULL WHERE id=?", (body.name, body.model_dump_json(), connection))
            audit(c, who, "read_connection.settings_revised", project, connection)
        return {"saved": True, "reauthorisation_required": True}

    @app.post("/api/projects/{project}/read-connections/{connection}/fixture-check")
    def fixture_check(project: str, connection: str, body: ReadRequest | None = None, who=Depends(identity)):
        permit(who, "connection")
        with db() as c:
            row = scoped(c, who, project, connection)
            provider = row["provider"]
            default_operation = "hubs" if provider == "forma" else "artefacts"
            operation = body.operation if body else default_operation
            key = provider if operation == default_operation else f"{provider}:{operation}"
            if key not in FIXTURES:
                raise HTTPException(422, "No fixture is available for that operation")
            transport = httpx.MockTransport(lambda request: httpx.Response(200, json=FIXTURES[key]))
            result = read_page(provider, "https://fixture.invalid", "synthetic-fixture-only", operation, {}, "X-Fixture-Key", transport=transport)
            result.update(synthetic=True, live_verified=False, note="Hand-authored contract example, not a recorded vendor response")
            audit(c, who, "read_connection.fixture_checked", project, connection)
        return result

    @app.delete("/api/projects/{project}/read-connections/{connection}/credential")
    def clear_credential(project: str, connection: str, who=Depends(identity)):
        permit(who, "connection")
        with db() as c:
            scoped(c, who, project, connection)
            c.execute("DELETE FROM autodesk_tokens WHERE connection_id=?", (connection,))
            c.execute("DELETE FROM autodesk_states WHERE connection_id=?", (connection,))
            c.execute("DELETE FROM autodesk_choices WHERE connection_id=?", (connection,))
            c.execute("UPDATE read_connections SET secret_ciphertext=NULL,generation=generation+1,last_result=NULL WHERE id=?", (connection,))
            audit(c, who, "read_connection.credential_cleared", project, connection)
        return {"credential_present": False, "vendor_revoked": False}

    @app.post("/api/projects/{project}/read-connections/{connection}/read")
    def read(project: str, connection: str, body: ReadRequest, who=Depends(identity)):
        permit(who, "connection")
        with db() as c:
            row = scoped(c, who, project, connection)
            cfg = json.loads(row["configuration"])
            if os.getenv("ORBIT_ENABLE_LIVE_READS") != "1":
                raise HTTPException(409, "Live reads are disabled. The local operator must explicitly enable approved test access.")
            if not cfg["approved_test_access"] or not cfg["vendor_settings_confirmed"] or not cfg["evidence_note"].strip():
                raise HTTPException(409, "Confirm vendor settings, test authorisation and a non-secret evidence reference first")
            if not row["secret_ciphertext"]:
                raise HTTPException(409, "Credential is missing")
            required = {"projects": ["hub"], "folders": ["hub", "project"], "documents": ["project", "folder"]}.get(body.operation, [])
            scope_values = {"hub": cfg["hub"], "project": cfg["vendor_project"], "folder": cfg["folder"]}
            for field in required:
                if not scope_values[field] or getattr(body, field) != scope_values[field]:
                    raise HTTPException(409, "Resource scope must match the IDs configured for this test connection")
            hosts = [h.strip().lower() for h in os.getenv("ORBIT_REDEYE_ALLOWED_HOSTS", "").split(",") if h.strip()]
            try:
                base = approved_base(row["provider"], cfg["base_url"], hosts)
                secret = vault.decrypt(row["secret_ciphertext"].encode()).decode()
            except ProviderError as e:
                raise HTTPException(409, e.message)
            except Exception:
                raise HTTPException(409, "Stored credential could not be decrypted; replace it securely")
            generation = row["generation"]
            audit(c, who, "read_connection.read_requested", project, f"{connection}: {body.operation}")
        try:
            result = read_page(row["provider"], base, secret, body.operation, body.model_dump(), cfg["auth_header"], cfg["auth_prefix"])
            result.update(synthetic=False, observed=now(), provider=row["provider"], permission_claim="Only this specific read succeeded; other permissions and completeness are unverified")
        except ProviderError as e:
            with db() as c:
                audit(c, who, "read_connection.read_failed", project, e.code)
            raise HTTPException(502, {"code": e.code, "message": e.message})
        with db() as c:
            current = scoped(c, who, project, connection)
            # Membership may have changed during the network operation.
            membership = c.execute("SELECT role FROM memberships WHERE tenant_id=? AND user_id=?", (who["tenant_id"], who["user_id"])).fetchone()
            if not membership:
                raise HTTPException(403, "Membership changed during read")
            permit({**who, "role": membership["role"]}, "connection")
            if current["generation"] != generation:
                raise HTTPException(409, "Credential changed during read; response discarded")
            summary = {k: v for k, v in result.items() if k != "resources"}
            c.execute("UPDATE read_connections SET last_result=? WHERE id=?", (json.dumps(summary), connection))
            audit(c, who, "read_connection.read_completed", project, f"{connection}: {body.operation}, {result['returned']} resources; no import")
        return result
