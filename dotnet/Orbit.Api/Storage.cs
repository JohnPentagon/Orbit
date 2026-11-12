using System.Security.Cryptography;
using System.Text;
using System.Text.Json.Nodes;
using Microsoft.EntityFrameworkCore;

namespace Orbit.Api;

public sealed class Record
{
    public string Tenant { get; set; } = "";
    public string Project { get; set; } = "";
    public string Kind { get; set; } = "";
    public string Id { get; set; } = "";
    public long Version { get; set; } = 1;
    public string Json { get; set; } = "{}";
    public string? Secret { get; set; }
    public DateTimeOffset Updated { get; set; } = DateTimeOffset.UtcNow;

    public JsonObject Data() => JsonNode.Parse(Json)!.AsObject();
}

public sealed class OrbitDb(DbContextOptions<OrbitDb> options) : DbContext(options)
{
    public DbSet<Record> Records => Set<Record>();

    protected override void OnModelCreating(ModelBuilder m)
    {
        m.Entity<Record>()
            .HasKey(x => new
            {
                x.Tenant,
                x.Project,
                x.Kind,
                x.Id,
            });
        m.Entity<Record>().Property(x => x.Tenant).HasMaxLength(50);
        m.Entity<Record>().Property(x => x.Project).HasMaxLength(100);
        m.Entity<Record>().Property(x => x.Kind).HasMaxLength(50);
        m.Entity<Record>().Property(x => x.Id).HasMaxLength(150);
        m.Entity<Record>().Property(x => x.Version).IsConcurrencyToken();
        m.Entity<Record>()
            .Property(x => x.Updated)
            .HasConversion(v => v.UtcTicks, v => new DateTimeOffset(v, TimeSpan.Zero));
    }

    public Task<Record?> Find(
        string tenant,
        string project,
        string kind,
        string id,
        CancellationToken ct = default
    ) =>
        Records.SingleOrDefaultAsync(
            x => x.Tenant == tenant && x.Project == project && x.Kind == kind && x.Id == id,
            ct
        );

    public async Task<List<Record>> List(
        string tenant,
        string project,
        string kind,
        CancellationToken ct = default
    ) =>
        await Records
            .Where(x => x.Tenant == tenant && x.Project == project && x.Kind == kind)
            .OrderByDescending(x => x.Updated)
            .ToListAsync(ct);

    public Record Add(string tenant, string project, string kind, string id, JsonObject value)
    {
        var r = new Record
        {
            Tenant = tenant,
            Project = project,
            Kind = kind,
            Id = id,
            Json = value.ToJsonString(),
        };
        Records.Add(r);
        return r;
    }

    public void Change(Record r, JsonObject value)
    {
        r.Json = value.ToJsonString();
        r.Version++;
        r.Updated = DateTimeOffset.UtcNow;
    }

    public void Audit(Actor who, string action, string project = "", string subject = "")
    {
        Add(
            who.Tenant,
            project,
            "audit",
            Guid.NewGuid().ToString(),
            new()
            {
                ["action"] = action,
                ["actor"] = who.Id,
                ["subject"] = subject,
                ["created"] = DateTimeOffset.UtcNow.ToString("O"),
            }
        );
    }
}

public sealed class ApiException(int status, string message) : Exception(message)
{
    public int Status => status;
}

public static class Json
{
    public static string S(this JsonNode? n, string key, string fallback = "") =>
        n is JsonObject o && o[key] is JsonValue v && v.TryGetValue<string>(out var text)
            ? text
            : fallback;

    public static bool B(this JsonNode? n, string key) =>
        n is JsonObject o
        && o[key] is JsonValue v
        && v.TryGetValue<bool>(out var enabled)
        && enabled;

    public static long N(this JsonNode? n, string key, long fallback = 0) =>
        long.TryParse(n?[key]?.ToString(), out var number) ? number : fallback;

    public static JsonObject Copy(this JsonObject n) => (JsonObject)n.DeepClone();

    public static string Required(this JsonNode n, string key, int max = 500)
    {
        var s = n.S(key).Trim();
        if (s.Length == 0 || s.Length > max)
            throw new ApiException(422, $"Enter a valid {key.Replace('_', ' ')}.");
        return s;
    }
}

public sealed class Cipher
{
    readonly byte[] key;

    public Cipher(IConfiguration config)
    {
        var value = config["Orbit:EncryptionKey"]
            ?? throw new InvalidOperationException(
                "Orbit:EncryptionKey must be configured securely."
            );
        key = Convert.FromBase64String(value);
        if (key.Length != 32)
            throw new InvalidOperationException("Encryption key must contain 32 bytes.");
    }

    public string Protect(string text)
    {
        var nonce = RandomNumberGenerator.GetBytes(12);
        var raw = Encoding.UTF8.GetBytes(text);
        var result = new byte[28 + raw.Length];
        nonce.CopyTo(result, 0);
        using var aes = new AesGcm(key, 16);
        aes.Encrypt(nonce, raw, result.AsSpan(28), result.AsSpan(12, 16));
        return Convert.ToBase64String(result);
    }

    public string Unprotect(string value)
    {
        var data = Convert.FromBase64String(value);
        var plain = new byte[data.Length - 28];
        using var aes = new AesGcm(key, 16);
        aes.Decrypt(data.AsSpan(0, 12), data.AsSpan(28), data.AsSpan(12, 16), plain);
        return Encoding.UTF8.GetString(plain);
    }
}
