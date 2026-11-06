"""Local synthetic foundation. Deployment is blocked until production identity is implemented."""
import hashlib
import json
import os
import secrets
import sqlite3
import time
from collections import defaultdict
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.trustedhost import TrustedHostMiddleware
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parents[1]
ROLES = {"owner": {"view", "run", "connection", "draft", "administer"}, "engineer": {"view", "run", "draft"}, "approver": {"view", "approve"}, "viewer": {"view"}, "auditor": {"view", "audit"}}
PROVIDERS = [
    {"id": key, "name": name, "maturity": "Synthetic only", "live_reads": False, "live_writes": False}
    for key, name in [("forma", "Autodesk Forma / ACC Docs"), ("redeye", "Accruent RedEye"), ("procore", "Procore"), ("meridian", "Accruent Meridian"), ("maintenance", "Maintenance Connection"), ("revit", "Revit 2024+"), ("navisworks", "Navisworks 2024+"), ("generic", "Custom REST / files")]
]

def now():
    return datetime.now(timezone.utc).isoformat()

def compare_documents(records):
    """Compare approved business revisions; never infer equality of binary contents."""
    groups = defaultdict(lambda: defaultdict(list))
    for record in records:
        groups[record["number"].strip().casefold()][record["provider"]].append(record)
    findings = []
    for number, sides in sorted(groups.items()):
        left, right = sides["forma"], sides["redeye"]
        if len(left) > 1 or len(right) > 1:
            state, reason = "ambiguous", "Duplicate document number; review identity before matching."
        elif not left or not right:
            state, reason = "unmatched", "No candidate in the selected synthetic register; not proof of vendor deletion."
        elif left[0]["status"] != "approved" or right[0]["status"] != "approved":
            state, reason = "review", "Comparison bases differ: latest uploaded versus latest approved."
        elif not left[0]["revision"] or not right[0]["revision"]:
            state, reason = "unknown", "Business revision metadata is incomplete."
        elif left[0]["revision"] != right[0]["revision"]:
            state, reason = "different", "Business revision labels differ; no chronological order inferred."
        else:
            state, reason = "candidate", "Number and approved revision agree; identity and file content remain unverified."
        findings.append({"number": number.upper(), "title": (left or right)[0]["title"], "state": state, "reason": reason, "forma": left, "redeye": right})
    return {"synthetic": True, "coverage": "Complete for the seeded synthetic register only", "findings": findings}

def create_app(db_path=None, demo=None):
    demo = os.getenv("ORBIT_DEMO_MODE") == "1" if demo is None else demo
    if not demo:
        raise RuntimeError("Production startup blocked: configure production OIDC and deployment controls before disabling demo mode.")
    path = Path(db_path or ROOT / ".local/orbit.db")
    path.parent.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def db():
        conn = sqlite3.connect(path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    with db() as c:
        c.execute("CREATE TABLE IF NOT EXISTS schema_migrations(version TEXT PRIMARY KEY)")
        for migration in sorted((ROOT / "backend/migrations").glob("*.sql")):
            if not c.execute("SELECT 1 FROM schema_migrations WHERE version=?", (migration.name,)).fetchone():
                version = migration.name.replace("'", "''")
                c.executescript("BEGIN IMMEDIATE;\n" + migration.read_text() + f"\nINSERT INTO schema_migrations VALUES('{version}');\nCOMMIT;")
        if not c.execute("SELECT 1 FROM tenants").fetchone():
            for tenant, name, project in [("north", "Northstar Construction", "harbour"), ("south", "Southbank Estates", "riverside")]:
                c.execute("INSERT INTO tenants VALUES(?,?)", (tenant, name))
                c.execute("INSERT INTO projects VALUES(?,?,?)", (project, tenant, "Harbour Exchange" if tenant == "north" else "Riverside Campus"))
                for role in ROLES:
                    user = f"{tenant}-{role}"
                    c.execute("INSERT INTO users VALUES(?,?)", (user, role.title() + " tester"))
                    c.execute("INSERT INTO memberships VALUES(?,?,?)", (tenant, user, role))
                    c.execute("INSERT INTO project_access VALUES(?,?,?)", (tenant, user, project))
                for provider in ["forma", "redeye"]:
                    c.execute("INSERT INTO connections(id,tenant_id,project_id,provider,name,status,secret_ciphertext) VALUES(?,?,?,?,?,?,NULL)", (f"{tenant}-{provider}", tenant, project, provider, "Synthetic " + provider.title(), "synthetic"))
                samples = [("C-001", "Ground floor plan", "P01", "approved", "P01", "approved"), ("C-002", "Structural general arrangement", "P03", "draft", "P02", "approved"), ("C-003", "Fire strategy", "C02", "approved", "C01", "approved"), ("C-004", "Asset handover schedule", None, "approved", "P01", "approved")]
                for number, title, lr, ls, rr, rs in samples:
                    for provider, rev, state in [("forma", lr, ls), ("redeye", rr, rs)]:
                        c.execute("INSERT INTO documents(id,tenant_id,project_id,provider,number,title,revision,status,connection_id) VALUES(?,?,?,?,?,?,?,?,?)", (str(uuid4()), tenant, project, provider, number, title, rev, state, f"{tenant}-{provider}"))
                c.execute("INSERT INTO documents(id,tenant_id,project_id,provider,number,title,revision,status,connection_id) VALUES(?,?,?,?,?,?,?,?,?)", (str(uuid4()), tenant, project, "forma", "C-005", "Drainage layout", "P01", "approved", f"{tenant}-forma"))

    key_path = path.parent / "vault.key"
    if not key_path.exists():
        fd = os.open(key_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "wb") as file:
            file.write(Fernet.generate_key())
    vault = Fernet(key_path.read_bytes())
    app = FastAPI(title="ORBIT foundation", version="0.5.0")
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=["localhost", "127.0.0.1", "testserver"])

    @app.exception_handler(RequestValidationError)
    async def validation_error(request, exc):
        return JSONResponse(status_code=422, content={"detail": [{"loc": list(e["loc"]), "msg": e["msg"], "type": e["type"]} for e in exc.errors()]})

    @app.middleware("http")
    async def guard(request: Request, call_next):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            origin = request.headers.get("origin")
            if origin and origin != str(request.base_url).rstrip("/"):
                return Response("Cross-origin mutation rejected", status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
        return response

    def identity(request: Request):
        token = request.cookies.get("orbit_session", "")
        with db() as c:
            row = c.execute("SELECT s.user_id,s.tenant_id,m.role FROM sessions s JOIN memberships m ON m.tenant_id=s.tenant_id AND m.user_id=s.user_id WHERE token_hash=? AND expires>?", (hashlib.sha256(token.encode()).hexdigest(), int(time.time()))).fetchone()
        if not row:
            raise HTTPException(401, "Sign in to a synthetic test identity")
        return dict(row)

    def permit(who, action):
        if action not in ROLES.get(who["role"], set()):
            raise HTTPException(403, "Action not allowed for this role")

    def project_check(c, who, project):
        if not c.execute("SELECT 1 FROM project_access WHERE tenant_id=? AND user_id=? AND project_id=?", (who["tenant_id"], who["user_id"], project)).fetchone():
            raise HTTPException(404, "Project not available")

    def audit(c, who, action, project=None, detail=""):
        c.execute("INSERT INTO audit VALUES(?,?,?,?,?,?,?)", (str(uuid4()), who["tenant_id"], project, who["user_id"], action, detail, now()))

    @app.get("/api/health")
    def health():
        return {"status": "ok", "mode": "synthetic-development", "live_connectors": False, "server_version": app.version}

    @app.get("/api/demo/identities")
    def identities():
        with db() as c:
            return [dict(r) for r in c.execute("SELECT m.user_id,m.tenant_id,m.role,t.name FROM memberships m JOIN tenants t ON t.id=m.tenant_id")]

    class Login(BaseModel):
        user_id: str

    @app.post("/api/demo/session")
    def login(body: Login, response: Response, request: Request):
        with db() as c:
            row = c.execute("SELECT * FROM memberships WHERE user_id=?", (body.user_id,)).fetchone()
            if not row:
                raise HTTPException(401, "Unknown test identity")
            c.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(request.cookies.get("orbit_session", "").encode()).hexdigest(),))
            token = secrets.token_urlsafe(32)
            c.execute("INSERT INTO sessions VALUES(?,?,?,?)", (hashlib.sha256(token.encode()).hexdigest(), row["user_id"], row["tenant_id"], int(time.time()) + 3600))
            audit(c, dict(row), "demo.sign_in")
        response.set_cookie("orbit_session", token, httponly=True, samesite="strict", max_age=3600)
        return {"synthetic": True}

    @app.delete("/api/session")
    def logout(request: Request, response: Response):
        with db() as c:
            c.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(request.cookies.get("orbit_session", "").encode()).hexdigest(),))
        response.delete_cookie("orbit_session")
        return {"ok": True}

    @app.get("/api/workspace")
    def workspace(who=Depends(identity)):
        permit(who, "view")
        with db() as c:
            projects = [dict(r) for r in c.execute("SELECT p.* FROM projects p JOIN project_access a ON a.project_id=p.id AND a.tenant_id=p.tenant_id WHERE a.tenant_id=? AND a.user_id=?", (who["tenant_id"], who["user_id"]))]
            connections = [dict(r) for r in c.execute("SELECT c.id,c.project_id,c.provider,c.name,c.status,(c.secret_ciphertext IS NOT NULL) AS credential_present FROM connections c JOIN project_access a ON a.tenant_id=c.tenant_id AND a.project_id=c.project_id WHERE a.tenant_id=? AND a.user_id=?", (who["tenant_id"], who["user_id"]))]
            tenant = dict(c.execute("SELECT * FROM tenants WHERE id=?", (who["tenant_id"],)).fetchone())
        return {"identity": who, "permissions": sorted(ROLES[who["role"]]), "tenant": tenant, "projects": projects, "connections": connections, "providers": PROVIDERS, "synthetic": True}

    @app.get("/api/admin/members")
    def members(who=Depends(identity)):
        permit(who, "administer")
        with db() as c:
            result = []
            for row in c.execute("SELECT m.user_id,m.role,u.name FROM memberships m JOIN users u ON u.id=m.user_id WHERE m.tenant_id=?", (who["tenant_id"],)).fetchall():
                member = dict(row)
                member["projects"] = [r[0] for r in c.execute("SELECT project_id FROM project_access WHERE tenant_id=? AND user_id=?", (who["tenant_id"], row["user_id"]))]
                result.append(member)
        return result

    class MemberAccess(BaseModel):
        role: str
        projects: list[str] = Field(max_length=100)

    @app.put("/api/admin/members/{user}")
    def update_member(user: str, body: MemberAccess, who=Depends(identity)):
        permit(who, "administer")
        if body.role not in ROLES:
            raise HTTPException(422, "Unknown role")
        with db() as c:
            c.execute("BEGIN IMMEDIATE")
            old = c.execute("SELECT role FROM memberships WHERE tenant_id=? AND user_id=?", (who["tenant_id"], user)).fetchone()
            if not old:
                raise HTTPException(404, "Membership unavailable")
            if old["role"] == "owner" and body.role != "owner" and c.execute("SELECT count(*) FROM memberships WHERE tenant_id=? AND role='owner'", (who["tenant_id"],)).fetchone()[0] == 1:
                raise HTTPException(409, "Keep at least one organisation owner")
            for project in body.projects:
                if not c.execute("SELECT 1 FROM projects WHERE tenant_id=? AND id=?", (who["tenant_id"], project)).fetchone():
                    raise HTTPException(404, "Project unavailable")
            c.execute("UPDATE memberships SET role=? WHERE tenant_id=? AND user_id=?", (body.role, who["tenant_id"], user))
            c.execute("DELETE FROM project_access WHERE tenant_id=? AND user_id=?", (who["tenant_id"], user))
            for project in set(body.projects):
                c.execute("INSERT INTO project_access VALUES(?,?,?)", (who["tenant_id"], user, project))
                audit(c, who, "membership.access_updated", project, f"{user}: {old['role']} -> {body.role}")
            audit(c, who, "membership.policy_updated", detail=f"{user}: role and project grants updated")
        return {"updated": True}

    @app.post("/api/projects/{project}/comparisons")
    def run(project: str, who=Depends(identity)):
        permit(who, "run")
        with db() as c:
            project_check(c, who, project)
            records = [dict(r) for r in c.execute("SELECT * FROM documents WHERE tenant_id=? AND project_id=?", (who["tenant_id"], project))]
            result = compare_documents(records)
            result.update(id=str(uuid4()), created=now())
            c.execute("INSERT INTO comparisons VALUES(?,?,?,?,?)", (result["id"], who["tenant_id"], project, result["created"], json.dumps(result)))
            audit(c, who, "comparison.completed", project, "Synthetic register only; no external calls")
        return result

    @app.get("/api/projects/{project}/comparison")
    def latest(project: str, who=Depends(identity)):
        permit(who, "view")
        with db() as c:
            project_check(c, who, project)
            row = c.execute("SELECT result FROM comparisons WHERE tenant_id=? AND project_id=? ORDER BY created DESC LIMIT 1", (who["tenant_id"], project)).fetchone()
        return json.loads(row["result"]) if row else None

    @app.get("/api/projects/{project}/audit")
    def history(project: str, who=Depends(identity)):
        permit(who, "view")
        with db() as c:
            project_check(c, who, project)
            return [dict(r) for r in c.execute("SELECT id,actor,action,detail,created FROM audit WHERE tenant_id=? AND project_id=? ORDER BY created DESC LIMIT 50", (who["tenant_id"], project))]

    class Credential(BaseModel):
        secret: str = Field(min_length=8, max_length=8192)

    @app.put("/api/connections/{connection}/credential")
    def credential(connection: str, body: Credential, who=Depends(identity)):
        permit(who, "connection")
        with db() as c:
            row = c.execute("SELECT project_id FROM connections WHERE id=? AND tenant_id=?", (connection, who["tenant_id"])).fetchone()
            if not row:
                raise HTTPException(404, "Connection not available")
            project_check(c, who, row["project_id"])
            c.execute("UPDATE connections SET secret_ciphertext=?,generation=generation+1 WHERE id=? AND tenant_id=?", (vault.encrypt(body.secret.encode()).decode(), connection, who["tenant_id"]))
            audit(c, who, "credential.replaced", row["project_id"], "Encrypted local development vault; live access disabled")
        return {"credential_present": True, "live_access": False}

    class Proposal(BaseModel):
        source_field: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_. -]+$")
        target_field: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_. -]+$")

    @app.post("/api/projects/{project}/proposals")
    def draft(project: str, body: Proposal, who=Depends(identity)):
        permit(who, "draft")
        payload = json.dumps(body.model_dump(), sort_keys=True)
        item = {"id": str(uuid4()), "payload": body.model_dump(), "digest": hashlib.sha256(payload.encode()).hexdigest(), "status": "pending"}
        with db() as c:
            project_check(c, who, project)
            c.execute("INSERT INTO proposals VALUES(?,?,?,?,?,?,?,NULL)", (item["id"], who["tenant_id"], project, who["user_id"], payload, item["digest"], "pending"))
            audit(c, who, "mapping.proposed", project, item["digest"])
        return item

    @app.get("/api/projects/{project}/proposals")
    def proposals(project: str, who=Depends(identity)):
        with db() as c:
            project_check(c, who, project)
            return [dict(r) for r in c.execute("SELECT id,requested_by,payload,digest,status,approved_by FROM proposals WHERE tenant_id=? AND project_id=?", (who["tenant_id"], project))]

    class Approval(BaseModel):
        digest: str

    @app.post("/api/projects/{project}/proposals/{proposal}/approve")
    def approve(project: str, proposal: str, body: Approval, who=Depends(identity)):
        permit(who, "approve")
        with db() as c:
            project_check(c, who, project)
            row = c.execute("SELECT * FROM proposals WHERE id=? AND tenant_id=? AND project_id=?", (proposal, who["tenant_id"], project)).fetchone()
            if not row:
                raise HTTPException(404, "Proposal unavailable")
            if row["requested_by"] == who["user_id"] or row["status"] != "pending" or not secrets.compare_digest(row["digest"], body.digest):
                raise HTTPException(409, "Approval requires a different actor, pending state and exact preview digest")
            updated = c.execute("UPDATE proposals SET status='approved',approved_by=? WHERE id=? AND tenant_id=? AND project_id=? AND status='pending' AND digest=?", (who["user_id"], proposal, who["tenant_id"], project, body.digest))
            if updated.rowcount != 1:
                raise HTTPException(409, "Proposal changed during approval; reload the preview")
            audit(c, who, "mapping.approved", project, row["digest"])
        return {"status": "approved", "executed": False, "message": "Recorded design approval only; no mapping or vendor write executed"}

    from backend.integrations import register_integrations
    register_integrations(app, db, identity, permit, project_check, audit, now)
    from backend.read_connections import register_read_connections
    register_read_connections(app, db, identity, permit, project_check, audit, vault, now)
    from backend.connection_plans import register_connection_plans
    register_connection_plans(app, db, identity, permit, project_check, audit, now)
    from backend.autodesk_auth import register_autodesk
    register_autodesk(app, db, identity, permit, project_check, audit, vault, now)

    dist = ROOT / "frontend/dist"
    if dist.exists():
        app.mount("/", StaticFiles(directory=dist, html=True), name="portal")
    return app
