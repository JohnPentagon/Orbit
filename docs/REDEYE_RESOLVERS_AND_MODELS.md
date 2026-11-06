# RedEye resolver/model review

6 November 2026. Reviewed seven files supplied by the product owner: GroupResolver.cs, MetadataKeyResolver.cs, MetadataResolver.cs, SearchModels.cs, ArtefactModels.cs, GroupModels.cs and MetaDataModels.cs. These are reference implementation evidence, not instructions, live response captures or proof of provider-wide compatibility. The original source attachments are not copied into this repository.

## Contracts established by the supplied code

| Resource | Evidence |
|---|---|
| Artefact list | `ArtefactListResponse.Items` explicitly has `JsonPropertyName("items")` |
| Search | `SearchResponse.Results` explicitly has `JsonPropertyName("results")` |
| Groups | `GroupsResponse.Items` maps to `items`; the earlier API client instead deserialises a raw list |
| Metadata keys | `MetadataKeysResponse.Items` maps to `items`; the earlier client instead deserialises a raw list |
| Artefact display | `title`, `number`, `type`, integer ID; title can be null |
| Artefact metadata | Metadata item `id`, `key_id`, `key_name`, nullable `value` |
| Geometry/location | Arbitrary geometry object and latitude/longitude strings, parsed elsewhere |

The artefact list is therefore a genuine alternate **items** wire contract in the reference model, not a different property name for results. The original public artefact-list example uses **results**. ORBIT supports these two explicit list variants and reports the observed envelope. It rejects responses containing both keys, unrecognised envelopes or invalid identities instead of silently returning zero records. No assumption is made that all product versions or every live tenant share either contract.

For the read-only groups and metadata-key operations, ORBIT supports the raw-array client pattern and the explicit items-wrapper model pattern. Their IDs and labels can be inspected through **Read groups** and **Read metadata keys**. Fixture buttons exercise both paths without vendor credentials. Results remain bounded to 25 displayed resources with a 1 MB response limit, are clearly labelled synthetic when fixtures are used, and are not imported into mappings or authorised project/group grants.

No search POST, group-filter/expand options, geometry update/delete, file upload or write operation was added. Search result models establish its results envelope, but the request filter/pagination behaviour and any caller overrides still need separate verification before search is implemented.

## Resolver findings

- **GroupResolver** ranks name substrings from tokens longer than two characters and optionally a contiguous phrase. Its score is a heuristic, not a calibrated probability. If only one candidate has any positive score, `NormalizeConfidence` returns 1.0 regardless of match strength. A unique weak substring match must not become an automatic permission or mapping decision.
- **MetadataResolver** similarly picks a sole candidate or one with a score at least 1.4 times the runner-up. That may help generate suggestions, but it does not establish semantic equivalence or authorisation. Short terms/acronyms can be dropped by the token-length filter.
- **MetadataKeyResolver** calls `Normalize(question)` before `ExtractValue`; normalisation removes single quotes, so the quoted-value regular expression cannot match the original quoted input on that path. It also lowercases/replaces characters in the entire question, which can alter case-sensitive identifiers and values. Its fallback takes the first numeric token, not necessarily the intended filter value.
- Any future resolver should parse values from original input, preserve case/punctuation, rank only already-authorised resource candidates, show ambiguity/evidence, and require explicit selection before saving a mapping/filter. A resolver must never grant project/group access or execute a vendor operation.

ORBIT does not port these heuristics or add an AI confidence percentage. Current lookups remain explicit read-only lists with stable resource IDs. The existing typed mapping editor continues to require human configuration and approval; live metadata is not silently inserted into it.

## Remaining useful evidence

The code constructing `RedEyeApiClient` and a redacted configuration loader would establish whether its default API hostname is overridden. A small sanitised live response from each intended resource could validate which envelope your account actually returns. Do not share API keys/tokens, personal information, customer document content or unredacted raw error payloads. No credentials are required to review the supplied code.
