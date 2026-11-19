using System.Text;
using System.Text.Json.Nodes;

namespace Orbit.Api;

/// <summary>Fixed-endpoint folder metadata reads with explicit sample or complete-scope coverage.</summary>
public static class AutodeskDocuments
{
    public const int PageSize = 25;
    public const int MaxPages = 40;
    public const int MaxFiles = 250;

    public static string Identifier(string value)
    {
        if (
            value.Length is < 1 or > 500
            || value is "." or ".."
            || value.Any(c => char.IsControl(c) || char.IsWhiteSpace(c) || "/\\?#".Contains(c))
        )
            throw new ApiException(422, "Select an Autodesk folder or file returned by discovery.");
        return value;
    }

    public static bool HasMore(JsonObject payload, int count)
    {
        if (payload["links"] is JsonObject links && links.ContainsKey("next"))
        {
            var next = links["next"];
            return next is JsonObject o
                ? o.S("href").Length > 0
                : next is JsonValue s && s.TryGetValue<string>(out var href) && href.Length > 0;
        }
        return count == PageSize;
    }

    public static async Task<(JsonArray Rows, bool More)> Page(
        ConnectorService reader,
        Record profile,
        string project,
        string folder,
        int page,
        CancellationToken ct,
        bool scan = false
    )
    {
        if (page < 0 || page >= (scan ? ScanPages : MaxPages))
            throw new ApiException(
                422,
                "Folder browsing supports up to 40 pages. Select a smaller folder if needed."
            );
        var url =
            AutodeskOAuth.Api
            + "/data/v1/projects/"
            + Uri.EscapeDataString(Identifier(project))
            + "/folders/"
            + Uri.EscapeDataString(Identifier(folder))
            + "/contents?page%5Blimit%5D=25&page%5Bnumber%5D="
            + page;
        var data = await reader.Get(new Uri(url), profile, ct);
        if (
            data is not JsonObject payload
            || payload["data"] is not JsonArray rows
            || rows.Count > PageSize
        )
            throw new ApiException(502, "Autodesk returned an invalid folder page.");
        return (rows, HasMore(payload, rows.Count));
    }

    public static JsonObject Resource(JsonNode? item, string secret)
    {
        if (item is not JsonObject row || !new[] { "items", "folders" }.Contains(row.S("type")))
            throw new ApiException(502, "Autodesk returned an unsupported folder entry.");
        string id;
        try
        {
            id = Identifier(row.Required("id", 500));
        }
        catch (ApiException)
        {
            throw new ApiException(502, "Autodesk returned an invalid folder entry identifier.");
        }
        if (secret.Length > 0 && id.Contains(secret, StringComparison.Ordinal))
            throw new ApiException(502, "Autodesk returned an invalid folder entry identifier.");
        var label = row["attributes"].S("displayName", row["attributes"].S("name", id));
        if (label.Length > 500)
            label = label[..500];
        if (secret.Length > 0)
            label = label.Replace(secret, "[REDACTED]", StringComparison.Ordinal);
        return new()
        {
            ["id"] = id,
            ["label"] = label,
            ["kind"] = row.S("type"),
            ["fields"] = ConnectorService.Flatten(row, secret: secret),
        };
    }

    public static string[] Selected(JsonNode? node)
    {
        if (node == null)
            return [];
        if (node is not JsonArray array || array.Count > MaxFiles)
            throw new ApiException(422, "Select at most 250 files.");
        var values = array
            .Select(v =>
                v is JsonValue scalar && scalar.TryGetValue<string>(out var text)
                    ? Identifier(text)
                    : throw new ApiException(422, "Choose file IDs returned by the folder browser.")
            )
            .ToArray();
        if (values.Distinct(StringComparer.Ordinal).Count() != values.Length)
            throw new ApiException(422, "Select each file only once.");
        return values;
    }

    public const int ScanFiles = 5000;
    public const int ScanFolders = 500;
    public const int ScanPages = 1000;
    public const int ScanBytes = 16_000_000;

    // Fail closed: a whole-folder scope never produces a partial snapshot.
    static async Task<JsonObject> ReadFolder(
        ConnectorService reader,
        Record profile,
        string secret,
        CancellationToken ct
    )
    {
        var config = profile.Data()["configuration"]!;
        if (Selected(config["file_ids"]).Length > 0)
            throw new ApiException(
                409,
                "Whole-folder mode cannot include an individual-file selection."
            );
        var project = Identifier(config.Required("vendor_project"));
        var root = Identifier(config.Required("folder"));
        var recursive = config.B("include_subfolders");
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
        deadline.CancelAfter(TimeSpan.FromSeconds(180));
        var pending = new Queue<(string Id, string Path, int Depth)>();
        pending.Enqueue((root, "", 0));
        var folders = new HashSet<string>(StringComparer.Ordinal) { root };
        var files = new HashSet<string>(StringComparer.Ordinal);
        var resources = new JsonArray();
        var pages = 0;
        var visited = 0;
        var excluded = 0;
        var bytes = 0;
        try
        {
            while (pending.Count > 0)
            {
                var current = pending.Dequeue();
                visited++;
                var seen = new HashSet<string>(StringComparer.Ordinal);
                for (var page = 0; ; page++)
                {
                    if (++pages > ScanPages)
                        throw new ApiException(
                            422,
                            "Whole-folder scan exceeds 1,000 pages. Choose a smaller folder; no partial comparison evidence was saved."
                        );
                    var result = await Page(
                        reader,
                        profile,
                        project,
                        current.Id,
                        page,
                        deadline.Token,
                        scan: true
                    );
                    var added = 0;
                    foreach (var row in result.Rows)
                    {
                        var item = Resource(row, secret);
                        var id = item.S("id");
                        if (!seen.Add(id))
                            continue;
                        added++;
                        if (item.S("kind") == "folders")
                        {
                            if (!recursive)
                            {
                                excluded++;
                                continue;
                            }
                            if (!folders.Add(id))
                                throw new ApiException(
                                    502,
                                    "Autodesk returned a repeated or cyclic folder. No partial comparison evidence was saved."
                                );
                            if (folders.Count > ScanFolders || current.Depth >= 64)
                                throw new ApiException(
                                    422,
                                    "Whole-folder scan exceeds 500 folders or 64 levels. Choose a smaller folder; no partial comparison evidence was saved."
                                );
                            pending.Enqueue(
                                (id, current.Path + item.S("label") + "/", current.Depth + 1)
                            );
                            continue;
                        }
                        if (!files.Add(id))
                            continue;
                        if (files.Count > ScanFiles)
                            throw new ApiException(
                                422,
                                "Whole-folder scan exceeds 5,000 files. Choose a smaller folder; no partial comparison evidence was saved."
                            );
                        item["fields"]!["orbit.relative_path"] = current.Path + item.S("label");
                        bytes += Encoding.UTF8.GetByteCount(item.ToJsonString());
                        if (bytes > ScanBytes)
                            throw new ApiException(
                                422,
                                "Whole-folder metadata exceeds 16 MB. Choose a smaller folder; no partial comparison evidence was saved."
                            );
                        resources.Add(item);
                    }
                    if (result.More && added == 0)
                        throw new ApiException(
                            502,
                            "Autodesk returned an empty or repeated continuation page. No partial comparison evidence was saved."
                        );
                    if (!result.More)
                        break;
                }
            }
        }
        catch (OperationCanceledException) when (!ct.IsCancellationRequested)
        {
            throw new ApiException(
                409,
                "Whole-folder scan timed out (180-second overall limit). Choose a smaller folder; no partial comparison evidence was saved."
            );
        }
        return new()
        {
            ["operation"] = "documents",
            ["resources"] = resources,
            ["returned"] = resources.Count,
            ["coverage"] =
                $"Completed selected folder scope: {resources.Count} files across {visited} folders and {pages} pages. "
                + (
                    recursive
                        ? "All returned descendant folders included. "
                        : $"Direct contents only; {excluded} subfolder entries excluded. "
                )
                + "Vendor-reported accessible contents at read time; concurrent changes and permission-hidden content cannot be detected. Metadata only, no file bytes downloaded.",
            ["scope_complete"] = true,
            ["include_subfolders"] = recursive,
            ["folders_read"] = visited,
            ["pages_read"] = pages,
            ["more_available"] = false,
            ["synthetic"] = false,
            ["imported"] = 0,
            ["files_transferred"] = 0,
        };
    }

    public static async Task<JsonObject> Read(
        ConnectorService reader,
        Record profile,
        string secret,
        CancellationToken ct
    )
    {
        var mode = profile.Data()["configuration"].S("read_mode", "sample");
        if (mode == "folder")
            return await ReadFolder(reader, profile, secret, ct);
        if (mode != "sample")
            throw new ApiException(409, "Choose a supported Autodesk read mode.");
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(ct);
        deadline.CancelAfter(TimeSpan.FromSeconds(90));
        ct = deadline.Token;
        var config = profile.Data()["configuration"]!;
        var project = Identifier(config.Required("vendor_project"));
        var folder = Identifier(config.Required("folder"));
        var limit = config.N("document_limit", 25);
        if (!new long[] { 25, 100, 250 }.Contains(limit))
            throw new ApiException(
                409,
                "Choose a supported file read limit in the Autodesk browser."
            );
        var selected = Selected(config["file_ids"]).ToHashSet(StringComparer.Ordinal);
        if (selected.Count > limit)
            throw new ApiException(
                409,
                "The file selection exceeds its comparison read limit. Review the Autodesk selection."
            );
        var resources = new JsonArray();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        var pages = 0;
        var folders = 0;
        var more = false;
        var bounded = false;
        for (var page = 0; page < MaxPages; page++)
        {
            var result = await Page(reader, profile, project, folder, page, ct);
            pages++;
            more = result.More;
            var newEntries = 0;
            foreach (var row in result.Rows)
            {
                var resource = Resource(row, secret);
                if (!seen.Add(resource.S("id")))
                    continue;
                newEntries++;
                if (resource.S("kind") == "folders")
                {
                    folders++;
                    continue;
                }
                if (selected.Count > 0 && !selected.Contains(resource.S("id")))
                    continue;
                if (resources.Count >= limit)
                {
                    bounded = true;
                    break;
                }
                resources.Add(resource);
            }
            if (result.Rows.Count > 0 && newEntries == 0)
                throw new ApiException(
                    502,
                    "Autodesk repeated a results page. Refresh the folder rather than treating it as complete."
                );
            if (resources.ToJsonString().Length > 2_000_000)
                throw new ApiException(
                    422,
                    "Selected file metadata exceeds the UAT read size. Choose fewer files."
                );
            if (selected.Count > 0 && resources.Count == selected.Count)
                break;
            if (resources.Count >= limit)
            {
                bounded = more || bounded;
                break;
            }
            if (!more)
                break;
            if (page == MaxPages - 1)
                bounded = true;
        }
        if (selected.Count > 0 && resources.Count != selected.Count)
            throw new ApiException(
                409,
                "Some selected files were not found in this folder within the paged read bound. Refresh the folder and review the file selection."
            );
        var coverage =
            selected.Count > 0
                ? $"Metadata for {resources.Count} explicitly selected files in this folder; {pages} pages checked."
                : $"Metadata for {resources.Count} files in this folder; {pages} pages checked; comparison limit {limit}.";
        coverage +=
            $" {folders} subfolder entries excluded. "
            + (bounded ? "More folder data may remain. " : "")
            + "Descendant folders are not read recursively. No file bytes downloaded; not a whole-project comparison.";
        return new()
        {
            ["operation"] = "documents",
            ["resources"] = resources,
            ["returned"] = resources.Count,
            ["coverage"] = coverage,
            ["synthetic"] = false,
            ["imported"] = 0,
            ["files_transferred"] = 0,
            ["pages_read"] = pages,
            ["more_available"] = bounded,
            ["selected_files"] = selected.Count,
            ["read_limit"] = limit,
        };
    }
}
