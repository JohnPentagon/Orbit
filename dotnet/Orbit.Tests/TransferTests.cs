using System.Net;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Orbit.Api;
using Xunit;

namespace Orbit.Tests;

public sealed class TransferTransport : HttpMessageHandler
{
    public byte[] Bytes = Encoding.UTF8.GetBytes("Fixture original file bytes");
    public int Uploads;
    public int Assignments;
    public bool LostUploadResponse;
    public bool Duplicate;
    public bool BadStorage;
    public bool ChangedVersion;
    public bool BadReadback;
    public bool OversizedSource;
    public bool FailGroups;
    public Func<Task>? DuringDownload;
    public Func<Task>? DuringUpload;
    public JsonObject? Payload;
    public JsonArray Groups = new();

    HttpResponseMessage Json(JsonNode value) =>
        new(HttpStatusCode.OK)
        {
            Content = new StringContent(value.ToJsonString(), Encoding.UTF8, "application/json"),
        };

    protected override async Task<HttpResponseMessage> SendAsync(
        HttpRequestMessage request,
        CancellationToken ct
    )
    {
        var u = request.RequestUri!;
        var path = Uri.UnescapeDataString(u.AbsolutePath);
        if (u.Host.EndsWith("s3.amazonaws.com", StringComparison.Ordinal))
        {
            Assert.False(request.Headers.Contains("Authorization"));
            if (DuringDownload != null)
            {
                var action = DuringDownload;
                DuringDownload = null;
                await action();
            }
            if (OversizedSource && path == "/source.bin")
            {
                var content = new ByteArrayContent(Bytes);
                content.Headers.ContentLength = TransferVendor.MaxBytes + 1L;
                return new(HttpStatusCode.OK) { Content = content };
            }
            return new(HttpStatusCode.OK)
            {
                Content = new ByteArrayContent(
                    BadReadback && path == "/destination.bin" ? [1, 2, 3] : Bytes
                ),
            };
        }
        Assert.Equal("https", u.Scheme);
        Assert.Equal(
            u.Host == "api.redeyedms.com"
                ? "Bearer redeye-fixture-key"
                : "Bearer aps-fixture-token",
            request.Headers.GetValues("Authorization").Single()
        );
        if (u.Host == "developer.api.autodesk.com")
        {
            if (path.Contains("/items/"))
            {
                var item = path[(path.LastIndexOf('/') + 1)..];
                return Json(
                    new JsonObject
                    {
                        ["data"] = new JsonObject
                        {
                            ["id"] = item,
                            ["type"] = "items",
                            ["attributes"] = new JsonObject
                            {
                                ["displayName"] = "Plan.pdf",
                                ["description"] = "Civil",
                            },
                            ["relationships"] = new JsonObject
                            {
                                ["tip"] = new JsonObject
                                {
                                    ["data"] = new JsonObject
                                    {
                                        ["id"] = ChangedVersion
                                            ? "urn:version?version=2"
                                            : "urn:version?version=1",
                                    },
                                },
                            },
                        },
                    }
                );
            }
            if (path.Contains("/versions/"))
                return Json(
                    new JsonObject
                    {
                        ["data"] = new JsonObject
                        {
                            ["id"] = ChangedVersion
                                ? "urn:version?version=2"
                                : "urn:version?version=1",
                            ["attributes"] = new JsonObject
                            {
                                ["displayName"] = "Plan.pdf",
                                ["storageSize"] = Bytes.Length,
                            },
                            ["relationships"] = new JsonObject
                            {
                                ["storage"] = new JsonObject
                                {
                                    ["data"] = new JsonObject
                                    {
                                        ["id"] =
                                            "urn:adsk.objects:os.object:bucket/fixture-original",
                                    },
                                },
                            },
                        },
                    }
                );
            if (path.EndsWith("/signeds3download"))
                return Json(
                    new JsonObject
                    {
                        ["status"] = "complete",
                        ["url"] = BadStorage
                            ? "https://127.0.0.1/private?X-Amz-Signature=no"
                            : "https://transfer-test.s3.amazonaws.com/source.bin?X-Amz-Signature=fixture",
                    }
                );
            if (path.EndsWith("/contents"))
                return Json(
                    new JsonObject
                    {
                        ["data"] = new JsonArray(
                            new JsonObject
                            {
                                ["id"] = "urn:item:one",
                                ["type"] = "items",
                                ["attributes"] = new JsonObject { ["displayName"] = "Plan.pdf" },
                            }
                        ),
                        ["links"] = new JsonObject { ["next"] = null },
                    }
                );
        }
        if (path == "/api/v1/metadata-keys")
            return Json(
                new JsonArray(
                    new JsonObject { ["id"] = 1, ["name"] = "Discipline" },
                    new JsonObject { ["id"] = 2, ["name"] = "Source path" }
                )
            );
        if (path == "/api/v1/groups")
            return Json(new JsonArray(new JsonObject { ["id"] = 7, ["name"] = "Civil drawings" }));
        if (path == "/api/v2/files/exist")
        {
            var p = await request.Content!.ReadFromJsonAsync<JsonObject>(ct);
            return Json(
                new JsonObject
                {
                    ["items"] = Duplicate ? p!["hashes"]!.DeepClone() : new JsonArray(),
                }
            );
        }
        if (path == "/api/v2/upload")
        {
            Uploads++;
            if (DuringUpload != null)
                await DuringUpload();
            Assert.Equal("?async=false", u.Query);
            var form = Assert.IsType<MultipartFormDataContent>(request.Content);
            var file = form.Single(p => p.Headers.ContentDisposition!.Name!.Trim('"') == "file");
            Assert.Equal(Bytes, await file.ReadAsByteArrayAsync(ct));
            var data = form.Single(p => p.Headers.ContentDisposition!.Name!.Trim('"') == "data");
            Payload = JsonNode.Parse(await data.ReadAsStringAsync(ct))!.AsObject();
            Assert.False(Payload.B("noFile"));
            Assert.Equal(64, Payload["artefactHash"].S("sha256").Length);
            if (LostUploadResponse)
                throw new HttpRequestException("fixture upload result lost");
            return Json(new JsonObject { ["artefact_id"] = 777, ["revision_action"] = "created" });
        }
        if (path == "/api/v1/artefact-groups")
        {
            Assignments++;
            var p = await request.Content!.ReadFromJsonAsync<JsonObject>(ct);
            if (!FailGroups)
                Groups = p!["groupIds"]!.DeepClone().AsArray();
            return Json(new JsonObject { ["success"] = !FailGroups, ["errors"] = new JsonArray() });
        }
        if (path == "/api/v1/artefacts/777")
            return Json(
                new JsonObject
                {
                    ["id"] = 777,
                    ["groups"] = new JsonArray(
                        Groups
                            .Select(g => (JsonNode)new JsonObject { ["id"] = g!.DeepClone() })
                            .ToArray()
                    ),
                    ["metadata"] = new JsonArray(
                        (Payload?["metadata"] as JsonArray ?? new())
                            .SelectMany(m =>
                                m!["value"]!
                                    .AsArray()
                                    .Select(v =>
                                        (JsonNode)
                                            new JsonObject
                                            {
                                                ["key_name"] = m.S("name"),
                                                ["value"] = v!.DeepClone(),
                                            }
                                    )
                            )
                            .ToArray()
                    ),
                }
            );
        if (path == "/api/v1/artefacts/777/download")
            return Json(
                new JsonObject
                {
                    ["id"] = 777,
                    ["url"] =
                        "https://transfer-test.s3.amazonaws.com/destination.bin?X-Amz-Signature=fixture",
                }
            );
        throw new InvalidOperationException(
            "Unexpected transfer fixture request "
                + request.Method
                + " "
                + u.GetLeftPart(UriPartial.Path)
        );
    }
}

public sealed class TransferScenario : IAsyncDisposable
{
    public const string Tenant = "11111111-1111-1111-1111-111111111111";
    public const string Root = "/api/projects/uat-project/transfers";
    public readonly Factory Factory = new();
    public readonly TransferTransport Vendor = new();
    public WebApplicationFactory<Program> Host;
    public HttpClient Client;

    public TransferScenario(bool enabled = true)
    {
        Host = Factory.WithWebHostBuilder(b =>
        {
            b.ConfigureAppConfiguration(
                (_, c) =>
                    c.AddInMemoryCollection(
                        new Dictionary<string, string?>
                        {
                            ["Orbit:EnableFileTransfers"] = enabled.ToString(),
                        }
                    )
            );
            b.ConfigureServices(s =>
            {
                s.AddHttpClient("vendor").ConfigurePrimaryHttpMessageHandler(() => Vendor);
                s.AddHttpClient("transfer").ConfigurePrimaryHttpMessageHandler(() => Vendor);
            });
        });
        Client = Host.CreateClient(
            new() { BaseAddress = new("https://localhost"), AllowAutoRedirect = false }
        );
        Client.DefaultRequestHeaders.Add("Test-Object", "33333333-3333-3333-3333-333333333333");
    }

    public async Task Db(Func<OrbitDb, Task> work)
    {
        using var scope = Host.Services.CreateScope();
        await work(scope.ServiceProvider.GetRequiredService<OrbitDb>());
    }

    public async Task Initialise()
    {
        await Client.GetAsync("/api/workspace");
        var session = await Client.GetFromJsonAsync<JsonObject>("/api/session");
        Client.DefaultRequestHeaders.Add("X-ORBIT-CSRF", session!.S("csrf_token"));
        using var scope = Host.Services.CreateScope();
        var db = scope.ServiceProvider.GetRequiredService<OrbitDb>();
        var cipher = scope.ServiceProvider.GetRequiredService<Cipher>();
        foreach (var id in new[] { "source", "target" })
        {
            var c = new JsonObject
            {
                ["base_url"] = id == "source" ? AutodeskOAuth.Api : "https://api.redeyedms.com",
                ["vendor_settings_confirmed"] = true,
                ["approved_test_access"] = true,
                ["evidence_note"] = "Simulated transfer test",
                ["auth_header"] = "Authorization",
                ["auth_prefix"] = "Bearer",
                ["vendor_project"] = "b.project",
                ["folder"] = "urn:folder:root",
            };
            var r = db.Add(
                Tenant,
                "uat-project",
                "connection",
                id,
                new()
                {
                    ["kind"] = "read",
                    ["provider"] = id == "source" ? "forma" : "redeye",
                    ["name"] = id == "source" ? "Autodesk test" : "RedEye test",
                    ["configuration"] = c,
                }
            );
            r.Secret = cipher.Protect(id == "source" ? "aps-fixture-token" : "redeye-fixture-key");
        }
        db.Add(
            Tenant,
            "uat-project",
            "transfer-sample",
            "sample",
            new()
            {
                ["source_id"] = "source",
                ["generation"] = 1,
                ["expires"] = DateTimeOffset.UtcNow.AddMinutes(30).ToUnixTimeSeconds(),
                ["records"] = new JsonArray(
                    new JsonObject
                    {
                        ["id"] = "urn:item:one",
                        ["label"] = "Plan.pdf",
                        ["fields"] = new JsonObject { ["orbit.relative_path"] = "Civil/Plan.pdf" },
                    }
                ),
            }
        );
        await db.SaveChangesAsync();
    }

    public JsonObject Body(string structure = "flat") =>
        new()
        {
            ["source_id"] = "source",
            ["target_id"] = "target",
            ["sample_id"] = "sample",
            ["file_ids"] = new JsonArray("urn:item:one"),
            ["rules_confirmed"] = true,
            ["quality_mode"] = "validate",
            ["structure"] = structure,
            ["path_key"] = "Source path",
            ["group_map"] = new JsonObject { ["Civil"] = 7 },
            ["metadata"] = new JsonObject { ["Discipline"] = "Civil" },
        };

    public async Task<JsonObject> Ok(HttpResponseMessage r)
    {
        var txt = await r.Content.ReadAsStringAsync();
        Assert.True(r.IsSuccessStatusCode, txt);
        return JsonNode.Parse(txt)!.AsObject();
    }

    public async Task<JsonObject> Preview(JsonObject? body = null) =>
        await Ok(await Client.PostAsJsonAsync(Root + "/preview", body ?? Body()));

    public Task<HttpResponseMessage> Send(
        JsonObject run,
        bool recheck = false,
        bool confirmed = true
    )
    {
        var item = run["items"]![0]!;
        return Client.PostAsJsonAsync(
            Root
                + "/"
                + run.S("id")
                + "/items/"
                + item.S("id")
                + (recheck ? "/recheck" : "/execute"),
            new
            {
                confirmed,
                preview_digest = item.S("preview_digest"),
                artefact_id = 777,
            }
        );
    }

    public async ValueTask DisposeAsync()
    {
        Client.Dispose();
        await Host.DisposeAsync();
        await Factory.DisposeAsync();
    }
}

public sealed class TransferTests
{
    [Theory]
    [InlineData("flat")]
    [InlineData("path_metadata")]
    [InlineData("group_map")]
    public async Task Copies_file_once_and_verifies_bytes_metadata_and_groups(string structure)
    {
        await using var x = new TransferScenario();
        await x.Initialise();
        var run = await x.Preview(x.Body(structure));
        Assert.Equal(0, x.Vendor.Uploads);
        Assert.Null(run["items"]![0]!["source"]);
        var item = await x.Ok(await x.Send(run));
        Assert.Equal("completed", item.S("status"));
        Assert.Equal(1, x.Vendor.Uploads);
        Assert.Equal(777, item.N("artefact_id"));
        Assert.Equal(64, item.S("sha256").Length);
        if (structure == "group_map")
            Assert.Equal(1, x.Vendor.Assignments);
        if (structure == "path_metadata")
            Assert.Contains(x.Vendor.Payload!["metadata"]!.AsArray(), m =>
                m.S("name") == "Source path" && m!["value"]![0]!.ToString() == "Civil/Plan.pdf"
            );
        var repeated = await x.Ok(await x.Send(run));
        Assert.Equal("completed", repeated.S("status"));
        Assert.Equal(1, x.Vendor.Uploads);
        var other = await x.Preview();
        var duplicate = await x.Ok(await x.Send(other));
        Assert.Equal("skipped", duplicate.S("status"));
        Assert.Equal(1, x.Vendor.Uploads);
    }

    [Fact]
    public async Task Lost_upload_response_is_reconciled_without_a_second_upload_or_overwriting_its_receipt()
    {
        await using var x = new TransferScenario();
        await x.Initialise();
        var first = await x.Preview();
        var second = await x.Preview();
        x.Vendor.LostUploadResponse = true;
        Assert.Equal("uncertain", (await x.Ok(await x.Send(first))).S("status"));
        Assert.Equal(HttpStatusCode.Conflict, (await x.Send(first)).StatusCode);
        Assert.Equal("failed", (await x.Ok(await x.Send(second))).S("status"));
        await x.Db(async db =>
            Assert.Equal(
                "uncertain",
                Assert
                    .Single(
                        await db.List(TransferScenario.Tenant, "uat-project", "transfer-receipt")
                    )
                    .Data()
                    .S("status")
            )
        );
        Assert.Equal("completed", (await x.Ok(await x.Send(first, recheck: true))).S("status"));
        Assert.Equal(1, x.Vendor.Uploads);
    }

    [Fact]
    public async Task Group_failure_resumes_only_groups_and_readback()
    {
        await using var x = new TransferScenario();
        await x.Initialise();
        var run = await x.Preview(x.Body("group_map"));
        x.Vendor.FailGroups = true;
        Assert.Equal("uploaded_needs_review", (await x.Ok(await x.Send(run))).S("status"));
        x.Vendor.FailGroups = false;
        Assert.Equal("completed", (await x.Ok(await x.Send(run, recheck: true))).S("status"));
        Assert.Equal(1, x.Vendor.Uploads);
        Assert.Equal(2, x.Vendor.Assignments);
    }

    [Fact]
    public async Task Invalid_source_and_disabled_execution_send_no_upload()
    {
        await using var x = new TransferScenario(false);
        await x.Initialise();
        var run = await x.Preview();
        Assert.Equal(HttpStatusCode.Conflict, (await x.Send(run)).StatusCode);
        Assert.Equal(0, x.Vendor.Uploads);
    }

    [Theory]
    [InlineData("version")]
    [InlineData("url")]
    [InlineData("connection")]
    [InlineData("confirmation")]
    [InlineData("digest")]
    public async Task Stale_or_unconfirmed_preparation_never_uploads(string change)
    {
        await using var x = new TransferScenario();
        await x.Initialise();
        var run = await x.Preview();
        if (change == "version")
            x.Vendor.ChangedVersion = true;
        if (change == "url")
            x.Vendor.BadStorage = true;
        if (change == "connection")
            x.Vendor.DuringDownload = () =>
                x.Db(async db =>
                {
                    var r = (
                        await db.Find(
                            TransferScenario.Tenant,
                            "uat-project",
                            "connection",
                            "target"
                        )
                    )!;
                    db.Change(r, r.Data());
                    await db.SaveChangesAsync();
                });
        if (change == "digest")
            run["items"]![0]!["preview_digest"] = "changed";
        var response = await x.Send(run, confirmed: change != "confirmation");
        if (response.IsSuccessStatusCode)
            Assert.Equal("failed", (await x.Ok(response)).S("status"));
        else
            Assert.Contains(
                response.StatusCode,
                new[] { HttpStatusCode.Conflict, HttpStatusCode.UnprocessableEntity }
            );
        Assert.Equal(0, x.Vendor.Uploads);
    }

    [Fact]
    public async Task Duplicate_hash_in_destination_skips_upload_and_bad_readback_never_marks_success()
    {
        await using var x = new TransferScenario();
        await x.Initialise();
        var run = await x.Preview();
        x.Vendor.Duplicate = true;
        Assert.Equal("skipped", (await x.Ok(await x.Send(run))).S("status"));
        Assert.Equal(0, x.Vendor.Uploads);
        var fresh = await x.Preview();
        x.Vendor.Duplicate = false;
        x.Vendor.BadReadback = true;
        Assert.Equal("uploaded_needs_review", (await x.Ok(await x.Send(fresh))).S("status"));
        Assert.Equal(1, x.Vendor.Uploads);
        Assert.Equal(
            "uploaded_needs_review",
            (await x.Ok(await x.Send(fresh, recheck: true))).S("status")
        );
        Assert.Equal(1, x.Vendor.Uploads);
    }

    [Fact]
    public async Task Validation_blocks_missing_required_values_but_explicit_skip_can_copy()
    {
        await using var x = new TransferScenario();
        await x.Initialise();
        await x.Db(async db =>
        {
            var a = (
                await db.Find(TransferScenario.Tenant, "uat-project", "connection", "source")
            )!;
            db.Add(
                TransferScenario.Tenant,
                "uat-project",
                "mapping",
                "map",
                new()
                {
                    ["source"] = new JsonObject
                    {
                        ["id"] = "source",
                        ["scope"] = a.Data()["configuration"]!.DeepClone(),
                    },
                    ["target"] = new JsonObject { ["id"] = "target" },
                    ["rules"] = new JsonArray(
                        new JsonObject
                        {
                            ["source_field"] = "missing",
                            ["target_field"] = "metadata.Required",
                            ["required"] = true,
                            ["transform"] = "copy",
                        }
                    ),
                }
            );
            await db.SaveChangesAsync();
        });
        var body = x.Body();
        body["mapping_id"] = "map";
        var blocked = await x.Preview(body);
        Assert.Equal("blocked", blocked["items"]![0].S("status"));
        Assert.Equal(HttpStatusCode.Conflict, (await x.Send(blocked)).StatusCode);
        body["quality_mode"] = "skip";
        var skip = await x.Preview(body);
        Assert.Equal("completed", (await x.Ok(await x.Send(skip))).S("status"));
    }

    [Fact]
    public async Task Source_loading_is_bounded_to_saved_scope_and_history_contains_no_signed_links_or_secrets()
    {
        await using var x = new TransferScenario();
        await x.Initialise();
        var sample = await x.Ok(
            await x.Client.PostAsJsonAsync(TransferScenario.Root + "/sources/source", new { })
        );
        Assert.Single(sample["files"]!.AsArray());
        var run = await x.Preview();
        await x.Ok(await x.Send(run));
        var history = await x.Client.GetStringAsync(TransferScenario.Root);
        Assert.DoesNotContain("X-Amz-Signature", history);
        Assert.DoesNotContain("aps-fixture-token", history);
        Assert.DoesNotContain("redeye-fixture-key", history);
    }

    [Theory]
    [InlineData("http://bucket.s3.amazonaws.com/file?X-Amz-Signature=x")]
    [InlineData("https://localhost/file?X-Amz-Signature=x")]
    [InlineData("https://bucket.s3.amazonaws.com.attacker.test/file?X-Amz-Signature=x")]
    [InlineData("https://user:password@bucket.s3.amazonaws.com/file?X-Amz-Signature=x")]
    public void Signed_storage_gate_rejects_unapproved_urls(string url) =>
        Assert.Throws<ApiException>(() => TransferVendor.StorageUrl(url));

    async Task<HttpClient> User(TransferScenario x, string role)
    {
        const string user = "44444444-4444-4444-4444-444444444444";
        await x.Db(async db =>
        {
            db.Add(
                TransferScenario.Tenant,
                "",
                "member",
                user,
                new() { ["role"] = role, ["projects"] = new JsonArray("uat-project") }
            );
            await db.SaveChangesAsync();
        });
        var c = x.Host.CreateClient(
            new() { BaseAddress = new("https://localhost"), AllowAutoRedirect = false }
        );
        c.DefaultRequestHeaders.Add("Test-Object", user);
        await c.GetAsync("/api/workspace");
        var session = await c.GetFromJsonAsync<JsonObject>("/api/session");
        c.DefaultRequestHeaders.Add("X-ORBIT-CSRF", session!.S("csrf_token"));
        return c;
    }

    [Fact]
    public async Task Viewer_project_and_csrf_boundaries_reject_unsafe_requests()
    {
        await using var x = new TransferScenario();
        await x.Initialise();
        var run = await x.Preview();
        using var viewer = await User(x, "viewer");
        Assert.Equal(HttpStatusCode.OK, (await viewer.GetAsync(TransferScenario.Root)).StatusCode);
        Assert.Equal(
            HttpStatusCode.Forbidden,
            (await viewer.PostAsJsonAsync(TransferScenario.Root + "/preview", x.Body())).StatusCode
        );
        var item = run["items"]![0]!;
        Assert.Equal(
            HttpStatusCode.Forbidden,
            (
                await viewer.PostAsJsonAsync(
                    TransferScenario.Root
                        + "/"
                        + run.S("id")
                        + "/items/"
                        + item.S("id")
                        + "/execute",
                    new { confirmed = true, preview_digest = item.S("preview_digest") }
                )
            ).StatusCode
        );
        Assert.Equal(
            HttpStatusCode.NotFound,
            (await x.Client.GetAsync("/api/projects/missing-project/transfers")).StatusCode
        );
        x.Client.DefaultRequestHeaders.Remove("X-ORBIT-CSRF");
        Assert.Equal(HttpStatusCode.BadRequest, (await x.Send(run)).StatusCode);
        Assert.Equal(0, x.Vendor.Uploads);
    }

    [Fact]
    public async Task Role_revoked_after_upload_stops_group_assignment_and_retains_recheckable_result()
    {
        await using var x = new TransferScenario();
        await x.Initialise();
        var run = await x.Preview(x.Body("group_map"));
        using var owner = await User(x, "owner");
        x.Vendor.DuringUpload = () =>
            x.Db(async db =>
            {
                var r = (
                    await db.Find(
                        TransferScenario.Tenant,
                        "",
                        "member",
                        "44444444-4444-4444-4444-444444444444"
                    )
                )!;
                var d = r.Data();
                d["role"] = "viewer";
                db.Change(r, d);
                await db.SaveChangesAsync();
            });
        var item = run["items"]![0]!;
        var result = await x.Ok(
            await owner.PostAsJsonAsync(
                TransferScenario.Root + "/" + run.S("id") + "/items/" + item.S("id") + "/execute",
                new { confirmed = true, preview_digest = item.S("preview_digest") }
            )
        );
        Assert.Equal("uploaded_needs_review", result.S("status"));
        Assert.Equal(1, x.Vendor.Uploads);
        Assert.Equal(0, x.Vendor.Assignments);
        // An authorised owner can reconcile the completed upload without its source preview remaining fresh.
        await x.Db(async db =>
        {
            var r = (
                await db.Find(TransferScenario.Tenant, "uat-project", "transfer", run.S("id"))
            )!;
            var d = r.Data();
            d["expires"] = 1;
            db.Change(r, d);
            await db.SaveChangesAsync();
        });
        Assert.Equal("completed", (await x.Ok(await x.Send(run, recheck: true))).S("status"));
        Assert.Equal(1, x.Vendor.Uploads);
    }

    [Fact]
    public async Task Concurrent_execution_of_one_item_sends_one_upload()
    {
        await using var x = new TransferScenario();
        await x.Initialise();
        var run = await x.Preview();
        var entered = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        var release = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
        x.Vendor.DuringDownload = async () =>
        {
            entered.SetResult();
            await release.Task;
        };
        var first = x.Send(run);
        await entered.Task.WaitAsync(TimeSpan.FromSeconds(10));
        Assert.Equal(HttpStatusCode.Conflict, (await x.Send(run)).StatusCode);
        release.SetResult();
        Assert.Equal("completed", (await x.Ok(await first)).S("status"));
        Assert.Equal(1, x.Vendor.Uploads);
    }

    [Fact]
    public async Task Destination_hash_mismatch_stops_group_mutation_and_never_reuploads()
    {
        await using var x = new TransferScenario();
        await x.Initialise();
        var run = await x.Preview(x.Body("group_map"));
        x.Vendor.BadReadback = true;
        Assert.Equal("uploaded_needs_review", (await x.Ok(await x.Send(run))).S("status"));
        Assert.Equal(0, x.Vendor.Assignments);
        Assert.Equal(HttpStatusCode.Conflict, (await x.Send(run)).StatusCode);
        Assert.Equal(1, x.Vendor.Uploads);
    }

    [Theory]
    [InlineData("https://bucket.s3.us-east-1.amazonaws.com/file?X-Amz-Signature=fixture")]
    [InlineData("https://account123.blob.core.windows.net/container/file?sig=fixture")]
    [InlineData("https://bucket.storage.googleapis.com/file?X-Goog-Signature=fixture")]
    public void Supported_signed_cloud_storage_contracts_are_accepted(string value) =>
        Assert.Equal(value, TransferVendor.StorageUrl(value).AbsoluteUri);

    [Fact]
    public async Task Oversized_download_does_not_upload_and_reservation_is_durable_before_upload()
    {
        await using var x = new TransferScenario();
        await x.Initialise();
        var run = await x.Preview();
        x.Vendor.OversizedSource = true;
        Assert.Equal("failed", (await x.Ok(await x.Send(run))).S("status"));
        Assert.Equal(0, x.Vendor.Uploads);
        x.Vendor.OversizedSource = false;
        x.Vendor.DuringUpload = () =>
            x.Db(async db =>
            {
                Assert.Equal(
                    "reserved",
                    Assert
                        .Single(
                            await db.List(
                                TransferScenario.Tenant,
                                "uat-project",
                                "transfer-receipt"
                            )
                        )
                        .Data()
                        .S("status")
                );
                Assert.Equal(
                    "in_progress",
                    (
                        await db.Find(
                            TransferScenario.Tenant,
                            "uat-project",
                            "transfer",
                            run.S("id")
                        )
                    )!.Data()["items"]!
                        [0]
                        .S("status")
                );
            });
        Assert.Equal("completed", (await x.Ok(await x.Send(run))).S("status"));
        Assert.Equal(1, x.Vendor.Uploads);
    }
}
