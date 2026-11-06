"""Offline Meridian Explorer contract groundwork; no transport or authentication."""
from backend.providers import ProviderError

# Hand-authored, deliberately not captured customer data. Official GetDocuments
# documents typed Properties, GlobalID and RevisionGlobalID as distinct fields.
EXPLORER_FIXTURE = {
    "PageIndex": 0, "ActualCount": 1,
    "Documents": [{"GlobalID": "synthetic-document-id", "RevisionGlobalID": "synthetic-version-id",
                   "Name": "Example drawing.dwg", "RevisionNumber": "P01", "TypeName": "Drawing",
                   "Properties": [{"Name": "Example.Discipline", "Value": "Structural"},
                                  {"Name": "Example.IsReleased", "Value": True},
                                  {"Name": "Example.Level", "Value": 2}]}],
}


def explorer_documents(payload, limit=25):
    """Validate a documented envelope; never treat filenames as document numbers.

    Download/viewer URLs are deliberately not returned or followed. Neither a
    successful parse nor ActualCount establishes current vault completeness.
    """
    def fail():
        raise ProviderError("meridian_contract_invalid", "Expected a documented Meridian Explorer GetDocuments response")
    if not isinstance(payload, dict) or not isinstance(payload.get("Documents"), list):
        fail()
    for key in ("PageIndex", "ActualCount"):
        if type(payload.get(key)) is not int or payload[key] < 0:
            fail()
    if type(limit) is not int or not 1 <= limit <= 25:
        raise ValueError("Display limit must be between 1 and 25")
    resources = []
    for record in payload["Documents"][:limit]:
        if not isinstance(record, dict):
            fail()
        for key in ("GlobalID", "RevisionGlobalID", "Name"):
            if not isinstance(record.get(key), str) or not record[key].strip() or len(record[key]) > 1000:
                fail()
        for key in ("RevisionNumber", "TypeName"):
            if key in record and record[key] is not None and not isinstance(record[key], str):
                fail()
        properties = record.get("Properties", [])
        if not isinstance(properties, list) or len(properties) > 200:
            fail()
        for prop in properties:
            if not isinstance(prop, dict) or not isinstance(prop.get("Name"), str) or not prop["Name"].strip() or "Value" not in prop or isinstance(prop["Value"], (list, dict)):
                fail()
        resources.append({"document_id": record["GlobalID"], "version_id": record["RevisionGlobalID"], "name": record["Name"], "revision": record.get("RevisionNumber"), "kind": record.get("TypeName"), "properties": [{"name": p["Name"], "value": p["Value"]} for p in properties]})
    return {"resources": resources, "returned": len(resources), "reported_count": payload["ActualCount"], "reported_page_index": payload["PageIndex"], "coverage": "Bounded response preview only; repository freshness and paging semantics require installation-specific validation", "files_transferred": 0, "imported": 0}
