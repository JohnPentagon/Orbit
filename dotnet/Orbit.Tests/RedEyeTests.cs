using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.Hosting;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Orbit.Api;
using Xunit;

namespace Orbit.Tests;

public sealed class VendorHandler : HttpMessageHandler
{
    public int Writes;
    public List<string> Headers = [];
    public JsonObject Document = JsonNode
        .Parse(
            """{"id":777,"number":"D-001","title":"Drawing","modified":"2026-11-12T10:00:00Z","state":{"is_modifiable":true},"revisions":[{"id":77,"status":"approved","version":"A"}],"groups":[],"metadata":[{"id":1,"key_id":10,"key_name":"Discipline","value":"Civil"},{"id":2,"key_id":20,"key_name":"Note","value":"Preserve this"}]}"""
        )!
        .AsObject();

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken ct
    )
    {
        Headers.Add(request.Headers.GetValues("Authorization").Single());
        if (request.Method == HttpMethod.Post)
        {
            Writes++;
            var payload = JsonNode.Parse(await request.Content!.ReadAsStringAsync(ct))!;
            var rows = new JsonArray();
            foreach (var p in payload["metadata"]!.AsArray())
            foreach (var v in p!["value"]!.AsArray())
                rows.Add(
                    new JsonObject
                    {
                        ["id"] = rows.Count + 1,
                        ["key_id"] = p.S("name") == "Discipline" ? 10 : 20,
                        ["key_name"] = p.S("name"),
                        ["value"] = v!.DeepClone(),
                    }
                );
            Document["metadata"] = rows;
            return new(HttpStatusCode.OK) { Content = new StringContent("{}") };
        }
        var body = request.RequestUri!.AbsolutePath switch
        {
            "/api/v1/metadata-keys" =>
                """[{"id":10,"name":"Discipline"},{"id":20,"name":"Note"}]""",
            "/api/v1/artefacts/777" => Document.ToJsonString(),
            _ => """[{"id":777,"title":"Drawing","number":"D-001"}]""",
        };
        return new(HttpStatusCode.OK)
        {
            Content = new StringContent(body, Encoding.UTF8, "application/json"),
        };
    }
}

public sealed class RedEyeTests
{
    [Fact]
    public async Task Native_metadata_inspect_verify_and_comparison_capture_preserve_fields()
    {
        await using var f = new Factory();
        var handler = new VendorHandler();
        await using var host = f.WithWebHostBuilder(b =>
            b.ConfigureServices(s =>
                s.AddHttpClient("vendor").ConfigurePrimaryHttpMessageHandler(() => handler)
            )
        );
        using var c = host.CreateClient(
            new() { BaseAddress = new("https://localhost"), AllowAutoRedirect = false }
        );
        c.DefaultRequestHeaders.Add("Test-Object", "33333333-3333-3333-3333-333333333333");
        await c.GetAsync("/api/workspace");
        var session = await c.GetFromJsonAsync<JsonObject>("/api/session");
        c.DefaultRequestHeaders.Add("X-ORBIT-CSRF", session!.S("csrf_token"));
        var created = await c.PostAsJsonAsync(
            "/api/projects/uat-project/read-connections",
            new
            {
                name = "RedEye",
                provider = "redeye",
                base_url = "https://api.redeyedms.com",
                auth_header = "Authorization",
                auth_prefix = "Bearer",
                vendor_settings_confirmed = true,
                approved_test_access = true,
                evidence_note = "Fixture",
            }
        );
        var id = (await created.Content.ReadFromJsonAsync<JsonObject>())!.S("id");
        await c.PutAsJsonAsync(
            $"/api/projects/uat-project/read-connections/{id}/credential",
            new { secret = "synthetic-uat-key" }
        );
        var root = "/api/projects/uat-project/redeye-metadata";
        var inspected = await c.PostAsJsonAsync(
            root + "/inspect",
            new { connection_id = id, artefact_id = 777 }
        );
        Assert.Equal(HttpStatusCode.OK, inspected.StatusCode);
        var inspection = (await inspected.Content.ReadFromJsonAsync<JsonObject>())!;
        Assert.Equal("Civil", inspection["snapshot"]!["values"]!["10"]![0]!.ToString());
        var verified = await c.PostAsJsonAsync(
            root + "/verify",
            new
            {
                inspection_id = inspection.S("id"),
                metadata_key_id = 10,
                values = new[] { "Civil" },
                property_uri = "",
                unit = "",
                overwrite_existing = false,
            }
        );
        Assert.Equal(HttpStatusCode.OK, verified.StatusCode);
        Assert.True((await verified.Content.ReadFromJsonAsync<JsonObject>())!.B("matches"));
        var capture = await c.PostAsJsonAsync(
            "/api/projects/uat-project/analysis/capture",
            new
            {
                kind = "read",
                id,
                artefact_ids = new[] { 777 },
            }
        );
        Assert.Equal(HttpStatusCode.OK, capture.StatusCode);
        var snapshot = (await capture.Content.ReadFromJsonAsync<JsonObject>())!["snapshot"]!;
        Assert.Contains(
            "metadata.Discipline",
            snapshot["fields"]!.AsArray().Select(x => x!.ToString())
        );
        Assert.All(handler.Headers, h => Assert.Equal("Bearer synthetic-uat-key", h));
        Assert.Equal(0, handler.Writes);
    }

    [Theory]
    [InlineData("http://api.redeyedms.com")]
    [InlineData("https://127.0.0.1")]
    [InlineData("https://api.redeyedms.com.evil.test")]
    [InlineData("https://api.redeyedms.com?key=x")]
    public void Reject_unapproved_origins(string origin)
    {
        var config = new Microsoft.Extensions.Configuration.ConfigurationBuilder()
            .AddInMemoryCollection(
                new Dictionary<string, string?>
                {
                    ["Orbit:EncryptionKey"] = Convert.ToBase64String(new byte[32]),
                }
            )
            .Build();
        var cipher = new Cipher(config);
        var service = new ConnectorService(null!, config, cipher);
        Assert.Throws<ApiException>(() => service.Approved(origin));
    }
}
