"""Project-scoped commissioning records. These routes never contact a provider."""
import json
from typing import Literal
from urllib.parse import urlsplit
from uuid import uuid4

from fastapi import Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator

MERIDIAN_HELP = "https://help.accruent.com/meridianenterprise/Content/Online_Help/"
COMMON_CHECKS = [
    ("access", "Administrator confirms licensed API access and an authorised test scope"),
    ("identity", "Authentication and least-privilege service/user identity verified"),
    ("network", "DNS, HTTPS certificate trust and approved network route verified from the executor"),
    ("scope", "Allowed resources visible; denied resources remain inaccessible"),
    ("paging", "Pagination, empty results, rate limits and expired credentials tested"),
    ("mapping", "Document identity, revisions, metadata types and missing values reviewed"),
]
CATALOGUE = {
    "meridian": {
        "name": "Meridian Enterprise / PowerWeb", "stage": "Preparation only — no live adapter",
        "summary": "PowerWeb is an IIS-hosted Enterprise client. Select a documented integration interface separately; a PowerWeb URL is not an API base URL.",
        "interfaces": ["Undecided", "Explorer Web API (read)", "Meridian API Service (Mobile)", ".NET / Connection API", "Meridian Portal / Cloud (separate product)"],
        "checks": [("edition", "Confirm Enterprise versus Portal/Cloud, installed release (2024+) and patch"), ("interface", "Administrator supplies version-matched interface documentation and installed API URL"), ("repository", "Confirm vault/repository/view mapping and Explorer synchronisation freshness"), ("auth_contract", "Confirm API login/token or Windows identity contract; browser SSO is not assumed reusable"), ("health", "Administrator validates documented API health route where applicable"), *COMMON_CHECKS],
        "sources": [{"label": "PowerWeb architecture", "url": MERIDIAN_HELP + "AdminGuide/Architecture/PowerWeb.htm"}, {"label": "Explorer Web API", "url": MERIDIAN_HELP + "Enterprise_Server/Explorer/WebAPI/Web_API_reference.htm"}, {"label": "API Service installation", "url": MERIDIAN_HELP + "AdminGuide/Installation/MeridianAPI_Service_Install.htm"}, {"label": ".NET / Connection API documentation", "url": MERIDIAN_HELP + "Common/API_LandingPage.htm"}],
    },
    "procore": {
        "name": "Procore", "stage": "Preparation only — no live adapter",
        "summary": "Confirm the approved developer application, OAuth flow, company/project permissions and sandbox before implementing discovery.",
        "interfaces": ["Undecided", "Procore REST API"],
        "checks": [("application", "Developer app, redirect URI and sandbox/customer installation confirmed"), ("company", "Company and project scope, document permissions and API entitlements confirmed"), *COMMON_CHECKS],
        "sources": [{"label": "Official developer documentation", "url": "https://developers.procore.com/documentation/introduction"}],
    },
    "maintenance_connection": {
        "name": "Accruent Maintenance Connection", "stage": "Preparation only — no live adapter",
        "summary": "Separate product from Meridian. Establish hosted/on-premises edition, licensed API contract and asset/document relationships with the administrator.",
        "interfaces": ["Undecided", "Administrator-confirmed API"],
        "checks": [("edition", "Hosted/on-premises edition, release and licensed API documentation confirmed"), ("assets", "Asset identifiers and document/attachment relationships reviewed"), *COMMON_CHECKS],
        "sources": [],
    },
    "forma": {
        "name": "Forma / ACC document management", "stage": "Bounded read adapter — customer OAuth tests pending",
        "summary": "Use Read connections for Autodesk sign-in and named hub/project selection. This checklist records testing; it does not configure credentials.",
        "interfaces": ["APS Data Management / ACC Docs"],
        "checks": [("consent", "Three-legged consent, callback and named hub/project/folder selection tested"), ("renewal", "Token renewal, disconnect, revocation and denied-project behaviour tested"), *COMMON_CHECKS],
        "sources": [{"label": "ACC API introduction", "url": "https://aps.autodesk.com/en/docs/acc/v1/overview/introduction/"}],
    },
    "redeye": {
        "name": "RedEye DMS", "stage": "Bounded read adapter — initial reads reported successful",
        "summary": "Artefact, group and metadata-key reads were reported successful by the owner. Record that evidence against the applicable local connection; new plans start untested.",
        "interfaces": ["RedEye DMS API"],
        "checks": [("artefacts", "Read artefacts succeeds against the intended environment"), ("groups", "Read groups succeeds"), ("metadata_keys", "Read metadata keys succeeds"), ("group_filter", "Prove group filtering excludes unrelated artefacts; listing groups alone does not prove isolation"), *COMMON_CHECKS],
        "sources": [{"label": "Official API documentation", "url": "https://api.redeyedms.com/#redeye-dms-api"}],
    },
}


class CheckResult(BaseModel):
    model_config = ConfigDict(extra="forbid")
    status: Literal["untested", "passed", "failed", "blocked", "not_applicable"] = "untested"
    evidence: str = Field(default="", max_length=1000)


class Plan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=100)
    provider: Literal["meridian", "procore", "maintenance_connection", "forma", "redeye"]
    product_version: str = Field(default="", max_length=100)
    deployment: Literal["undecided", "cloud", "on_premises", "hybrid"] = "undecided"
    interface: str = Field(default="Undecided", max_length=100)
    execution: Literal["undecided", "local_network", "private_route", "outbound_worker", "public_https"] = "undecided"
    service_url: str = Field(default="", max_length=500)
    scope_note: str = Field(default="", max_length=1000)
    auth_note: str = Field(default="", max_length=1000)
    network_note: str = Field(default="", max_length=1000)
    checks: dict[str, CheckResult] = Field(default_factory=dict, max_length=30)

    @field_validator("name")
    @classmethod
    def name_nonempty(cls, value):
        if not value.strip():
            raise ValueError("Enter a connection plan name")
        return value.strip()

    @field_validator("service_url")
    @classmethod
    def safe_url(cls, value):
        if not value:
            return value
        try:
            url = urlsplit(value)
            if url.scheme != "https" or not url.hostname or url.username or url.password or url.query or url.fragment or any(c.isspace() for c in value):
                raise ValueError()
            _ = url.port
        except ValueError:
            raise ValueError("Use an HTTPS URL without credentials, query parameters or fragments; this is a reference only")
        return value


class Revision(Plan):
    version: int = Field(ge=1)


def register_connection_plans(app, db, identity, permit, project_check, audit, now):
    def validate(body):
        definition = CATALOGUE[body.provider]
        if body.interface not in definition["interfaces"]:
            raise HTTPException(422, "Choose an interface listed for this provider")
        if set(body.checks) - {key for key, _ in definition["checks"]}:
            raise HTTPException(422, "Unknown checklist item for this provider")
        if any(item.status != "untested" and not item.evidence.strip() for item in body.checks.values()):
            raise HTTPException(422, "Record non-secret evidence or a reason for each completed, failed, blocked or inapplicable check")

    @app.get("/api/projects/{project}/connection-plans")
    def listing(project: str, who=Depends(identity)):
        permit(who, "view")
        with db() as c:
            project_check(c, who, project)
            rows = c.execute("SELECT * FROM connection_plans WHERE tenant_id=? AND project_id=? ORDER BY updated DESC,id", (who["tenant_id"], project)).fetchall()
        return {"catalogue": CATALOGUE, "plans": [{"id": r["id"], "version": r["version"], "updated": r["updated"], "updated_by": r["updated_by"], "configuration": json.loads(r["configuration"])} for r in rows], "live_adapter_enabled": False, "evidence_type": "Manual tester records; not automatic verification"}

    @app.post("/api/projects/{project}/connection-plans")
    def create(project: str, body: Plan, who=Depends(identity)):
        permit(who, "connection")
        validate(body)
        ident = str(uuid4())
        with db() as c:
            project_check(c, who, project)
            c.execute("INSERT INTO connection_plans VALUES(?,?,?,?,?,?,1,?,?)", (ident, who["tenant_id"], project, body.provider, body.name, body.model_dump_json(), now(), who["user_id"]))
            audit(c, who, "connection_plan.created", project, ident)
        return {"id": ident, "version": 1}

    @app.post("/api/projects/{project}/connection-plans/{ident}/fixture-check")
    def fixture(project: str, ident: str, who=Depends(identity)):
        permit(who, "connection")
        with db() as c:
            project_check(c, who, project)
            row = c.execute("SELECT provider FROM connection_plans WHERE id=? AND tenant_id=? AND project_id=?", (ident, who["tenant_id"], project)).fetchone()
            if not row:
                raise HTTPException(404, "Connection plan unavailable")
            if row["provider"] != "meridian":
                raise HTTPException(422, "This offline contract preview is for Meridian Explorer only")
            from backend.meridian import EXPLORER_FIXTURE, explorer_documents
            result = explorer_documents(EXPLORER_FIXTURE)
            audit(c, who, "connection_plan.fixture_checked", project, ident)
        return {**result, "synthetic": True, "note": "Hand-authored Explorer contract fixture. No network request, authentication test or saved checklist change."}

    @app.put("/api/projects/{project}/connection-plans/{ident}")
    def update(project: str, ident: str, body: Revision, who=Depends(identity)):
        permit(who, "connection")
        validate(body)
        with db() as c:
            project_check(c, who, project)
            row = c.execute("SELECT * FROM connection_plans WHERE id=? AND tenant_id=? AND project_id=?", (ident, who["tenant_id"], project)).fetchone()
            if not row:
                raise HTTPException(404, "Connection plan unavailable")
            if body.provider != row["provider"]:
                raise HTTPException(422, "Create a separate plan for another provider")
            previous = json.loads(row["configuration"])
            fields = ("product_version", "deployment", "interface", "execution", "service_url", "scope_note", "auth_note", "network_note")
            checks_reset = any(previous.get(key) != getattr(body, key) for key in fields)
            configuration = body.model_dump(exclude={"version"})
            if checks_reset:
                configuration["checks"] = {}
            result = c.execute("UPDATE connection_plans SET name=?,configuration=?,version=version+1,updated=?,updated_by=? WHERE id=? AND version=?", (body.name, json.dumps(configuration), now(), who["user_id"], ident, body.version))
            if not result.rowcount:
                raise HTTPException(409, "This plan changed. Reload before saving your revision.")
            audit(c, who, "connection_plan.updated", project, ident)
        return {"id": ident, "version": body.version + 1, "checks_reset": checks_reset}
