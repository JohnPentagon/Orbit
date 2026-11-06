"""Local confidential APS OAuth app and browser-bound, one-use PKCE consent."""
import base64
import hashlib
import json
import logging
import os
import secrets
import time
from typing import Literal
from urllib.parse import urlencode

import httpx
from fastapi import Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field

from backend.providers import ProviderError, read_page

CALLBACK = "http://127.0.0.1:8000/api/autodesk/callback"
TOKEN_URL = "https://developer.api.autodesk.com/authentication/v2/token"
AUTHORIZE_URL = "https://developer.api.autodesk.com/authentication/v2/authorize"


class RedactCallback(logging.Filter):
    def filter(self, record):
        if isinstance(record.args, tuple) and len(record.args) >= 3 and isinstance(record.args[2], str) and "/api/autodesk/callback?" in record.args[2]:
            args = list(record.args)
            args[2] = "/api/autodesk/callback?[REDACTED]"
            record.args = tuple(args)
        return True


def token_request(client_id, client_secret, data, transport=None):
    """Fixed vendor endpoint; never returns provider errors or logs secret material."""
    try:
        with httpx.Client(transport=transport, follow_redirects=False, timeout=15, trust_env=True) as client:
            with client.stream("POST", TOKEN_URL, auth=httpx.BasicAuth(client_id, client_secret), data=data, headers={"Accept": "application/json"}) as response:
                if response.status_code != 200:
                    raise ProviderError("token_rejected", "Autodesk rejected authorisation; check app settings, consent and provisioning")
                chunks, size = [], 0
                for part in response.iter_bytes():
                    size += len(part)
                    if size > 100_000:
                        raise ProviderError("token_response_invalid", "Unexpected Autodesk token response")
                    chunks.append(part)
                payload = json.loads(b"".join(chunks))
        access, expiry = payload.get("access_token"), payload.get("expires_in")
        refresh = payload.get("refresh_token", "")
        if not isinstance(access, str) or not 8 <= len(access) <= 8192 or any(c in access for c in "\r\n") or not isinstance(expiry, int) or isinstance(expiry, bool) or not 0 < expiry <= 86400 or not isinstance(refresh, str) or len(refresh) > 8192 or any(c in refresh for c in "\r\n"):
            raise ProviderError("token_response_invalid", "Unexpected Autodesk token response")
        if payload.get("token_type", "Bearer").lower() != "bearer":
            raise ProviderError("token_response_invalid", "Unexpected Autodesk token type")
        return {"access_token": access, "refresh_token": refresh, "expires": int(time.time()) + expiry}
    except (httpx.HTTPError, ValueError, AttributeError):
        raise ProviderError("token_exchange_failed", "Autodesk authorisation could not be completed; no token details returned")


class AppSettings(BaseModel):
    client_id: str = Field(min_length=5, max_length=200, pattern=r"^[A-Za-z0-9_.-]+$")
    client_secret: str = Field(min_length=8, max_length=8192)
    mode: Literal["three_legged", "two_legged"] = "three_legged"


class Discovery(BaseModel):
    kind: Literal["hubs", "projects", "folders"]
    hub: str = Field(default="", max_length=500)
    project: str = Field(default="", max_length=500)
    page: int = Field(default=0, ge=0, le=39)


class Selection(BaseModel):
    hub: str = Field(min_length=1, max_length=500)
    project: str = Field(min_length=1, max_length=500)
    folder: str = Field(default="", max_length=500)


def register_autodesk(app, db, identity, permit, project_check, audit, vault, now):
    logger = logging.getLogger("uvicorn.access")
    if not any(isinstance(item, RedactCallback) for item in logger.filters):
        logger.addFilter(RedactCallback())

    def scoped(c, who, project, connection):
        membership = c.execute("SELECT role FROM memberships WHERE tenant_id=? AND user_id=?", (who["tenant_id"], who["user_id"])).fetchone()
        if not membership:
            raise HTTPException(403, "Membership unavailable")
        permit({**who, "role": membership[0]}, "connection")
        project_check(c, who, project)
        row = c.execute("SELECT * FROM read_connections WHERE id=? AND tenant_id=? AND project_id=? AND provider='forma'", (connection, who["tenant_id"], project)).fetchone()
        if not row:
            raise HTTPException(404, "Autodesk connection unavailable")
        return dict(row)

    def gate(row):
        cfg = json.loads(row["configuration"])
        if os.getenv("ORBIT_ENABLE_LIVE_READS") != "1" or not cfg["approved_test_access"] or not cfg["vendor_settings_confirmed"] or not cfg["evidence_note"].strip():
            raise HTTPException(409, "Enable local live reads and confirm the approved Autodesk test access/settings first")

    def save_tokens(c, connection, tokens):
        c.execute("INSERT INTO autodesk_tokens VALUES(?,?) ON CONFLICT(connection_id) DO UPDATE SET tokens_ciphertext=excluded.tokens_ciphertext", (connection, vault.encrypt(json.dumps(tokens).encode()).decode()))
        c.execute("UPDATE read_connections SET secret_ciphertext=?,generation=generation+1,last_result=NULL WHERE id=?", (vault.encrypt(tokens["access_token"].encode()).decode(), connection))
        c.execute("DELETE FROM autodesk_choices WHERE connection_id=?", (connection,))

    def credentials(c, connection):
        row = c.execute("SELECT * FROM autodesk_apps WHERE connection_id=?", (connection,)).fetchone()
        if not row:
            raise HTTPException(409, "Save your APS application settings first")
        return row["client_id"], vault.decrypt(row["client_secret_ciphertext"].encode()).decode(), row["mode"]

    @app.get("/api/projects/{project}/read-connections/{connection}/autodesk")
    def status(project: str, connection: str, who=Depends(identity)):
        permit(who, "connection")
        with db() as c:
            scoped(c, who, project, connection)
            settings = c.execute("SELECT client_id,mode FROM autodesk_apps WHERE connection_id=?", (connection,)).fetchone()
            token = c.execute("SELECT tokens_ciphertext FROM autodesk_tokens WHERE connection_id=?", (connection,)).fetchone()
            tokens = json.loads(vault.decrypt(token[0].encode())) if token else {}
        return {"callback_url": CALLBACK, "app": dict(settings) if settings else None, "expires": tokens.get("expires"), "renewal_available": bool(tokens.get("refresh_token")) or (settings is not None and settings["mode"] == "two_legged"), "scope": "data:read"}

    @app.put("/api/projects/{project}/read-connections/{connection}/autodesk")
    def configure(project: str, connection: str, body: AppSettings, who=Depends(identity)):
        permit(who, "connection")
        if any(ch in body.client_secret for ch in "\r\n"):
            raise HTTPException(422, "Client secret must not contain line breaks")
        with db() as c:
            scoped(c, who, project, connection)
            c.execute("INSERT INTO autodesk_apps VALUES(?,?,?,?) ON CONFLICT(connection_id) DO UPDATE SET client_id=excluded.client_id,client_secret_ciphertext=excluded.client_secret_ciphertext,mode=excluded.mode", (connection, body.client_id, vault.encrypt(body.client_secret.encode()).decode(), body.mode))
            c.execute("DELETE FROM autodesk_tokens WHERE connection_id=?", (connection,))
            c.execute("DELETE FROM autodesk_states WHERE connection_id=?", (connection,))
            c.execute("DELETE FROM autodesk_choices WHERE connection_id=?", (connection,))
            c.execute("UPDATE read_connections SET secret_ciphertext=NULL,generation=generation+1,last_result=NULL WHERE id=?", (connection,))
            audit(c, who, "autodesk.app_configured", project, connection)
        return {"configured": True, "callback_url": CALLBACK}

    @app.post("/api/projects/{project}/read-connections/{connection}/autodesk/connect")
    def connect(project: str, connection: str, request: Request, who=Depends(identity)):
        permit(who, "connection")
        with db() as c:
            c.execute("BEGIN IMMEDIATE")
            row = scoped(c, who, project, connection)
            gate(row)
            client_id, secret, mode = credentials(c, connection)
            if mode == "three_legged":
                if str(request.base_url).rstrip("/") != "http://127.0.0.1:8000":
                    raise HTTPException(409, "Open ORBIT at http://127.0.0.1:8000 to use the registered local callback")
                state, browser, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(48)
                challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
                session_hash = hashlib.sha256(request.cookies.get("orbit_session", "").encode()).hexdigest()
                c.execute("DELETE FROM autodesk_states WHERE connection_id=? OR expires<?", (connection, int(time.time())))
                c.execute("INSERT INTO autodesk_states VALUES(?,?,?,?,?,?,?,?,?,?)", (hashlib.sha256(state.encode()).hexdigest(), connection, who["tenant_id"], project, who["user_id"], session_hash, hashlib.sha256(browser.encode()).hexdigest(), vault.encrypt(verifier.encode()).decode(), row["generation"], int(time.time()) + 600))
                from fastapi.responses import JSONResponse
                response = JSONResponse({"authorize_url": AUTHORIZE_URL + "?" + urlencode({"client_id": client_id, "response_type": "code", "redirect_uri": CALLBACK, "scope": "data:read", "state": state, "code_challenge": challenge, "code_challenge_method": "S256"})})
                response.set_cookie("orbit_oauth", browser, httponly=True, samesite="lax", max_age=600, path="/api/autodesk/callback")
                audit(c, who, "autodesk.consent_started", project, connection)
                return response
            try:
                tokens = token_request(client_id, secret, {"grant_type": "client_credentials", "scope": "data:read"})
            except ProviderError as e:
                raise HTTPException(502, e.message)
            save_tokens(c, connection, tokens)
            audit(c, who, "autodesk.application_token_obtained", project, connection)
        return {"connected": True, "expires": tokens["expires"], "permission_claim": "Token obtained; resource access remains unverified"}

    @app.delete("/api/projects/{project}/read-connections/{connection}/autodesk")
    def disconnect(project: str, connection: str, who=Depends(identity)):
        permit(who, "connection")
        with db() as c:
            scoped(c, who, project, connection)
            for table in ["autodesk_apps", "autodesk_tokens", "autodesk_states", "autodesk_choices"]:
                c.execute(f"DELETE FROM {table} WHERE connection_id=?", (connection,))
            c.execute("UPDATE read_connections SET secret_ciphertext=NULL,generation=generation+1,last_result=NULL WHERE id=?", (connection,))
            audit(c, who, "autodesk.disconnected_locally", project, connection)
        return {"disconnected_locally": True, "vendor_revoked": False}

    @app.get("/api/autodesk/callback")
    def callback(request: Request):
        result = "failed"
        saved = None
        try:
            state = request.query_params.get("state", "")
            with db() as c:
                c.execute("BEGIN IMMEDIATE")
                row = c.execute("SELECT * FROM autodesk_states WHERE state_hash=?", (hashlib.sha256(state.encode()).hexdigest(),)).fetchone()
                if not row:
                    raise HTTPException(409)
                # Consume before any network exchange; retries require a new consent flow.
                c.execute("DELETE FROM autodesk_states WHERE state_hash=?", (row["state_hash"],))
                saved = dict(row)
            if saved["expires"] <= time.time() or not secrets.compare_digest(saved["browser_hash"], hashlib.sha256(request.cookies.get("orbit_oauth", "").encode()).hexdigest()) or request.query_params.get("error") or not request.query_params.get("code"):
                raise HTTPException(409)
            with db() as c:
                c.execute("BEGIN IMMEDIATE")
                session = c.execute("SELECT s.user_id,s.tenant_id,m.role FROM sessions s JOIN memberships m ON m.tenant_id=s.tenant_id AND m.user_id=s.user_id WHERE token_hash=? AND expires>?", (saved["session_hash"], int(time.time()))).fetchone()
                if not session or session["user_id"] != saved["user_id"] or session["tenant_id"] != saved["tenant_id"]:
                    raise HTTPException(409)
                who = dict(session)
                permit(who, "connection")
                row = scoped(c, who, saved["project_id"], saved["connection_id"])
                gate(row)
                if row["generation"] != saved["generation"]:
                    raise HTTPException(409)
                client_id, secret, mode = credentials(c, saved["connection_id"])
                if mode != "three_legged":
                    raise HTTPException(409)
                tokens = token_request(client_id, secret, {"grant_type": "authorization_code", "code": request.query_params["code"], "redirect_uri": CALLBACK, "code_verifier": vault.decrypt(saved["verifier_ciphertext"].encode()).decode()})
                save_tokens(c, saved["connection_id"], tokens)
                audit(c, who, "autodesk.consent_completed", saved["project_id"], saved["connection_id"])
            result = "connected"
        except (HTTPException, ProviderError) as error:
            if saved:
                with db() as c:
                    audit(c, {"tenant_id": saved["tenant_id"], "user_id": saved["user_id"]}, "autodesk.consent_failed", saved["project_id"], error.code if isinstance(error, ProviderError) else "consent_rejected")
        response = RedirectResponse("/?autodesk=" + result, status_code=303)
        response.delete_cookie("orbit_oauth", path="/api/autodesk/callback")
        response.headers["Referrer-Policy"] = "no-referrer"
        return response

    @app.post("/api/projects/{project}/read-connections/{connection}/autodesk/renew")
    def renew(project: str, connection: str, who=Depends(identity)):
        permit(who, "connection")
        with db() as c:
            c.execute("BEGIN IMMEDIATE")
            row = scoped(c, who, project, connection)
            gate(row)
            client_id, secret, mode = credentials(c, connection)
            stored = c.execute("SELECT tokens_ciphertext FROM autodesk_tokens WHERE connection_id=?", (connection,)).fetchone()
            old = json.loads(vault.decrypt(stored[0].encode())) if stored else {}
            if mode == "three_legged" and not old.get("refresh_token"):
                raise HTTPException(409, "Sign in again; no refresh token is available")
            data = {"grant_type": "client_credentials", "scope": "data:read"} if mode == "two_legged" else {"grant_type": "refresh_token", "refresh_token": old["refresh_token"]}
            try:
                tokens = token_request(client_id, secret, data)
            except ProviderError as e:
                raise HTTPException(502, e.message)
            if mode == "three_legged" and not tokens["refresh_token"]:
                tokens["refresh_token"] = old["refresh_token"]
            save_tokens(c, connection, tokens)
            audit(c, who, "autodesk.token_renewed", project, connection)
        return {"expires": tokens["expires"], "renewed": True}

    def choice(c, row, kind, parent, selected):
        cache = c.execute("SELECT * FROM autodesk_choices WHERE connection_id=? AND kind=? AND parent=? AND generation=? AND expires>?", (row["id"], kind, parent, row["generation"], int(time.time()))).fetchone()
        found = next((r for r in json.loads(cache["resources"]) if r["id"] == selected), None) if cache else None
        if not found:
            raise HTTPException(409, "Refresh discovery and select an authorised resource from its current list")
        return found

    @app.post("/api/projects/{project}/read-connections/{connection}/autodesk/discover")
    def discover(project: str, connection: str, body: Discovery, who=Depends(identity)):
        permit(who, "connection")
        with db() as c:
            row = scoped(c, who, project, connection)
            gate(row)
            c.execute("DELETE FROM autodesk_choices WHERE expires<?", (int(time.time()),))
            if not row["secret_ciphertext"]:
                raise HTTPException(409, "Authorise Autodesk first")
            if body.kind != "hubs":
                choice(c, row, "hubs", "", body.hub)
            if body.kind == "folders":
                choice(c, row, "projects", body.hub, body.project)
            if body.page and body.kind != "projects":
                raise HTTPException(422, "Paging is supported for the documented project-list resource only")
            secret = vault.decrypt(row["secret_ciphertext"].encode()).decode()
        try:
            result = read_page("forma", "https://developer.api.autodesk.com", secret, body.kind, body.model_dump())
        except ProviderError as e:
            raise HTTPException(502, e.message)
        parent = "" if body.kind == "hubs" else body.hub if body.kind == "projects" else json.dumps([body.hub, body.project])
        with db() as c:
            current = scoped(c, who, project, connection)
            membership = c.execute("SELECT role FROM memberships WHERE tenant_id=? AND user_id=?", (who["tenant_id"], who["user_id"])).fetchone()
            if not membership:
                raise HTTPException(403, "Membership changed")
            permit({**who, "role": membership[0]}, "connection")
            if current["generation"] != row["generation"]:
                raise HTTPException(409, "Authorisation changed; refresh discovery")
            resources = result["resources"]
            if body.page:
                previous = c.execute("SELECT resources FROM autodesk_choices WHERE connection_id=? AND kind=? AND parent=? AND generation=? AND expires>?", (connection, body.kind, parent, row["generation"], int(time.time()))).fetchone()
                if not previous:
                    raise HTTPException(409, "Start project discovery again; the previous list expired")
                resources = list({r["id"]: r for r in json.loads(previous[0]) + resources}.values())
                if len(resources) > 1000:
                    raise HTTPException(409, "Discovery reached the local 1,000-project limit")
            c.execute("INSERT INTO autodesk_choices VALUES(?,?,?,?,?,?) ON CONFLICT(connection_id,kind,parent) DO UPDATE SET resources=excluded.resources,generation=excluded.generation,expires=excluded.expires", (connection, body.kind, parent, json.dumps(resources), row["generation"], int(time.time()) + 600))
            audit(c, who, "autodesk.resources_discovered", project, f"{connection}: {body.kind}; bounded first page")
        return {**result, "synthetic": False}

    @app.put("/api/projects/{project}/read-connections/{connection}/autodesk/selection")
    def select(project: str, connection: str, body: Selection, who=Depends(identity)):
        permit(who, "connection")
        with db() as c:
            c.execute("BEGIN IMMEDIATE")
            row = scoped(c, who, project, connection)
            gate(row)
            hub = choice(c, row, "hubs", "", body.hub)
            selected_project = choice(c, row, "projects", body.hub, body.project)
            folder = choice(c, row, "folders", json.dumps([body.hub, body.project]), body.folder) if body.folder else None
            cfg = json.loads(row["configuration"])
            cfg.update(hub=body.hub, vendor_project=body.project, folder=body.folder, hub_label=hub["label"], project_label=selected_project["label"], folder_label=folder["label"] if folder else "")
            c.execute("UPDATE read_connections SET configuration=?,generation=generation+1,last_result=NULL WHERE id=?", (json.dumps(cfg), connection))
            c.execute("DELETE FROM autodesk_choices WHERE connection_id=?", (connection,))
            audit(c, who, "autodesk.scope_selected", project, connection)
        return {"saved": True, "hub": hub["label"], "project": selected_project["label"], "folder": folder["label"] if folder else None}
