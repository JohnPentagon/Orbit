# Optional bSDD dictionary and property reference

Version 0.6.0. Public read connectivity checked on 6 November 2026.

## Use in the portal

1. Select the intended project and sign in as its synthetic owner. Open **bSDD dictionaries**.
2. Click **Connect & browse dictionaries**, then select an explicit dictionary version. The list pages through 25 entries; the text filter applies to the displayed page. Alternatively paste a versioned dictionary identifier into **Dictionary URL**, then click **Verify dictionary URL**.
3. Optionally browse classes, or enter a class code (for example `IfcWall`) / class identifier URL and click **Load class properties**.
4. Select the property definitions needed for the project (up to 100). The table shows names, property sets/codes, data types, definitions, units and allowed values where supplied. Missing type/units remain unspecified.
5. Check **Use this dictionary … for this project's mapping reference**, then **Save dictionary selection**. You may also save a dictionary reference without a class or properties.
6. In **Integration profiles**, destination-field inputs suggest selected, unambiguous property-set/code names supported by the current mapping vocabulary. Review these as mapping design choices. Required destination values remain explicit mapping checkboxes.

Example dictionary identifier:

```text
https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3
```

Example class identifier:

```text
https://identifier.buildingsmart.org/uri/buildingsmart/ifc/4.3/class/IfcWall
```

These are examples, not a recommended mandatory project standard. The service reported IFC 4.3 as **Preview** during verification; the portal preserves dictionary status/licence rather than treating it as approved/compliant.

Opening the page loads only saved local settings. Public reads occur when explicitly browsing, verifying, loading a class or saving a selected reference. Successful public API responses may be reused for up to five minutes to reduce duplicate requests. A bounded in-memory cache holds at most 64 responses; HTTP/transport failures are not cached, and it is not a credentials/customer-data cache. The saved selection remains available across restarts without a network request.

**Disable & clear bSDD** removes the optional project reference without a network request. It does not remove fields from existing mapping profiles. Other authorised project roles can view the saved reference/properties; only owners can perform public lookups or change settings in this local foundation. New projects start disabled, and another organisation does not inherit the selection.

## What is persisted

The project stores the exact versioned dictionary URI, name/version/status/licence metadata, optional class URI/name/code and selected property snapshots. Each snapshot retains both the class-property URI and underlying property URI, with supplied types/units/value constraints. Data comes from the server-side API response, not client-submitted definitions. Changing to a different dictionary/class clears unsaved property choices. Saving uses revision checks to reject an outdated editor. Identity, role and project access are rechecked after the external read.

A saved snapshot pins the chosen reference; it does not automatically follow a newer dictionary version. Upstream content can still change within a dictionary version, so saving/reloading a class is an explicit review point. The displayed save/verification time can use a response cached within the five-minute window. Returning to a saved selection displays its selected subset; use **Load class properties** to browse the full class again.

## Connection and headers

Fixed base URL: **https://api.bsdd.buildingsmart.org**.

Implemented versioned GET endpoints:

- `/api/Dictionary/v1` with `Offset`/`Limit`, or exact `Uri`.
- `/api/Dictionary/v1/Classes` with dictionary `Uri`, `Offset`, `Limit`.
- `/api/Class/v1` with class `Uri` and `IncludeClassProperties=true`.

Headers: `Accept: application/json` and `User-Agent: ORBIT/0.9.0`. No API key, bearer token or cookie is sent by this adapter. These public operations succeeded anonymously. Private/secured dictionaries and GraphQL authentication are separate capabilities and are not implemented.

The identifier URL is validated as a canonical versioned buildingSMART identifier and sent as a query parameter to the fixed API. It is **never fetched directly**. Arbitrary hosts, HTTP, credentials, ports, query strings, fragments and traversal-like identifiers are rejected. Outbound requests keep TLS verification, use the configured proxy, refuse redirects, time out, and cap decoded response bytes at 2 MB. Network/contract/rate-limit errors leave the existing saved settings unchanged. This public reference adapter does not use the customer-connector live-read opt-in or send vendor project data to bSDD.

## Observed verification

Public reads returned HTTP 200 for dictionary listing, exact dictionary resolution, paged classes and IFC `IfcWall` with properties. At observation the list reported 442 dictionaries; IFC 4.3 reported 2,163 classes. The running portal also returned HTTP 200 for exact IFC 4.3 dictionary resolution. The implemented parser successfully read 233 `IfcWall` class-property definitions at 18:36 UTC on 6 November 2026, including Boolean, Real, String and unspecified data types. Counts are service observations, not hard-coded limits or a completeness guarantee for all dictionaries.

One burst of verification calls received HTTP 429; a subsequent single class read succeeded. The portal reports a safe retry-later message and caches successful reads to reduce repeated requests. Automated contract tests exercise transport failures, scope/role restrictions, stale saves, cache behaviour, server-sourced property snapshots and preservation of saved settings. Browser tests use explicitly intercepted service fixtures; they are separate from the live verification above.

## Boundaries

This increment defines an optional **project reference schema** and mapping field suggestions. It does not create fields in Autodesk/RedEye, import records, convert units, enforce bSDD data types/allowed values against documents, issue an IDS/ISO 19650 compliance result or execute a transfer. Mapping profile digests still bind their existing mapping configuration; they do not bind or enforce the mutable project bSDD setting. The selected property identities/snapshots remain in the separate project reference record. Binding a reviewed schema snapshot to executable profiles and validating real data are later increments.

Dictionary/class/property content and licences belong to their publishers. Review the displayed dictionary licence/status and intended project use. No source dictionary content is silently designated mandatory.

Official sources:

- [buildingSMART bSDD API documentation](https://github.com/buildingSMART/bSDD/blob/master/Documentation/bSDD%20API.md)
- [Official public dictionary endpoint](https://api.bsdd.buildingsmart.org/api/Dictionary/v1)

The API documentation explicitly advises versioned API calls for system-to-system communication and an application/version User-Agent. The SwaggerHub link currently referenced by that document returned 404 during research; the implementation was checked against the successful public v1 responses rather than an invented schema endpoint. The documentation describes separate authentication/registration for secured APIs; its demonstration client IDs are not used by ORBIT.

## Parameter imports added in version 0.7

The separate **Parameter imports** workflow now binds selected bSDD snapshots to reviewed definition/value jobs and enforces supported types/allowed values/units in local synthetic execution. It can create local field definitions and populate optional document values with read-back/quality checks. Existing integration mapping profiles remain separate and are not silently changed. Real platform parameter writes are not implemented; see PARAMETER_IMPORTS.md for precise scope and outstanding API prerequisites.

The v0.9 RedEye import-test pilot can associate one selected validated bSDD value with one existing native metadata key on an operator-confirmed disposable artefact. This is not dictionary/key creation; see REDEYE_IMPORT_TEST.md.
