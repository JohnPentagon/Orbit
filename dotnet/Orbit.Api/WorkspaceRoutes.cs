using System.Text.Json.Nodes;
using Microsoft.EntityFrameworkCore;

namespace Orbit.Api;

public static class WorkspaceRoutes
{
    public static void Map(WebApplication app)
    {
        app.MapGet("/api/workspace", async (HttpContext ctx, OrbitDb db, IConfiguration cfg) =>
        {
            var who = await Actor.Resolve(ctx, db, cfg);
            var workspace = await db.Find(who.Tenant, "", "workspace", "settings");
            if (workspace == null && who.Role == "owner")
            {
                workspace = db.Add(
                    who.Tenant,
                    "",
                    "workspace",
                    "settings",
                    new() { ["name"] = cfg["Orbit:WorkspaceName"] ?? "ORBIT UAT" }
                );
                db.Add(
                    who.Tenant,
                    "",
                    "project",
                    "uat-project",
                    new() { ["name"] = "Initial UAT project" }
                );
                db.Audit(who, "workspace.initialised");
                await db.SaveChangesAsync();
            }
            var projects = await db.List(who.Tenant, "", "project");
            if (who.Role != "owner")
            {
                var member = (await db.Find(who.Tenant, "", "member", who.Id))!.Data();
                projects = projects
                    .Where(p =>
                        member["projects"]?.AsArray().Any(v => v?.GetValue<string>() == p.Id)
                        == true
                    )
                    .ToList();
            }
            return Results.Ok(
                new
                {
                    identity = new
                    {
                        user_id = who.Id,
                        tenant_id = who.Tenant,
                        role = who.Role,
                    },
                    operator_name = ctx.User.FindFirst("name")?.Value ?? "ORBIT user",
                    tenant = new { name = workspace?.Data().S("name") ?? "ORBIT" },
                    permissions = who.Permissions,
                    projects = projects.Select(p => new { id = p.Id, name = p.Data().S("name") }),
                }
            );
        });
        app.MapPut(
            "/api/local/settings",
            async (JsonObject body, HttpContext ctx, OrbitDb db, IConfiguration cfg) =>
            {
                var who = await Actor.Resolve(ctx, db, cfg);
                who.Permit("administer");
                var project = body.Required("project_id", 150);
                await who.Project(db, project);
                var w = await db.Find(who.Tenant, "", "workspace", "settings");
                db.Change(w!, new() { ["name"] = body.Required("workspace_name", 100) });
                var p = (await db.Find(who.Tenant, "", "project", project))!;
                db.Change(p, new() { ["name"] = body.Required("project_name", 100) });
                db.Audit(who, "workspace.settings_updated", project);
                await db.SaveChangesAsync();
                return Results.Ok(new { saved = true });
            }
        );
        app.MapPost(
            "/api/local/projects",
            async (JsonObject body, HttpContext ctx, OrbitDb db, IConfiguration cfg) =>
            {
                var who = await Actor.Resolve(ctx, db, cfg);
                who.Permit("connection");
                var id = Guid.NewGuid().ToString();
                db.Add(
                    who.Tenant,
                    "",
                    "project",
                    id,
                    new() { ["name"] = body.Required("name", 100) }
                );
                db.Audit(who, "workspace.project_created", id);
                await db.SaveChangesAsync();
                return Results.Ok(new { id });
            }
        );
        app.MapGet("/api/admin/members", async (HttpContext ctx, OrbitDb db, IConfiguration cfg) =>
        {
            var who = await Actor.Resolve(ctx, db, cfg);
            who.Permit("administer");
            return Results.Ok(
                (await db.List(who.Tenant, "", "member")).Select(r => new
                {
                    id = r.Id,
                    configuration = r.Data(),
                    version = r.Version,
                })
            );
        });
        app.MapPut(
            "/api/admin/members/{id}",
            async (string id, JsonObject body, HttpContext ctx, OrbitDb db, IConfiguration cfg) =>
            {
                var who = await Actor.Resolve(ctx, db, cfg);
                who.Permit("administer");
                if (!Guid.TryParse(id, out _))
                    throw new ApiException(422, "Use the Entra object ID, not an email address.");
                var role = body.Required("role", 30);
                if (!new[] { "owner", "engineer", "viewer", "auditor", "approver" }.Contains(role))
                    throw new ApiException(422, "Choose a supported role.");
                foreach (var p in body["projects"]?.AsArray() ?? new JsonArray())
                    await who.Project(db, p!.GetValue<string>());
                var r = await db.Find(who.Tenant, "", "member", id);
                if (r == null)
                    db.Add(who.Tenant, "", "member", id, body);
                else
                {
                    if (body.N("expected_version") != r.Version)
                        throw new ApiException(409, "Membership changed; reload first.");
                    db.Change(r, body);
                }
                db.Audit(who, "workspace.member_updated", "", id);
                await db.SaveChangesAsync();
                return Results.Ok(new { saved = true });
            }
        );
        app.MapGet(
            "/api/projects/{project}/audit",
            async (string project, HttpContext ctx, OrbitDb db, IConfiguration cfg) =>
            {
                var who = await Actor.Resolve(ctx, db, cfg);
                await who.Project(db, project);
                return Results.Ok(
                    (await db.List(who.Tenant, project, "audit"))
                        .Take(200)
                        .Select(r => new
                        {
                            id = r.Id,
                            action = r.Data().S("action"),
                            actor = r.Data().S("actor"),
                            created = r.Updated.ToString("O"),
                        })
                );
            }
        );
        app.MapGet(
            "/api/projects/{project}/connection-summary",
            async (string project, HttpContext ctx, OrbitDb db, IConfiguration cfg) =>
            {
                var who = await Actor.Resolve(ctx, db, cfg);
                await who.Project(db, project);
                var all = await db.List(who.Tenant, project, "connection");
                var b = (await db.Find(who.Tenant, project, "bsdd", "reference"))?.Data();
                return Results.Ok(
                    new
                    {
                        connections = all.Select(r =>
                        {
                            var d = r.Data();
                            var last = d["last_result"];
                            return new
                            {
                                id = r.Id,
                                name = d.S("name"),
                                provider = d.S("provider"),
                                kind = d.S("kind"),
                                credential_present = r.Secret != null,
                                last_read = last?.S("observed"),
                                last_operation = last?.S("operation"),
                                last_returned = last?["returned"]?.GetValue<int>(),
                                binding_count = d["configuration"]?["bindings"]?.AsArray().Count
                                    ?? 0,
                            };
                        }),
                        mapping_count = (await db.List(who.Tenant, project, "mapping")).Count(m =>
                            !m.Data().B("deleted")
                        ),
                        dictionary = new
                        {
                            enabled = b.B("enabled"),
                            name = b?["dictionary"]?.S("name"),
                            property_count = b?["properties"]?.AsArray().Count ?? 0,
                        },
                        observed = DateTimeOffset.UtcNow.ToString("O"),
                    }
                );
            }
        );
    }
}
