using System.Text.Json.Nodes;

namespace Orbit.Api;

public static class ConnectionRoutes
{
    public static async Task<Record> Scoped(OrbitDb db, Actor who, string project, string id)
    {
        await who.Project(db, project);
        return await db.Find(who.Tenant, project, "connection", id)
            ?? throw new ApiException(404, "Connection unavailable in this project.");
    }

    static JsonObject Public(Record r, bool additional)
    {
        var d = r.Data();
        var config = d["configuration"]!.DeepClone();
        var issues = new JsonArray();
        if (!config.B("approved_test_access") || !config.B("vendor_settings_confirmed"))
            issues.Add("Confirm vendor settings and authorised access.");
        if (r.Secret == null && config.S("auth_mode") != "none")
            issues.Add(
                d.S("provider") == "forma"
                    ? "Save the APS application below, then select Sign in with Autodesk. An API key is not required."
                    : "Add a credential."
            );
        if (
            d.S("provider") == "forma"
            && r.Secret != null
            && d["autodesk_expires"] != null
            && d.N("autodesk_expires") <= DateTimeOffset.UtcNow.ToUnixTimeSeconds() + 15
        )
            issues.Add(
                "Autodesk authorisation expired. Select Renew authorisation or Sign in with Autodesk."
            );
        var readIssues = new JsonArray(
            issues
                .Select(x =>
                    (JsonNode)
                        new JsonObject
                        {
                            ["code"] = "setup_required",
                            ["message"] = x!.ToString(),
                            ["next_action"] =
                                d.S("provider") == "forma"
                                    ? "Use the APS application and Autodesk sign-in controls below."
                                    : "Review the saved connection.",
                        }
                )
                .ToArray()
        );
        return new()
        {
            ["id"] = r.Id,
            ["name"] = d.S("name"),
            ["provider"] = d.S("provider"),
            ["generation"] = r.Version,
            ["configuration"] = config,
            ["credential_present"] = r.Secret != null,
            ["last_result"] = d["last_result"]?.DeepClone(),
            ["readiness"] = new JsonObject
            {
                ["ready"] = issues.Count == 0,
                ["issues"] = additional ? issues : readIssues,
            },
        };
    }

    public static void Map(WebApplication app)
    {
        foreach (var path in new[] { "read-connections", "additional-connections" })
        {
            var kind = path == "read-connections" ? "read" : "additional";
            app.MapGet(
                "/api/projects/{project}/" + path,
                async (string project, HttpContext ctx, OrbitDb db, IConfiguration cfg) =>
                {
                    var who = await Actor.Resolve(ctx, db, cfg);
                    who.Permit("connection");
                    await who.Project(db, project);
                    var rows = await db.List(who.Tenant, project, "connection");
                    return Results.Ok(
                        new
                        {
                            server_version = "0.18.0",
                            live_reads_enabled = true,
                            connections = rows.Where(r => r.Data().S("kind") == kind)
                                .Select(r => Public(r, kind == "additional")),
                        }
                    );
                }
            );
            app.MapPost(
                "/api/projects/{project}/" + path,
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
                    await who.Project(db, project);
                    service.Approved(body.Required("base_url"));
                    var provider = body.Required("provider", 50);
                    if (provider == "forma" && body.S("base_url").TrimEnd('/') != AutodeskOAuth.Api)
                        throw new ApiException(422, "Use the documented Autodesk API host.");
                    if (
                        kind == "read" && !new[] { "forma", "redeye" }.Contains(provider)
                        || kind == "additional"
                            && !new[]
                            {
                                "meridian",
                                "procore",
                                "maintenance_connection",
                                "generic",
                            }.Contains(provider)
                    )
                        throw new ApiException(422, "Choose a supported provider.");
                    var id = Guid.NewGuid().ToString();
                    db.Add(
                        who.Tenant,
                        project,
                        "connection",
                        id,
                        new()
                        {
                            ["name"] = body.Required("name", 100),
                            ["provider"] = provider,
                            ["kind"] = kind,
                            ["configuration"] = body.Copy(),
                        }
                    );
                    db.Audit(who, "connection.created", project, id);
                    await db.SaveChangesAsync();
                    return Results.Ok(new { id, live_verified = false });
                }
            );
            var root = "/api/projects/{project}/" + path + "/{id}";
            app.MapPut(
                root + "/credential",
                async (
                    string project,
                    string id,
                    JsonObject body,
                    HttpContext ctx,
                    OrbitDb db,
                    IConfiguration cfg,
                    Cipher cipher
                ) =>
                {
                    var who = await Actor.Resolve(ctx, db, cfg);
                    who.Permit("connection");
                    var r = await Scoped(db, who, project, id);
                    if (
                        body["expected_generation"] != null
                        && body.N("expected_generation") != r.Version
                    )
                        throw new ApiException(409, "Connection changed; reload first.");
                    var secret = body.Required("secret", 8192);
                    if (secret.Length < 8 || secret.Any(char.IsControl))
                        throw new ApiException(
                            422,
                            "Enter a credential without control characters."
                        );
                    if (r.Data().S("provider") == "forma")
                        throw new ApiException(
                            409,
                            "Use the APS application settings and Sign in with Autodesk instead of entering a token manually."
                        );
                    r.Secret = cipher.Protect(secret);
                    var d = r.Data();
                    d["last_result"] = null;
                    if (r.Data().S("provider") == "forma")
                        d.Remove("autodesk_expires");
                    db.Change(r, d);
                    db.Audit(who, "connection.credential_replaced", project, id);
                    await db.SaveChangesAsync();
                    return Results.Ok(new { credential_present = true });
                }
            );
            app.MapDelete(
                root + "/credential",
                async (
                    string project,
                    string id,
                    HttpContext ctx,
                    OrbitDb db,
                    IConfiguration cfg
                ) =>
                {
                    var who = await Actor.Resolve(ctx, db, cfg);
                    who.Permit("connection");
                    var r = await Scoped(db, who, project, id);
                    if (r.Data().S("provider") == "forma")
                        await AutodeskOAuth.Invalidate(db, r);
                    r.Secret = null;
                    var d = r.Data();
                    d["last_result"] = null;
                    if (r.Data().S("provider") == "forma")
                        d.Remove("autodesk_expires");
                    db.Change(r, d);
                    db.Audit(who, "connection.credential_removed", project, id);
                    await db.SaveChangesAsync();
                    return Results.Ok(new { credential_present = false });
                }
            );
            app.MapPut(
                root + (kind == "additional" ? "" : "/configuration"),
                async (
                    string project,
                    string id,
                    JsonObject body,
                    HttpContext ctx,
                    OrbitDb db,
                    IConfiguration cfg,
                    ConnectorService service
                ) =>
                {
                    var who = await Actor.Resolve(ctx, db, cfg);
                    who.Permit("connection");
                    var r = await Scoped(db, who, project, id);
                    service.Approved(body.Required("base_url"));
                    var d = r.Data();
                    if (
                        d.S("provider") == "forma"
                        && body.S("base_url").TrimEnd('/') != AutodeskOAuth.Api
                    )
                        throw new ApiException(422, "Use the documented Autodesk API host.");
                    if (body.S("provider") != d.S("provider"))
                        throw new ApiException(
                            409,
                            "Create another connection to change provider."
                        );
                    if (
                        body["expected_generation"] != null
                        && body.N("expected_generation") != r.Version
                    )
                        throw new ApiException(409, "Connection changed; reload first.");
                    d["configuration"] = body.Copy();
                    d["name"] = body.Required("name", 100);
                    d["last_result"] = null;
                    if (r.Data().S("provider") == "forma")
                        await AutodeskOAuth.Invalidate(db, r);
                    r.Secret = null;
                    db.Change(r, d);
                    db.Audit(who, "connection.configuration_updated", project, id);
                    await db.SaveChangesAsync();
                    return Results.Ok(new { saved = true, reauthorisation_required = true });
                }
            );
            app.MapPost(
                root + "/read",
                async (
                    string project,
                    string id,
                    JsonObject body,
                    HttpContext ctx,
                    OrbitDb db,
                    IConfiguration cfg,
                    ConnectorService service
                ) =>
                {
                    var who = await Actor.Resolve(ctx, db, cfg);
                    who.Permit("connection");
                    var r = await Scoped(db, who, project, id);
                    var generation = r.Version;
                    var result = await service.Read(r, body, ctx.RequestAborted);
                    db.ChangeTracker.Clear();
                    who = await Actor.Resolve(ctx, db, cfg);
                    who.Permit("connection");
                    r = await Scoped(db, who, project, id);
                    if (r.Version != generation)
                        throw new ApiException(
                            409,
                            "Connection changed during the read. Read again using the current selection."
                        );
                    var data = r.Data();
                    result["observed"] = DateTimeOffset.UtcNow.ToString("O");
                    data["last_result"] = new JsonObject
                    {
                        ["operation"] = result["operation"]!.DeepClone(),
                        ["returned"] = result["returned"]!.DeepClone(),
                        ["observed"] = result["observed"]!.DeepClone(),
                    };
                    r.Json = data.ToJsonString();
                    db.Audit(who, "connection.read_completed", project, id);
                    await db.SaveChangesAsync();
                    return Results.Ok(result);
                }
            );
        }
        app.MapGet(
            "/api/projects/{project}/sql-connections",
            async (string project, HttpContext ctx, OrbitDb db, IConfiguration cfg) =>
            {
                var who = await Actor.Resolve(ctx, db, cfg);
                await who.Project(db, project);
                return Results.Ok(
                    new
                    {
                        connections = Array.Empty<object>(),
                        mappings = Array.Empty<object>(),
                        driver = new
                        {
                            available = false,
                            required_driver = "Microsoft.Data.SqlClient native port pending",
                        },
                        hosted_status = "SQL connector port pending; no existing local configurations have been deleted.",
                    }
                );
            }
        );
    }
}
