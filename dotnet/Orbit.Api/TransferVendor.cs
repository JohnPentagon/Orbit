using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;

namespace Orbit.Api;

/// <summary>Fixed Autodesk/RedEye endpoints; signed storage URLs never receive API credentials.</summary>
public sealed class TransferVendor(
    IHttpClientFactory factory,
    ConnectorService service,
    Cipher cipher
)
{
    public const int MaxBytes = 20 * 1024 * 1024;

    public static string FileName(string value)
    {
        if (
            value.Length is < 1 or > 240
            || value.Any(char.IsControl)
            || value.IndexOfAny(['/', '\\', '"']) >= 0
            || value is "." or ".."
        )
            throw new ApiException(
                422,
                "The source file name is not supported. Rename it in the source platform first."
            );
        return value;
    }

    public static Uri StorageUrl(string value)
    {
        if (
            !Uri.TryCreate(value, UriKind.Absolute, out var u)
            || u.Scheme != "https"
            || !u.IsDefaultPort
            || u.UserInfo.Length > 0
            || u.Fragment.Length > 0
        )
            throw new ApiException(
                409,
                "The vendor returned an unsupported signed storage URL. Inspect the recorded transfer state."
            );
        var query = Microsoft.AspNetCore.WebUtilities.QueryHelpers.ParseQuery(u.Query);
        var signed =
            Regex.IsMatch(
                u.Host,
                @"(^|\.)s3([.-][a-z0-9-]+)?\.amazonaws\.com$",
                RegexOptions.IgnoreCase
            ) && query.ContainsKey("X-Amz-Signature")
            || Regex.IsMatch(
                u.Host,
                @"^[a-z0-9]{3,24}\.blob\.core\.windows\.net$",
                RegexOptions.IgnoreCase
            ) && query.ContainsKey("sig")
            || Regex.IsMatch(u.Host, @"(^|\.)storage\.googleapis\.com$", RegexOptions.IgnoreCase)
                && query.ContainsKey("X-Goog-Signature");
        if (!signed)
            throw new ApiException(
                409,
                "The vendor returned an unsupported signed storage URL. Inspect the recorded transfer state."
            );
        return u;
    }

    public static string Root(Record target, ConnectorService service)
    {
        var c = target.Data()["configuration"]!;
        if (
            target.Data().S("provider") != "redeye"
            || !c.B("approved_test_access")
            || !c.B("vendor_settings_confirmed")
            || target.Secret == null
        )
            throw new ApiException(409, "Confirm and authorise the RedEye destination connection.");
        var uri = service.Approved(c.Required("base_url"));
        if (uri.AbsolutePath != "/")
            throw new ApiException(422, "Use the RedEye API origin without a path.");
        return uri.GetLeftPart(UriPartial.Authority);
    }

    public async Task<JsonNode> Post(
        Record target,
        string path,
        HttpContent content,
        CancellationToken ct
    )
    {
        var c = target.Data()["configuration"]!;
        using var req = new HttpRequestMessage(HttpMethod.Post, Root(target, service) + path)
        {
            Content = content,
        };
        var header = c.S("auth_header", "Authorization");
        var prefix = c.S("auth_prefix", "Bearer");
        var secret = cipher.Unprotect(target.Secret!);
        if (
            !Regex.IsMatch(header, "^[A-Za-z0-9-]{1,64}$")
            || new[] { "host", "cookie", "proxy-authorization", "content-type" }.Contains(
                header.ToLowerInvariant()
            )
            || secret.Any(char.IsControl)
            || prefix.Any(char.IsControl)
            || prefix.Length > 30
        )
            throw new ApiException(422, "Review the destination authentication header.");
        req.Headers.Add(header, (prefix.Length == 0 ? "" : prefix + " ") + secret);
        req.Headers.Accept.Add(new("application/json"));
        using var response = await factory
            .CreateClient("transfer")
            .SendAsync(req, HttpCompletionOption.ResponseHeadersRead, ct);
        if (!response.IsSuccessStatusCode)
            throw new ApiException(
                502,
                $"RedEye returned HTTP {(int)response.StatusCode}. Inspect transfer history before retrying."
            );
        return JsonNode.Parse(await Limited(response.Content, 1_048_576, ct))
            ?? throw new ApiException(502, "RedEye returned no transfer result.");
    }

    public async Task<JsonObject> Inventory(Record target, CancellationToken ct)
    {
        var root = Root(target, service);
        JsonArray Read(JsonNode data) =>
            ConnectorService.Collection(data, "items", "data", "groups", "metadata_keys");
        var keys = Read(await service.Get(new(root + "/api/v1/metadata-keys"), target, ct));
        var groups = Read(await service.Get(new(root + "/api/v1/groups"), target, ct));
        if (
            keys.Count > 1000
            || groups.Count > 1000
            || keys.Any(k => k.S("name").Length == 0)
            || groups.Any(g => g.N("id") <= 0)
        )
            throw new ApiException(
                502,
                "The destination key/group inventory is outside the supported transfer contract."
            );
        return new() { ["keys"] = keys.DeepClone(), ["groups"] = groups.DeepClone() };
    }

    public async Task<JsonObject> Version(Record source, string item, CancellationToken ct)
    {
        AutodeskOAuth.FreshAccess(source);
        var config = source.Data()["configuration"]!;
        if (
            source.Data().S("provider") != "forma"
            || !config.B("approved_test_access")
            || !config.B("vendor_settings_confirmed")
        )
            throw new ApiException(409, "Confirm the Autodesk source connection.");
        var project = Uri.EscapeDataString(
            AutodeskDocuments.Identifier(config.Required("vendor_project"))
        );
        var root = AutodeskOAuth.Api + "/data/v1/projects/" + project;
        var document = (
            await service.Get(
                new(root + "/items/" + Uri.EscapeDataString(AutodeskDocuments.Identifier(item))),
                source,
                ct
            )
        )["data"];
        if (document.S("id") != item)
            throw new ApiException(502, "Autodesk returned a different source item.");
        var version = document?["relationships"]?["tip"]?["data"].S("id") ?? "";
        if (version.Length is < 1 or > 1500 || version.Any(char.IsControl))
            throw new ApiException(502, "Autodesk did not return a current file version.");
        var details = (
            await service.Get(new(root + "/versions/" + Uri.EscapeDataString(version)), source, ct)
        )["data"];
        if (details.S("id") != version)
            throw new ApiException(502, "Autodesk returned a different file version.");
        var storage = details?["relationships"]?["storage"]?["data"].S("id") ?? "";
        if (
            !storage.StartsWith("urn:adsk.objects:os.object:", StringComparison.Ordinal)
            || storage.Length > 3000
            || storage.Any(char.IsControl)
        )
            throw new ApiException(
                409,
                "This Autodesk item has no supported downloadable original."
            );
        var name = FileName(
            details?["attributes"].S(
                "displayName",
                document?["attributes"].S("displayName", "") ?? ""
            )
                ?? ""
        );
        var size = details?["attributes"].N("storageSize") ?? 0;
        if (size > MaxBytes)
            throw new ApiException(422, "Transfer UAT supports files up to 20 MB.");
        var fields = ConnectorService.Flatten(document, secret: cipher.Unprotect(source.Secret!));
        return new()
        {
            ["version"] = version,
            ["storage"] = storage,
            ["name"] = name,
            ["size"] = size,
            ["fields"] = fields,
        };
    }

    public async Task<byte[]> Download(Record source, string storage, CancellationToken ct)
    {
        var objectId = storage["urn:adsk.objects:os.object:".Length..];
        var slash = objectId.IndexOf('/');
        if (slash <= 0 || slash == objectId.Length - 1)
            throw new ApiException(502, "Unsupported Autodesk object identifier.");
        var signed = await service.Get(
            new(
                AutodeskOAuth.Api
                    + "/oss/v2/buckets/"
                    + Uri.EscapeDataString(objectId[..slash])
                    + "/objects/"
                    + Uri.EscapeDataString(objectId[(slash + 1)..])
                    + "/signeds3download"
            ),
            source,
            ct
        );
        if (signed.S("status") != "complete")
            throw new ApiException(409, "Autodesk file is not ready for a complete download.");
        return await DownloadUrl(signed.Required("url", 12000), ct);
    }

    public async Task<byte[]> DownloadUrl(string url, CancellationToken ct)
    {
        using var request = new HttpRequestMessage(HttpMethod.Get, StorageUrl(url));
        using var response = await factory
            .CreateClient("transfer")
            .SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
        if (!response.IsSuccessStatusCode)
            throw new ApiException(502, "Signed file download failed; redirects are not followed.");
        return await Limited(response.Content, MaxBytes, ct);
    }

    public static async Task<byte[]> Limited(HttpContent content, int limit, CancellationToken ct)
    {
        if (content.Headers.ContentLength > limit)
            throw new ApiException(422, "Transfer response exceeds its size limit.");
        await using var input = await content.ReadAsStreamAsync(ct);
        using var output = new MemoryStream();
        var buffer = new byte[81920];
        int n;
        while ((n = await input.ReadAsync(buffer, ct)) > 0)
        {
            if (output.Length + n > limit)
                throw new ApiException(422, "Transfer response exceeds its size limit.");
            output.Write(buffer, 0, n);
        }
        return output.ToArray();
    }

    public async Task<JsonNode> Upload(
        Record target,
        byte[] bytes,
        string name,
        JsonObject payload,
        CancellationToken ct
    )
    {
        var multipart = new MultipartFormDataContent();
        var file = new ByteArrayContent(bytes);
        file.Headers.ContentType = new("application/octet-stream");
        multipart.Add(file, "file", FileName(name));
        multipart.Add(
            new StringContent(payload.ToJsonString(), Encoding.UTF8, "application/json"),
            "data"
        );
        return await Post(target, "/api/v2/upload?async=false", multipart, ct);
    }

    public async Task<bool> Exists(Record target, string sha256, string md5, CancellationToken ct)
    {
        var result = await Post(
            target,
            "/api/v2/files/exist",
            JsonContent.Create(new { hashes = new[] { sha256, md5 } }),
            ct
        );
        var items =
            result["items"] as JsonArray
            ?? throw new ApiException(502, "RedEye duplicate-check response is unsupported.");
        if (items.Any(i => i?.ToString() != sha256 && i?.ToString() != md5))
            throw new ApiException(502, "RedEye returned an unexpected duplicate hash.");
        return items.Count > 0;
    }

    public async Task Assign(Record target, long artefact, JsonArray groups, CancellationToken ct)
    {
        if (groups.Count == 0)
            return;
        var r = await Post(
            target,
            "/api/v1/artefact-groups",
            JsonContent.Create(
                new JsonObject
                {
                    ["artefactIds"] = new JsonArray(artefact),
                    ["groupIds"] = groups.DeepClone(),
                }
            ),
            ct
        );
        if (!r.B("success") || r["errors"] is JsonArray errors && errors.Count > 0)
            throw new ApiException(409, "File uploaded, but group assignment needs review.");
    }

    public async Task Verify(Record target, long artefact, JsonObject row, CancellationToken ct)
    {
        var root = Root(target, service);
        var doc = await service.Get(new(root + "/api/v1/artefacts/" + artefact), target, ct);
        if (doc.N("id") != artefact)
            throw new ApiException(502, "Destination read-back returned a different artefact.");
        foreach (var m in row["payload"]!["metadata"]!.AsArray())
        {
            var expected = m!["value"]!.AsArray().Select(v => v!.ToString()).Order().ToArray();
            var actual = (doc["metadata"] as JsonArray ?? new())
                .Where(v => v.S("key_name") == m.S("name"))
                .Select(v => v.S("value"))
                .Order()
                .ToArray();
            if (!actual.SequenceEqual(expected))
                throw new ApiException(
                    409,
                    "File uploaded, but destination metadata differs from the preview. Inspect the bucket upload rules."
                );
        }
        foreach (var g in row["groups"]!.AsArray())
            if (!(doc["groups"] as JsonArray ?? new()).Any(v => v.N("id") == g!.GetValue<long>()))
                throw new ApiException(
                    409,
                    "Destination group read-back does not match the preview."
                );
        var link = await service.Get(
            new(root + "/api/v1/artefacts/" + artefact + "/download"),
            target,
            ct
        );
        if (link.N("id") != artefact)
            throw new ApiException(502, "Destination download link returned a different artefact.");
        var bytes = await DownloadUrl(link.Required("url", 12000), ct);
        if (Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant() != row.S("sha256"))
            throw new ApiException(
                409,
                "Destination file hash did not match. No second upload was attempted."
            );
    }
}
