using System.Net.Http.Headers;
using System.Security.Claims;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using System.Text.RegularExpressions;
using Microsoft.AspNetCore.WebUtilities;
using Microsoft.EntityFrameworkCore;

namespace Orbit.Api;

/// <summary>Confidential APS OAuth and bounded document-management discovery.</summary>
public sealed class AutodeskOAuth(
    OrbitDb db,
    Cipher cipher,
    IHttpClientFactory clients,
    IConfiguration config,
    ConnectorService reader
)
{
    public const string SessionClaim = "orbit:session";
    public const string BrowserCookie = "__Host-orbit-aps";
    public const string Api = "https://developer.api.autodesk.com";
    public const string CallbackPath = "/api/autodesk/callback";
    static long Now => DateTimeOffset.UtcNow.ToUnixTimeSeconds();

    static string Hash(string value) =>
        Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(value)));

    static string Random() => WebEncoders.Base64UrlEncode(RandomNumberGenerator.GetBytes(32));

    static bool Equal(string a, string b) =>
        CryptographicOperations.FixedTimeEquals(
            Encoding.UTF8.GetBytes(a),
            Encoding.UTF8.GetBytes(b)
        );

    static string Session(HttpContext ctx) =>
        Hash(
            ctx.User.FindFirstValue(SessionClaim)
                ?? throw new ApiException(
                    409,
                    "Sign out of ORBIT and sign in again before authorising Autodesk."
                )
        );

    static CookieOptions Cookie() =>
        new()
        {
            HttpOnly = true,
            Secure = true,
            SameSite = SameSiteMode.Lax,
            Path = "/",
            MaxAge = TimeSpan.FromMinutes(10),
            IsEssential = true,
        };

    public static void UpgradeSession(ClaimsPrincipal? principal)
    {
        if (
            principal?.Identity is ClaimsIdentity identity
            && identity.IsAuthenticated
            && !identity.HasClaim(c => c.Type == SessionClaim)
        )
            identity.AddClaim(new Claim(SessionClaim, Random()));
    }

    public string Callback(HttpContext ctx)
    {
        var origin = config["Orbit:PublicOrigin"];
        if (
            string.IsNullOrWhiteSpace(origin)
            && !string.IsNullOrWhiteSpace(config["WEBSITE_HOSTNAME"])
        )
            origin = "https://" + config["WEBSITE_HOSTNAME"];
        origin = string.IsNullOrWhiteSpace(origin)
            ? ctx.Request.Scheme + "://" + ctx.Request.Host
            : origin;
        if (
            !Uri.TryCreate(origin, UriKind.Absolute, out var uri)
            || uri.Scheme != "https"
            || uri.AbsolutePath != "/"
            || uri.UserInfo.Length > 0
            || uri.Query.Length > 0
            || uri.Fragment.Length > 0
        )
            throw new ApiException(
                409,
                "Autodesk sign-in requires ORBIT's HTTPS website address. Check Orbit__PublicOrigin if a custom domain is used."
            );
        return uri.GetLeftPart(UriPartial.Authority) + CallbackPath;
    }

    public async Task<(Actor Who, Record Profile)> Scoped(
        HttpContext ctx,
        string project,
        string id,
        bool gate = false
    )
    {
        var who = await Actor.Resolve(ctx, db, config);
        who.Permit("connection");
        var r = await ConnectionRoutes.Scoped(db, who, project, id);
        if (r.Data().S("provider") != "forma" || r.Data().S("kind") != "read")
            throw new ApiException(404, "Autodesk connection unavailable in this project.");
        if (gate)
            Gate(r);
        return (who, r);
    }

    static void Gate(Record r)
    {
        var c = r.Data()["configuration"]!;
        if (c.S("base_url").TrimEnd('/') != Api)
            throw new ApiException(
                422,
                "Use https://developer.api.autodesk.com for Autodesk document management."
            );
        if (
            !c.B("approved_test_access")
            || !c.B("vendor_settings_confirmed")
            || string.IsNullOrWhiteSpace(c.S("evidence_note"))
        )
            throw new ApiException(
                409,
                "Confirm authorised access, vendor settings and a non-secret reference in Edit setup first."
            );
    }

    async Task<Record> App(Record r) =>
        await db.Find(r.Tenant, r.Project, "aps-app", r.Id)
        ?? throw new ApiException(
            409,
            "Save your APS Client ID and Client Secret below, then select Sign in with Autodesk."
        );

    async Task<Record> Recheck(
        HttpContext ctx,
        Actor actor,
        Record original,
        long generation,
        long appVersion
    )
    {
        db.ChangeTracker.Clear();
        var (who, current) = await Scoped(ctx, original.Project, original.Id, true);
        if (
            who.Id != actor.Id
            || who.Tenant != actor.Tenant
            || current.Version != generation
            || (await App(current)).Version != appVersion
        )
            throw new ApiException(
                409,
                "The account or Autodesk connection changed. Restart authorisation or discovery."
            );
        return current;
    }

    public static async Task Invalidate(OrbitDb db, Record profile, bool removeApp = false)
    {
        foreach (
            var kind in new[] { "aps-state", "aps-choice", "aps-token" }.Concat(
                removeApp ? ["aps-app"] : Array.Empty<string>()
            )
        )
        foreach (var row in await db.List(profile.Tenant, profile.Project, kind))
            if (row.Id == profile.Id || row.Data().S("connection_id") == profile.Id)
                db.Remove(row);
    }

    JsonObject Tokens(Record? r) =>
        r?.Secret == null ? new() : JsonNode.Parse(cipher.Unprotect(r.Secret))!.AsObject();

    public async Task<object> Status(HttpContext ctx, string project, string id)
    {
        var (_, r) = await Scoped(ctx, project, id);
        var app = await db.Find(r.Tenant, r.Project, "aps-app", id);
        var stored = await db.Find(r.Tenant, r.Project, "aps-token", id);
        var tokens = Tokens(stored);
        return new
        {
            callback_url = Callback(ctx),
            app = app == null
                ? null
                : new { client_id = app.Data().S("client_id"), mode = app.Data().S("mode") },
            expires = stored == null ? (long?)null : stored.Data().N("expires"),
            renewal_available = app != null
                && (app.Data().S("mode") == "two_legged" || tokens.S("refresh_token").Length > 0),
            scope = "data:read",
        };
    }

    public async Task<object> Configure(HttpContext ctx, string project, string id, JsonObject body)
    {
        var (who, r) = await Scoped(ctx, project, id);
        var clientId = body.Required("client_id", 200);
        var secret = body.Required("client_secret", 8192);
        var mode = body.S("mode", "three_legged");
        if (
            !Regex.IsMatch(clientId, "^[A-Za-z0-9_.-]{5,200}$")
            || secret.Length < 8
            || secret.Any(char.IsControl)
            || !new[] { "three_legged", "two_legged" }.Contains(mode)
        )
            throw new ApiException(
                422,
                "Check the APS Client ID, Client Secret and authorisation mode."
            );
        var callback = Callback(ctx);
        await Invalidate(db, r);
        var app = await db.Find(who.Tenant, project, "aps-app", id);
        var data = new JsonObject
        {
            ["connection_id"] = id,
            ["client_id"] = clientId,
            ["mode"] = mode,
        };
        if (app == null)
            app = db.Add(who.Tenant, project, "aps-app", id, data);
        else
            db.Change(app, data);
        app.Secret = cipher.Protect(secret);
        ClearAccess(r);
        db.Audit(who, "autodesk.app_configured", project, id);
        await db.SaveChangesAsync(ctx.RequestAborted);
        return new { configured = true, callback_url = callback };
    }

    void ClearAccess(Record r)
    {
        r.Secret = null;
        var d = r.Data();
        d["last_result"] = null;
        d.Remove("autodesk_expires");
        db.Change(r, d);
    }

    async Task<JsonObject> Exchange(
        Record app,
        Dictionary<string, string> parameters,
        CancellationToken ct
    )
    {
        if (app.Secret == null)
            throw new ApiException(409, "Save the APS application secret again.");
        using var request = new HttpRequestMessage(
            HttpMethod.Post,
            Api + "/authentication/v2/token"
        );
        request.Headers.Authorization = new AuthenticationHeaderValue(
            "Basic",
            Convert.ToBase64String(
                Encoding.UTF8.GetBytes(
                    app.Data().S("client_id") + ":" + cipher.Unprotect(app.Secret)
                )
            )
        );
        request.Headers.Accept.Add(new("application/json"));
        request.Content = new FormUrlEncodedContent(parameters);
        using var response = await clients
            .CreateClient("vendor")
            .SendAsync(request, HttpCompletionOption.ResponseHeadersRead, ct);
        if (!response.IsSuccessStatusCode)
            throw new ApiException(
                502,
                "Autodesk rejected authorisation. Check the APS application type, Client ID/Secret, exact callback URL, consent and administrator provisioning, then sign in again."
            );
        if (response.Content.Headers.ContentLength > 100000)
            throw new ApiException(502, "Unexpected Autodesk token response.");
        await using var stream = await response.Content.ReadAsStreamAsync(ct);
        using var memory = new MemoryStream();
        var buffer = new byte[8192];
        int length;
        while ((length = await stream.ReadAsync(buffer, ct)) > 0)
        {
            if (memory.Length + length > 100000)
                throw new ApiException(502, "Unexpected Autodesk token response.");
            await memory.WriteAsync(buffer.AsMemory(0, length), ct);
        }
        JsonObject payload;
        try
        {
            payload = JsonNode.Parse(memory.ToArray())!.AsObject();
        }
        catch (Exception e)
            when (e
                    is System.Text.Json.JsonException
                        or InvalidOperationException
                        or NullReferenceException
            )
        {
            throw new ApiException(502, "Unexpected Autodesk token response.");
        }
        var access = payload.S("access_token");
        var refresh = payload.S("refresh_token");
        if (
            access.Length is < 8 or > 8192
            || access.Any(char.IsControl)
            || refresh.Length > 8192
            || refresh.Any(char.IsControl)
            || payload.N("expires_in") is < 1 or > 86400
            || payload.S("token_type", "Bearer").ToLowerInvariant() != "bearer"
        )
            throw new ApiException(502, "Unexpected Autodesk token response.");
        var granted = payload.S("scope");
        if (granted.Length > 0 && !granted.Split(' ').Contains("data:read"))
            throw new ApiException(502, "Autodesk did not grant the requested read scope.");
        return new()
        {
            ["access_token"] = access,
            ["refresh_token"] = refresh,
            ["expires"] = Now + payload.N("expires_in"),
        };
    }

    async Task StoreTokens(Actor who, Record r, JsonObject tokens, string action)
    {
        var previous = await db.Find(r.Tenant, r.Project, "aps-token", r.Id);
        foreach (var choice in await db.List(r.Tenant, r.Project, "aps-choice"))
            if (choice.Data().S("connection_id") == r.Id)
                db.Remove(choice);
        var meta = new JsonObject { ["connection_id"] = r.Id, ["expires"] = tokens.N("expires") };
        if (previous == null)
            previous = db.Add(r.Tenant, r.Project, "aps-token", r.Id, meta);
        else
            db.Change(previous, meta);
        previous.Secret = cipher.Protect(tokens.ToJsonString());
        r.Secret = cipher.Protect(tokens.S("access_token"));
        var d = r.Data();
        d["autodesk_expires"] = tokens.N("expires");
        d["last_result"] = null;
        db.Change(r, d);
        db.Audit(who, action, r.Project, r.Id);
        await db.SaveChangesAsync();
    }

    public async Task<object> Connect(HttpContext ctx, string project, string id)
    {
        var (who, r) = await Scoped(ctx, project, id, true);
        var app = await App(r);
        var generation = r.Version;
        var appVersion = app.Version;
        if (app.Data().S("mode") == "two_legged")
        {
            var tokens = await Exchange(
                app,
                new() { ["grant_type"] = "client_credentials", ["scope"] = "data:read" },
                ctx.RequestAborted
            );
            r = await Recheck(ctx, who, r, generation, appVersion);
            await StoreTokens(who, r, tokens, "autodesk.application_token_obtained");
            return new
            {
                connected = true,
                expires = tokens.N("expires"),
                permission_claim = "Token obtained; resource access remains unverified.",
            };
        }
        var callback = Callback(ctx);
        var browserOrigin = ctx.Request.Scheme + "://" + ctx.Request.Host;
        if (
            !string.Equals(
                new Uri(callback).GetLeftPart(UriPartial.Authority),
                browserOrigin,
                StringComparison.OrdinalIgnoreCase
            )
        )
            throw new ApiException(
                409,
                "Open ORBIT at "
                    + new Uri(callback).GetLeftPart(UriPartial.Authority)
                    + " before signing in with Autodesk."
            );
        var session = Session(ctx);
        var state = Random();
        var browser = Random();
        var verifier = Random();
        var challenge = WebEncoders.Base64UrlEncode(
            SHA256.HashData(Encoding.ASCII.GetBytes(verifier))
        );
        foreach (var old in await db.List(r.Tenant, project, "aps-state"))
            if (old.Data().S("connection_id") == id || old.Data().N("expires") <= Now)
                db.Remove(old);
        var saved = db.Add(
            r.Tenant,
            project,
            "aps-state",
            Hash(state),
            new()
            {
                ["connection_id"] = id,
                ["actor"] = who.Id,
                ["session"] = session,
                ["browser"] = Hash(browser),
                ["generation"] = generation,
                ["app_version"] = appVersion,
                ["callback"] = callback,
                ["expires"] = Now + 600,
                ["consumed"] = false,
            }
        );
        saved.Secret = cipher.Protect(verifier);
        db.Audit(who, "autodesk.consent_started", project, id);
        await db.SaveChangesAsync(ctx.RequestAborted);
        ctx.Response.Cookies.Append(BrowserCookie, browser, Cookie());
        return new
        {
            authorize_url = QueryHelpers.AddQueryString(
                Api + "/authentication/v2/authorize",
                new Dictionary<string, string?>
                {
                    ["client_id"] = app.Data().S("client_id"),
                    ["response_type"] = "code",
                    ["redirect_uri"] = callback,
                    ["scope"] = "data:read",
                    ["state"] = state,
                    ["code_challenge"] = challenge,
                    ["code_challenge_method"] = "S256",
                }
            ),
        };
    }

    public async Task<IResult> Complete(HttpContext ctx)
    {
        string? project = null;
        var outcome = "failed";
        var reason = "consent_rejected";
        try
        {
            var who = await Actor.Resolve(ctx, db, config);
            who.Permit("connection");
            var state = ctx.Request.Query["state"].ToString();
            if (state.Length is < 32 or > 200)
                throw new ApiException(409, "Invalid consent state.");
            var saved = await db.Records.SingleOrDefaultAsync(r =>
                r.Tenant == who.Tenant && r.Kind == "aps-state" && r.Id == Hash(state)
            );
            if (saved == null)
                throw new ApiException(409, "Consent state unavailable.");
            var details = saved.Data();
            project = saved.Project;
            if (
                details.B("consumed")
                || details.N("expires") <= Now
                || details.S("actor") != who.Id
                || !Equal(details.S("session"), Session(ctx))
                || !Equal(details.S("browser"), Hash(ctx.Request.Cookies[BrowserCookie] ?? ""))
            )
                throw new ApiException(409, "Consent session expired or changed.");
            var (_, r) = await Scoped(ctx, project, details.S("connection_id"), true);
            var app = await App(r);
            if (
                r.Version != details.N("generation")
                || app.Version != details.N("app_version")
                || app.Data().S("mode") != "three_legged"
                || Callback(ctx) != details.S("callback")
            )
                throw new ApiException(409, "Consent settings changed.");
            var verifier = cipher.Unprotect(saved.Secret!);
            saved.Secret = null;
            details["consumed"] = true;
            db.Change(saved, details);
            await db.SaveChangesAsync();
            if (ctx.Request.Query.ContainsKey("error"))
            {
                reason = "consent_denied";
                throw new ApiException(409, "Autodesk consent was not completed.");
            }
            var code = ctx.Request.Query["code"].ToString();
            if (code.Length is < 1 or > 8192 || code.Any(char.IsControl))
                throw new ApiException(409, "Authorisation code unavailable.");
            var tokens = await Exchange(
                app,
                new()
                {
                    ["grant_type"] = "authorization_code",
                    ["code"] = code,
                    ["redirect_uri"] = details.S("callback"),
                    ["code_verifier"] = verifier,
                },
                ctx.RequestAborted
            );
            r = await Recheck(ctx, who, r, details.N("generation"), details.N("app_version"));
            var consumed = await db.Find(who.Tenant, project, "aps-state", saved.Id);
            if (consumed == null || !consumed.Data().B("consumed"))
                throw new ApiException(409, "A newer consent flow replaced this one.");
            await StoreTokens(who, r, tokens, "autodesk.consent_completed");
            outcome = "connected";
        }
        catch (Exception error)
            when (error
                    is ApiException
                        or DbUpdateException
                        or HttpRequestException
                        or TaskCanceledException
                        or CryptographicException
            ) { }
        ctx.Response.Cookies.Delete(
            BrowserCookie,
            new CookieOptions
            {
                Path = "/",
                Secure = true,
                HttpOnly = true,
                SameSite = SameSiteMode.Lax,
            }
        );
        ctx.Response.Headers["Referrer-Policy"] = "no-referrer";
        var parameters = new Dictionary<string, string?> { ["autodesk"] = outcome };
        if (project != null)
            parameters["autodesk_project"] = project;
        if (outcome != "connected")
            parameters["autodesk_error"] = reason;
        return Results.Redirect(QueryHelpers.AddQueryString("/", parameters), false, false);
    }

    public async Task<object> Renew(HttpContext ctx, string project, string id)
    {
        var (who, r) = await Scoped(ctx, project, id, true);
        var app = await App(r);
        var mode = app.Data().S("mode");
        var stored = await db.Find(who.Tenant, project, "aps-token", id);
        var old = Tokens(stored);
        if (mode == "three_legged" && old.S("refresh_token").Length == 0)
            throw new ApiException(
                409,
                "Sign in with Autodesk again; no refresh token is available."
            );
        if (stored != null && stored.Data().N("renewing_until") > Now)
            throw new ApiException(
                409,
                "Authorisation renewal is already running. Wait briefly, then refresh."
            );
        var generation = r.Version;
        var appVersion = app.Version;
        var tokenVersion = stored?.Version ?? 0;
        if (stored != null)
        {
            var d = stored.Data();
            d["renewing_until"] = Now + 90;
            db.Change(stored, d);
            await db.SaveChangesAsync();
            tokenVersion = stored.Version;
        }
        try
        {
            var parameters =
                mode == "two_legged"
                    ? new Dictionary<string, string>
                    {
                        ["grant_type"] = "client_credentials",
                        ["scope"] = "data:read",
                    }
                    : new()
                    {
                        ["grant_type"] = "refresh_token",
                        ["refresh_token"] = old.S("refresh_token"),
                    };
            var tokens = await Exchange(app, parameters, ctx.RequestAborted);
            if (mode == "three_legged" && tokens.S("refresh_token").Length == 0)
                tokens["refresh_token"] = old.S("refresh_token");
            r = await Recheck(ctx, who, r, generation, appVersion);
            var current = await db.Find(r.Tenant, project, "aps-token", id);
            if ((current?.Version ?? 0) != tokenVersion)
                throw new ApiException(409, "Authorisation changed during renewal. Sign in again.");
            await StoreTokens(who, r, tokens, "autodesk.token_renewed");
            return new { renewed = true, expires = tokens.N("expires") };
        }
        finally
        {
            db.ChangeTracker.Clear();
            var lease = await db.Find(r.Tenant, project, "aps-token", id);
            if (lease?.Version == tokenVersion && lease.Data().N("renewing_until") > 0)
            {
                var d = lease.Data();
                d.Remove("renewing_until");
                db.Change(lease, d);
                await db.SaveChangesAsync();
            }
        }
    }

    public async Task<object> Disconnect(HttpContext ctx, string project, string id)
    {
        var (who, r) = await Scoped(ctx, project, id);
        await Invalidate(db, r, true);
        ClearAccess(r);
        db.Audit(who, "autodesk.disconnected_locally", project, id);
        await db.SaveChangesAsync();
        return new { disconnected_locally = true, vendor_revoked = false };
    }

    public static void FreshAccess(Record r)
    {
        if (r.Secret == null)
            throw new ApiException(
                409,
                "Save the APS application and select Sign in with Autodesk first."
            );
        var expires = r.Data()["autodesk_expires"];
        if (expires != null && r.Data().N("autodesk_expires") <= Now + 15)
            throw new ApiException(
                409,
                "Autodesk authorisation expired. Select Renew authorisation or Sign in with Autodesk."
            );
    }

    static string Identifier(string value)
    {
        if (
            value.Length is < 1 or > 500
            || value is "." or ".."
            || value.Any(c => char.IsControl(c) || char.IsWhiteSpace(c) || "/\\?#".Contains(c))
        )
            throw new ApiException(422, "Choose a valid Autodesk resource from discovery.");
        return value;
    }

    static string Parent(string kind, string hub, string project) =>
        kind == "hubs" ? ""
        : kind == "projects" ? hub
        : new JsonArray(hub, project).ToJsonString();

    static string ChoiceId(string connection, string kind, string parent) =>
        Hash(new JsonArray(connection, kind, parent).ToJsonString());

    async Task<JsonObject> Choice(Record r, string kind, string parent, string id)
    {
        var cache = await db.Find(r.Tenant, r.Project, "aps-choice", ChoiceId(r.Id, kind, parent));
        var d = cache?.Data();
        if (d == null || d.N("generation") != r.Version || d.N("expires") <= Now)
            throw new ApiException(
                409,
                "Refresh discovery and select from the current authorised list."
            );
        return d["resources"]!.AsArray().SingleOrDefault(v => v.S("id") == id)?.AsObject()
            ?? throw new ApiException(
                409,
                "That resource was not discovered in this hub/project. Refresh the list."
            );
    }

    public async Task<object> Discover(HttpContext ctx, string project, string id, JsonObject body)
    {
        var (who, r) = await Scoped(ctx, project, id, true);
        FreshAccess(r);
        var app = await App(r);
        var generation = r.Version;
        var appVersion = app.Version;
        var kind = body.Required("kind", 20);
        var hub = body.S("hub");
        var vendorProject = body.S("project");
        var page = body.N("page");
        if (
            !new[] { "hubs", "projects", "folders" }.Contains(kind)
            || page < 0
            || page > 39
            || kind != "projects" && page != 0
        )
            throw new ApiException(
                422,
                "Choose hubs, projects or folders and a valid project page."
            );
        if (kind != "hubs")
            await Choice(r, "hubs", "", Identifier(hub));
        if (kind == "folders")
            await Choice(r, "projects", hub, Identifier(vendorProject));
        var parent = Parent(kind, hub, vendorProject);
        var cacheId = ChoiceId(id, kind, parent);
        var previous = await db.Find(who.Tenant, project, "aps-choice", cacheId);
        if (
            page > 0
            && (
                previous == null
                || previous.Data().N("expires") <= Now
                || previous.Data().N("generation") != generation
                || previous.Data()["pages"]?.AsArray().Any(n => n!.GetValue<long>() == page - 1)
                    != true
            )
        )
            throw new ApiException(
                409,
                "Load project pages in order; restart discovery if the list expired."
            );
        var path = kind switch
        {
            "hubs" => "/project/v1/hubs",
            "projects" => "/project/v1/hubs/"
                + Uri.EscapeDataString(hub)
                + "/projects?page%5Blimit%5D=25&page%5Bnumber%5D="
                + page,
            _ => "/project/v1/hubs/"
                + Uri.EscapeDataString(hub)
                + "/projects/"
                + Uri.EscapeDataString(vendorProject)
                + "/topFolders",
        };
        var payload = await reader.Get(new Uri(Api + path), r, ctx.RequestAborted);
        if (payload is not JsonObject payloadObject || payloadObject["data"] is not JsonArray rows)
            throw new ApiException(502, "Autodesk returned an unexpected resource collection.");
        var resources = new JsonArray();
        var seen = new HashSet<string>(StringComparer.Ordinal);
        foreach (var item in rows.Take(25))
        {
            if (item is not JsonObject row)
                throw new ApiException(502, "Autodesk returned an invalid resource.");
            string native;
            try
            {
                native = Identifier(row.Required("id", 500));
            }
            catch (ApiException)
            {
                throw new ApiException(502, "Autodesk returned an invalid resource identifier.");
            }
            var access = cipher.Unprotect(r.Secret!);
            if (native.Contains(access, StringComparison.Ordinal))
                throw new ApiException(502, "Autodesk returned an invalid resource identifier.");
            if (!seen.Add(native))
                throw new ApiException(502, "Autodesk returned ambiguous resource IDs.");
            var label = item?["attributes"].S(
                "name",
                item?["attributes"].S("displayName", native) ?? native
            )
                ?? native;
            label = label.Replace(access, "[REDACTED]", StringComparison.Ordinal);
            if (label.Length > 500)
                label = label[..500];
            resources.Add(
                new JsonObject
                {
                    ["id"] = native,
                    ["label"] = label,
                    ["kind"] = kind,
                }
            );
        }
        r = await Recheck(ctx, who, r, generation, appVersion);
        previous = await db.Find(who.Tenant, project, "aps-choice", cacheId);
        var all = resources.DeepClone().AsArray();
        var pages = new JsonArray(page);
        if (page > 0)
        {
            if (
                previous == null
                || previous.Data().N("expires") <= Now
                || previous.Data().N("generation") != generation
            )
                throw new ApiException(409, "Discovery changed; reload the projects.");
            var d = previous.Data();
            var combined = d["resources"]!
                .AsArray()
                .Concat(resources)
                .GroupBy(v => v.S("id"))
                .Select(g => g.Last()!.DeepClone())
                .ToArray();
            if (combined.Length > 1000)
                throw new ApiException(409, "Discovery reached the 1,000-project limit.");
            all = new JsonArray(combined);
            pages = d["pages"]!.DeepClone().AsArray();
            if (!pages.Any(p => p!.GetValue<long>() == page))
                pages.Add(page);
        }
        var cached = new JsonObject
        {
            ["connection_id"] = id,
            ["generation"] = generation,
            ["kind"] = kind,
            ["parent"] = parent,
            ["resources"] = all,
            ["pages"] = pages,
            ["expires"] = Now + 600,
        };
        if (previous == null)
            db.Add(who.Tenant, project, "aps-choice", cacheId, cached);
        else
            db.Change(previous, cached);
        db.Audit(who, "autodesk.resources_discovered", project, id + ": " + kind);
        await db.SaveChangesAsync();
        return new
        {
            resources,
            returned = resources.Count,
            synthetic = false,
            coverage = "Bounded Autodesk discovery response; not a complete register.",
            page,
        };
    }

    public async Task<object> Select(HttpContext ctx, string project, string id, JsonObject body)
    {
        var (who, r) = await Scoped(ctx, project, id, true);
        FreshAccess(r);
        var hub = body.Required("hub", 500);
        var vendorProject = body.Required("project", 500);
        var folder = body.S("folder");
        var h = await Choice(r, "hubs", "", hub);
        var p = await Choice(r, "projects", hub, vendorProject);
        var f =
            folder.Length > 0
                ? await Choice(r, "folders", Parent("folders", hub, vendorProject), folder)
                : null;
        var d = r.Data();
        var c = d["configuration"]!.AsObject();
        c["hub"] = hub;
        c["vendor_project"] = vendorProject;
        c["folder"] = folder;
        c["hub_label"] = h.S("label");
        c["project_label"] = p.S("label");
        c["folder_label"] = f?.S("label") ?? "";
        d["last_result"] = null;
        db.Change(r, d);
        foreach (var choice in await db.List(r.Tenant, project, "aps-choice"))
            if (choice.Data().S("connection_id") == id)
                db.Remove(choice);
        db.Audit(who, "autodesk.scope_selected", project, id);
        await db.SaveChangesAsync();
        return new
        {
            saved = true,
            hub = h.S("label"),
            project = p.S("label"),
            folder = f?.S("label"),
        };
    }

    public static void Map(WebApplication app)
    {
        var root = "/api/projects/{project}/read-connections/{id}/autodesk";
        app.MapGet(root, async (string project, string id, HttpContext ctx, AutodeskOAuth aps) =>
            Results.Ok(await aps.Status(ctx, project, id))
        );
        app.MapPut(
            root,
            async (
                string project,
                string id,
                JsonObject body,
                HttpContext ctx,
                AutodeskOAuth aps
            ) => Results.Ok(await aps.Configure(ctx, project, id, body))
        );
        app.MapPost(
            root + "/connect",
            async (string project, string id, HttpContext ctx, AutodeskOAuth aps) =>
                Results.Ok(await aps.Connect(ctx, project, id))
        );
        app.MapPost(
            root + "/renew",
            async (string project, string id, HttpContext ctx, AutodeskOAuth aps) =>
                Results.Ok(await aps.Renew(ctx, project, id))
        );
        app.MapDelete(root, async (string project, string id, HttpContext ctx, AutodeskOAuth aps) =>
            Results.Ok(await aps.Disconnect(ctx, project, id))
        );
        app.MapPost(
            root + "/discover",
            async (
                string project,
                string id,
                JsonObject body,
                HttpContext ctx,
                AutodeskOAuth aps
            ) => Results.Ok(await aps.Discover(ctx, project, id, body))
        );
        app.MapPut(
            root + "/selection",
            async (
                string project,
                string id,
                JsonObject body,
                HttpContext ctx,
                AutodeskOAuth aps
            ) => Results.Ok(await aps.Select(ctx, project, id, body))
        );
        app.MapGet(CallbackPath, async (HttpContext ctx, AutodeskOAuth aps) =>
            await aps.Complete(ctx)
        );
    }
}
