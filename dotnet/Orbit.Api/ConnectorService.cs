using System.Net;
using System.Net.Http.Headers;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Orbit.Api;

public sealed class ConnectorService(
    IHttpClientFactory factory,
    IConfiguration cfg,
    Cipher cipher,
    OrbitDb? db = null
)
{
    public static readonly HashSet<string> FixedOrigins =
    [
        "https://api.redeyedms.com",
        "https://developer.api.autodesk.com",
        "https://api.bsdd.buildingsmart.org",
        "https://api.procore.com",
    ];

    public Uri Approved(string value)
    {
        if (
            !Uri.TryCreate(value, UriKind.Absolute, out var uri)
            || uri.Scheme != "https"
            || !string.IsNullOrEmpty(uri.UserInfo)
            || !string.IsNullOrEmpty(uri.Query)
            || !string.IsNullOrEmpty(uri.Fragment)
            || uri.IsLoopback
            || IPAddress.TryParse(uri.Host, out _)
        )
            throw new ApiException(
                422,
                "Use an approved HTTPS vendor URL without credentials, IP addresses, query or fragment."
            );
        var origin = uri.GetLeftPart(UriPartial.Authority);
        var allowed = (cfg["Orbit:AllowedApiOrigins"] ?? "").Split(
            ',',
            StringSplitOptions.TrimEntries | StringSplitOptions.RemoveEmptyEntries
        );
        if (
            !FixedOrigins.Contains(origin)
            && !allowed.Contains(origin, StringComparer.OrdinalIgnoreCase)
        )
            throw new ApiException(
                409,
                "This API origin must be approved in the Azure application settings before connecting."
            );
        return uri;
    }

    public async Task<JsonNode> Get(Uri uri, Record? profile = null, CancellationToken ct = default)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, uri);
        request.Headers.Accept.Add(new("application/json"));
        if (profile != null)
        {
            if (profile.Data().S("provider") == "forma")
                AutodeskOAuth.FreshAccess(profile);
            if (profile.Secret == null)
                throw new ApiException(409, "Add a credential to this connection first.");
            var config = profile.Data()["configuration"]!;
            var secret = cipher.Unprotect(profile.Secret);
            var header = config.S("auth_header", "Authorization");
            var prefix = config.S(
                "auth_prefix",
                config.S("auth_mode") == "api_key" ? "" : "Bearer"
            );
            if (profile.Data().S("provider") == "forma" || config.S("auth_mode") == "bearer")
            {
                header = "Authorization";
                prefix = "Bearer";
            }
            if (config.S("auth_mode") == "basic")
            {
                header = "Authorization";
                prefix = "Basic";
                secret = Convert.ToBase64String(System.Text.Encoding.UTF8.GetBytes(secret));
            }
            if (
                !Regex.IsMatch(header, "^[A-Za-z0-9-]{1,64}$")
                || new[] { "host", "cookie", "proxy-authorization", "content-type" }.Contains(
                    header.ToLowerInvariant()
                )
                || secret.Any(char.IsControl)
                || prefix.Any(char.IsControl)
                || prefix.Length > 30
            )
                throw new ApiException(422, "Invalid authentication header or credential.");
            request.Headers.Add(header, (prefix.Length > 0 ? prefix + " " : "") + secret);
        }
        using var response = await factory
            .CreateClient("vendor")
            .SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
        if (!response.IsSuccessStatusCode)
            throw new ApiException(
                response.StatusCode is HttpStatusCode.Unauthorized or HttpStatusCode.Forbidden
                    ? 409
                    : 502,
                $"Vendor read returned HTTP {(int)response.StatusCode}. Verify access and scope."
            );
        if (response.Content.Headers.ContentLength > 1048576)
            throw new ApiException(502, "Vendor response exceeded the 1 MB read limit.");
        await using var stream = await response.Content.ReadAsStreamAsync(ct);
        using var memory = new MemoryStream();
        var buffer = new byte[8192];
        int count;
        while ((count = await stream.ReadAsync(buffer, ct)) > 0)
        {
            if (memory.Length + count > 1048576)
                throw new ApiException(502, "Vendor response exceeded the 1 MB read limit.");
            await memory.WriteAsync(buffer.AsMemory(0, count), ct);
        }
        try
        {
            return JsonNode.Parse(memory.ToArray())
                ?? throw new ApiException(502, "Vendor returned an empty JSON response.");
        }
        catch (System.Text.Json.JsonException)
        {
            throw new ApiException(502, "Vendor returned an unexpected response format.");
        }
    }

    public static JsonArray Collection(JsonNode data, params string[] names)
    {
        if (data is JsonArray a)
            return a;
        foreach (var n in names)
            if (data[n] is JsonArray rows)
                return rows;
        throw new ApiException(502, "Vendor collection did not match the supported contract.");
    }

    public static JsonObject Flatten(JsonNode? data, string prefix = "", string secret = "")
    {
        var result = new JsonObject();
        void walk(JsonNode? n, string path, int depth)
        {
            if (result.Count >= 200)
                return;
            if (n is JsonObject o && depth < 4)
            {
                foreach (var pair in o)
                {
                    if (
                        Regex.IsMatch(
                            pair.Key,
                            "^(password|secret|access_token|refresh_token|authorization|cookie|connection_string|links|href|url|downloadurl|download_url)$",
                            RegexOptions.IgnoreCase
                        )
                    )
                        continue;
                    walk(
                        pair.Value,
                        path.Length == 0 ? pair.Key : path + "." + pair.Key,
                        depth + 1
                    );
                }
            }
            else if (
                n is JsonValue
                || n == null
                || n is JsonArray arr
                    && arr.Count <= 100
                    && arr.All(v => v == null || v is JsonValue)
            )
            {
                var raw = n?.ToJsonString() ?? "null";
                result[path] =
                    raw.Length > 2000 || secret.Length > 0 && raw.Contains(secret)
                        ? JsonValue.Create("[not captured]")
                        : n?.DeepClone();
            }
        }
        walk(data, prefix, 0);
        return result;
    }

    public async Task<JsonObject> Read(Record r, JsonObject body, CancellationToken ct)
    {
        try
        {
            var result = await ReadCore(r, body, ct);
            await Observe(r, "success", body.S("operation"));
            return result;
        }
        catch (ApiException e)
        {
            await Observe(
                r,
                e.Status is 409 or 422 or 501 ? "needs_setup" : "failed",
                body.S("operation")
            );
            throw;
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException)
        {
            await Observe(r, "failed", body.S("operation"));
            throw;
        }
    }

    async Task Observe(Record r, string status, string operation)
    {
        if (db == null)
            return;
        db.Add(
            r.Tenant,
            r.Project,
            "connection-check",
            Guid.NewGuid().ToString(),
            new()
            {
                ["connection_id"] = r.Id,
                ["generation"] = r.Version,
                ["status"] = status,
                ["operation"] = operation,
            }
        );
        await db.SaveChangesAsync(CancellationToken.None);
    }

    async Task<JsonObject> ReadCore(Record r, JsonObject body, CancellationToken ct)
    {
        var d = r.Data();
        var config = d["configuration"]!;
        if (
            !config.B("vendor_settings_confirmed")
            || !config.B("approved_test_access")
            || config.S("evidence_note").Length == 0
        )
            throw new ApiException(
                409,
                "Confirm vendor settings, authorised test access and a non-secret reference in connection setup."
            );
        var basis = Approved(config.Required("base_url"));
        var provider = d.S("provider");
        var op = body.S("operation");
        string path;
        var root = basis.ToString().TrimEnd('/');
        var scope = (string key, string fallback) =>
        {
            var saved = config.Required(fallback);
            if (body.S(key).Length > 0 && body.S(key) != saved)
                throw new ApiException(
                    409,
                    "Requested resource is outside the saved connection scope."
                );
            return Uri.EscapeDataString(saved);
        };
        if (provider == "redeye")
            path = op switch
            {
                "artefacts" => "/api/v1/artefacts",
                "groups" => "/api/v1/groups",
                "metadata_keys" => "/api/v1/metadata-keys",
                _ => throw new ApiException(422, "Choose a supported RedEye read."),
            };
        else if (provider == "forma")
        {
            if (root != "https://developer.api.autodesk.com")
                throw new ApiException(422, "Use the Autodesk API host.");
            if (op == "documents")
            {
                scope("project", "vendor_project");
                scope("folder", "folder");
                return await AutodeskDocuments.Read(
                    this,
                    r,
                    cipher.Unprotect(
                        r.Secret ?? throw new ApiException(409, "Sign in with Autodesk first.")
                    ),
                    ct
                );
            }
            path = op switch
            {
                "hubs" => "/project/v1/hubs",
                "projects" => "/project/v1/hubs/" + scope("hub", "hub") + "/projects",
                "folders" => "/project/v1/hubs/"
                    + scope("hub", "hub")
                    + "/projects/"
                    + scope("project", "vendor_project")
                    + "/topFolders",
                "documents" => "/data/v1/projects/"
                    + scope("project", "vendor_project")
                    + "/folders/"
                    + scope("folder", "folder")
                    + "/contents?page%5Blimit%5D=25",
                _ => throw new ApiException(422, "Choose a supported Autodesk read."),
            };
        }
        else if (provider == "meridian")
        {
            if (config.S("auth_mode") == "windows_integrated")
                throw new ApiException(
                    409,
                    "Azure App Service cannot use your local Windows identity. Configure a supported service credential and private network route first."
                );
            path =
                "/api/GetDocuments.ashx?VIEWID="
                + Uri.EscapeDataString(config.Required("view_id"))
                + "&DOCFILTER="
                + Uri.EscapeDataString(config.S("filter_name"))
                + "&PAGEINDEX=0&PAGESIZE=25";
            if (config["property_names"] is JsonArray names && names.Count > 0)
                path +=
                    "&pn="
                    + Uri.EscapeDataString(string.Join("|", names.Select(n => n!.ToString())));
        }
        else if (provider == "procore")
            path = op switch
            {
                "companies" => "/rest/v1.0/companies",
                "projects" => "/rest/v1.0/projects?company_id="
                    + Uri.EscapeDataString(config.Required("company_id")),
                _ => throw new ApiException(501, "This Procore operation is not yet ported."),
            };
        else
            throw new ApiException(
                501,
                "This provider adapter is not yet ported to .NET. No request was sent."
            );
        var data = await Get(new Uri(root + path), r, ct);
        if (provider == "meridian")
        {
            var docs = Collection(data, "Documents");
            var meridianResources = new JsonArray();
            foreach (var doc in docs.Take(25))
            {
                var props = new JsonObject();
                foreach (var prop in doc!["Properties"]?.AsArray() ?? new JsonArray())
                {
                    if (prop == null || prop["Value"] is JsonObject or JsonArray)
                        throw new ApiException(502, "Unexpected Meridian property contract.");
                    props[prop.Required("Name")] = prop["Value"]?.DeepClone();
                }
                var native = new JsonObject
                {
                    ["document_id"] = doc.Required("GlobalID"),
                    ["version_id"] = doc.Required("RevisionGlobalID"),
                    ["name"] = doc.Required("Name"),
                    ["revision"] = doc["RevisionNumber"]?.DeepClone(),
                    ["properties"] = props,
                };
                meridianResources.Add(
                    new JsonObject
                    {
                        ["id"] = native["document_id"]!.DeepClone(),
                        ["label"] = native["name"]!.DeepClone(),
                        ["kind"] = "document",
                        ["fields"] = Flatten(
                            native,
                            secret: r.Secret == null ? "" : cipher.Unprotect(r.Secret)
                        ),
                    }
                );
            }
            return new()
            {
                ["operation"] = op,
                ["meridianResources"] = meridianResources,
                ["returned"] = meridianResources.Count,
                ["coverage"] =
                    "First bounded Meridian Explorer view response; completeness is not established.",
                ["synthetic"] = false,
            };
        }
        var rows = Collection(data, "data", op, "results");
        var resources = new JsonArray();
        foreach (var item in rows.Take(25))
        {
            if (item == null || item["id"] == null)
                throw new ApiException(502, "Vendor response has no supported resource ID.");
            var id = item["id"]!.ToString();
            var label = item["attributes"]?.S("displayName", item["attributes"]!.S("name"))
                ?? item.S("name", item.S("title", id));
            var secret = r.Secret == null ? "" : cipher.Unprotect(r.Secret);
            resources.Add(
                new JsonObject
                {
                    ["id"] = id.Replace(secret.Length > 0 ? secret : "\0", "[REDACTED]"),
                    ["label"] = label.Replace(secret.Length > 0 ? secret : "\0", "[REDACTED]"),
                    ["kind"] = item.S("type", op),
                    ["fields"] = Flatten(item, secret: secret),
                }
            );
        }
        return new()
        {
            ["operation"] = op,
            ["resources"] = resources,
            ["returned"] = resources.Count,
            ["coverage"] = "At most 25 resources from one response; not a complete register.",
            ["synthetic"] = false,
            ["imported"] = 0,
            ["files_transferred"] = 0,
        };
    }
}
