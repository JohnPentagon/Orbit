using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.WebUtilities;
using Orbit.Api;
using Xunit;

namespace Orbit.Tests;

public sealed class FolderTransport : ApsTransport
{
    public const string Root = "urn:adsk.wipprod:fs.folder:co.root-a";
    public const string Structural = "urn:adsk.wipprod:fs.folder:co.structural";
    public const string Drawings = "urn:adsk.wipprod:fs.folder:co.drawings";
    public bool RepeatPage;
    public bool RemoveFile;
    public Func<Task>? DuringPage;

    public static string File(int n) => "urn:fixture:lineage:ga-" + n;

    static JsonObject Entry(string id, string label, string type) =>
        new()
        {
            ["id"] = id,
            ["type"] = type,
            ["attributes"] = new JsonObject { ["displayName"] = label, ["name"] = label },
        };

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken ct
    )
    {
        var path = Uri.UnescapeDataString(request.RequestUri!.AbsolutePath);
        if (!path.StartsWith("/data/v1/projects/b.project-0/folders/", StringComparison.Ordinal))
            return await base.SendAsync(request, ct);
        Assert.Equal("developer.api.autodesk.com", request.RequestUri.Host);
        Assert.Equal(HttpMethod.Get, request.Method);
        Assert.Equal("Bearer", request.Headers.Authorization!.Scheme);
        Gets.Add(path + request.RequestUri.Query);
        if (DuringPage != null)
            await DuringPage();
        var query = QueryHelpers.ParseQuery(request.RequestUri.Query);
        Assert.Equal("25", query["page[limit]"]);
        var page = int.Parse(query["page[number]"]!);
        var folder = path["/data/v1/projects/b.project-0/folders/".Length..^"/contents".Length];
        var entries = new List<JsonObject>();
        if (folder == Root)
        {
            entries.Add(Entry(Structural, "Structural", "folders"));
            for (var n = 0; n < 30; n++)
                entries.Add(Entry("urn:fixture:root-file-" + n, $"Root-{n:000}.pdf", "items"));
        }
        else if (folder == Structural)
        {
            entries.Add(Entry(Drawings, "GA drawings", "folders"));
            for (var n = 0; n < 61; n++)
                entries.Add(
                    Entry("urn:fixture:structural-file-" + n, $"Structural-{n:000}.pdf", "items")
                );
        }
        else if (folder == Drawings)
        {
            for (var n = 0; n < 60; n++)
                if (!RemoveFile || n != 37)
                    entries.Add(Entry(File(n), $"GA-{n:000}.pdf", "items"));
        }
        else
            throw new InvalidOperationException("Unexpected folder fixture " + folder);
        var effective = RepeatPage ? 0 : page;
        var rows = new JsonArray(
            entries.Skip(effective * 25).Take(25).Select(n => (JsonNode)n).ToArray()
        );
        var more = RepeatPage || entries.Count > (effective + 1) * 25;
        return new(HttpStatusCode.OK)
        {
            Content = new StringContent(
                new JsonObject
                {
                    ["data"] = rows,
                    ["links"] = new JsonObject
                    {
                        ["next"] = more ? "https://unapproved.invalid/never-follow" : null,
                    },
                }.ToJsonString(),
                Encoding.UTF8,
                "application/json"
            ),
        };
    }
}

public sealed class AutodeskFolderTests
{
    async Task Roots(ApsScenario x)
    {
        await x.Initialise("two_legged");
        await x.Post(x.Url + "/connect", new { });
        await x.Post(x.Url + "/discover", new { kind = "hubs" });
        await x.Post(x.Url + "/discover", new { kind = "projects", hub = "b.hub-a" });
        await x.Post(
            x.Url + "/discover",
            new
            {
                kind = "folders",
                hub = "b.hub-a",
                project = "b.project-0",
            }
        );
    }

    Task<JsonObject> Browse(ApsScenario x, string folder, int page = 0) =>
        x.Post(
            x.Url + "/discover",
            new
            {
                kind = "contents",
                hub = "b.hub-a",
                project = "b.project-0",
                folder,
                page,
            }
        );

    async Task Nested(ApsScenario x)
    {
        await Roots(x);
        await Browse(x, FolderTransport.Root);
        await Browse(x, FolderTransport.Structural);
        await Browse(x, FolderTransport.Drawings);
    }

    Task<HttpResponseMessage> Save(ApsScenario x, string folder, string[] files, int limit = 100) =>
        x.Client.PutAsJsonAsync(
            x.Url + "/selection",
            new
            {
                hub = "b.hub-a",
                project = "b.project-0",
                folder,
                file_ids = files,
                document_limit = limit,
            }
        );

    [Fact]
    public async Task Nested_browsing_and_paging_select_exact_files_for_read_and_comparison()
    {
        var vendor = new FolderTransport();
        await using var x = new ApsScenario(vendor);
        await Nested(x);
        var page1 = await Browse(x, FolderTransport.Drawings, 1);
        Assert.Equal(50, page1.N("loaded_count"));
        Assert.True(page1.B("has_more"));
        Assert.Equal(3, page1["folder"]!["path"]!.AsArray().Count);
        await ApsScenario.Check(
            await Save(
                x,
                FolderTransport.Drawings,
                [FolderTransport.File(37), FolderTransport.File(48)]
            )
        );
        var read = await x.Post(
            x.Url.Replace("/autodesk", "/read"),
            new { operation = "documents" }
        );
        Assert.Equal(2, read.N("returned"));
        Assert.Equal(2, read.N("pages_read"));
        Assert.Equal(
            new[] { FolderTransport.File(37), FolderTransport.File(48) },
            read["resources"]!.AsArray().Select(r => r.S("id")).ToArray()
        );
        Assert.All(read["resources"]!.AsArray(), r => Assert.Equal("items", r.S("kind")));
        var snapshot = await x.Post(
            "/api/projects/uat-project/analysis/capture",
            new { kind = "read", id = x.Id }
        );
        Assert.Equal(2, snapshot["snapshot"]!.N("record_count"));
        Assert.Equal(2, snapshot["snapshot"]!["scope"]!["file_ids"]!.AsArray().Count);
        Assert.DoesNotContain(vendor.Gets, g => g.Contains("unapproved"));
        var saved = await Browse(x, FolderTransport.Drawings);
        Assert.Equal(3, saved["folder"]!["path"]!.AsArray().Count);
    }

    [Fact]
    public async Task Folder_read_excludes_subfolders_and_reads_more_than_25_files()
    {
        await using var x = new ApsScenario(new FolderTransport());
        await Roots(x);
        await Browse(x, FolderTransport.Root);
        await ApsScenario.Check(await Save(x, FolderTransport.Root, [], 100));
        var read = await x.Post(
            x.Url.Replace("/autodesk", "/read"),
            new { operation = "documents" }
        );
        Assert.Equal(30, read.N("returned"));
        Assert.Equal(2, read.N("pages_read"));
        Assert.DoesNotContain(read["resources"]!.AsArray(), r => r.S("kind") == "folders");
        Assert.Contains("not read recursively", read.S("coverage"));
    }

    [Fact]
    public async Task Explicit_read_limit_is_reported_instead_of_claiming_completeness()
    {
        await using var x = new ApsScenario(new FolderTransport());
        await Nested(x);
        await ApsScenario.Check(await Save(x, FolderTransport.Drawings, [], 25));
        var read = await x.Post(
            x.Url.Replace("/autodesk", "/read"),
            new { operation = "documents" }
        );
        Assert.Equal(25, read.N("returned"));
        Assert.True(read.B("more_available"));
        Assert.Contains("More folder data may remain", read.S("coverage"));
    }

    [Fact]
    public async Task Undiscovered_folders_and_cross_folder_file_ids_are_rejected()
    {
        var vendor = new FolderTransport();
        await using var x = new ApsScenario(vendor);
        await Roots(x);
        var count = vendor.Gets.Count;
        Assert.Equal(
            HttpStatusCode.Conflict,
            (
                await x.Client.PostAsJsonAsync(
                    x.Url + "/discover",
                    new
                    {
                        kind = "contents",
                        hub = "b.hub-a",
                        project = "b.project-0",
                        folder = FolderTransport.Drawings,
                    }
                )
            ).StatusCode
        );
        Assert.Equal(count, vendor.Gets.Count);
        await Browse(x, FolderTransport.Root);
        Assert.Equal(
            HttpStatusCode.Conflict,
            (await Save(x, FolderTransport.Root, [FolderTransport.File(37)])).StatusCode
        );
        Assert.Equal(
            HttpStatusCode.UnprocessableEntity,
            (await Save(x, FolderTransport.Root, [FolderTransport.Structural])).StatusCode
        );
        Assert.Equal(
            HttpStatusCode.Conflict,
            (
                await x.Client.PostAsJsonAsync(
                    x.Url + "/discover",
                    new
                    {
                        kind = "contents",
                        hub = "b.hub-a",
                        project = "b.project-0",
                        folder = FolderTransport.Root,
                        page = 2,
                    }
                )
            ).StatusCode
        );
    }

    [Fact]
    public async Task Missing_selected_file_requires_review_instead_of_a_partial_silent_capture()
    {
        var vendor = new FolderTransport();
        await using var x = new ApsScenario(vendor);
        await Nested(x);
        await Browse(x, FolderTransport.Drawings, 1);
        await ApsScenario.Check(
            await Save(x, FolderTransport.Drawings, [FolderTransport.File(37)])
        );
        vendor.RemoveFile = true;
        var read = await x.Client.PostAsJsonAsync(
            "/api/projects/uat-project/analysis/capture",
            new { kind = "read", id = x.Id }
        );
        Assert.Equal(HttpStatusCode.Conflict, read.StatusCode);
        Assert.Contains("Some selected files", await read.Content.ReadAsStringAsync());
        await x.Db(async db =>
            Assert.Empty(
                await db.List("11111111-1111-1111-1111-111111111111", "uat-project", "snapshot")
            )
        );
    }

    [Fact]
    public async Task Repeated_vendor_page_does_not_become_a_complete_result()
    {
        var vendor = new FolderTransport();
        await using var x = new ApsScenario(vendor);
        await Nested(x);
        await ApsScenario.Check(await Save(x, FolderTransport.Drawings, [], 100));
        vendor.RepeatPage = true;
        Assert.Equal(
            HttpStatusCode.BadGateway,
            (
                await x.Client.PostAsJsonAsync(
                    x.Url.Replace("/autodesk", "/read"),
                    new { operation = "documents" }
                )
            ).StatusCode
        );
    }

    [Fact]
    public async Task Saving_an_unseen_file_or_an_invalid_limit_is_rejected()
    {
        await using var x = new ApsScenario(new FolderTransport());
        await Nested(x);
        Assert.Equal(
            HttpStatusCode.Conflict,
            (await Save(x, FolderTransport.Drawings, [FolderTransport.File(37)])).StatusCode
        );
        Assert.Equal(
            HttpStatusCode.UnprocessableEntity,
            (await Save(x, FolderTransport.Drawings, [], 1000)).StatusCode
        );
    }

    [Fact]
    public async Task Scope_change_during_paged_read_discards_capture()
    {
        var vendor = new FolderTransport();
        await using var x = new ApsScenario(vendor);
        await Nested(x);
        await ApsScenario.Check(await Save(x, FolderTransport.Drawings, [], 100));
        var changed = false;
        vendor.DuringPage = async () =>
        {
            if (changed)
                return;
            changed = true;
            await x.Db(async db =>
            {
                var r = (
                    await db.Find(
                        "11111111-1111-1111-1111-111111111111",
                        "uat-project",
                        "connection",
                        x.Id
                    )
                )!;
                db.Change(r, r.Data());
                await db.SaveChangesAsync();
            });
        };
        Assert.Equal(
            HttpStatusCode.Conflict,
            (
                await x.Client.PostAsJsonAsync(
                    "/api/projects/uat-project/analysis/capture",
                    new { kind = "read", id = x.Id }
                )
            ).StatusCode
        );
        await x.Db(async db =>
            Assert.Empty(
                await db.List("11111111-1111-1111-1111-111111111111", "uat-project", "snapshot")
            )
        );
    }
}
