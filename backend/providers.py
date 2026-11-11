"""Bounded read-only HTTP adapters. Tests inject httpx.MockTransport."""
import ipaddress
import re
from urllib.parse import quote, urlsplit

import httpx


class ProviderError(Exception):
    def __init__(self, code, message):
        self.code, self.message = code, message
        super().__init__(message)


def resource_collection(provider, operation, payload):
    """Explicit, evidenced envelopes; never turn a missing key into an empty list."""
    if provider == "forma":
        keys = ["data"]
    elif operation == "artefacts":
        keys = ["results", "items"]  # Official example versus owner-supplied DTO.
    elif operation in {"groups", "metadata_keys"}:
        if isinstance(payload, list):
            return payload, "raw_array"
        keys = ["items"]
    else:
        raise ProviderError("unsupported_operation", "Resource contract not implemented")
    matches = [key for key in keys if isinstance(payload, dict) and key in payload]
    if len(matches) != 1 or not isinstance(payload[matches[0]], list):
        raise ProviderError("contract_mismatch", "Response has a missing, invalid or ambiguous resource-list envelope")
    return payload[matches[0]], matches[0]


def approved_base(provider, base, allowed_hosts):
    try:
        parsed = urlsplit(base)
    except ValueError:
        raise ProviderError("invalid_host", "Invalid server URL")
    host = (parsed.hostname or "").lower()
    try:
        port = parsed.port
    except ValueError:
        raise ProviderError("invalid_host", "Invalid server port")
    if parsed.scheme != "https" or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in {"", "/"} or port not in {None, 443}:
        raise ProviderError("invalid_host", "Use an HTTPS vendor hostname without a path, credentials or custom port")
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise ProviderError("invalid_host", "IP-address destinations are not supported")
    # QA comes from official docs; api.redeyedms.com comes from the owner's reference client.
    allowed = {"developer.api.autodesk.com"} if provider == "forma" else {"qa-api.redeyedms.com", "api.redeyedms.com", *allowed_hosts}
    if host not in allowed or not re.fullmatch(r"[a-z0-9]+(?:[.-][a-z0-9]+)*", host):
        raise ProviderError("host_not_allowed", "Vendor host is not in the operator's exact-host allowlist")
    return "https://" + host


def auth_headers(provider, secret, header="", prefix=""):
    if not secret or any(c in secret for c in "\r\n"):
        raise ProviderError("invalid_credential", "Supply a nonempty credential without line breaks")
    if provider == "forma":
        return {"Authorization": "Bearer " + secret, "Accept": "application/json"}
    forbidden = {"host", "cookie", "set-cookie", "connection", "accept", "user-agent", "content-length", "transfer-encoding"}
    if not re.fullmatch(r"[A-Za-z][A-Za-z0-9-]{0,63}", header) or header.lower() in forbidden or header.lower().startswith(("proxy-", "content-", "sec-")) or prefix not in {"", "Bearer"}:
        raise ProviderError("invalid_header", "Use the vendor-confirmed credential header and optional Bearer prefix")
    return {header: (prefix + " " if prefix else "") + secret, "Accept": "application/json"}


def read_page(provider, base, secret, operation, scope, header="", prefix="", transport=None):
    encode = lambda value: quote(value, safe="")
    params = {}
    if provider == "forma":
        if operation == "hubs":
            path = "/project/v1/hubs"
        elif operation == "projects" and scope.get("hub"):
            path = f"/project/v1/hubs/{encode(scope['hub'])}/projects"
            params = {"page[limit]": 25, "page[number]": scope.get("page", 0)}
        elif operation == "folders" and scope.get("hub") and scope.get("project"):
            path = f"/project/v1/hubs/{encode(scope['hub'])}/projects/{encode(scope['project'])}/topFolders"
        elif operation == "documents" and scope.get("project") and scope.get("folder"):
            path = f"/data/v1/projects/{encode(scope['project'])}/folders/{encode(scope['folder'])}/contents"
            params = {"page[limit]": 25}
        else:
            raise ProviderError("scope_required", "Choose a supported operation and its required hub/project/folder IDs")
    elif provider == "redeye" and operation in {"artefacts", "groups", "metadata_keys"}:
        path = {"artefacts": "/api/v1/artefacts", "groups": "/api/v1/groups", "metadata_keys": "/api/v1/metadata-keys"}[operation]
        params = {"limit": 25} if operation == "artefacts" else {}
    else:
        raise ProviderError("unsupported_operation", "This adapter does not implement that resource")
    headers = auth_headers(provider, secret, header, prefix)
    try:
        with httpx.Client(transport=transport, timeout=httpx.Timeout(15, connect=5), follow_redirects=False, trust_env=True) as client:
            with client.stream("GET", base + path, params=params, headers=headers) as response:
                if response.status_code in {401, 403}:
                    raise ProviderError("access_denied", "Credential or resource permission was rejected; no data imported")
                if response.status_code == 429:
                    raise ProviderError("rate_limited", "Provider rate limit reached; retry later")
                if response.status_code in range(300, 400):
                    raise ProviderError("redirect_refused", "Provider redirected the request; verify the approved base URL")
                if response.status_code != 200:
                    raise ProviderError("provider_error", "Provider did not return a successful read response")
                chunks, size = [], 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > 1_000_000:
                        raise ProviderError("response_too_large", "Provider response exceeds the bounded test-read limit")
                    chunks.append(chunk)
                import json
                data = json.loads(b"".join(chunks))
    except (httpx.HTTPError, ValueError):
        raise ProviderError("read_failed", "Provider response could not be read; verify network access and contract")
    collection, response_shape = resource_collection(provider, operation, data)
    from backend.record_data import fields
    resources = []
    for item in collection[:25]:
        if not isinstance(item, dict) or not isinstance(item.get("id"), (str, int)) or isinstance(item.get("id"), bool):
            raise ProviderError("contract_mismatch", "Resource identity is missing or has an unsupported shape")
        attributes = item.get("attributes", {}) if provider == "forma" else item
        if not isinstance(attributes, dict):
            raise ProviderError("contract_mismatch", "Resource attributes have an unsupported shape")
        label = attributes.get("displayName") or attributes.get("title") or attributes.get("name") or attributes.get("number") or "Unnamed resource"
        if not isinstance(label, str):
            raise ProviderError("contract_mismatch", "Resource label is not text")
        redact = lambda value: str(value).replace(secret, "[REDACTED]")
        kind = {"groups": "group", "metadata_keys": "metadata_key"}.get(operation, "artefact")
        resources.append({"id": redact(item["id"])[:500], "label": redact(label)[:250], "kind": redact(item.get("type", kind))[:100], "fields": fields({k:v for k,v in item.items() if k not in {"links","relationships"}}, secret)})
    return {"operation": operation, "resources": resources, "returned": len(resources), "response_shape": response_shape, "coverage": "Bounded sample: at most 25 resources; not a complete register", "imported": 0, "files_transferred": 0}


FIXTURES = {
    "forma": {"data": [{"id": "SYNTHETIC-HUB-001", "type": "hubs", "attributes": {"name": "Synthetic Autodesk hub"}}]},
    "redeye": {"results": [{"id": 1001, "name": "Synthetic controlled drawing", "number": "SYNTHETIC-001", "type": "drawing"}], "total": 1, "offset": 0, "limit": 25},
    "redeye:groups": [{"id": 501, "name": "SYNTHETIC group"}],
    "redeye:metadata_keys": {"items": [{"id": 601, "name": "SYNTHETIC Document Number", "description": "Synthetic metadata definition"}]},
}
