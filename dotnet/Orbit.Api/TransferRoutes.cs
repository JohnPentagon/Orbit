using System.Collections.Concurrent;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text.Json.Nodes;
using Microsoft.EntityFrameworkCore;

namespace Orbit.Api;

public sealed class TransferRoutes(
    OrbitDb db,
    IConfiguration cfg,
    ConnectorService reader,
    TransferVendor vendor
)
{
    static readonly ConcurrentDictionary<string, SemaphoreSlim> Locks = new();
    static long Now => DateTimeOffset.UtcNow.ToUnixTimeSeconds();

    static JsonArray Array(JsonNode? n) => n as JsonArray ?? new();

    static void Operator(Actor a)
    {
        a.Permit("connection");
        a.Permit("run");
    }

    static string Text(JsonNode? n) =>
        n is JsonValue
            ? n.ToString()
            : throw new ApiException(422, "Upload metadata must contain scalar values.");

    static string Parent(string path) => path.Contains('/') ? path[..path.LastIndexOf('/')] : "";

    static string MetadataName(string field) =>
        field.StartsWith("metadata.", StringComparison.Ordinal) ? field[9..] : field;

    async Task<(Actor Who, Record Source, Record Target)> Connections(
        HttpContext ctx,
        string project,
        string source,
        string target,
        bool sourceAccess = true
    )
    {
        var who = await Actor.Resolve(ctx, db, cfg);
        Operator(who);
        var a = await ConnectionRoutes.Scoped(db, who, project, source);
        var b = await ConnectionRoutes.Scoped(db, who, project, target);
        if (a.Data().S("provider") != "forma" || b.Data().S("provider") != "redeye")
            throw new ApiException(
                422,
                "This transfer direction supports Autodesk to RedEye only."
            );
        if (sourceAccess)
            AutodeskOAuth.FreshAccess(a);
        TransferVendor.Root(b, reader);
        return (who, a, b);
    }

    async Task<(Actor Who, Record Plan, Record Source, Record Target)> Fresh(
        HttpContext ctx,
        string project,
        string id,
        bool verification = false
    )
    {
        db.ChangeTracker.Clear();
        var who = await Actor.Resolve(ctx, db, cfg);
        Operator(who);
        await who.Project(db, project);
        var plan = await db.Find(who.Tenant, project, "transfer", id)
            ?? throw new ApiException(404, "Transfer unavailable.");
        var p = plan.Data();
        var (_, a, b) = await Connections(
            ctx,
            project,
            p.Required("source_id"),
            p.Required("target_id"),
            !verification
        );
        if (
            b.Version != p.N("target_generation")
            || !verification && (a.Version != p.N("source_generation") || p.N("expires") <= Now)
        )
            throw new ApiException(
                409,
                "Transfer preview expired or a connection changed. Prepare a fresh preview; completed items remain recorded."
            );
        if (!verification && p.S("mapping_id").Length > 0)
        {
            var m = await db.Find(who.Tenant, project, "mapping", p.S("mapping_id"));
            if (m == null || m.Data().B("deleted") || m.Version != p.N("mapping_version"))
                throw new ApiException(409, "Mapping profile changed. Prepare a new preview.");
        }
        if (
            !verification
            && p["reference_version"] != null
            && (await db.Find(who.Tenant, project, "bsdd", "reference"))?.Version
                != p.N("reference_version")
        )
            throw new ApiException(409, "Property reference changed. Prepare a new preview.");
        return (who, plan, a, b);
    }

    async Task SaveRow(Actor who, string project, string id, JsonObject row, string action)
    {
        var tenant = who.Tenant;
        db.ChangeTracker.Clear();
        var plan = await db.Find(tenant, project, "transfer", id)
            ?? throw new ApiException(404, "Transfer unavailable.");
        var p = plan.Data();
        var rows = p["items"]!.AsArray();
        var index = rows.Select((r, n) => (r, n)).First(x => x.r.S("id") == row.S("id")).n;
        rows[index] = row.DeepClone();
        db.Change(plan, p);
        // No metadata values, file bytes, signed URLs or credentials in the audit event.
        db.Add(
            tenant,
            project,
            "audit",
            Guid.NewGuid().ToString(),
            new()
            {
                ["action"] = action,
                ["created"] = DateTimeOffset.UtcNow.ToString("O"),
                ["actor"] = who.Id,
                ["transfer"] = id,
                ["item"] = row.S("id"),
                ["status"] = row.S("status"),
            }
        );
        await db.SaveChangesAsync();
    }

    async Task Receipt(
        string tenant,
        string project,
        string key,
        string status,
        long artefact,
        string transfer,
        string item
    )
    {
        var r = await db.Find(tenant, project, "transfer-receipt", key);
        if (r == null || r.Data().S("transfer") != transfer || r.Data().S("item") != item)
            return;
        var d = r.Data();
        d["status"] = status;
        d["artefact_id"] = artefact;
        db.Change(r, d);
        await db.SaveChangesAsync();
    }

    public async Task<JsonObject> LoadSource(HttpContext ctx, string project, string source)
    {
        var who = await Actor.Resolve(ctx, db, cfg);
        Operator(who);
        var a = await ConnectionRoutes.Scoped(db, who, project, source);
        if (a.Data().S("provider") != "forma" || a.Data()["configuration"].S("folder").Length == 0)
            throw new ApiException(
                422,
                "Choose an Autodesk connection with a saved folder/file scope."
            );
        var generation = a.Version;
        var read = await reader.Read(a, new() { ["operation"] = "documents" }, ctx.RequestAborted);
        db.ChangeTracker.Clear();
        who = await Actor.Resolve(ctx, db, cfg);
        Operator(who);
        a = await ConnectionRoutes.Scoped(db, who, project, source);
        if (a.Version != generation)
            throw new ApiException(409, "Source changed while loading files.");
        var records = new JsonArray(
            Array(read["resources"])
                .Where(r => r.S("kind") == "items")
                .Select(r => r!.DeepClone())
                .ToArray()
        );
        var id = Guid.NewGuid().ToString();
        db.Add(
            who.Tenant,
            project,
            "transfer-sample",
            id,
            new()
            {
                ["source_id"] = source,
                ["generation"] = generation,
                ["expires"] = Now + 1800,
                ["records"] = records.DeepClone(),
                ["coverage"] = read.S("coverage"),
            }
        );
        await db.SaveChangesAsync();
        return new()
        {
            ["id"] = id,
            ["files"] = new JsonArray(
                records
                    .Select(r =>
                        (JsonNode)
                            new JsonObject
                            {
                                ["id"] = r.S("id"),
                                ["name"] = r.S("label"),
                                ["path"] = r?["fields"].S("orbit.relative_path", r.S("label")),
                            }
                    )
                    .ToArray()
            ),
            ["coverage"] = read.S("coverage"),
        };
    }

    public async Task<JsonObject> Prepare(HttpContext ctx, string project, JsonObject body)
    {
        var (who, a, b) = await Connections(
            ctx,
            project,
            body.Required("source_id"),
            body.Required("target_id")
        );
        var sourceGeneration = a.Version;
        var targetGeneration = b.Version;
        var sample = await db.Find(
            who.Tenant,
            project,
            "transfer-sample",
            body.Required("sample_id")
        ) ?? throw new ApiException(409, "Load source files first.");
        if (
            sample.Data().S("source_id") != a.Id
            || sample.Data().N("generation") != a.Version
            || sample.Data().N("expires") <= Now
        )
            throw new ApiException(409, "Reload the source file selection.");
        var ids = Array(body["file_ids"]).Select(v => v?.ToString() ?? "").ToArray();
        if (ids.Length is < 1 or > 10 || ids.Distinct().Count() != ids.Length)
            throw new ApiException(422, "Choose 1–10 distinct source files for this UAT batch.");
        var quality = body.S("quality_mode", "validate");
        var structure = body.S("structure", "flat");
        var type = body.S("artefact_type", "document");
        var conflict = body.S("conflict_policy", "skip");
        if (
            !new[] { "validate", "skip" }.Contains(quality)
            || !new[] { "flat", "path_metadata", "group_map" }.Contains(structure)
            || !new[] { "document", "drawing", "media" }.Contains(type)
            || !new[] { "skip", "stop" }.Contains(conflict)
        )
            throw new ApiException(422, "Choose supported transfer options.");
        if (!body.B("rules_confirmed"))
            throw new ApiException(
                422,
                "Confirm how the destination bucket upload rules handle these metadata keys and revisions."
            );
        var inventory = await vendor.Inventory(b, ctx.RequestAborted);
        var mappingId = body.S("mapping_id");
        Record? mapping = null;
        JsonObject? reference = null;
        var rules = new JsonArray();
        if (mappingId.Length > 0)
        {
            mapping = await db.Find(who.Tenant, project, "mapping", mappingId)
                ?? throw new ApiException(404, "Mapping unavailable.");
            var m = mapping.Data();
            if (
                m.B("deleted")
                || m["source"].S("id") != a.Id
                || m["target"].S("id") != b.Id
                || !JsonNode.DeepEquals(m["source"]?["scope"], a.Data()["configuration"])
            )
                throw new ApiException(
                    409,
                    "The profile source/destination or saved source scope does not match this transfer."
                );
            rules = m["rules"]!.DeepClone().AsArray();
            if (m["reference_version"] != null)
            {
                var r = await db.Find(who.Tenant, project, "bsdd", "reference");
                if (r?.Version != m.N("reference_version"))
                    throw new ApiException(409, "Refresh the profile's property reference first.");
                reference = r.Data();
            }
        }
        var constant = body["metadata"] as JsonObject ?? new();
        if (constant.Count > 50)
            throw new ApiException(422, "Use at most 50 upload-rule metadata keys.");
        var groupMap = body["group_map"] as JsonObject ?? new();
        var rows = new JsonArray();
        foreach (var id in ids)
        {
            var file = Array(sample.Data()["records"]).FirstOrDefault(r => r.S("id") == id)
                ?? throw new ApiException(422, "Choose files from the loaded source scope.");
            var current = await vendor.Version(a, id, ctx.RequestAborted);
            if (file.S("label") != current.S("name"))
                throw new ApiException(409, "A source file name changed. Reload the file list.");
            var fields = current["fields"]!.DeepClone().AsObject();
            var path = file["fields"].S("orbit.relative_path", current.S("name"));
            if (
                path.Length > 4000
                || path.Split('/').Any(v => v is ".." or "." || v.Any(char.IsControl))
            )
                throw new ApiException(422, "Unsupported source folder path.");
            fields["orbit.relative_path"] = path;
            var metadata = new JsonObject();
            var issues = new JsonArray();
            foreach (var rule in rules)
            {
                var field = rule!.Required("source_field");
                var value = AnalysisRoutes.Transform(fields[field], rule.S("transform", "copy"));
                var key = MetadataName(rule!.Required("target_field"));
                if (quality == "validate")
                {
                    if (value == null || value.ToString() == "[not captured]")
                        issues.Add("Source parameter not captured: " + field);
                    if (rule.S("property_uri").Length > 0)
                        foreach (
                            var issue in Validation.Value(
                                value,
                                Validation.Property(reference, rule.S("property_uri")),
                                rule.S("unit"),
                                rule.B("required"),
                                rule.B("interpret_strings")
                            )
                        )
                            issues.Add(key + ": " + issue);
                    else if (
                        rule.B("required")
                        && (
                            value == null
                            || value.ToString().Trim().Length == 0
                            || value is JsonArray list && list.Count == 0
                        )
                    )
                        issues.Add("Required value missing: " + key);
                }
                if (value != null)
                    metadata[key] = value.DeepClone();
            }
            foreach (var c in constant)
            {
                if (metadata.ContainsKey(c.Key))
                    throw new ApiException(422, "A constant metadata key duplicates a mapped key.");
                metadata[c.Key] = c.Value?.DeepClone();
            }
            if (structure == "path_metadata")
            {
                var key = body.Required("path_key", 200);
                if (metadata.ContainsKey(key))
                    throw new ApiException(
                        422,
                        "The source-path key duplicates another metadata key."
                    );
                metadata[key] = path;
            }
            var groups = new JsonArray();
            if (structure == "group_map")
            {
                var folder = Parent(path);
                var selected = groupMap.N(folder);
                if (!Array(inventory["groups"]).Any(g => g.N("id") == selected))
                    throw new ApiException(
                        422,
                        "Choose an existing destination group for every selected source folder."
                    );
                groups.Add(selected);
            }
            else if (body.N("group_id") > 0)
            {
                if (!Array(inventory["groups"]).Any(g => g.N("id") == body.N("group_id")))
                    throw new ApiException(
                        422,
                        "Choose a group returned by the destination connection."
                    );
                groups.Add(body.N("group_id"));
            }
            if (
                metadata.Select(m => m.Key).Distinct(StringComparer.OrdinalIgnoreCase).Count()
                != metadata.Count
            )
                throw new ApiException(422, "Upload metadata contains case-ambiguous keys.");
            var payloadMetadata = new JsonArray();
            foreach (var m in metadata)
            {
                if (m.Key.Length is < 1 or > 200 || m.Key.Any(char.IsControl))
                    throw new ApiException(
                        422,
                        "Use a non-empty upload metadata key without control characters."
                    );
                var values =
                    m.Value is JsonArray list ? list.Select(Text).ToArray()
                    : m.Value == null ? System.Array.Empty<string>()
                    : new[] { Text(m.Value) };
                if (values.Length > 100 || values.Any(v => v.Length > 10000))
                    throw new ApiException(422, "Upload metadata exceeds the supported length.");
                payloadMetadata.Add(
                    new JsonObject
                    {
                        ["name"] = m.Key,
                        ["value"] = new JsonArray(
                            values.Select(v => (JsonNode)JsonValue.Create(v)!).ToArray()
                        ),
                    }
                );
            }
            if (System.Text.Encoding.UTF8.GetByteCount(payloadMetadata.ToJsonString()) > 100_000)
                throw new ApiException(422, "Upload metadata exceeds the 100 KB UAT limit.");
            rows.Add(
                new JsonObject
                {
                    ["id"] = Guid.NewGuid().ToString(),
                    ["source_item"] = id,
                    ["path"] = path,
                    ["source"] = current.DeepClone(),
                    ["source_version"] = current.S("version"),
                    ["source_size"] = current.N("size"),
                    ["name"] = current.S("name"),
                    ["payload"] = new JsonObject
                    {
                        ["type"] = type,
                        ["noFile"] = false,
                        ["metadata"] = payloadMetadata,
                    },
                    ["groups"] = groups,
                    ["group_labels"] = new JsonArray(
                        groups
                            .Select(g =>
                                (JsonNode)
                                    JsonValue.Create(
                                        Array(inventory["groups"])
                                            .First(v => v.N("id") == g!.GetValue<long>())
                                            .S("name")
                                    )!
                            )
                            .ToArray()
                    ),
                    ["issues"] = issues,
                    ["status"] = issues.Count > 0 ? "blocked" : "ready",
                    ["message"] = "",
                }
            );
        }
        db.ChangeTracker.Clear();
        (who, a, b) = await Connections(ctx, project, a.Id, b.Id);
        if (a.Version != sourceGeneration || b.Version != targetGeneration)
            throw new ApiException(409, "A connection changed while preparing this preview.");
        if (
            mapping != null
            && (await db.Find(who.Tenant, project, "mapping", mappingId))?.Version
                != mapping.Version
        )
            throw new ApiException(409, "Mapping changed while preparing preview.");
        var plan = new JsonObject
        {
            ["source_id"] = a.Id,
            ["target_id"] = b.Id,
            ["source_name"] = a.Data().S("name"),
            ["target_name"] = b.Data().S("name"),
            ["source_generation"] = a.Version,
            ["target_generation"] = b.Version,
            ["mapping_id"] = mappingId,
            ["mapping_version"] = mapping?.Version ?? 0,
            ["reference_version"] = mapping?.Data()["reference_version"]?.DeepClone(),
            ["inventory_digest"] = RedEyeRoutes.Digest(inventory),
            ["quality_mode"] = quality,
            ["structure"] = structure,
            ["conflict_policy"] = conflict,
            ["expires"] = Now + 1800,
            ["created"] = DateTimeOffset.UtcNow.ToString("O"),
            ["items"] = rows,
        };
        var planId = Guid.NewGuid().ToString();
        db.Add(who.Tenant, project, "transfer", planId, plan);
        db.Audit(who, "transfer.preview_prepared", project, planId);
        await db.SaveChangesAsync();
        plan["id"] = planId;
        return plan;
    }

    public async Task<JsonObject> Execute(
        HttpContext ctx,
        string project,
        string id,
        string itemId,
        JsonObject body,
        bool reconcile
    )
    {
        if (!cfg.GetValue<bool>("Orbit:EnableFileTransfers"))
            throw new ApiException(
                409,
                "File copy execution is disabled. Set Orbit__EnableFileTransfers=true in the Azure App Service environment; previews remain available."
            );
        if (!body.B("confirmed"))
            throw new ApiException(422, "Confirm the exact reviewed file copy.");
        var actor = await Actor.Resolve(ctx, db, cfg);
        Operator(actor);
        await actor.Project(db, project);
        var gate = Locks.GetOrAdd(actor.Tenant + ":" + project + ":" + id, _ => new(1));
        if (!await gate.WaitAsync(0))
            throw new ApiException(
                409,
                "A file in this batch is already running. Refresh its history."
            );
        try
        {
            var (who, record, a, b) = await Fresh(ctx, project, id, reconcile);
            var plan = record.Data();
            var row = Array(plan["items"])
                .FirstOrDefault(r => r.S("id") == itemId)
                ?.DeepClone()
                .AsObject()
                ?? throw new ApiException(404, "Transfer file unavailable.");
            if (row.S("status") is "completed" or "skipped")
                return row;
            if (
                body.S("preview_digest")
                != RedEyeRoutes.Digest(
                    new JsonObject
                    {
                        ["source"] = row["source"]!.DeepClone(),
                        ["payload"] = row["payload"]!.DeepClone(),
                        ["groups"] = row["groups"]!.DeepClone(),
                    }
                )
            )
                throw new ApiException(
                    409,
                    "The reviewed file preview changed. Refresh before copying."
                );
            if (!reconcile && row.S("status") is not ("ready" or "failed"))
                throw new ApiException(
                    409,
                    "This item is blocked, running or uncertain. Recheck the destination; do not repeat its upload."
                );
            if (
                reconcile
                && row.S("status") is not ("uncertain" or "uploaded_needs_review" or "in_progress")
            )
                throw new ApiException(409, "This item does not need destination reconciliation.");
            var inventory = await vendor.Inventory(b, ctx.RequestAborted);
            if (!reconcile && RedEyeRoutes.Digest(inventory) != plan.S("inventory_digest"))
                throw new ApiException(
                    409,
                    "Destination keys/groups changed. Prepare a new preview."
                );
            using var deadline = CancellationTokenSource.CreateLinkedTokenSource(
                ctx.RequestAborted
            );
            deadline.CancelAfter(TimeSpan.FromSeconds(180));
            var ct = deadline.Token;
            var uploadStarted = false;
            var ownsReservation = false;
            var key = row.S("receipt");
            try
            {
                if (!reconcile)
                {
                    var version = await vendor.Version(a, row.Required("source_item"), ct);
                    if (RedEyeRoutes.Digest(version) != RedEyeRoutes.Digest(row["source"]!))
                        throw new ApiException(
                            409,
                            "Source version or metadata changed. Prepare a new preview."
                        );
                    var bytes = await vendor.Download(a, version.Required("storage", 3000), ct);
                    if (version.N("size") > 0 && bytes.LongLength != version.N("size"))
                        throw new ApiException(
                            502,
                            "Source download size did not match the reviewed version."
                        );
                    (who, record, a, b) = await Fresh(ctx, project, id);
                    var sha = Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant();
                    row["sha256"] = sha;
                    key = RedEyeRoutes.Digest(new JsonArray(b.Id, sha));
                    row["receipt"] = key;
                    var previous = await db.Find(who.Tenant, project, "transfer-receipt", key);
                    if (
                        previous != null
                        && !(
                            previous.Data().S("transfer") == id
                            && previous.Data().S("item") == itemId
                            && previous.Data().S("status") == "not_sent"
                        )
                    )
                    {
                        if (previous.Data().S("status") != "completed")
                            throw new ApiException(
                                409,
                                "An earlier upload of these bytes is unresolved. Recheck its destination before another copy."
                            );
                        row["status"] = plan.S("conflict_policy") == "skip" ? "skipped" : "blocked";
                        row["message"] =
                            "Identical bytes were already copied by ORBIT to this connection.";
                        await SaveRow(who, project, id, row, "transfer.duplicate_detected");
                        return row;
                    }
                    if (
                        await vendor.Exists(
                            b,
                            sha,
                            Convert.ToHexString(MD5.HashData(bytes)).ToLowerInvariant(),
                            ct
                        )
                    )
                    {
                        row["status"] = plan.S("conflict_policy") == "skip" ? "skipped" : "blocked";
                        row["message"] =
                            "RedEye reported an existing content hash; no upload was sent.";
                        await SaveRow(who, project, id, row, "transfer.duplicate_detected");
                        return row;
                    }
                    (who, record, a, b) = await Fresh(ctx, project, id);
                    if (previous == null)
                        db.Add(
                            who.Tenant,
                            project,
                            "transfer-receipt",
                            key,
                            new()
                            {
                                ["transfer"] = id,
                                ["item"] = itemId,
                                ["status"] = "reserved",
                            }
                        );
                    else
                    {
                        previous = (await db.Find(who.Tenant, project, "transfer-receipt", key))!;
                        var d = previous.Data();
                        d["status"] = "reserved";
                        db.Change(previous, d);
                    }
                    // Reserve the content hash and in-progress row in one transaction.
                    row["status"] = "in_progress";
                    var reservedPlan = record.Data();
                    var reservedRows = reservedPlan["items"]!.AsArray();
                    var reservedIndex = Enumerable
                        .Range(0, reservedRows.Count)
                        .First(n => reservedRows[n].S("id") == itemId);
                    reservedRows[reservedIndex] = row.DeepClone();
                    db.Change(record, reservedPlan);
                    db.Audit(who, "transfer.upload_reserved", project, id);
                    try
                    {
                        await db.SaveChangesAsync();
                        ownsReservation = true;
                    }
                    catch (DbUpdateException)
                    {
                        throw new ApiException(
                            409,
                            "Another transfer reserved these bytes. Inspect its history before retrying."
                        );
                    }
                    var payload = row["payload"]!.DeepClone().AsObject();
                    payload["artefactHash"] = new JsonObject
                    {
                        ["sha256"] = sha,
                        ["md5"] = Convert.ToHexString(MD5.HashData(bytes)).ToLowerInvariant(),
                    };
                    (who, record, a, b) = await Fresh(ctx, project, id);
                    // The durable reservation precedes the first irreversible request. No automatic HTTP retry.
                    uploadStarted = true;
                    var response = await vendor.Upload(b, bytes, row.Required("name"), payload, ct);
                    var artefact = response.N("artefact_id", response["artefact"].N("id"));
                    if (
                        artefact <= 0
                        || response["artefact"] != null
                            && response["artefact"].N("id") > 0
                            && response["artefact"].N("id") != artefact
                    )
                        throw new ApiException(
                            502,
                            "Upload response did not identify one destination artefact."
                        );
                    row["artefact_id"] = artefact;
                    row["revision_action"] = response.S("revision_action");
                    row["status"] = "uploaded_needs_review";
                    await SaveRow(who, project, id, row, "transfer.upload_response_received");
                    await Receipt(who.Tenant, project, key, "uploaded", artefact, id, itemId);
                }
                else
                {
                    if (row.S("sha256").Length == 0)
                        throw new ApiException(
                            409,
                            "No content hash was recorded. Inspect this item manually; do not resend it."
                        );
                    var artefact = body.N("artefact_id", row.N("artefact_id"));
                    if (
                        artefact <= 0
                        || row.N("artefact_id") > 0 && row.N("artefact_id") != artefact
                    )
                        throw new ApiException(
                            422,
                            "Use the destination artefact identified by the upload result."
                        );
                    row["artefact_id"] = artefact;
                }
                // Read-back and group operations may be resumed without repeating the upload.
                (who, record, a, b) = await Fresh(ctx, project, id, true);
                {
                    // Verify the returned artefact bytes before changing any group associations.
                    var root = TransferVendor.Root(b, reader);
                    var link = await reader.Get(
                        new(root + "/api/v1/artefacts/" + row.N("artefact_id") + "/download"),
                        b,
                        ct
                    );
                    if (link.N("id") != row.N("artefact_id"))
                        throw new ApiException(
                            409,
                            "The destination link identifies a different artefact."
                        );
                    var bytes = await vendor.DownloadUrl(link.Required("url", 12000), ct);
                    if (
                        Convert.ToHexString(SHA256.HashData(bytes)).ToLowerInvariant()
                        != row.S("sha256")
                    )
                        throw new ApiException(
                            409,
                            "Destination bytes do not match this transfer. No group change was sent."
                        );
                }
                (who, record, a, b) = await Fresh(ctx, project, id, true);
                await vendor.Assign(b, row.N("artefact_id"), row["groups"]!.AsArray(), ct);
                await vendor.Verify(b, row.N("artefact_id"), row, ct);
                await Fresh(ctx, project, id, true);
                row["status"] = "completed";
                row["message"] =
                    "Destination file hash, mapped metadata and groups verified. Source retained.";
                await SaveRow(who, project, id, row, "transfer.completed");
                await Receipt(
                    who.Tenant,
                    project,
                    key,
                    "completed",
                    row.N("artefact_id"),
                    id,
                    itemId
                );
                return row;
            }
            catch (Exception e)
                when (e
                        is ApiException
                            or HttpRequestException
                            or OperationCanceledException
                            or System.Text.Json.JsonException
                )
            {
                row["status"] =
                    row.N("artefact_id") > 0 ? "uploaded_needs_review"
                    : uploadStarted || reconcile ? "uncertain"
                    : "failed";
                row["message"] =
                    e is ApiException ae ? ae.Message
                    : uploadStarted || reconcile
                        ? "The destination outcome is uncertain. Recheck before any further upload."
                    : "File preparation/download failed. No upload was sent; an explicit retry is available.";
                await SaveRow(who, project, id, row, "transfer.item_stopped");
                if (key.Length > 0 && (ownsReservation || reconcile))
                    await Receipt(
                        who.Tenant,
                        project,
                        key,
                        row.S("status") == "failed" ? "not_sent" : row.S("status"),
                        row.N("artefact_id"),
                        id,
                        itemId
                    );
                return row;
            }
        }
        finally
        {
            gate.Release();
        }
    }

    public static JsonObject Public(Record record)
    {
        var p = record.Data();
        p["id"] = record.Id;
        foreach (var row in Array(p["items"]))
        {
            row!["preview_digest"] = RedEyeRoutes.Digest(
                new JsonObject
                {
                    ["source"] = row["source"]!.DeepClone(),
                    ["payload"] = row["payload"]!.DeepClone(),
                    ["groups"] = row["groups"]!.DeepClone(),
                }
            );
            row.AsObject().Remove("source");
        }
        return p;
    }

    public static void Map(WebApplication app)
    {
        const string root = "/api/projects/{project}/transfers";
        app.MapGet(root, async (string project, HttpContext ctx, OrbitDb db, IConfiguration cfg) =>
        {
            var who = await Actor.Resolve(ctx, db, cfg);
            await who.Project(db, project);
            return Results.Ok(
                new
                {
                    enabled = cfg.GetValue<bool>("Orbit:EnableFileTransfers"),
                    direction = "Autodesk → RedEye",
                    connections = (await db.List(who.Tenant, project, "connection"))
                        .Where(r => new[] { "forma", "redeye" }.Contains(r.Data().S("provider")))
                        .Select(r => new
                        {
                            id = r.Id,
                            name = r.Data().S("name"),
                            provider = r.Data().S("provider"),
                        }),
                    mappings = (await db.List(who.Tenant, project, "mapping"))
                        .Where(r => !r.Data().B("deleted"))
                        .Select(r => new
                        {
                            id = r.Id,
                            name = r.Data().S("name"),
                            source_id = r.Data()["source"].S("id"),
                            target_id = r.Data()["target"].S("id"),
                        }),
                    runs = (await db.List(who.Tenant, project, "transfer")).Take(50).Select(Public),
                }
            );
        });
        app.MapPost(
            root + "/sources/{id}",
            async (string project, string id, HttpContext ctx, TransferRoutes transfers) =>
                Results.Ok(await transfers.LoadSource(ctx, project, id))
        );
        app.MapPost(
            root + "/targets/{id}",
            async (
                string project,
                string id,
                HttpContext ctx,
                OrbitDb db,
                IConfiguration cfg,
                TransferVendor vendor
            ) =>
            {
                var who = await Actor.Resolve(ctx, db, cfg);
                Operator(who);
                var r = await ConnectionRoutes.Scoped(db, who, project, id);
                return Results.Ok(await vendor.Inventory(r, ctx.RequestAborted));
            }
        );
        app.MapPost(
            root + "/preview",
            async (
                string project,
                JsonObject body,
                HttpContext ctx,
                TransferRoutes transfers,
                OrbitDb db,
                IConfiguration cfg
            ) =>
            {
                var p = await transfers.Prepare(ctx, project, body);
                var r = (
                    await db.Find(
                        (await Actor.Resolve(ctx, db, cfg)).Tenant,
                        project,
                        "transfer",
                        p.S("id")
                    )
                )!;
                return Results.Ok(Public(r));
            }
        );
        foreach (var action in new[] { "execute", "recheck" })
        {
            var reconcile = action == "recheck";
            app.MapPost(
                root + "/{id}/items/{item}/" + action,
                async (
                    string project,
                    string id,
                    string item,
                    JsonObject body,
                    HttpContext ctx,
                    TransferRoutes transfers
                ) => Results.Ok(await transfers.Execute(ctx, project, id, item, body, reconcile))
            );
        }
    }
}
