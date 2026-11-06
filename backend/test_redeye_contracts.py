"""Hand-authored examples based on the owner's DTOs; not captured live payloads."""
import httpx
import pytest
from fastapi.testclient import TestClient

from backend.main import create_app
from backend.providers import ProviderError, read_page


def read(operation, payload):
    requests = []
    def handler(request):
        requests.append(request)
        return httpx.Response(200, json=payload)
    result = read_page("redeye", "https://api.redeyedms.com", "synthetic-reference-key", operation, {}, "Authorization", "Bearer", transport=httpx.MockTransport(handler))
    return result, requests


@pytest.mark.parametrize("key", ["items", "results"])
def test_artefact_envelopes_preserve_title_and_report_shape(key):
    result, requests = read("artefacts", {key: [{"id": 12, "title": "Controlled drawing", "number": "DR-001", "type": "drawing"}]})
    assert result["response_shape"] == key and result["resources"][0]["label"] == "Controlled drawing"
    assert requests[0].url.path == "/api/v1/artefacts" and requests[0].method == "GET"
    assert requests[0].headers["authorization"] == "Bearer synthetic-reference-key"
    assert result["files_transferred"] == 0


@pytest.mark.parametrize("operation,path", [("groups","/api/v1/groups"),("metadata_keys","/api/v1/metadata-keys")])
@pytest.mark.parametrize("wrapped", [True,False])
def test_lookup_array_and_items_envelopes(operation,path,wrapped):
    values=[{"id":41,"name":"Document Number"}]
    result, requests=read(operation,{"items":values} if wrapped else values)
    assert result["response_shape"] == ("items" if wrapped else "raw_array")
    assert result["resources"][0]["id"] == "41" and result["resources"][0]["label"] == "Document Number"
    assert requests[0].url.path == path and not requests[0].url.query


@pytest.mark.parametrize("payload", [{"items":[],"results":[]},{"items":None},{"unrecognised":[]},[]])
def test_artefact_contract_mismatch_is_not_a_false_empty_success(payload):
    with pytest.raises(ProviderError) as error:read("artefacts",payload)
    assert error.value.code == "contract_mismatch"


def test_empty_known_envelope_is_valid_and_boolean_identity_is_not():
    assert read("artefacts",{"items":[]})[0]["returned"] == 0
    with pytest.raises(ProviderError):read("groups",[{"id":True,"name":"Invalid identity"}])


def test_lookup_fixture_routes_remain_synthetic_without_live_credentials(tmp_path):
    c=TestClient(create_app(tmp_path/"lookup.db",demo=True))
    c.post("/api/demo/session",json={"user_id":"north-owner"})
    item=c.post("/api/projects/harbour/read-connections",json={"name":"Reference lookup","provider":"redeye","base_url":"https://api.redeyedms.com","auth_header":"Authorization","auth_prefix":"Bearer"}).json()
    for operation, shape in [("groups","raw_array"),("metadata_keys","items")]:
        result=c.post(f"/api/projects/harbour/read-connections/{item['id']}/fixture-check",json={"operation":operation})
        assert result.status_code == 200 and result.json()["synthetic"] is True
        assert result.json()["response_shape"] == shape and result.json()["live_verified"] is False
