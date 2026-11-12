using System.Text.Json.Nodes;

namespace Orbit.Api;

public static class BsddRoutes
{
    const string Root = "https://api.bsdd.buildingsmart.org";

    static string Identifier(string value)
    {
        if (
            !Uri.TryCreate(value, UriKind.Absolute, out var uri)
            || uri.Scheme != "https"
            || uri.Host != "identifier.buildingsmart.org"
            || !string.IsNullOrEmpty(uri.Query)
            || !string.IsNullOrEmpty(uri.Fragment)
            || !string.IsNullOrEmpty(uri.UserInfo)
            || uri.Port != 443
            || !uri.AbsolutePath.StartsWith("/uri/")
        )
            throw new ApiException(422, "Use a versioned buildingSMART identifier URL.");
        return value.TrimEnd('/');
    }

    public static async Task<JsonObject> Dictionaries(
        ConnectorService service,
        int offset,
        string uri,
        CancellationToken ct
    )
    {
        if (offset < 0 || offset > 100000)
            throw new ApiException(422, "Invalid page offset.");
        var query =
            uri.Length > 0
                ? "Uri=" + Uri.EscapeDataString(Identifier(uri))
                : "Offset=" + offset + "&Limit=25";
        var data = await service.Get(new(Root + "/api/Dictionary/v1?" + query), ct: ct);
        var rows = ConnectorService.Collection(data, "dictionaries");
        if (rows.Count > 25 || data.N("count") != rows.Count)
            throw new ApiException(502, "Unexpected bSDD dictionary contract.");
        if (uri.Length > 0 && (rows.Count != 1 || rows[0].S("uri") != uri))
            throw new ApiException(404, "Exact dictionary version was not returned.");
        return new()
        {
            ["dictionaries"] = rows.DeepClone(),
            ["offset"] = data["offset"]?.DeepClone(),
            ["count"] = rows.Count,
            ["total"] = data["totalCount"]?.DeepClone(),
            ["observed"] = DateTimeOffset.UtcNow.ToString("O"),
        };
    }

    public static async Task<JsonObject> Detail(
        ConnectorService service,
        string dictionary,
        string uri,
        CancellationToken ct
    )
    {
        Identifier(dictionary);
        Identifier(uri);
        if (!uri.StartsWith(dictionary + "/class/", StringComparison.Ordinal))
            throw new ApiException(422, "Select a class from the chosen dictionary version.");
        var d = await service.Get(
            new(
                Root
                    + "/api/Class/v1?Uri="
                    + Uri.EscapeDataString(uri)
                    + "&IncludeClassProperties=true"
            ),
            ct: ct
        );
        if (
            d.S("uri") != uri
            || d.S("dictionaryUri") != dictionary
            || d["classProperties"] is not JsonArray props
            || props.Count > 500
        )
            throw new ApiException(502, "Unexpected bSDD class contract.");
        var result = new JsonArray();
        foreach (var p in props)
        {
            if (p == null)
                throw new ApiException(502, "Empty bSDD property.");
            result.Add(
                new JsonObject
                {
                    ["uri"] = p.Required("uri", 1000),
                    ["propertyUri"] = p.S("propertyUri"),
                    ["name"] = p.Required("name"),
                    ["propertyCode"] = p.S("propertyCode"),
                    ["propertySet"] = p.S("propertySet"),
                    ["dataType"] = p.S("dataType"),
                    ["definition"] = p.S("definition"),
                    ["unit"] = p.S("unit"),
                    ["units"] = p["units"]?.DeepClone() ?? new JsonArray(),
                    ["allowedValues"] = p["allowedValues"]?.DeepClone() ?? new JsonArray(),
                }
            );
        }
        return new()
        {
            ["uri"] = uri,
            ["name"] = d.Required("name"),
            ["code"] = d.S("code"),
            ["properties"] = result,
        };
    }

    public static void Map(WebApplication app)
    {
        var root = "/api/projects/{project}/bsdd";
        app.MapGet(root, async (string project, HttpContext ctx, OrbitDb db, IConfiguration cfg) =>
        {
            var who = await Actor.Resolve(ctx, db, cfg);
            await who.Project(db, project);
            var r = await db.Find(who.Tenant, project, "bsdd", "reference");
            return Results.Ok(
                new
                {
                    version = r?.Version ?? 0,
                    configuration = r?.Data()
                        ?? new JsonObject
                        {
                            ["enabled"] = false,
                            ["dictionary"] = null,
                            ["class"] = null,
                            ["properties"] = new JsonArray(),
                        },
                    updated = r?.Updated.ToString("O"),
                    updated_by = r?.Data().S("updated_by"),
                }
            );
        });
        app.MapGet(
            root + "/dictionaries",
            async (
                string project,
                HttpContext ctx,
                OrbitDb db,
                IConfiguration cfg,
                ConnectorService service
            ) =>
            {
                var who = await Actor.Resolve(ctx, db, cfg);
                who.Permit("connection");
                await who.Project(db, project);
                return Results.Ok(
                    await Dictionaries(
                        service,
                        int.TryParse(ctx.Request.Query["offset"], out var offset) ? offset : 0,
                        ctx.Request.Query["uri"].ToString(),
                        ctx.RequestAborted
                    )
                );
            }
        );
        app.MapGet(
            root + "/classes",
            async (
                string project,
                HttpContext ctx,
                OrbitDb db,
                IConfiguration cfg,
                ConnectorService service
            ) =>
            {
                var who = await Actor.Resolve(ctx, db, cfg);
                who.Permit("connection");
                await who.Project(db, project);
                var uri = Identifier(ctx.Request.Query["dictionary_uri"].ToString());
                var offset =
                    int.TryParse(ctx.Request.Query["offset"], out var n) && n >= 0 && n <= 100000
                        ? n
                        : 0;
                var d = await service.Get(
                    new(
                        Root
                            + "/api/Dictionary/v1/Classes?Uri="
                            + Uri.EscapeDataString(uri)
                            + "&Offset="
                            + offset
                            + "&Limit=25"
                    ),
                    ct: ctx.RequestAborted
                );
                if (d.S("uri") != uri)
                    throw new ApiException(502, "bSDD returned another dictionary scope.");
                return Results.Ok(
                    new
                    {
                        classes = d["classes"],
                        offset = d["classesOffset"],
                        count = d["classesCount"],
                        total = d["classesTotalCount"],
                    }
                );
            }
        );
        app.MapGet(
            root + "/class",
            async (
                string project,
                HttpContext ctx,
                OrbitDb db,
                IConfiguration cfg,
                ConnectorService service
            ) =>
            {
                var who = await Actor.Resolve(ctx, db, cfg);
                who.Permit("connection");
                await who.Project(db, project);
                return Results.Ok(
                    await Detail(
                        service,
                        ctx.Request.Query["dictionary_uri"].ToString(),
                        ctx.Request.Query["class_uri"].ToString(),
                        ctx.RequestAborted
                    )
                );
            }
        );
        app.MapPut(
            root,
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
                var r = await db.Find(who.Tenant, project, "bsdd", "reference");
                if ((r?.Version ?? 0) != body.N("version"))
                    throw new ApiException(409, "Dictionary selection changed; reload first.");
                var selection = new JsonObject
                {
                    ["enabled"] = body.B("enabled"),
                    ["dictionary"] = null,
                    ["class"] = null,
                    ["properties"] = new JsonArray(),
                    ["updated_by"] = who.Id,
                };
                if (body.S("dictionary_uri").Length > 0)
                {
                    var dictionaries = await Dictionaries(
                        service,
                        0,
                        body.S("dictionary_uri"),
                        ctx.RequestAborted
                    );
                    selection["dictionary"] = dictionaries["dictionaries"]![0]!.DeepClone();
                    if (body.S("class_uri").Length > 0)
                    {
                        var detail = await Detail(
                            service,
                            body.S("dictionary_uri"),
                            body.S("class_uri"),
                            ctx.RequestAborted
                        );
                        var chosen = body["property_uris"]
                            ?.AsArray()
                            .Select(x => x!.ToString())
                            .ToHashSet()
                            ?? [];
                        var props = detail["properties"]!
                            .AsArray()
                            .Where(p => chosen.Contains(p.S("uri")))
                            .ToList();
                        if (props.Count != chosen.Count)
                            throw new ApiException(
                                422,
                                "A selected property was not returned by the chosen class."
                            );
                        selection["class"] = new JsonObject
                        {
                            ["uri"] = detail["uri"]!.DeepClone(),
                            ["name"] = detail["name"]!.DeepClone(),
                            ["code"] = detail["code"]!.DeepClone(),
                        };
                        selection["properties"] = new JsonArray(
                            props.Select(p => p!.DeepClone()).ToArray()
                        );
                    }
                }
                if (r == null)
                    r = db.Add(who.Tenant, project, "bsdd", "reference", selection);
                else
                    db.Change(r, selection);
                db.Audit(who, "bsdd.selection_saved", project);
                await db.SaveChangesAsync();
                return Results.Ok(
                    new
                    {
                        version = r.Version,
                        configuration = r.Data(),
                        updated = r.Updated.ToString("O"),
                        updated_by = who.Id,
                    }
                );
            }
        );
    }
}
