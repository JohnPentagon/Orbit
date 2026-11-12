using System.Text.Json.Nodes;

namespace Orbit.Api;

public static class AnalysisRoutes
{
    static JsonArray Rows(JsonObject snap) => snap["records"]!.AsArray();

    static string[] Fields(JsonObject snap) =>
        Rows(snap)
            .SelectMany(r => r!["values"]!.AsObject().Select(p => p.Key))
            .Distinct()
            .Order()
            .ToArray();

    public static JsonNode? Transform(JsonNode? value, string mode)
    {
        if (value == null || mode == "copy")
            return value?.DeepClone();
        if (value is JsonArray a)
            return new JsonArray(a.Select(v => Transform(v, mode)).ToArray());
        var s = value.ToString();
        return JsonValue.Create(
            mode switch
            {
                "trim" => s.Trim(),
                "uppercase" => s.ToUpperInvariant(),
                "lowercase" => s.ToLowerInvariant(),
                "filename_stem" => Path.GetFileNameWithoutExtension(s.Replace('\\', '/')),
                _ => throw new ApiException(422, "Unknown transformation."),
            }
        );
    }

    public static JsonObject Evaluate(
        JsonObject left,
        JsonObject right,
        JsonObject config,
        JsonObject? reference = null
    )
    {
        var counts = new JsonObject();
        foreach (
            var k in new[]
            {
                "matched",
                "different",
                "invalid",
                "unknown",
                "ambiguous",
                "not_in_source_sample",
                "not_in_target_sample",
            }
        )
            counts[k] = 0;
        var indexes = new List<Dictionary<string, List<JsonNode>>>();
        var problems = new JsonArray();
        var quality = new JsonArray();
        foreach (var pair in new[] { ("source", left), ("target", right) })
        {
            var index = new Dictionary<string, List<JsonNode>>(StringComparer.Ordinal);
            foreach (var r in Rows(pair.Item2))
            {
                var values = r!["values"]!.AsObject();
                var v = values[config.S(pair.Item1 + "_key")];
                var key = Transform(v, config.S(pair.Item1 + "_key_transform", "trim"));
                if (
                    key == null
                    || key is JsonArray
                    || key.ToString().Trim().Length == 0
                    || key.ToString() == "[not captured]"
                )
                {
                    problems.Add(
                        new JsonObject
                        {
                            ["side"] = pair.Item1,
                            ["record_id"] = r["id"]!.DeepClone(),
                            ["reason"] = "Matching field is missing, unavailable or multi-valued.",
                        }
                    );
                    continue;
                }
                var text =
                    config.S("key_mode", "text") == "typed" ? key.ToJsonString() : key.ToString();
                if (!index.TryGetValue(text, out var group))
                    index[text] = group = [];
                group.Add(r);
            }
            indexes.Add(index);
        }
        var rows = new JsonArray();
        foreach (var key in indexes[0].Keys.Union(indexes[1].Keys).Order())
        {
            var a = indexes[0].GetValueOrDefault(key, []);
            var b = indexes[1].GetValueOrDefault(key, []);
            var checks = new JsonArray();
            var status =
                a.Count > 1 || b.Count > 1 ? "ambiguous"
                : a.Count == 0 ? "not_in_source_sample"
                : b.Count == 0 ? "not_in_target_sample"
                : "matched";
            if (a.Count == 1 && b.Count == 1)
            {
                foreach (var rule in config["rules"]!.AsArray())
                {
                    var av = a[0]["values"]!.AsObject();
                    var bv = b[0]["values"]!.AsObject();
                    var x = Transform(av[rule.S("source_field")], rule.S("transform", "copy"));
                    var y = Transform(bv[rule.S("target_field")], rule.S("transform", "copy"));
                    bool blank(JsonNode? n) =>
                        n == null
                        || string.IsNullOrWhiteSpace(n.ToString())
                        || n is JsonArray arr && arr.Count == 0;
                    var unknown =
                        !av.ContainsKey(rule.S("source_field"))
                        || !bv.ContainsKey(rule.S("target_field"))
                        || x?.ToString() == "[not captured]"
                        || y?.ToString() == "[not captured]";
                    var state =
                        rule.B("required") && (blank(x) || blank(y)) ? "invalid"
                        : unknown || blank(x) && blank(y) ? "unknown"
                        : JsonNode.DeepEquals(x, y) ? "matched"
                        : "different";
                    var issues = new JsonArray();
                    if (rule.S("property_uri").Length > 0 && !unknown)
                    {
                        var property = Validation.Property(reference, rule.S("property_uri"));
                        var valueProblems = Validation
                            .Value(
                                x,
                                property,
                                rule.S("unit"),
                                rule.B("required"),
                                rule.B("interpret_strings")
                            )
                            .Concat(
                                Validation.Value(
                                    y,
                                    property,
                                    rule.S("unit"),
                                    rule.B("required"),
                                    rule.B("interpret_strings")
                                )
                            )
                            .Distinct();
                        foreach (var problem in valueProblems)
                            issues.Add(problem);
                        if (issues.Count > 0)
                            state = "invalid";
                    }
                    if (state == "invalid")
                        issues.Add("Required value is missing.");
                    if (state == "unknown")
                        issues.Add("Field value is missing or was not captured.");
                    if (state is "invalid" or "unknown")
                        quality.Add(
                            new JsonObject
                            {
                                ["side"] = "pair",
                                ["record_id"] = key,
                                ["field"] = rule.S("source_field"),
                                ["status"] = state,
                                ["issues"] = issues.DeepClone(),
                            }
                        );
                    checks.Add(
                        new JsonObject
                        {
                            ["source_field"] = rule.S("source_field"),
                            ["target_field"] = rule.S("target_field"),
                            ["source_value"] = x,
                            ["target_value"] = y,
                            ["status"] = state,
                            ["issues"] = issues,
                        }
                    );
                }
                status = new[] { "invalid", "different", "unknown", "matched" }.First(s =>
                    checks.Any(c => c.S("status") == s)
                );
            }
            counts[status] = counts.N(status) + 1;
            rows.Add(
                new JsonObject
                {
                    ["match_key"] = key,
                    ["status"] = status,
                    ["source_ids"] = new JsonArray(a.Select(r => r["id"]!.DeepClone()).ToArray()),
                    ["target_ids"] = new JsonArray(b.Select(r => r["id"]!.DeepClone()).ToArray()),
                    ["fields"] = checks,
                }
            );
        }
        return new()
        {
            ["counts"] = counts,
            ["rows"] = rows,
            ["matching_issues"] = problems,
            ["validation_findings"] = quality,
            ["quality"] = new JsonObject
            {
                ["invalid_records"] = quality.Count(q => q.S("status") == "invalid"),
                ["invalid_fields"] = quality.Count(q => q.S("status") == "invalid"),
                ["unknown_fields"] = quality.Count(q => q.S("status") == "unknown"),
            },
            ["record_counts"] = new JsonObject
            {
                ["source"] = Rows(left).Count,
                ["target"] = Rows(right).Count,
            },
            ["outcome"] =
                Rows(left).Count == 0 || Rows(right).Count == 0 ? "no_data"
                : counts.Any(p => p.Key != "matched" && counts.N(p.Key) > 0) || problems.Count > 0
                    ? "findings"
                : "sample_matches",
            ["scope"] =
                "Captured samples only. A missing counterpart means not in this sample, not absent from the platform. Matching metadata does not prove file equality or whole-project compliance.",
            ["written"] = false,
        };
    }

    static async Task Fresh(OrbitDb db, Actor who, string project, Record snapshot)
    {
        var d = snapshot.Data();
        if (d.N("expires") <= DateTimeOffset.UtcNow.ToUnixTimeSeconds())
            throw new ApiException(409, "Read fresh samples before comparing.");
        var c = await ConnectionRoutes.Scoped(db, who, project, d.S("connection_id"));
        if (c.Version != d.N("generation"))
            throw new ApiException(409, "Connection changed; read a new sample.");
    }

    static JsonObject Descriptor(Record s, bool fresh)
    {
        var d = s.Data();
        d.Remove("records");
        d["id"] = s.Id;
        d["fresh"] = fresh;
        d["fields"] = new JsonArray(
            Fields(s.Data()).Select(v => (JsonNode)JsonValue.Create(v)!).ToArray()
        );
        d["record_count"] = Rows(s.Data()).Count;
        return d;
    }

    public static void Map(WebApplication app)
    {
        var root = "/api/projects/{project}/analysis";
        app.MapGet(root, async (string project, HttpContext ctx, OrbitDb db, IConfiguration cfg) =>
        {
            var who = await Actor.Resolve(ctx, db, cfg);
            await who.Project(db, project);
            var connections = await db.List(who.Tenant, project, "connection");
            var checks = await db.List(who.Tenant, project, "connection-check");
            var snapshots = new JsonArray();
            foreach (var s in await db.List(who.Tenant, project, "snapshot"))
            {
                var fresh = true;
                try
                {
                    await Fresh(db, who, project, s);
                }
                catch (ApiException)
                {
                    fresh = false;
                }
                snapshots.Add(Descriptor(s, fresh));
            }
            var reports = new JsonArray();
            foreach (var r in await db.List(who.Tenant, project, "report"))
            {
                var d = r.Data();
                var stale = false;
                var reportConfig = d["report"]!["configuration"]!;
                if (reportConfig["reference_version"] != null)
                {
                    var definition = await db.Find(who.Tenant, project, "bsdd", "reference");
                    stale = definition?.Version != reportConfig.N("reference_version");
                }
                foreach (var side in new[] { "source", "target" })
                {
                    var s = await db.Find(
                        who.Tenant,
                        project,
                        "snapshot",
                        d["report"]![side]!.S("id")
                    );
                    try
                    {
                        if (s == null)
                            throw new ApiException(409, "Missing sample.");
                        await Fresh(db, who, project, s);
                    }
                    catch (ApiException)
                    {
                        stale = true;
                    }
                }
                reports.Add(
                    new JsonObject
                    {
                        ["id"] = r.Id,
                        ["mapping_id"] = d.S("mapping_id"),
                        ["mapping_version"] = d.N("mapping_version"),
                        ["name"] = d["report"]!.S("mapping_name"),
                        ["counts"] = d["report"]!["counts"]!.DeepClone(),
                        ["quality"] = d["report"]!["quality"]!.DeepClone(),
                        ["outcome"] = d["report"]!.S("outcome"),
                        ["created"] = r.Updated.ToString("O"),
                        ["stale"] = stale,
                    }
                );
            }
            var maps = await db.List(who.Tenant, project, "mapping");
            var latest = reports.GroupBy(r => r.S("mapping_id")).Select(g => g.First()!).ToList();
            var active = latest.Where(r => !r.B("stale")).ToList();
            return Results.Ok(
                new
                {
                    connections = connections.Select(r =>
                    {
                        var d = r.Data();
                        var latest = checks.FirstOrDefault(c =>
                            c.Data().S("connection_id") == r.Id
                            && c.Data().N("generation") == r.Version
                        );
                        var last = d["last_result"];
                        var health =
                            latest == null ? "unverified"
                            : latest.Data().S("status") != "success" ? latest.Data().S("status")
                            : DateTimeOffset.UtcNow - latest.Updated < TimeSpan.FromMinutes(30)
                                ? "read_verified"
                            : "stale";
                        return new
                        {
                            kind = d.S("kind"),
                            id = r.Id,
                            name = d.S("name"),
                            provider = d.S("provider"),
                            generation = r.Version,
                            health,
                            last_check = latest?.Updated.ToString("O"),
                            scope_hint = d["configuration"]
                                ?.S(
                                    "folder_label",
                                    d["configuration"]!.S("view_id", "Configured API scope")
                                ),
                        };
                    }),
                    snapshots,
                    mappings = maps.Select(m => new
                    {
                        id = m.Id,
                        version = m.Version,
                        configuration = m.Data(),
                    }),
                    reports,
                    properties = (await db.Find(who.Tenant, project, "bsdd", "reference"))?.Data()[
                        "properties"
                    ]
                        ?? new JsonArray(),
                    health = new { },
                    validation = new
                    {
                        mappings = maps.Count,
                        never_compared = maps.Count(m =>
                            !latest.Any(r => r.S("mapping_id") == m.Id)
                        ),
                        fresh_reports = active.Count,
                        stale_reports = latest.Count - active.Count,
                        invalid_fields = active.Sum(r => r["quality"]!.N("invalid_fields")),
                        unknown_fields = active.Sum(r => r["quality"]!.N("unknown_fields")),
                        differences = active.Sum(r => r["counts"]!.N("different")),
                        unmatched_in_samples = active.Sum(r =>
                            r["counts"]!.N("not_in_source_sample")
                            + r["counts"]!.N("not_in_target_sample")
                        ),
                    },
                    scope = "Recorded reads and captured samples, not continuous monitoring or complete-platform assurance.",
                }
            );
        });
        app.MapPost(
            root + "/capture",
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
                var r = await ConnectionRoutes.Scoped(db, who, project, body.Required("id", 150));
                var data = r.Data();
                if (body.S("kind") != data.S("kind"))
                    throw new ApiException(422, "Connection kind mismatch.");
                var config = data["configuration"]!;
                var sampleScope = config.DeepClone().AsObject();
                var op = body.S("operation");
                if (op.Length == 0)
                    op = data.S("provider") switch
                    {
                        "redeye" => "artefacts",
                        "forma" => config.S("folder").Length > 0 ? "documents" : "hubs",
                        "meridian" => "documents",
                        _ => "companies",
                    };
                var result = await service.Read(
                    r,
                    new() { ["operation"] = op },
                    ctx.RequestAborted
                );
                var captured = DateTimeOffset.UtcNow;
                data["last_result"] = new JsonObject
                {
                    ["operation"] = op,
                    ["returned"] = result["returned"]!.DeepClone(),
                    ["observed"] = captured.ToString("O"),
                };
                r.Json = data.ToJsonString();
                if (body.B("health_only"))
                {
                    await db.SaveChangesAsync();
                    return Results.Ok(new { checked_read = true, written = false });
                }
                var records = new JsonArray(
                    result["resources"]!
                        .AsArray()
                        .Select(row =>
                            (JsonNode)
                                new JsonObject
                                {
                                    ["id"] = row!["id"]!.DeepClone(),
                                    ["values"] = row["fields"]!.DeepClone(),
                                }
                        )
                        .ToArray()
                );
                if (data.S("provider") == "redeye")
                {
                    records = new JsonArray();
                    var selected =
                        body["artefact_ids"] is JsonArray explicitIds && explicitIds.Count > 0
                            ? explicitIds
                            : result["resources"]!.AsArray();
                    if (
                        selected.Count > 5
                        && body["artefact_ids"] is JsonArray requested
                        && requested.Count > 5
                    )
                        throw new ApiException(422, "Choose at most five artefact IDs.");
                    foreach (var native in selected.Take(5))
                    {
                        var idText = native is JsonObject ? native.S("id") : native!.ToString();
                        if (!long.TryParse(idText, out var artefact) || artefact <= 0)
                            throw new ApiException(502, "Expected numeric RedEye artefact IDs.");
                        records.Add(
                            RedEyeRoutes.Record(
                                await RedEyeRoutes.Inspect(service, r, artefact, ctx.RequestAborted)
                            )
                        );
                    }
                    sampleScope = new JsonObject
                    {
                        ["artefact_ids"] = body["artefact_ids"]?.DeepClone() ?? new JsonArray(),
                        ["detail_limit"] = 5,
                        ["selection"] =
                            body["artefact_ids"] is JsonArray ids && ids.Count > 0
                                ? "explicit_ids"
                                : "first_bounded_page",
                    };
                    op = "document_metadata";
                    result["coverage"] =
                        "Metadata for at most five selected artefacts or the first bounded page; not a complete register.";
                }
                var id = Guid.NewGuid().ToString();
                var snapshot = db.Add(
                    who.Tenant,
                    project,
                    "snapshot",
                    id,
                    new()
                    {
                        ["kind"] = data.S("kind"),
                        ["connection_id"] = r.Id,
                        ["generation"] = r.Version,
                        ["operation"] = op,
                        ["scope"] = sampleScope,
                        ["records"] = records,
                        ["observed"] = captured.ToString("O"),
                        ["expires"] = captured.AddMinutes(30).ToUnixTimeSeconds(),
                        ["coverage"] = new JsonObject
                        {
                            ["description"] = result.S("coverage"),
                            ["complete"] = false,
                            ["notes"] = new JsonArray(),
                        },
                    }
                );
                db.Audit(who, "analysis.sample_captured", project, id);
                await db.SaveChangesAsync();
                return Results.Ok(new { snapshot = Descriptor(snapshot, true), written = false });
            }
        );
        app.MapPost(
            root + "/mappings",
            async (
                string project,
                JsonObject body,
                HttpContext ctx,
                OrbitDb db,
                IConfiguration cfg
            ) =>
            {
                var who = await Actor.Resolve(ctx, db, cfg);
                who.Permit("draft");
                await who.Project(db, project);
                var config = body.Copy();
                config.Required("name", 100);
                if (body.S("source_snapshot") == body.S("target_snapshot"))
                    throw new ApiException(422, "Choose distinct samples.");
                foreach (var side in new[] { "source", "target" })
                {
                    var sample = await db.Find(
                        who.Tenant,
                        project,
                        "snapshot",
                        body.Required(side + "_snapshot", 150)
                    ) ?? throw new ApiException(404, "Sample unavailable.");
                    await Fresh(db, who, project, sample);
                    var d = sample.Data();
                    var c = await ConnectionRoutes.Scoped(db, who, project, d.S("connection_id"));
                    if (!Fields(d).Contains(body.Required(side + "_key")))
                        throw new ApiException(422, "Choose matching fields from the sample.");
                    config[side] = new JsonObject
                    {
                        ["id"] = c.Id,
                        ["kind"] = d.S("kind"),
                        ["name"] = c.Data().S("name"),
                        ["provider"] = c.Data().S("provider"),
                        ["operation"] = d.S("operation"),
                        ["scope"] = d["scope"]!.DeepClone(),
                    };
                    foreach (var rule in body["rules"]?.AsArray() ?? new JsonArray())
                    {
                        if (!Fields(d).Contains(rule!.Required(side + "_field")))
                            throw new ApiException(422, "Choose mapped fields from the sample.");
                        if (rule.S("property_uri").Length > 0)
                        {
                            var reference = await db.Find(who.Tenant, project, "bsdd", "reference");
                            Validation.Property(reference?.Data(), rule.S("property_uri"));
                            config["reference_version"] = reference!.Version;
                        }
                    }
                }
                if (body["rules"] is not JsonArray rules || rules.Count is < 1 or > 50)
                    throw new ApiException(422, "Choose 1–50 field mappings.");
                var id = Guid.NewGuid().ToString();
                db.Add(who.Tenant, project, "mapping", id, config);
                db.Audit(who, "analysis.mapping_saved", project, id);
                await db.SaveChangesAsync();
                return Results.Ok(
                    new
                    {
                        id,
                        version = 1,
                        written = false,
                    }
                );
            }
        );
        app.MapPost(
            root + "/mappings/{id}/compare",
            async (
                string project,
                string id,
                JsonObject body,
                HttpContext ctx,
                OrbitDb db,
                IConfiguration cfg
            ) =>
            {
                var who = await Actor.Resolve(ctx, db, cfg);
                who.Permit("run");
                await who.Project(db, project);
                var m = await db.Find(who.Tenant, project, "mapping", id)
                    ?? throw new ApiException(404, "Mapping unavailable.");
                if (body.N("expected_version") != m.Version)
                    throw new ApiException(409, "Mapping changed; reload first.");
                var config = m.Data();
                var samples = new List<Record>();
                foreach (var side in new[] { "source", "target" })
                {
                    var reference = config[side]!;
                    var candidates = await db.List(who.Tenant, project, "snapshot");
                    var s = candidates.FirstOrDefault(r =>
                        r.Data().S("connection_id") == reference.S("id")
                        && r.Data().S("operation") == reference.S("operation")
                        && JsonNode.DeepEquals(r.Data()["scope"], reference["scope"])
                    ) ?? throw new ApiException(409, "Read the selected scope again.");
                    await Fresh(db, who, project, s);
                    samples.Add(s);
                }
                var schema = await db.Find(who.Tenant, project, "bsdd", "reference");
                if (
                    config["reference_version"] != null
                    && config.N("reference_version") != schema?.Version
                )
                    throw new ApiException(
                        409,
                        "bSDD reference changed; review and save the mapping again."
                    );
                var report = Evaluate(samples[0].Data(), samples[1].Data(), config, schema?.Data());
                report["mapping_name"] = config.S("name");
                report["configuration"] = config.Copy();
                report["warnings"] = new JsonArray(
                    "Confirm that the matching keys have the same meaning across these platforms."
                );
                for (var i = 0; i < 2; i++)
                {
                    var d = samples[i].Data();
                    report[i == 0 ? "source" : "target"] = new JsonObject
                    {
                        ["id"] = samples[i].Id,
                        ["observed"] = d["observed"]!.DeepClone(),
                        ["coverage"] = d["coverage"]!.DeepClone(),
                        ["operation"] = d.S("operation"),
                        ["scope"] = d["scope"]!.DeepClone(),
                    };
                }
                var rid = Guid.NewGuid().ToString();
                var stored = db.Add(
                    who.Tenant,
                    project,
                    "report",
                    rid,
                    new()
                    {
                        ["mapping_id"] = id,
                        ["mapping_version"] = m.Version,
                        ["report"] = report,
                    }
                );
                db.Audit(who, "analysis.comparison_completed", project, rid);
                await db.SaveChangesAsync();
                return Results.Ok(
                    new
                    {
                        id = rid,
                        created = stored.Updated.ToString("O"),
                        report,
                    }
                );
            }
        );
        app.MapGet(
            root + "/reports/{id}",
            async (string project, string id, HttpContext ctx, OrbitDb db, IConfiguration cfg) =>
            {
                var who = await Actor.Resolve(ctx, db, cfg);
                await who.Project(db, project);
                var r = await db.Find(who.Tenant, project, "report", id)
                    ?? throw new ApiException(404, "Report unavailable.");
                return Results.Ok(
                    new
                    {
                        id = r.Id,
                        created = r.Updated.ToString("O"),
                        report = r.Data()["report"],
                    }
                );
            }
        );
    }
}
