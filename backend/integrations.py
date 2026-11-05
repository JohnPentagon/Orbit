"""Versioned synthetic integration configuration; never executes provider operations."""
import hashlib
import json
import secrets
import time
from typing import Literal
from uuid import uuid4

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, model_validator


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(canonical(value).encode()).hexdigest()


class MappingRule(BaseModel):
    source: Literal["number", "title", "revision", "status"]
    target: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z][A-Za-z0-9_.]*$")
    transform: Literal["copy", "trim", "uppercase", "lowercase"] = "copy"
    required: bool = False
    default: str = Field(default="", max_length=250)
    value_map: dict[str, str] = Field(default_factory=dict, max_length=50)


class ProfileConfig(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    source_connection: str
    target_connection: str
    source_scope: str = Field(min_length=1, max_length=250)
    target_scope: str = Field(min_length=1, max_length=250)
    purpose: Literal["comparison", "handover_preview"] = "handover_preview"
    conflict_policy: Literal["review", "skip_existing"] = "review"
    mappings: list[MappingRule] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def unique_targets(self):
        if self.source_connection == self.target_connection:
            raise ValueError("Choose distinct source and target connections")
        if len({r.target for r in self.mappings}) != len(self.mappings):
            raise ValueError("Each target field can only be mapped once")
        if self.purpose == "handover_preview" and not {"number", "title", "revision"}.issubset({r.target for r in self.mappings if r.required}):
            raise ValueError("Synthetic handover profiles require number, title and revision mappings marked required")
        return self


class RevisionRequest(ProfileConfig):
    expected_version: int = Field(ge=1)


class PreviewRequest(BaseModel):
    document_ids: list[str] = Field(min_length=1, max_length=100)


class ApprovalRequest(BaseModel):
    digest: str = Field(min_length=64, max_length=64)


class ConnectionRequest(BaseModel):
    provider: Literal["forma", "redeye"]
    name: str = Field(min_length=1, max_length=100)


def apply_mapping(document, rules):
    values, errors = {}, []
    for rule in rules:
        value = document.get(rule["source"])
        value = rule["default"] if value is None or value == "" else str(value)
        transform = rule["transform"]
        if transform == "trim":
            value = value.strip()
        elif transform == "uppercase":
            value = value.upper()
        elif transform == "lowercase":
            value = value.lower()
        value = rule["value_map"].get(value, value)
        if rule["required"] and not value.strip():
            errors.append(f"Required target field {rule['target']} is missing")
        values[rule["target"]] = value
    return values, errors


def register_integrations(app, db, identity, permit, project_check, audit, now):
    @app.post("/api/projects/{project}/connections")
    def add_connection(project: str, body: ConnectionRequest, who=Depends(identity)):
        permit(who, "connection")
        with db() as c:
            project_check(c, who, project)
            ident = str(uuid4())
            c.execute("INSERT INTO connections(id,tenant_id,project_id,provider,name,status) VALUES(?,?,?,?,?,'synthetic')", (ident, who["tenant_id"], project, body.provider, body.name))
            audit(c, who, "connection.synthetic_created", project, ident)
        return {"id": ident, "live_access": False}

    def connections(c, who, project, config):
        result = []
        for key in ["source_connection", "target_connection"]:
            row = c.execute("SELECT id,provider,status,generation FROM connections WHERE id=? AND tenant_id=? AND project_id=?", (config[key], who["tenant_id"], project)).fetchone()
            if not row:
                raise HTTPException(404, "Connection unavailable in this project")
            if row["provider"] not in {"forma", "redeye"} or row["status"] != "synthetic":
                raise HTTPException(422, "Only synthetic Forma/RedEye adapters support this preview")
            result.append(dict(row))
        return result

    def current(c, who, project, profile):
        project_check(c, who, project)
        row = c.execute("SELECT v.* FROM profile_versions v JOIN integration_profiles p ON p.id=v.profile_id AND p.tenant_id=v.tenant_id AND p.project_id=v.project_id AND p.version=v.version WHERE p.id=? AND p.tenant_id=? AND p.project_id=?", (profile, who["tenant_id"], project)).fetchone()
        if not row:
            raise HTTPException(404, "Integration profile unavailable")
        return dict(row)

    def public_version(row):
        result = dict(row)
        result["configuration"] = json.loads(result["configuration"])
        result["synthetic"] = True
        return result

    @app.get("/api/projects/{project}/profiles")
    def profiles(project: str, who=Depends(identity)):
        permit(who, "view")
        with db() as c:
            project_check(c, who, project)
            rows = c.execute("SELECT v.* FROM profile_versions v JOIN integration_profiles p ON p.id=v.profile_id AND p.version=v.version WHERE p.tenant_id=? AND p.project_id=? ORDER BY v.created DESC", (who["tenant_id"], project)).fetchall()
            return [public_version(r) for r in rows]

    def save(c, who, project, profile, version, config):
        connections(c, who, project, config)
        fingerprint = digest({"tenant": who["tenant_id"], "project": project, "profile": profile, "version": version, "configuration": config})
        c.execute("INSERT INTO profile_versions VALUES(?,?,?,?,?,?,?,'draft',NULL,?)", (profile, who["tenant_id"], project, version, canonical(config), fingerprint, who["user_id"], now()))
        audit(c, who, "profile.version_created", project, f"{profile} v{version}: {fingerprint}")
        return public_version(c.execute("SELECT * FROM profile_versions WHERE profile_id=? AND version=?", (profile, version)).fetchone())

    @app.post("/api/projects/{project}/profiles")
    def create_profile(project: str, body: ProfileConfig, who=Depends(identity)):
        permit(who, "draft")
        with db() as c:
            project_check(c, who, project)
            profile = str(uuid4())
            c.execute("INSERT INTO integration_profiles VALUES(?,?,?,1)", (profile, who["tenant_id"], project))
            return save(c, who, project, profile, 1, body.model_dump())

    @app.post("/api/projects/{project}/profiles/{profile}/versions")
    def revise(project: str, profile: str, body: RevisionRequest, who=Depends(identity)):
        permit(who, "draft")
        with db() as c:
            c.execute("BEGIN IMMEDIATE")
            row = current(c, who, project, profile)
            if row["version"] != body.expected_version:
                raise HTTPException(409, "Profile changed; reload before saving a new version")
            version = row["version"] + 1
            c.execute("UPDATE integration_profiles SET version=? WHERE id=?", (version, profile))
            return save(c, who, project, profile, version, body.model_dump(exclude={"expected_version"}))

    @app.get("/api/projects/{project}/profiles/{profile}/versions")
    def versions(project: str, profile: str, who=Depends(identity)):
        permit(who, "view")
        with db() as c:
            current(c, who, project, profile)
            return [public_version(r) for r in c.execute("SELECT * FROM profile_versions WHERE profile_id=? AND tenant_id=? AND project_id=? ORDER BY version DESC", (profile, who["tenant_id"], project))]

    @app.post("/api/projects/{project}/profiles/{profile}/approve")
    def approve_profile(project: str, profile: str, body: ApprovalRequest, who=Depends(identity)):
        permit(who, "approve")
        with db() as c:
            c.execute("BEGIN IMMEDIATE")
            row = current(c, who, project, profile)
            connections(c, who, project, json.loads(row["configuration"]))
            if row["requested_by"] == who["user_id"] or row["status"] != "draft" or not secrets.compare_digest(row["digest"], body.digest):
                raise HTTPException(409, "Approval needs another actor, current draft and exact digest")
            c.execute("UPDATE profile_versions SET status='approved',approved_by=? WHERE profile_id=? AND version=?", (who["user_id"], profile, row["version"]))
            audit(c, who, "profile.approved", project, row["digest"])
        return {"status": "approved", "executed": False}

    @app.get("/api/projects/{project}/connections/{connection}/documents")
    def documents(project: str, connection: str, who=Depends(identity)):
        permit(who, "view")
        with db() as c:
            project_check(c, who, project)
            if not c.execute("SELECT 1 FROM connections WHERE id=? AND tenant_id=? AND project_id=?", (connection, who["tenant_id"], project)).fetchone():
                raise HTTPException(404, "Connection unavailable")
            return [dict(r) for r in c.execute("SELECT id,number,title,revision,status FROM documents WHERE tenant_id=? AND project_id=? AND connection_id=? ORDER BY number,id", (who["tenant_id"], project, connection))]

    def snapshot(c, who, project, row, selected):
        config = json.loads(row["configuration"])
        pair = connections(c, who, project, config)
        sources = [dict(r) for r in c.execute("SELECT id,number,title,revision,status FROM documents WHERE tenant_id=? AND project_id=? AND connection_id=? ORDER BY id", (who["tenant_id"], project, config["source_connection"]))]
        targets = [dict(r) for r in c.execute("SELECT id,number,title,revision,status FROM documents WHERE tenant_id=? AND project_id=? AND connection_id=? ORDER BY id", (who["tenant_id"], project, config["target_connection"]))]
        chosen = [r for r in sources if r["id"] in selected]
        if len(chosen) != len(set(selected)):
            raise HTTPException(404, "Selected document unavailable in this source connection")
        return {"profile_digest": row["digest"], "connections": pair, "source": chosen, "target": targets}

    @app.post("/api/projects/{project}/profiles/{profile}/handovers")
    def preview(project: str, profile: str, body: PreviewRequest, who=Depends(identity)):
        permit(who, "draft")
        with db() as c:
            row = current(c, who, project, profile)
            config = json.loads(row["configuration"])
            if config["purpose"] != "handover_preview":
                raise HTTPException(422, "Select a handover-preview profile")
            data = snapshot(c, who, project, row, body.document_ids)
            items = []
            for document in data["source"]:
                mapped, errors = apply_mapping(document, config["mappings"])
                if document["status"] != "approved":
                    errors.append("Source is not approved")
                if not document["revision"]:
                    errors.append("Source business revision is missing")
                matches = [t for t in data["target"] if t["number"].strip().casefold() == mapped.get("number", "").strip().casefold()]
                if len(matches) > 1:
                    errors.append("Ambiguous destination identity")
                skipped = bool(matches) and config["conflict_policy"] == "skip_existing"
                if matches and not skipped:
                    errors.append("Destination candidate exists; explicit conflict review required")
                items.append({"source_id": document["id"], "number": document["number"], "title": document["title"], "revision": document["revision"], "mapped_metadata": mapped, "errors": errors, "disposition": "skip" if skipped else "blocked" if errors else "preview_only", "file_evidence": "Not fetched; binary, checksum and historical attachments unverified"})
            blockers = []
            if not any(i["disposition"] == "preview_only" for i in items):
                blockers.append("No eligible document remains after validation and skips")
            if any(i["errors"] for i in items):
                blockers.append("Resolve document validation errors")
            manifest = {"synthetic": True, "profile_id": profile, "profile_version": row["version"], "profile_digest": row["digest"], "configuration": config, "items": items, "blockers": blockers, "scope": "Synthetic current-revision metadata preview only; not a complete handover", "live_transfer": False}
            ident, fingerprint = str(uuid4()), digest(manifest)
            c.execute("INSERT INTO handovers VALUES(?,?,?,?,?,?,?,?,?,'preview',NULL,?,?)", (ident, who["tenant_id"], project, profile, row["version"], canonical(manifest), fingerprint, digest(data), who["user_id"], now(), int(time.time()) + 86400))
            audit(c, who, "handover.preview_created", project, fingerprint)
            return {"id": ident, "manifest": manifest, "digest": fingerprint, "status": "preview"}

    @app.get("/api/projects/{project}/handovers")
    def handovers(project: str, who=Depends(identity)):
        permit(who, "view")
        with db() as c:
            project_check(c, who, project)
            return [{**dict(r), "manifest": json.loads(r["manifest"])} for r in c.execute("SELECT id,profile_id,profile_version,manifest,digest,requested_by,status,approved_by,created,expires FROM handovers WHERE tenant_id=? AND project_id=? ORDER BY created DESC", (who["tenant_id"], project))]

    @app.post("/api/projects/{project}/handovers/{handover}/approve")
    def approve_handover(project: str, handover: str, body: ApprovalRequest, who=Depends(identity)):
        permit(who, "approve")
        with db() as c:
            c.execute("BEGIN IMMEDIATE")
            project_check(c, who, project)
            item = c.execute("SELECT * FROM handovers WHERE id=? AND tenant_id=? AND project_id=?", (handover, who["tenant_id"], project)).fetchone()
            if not item:
                raise HTTPException(404, "Handover unavailable")
            row = current(c, who, project, item["profile_id"])
            manifest = json.loads(item["manifest"])
            if item["requested_by"] == who["user_id"] or item["status"] != "preview" or item["expires"] <= time.time() or row["version"] != item["profile_version"] or row["status"] != "approved" or manifest["blockers"] or not secrets.compare_digest(item["digest"], body.digest):
                raise HTTPException(409, "Approve the current profile, resolve blockers and use an unexpired preview from another actor")
            data = snapshot(c, who, project, row, [i["source_id"] for i in manifest["items"]])
            if digest(data) != item["snapshot_digest"]:
                raise HTTPException(409, "Source, destination or connection changed; create a fresh preview")
            c.execute("UPDATE handovers SET status='approved_preview',approved_by=? WHERE id=?", (who["user_id"], handover))
            audit(c, who, "handover.preview_approved", project, item["digest"])
        return {"status": "approved_preview", "executed": False, "files_transferred": 0}
