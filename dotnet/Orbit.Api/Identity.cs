using System.Security.Claims;
using Microsoft.EntityFrameworkCore;

namespace Orbit.Api;

public sealed record Actor(string Id, string Tenant, string Role)
{
    public string[] Permissions =>
        Role switch
        {
            "owner" => ["view", "run", "connection", "draft", "administer", "audit"],
            "engineer" => ["view", "run", "draft"],
            "approver" => ["view", "approve"],
            "auditor" => ["view", "audit"],
            _ => ["view"],
        };

    public void Permit(string action)
    {
        if (!Permissions.Contains(action))
            throw new ApiException(403, "Your role does not permit this action.");
    }

    public static async Task<Actor> Resolve(HttpContext ctx, OrbitDb db, IConfiguration config)
    {
        var oid = ctx.User.FindFirstValue("oid")
            ?? ctx.User.FindFirstValue(
                "http://schemas.microsoft.com/identity/claims/objectidentifier"
            );
        var tid = ctx.User.FindFirstValue("tid")
            ?? ctx.User.FindFirstValue("http://schemas.microsoft.com/identity/claims/tenantid");
        if (
            ctx.User.Identity?.IsAuthenticated != true
            || string.IsNullOrEmpty(oid)
            || string.IsNullOrEmpty(tid)
            || tid != config["Entra:TenantId"]
        )
            throw new ApiException(401, "Sign in with your organisation account.");
        var admin = (config["Orbit:AdminObjectIds"] ?? "")
            .Split(',', StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries)
            .Contains(oid, StringComparer.OrdinalIgnoreCase);
        var grant = await db.Find(tid, "", "member", oid, ctx.RequestAborted);
        if (!admin && grant == null)
            throw new ApiException(
                403,
                "Your account has not been granted access to ORBIT. Ask the workspace administrator."
            );
        return new(oid, tid, admin ? "owner" : grant!.Data().S("role", "viewer"));
    }

    public async Task Project(OrbitDb db, string project)
    {
        if (await db.Find(Tenant, "", "project", project) == null)
            throw new ApiException(404, "Project unavailable.");
        if (Role == "owner")
            return;
        var grant = await db.Find(Tenant, "", "member", Id);
        if (grant?.Data()["projects"]?.AsArray().Any(p => p?.GetValue<string>() == project) != true)
            throw new ApiException(403, "This project has not been granted to your account.");
    }
}
