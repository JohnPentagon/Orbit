using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using Microsoft.EntityFrameworkCore;

namespace Orbit.Api;

public static class RedEyeRoutes
{
    public static string Digest(JsonNode value)
    {
        JsonNode? Sort(JsonNode? n) =>
            n switch
            {
                JsonObject o => new JsonObject(
                    o.OrderBy(p => p.Key, StringComparer.Ordinal)
                        .Select(p => new KeyValuePair<string, JsonNode?>(p.Key, Sort(p.Value)))
                ),
                JsonArray a => new JsonArray(a.Select(Sort).ToArray()),
                _ => n?.DeepClone(),
            };
        return Convert.ToHexString(
            SHA256.HashData(Encoding.UTF8.GetBytes(Sort(value)!.ToJsonString()))
        );
    }

    static long Positive(JsonNode body, string key)
    {
        var id = body.N(key);
        if (id <= 0 || id > 9007199254740991)
            throw new ApiException(422, "Enter a positive artefact/key ID.");
        return id;
    }

    public static async Task<JsonObject> Inspect(
        ConnectorService service,
        Record profile,
        long artefact,
        CancellationToken ct
    )
    {
        var config = profile.Data()["configuration"]!;
        if (
            profile.Data().S("provider") != "redeye"
            || !config.B("approved_test_access")
            || !config.B("vendor_settings_confirmed")
        )
            throw new ApiException(409, "Confirm the RedEye connection first.");
        var root = service.Approved(config.Required("base_url")).ToString().TrimEnd('/');
        var keyData = await service.Get(new(root + "/api/v1/metadata-keys"), profile, ct);
        var keys = ConnectorService.Collection(keyData, "metadata_keys", "data");
        if (keys.Count > 1000)
            throw new ApiException(502, "Metadata key inventory exceeds supported bound.");
        var names = new HashSet<string>(StringComparer.OrdinalIgnoreCase);
        var ids = new HashSet<long>();
        var clean = new JsonArray();
        foreach (var k in keys)
        {
            if (k == null || !ids.Add(Positive(k, "id")) || !names.Add(k.Required("name")))
                throw new ApiException(502, "RedEye metadata keys are ambiguous.");
            clean.Add(new JsonObject { ["id"] = k.N("id"), ["name"] = k.S("name") });
        }
        var doc = await service.Get(new(root + "/api/v1/artefacts/" + artefact), profile, ct);
        if (
            doc.N("id") != artefact
            || doc["metadata"] is not JsonArray metadata
            || metadata.Count > 1000
            || doc["revisions"] is not JsonArray
            || doc["state"] is not JsonObject
        )
            throw new ApiException(
                502,
                "RedEye artefact contract does not match the selected target."
            );
        var values = new JsonObject();
        foreach (var m in metadata)
        {
            if (
                m == null
                || !ids.Contains(m.N("key_id"))
                || !clean.Any(k => k!.N("id") == m.N("key_id") && k.S("name") == m.S("key_name"))
                || m["value"] is not JsonValue
            )
                throw new ApiException(502, "Unexpected native RedEye metadata contract.");
            var id = m.N("key_id").ToString();
            if (values[id] == null)
                values[id] = new JsonArray();
            if (m["value"]!.GetValue<string>().Length > 2000)
                throw new ApiException(502, "Metadata value exceeds the supported bound.");
            values[id]!.AsArray().Add(m["value"]!.GetValue<string>());
        }
        var guard = new JsonObject();
        foreach (
            var k in new[]
            {
                "id",
                "number",
                "title",
                "state",
                "revisions",
                "groups",
                "workflow",
                "geometry",
                "type",
                "created",
            }
        )
            if (doc[k] != null)
                guard[k] = doc[k]!.DeepClone();
        return new()
        {
            ["artefact_id"] = artefact,
            ["number"] = doc.S("number"),
            ["title"] = doc.S("title"),
            ["modified"] = doc.S("modified"),
            ["keys"] = clean,
            ["values"] = values,
            ["modifiable"] = doc["state"].B("is_modifiable"),
            ["guard"] = guard,
        };
    }

    public static JsonObject Record(JsonObject snapshot)
    {
        var values = new JsonObject
        {
            ["id"] = snapshot.N("artefact_id").ToString(),
            ["number"] = snapshot.S("number"),
            ["title"] = snapshot.S("title"),
            ["modified"] = snapshot.S("modified"),
        };
        foreach (var k in snapshot["keys"]!.AsArray())
        {
            var a = snapshot["values"]![k!.N("id").ToString()]?.AsArray();
            values["metadata." + k.S("name")] = a?.Count == 1 ? a[0]?.DeepClone() : a?.DeepClone();
        }
        return new() { ["id"] = snapshot.N("artefact_id").ToString(), ["values"] = values };
    }

    static JsonObject Public(Record r)
    {
        var d = r.Data();
        d.Remove("actor");
        d.Remove("session");
        d.Remove("generation");
        d["id"] = r.Id;
        d["created"] = r.Updated.ToString("O");
        return d;
    }

    static string Session(HttpContext ctx) =>
        Convert.ToHexString(
            SHA256.HashData(Encoding.UTF8.GetBytes(ctx.Request.Cookies["__Host-orbit"] ?? ""))
        );

    public static void Map(WebApplication app)
    {
        var root = "/api/projects/{project}/redeye-metadata";
        app.MapGet(root, async (string project, HttpContext ctx, OrbitDb db, IConfiguration cfg) =>
        {
            var who = await Actor.Resolve(ctx, db, cfg);
            await who.Project(db, project);
            var connections = (await db.List(who.Tenant, project, "connection")).Where(r =>
                r.Data().S("provider") == "redeye"
            );
            return Results.Ok(
                new
                {
                    connections = connections.Select(r => new
                    {
                        id = r.Id,
                        name = r.Data().S("name"),
                        base_url = r.Data()["configuration"]!.S("base_url"),
                    }),
                    updates = (await db.List(who.Tenant, project, "metadata-update")).Select(
                        Public
                    ),
                    legacy_unresolved = Array.Empty<object>(),
                    uat_mode = cfg.GetValue<bool>("Orbit:EnableRedEyeWrites"),
                    server_version = "0.15.0",
                }
            );
        });
        app.MapPost(
            root + "/candidates",
            async (
                string project,
                JsonObject body,
                HttpContext ctx,
                OrbitDb db,
                IConfiguration cfg,
                ConnectorService service
            ) =>
            {
                var who = await Actor.Resolve(ctx, db, cfg);
                who.Permit("connection");
                var p = await ConnectionRoutes.Scoped(
                    db,
                    who,
                    project,
                    body.Required("connection_id", 150)
                );
                return Results.Ok(
                    await service.Read(p, new() { ["operation"] = "artefacts" }, ctx.RequestAborted)
                );
            }
        );
        app.MapPost(
            root + "/inspect",
            async (
                string project,
                JsonObject body,
                HttpContext ctx,
                OrbitDb db,
                IConfiguration cfg,
                ConnectorService service
            ) =>
            {
                var who = await Actor.Resolve(ctx, db, cfg);
                who.Permit("connection");
                var p = await ConnectionRoutes.Scoped(
                    db,
                    who,
                    project,
                    body.Required("connection_id", 150)
                );
                var snapshot = await Inspect(
                    service,
                    p,
                    Positive(body, "artefact_id"),
                    ctx.RequestAborted
                );
                var id = Guid.NewGuid().ToString();
                db.Add(
                    who.Tenant,
                    project,
                    "inspection",
                    id,
                    new()
                    {
                        ["connection_id"] = p.Id,
                        ["generation"] = p.Version,
                        ["snapshot"] = snapshot,
                        ["expires"] = DateTimeOffset.UtcNow.AddMinutes(30).ToUnixTimeSeconds(),
                    }
                );
                db.Audit(who, "redeye_metadata.inspected", project, id);
                await db.SaveChangesAsync();
                return Results.Ok(
                    new
                    {
                        id,
                        snapshot,
                        observed = DateTimeOffset.UtcNow.ToString("O"),
                    }
                );
            }
        );
        foreach (var operation in new[] { "verify", "preview" })
            app.MapPost(
                root + "/" + operation,
                async (
                    string project,
                    JsonObject body,
                    HttpContext ctx,
                    OrbitDb db,
                    IConfiguration cfg,
                    ConnectorService service
                ) =>
                {
                    var who = await Actor.Resolve(ctx, db, cfg);
                    who.Permit("connection");
                    var inspection = await db.Find(
                        who.Tenant,
                        project,
                        "inspection",
                        body.Required("inspection_id", 150)
                    ) ?? throw new ApiException(404, "Inspection unavailable.");
                    var inspectionData = inspection.Data();
                    if (inspectionData.N("expires") <= DateTimeOffset.UtcNow.ToUnixTimeSeconds())
                        throw new ApiException(409, "Inspection expired; inspect again.");
                    var p = await ConnectionRoutes.Scoped(
                        db,
                        who,
                        project,
                        inspectionData.S("connection_id")
                    );
                    if (p.Version != inspectionData.N("generation"))
                        throw new ApiException(409, "Connection changed; inspect again.");
                    var snapshot = await Inspect(
                        service,
                        p,
                        inspectionData["snapshot"]!.N("artefact_id"),
                        ctx.RequestAborted
                    );
                    var key = snapshot["keys"]!
                        .AsArray()
                        .SingleOrDefault(k => k!.N("id") == body.N("metadata_key_id"))
                        ?? throw new ApiException(422, "Choose an existing metadata key.");
                    if (body.S("property_uri").Length > 0)
                        throw new ApiException(
                            501,
                            "Hosted bSDD write validation parity is pending; this write has not been prepared."
                        );
                    var previous = snapshot["values"]!
                        [body.N("metadata_key_id").ToString()]
                        ?.DeepClone()
                        ?? new JsonArray();
                    var proposed = body["values"]?.AsArray();
                    if (operation == "verify")
                        return Results.Ok(
                            new
                            {
                                actual = previous,
                                expected = proposed,
                                matches = proposed == null
                                    ? (bool?)null
                                    : JsonNode.DeepEquals(previous, proposed),
                                validation_errors = Array.Empty<string>(),
                                observed = DateTimeOffset.UtcNow.ToString("O"),
                                scope = "Existing field on the selected artefact; read-only verification.",
                            }
                        );
                    if (proposed == null || proposed.Count > 100)
                        throw new ApiException(422, "Specify the field values.");
                    if (!snapshot.B("modifiable"))
                        throw new ApiException(409, "The artefact is not modifiable.");
                    if (previous.AsArray().Count > 0 && !body.B("overwrite_existing"))
                        throw new ApiException(409, "Confirm replacement of the existing value.");
                    var revisions = snapshot["guard"]!["revisions"]!.AsArray();
                    if (revisions.Count != 1)
                        throw new ApiException(
                            409,
                            "A single current revision must be established before writing."
                        );
                    var values = new JsonArray(
                        proposed
                            .Select(v =>
                                (JsonNode)
                                    JsonValue.Create(
                                        v is JsonValue j && j.TryGetValue<string>(out var text)
                                            ? text
                                            : v?.ToJsonString() ?? "null"
                                    )!
                            )
                            .ToArray()
                    );
                    var payload = new JsonArray();
                    foreach (var k in snapshot["keys"]!.AsArray())
                    {
                        var native = k!.N("id").ToString();
                        var existing = snapshot["values"]![native];
                        if (native == body.N("metadata_key_id").ToString())
                            payload.Add(
                                new JsonObject
                                {
                                    ["name"] = k.S("name"),
                                    ["value"] = values.DeepClone(),
                                }
                            );
                        else if (existing != null)
                            payload.Add(
                                new JsonObject
                                {
                                    ["name"] = k.S("name"),
                                    ["value"] = existing.DeepClone(),
                                }
                            );
                    }
                    if (payload.ToJsonString().Length > 100000)
                        throw new ApiException(422, "Metadata payload is too large.");
                    var plan = new JsonObject
                    {
                        ["before"] = snapshot,
                        ["key"] = key.DeepClone(),
                        ["values"] = values,
                        ["previous"] = previous,
                        ["source"] = null,
                        ["connection_name"] = p.Data().S("name"),
                        ["base_url"] = p.Data()["configuration"]!.S("base_url"),
                        ["payload"] = new JsonObject { ["metadata"] = payload },
                    };
                    var id = Guid.NewGuid().ToString();
                    var draft = db.Add(
                        who.Tenant,
                        project,
                        "metadata-update",
                        id,
                        new()
                        {
                            ["connection_id"] = p.Id,
                            ["generation"] = p.Version,
                            ["actor"] = who.Id,
                            ["session"] = Session(ctx),
                            ["expires"] = DateTimeOffset.UtcNow.AddMinutes(30).ToUnixTimeSeconds(),
                            ["plan"] = plan,
                            ["digest"] = Digest(plan),
                            ["status"] = "preview",
                            ["receipt"] = null,
                        }
                    );
                    db.Audit(who, "redeye_metadata.preview", project, id);
                    await db.SaveChangesAsync();
                    return Results.Ok(Public(draft));
                }
            );
        app.MapPost(
            root + "/{id}/execute",
            async (
                string project,
                string id,
                JsonObject body,
                HttpContext ctx,
                OrbitDb db,
                IConfiguration cfg,
                ConnectorService service,
                IHttpClientFactory factory,
                Cipher cipher
            ) =>
            {
                var who = await Actor.Resolve(ctx, db, cfg);
                who.Permit("connection");
                await who.Project(db, project);
                if (!cfg.GetValue<bool>("Orbit:EnableRedEyeWrites"))
                    throw new ApiException(409, "Hosted RedEye writes are not enabled yet.");
                var r = await db.Find(who.Tenant, project, "metadata-update", id)
                    ?? throw new ApiException(404, "Preview unavailable.");
                var d = r.Data();
                if (
                    d.S("digest") != body.S("digest")
                    || d.S("actor") != who.Id
                    || d.S("session") != Session(ctx)
                )
                    throw new ApiException(409, "Preview or session changed; inspect again.");
                if (d.S("status") != "preview")
                    return Results.Ok(
                        d["receipt"]
                            ?? new JsonObject
                            {
                                ["status"] = d.S("status"),
                                ["reason"] =
                                    "This preview has already been reserved. No retry was sent.",
                            }
                    );
                if (
                    !body.B("confirmed")
                    || !body.B("current_revision_confirmed")
                    || d.N("expires") <= DateTimeOffset.UtcNow.ToUnixTimeSeconds()
                )
                    throw new ApiException(409, "Confirm both changes using a current preview.");
                var p = await ConnectionRoutes.Scoped(db, who, project, d.S("connection_id"));
                if (p.Version != d.N("generation"))
                    throw new ApiException(409, "Connection changed; inspect again.");
                var plan = d["plan"]!;
                var artefact = plan["before"]!.N("artefact_id");
                var lockId = Digest(
                    new JsonObject { ["url"] = plan.S("base_url"), ["artefact"] = artefact }
                );
                if (await db.Find(who.Tenant, project, "write-lock", lockId) != null)
                    throw new ApiException(
                        409,
                        "An earlier update on this target is unresolved. Inspect/recheck it before another update."
                    );
                db.Add(who.Tenant, project, "write-lock", lockId, new() { ["update_id"] = id });
                d["status"] = "attempting";
                db.Change(r, d);
                db.Audit(who, "redeye_metadata.reserved", project, id);
                await db.SaveChangesAsync();
                var sent = false;
                var ack = false;
                JsonObject receipt;
                try
                {
                    var current = await Inspect(service, p, artefact, ctx.RequestAborted);
                    if (!JsonNode.DeepEquals(current, plan["before"]))
                        throw new ApiException(409, "Target changed after preview. No write sent.");
                    await db.Entry(p).ReloadAsync(ctx.RequestAborted);
                    if (p.Version != d.N("generation"))
                        throw new ApiException(
                            409,
                            "Connection changed during preflight. No write sent."
                        );
                    using var request = new HttpRequestMessage(
                        HttpMethod.Post,
                        new Uri(
                            service.Approved(plan.S("base_url")).ToString().TrimEnd('/')
                                + "/api/v1/artefacts/"
                                + artefact
                        )
                    );
                    var pc = p.Data()["configuration"]!;
                    request.Headers.Add(
                        pc.S("auth_header", "Authorization"),
                        (pc.S("auth_prefix", "Bearer") + " ").TrimStart()
                            + cipher.Unprotect(p.Secret!)
                    );
                    request.Content = new StringContent(
                        plan["payload"]!.ToJsonString(),
                        Encoding.UTF8,
                        "application/json"
                    );
                    sent = true;
                    using var response = await factory
                        .CreateClient("vendor")
                        .SendAsync(
                            request,
                            HttpCompletionOption.ResponseHeadersRead,
                            ctx.RequestAborted
                        );
                    ack = (int)response.StatusCode == 200;
                    if (!ack)
                        throw new ApiException(
                            409,
                            "The vendor did not acknowledge the update. Review without retrying."
                        );
                    var after = await Inspect(service, p, artefact, ctx.RequestAborted);
                    var expected = plan["before"]!["values"]!.DeepClone().AsObject();
                    expected[plan["key"]!.N("id").ToString()] = plan["values"]!.DeepClone();
                    if (
                        !JsonNode.DeepEquals(after["values"], expected)
                        || !JsonNode.DeepEquals(after["guard"], plan["before"]!["guard"])
                        || !JsonNode.DeepEquals(after["keys"], plan["before"]!["keys"])
                    )
                        throw new ApiException(
                            409,
                            "Read-back did not match the complete intended metadata. Review without retrying."
                        );
                    receipt = new()
                    {
                        ["status"] = "succeeded",
                        ["reason"] = "Selected field and all preserved metadata matched.",
                        ["read_back_verified"] = true,
                        ["http_200_observed"] = true,
                    };
                }
                catch (Exception)
                {
                    receipt = new()
                    {
                        ["status"] = sent ? "needs_review" : "not_sent",
                        ["reason"] = sent
                            ? "The outcome needs review in RedEye. No automatic retry will be sent."
                            : "Preflight changed or could not complete. No write was sent; inspect again.",
                        ["read_back_verified"] = false,
                        ["http_200_observed"] = ack,
                    };
                }
                receipt["observed"] = DateTimeOffset.UtcNow.ToString("O");
                receipt["automatic_retry"] = false;
                d["status"] = receipt.S("status");
                d["receipt"] = receipt;
                db.Change(r, d);
                if (receipt.S("status") != "needs_review")
                {
                    var held = await db.Find(who.Tenant, project, "write-lock", lockId);
                    if (held != null)
                        db.Remove(held);
                }
                db.Audit(who, "redeye_metadata." + receipt.S("status"), project, id);
                await db.SaveChangesAsync(CancellationToken.None);
                return Results.Ok(receipt);
            }
        );
    }
}
