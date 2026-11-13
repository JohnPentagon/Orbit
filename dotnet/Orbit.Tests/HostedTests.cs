using System.Net;
using System.Net.Http.Json;
using System.Security.Claims;
using System.Text.Encodings.Web;
using System.Text.Json.Nodes;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Logging;
using Microsoft.Extensions.Options;
using Orbit.Api;
using Xunit;

namespace Orbit.Tests;

public sealed class AuthHandler(
    IOptionsMonitor<AuthenticationSchemeOptions> options,
    ILoggerFactory logger,
    UrlEncoder encoder
) : AuthenticationHandler<AuthenticationSchemeOptions>(options, logger, encoder)
{
    protected override Task<AuthenticateResult> HandleAuthenticateAsync()
    {
        if (!Request.Headers.TryGetValue("Test-Object", out var oid))
            return Task.FromResult(AuthenticateResult.NoResult());
        var claims = new[]
        {
            new Claim("oid", oid!),
            new Claim(
                "tid",
                Request.Headers["Test-Tenant"].FirstOrDefault()
                    ?? "11111111-1111-1111-1111-111111111111"
            ),
            new Claim("name", "Fixture operator"),
            new Claim(
                AutodeskOAuth.SessionClaim,
                Request.Headers["Test-Session"].FirstOrDefault() ?? "fixture-session"
            ),
        };
        return Task.FromResult(
            AuthenticateResult.Success(
                new AuthenticationTicket(
                    new ClaimsPrincipal(new ClaimsIdentity(claims, Scheme.Name)),
                    Scheme.Name
                )
            )
        );
    }
}

public sealed class Factory : WebApplicationFactory<Program>
{
    public bool FileUat;
    public string Folder = Path.Combine(Path.GetTempPath(), "orbit-dotnet-tests-" + Guid.NewGuid());

    protected override void ConfigureWebHost(IWebHostBuilder builder)
    {
        Directory.CreateDirectory(Folder);
        builder.UseEnvironment(FileUat ? "Production" : "Development");
        builder.ConfigureAppConfiguration(
            (_, c) =>
                c.AddInMemoryCollection(
                    new Dictionary<string, string?>
                    {
                        ["Entra:TenantId"] = "11111111-1111-1111-1111-111111111111",
                        ["Entra:ClientId"] = "22222222-2222-2222-2222-222222222222",
                        ["Entra:ClientSecret"] = "fixture-only-not-a-live-secret",
                        ["Orbit:Storage"] = FileUat ? "FileUat" : null,
                        ["Orbit:DataPath"] = Path.Combine(Folder, "data"),
                        ["Orbit:AdminObjectIds"] = "33333333-3333-3333-3333-333333333333",
                        ["Orbit:EncryptionKey"] = Convert.ToBase64String(new byte[32]),
                        ["Orbit:KeyRingPath"] = Path.Combine(Folder, "keys"),
                        ["ConnectionStrings:Orbit"] = "",
                    }
                )
        );
        builder.ConfigureServices(s =>
        {
            s.AddAuthentication(o =>
                {
                    o.DefaultAuthenticateScheme = "Test";
                    o.DefaultChallengeScheme = "Test";
                })
                .AddScheme<AuthenticationSchemeOptions, AuthHandler>("Test", _ => { });
            if (!FileUat)
                s.AddDbContext<OrbitDb>(o =>
                    Microsoft.EntityFrameworkCore.SqliteDbContextOptionsBuilderExtensions.UseSqlite(
                        o,
                        "Data Source=" + Path.Combine(Folder, "test.db")
                    )
                );
        });
    }
}

public sealed class HostedTests
{
    [Fact]
    public async Task Anonymous_cannot_open_local_owner_or_read_workspace()
    {
        await using var f = new Factory();
        using var c = f.CreateClient(
            new() { BaseAddress = new("https://localhost"), AllowAutoRedirect = false }
        );
        Assert.Equal(HttpStatusCode.Unauthorized, (await c.GetAsync("/api/workspace")).StatusCode);
        Assert.Equal(
            HttpStatusCode.NotImplemented,
            (await c.GetAsync("/api/local/status")).StatusCode
        );
        var health = await c.GetFromJsonAsync<JsonObject>("/api/health");
        Assert.Equal("hosted-workspace", health!.S("mode"));
    }

    [Fact]
    public async Task Tenant_role_csrf_and_credential_storage_boundaries()
    {
        await using var f = new Factory();
        using var c = f.CreateClient(
            new() { BaseAddress = new("https://localhost"), AllowAutoRedirect = false }
        );
        c.DefaultRequestHeaders.Add("Test-Object", "33333333-3333-3333-3333-333333333333");
        var workspace = await c.GetFromJsonAsync<JsonObject>("/api/workspace");
        Assert.Equal("owner", workspace!["identity"]!.S("role"));
        var denied = await c.PostAsJsonAsync("/api/local/projects", new { name = "No CSRF" });
        Assert.Equal(HttpStatusCode.BadRequest, denied.StatusCode);
        var session = await c.GetFromJsonAsync<JsonObject>("/api/session");
        c.DefaultRequestHeaders.Add("X-ORBIT-CSRF", session!.S("csrf_token"));
        var create = await c.PostAsJsonAsync(
            "/api/projects/uat-project/read-connections",
            new
            {
                name = "UAT RedEye",
                provider = "redeye",
                base_url = "https://api.redeyedms.com",
                auth_header = "Authorization",
                auth_prefix = "Bearer",
                vendor_settings_confirmed = true,
                approved_test_access = true,
                evidence_note = "Test fixture only",
            }
        );
        Assert.Equal(HttpStatusCode.OK, create.StatusCode);
        var id = (await create.Content.ReadFromJsonAsync<JsonObject>())!.S("id");
        Assert.Equal(
            HttpStatusCode.OK,
            (
                await c.PutAsJsonAsync(
                    $"/api/projects/uat-project/read-connections/{id}/credential",
                    new { secret = "synthetic-test-key" }
                )
            ).StatusCode
        );
        var text = await c.GetStringAsync("/api/projects/uat-project/read-connections");
        Assert.DoesNotContain("synthetic-test-key", text);
        Assert.Contains("credential_present", text);
        using (var scope = f.Services.CreateScope())
        {
            var db = scope.ServiceProvider.GetRequiredService<OrbitDb>();
            var row = await db.Find(
                "11111111-1111-1111-1111-111111111111",
                "uat-project",
                "connection",
                id
            );
            Assert.NotEqual("synthetic-test-key", row!.Secret);
            db.Add(
                "11111111-1111-1111-1111-111111111111",
                "",
                "member",
                "44444444-4444-4444-4444-444444444444",
                new() { ["role"] = "viewer", ["projects"] = new JsonArray("uat-project") }
            );
            await db.SaveChangesAsync();
        }
        c.DefaultRequestHeaders.Remove("Test-Object");
        c.DefaultRequestHeaders.Add("Test-Object", "44444444-4444-4444-4444-444444444444");
        Assert.Equal(
            HttpStatusCode.OK,
            (await c.GetAsync("/api/projects/uat-project/analysis")).StatusCode
        );
        Assert.Equal(
            HttpStatusCode.Forbidden,
            (await c.GetAsync("/api/projects/uat-project/read-connections")).StatusCode
        );
        c.DefaultRequestHeaders.Add("Test-Tenant", "55555555-5555-5555-5555-555555555555");
        Assert.Equal(HttpStatusCode.Unauthorized, (await c.GetAsync("/api/workspace")).StatusCode);
    }

    [Fact]
    public void Comparison_handles_duplicates_missing_required_and_reverse()
    {
        JsonObject sample(string id, string number, string field, string value) =>
            new()
            {
                ["records"] = new JsonArray(
                    new JsonObject
                    {
                        ["id"] = id,
                        ["values"] = new JsonObject { ["number"] = number, [field] = value },
                    }
                ),
            };
        var a = sample("a", "D-001", "discipline", "Civil");
        var b = sample("b", "D-001.pdf", "properties.Discipline", "Civil");
        var config = new JsonObject
        {
            ["source_key"] = "number",
            ["target_key"] = "number",
            ["source_key_transform"] = "trim",
            ["target_key_transform"] = "filename_stem",
            ["rules"] = new JsonArray(
                new JsonObject
                {
                    ["source_field"] = "discipline",
                    ["target_field"] = "properties.Discipline",
                    ["required"] = true,
                }
            ),
        };
        Assert.Equal(1, AnalysisRoutes.Evaluate(a, b, config)["counts"]!.N("matched"));
        b["records"]![0]!["values"]!["properties.Discipline"] = "";
        Assert.Equal(1, AnalysisRoutes.Evaluate(a, b, config)["counts"]!.N("invalid"));
        a["records"]!.AsArray().Add(a["records"]![0]!.DeepClone());
        Assert.Equal(1, AnalysisRoutes.Evaluate(a, b, config)["counts"]!.N("ambiguous"));
    }

    [Fact]
    public void Cipher_round_trip_and_tamper_rejection()
    {
        var cfg = new ConfigurationBuilder()
            .AddInMemoryCollection(
                new Dictionary<string, string?>
                {
                    ["Orbit:EncryptionKey"] = Convert.ToBase64String(new byte[32]),
                }
            )
            .Build();
        var cipher = new Cipher(cfg);
        var encrypted = cipher.Protect("fixture-key");
        Assert.Equal("fixture-key", cipher.Unprotect(encrypted));
        var bytes = Convert.FromBase64String(encrypted);
        bytes[^1] ^= 1;
        Assert.ThrowsAny<System.Security.Cryptography.CryptographicException>(() =>
            cipher.Unprotect(Convert.ToBase64String(bytes))
        );
    }

    [Fact]
    public void Cookie_key_ring_is_encrypted_and_survives_restart()
    {
        var directory = Path.Combine(Path.GetTempPath(), "orbit-keyring-" + Guid.NewGuid());
        Microsoft.Extensions.DependencyInjection.ServiceProvider Services()
        {
            var services = new ServiceCollection();
            var configuration = new ConfigurationBuilder()
                .AddInMemoryCollection(
                    new Dictionary<string, string?>
                    {
                        ["Orbit:EncryptionKey"] = Convert.ToBase64String(new byte[32]),
                    }
                )
                .Build();
            services.AddSingleton<IConfiguration>(configuration);
            services.AddSingleton<Cipher>();
            services.AddLogging();
            services.AddDataProtection().PersistKeysToFileSystem(new DirectoryInfo(directory));
            services
                .AddOptions<Microsoft.AspNetCore.DataProtection.KeyManagement.KeyManagementOptions>()
                .Configure<Cipher>((o, c) => o.XmlEncryptor = new KeyEncryption(c));
            return services.BuildServiceProvider();
        }
        string token;
        using (var services = Services())
        {
            token = services
                .GetRequiredService<Microsoft.AspNetCore.DataProtection.IDataProtectionProvider>()
                .CreateProtector("fixture")
                .Protect("session-content");
        }
        using (var services = Services())
        {
            Assert.Equal(
                "session-content",
                services
                    .GetRequiredService<Microsoft.AspNetCore.DataProtection.IDataProtectionProvider>()
                    .CreateProtector("fixture")
                    .Unprotect(token)
            );
        }
        var xml = File.ReadAllText(Directory.GetFiles(directory, "key-*.xml").Single());
        Assert.Contains("orbitEncryptedKey", xml);
        Assert.DoesNotContain("<masterKey", xml);
    }

    [Fact]
    public async Task Production_file_uat_survives_restart_without_sql_or_passwordless_login()
    {
        var directory = Path.Combine(Path.GetTempPath(), "orbit-file-uat-tests-" + Guid.NewGuid());
        await using (var first = new Factory { FileUat = true, Folder = directory })
        {
            using var client = first.CreateClient(
                new() { BaseAddress = new("https://localhost"), AllowAutoRedirect = false }
            );
            Assert.Equal(
                HttpStatusCode.Unauthorized,
                (await client.GetAsync("/api/workspace")).StatusCode
            );
            client.DefaultRequestHeaders.Add("Test-Object", "33333333-3333-3333-3333-333333333333");
            await client.GetAsync("/api/workspace");
            var session = await client.GetFromJsonAsync<JsonObject>("/api/session");
            client.DefaultRequestHeaders.Add("X-ORBIT-CSRF", session!.S("csrf_token"));
            var created = await client.PostAsJsonAsync(
                "/api/local/projects",
                new { name = "Persistent UAT project" }
            );
            Assert.Equal(HttpStatusCode.OK, created.StatusCode);
            Assert.Equal(HttpStatusCode.OK, (await client.GetAsync("/api/readiness")).StatusCode);
            Assert.True(File.Exists(Path.Combine(directory, "data", "orbit-uat.db")));
            using (var scope = first.Services.CreateScope())
            {
                var db = scope.ServiceProvider.GetRequiredService<OrbitDb>();
                var row = db.Add(
                    "11111111-1111-1111-1111-111111111111",
                    "uat-project",
                    "connection",
                    "restart-check",
                    new()
                    {
                        ["name"] = "Persistent connection",
                        ["provider"] = "redeye",
                        ["kind"] = "read",
                    }
                );
                row.Secret = scope
                    .ServiceProvider.GetRequiredService<Cipher>()
                    .Protect("synthetic-restart-key");
                await db.SaveChangesAsync();
            }
        }
        await using (var restarted = new Factory { FileUat = true, Folder = directory })
        {
            using var client = restarted.CreateClient(
                new() { BaseAddress = new("https://localhost"), AllowAutoRedirect = false }
            );
            client.DefaultRequestHeaders.Add("Test-Object", "33333333-3333-3333-3333-333333333333");
            var workspace = await client.GetFromJsonAsync<JsonObject>("/api/workspace");
            Assert.Contains(workspace!["projects"]!.AsArray(), p =>
                p.S("name") == "Persistent UAT project"
            );
            using (var scope = restarted.Services.CreateScope())
            {
                var db = scope.ServiceProvider.GetRequiredService<OrbitDb>();
                var row = await db.Find(
                    "11111111-1111-1111-1111-111111111111",
                    "uat-project",
                    "connection",
                    "restart-check"
                );
                Assert.Equal(
                    "synthetic-restart-key",
                    scope.ServiceProvider.GetRequiredService<Cipher>().Unprotect(row!.Secret!)
                );
            }
            Assert.Equal(
                HttpStatusCode.NotImplemented,
                (await client.GetAsync("/api/local/status")).StatusCode
            );
        }
    }

    [Fact]
    public void File_uat_refuses_a_second_process_lease()
    {
        var directory = Path.Combine(Path.GetTempPath(), "orbit-lease-test-" + Guid.NewGuid());
        var config = new ConfigurationBuilder()
            .AddInMemoryCollection(
                new Dictionary<string, string?> { ["Orbit:DataPath"] = directory }
            )
            .Build();
        using (var storage = new UatStorage(config))
            Assert.Throws<InvalidOperationException>(() => new UatStorage(config));
        using var restarted = new UatStorage(config);
    }
}
