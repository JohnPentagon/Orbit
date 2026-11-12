using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;

namespace Orbit.Api;

/// <summary>
/// Explicit single-process file storage for limited UAT on an existing App Service.
/// It creates no Azure resources and never enables the local passwordless login.
/// </summary>
public sealed class UatStorage : IDisposable
{
    public const string Mode = "FileUat";
    readonly FileStream lease;
    public string DirectoryPath { get; }
    public string ConnectionString { get; }

    public UatStorage(IConfiguration configuration)
    {
        var path = configuration["Orbit:DataPath"];
        if (string.IsNullOrWhiteSpace(path) || !Path.IsPathFullyQualified(path))
            throw new InvalidOperationException(
                "FileUat requires an absolute persistent Orbit:DataPath."
            );
        DirectoryPath = Path.GetFullPath(path);
        Directory.CreateDirectory(DirectoryPath);
        try
        {
            lease = new FileStream(
                Path.Combine(DirectoryPath, "orbit-uat.lock"),
                FileMode.OpenOrCreate,
                FileAccess.ReadWrite,
                FileShare.None
            );
        }
        catch (IOException error)
        {
            throw new InvalidOperationException(
                "The UAT data folder is in use. FileUat permits one application process/instance only. Stop the previous instance before restarting; do not delete its lock file.",
                error
            );
        }
        ConnectionString = new SqliteConnectionStringBuilder
        {
            DataSource = Path.Combine(DirectoryPath, "orbit-uat.db"),
            Pooling = false,
            DefaultTimeout = 15,
        }.ToString();
    }

    public async Task Initialise(OrbitDb database)
    {
        await database.Database.EnsureCreatedAsync();
        // Use rollback journaling rather than WAL on App Service's persistent share.
        await database.Database.ExecuteSqlRawAsync("PRAGMA journal_mode=DELETE;");
        await database.Database.ExecuteSqlRawAsync("PRAGMA synchronous=FULL;");
    }

    public void Dispose() => lease.Dispose();
}
