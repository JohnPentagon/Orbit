# RedEye reference-client evidence

6 November 2026. Reviewed the product-owner-supplied `RedEyeApiClient.cs` (187 lines). This is implementation evidence from another utility, not a vendor certification or proof of a live ORBIT connection. The original attachment is not copied into the repository.

## Connection findings

- Constructor line 17 defaults to `https://api.redeyedms.com`; callers can override `baseUrl`. The effective host therefore needs checking in the construction/calling code or configuration resolver.
- `SetApiKey` lines 31–34 assigns `AuthenticationHeaderValue("Bearer", apiKey)`, establishing that this client sends `Authorization: Bearer <apiKey>`.
- Resource requests add `Accept: application/json`. JSON request bodies use `Content-Type: application/json`.
- No extra bucket/account header appears in this file. That does not establish how a key is scoped to a bucket; entitlement and permissions still need verification.
- No hard-coded API key is present in this file; the key is passed as an argument.

ORBIT now defaults RedEye setup to this reference client's URL and bearer format, labelled **Utility default — verify configured overrides**. The official-docs QA option remains separate. Both hosts are exact presets, with the existing explicit test-access confirmations and local live-read opt-in still required. A custom host still requires the operator allowlist. No live credential request was made to validate the reference utility's host.

## Response/mapping questions

- Metadata keys and groups are deserialised as **raw arrays** in this client, whereas the published docs show wrapper schemas. Need actual model definitions and, later, sanitised responses before implementing that behaviour as verified contract support.
- Artefact listing deserialises `ArtefactListResponse` and reads `.Items`; search reads `SearchResponse.Results`. A C# property may have a `JsonPropertyName` attribute or other mapping. `.Items` alone does not prove the wire JSON key is `items`.
- Optional `groupId` is added to the list query. Search adds `groups` in the request body and repeated `expand` query parameters. These details require the models/resolvers and operation/version evidence before being copied into ORBIT.
- Caller-provided page/limit values do not establish page numbering, exhaustion rules or maximum limits. The calling code/resolver may explain those policies.
- The example includes geometry update and delete operations. These are not required for connection setup and are not enabled in ORBIT.
- The example does not implement file upload/complete document handover, so it does not verify that workflow.
- Its parse-error messages embed full raw response JSON. ORBIT should retain sanitised errors instead of copying that logging pattern.

## Most useful follow-up files

1. Resolver classes for group selection, metadata keys/values and document identity/matching.
2. `ArtefactListResponse`, `SearchResponse`, `MetadataKey`, `GroupInfo`, and artefact DTO/model definitions, including JSON serialisation attributes.
3. The code that constructs `RedEyeApiClient`, and a redacted configuration loader showing whether the default base URL is overridden.
4. If available, a separate upload/document-revision client for future handover research.

Remove API keys, tokens, passwords, client secrets and customer document/personal data before sharing. Synthetic or redacted settings are sufficient. We do not need a real key in chat.
