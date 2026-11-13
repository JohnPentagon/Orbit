using System.Net;
using System.Net.Http.Json;
using System.Text.Json.Nodes;
using Microsoft.Extensions.DependencyInjection;
using Orbit.Api;
using Xunit;

namespace Orbit.Tests;

public sealed class MappingProfileTests
{
    const string Tenant = "11111111-1111-1111-1111-111111111111";
    const string Root = "/api/projects/uat-project/analysis";

    async Task<HttpClient> Setup(Factory factory, bool expired = false)
    {
        var client = factory.CreateClient(
            new() { BaseAddress = new("https://localhost"), AllowAutoRedirect = false }
        );
        client.DefaultRequestHeaders.Add("Test-Object", "33333333-3333-3333-3333-333333333333");
        await client.GetAsync("/api/workspace");
        var session = await client.GetFromJsonAsync<JsonObject>("/api/session");
        client.DefaultRequestHeaders.Add("X-ORBIT-CSRF", session!.S("csrf_token"));
        using var scope = factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<OrbitDb>();
        foreach (var side in new[] { "a", "b" })
        {
            db.Add(
                Tenant,
                "uat-project",
                "connection",
                side,
                new()
                {
                    ["name"] = side == "a" ? "Autodesk" : "RedEye",
                    ["provider"] = side == "a" ? "forma" : "redeye",
                    ["kind"] = "read",
                    ["configuration"] = new JsonObject(),
                }
            );
            db.Add(
                Tenant,
                "uat-project",
                "snapshot",
                side + "-sample",
                new()
                {
                    ["kind"] = "read",
                    ["connection_id"] = side,
                    ["generation"] = 1,
                    ["operation"] = "documents",
                    ["scope"] = new JsonObject(),
                    ["observed"] = DateTimeOffset.UtcNow.ToString("O"),
                    ["expires"] = DateTimeOffset
                        .UtcNow.AddMinutes(expired ? -1 : 30)
                        .ToUnixTimeSeconds(),
                    ["records"] = new JsonArray(
                        new JsonObject
                        {
                            ["id"] = side + "-document",
                            ["values"] = new JsonObject
                            {
                                ["number"] = "D-001",
                                ["title"] = "Floor plan",
                            },
                        }
                    ),
                    ["coverage"] = new JsonObject
                    {
                        ["description"] = "Simulated profile tests only",
                        ["complete"] = false,
                    },
                }
            );
        }
        await db.SaveChangesAsync();
        return client;
    }

    JsonObject Body(bool matching = false) =>
        new()
        {
            ["name"] = "Drawing parameters",
            ["source_snapshot"] = "a-sample",
            ["target_snapshot"] = "b-sample",
            ["source_key"] = matching ? "number" : "",
            ["target_key"] = matching ? "number" : "",
            ["rules"] = new JsonArray(
                new JsonObject
                {
                    ["source_field"] = "title",
                    ["target_field"] = "title",
                    ["transform"] = "copy",
                }
            ),
        };

    async Task<JsonObject> Ok(HttpResponseMessage response)
    {
        var text = await response.Content.ReadAsStringAsync();
        Assert.True(response.IsSuccessStatusCode, text);
        return JsonNode.Parse(text)!.AsObject();
    }

    [Fact]
    public async Task Parameter_profile_saves_without_matching_and_can_be_edited_in_place()
    {
        await using var factory = new Factory();
        using var client = await Setup(factory);
        var body = Body();
        var saved = await Ok(await client.PostAsJsonAsync(Root + "/mappings", body));
        var id = saved.S("id");
        Assert.Equal(
            HttpStatusCode.Conflict,
            (
                await client.PostAsJsonAsync(
                    Root + "/mappings/" + id + "/compare",
                    new { expected_version = 1 }
                )
            ).StatusCode
        );
        body["id"] = id;
        body["expected_version"] = 1;
        body["name"] = "Renamed reusable profile";
        body["source_key"] = "number";
        body["target_key"] = "number";
        var edited = await Ok(await client.PostAsJsonAsync(Root + "/mappings", body));
        Assert.Equal(id, edited.S("id"));
        Assert.Equal(2, edited.N("version"));
        Assert.Equal(
            HttpStatusCode.Conflict,
            (await client.PostAsJsonAsync(Root + "/mappings", body)).StatusCode
        );
        var context = await client.GetFromJsonAsync<JsonObject>(Root);
        Assert.Single(context!["mappings"]!.AsArray());
        Assert.Equal(
            "Renamed reusable profile",
            context["mappings"]![0]!["configuration"]!.S("name")
        );
        await Ok(
            await client.PostAsJsonAsync(
                Root + "/mappings/" + id + "/compare",
                new { expected_version = 2 }
            )
        );
        using var scope = factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<OrbitDb>();
        Assert.Equal(2, (await db.List(Tenant, "uat-project", "mapping-revision")).Count);
    }

    [Fact]
    public async Task Deletion_keeps_reports_history_and_removes_profile_from_dashboard()
    {
        await using var factory = new Factory();
        using var client = await Setup(factory);
        var saved = await Ok(await client.PostAsJsonAsync(Root + "/mappings", Body(true)));
        var id = saved.S("id");
        var compared = await Ok(
            await client.PostAsJsonAsync(
                Root + "/mappings/" + id + "/compare",
                new { expected_version = 1 }
            )
        );
        Assert.Equal(
            HttpStatusCode.UnprocessableEntity,
            (
                await client.SendAsync(
                    new(HttpMethod.Delete, Root + "/mappings/" + id)
                    {
                        Content = JsonContent.Create(
                            new { expected_version = 1, confirmed = false }
                        ),
                    }
                )
            ).StatusCode
        );
        Assert.Equal(
            HttpStatusCode.Conflict,
            (
                await client.SendAsync(
                    new(HttpMethod.Delete, Root + "/mappings/" + id)
                    {
                        Content = JsonContent.Create(
                            new { expected_version = 9, confirmed = true }
                        ),
                    }
                )
            ).StatusCode
        );
        var deleted = await Ok(
            await client.SendAsync(
                new(HttpMethod.Delete, Root + "/mappings/" + id)
                {
                    Content = JsonContent.Create(new { expected_version = 1, confirmed = true }),
                }
            )
        );
        Assert.True(deleted.B("reports_preserved"));
        var context = await client.GetFromJsonAsync<JsonObject>(Root);
        Assert.Empty(context!["mappings"]!.AsArray());
        Assert.True(context["reports"]![0].B("mapping_deleted"));
        Assert.Equal(0, context["validation"]!.N("fresh_reports"));
        Assert.Equal(0, context["validation"]!.N("stale_reports"));
        Assert.Equal(
            HttpStatusCode.OK,
            (await client.GetAsync(Root + "/reports/" + compared.S("id"))).StatusCode
        );
        Assert.Equal(
            HttpStatusCode.NotFound,
            (
                await client.PostAsJsonAsync(
                    Root + "/mappings/" + id + "/compare",
                    new { expected_version = 2 }
                )
            ).StatusCode
        );
        var summary = await client.GetFromJsonAsync<JsonObject>(
            "/api/projects/uat-project/connection-summary"
        );
        Assert.Equal(0, summary!.N("mapping_count"));
        using var scope = factory.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<OrbitDb>();
        Assert.Equal(2, (await db.List(Tenant, "uat-project", "mapping-revision")).Count);
        Assert.Contains(await db.List(Tenant, "uat-project", "audit"), r =>
            r.Data().S("action") == "analysis.mapping_deleted"
        );
    }

    [Fact]
    public async Task Expired_sample_schema_can_save_profiles_but_cannot_compare()
    {
        await using var factory = new Factory();
        using var client = await Setup(factory, true);
        var saved = await Ok(await client.PostAsJsonAsync(Root + "/mappings", Body(true)));
        Assert.Equal(
            HttpStatusCode.Conflict,
            (
                await client.PostAsJsonAsync(
                    Root + "/mappings/" + saved.S("id") + "/compare",
                    new { expected_version = 1 }
                )
            ).StatusCode
        );
    }

    [Fact]
    public async Task Editing_invalidates_old_report_and_uses_optimistic_versions()
    {
        await using var factory = new Factory();
        using var client = await Setup(factory);
        var body = Body(true);
        var saved = await Ok(await client.PostAsJsonAsync(Root + "/mappings", body));
        await Ok(
            await client.PostAsJsonAsync(
                Root + "/mappings/" + saved.S("id") + "/compare",
                new { expected_version = 1 }
            )
        );
        body["id"] = saved.S("id");
        body["expected_version"] = 1;
        body["name"] = "Updated profile";
        await Ok(await client.PostAsJsonAsync(Root + "/mappings", body));
        var context = await client.GetFromJsonAsync<JsonObject>(Root);
        Assert.True(context!["reports"]![0].B("stale"));
        Assert.Equal(0, context["validation"]!.N("fresh_reports"));
        Assert.Equal(1, context["validation"]!.N("stale_reports"));
    }

    [Fact]
    public async Task Viewer_and_other_projects_cannot_delete_profiles()
    {
        await using var factory = new Factory();
        using var client = await Setup(factory);
        var saved = await Ok(await client.PostAsJsonAsync(Root + "/mappings", Body()));
        const string viewer = "44444444-4444-4444-4444-444444444444";
        using (var scope = factory.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<OrbitDb>();
            db.Add(
                Tenant,
                "",
                "member",
                viewer,
                new() { ["role"] = "viewer", ["projects"] = new JsonArray("uat-project") }
            );
            await db.SaveChangesAsync();
        }
        var project = await Ok(
            await client.PostAsJsonAsync("/api/local/projects", new { name = "Other project" })
        );
        var path = Root + "/mappings/" + saved.S("id");
        Assert.Equal(
            HttpStatusCode.NotFound,
            (
                await client.SendAsync(
                    new(HttpMethod.Delete, path.Replace("uat-project", project.S("id")))
                    {
                        Content = JsonContent.Create(
                            new { expected_version = 1, confirmed = true }
                        ),
                    }
                )
            ).StatusCode
        );
        client.DefaultRequestHeaders.Remove("Test-Object");
        client.DefaultRequestHeaders.Add("Test-Object", viewer);
        var viewerSession = await client.GetFromJsonAsync<JsonObject>("/api/session");
        client.DefaultRequestHeaders.Remove("X-ORBIT-CSRF");
        client.DefaultRequestHeaders.Add("X-ORBIT-CSRF", viewerSession!.S("csrf_token"));
        Assert.Equal(
            HttpStatusCode.Forbidden,
            (
                await client.SendAsync(
                    new(HttpMethod.Delete, path)
                    {
                        Content = JsonContent.Create(
                            new { expected_version = 1, confirmed = true }
                        ),
                    }
                )
            ).StatusCode
        );
        Assert.Equal(
            HttpStatusCode.Forbidden,
            (await client.PostAsJsonAsync(Root + "/mappings", Body())).StatusCode
        );
    }

    [Fact]
    public async Task Copy_creates_a_separate_profile_without_modifying_original()
    {
        await using var factory = new Factory();
        using var client = await Setup(factory);
        var body = Body(true);
        var first = await Ok(await client.PostAsJsonAsync(Root + "/mappings", body));
        body["name"] = "Drawing parameters copy";
        var copy = await Ok(await client.PostAsJsonAsync(Root + "/mappings", body));
        Assert.NotEqual(first.S("id"), copy.S("id"));
        var context = await client.GetFromJsonAsync<JsonObject>(Root);
        Assert.Equal(2, context!["mappings"]!.AsArray().Count);
    }
}
