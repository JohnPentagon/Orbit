using System.Text.Json.Nodes;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authentication.OpenIdConnect;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.DataProtection.KeyManagement;
using Microsoft.EntityFrameworkCore;
using Orbit.Api;

var builder = WebApplication.CreateBuilder(args);
if (args.Contains("--schema"))
{
    using var schemaDb = new OrbitDb(
        new DbContextOptionsBuilder<OrbitDb>()
            .UseSqlServer(
                "Server=localhost;Database=OrbitSchemaOnly;Integrated Security=true;TrustServerCertificate=false"
            )
            .Options
    );
    Console.Write(schemaDb.Database.GenerateCreateScript());
    return;
}
builder.WebHost.ConfigureKestrel(o => o.Limits.MaxRequestBodySize = 1_000_000);
builder.Services.Configure<Microsoft.AspNetCore.Builder.IISServerOptions>(o =>
    o.MaxRequestBodySize = 1_000_000
);
builder.Logging.AddFilter("Microsoft.AspNetCore.Authentication", LogLevel.Warning);

// OAuth callback codes must not appear in ASP.NET request-start/finish logs.
builder.Logging.AddFilter("Microsoft.AspNetCore.Hosting.Diagnostics", LogLevel.Warning);
builder.Services.AddSingleton<UatStorage>();
builder.Services.AddSingleton<Cipher>();
builder.Services.AddDataProtection().SetApplicationName("ORBIT.NET10");
builder
    .Services.AddOptions<KeyManagementOptions>()
    .Configure<Cipher, IConfiguration, IHostEnvironment, ILoggerFactory>(
        (o, c, cfg, environment, logger) =>
        {
            var path = cfg["Orbit:KeyRingPath"]
                ?? Path.Combine(environment.ContentRootPath, ".data", "keys");
            o.XmlRepository =
                new Microsoft.AspNetCore.DataProtection.Repositories.FileSystemXmlRepository(
                    new DirectoryInfo(path),
                    logger
                );
            o.XmlEncryptor = new KeyEncryption(c);
        }
    );
builder.Services.AddDbContext<OrbitDb>(
    (services, o) =>
    {
        var config = services.GetRequiredService<IConfiguration>();
        var sql = config.GetConnectionString("Orbit");
        var fileStorage = string.Equals(
            config["Orbit:Storage"],
            UatStorage.Mode,
            StringComparison.OrdinalIgnoreCase
        );
        if (fileStorage && !string.IsNullOrWhiteSpace(sql))
            throw new InvalidOperationException("Choose FileUat or a SQL connection, not both.");
        if (fileStorage)
            o.UseSqlite(services.GetRequiredService<UatStorage>().ConnectionString);
        else if (!string.IsNullOrWhiteSpace(sql))
            o.UseSqlServer(sql);
        else if (builder.Environment.IsDevelopment())
            o.UseSqlite(
                "Data Source="
                    + Path.Combine(builder.Environment.ContentRootPath, ".data", "orbit-net.db")
            );
        else
            throw new InvalidOperationException(
                "Choose FileUat with a persistent data path, or configure an application SQL connection."
            );
    }
);
builder
    .Services.AddAuthentication(o =>
    {
        o.DefaultScheme = CookieAuthenticationDefaults.AuthenticationScheme;
        o.DefaultChallengeScheme = OpenIdConnectDefaults.AuthenticationScheme;
    })
    .AddCookie(o =>
    {
        o.Cookie.Name = "__Host-orbit";
        o.Cookie.HttpOnly = true;
        o.Cookie.SecurePolicy = CookieSecurePolicy.Always;
        o.Cookie.SameSite = SameSiteMode.Lax;
        o.ExpireTimeSpan = TimeSpan.FromHours(8);
        o.SlidingExpiration = true;
        o.Events.OnSigningIn = ctx =>
        {
            AutodeskOAuth.UpgradeSession(ctx.Principal);
            return Task.CompletedTask;
        };
        o.Events.OnValidatePrincipal = ctx =>
        {
            if (ctx.Principal?.HasClaim(c => c.Type == AutodeskOAuth.SessionClaim) != true)
            {
                AutodeskOAuth.UpgradeSession(ctx.Principal);
                ctx.ShouldRenew = true;
            }
            return Task.CompletedTask;
        };
        o.Events.OnRedirectToLogin = ctx =>
        {
            ctx.Response.StatusCode = 401;
            return Task.CompletedTask;
        };
    })
    .AddOpenIdConnect(o =>
    {
        o.Authority =
            "https://login.microsoftonline.com/"
            + builder.Configuration["Entra:TenantId"]
            + "/v2.0";
        o.ClientId = builder.Configuration["Entra:ClientId"] ?? "not-configured";
        o.ClientSecret = builder.Configuration["Entra:ClientSecret"];
        o.ResponseType = "code";
        o.UsePkce = true;
        o.MapInboundClaims = false;
        o.SaveTokens = false;
        o.Scope.Clear();
        o.Scope.Add("openid");
        o.Scope.Add("profile");
        o.TokenValidationParameters.ValidateIssuer = true;
        o.Events.OnRemoteFailure = ctx =>
        {
            ctx.HandleResponse();
            ctx.Response.Redirect("/?signin=failed");
            return Task.CompletedTask;
        };
    });
builder.Services.AddAuthorization();
builder.Services.AddAntiforgery(o =>
{
    o.HeaderName = "X-ORBIT-CSRF";
    o.Cookie.Name = "__Host-orbit-csrf";
    o.Cookie.SecurePolicy = CookieSecurePolicy.Always;
});
builder
    .Services.AddHttpClient("vendor", c =>
    {
        c.Timeout = TimeSpan.FromSeconds(25);
        c.DefaultRequestHeaders.UserAgent.ParseAdd("ORBIT/0.16.0");
    })
    .ConfigurePrimaryHttpMessageHandler(() => new HttpClientHandler { AllowAutoRedirect = false });
builder.Services.AddScoped<ConnectorService>();
builder.Services.AddScoped<AutodeskOAuth>();
var app = builder.Build();
var fileUat = string.Equals(
    app.Configuration["Orbit:Storage"],
    UatStorage.Mode,
    StringComparison.OrdinalIgnoreCase
);
if (!app.Environment.IsDevelopment())
{
    foreach (
        var key in new[]
        {
            "Entra:TenantId",
            "Entra:ClientId",
            "Entra:ClientSecret",
            "Orbit:AdminObjectIds",
            "Orbit:EncryptionKey",
            "Orbit:KeyRingPath",
        }
    )
        if (string.IsNullOrWhiteSpace(app.Configuration[key]))
            throw new InvalidOperationException($"Required hosted configuration is missing: {key}");
}

app.Services.GetRequiredService<Cipher>();
if (!app.Environment.IsDevelopment())
{
    app.UseHsts();
    app.UseHttpsRedirection();
}
app.Use(
    async (ctx, next) =>
    {
        ctx.Response.Headers["X-Content-Type-Options"] = "nosniff";
        ctx.Response.Headers["Referrer-Policy"] = "same-origin";
        if (ctx.Request.Path.StartsWithSegments("/api"))
            ctx.Response.Headers.CacheControl = "no-store";
        try
        {
            await next();
        }
        catch (ApiException e)
        {
            ctx.Response.StatusCode = e.Status;
            await ctx.Response.WriteAsJsonAsync(new { detail = e.Message });
        }
        catch (DbUpdateConcurrencyException)
        {
            ctx.Response.StatusCode = 409;
            await ctx.Response.WriteAsJsonAsync(
                new { detail = "This item changed. Reload before retrying." }
            );
        }
        catch (DbUpdateException)
        {
            ctx.Response.StatusCode = 409;
            await ctx.Response.WriteAsJsonAsync(
                new
                {
                    detail = "A concurrent operation changed this item. Reload and inspect its status before retrying.",
                }
            );
        }
        catch (Exception e) when (e is HttpRequestException or TaskCanceledException)
        {
            ctx.Response.StatusCode = 502;
            await ctx.Response.WriteAsJsonAsync(
                new
                {
                    detail = "The vendor could not be reached. Check the connection and retry the read.",
                }
            );
        }
    }
);
app.UseAuthentication();
app.UseAuthorization();
app.Use(
    async (ctx, next) =>
    {
        if (
            ctx.Request.Path.StartsWithSegments("/api") && HttpMethods.IsPost(ctx.Request.Method)
            || ctx.Request.Path.StartsWithSegments("/api")
                && (
                    HttpMethods.IsPut(ctx.Request.Method)
                    || HttpMethods.IsDelete(ctx.Request.Method)
                )
        )
        {
            try
            {
                await ctx
                    .RequestServices.GetRequiredService<Microsoft.AspNetCore.Antiforgery.IAntiforgery>()
                    .ValidateRequestAsync(ctx);
            }
            catch (Microsoft.AspNetCore.Antiforgery.AntiforgeryValidationException)
            {
                ctx.Response.StatusCode = 400;
                await ctx.Response.WriteAsJsonAsync(
                    new { detail = "Refresh the page before saving again." }
                );
                return;
            }
        }
        await next();
    }
);
app.MapGet("/api/health", () => new
    {
        status = "ok",
        mode = "hosted-workspace",
        version = "0.16.0",
        runtime = "ASP.NET Core 10",
    });
app.MapGet("/api/readiness", async (OrbitDb db) =>
{
    try
    {
        await db.Records.AnyAsync();
        return Results.Ok(new { status = "ready" });
    }
    catch
    {
        return Results.Json(new { status = "not_ready" }, statusCode: 503);
    }
});
app.MapGet("/auth/login", () =>
    Results.Challenge(
        new AuthenticationProperties { RedirectUri = "/" },
        [OpenIdConnectDefaults.AuthenticationScheme]
    )
);
app.MapGet(
    "/api/session",
    async (
        HttpContext ctx,
        OrbitDb db,
        IConfiguration cfg,
        Microsoft.AspNetCore.Antiforgery.IAntiforgery csrf
    ) =>
    {
        if (ctx.User.Identity?.IsAuthenticated != true)
            return Results.Json(new { authenticated = false });
        var who = await Actor.Resolve(ctx, db, cfg);
        return Results.Json(
            new
            {
                authenticated = true,
                csrf_token = csrf.GetAndStoreTokens(ctx).RequestToken,
                identity = new
                {
                    user_id = who.Id,
                    tenant_id = who.Tenant,
                    role = who.Role,
                },
            }
        );
    }
);
app.MapDelete("/api/session", async (HttpContext ctx) =>
{
    await ctx.SignOutAsync(CookieAuthenticationDefaults.AuthenticationScheme);
    return Results.Ok(new { signed_out = true });
});
WorkspaceRoutes.Map(app);
ConnectionRoutes.Map(app);
BsddRoutes.Map(app);
AnalysisRoutes.Map(app);
RedEyeRoutes.Map(app);
AutodeskOAuth.Map(app);
app.Map("/api/{**path}", () =>
    Results.Json(
        new
        {
            detail = "This operation has not yet been ported to the hosted .NET backend. No vendor request was sent.",
        },
        statusCode: 501
    )
);
app.UseDefaultFiles();
app.UseStaticFiles();
app.MapFallbackToFile("index.html");
if (app.Environment.IsDevelopment())
    Directory.CreateDirectory(Path.Combine(app.Environment.ContentRootPath, ".data"));
using (var scope = app.Services.CreateScope())
{
    var db = scope.ServiceProvider.GetRequiredService<OrbitDb>();
    if (fileUat)
        await app.Services.GetRequiredService<UatStorage>().Initialise(db);
    else if (
        app.Environment.IsDevelopment()
        || app.Configuration.GetValue<bool>("Orbit:InitializeDatabase")
    )
        await db.Database.EnsureCreatedAsync();
}
app.Run();

public partial class Program { }
