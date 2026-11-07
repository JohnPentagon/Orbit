# Meridian and on-premises connection groundwork

Research checked 6 November 2026 against public official Accruent documentation. These pages currently identify themselves as **Meridian Enterprise 2026**. A 2024 release-notes page also exists; that does not prove API compatibility across all 2024+ releases. Installed release, patch and licensed components must be recorded before choosing a live adapter.

## Products and interfaces

| Interface | Officially documented behaviour | ORBIT implication |
| --- | --- | --- |
| Enterprise / PowerWeb | Enterprise is on-premises. PowerWeb is an IIS-hosted ISAPI browser application accessing Enterprise vaults. | Record PowerWeb as product context; do not scrape it or treat its browser URL as a generic REST API. |
| Explorer Web API | Retrieve document information from an Explorer repository; requests use calling-process security credentials and Explorer privileges. | Best documented initial read candidate if Explorer is installed. Exact Windows/auth delegation must be confirmed with the administrator. |
| Meridian API Service | Installed separately/in server setup; documented primarily for Meridian Mobile. Requires Enterprise/Explorer configuration and licences. | Do not equate it with PowerWeb or assume app/API-key compatibility. Obtain installed API contract first. |
| .NET / Connection API | Separate API documentation, outside the main guide's search. | Candidate for a Windows integration bridge and later controlled writes; SDK, licensing and supported execution model remain unverified. |
| Meridian Portal / Cloud | Separate collaboration product linked from Enterprise introduction. | Needs its own API/auth investigation if that is the customer's product. |

Official sources:

- [Enterprise introduction](https://help.accruent.com/meridianenterprise/Content/Online_Help/Common/Introduction.htm)
- [PowerWeb architecture](https://help.accruent.com/meridianenterprise/Content/Online_Help/AdminGuide/Architecture/PowerWeb.htm)
- [Explorer Web API reference](https://help.accruent.com/meridianenterprise/Content/Online_Help/Enterprise_Server/Explorer/WebAPI/Web_API_reference.htm)
- [API Service installation](https://help.accruent.com/meridianenterprise/Content/Online_Help/AdminGuide/Installation/MeridianAPI_Service_Install.htm)
- [.NET / Connection API landing page](https://help.accruent.com/meridianenterprise/Content/Online_Help/Common/API_LandingPage.htm)
- [2024 release notes](https://help.accruent.com/meridianenterprise/Content/Enterprise_RN/2024.htm)

## Explorer read contract

[GetDocuments](https://help.accruent.com/meridianenterprise/Content/Online_Help/Enterprise_Server/Explorer/WebAPI/GetDocuments.htm) documents `/BCEnterprise/api/GetDocuments.ashx` with `VIEWID`, `DOCFILTER` or `TAGFILTER`, optional filter parameters, `pn` property names, `PAGEINDEX` and `PAGESIZE`. It returns `PageIndex`, `ActualCount` and `Documents`. Do not invent a global host: the customer supplies their installed application URL. Although some vendor examples show HTTP, ORBIT's planning references require HTTPS.

[GetDocument](https://help.accruent.com/meridianenterprise/Content/Online_Help/Enterprise_Server/Explorer/WebAPI/GetDocument.htm) documents `/BCEnterprise/api/getdocument.ashx` with `viewid` and `DocID` (current revision) or `RevID` (specific revision; takes precedence). Optional `pn` selects properties.

Important mapping distinctions:

- `GlobalID` identifies a document; `RevisionGlobalID` represents its version identity. `RevisionNumber` is a business label, not the stable identity.
- `Name` is a display name/filename. It is not automatically a construction document number.
- `Properties` contains typed name/value pairs. Preserve booleans and numbers; do not flatten everything into lowercased text.
- `DownloadUrlSource` and `DownloadUrl` distinguish original and PDF rendition. Links can be empty. Do not follow returned URLs automatically; host, transport, permission and content validation would be needed for transfers.
- Explorer data may be a synchronised/published repository. Its freshness and visibility must be established before drawing conclusions about current vault contents.
- The GetDocuments parameter description calls `PAGEINDEX` a starting document index, whereas its response description calls `PageIndex` a page number. Resolve this against installed API behaviour rather than assume offset or page semantics. `ActualCount` alone is not proof that ORBIT has retrieved a full register.

Initial version 0.5 groundwork: `backend/meridian.py` validates the documented response shape, bounds display to 25, preserves document/version/revision separation and scalar metadata types, and excludes download/viewer links. An owner can preview a **hand-authored fixture** from a saved Meridian preparation plan. That initial increment had no Meridian network transport or authentication handler; see the version 0.8 update below for the optional Explorer reader.

## API Service prerequisites and uncertainties

The installation guide names IIS, Enterprise website components, registered vault, Explorer repository/views, a successful synchronisation job, valid CA-signed HTTPS certificates and Explorer Standard/Plus licences for Mobile. The IIS application-pool account is documented as matching the EDM Server service identity. This is a vendor installation requirement, not a recommendation to give ORBIT that identity.

It mentions local or `DOMAIN\User` account formats and rejects UPN format for Mobile. Token issuer/key/timeout settings are documented; **this does not establish a public login endpoint, grant type or reusable API-key header for ORBIT**. Do not collect Windows passwords in preparation notes.

There is a path inconsistency in the guide: one paragraph states `https://<ServerName>/m360.meridian/<api_version>/`, while its health test uses `https://<ServerName>/m360.meridian/api/<api_version>/checks/health`. Record the actual installed path and version from the administrator. ORBIT performs neither an automatic health probe nor discovery against guessed paths.

## Cloud-first with private systems

The portal models these proposed execution routes per connection:

1. Local executor on the same authorised network — appropriate for current local testing once a verified adapter exists.
2. Administrator-managed private route/VPN from the eventual executor — depends on customer routing, DNS, identity, certificate trust and policy.
3. A future customer-hosted outbound worker — proposed cloud deployment pattern, not implemented. It would claim only tenant/connection-bound jobs, store local provider credentials securely, use authenticated outbound HTTPS and return scoped results/audit evidence. It must not become an arbitrary URL proxy or shell runner.
4. Administrator-approved public HTTPS API where the vendor/customer already supports it.

No worker, VPN, tunnel, ingress firewall rule or Windows authentication package is installed by this increment. A cloud browser reaching PowerWeb does not prove a cloud executor can reach/authenticate its API. The selected cloud workspace currently has no configured VPN.

[PowerWeb firewall guidance](https://help.accruent.com/meridianenterprise/Content/Online_Help/AdminGuide/NetworkAdministration/AllowPowerWebAccess_Firewall.htm) describes DCOM between IIS and the EDM server, including TCP 135 and dynamically allocated ports. These are internal vendor-topology concerns. ORBIT does not open or expose DCOM to the Internet. Network changes belong with the customer administrator, using version-matched vendor guidance.

Preparation records allow HTTPS URLs with virtual paths/custom ports as references, but reject embedded credentials, query strings and fragments. They are never fetched, resolved or admitted to the live host allowlist. Notes are ordinary project-visible configuration, not secret storage. Store credentials only through an implemented encrypted credential flow after an authentication contract exists.

## What can be supplied later

When convenient: exact product and release/patch, enabled components/licence, administrator-confirmed API interface/docs/base URL, vault/repository/view/filter references, authentication scheme and least-privilege account requirements, and network/certificate constraints. No production secrets or sample customer files are needed to maintain the preparation plan.

## Version 0.8 implementation update

Additional connections now provides an optional first-response Explorer GET adapter using the current Windows process identity via SSPI with delegation disabled. It is constrained to the saved HTTPS application/view/filter and an exact operator-approved origin. No Windows password is stored. Actual SSPI/Windows deployment validation is still pending; Mobile/.NET/Connection API writes, Portal/Cloud and any private worker remain unimplemented. See ADDITIONAL_CONNECTIONS.md.
