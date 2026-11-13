using System.Net;
using System.Net.Http.Json;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Orbit.Api;
using Xunit;

namespace Orbit.Tests;

public class ApsTransport : HttpMessageHandler
{
    public const string ClientId = "fixture-aps-client";
    public const string ClientSecret = "fixture-aps-secret-123";
    public int TokenCalls;
    public List<string> Gets = [];
    public List<Dictionary<string, string>> Forms = [];
    public Func<Task>? DuringToken;
    public bool RejectToken;
    public bool BadToken;
    public bool MalformedCollection;
    public bool OmitRefresh;
    public bool IncludeSecondHub = true;

    static HttpResponseMessage Response(JsonNode node) =>
        new(HttpStatusCode.OK)
        {
            Content = new StringContent(node.ToJsonString(), Encoding.UTF8, "application/json"),
        };

    static JsonObject Item(string id, string name, string type) =>
        new()
        {
            ["id"] = id,
            ["type"] = type,
            ["attributes"] = new JsonObject { ["name"] = name, ["displayName"] = name },
        };

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken ct
    )
    {
        Assert.Equal("https", request.RequestUri!.Scheme);
        Assert.Equal("developer.api.autodesk.com", request.RequestUri.Host);
        var path = Uri.UnescapeDataString(request.RequestUri.AbsolutePath);
        if (path == "/authentication/v2/token")
        {
            Assert.Equal(HttpMethod.Post, request.Method);
            Assert.Equal("Basic", request.Headers.Authorization!.Scheme);
            Assert.Equal(
                ClientId + ":" + ClientSecret,
                Encoding.UTF8.GetString(
                    Convert.FromBase64String(request.Headers.Authorization.Parameter!)
                )
            );
            var form = QueryHelpers
                .ParseQuery("?" + await request.Content!.ReadAsStringAsync(ct))
                .ToDictionary(p => p.Key, p => p.Value.ToString());
            Forms.Add(form);
            TokenCalls++;
            if (DuringToken != null)
                await DuringToken();
            if (RejectToken)
                return new(HttpStatusCode.BadRequest)
                {
                    Content = new StringContent(
                        "fixture vendor error must stay private: " + ClientSecret
                    ),
                };
            if (BadToken)
                return Response(
                    new JsonObject { ["access_token"] = "short", ["expires_in"] = 999999 }
                );
            var response = new JsonObject
            {
                ["access_token"] = "fixture-access-token-" + TokenCalls,
                ["expires_in"] = 3600,
                ["token_type"] = "Bearer",
                ["scope"] = "data:read",
            };
            if (!OmitRefresh)
                response["refresh_token"] = "fixture-refresh-token-" + TokenCalls;
            return Response(response);
        }
        Assert.Equal(HttpMethod.Get, request.Method);
        Assert.Equal("Bearer", request.Headers.Authorization!.Scheme);
        Assert.StartsWith("fixture-access-token-", request.Headers.Authorization.Parameter);
        Gets.Add(path + request.RequestUri.Query);
        if (MalformedCollection)
            return Response(new JsonObject { ["unexpected"] = new JsonArray() });
        var rows = new JsonArray();
        if (path == "/project/v1/hubs")
        {
            rows.Add(Item("b.hub-a", "Account A", "hubs"));
            if (IncludeSecondHub)
                rows.Add(Item("b.hub-b", "Account B", "hubs"));
        }
        else if (path == "/project/v1/hubs/b.hub-a/projects")
        {
            var query = QueryHelpers.ParseQuery(request.RequestUri.Query);
            Assert.Equal("25", query["page[limit]"]);
            var page = int.Parse(query["page[number]"]!);
            if (page == 0)
                for (var n = 0; n < 25; n++)
                    rows.Add(Item("b.project-" + n, "Project " + n, "projects"));
            else
                rows.Add(Item("b.project-25", "Project 25", "projects"));
        }
        else if (path == "/project/v1/hubs/b.hub-b/projects")
            rows.Add(Item("b.other-project", "Other project", "projects"));
        else if (path == "/project/v1/hubs/b.hub-a/projects/b.project-0/topFolders")
            rows.Add(Item("urn:adsk.wipprod:fs.folder:co.root-a", "Project Files", "folders"));
        else if (
            path
            == "/data/v1/projects/b.project-0/folders/urn:adsk.wipprod:fs.folder:co.root-a/contents"
        )
            rows.Add(Item("urn:adsk.wipprod:dm.lineage:file-a", "D-001.pdf", "items"));
        else
            throw new InvalidOperationException("Unexpected fixture request path: " + path);
        return Response(
            new JsonObject
            {
                ["data"] = rows,
                ["links"] = new JsonObject
                {
                    ["next"] = path.StartsWith("/data/", StringComparison.Ordinal)
                        ? null
                        : "https://unapproved.invalid/do-not-follow",
                },
            }
        );
    }
}

public sealed class ApsScenario : IAsyncDisposable
{
    public Factory Root;
    public WebApplicationFactory<Program> Host;
    public HttpClient Client;
    public ApsTransport Vendor;
    public string Id = "";
    public string Url => "/api/projects/uat-project/read-connections/" + Id + "/autodesk";

    public ApsScenario(
        ApsTransport? transport = null,
        bool fileUat = false,
        string? directory = null,
        string? origin = null
    )
    {
        Root = new Factory { FileUat = fileUat };
        if (directory != null)
            Root.Folder = directory;
        Vendor = transport ?? new();
        Host = Root.WithWebHostBuilder(b =>
        {
            if (origin != null)
                b.ConfigureAppConfiguration(
                    (_, c) =>
                        c.AddInMemoryCollection(
                            new Dictionary<string, string?> { ["Orbit:PublicOrigin"] = origin }
                        )
                );
            b.ConfigureServices(s =>
                s.AddHttpClient("vendor").ConfigurePrimaryHttpMessageHandler(() => Vendor)
            );
        });
        Client = NewClient();
    }

    public HttpClient NewClient(string user = "33333333-3333-3333-3333-333333333333")
    {
        var client = Host.CreateClient(
            new() { BaseAddress = new("https://localhost"), AllowAutoRedirect = false }
        );
        client.DefaultRequestHeaders.Add("Test-Object", user);
        return client;
    }

    public async Task Initialise(string mode = "three_legged")
    {
        await Client.GetAsync("/api/workspace");
        var session = await Get("/api/session");
        Client.DefaultRequestHeaders.Add("X-ORBIT-CSRF", session.S("csrf_token"));
        var created = await Post(
            "/api/projects/uat-project/read-connections",
            new
            {
                name = "APS test connection",
                provider = "forma",
                base_url = AutodeskOAuth.Api,
                auth_header = "",
                auth_prefix = "",
                vendor_settings_confirmed = true,
                approved_test_access = true,
                evidence_note = "Simulated APS test, no customer calls",
                hub = "",
                vendor_project = "",
                folder = "",
            }
        );
        Id = created.S("id");
        await Configure(mode);
    }

    public async Task Configure(string mode = "three_legged") =>
        await Check(
            await Client.PutAsJsonAsync(
                Url,
                new
                {
                    client_id = ApsTransport.ClientId,
                    client_secret = ApsTransport.ClientSecret,
                    mode,
                }
            )
        );

    public async Task<JsonObject> Get(string url) => await Check(await Client.GetAsync(url));

    public async Task<JsonObject> Post(string url, object body) =>
        await Check(await Client.PostAsJsonAsync(url, body));

    public static async Task<JsonObject> Check(HttpResponseMessage response)
    {
        var text = await response.Content.ReadAsStringAsync();
        Assert.True(response.IsSuccessStatusCode, text);
        return JsonNode.Parse(text)!.AsObject();
    }

    public async Task<string> Start()
    {
        var connected = await Post(Url + "/connect", new { });
        return connected.S("authorize_url");
    }

    public static string CallbackUrl(string url, string code = "fixture-authorization-code")
    {
        var query = QueryHelpers.ParseQuery(new Uri(url).Query);
        return AutodeskOAuth.CallbackPath
            + "?state="
            + Uri.EscapeDataString(query["state"].ToString())
            + "&code="
            + Uri.EscapeDataString(code);
    }

    public async Task ConnectThree()
    {
        var url = await Start();
        var response = await Client.GetAsync(CallbackUrl(url));
        Assert.Equal(HttpStatusCode.Found, response.StatusCode);
        Assert.Contains("autodesk=connected", response.Headers.Location!.ToString());
    }

    public async Task DiscoverAndSelect()
    {
        await Post(Url + "/discover", new { kind = "hubs" });
        await Post(
            Url + "/discover",
            new
            {
                kind = "projects",
                hub = "b.hub-a",
                page = 0,
            }
        );
        await Post(
            Url + "/discover",
            new
            {
                kind = "folders",
                hub = "b.hub-a",
                project = "b.project-0",
            }
        );
        await Check(
            await Client.PutAsJsonAsync(
                Url + "/selection",
                new
                {
                    hub = "b.hub-a",
                    project = "b.project-0",
                    folder = "urn:adsk.wipprod:fs.folder:co.root-a",
                }
            )
        );
    }

    public async Task Db(Func<OrbitDb, Task> work)
    {
        using var scope = Host.Services.CreateScope();
        await work(scope.ServiceProvider.GetRequiredService<OrbitDb>());
    }

    public async ValueTask DisposeAsync()
    {
        Client.Dispose();
        await Host.DisposeAsync();
        await Root.DisposeAsync();
    }
}

public sealed class AutodeskTests
{
    [Fact]
    public async Task Configuration_is_encrypted_and_exposes_exact_https_callback()
    {
        await using var x = new ApsScenario();
        await x.Initialise();
        var status = await x.Get(x.Url);
        Assert.Equal("https://localhost/api/autodesk/callback", status.S("callback_url"));
        Assert.Equal(ApsTransport.ClientId, status["app"]!.S("client_id"));
        Assert.DoesNotContain(ApsTransport.ClientSecret, status.ToJsonString());
        Assert.Equal(0, x.Vendor.TokenCalls);
        await x.Db(async db =>
        {
            var r = (
                await db.List("11111111-1111-1111-1111-111111111111", "uat-project", "aps-app")
            ).Single();
            Assert.DoesNotContain(ApsTransport.ClientSecret, r.Json);
            Assert.NotEqual(ApsTransport.ClientSecret, r.Secret);
        });
        var profiles = await x.Get("/api/projects/uat-project/read-connections");
        var issue = profiles["connections"]![0]!["readiness"]!["issues"]![0]!;
        Assert.Contains("Sign in with Autodesk", issue.S("message"));
        Assert.DoesNotContain("Add a credential", issue.ToJsonString());
    }

    [Fact]
    public async Task Three_legged_pkce_callback_discovery_documents_refresh_and_replay()
    {
        await using var x = new ApsScenario();
        await x.Initialise();
        var url = await x.Start();
        var query = QueryHelpers.ParseQuery(new Uri(url).Query);
        Assert.Equal("data:read", query["scope"]);
        Assert.Equal("S256", query["code_challenge_method"]);
        Assert.Equal("https://localhost/api/autodesk/callback", query["redirect_uri"]);
        var response = await x.Client.GetAsync(ApsScenario.CallbackUrl(url));
        Assert.Contains("autodesk=connected", response.Headers.Location!.ToString());
        var form = x.Vendor.Forms.Single();
        Assert.Equal("authorization_code", form["grant_type"]);
        Assert.Equal(
            query["code_challenge"],
            WebEncoders.Base64UrlEncode(
                SHA256.HashData(Encoding.ASCII.GetBytes(form["code_verifier"]))
            )
        );
        Assert.DoesNotContain(ApsTransport.ClientSecret, response.Headers.Location.ToString());
        var replay = await x.Client.GetAsync(ApsScenario.CallbackUrl(url));
        Assert.Contains("autodesk=failed", replay.Headers.Location!.ToString());
        Assert.Equal(1, x.Vendor.TokenCalls);
        await x.DiscoverAndSelect();
        var documents = await x.Post(
            x.Url.Replace("/autodesk", "/read"),
            new
            {
                operation = "documents",
                hub = "b.hub-a",
                project = "b.project-0",
                folder = "urn:adsk.wipprod:fs.folder:co.root-a",
            }
        );
        Assert.Equal("D-001.pdf", documents["resources"]![0]!.S("label"));
        Assert.Equal(1, documents.N("returned"));
        var status = await x.Get(x.Url);
        Assert.True(status.B("renewal_available"));
        var renewed = await x.Post(x.Url + "/renew", new { });
        Assert.True(renewed.B("renewed"));
        Assert.Equal("refresh_token", x.Vendor.Forms.Last()["grant_type"]);
        Assert.Equal("fixture-refresh-token-1", x.Vendor.Forms.Last()["refresh_token"]);
        await x.Post(x.Url + "/renew", new { });
        Assert.Equal("fixture-refresh-token-2", x.Vendor.Forms.Last()["refresh_token"]);
        await x.Post(x.Url.Replace("/autodesk", "/read"), new { operation = "documents" });
        Assert.Equal(3, x.Vendor.TokenCalls);
    }

    [Fact]
    public async Task Two_legged_token_and_project_paging_use_fixed_scoped_endpoints()
    {
        await using var x = new ApsScenario();
        await x.Initialise("two_legged");
        var connected = await x.Post(x.Url + "/connect", new { });
        Assert.True(connected.B("connected"));
        Assert.Equal("client_credentials", x.Vendor.Forms.Single()["grant_type"]);
        Assert.Equal("data:read", x.Vendor.Forms.Single()["scope"]);
        await x.Post(x.Url + "/discover", new { kind = "hubs" });
        var page0 = await x.Post(
            x.Url + "/discover",
            new
            {
                kind = "projects",
                hub = "b.hub-a",
                page = 0,
            }
        );
        Assert.Equal(25, page0.N("returned"));
        var page1 = await x.Post(
            x.Url + "/discover",
            new
            {
                kind = "projects",
                hub = "b.hub-a",
                page = 1,
            }
        );
        Assert.Equal("b.project-25", page1["resources"]![0]!.S("id"));
        Assert.All(x.Vendor.Gets, p => Assert.DoesNotContain("unapproved", p));
        await x.Post(x.Url + "/renew", new { });
        Assert.Equal("client_credentials", x.Vendor.Forms.Last()["grant_type"]);
    }

    [Theory]
    [InlineData("missing_browser")]
    [InlineData("session_changed")]
    [InlineData("expired")]
    [InlineData("denied")]
    [InlineData("settings_changed")]
    [InlineData("bad_state")]
    public async Task Invalid_consent_never_exchanges_a_code(string scenario)
    {
        await using var x = new ApsScenario();
        await x.Initialise();
        var url = await x.Start();
        var callback = ApsScenario.CallbackUrl(url);
        HttpClient client = x.Client;
        if (scenario == "missing_browser")
            client = x.NewClient();
        if (scenario == "session_changed")
            client.DefaultRequestHeaders.Add("Test-Session", "different-session");
        if (scenario == "expired")
            await x.Db(async db =>
            {
                var state = (
                    await db.List(
                        "11111111-1111-1111-1111-111111111111",
                        "uat-project",
                        "aps-state"
                    )
                ).Single();
                var d = state.Data();
                d["expires"] = 0;
                db.Change(state, d);
                await db.SaveChangesAsync();
            });
        if (scenario == "denied")
            callback += "&error=access_denied";
        if (scenario == "settings_changed")
            await x.Configure();
        if (scenario == "bad_state")
            callback =
                AutodeskOAuth.CallbackPath + "?state=" + new string('x', 64) + "&code=ignored";
        var response = await client.GetAsync(callback);
        Assert.Equal(HttpStatusCode.Found, response.StatusCode);
        Assert.Contains("autodesk=failed", response.Headers.Location!.ToString());
        Assert.Equal(0, x.Vendor.TokenCalls);
        if (client != x.Client)
            client.Dispose();
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public async Task Rejected_or_malformed_token_does_not_leak_credentials(bool malformed)
    {
        var vendor = new ApsTransport { RejectToken = !malformed, BadToken = malformed };
        await using var x = new ApsScenario(vendor);
        await x.Initialise("two_legged");
        var response = await x.Client.PostAsJsonAsync(x.Url + "/connect", new { });
        Assert.Equal(HttpStatusCode.BadGateway, response.StatusCode);
        Assert.DoesNotContain(
            ApsTransport.ClientSecret,
            await response.Content.ReadAsStringAsync()
        );
        Assert.Null((await x.Get(x.Url))["expires"]);
    }

    [Fact]
    public async Task Discovery_rejects_undiscovered_scope_expired_lists_and_forged_selection()
    {
        await using var x = new ApsScenario();
        await x.Initialise("two_legged");
        await x.Post(x.Url + "/connect", new { });
        Assert.Equal(
            HttpStatusCode.Conflict,
            (
                await x.Client.PostAsJsonAsync(
                    x.Url + "/discover",
                    new { kind = "projects", hub = "b.hub-a" }
                )
            ).StatusCode
        );
        Assert.Empty(x.Vendor.Gets);
        await x.Post(x.Url + "/discover", new { kind = "hubs" });
        await x.Post(x.Url + "/discover", new { kind = "projects", hub = "b.hub-a" });
        var count = x.Vendor.Gets.Count;
        Assert.Equal(
            HttpStatusCode.Conflict,
            (
                await x.Client.PostAsJsonAsync(
                    x.Url + "/discover",
                    new
                    {
                        kind = "folders",
                        hub = "b.hub-a",
                        project = "b.other-project",
                    }
                )
            ).StatusCode
        );
        Assert.Equal(
            HttpStatusCode.Conflict,
            (
                await x.Client.PutAsJsonAsync(
                    x.Url + "/selection",
                    new
                    {
                        hub = "b.hub-a",
                        project = "b.project-0",
                        folder = "forged-folder",
                    }
                )
            ).StatusCode
        );
        Assert.Equal(count, x.Vendor.Gets.Count);
        Assert.Equal(
            HttpStatusCode.UnprocessableEntity,
            (
                await x.Client.PostAsJsonAsync(x.Url + "/discover", new { kind = "hubs", page = 2 })
            ).StatusCode
        );
        await x.Db(async db =>
        {
            foreach (
                var row in await db.List(
                    "11111111-1111-1111-1111-111111111111",
                    "uat-project",
                    "aps-choice"
                )
            )
            {
                var d = row.Data();
                d["expires"] = 0;
                db.Change(row, d);
            }
            await db.SaveChangesAsync();
        });
        Assert.Equal(
            HttpStatusCode.Conflict,
            (
                await x.Client.PostAsJsonAsync(
                    x.Url + "/discover",
                    new { kind = "projects", hub = "b.hub-a" }
                )
            ).StatusCode
        );
        Assert.Equal(count, x.Vendor.Gets.Count);
    }

    [Fact]
    public async Task Expired_token_requires_renewal_and_disconnect_clears_all_aps_material()
    {
        await using var x = new ApsScenario();
        await x.Initialise("two_legged");
        await x.Post(x.Url + "/connect", new { });
        await x.DiscoverAndSelect();
        var gets = x.Vendor.Gets.Count;
        await x.Db(async db =>
        {
            var r = (
                await db.List("11111111-1111-1111-1111-111111111111", "uat-project", "connection")
            ).Single();
            var d = r.Data();
            d["autodesk_expires"] = 1;
            db.Change(r, d);
            await db.SaveChangesAsync();
        });
        var response = await x.Client.PostAsJsonAsync(
            x.Url.Replace("/autodesk", "/read"),
            new { operation = "documents" }
        );
        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
        Assert.Contains("Renew authorisation", await response.Content.ReadAsStringAsync());
        Assert.Equal(gets, x.Vendor.Gets.Count);
        await ApsScenario.Check(await x.Client.DeleteAsync(x.Url));
        var status = await x.Get(x.Url);
        Assert.Null(status["app"]);
        Assert.Null(status["expires"]);
        await x.Db(async db =>
        {
            foreach (var kind in new[] { "aps-app", "aps-token", "aps-state", "aps-choice" })
                Assert.Empty(
                    await db.List("11111111-1111-1111-1111-111111111111", "uat-project", kind)
                );
            Assert.Null(
                (await db.List("11111111-1111-1111-1111-111111111111", "uat-project", "connection"))
                    .Single()
                    .Secret
            );
        });
    }

    [Fact]
    public async Task Settings_changed_during_exchange_discards_token()
    {
        await using var x = new ApsScenario();
        await x.Initialise("two_legged");
        x.Vendor.DuringToken = () =>
            x.Db(async db =>
            {
                var r = (
                    await db.List(
                        "11111111-1111-1111-1111-111111111111",
                        "uat-project",
                        "connection"
                    )
                ).Single();
                db.Change(r, r.Data());
                await db.SaveChangesAsync();
            });
        var response = await x.Client.PostAsJsonAsync(x.Url + "/connect", new { });
        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
        Assert.Null((await x.Get(x.Url))["expires"]);
    }

    [Fact]
    public async Task Role_and_tenant_denials_apply_to_oauth_endpoints()
    {
        await using var x = new ApsScenario();
        await x.Initialise();
        const string viewer = "44444444-4444-4444-4444-444444444444";
        await x.Db(async db =>
        {
            db.Add(
                "11111111-1111-1111-1111-111111111111",
                "",
                "member",
                viewer,
                new() { ["role"] = "viewer", ["projects"] = new JsonArray("uat-project") }
            );
            await db.SaveChangesAsync();
        });
        using var c = x.NewClient(viewer);
        Assert.Equal(HttpStatusCode.Forbidden, (await c.GetAsync(x.Url)).StatusCode);
        c.DefaultRequestHeaders.Add("Test-Tenant", "55555555-5555-5555-5555-555555555555");
        Assert.Equal(HttpStatusCode.Unauthorized, (await c.GetAsync(x.Url)).StatusCode);
    }

    [Fact]
    public async Task File_uat_preserves_aps_settings_and_encrypted_refresh_across_restart()
    {
        var directory = Path.Combine(Path.GetTempPath(), "aps-restart-" + Guid.NewGuid());
        string id;
        await using (var first = new ApsScenario(fileUat: true, directory: directory))
        {
            await first.Initialise();
            await first.ConnectThree();
            id = first.Id;
        }
        await using (var next = new ApsScenario(fileUat: true, directory: directory))
        {
            next.Id = id;
            var session = await next.Get("/api/session");
            next.Client.DefaultRequestHeaders.Add("X-ORBIT-CSRF", session.S("csrf_token"));
            var status = await next.Get(next.Url);
            Assert.Equal(ApsTransport.ClientId, status["app"]!.S("client_id"));
            Assert.True(status.B("renewal_available"));
            await next.Post(next.Url + "/renew", new { });
            Assert.Equal("fixture-refresh-token-1", next.Vendor.Forms.Single()["refresh_token"]);
        }
    }

    [Fact]
    public async Task Canonical_callback_does_not_accept_a_different_browser_host()
    {
        await using var x = new ApsScenario(origin: "https://orbit.example");
        await x.Initialise();
        Assert.Equal(
            "https://orbit.example/api/autodesk/callback",
            (await x.Get(x.Url)).S("callback_url")
        );
        var response = await x.Client.PostAsJsonAsync(x.Url + "/connect", new { });
        Assert.Equal(HttpStatusCode.Conflict, response.StatusCode);
        Assert.Equal(0, x.Vendor.TokenCalls);
    }

    [Fact]
    public async Task Permission_removed_during_callback_discards_exchanged_token()
    {
        await using var x = new ApsScenario();
        await x.Initialise();
        const string operatorId = "66666666-6666-6666-6666-666666666666";
        await x.Db(async db =>
        {
            db.Add(
                "11111111-1111-1111-1111-111111111111",
                "",
                "member",
                operatorId,
                new() { ["role"] = "owner", ["projects"] = new JsonArray("uat-project") }
            );
            await db.SaveChangesAsync();
        });
        using var client = x.NewClient(operatorId);
        var session = await ApsScenario.Check(await client.GetAsync("/api/session"));
        client.DefaultRequestHeaders.Add("X-ORBIT-CSRF", session.S("csrf_token"));
        var started = await ApsScenario.Check(
            await client.PostAsJsonAsync(x.Url + "/connect", new { })
        );
        x.Vendor.DuringToken = () =>
            x.Db(async db =>
            {
                var member = (
                    await db.Find("11111111-1111-1111-1111-111111111111", "", "member", operatorId)
                )!;
                var data = member.Data();
                data["role"] = "viewer";
                db.Change(member, data);
                await db.SaveChangesAsync();
            });
        var response = await client.GetAsync(ApsScenario.CallbackUrl(started.S("authorize_url")));
        Assert.Contains("autodesk=failed", response.Headers.Location!.ToString());
        Assert.Equal(1, x.Vendor.TokenCalls);
        Assert.Null((await x.Get(x.Url))["expires"]);
    }

    [Fact]
    public async Task Connection_id_cannot_be_used_in_another_project()
    {
        await using var x = new ApsScenario();
        await x.Initialise();
        var project = await x.Post("/api/local/projects", new { name = "Separate test project" });
        var wrong = x.Url.Replace("uat-project", project.S("id"));
        Assert.Equal(HttpStatusCode.NotFound, (await x.Client.GetAsync(wrong)).StatusCode);
        Assert.Equal(0, x.Vendor.TokenCalls);
    }

    [Fact]
    public async Task Renewal_without_replacement_refresh_preserves_previous_refresh()
    {
        await using var x = new ApsScenario();
        await x.Initialise();
        await x.ConnectThree();
        x.Vendor.OmitRefresh = true;
        await x.Post(x.Url + "/renew", new { });
        await x.Post(x.Url + "/renew", new { });
        Assert.Equal("fixture-refresh-token-1", x.Vendor.Forms.Last()["refresh_token"]);
    }
}
