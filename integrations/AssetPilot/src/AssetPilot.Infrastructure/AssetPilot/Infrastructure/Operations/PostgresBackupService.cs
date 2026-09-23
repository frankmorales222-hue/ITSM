using System.Diagnostics;
using AssetPilot.Application.Auditing;
using AssetPilot.Application.Operations;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;
using Npgsql;

namespace AssetPilot.Infrastructure.Operations;

public sealed class PostgresBackupService(
    IConfiguration configuration,
    IHostEnvironment environment,
    AssetPilotDbContext db,
    IAuditService audit) : IBackupService
{
    public Task<IReadOnlyList<BackupInfo>> ListAsync(CancellationToken cancellationToken = default)
    {
        cancellationToken.ThrowIfCancellationRequested();
        var directory = BackupDirectory();
        Directory.CreateDirectory(directory);
        IReadOnlyList<BackupInfo> backups = new DirectoryInfo(directory)
            .EnumerateFiles("assetpilot-*.dump", SearchOption.TopDirectoryOnly)
            .OrderByDescending(file => file.CreationTimeUtc)
            .Select(file => new BackupInfo(file.Name, file.Length, file.CreationTimeUtc))
            .ToList();
        return Task.FromResult(backups);
    }

    public async Task<BackupResult> CreateAndVerifyAsync(
        string? userId,
        string correlationId,
        CancellationToken cancellationToken = default)
    {
        var directory = BackupDirectory();
        Directory.CreateDirectory(directory);
        var fileName = $"assetpilot-{DateTime.UtcNow:yyyyMMdd-HHmmss}-{Guid.NewGuid():N}.dump";
        var destination = Path.Combine(directory, fileName);
        var connection = new NpgsqlConnectionStringBuilder(
            configuration["Database:ConnectionString"] ??
            throw new InvalidOperationException("Database:ConnectionString is required."));
        var pgDump = FindPostgresTool("pg_dump.exe");
        var pgRestore = FindPostgresTool("pg_restore.exe", Path.GetDirectoryName(pgDump));

        try
        {
            await RunAsync(pgDump, connection, true, cancellationToken,
                "--format=custom", "--no-owner", "--no-privileges", "--schema=assetpilot",
                $"--file={destination}");
            await RunAsync(pgRestore, connection, false, cancellationToken, "--list", destination);
            var assetCount = await db.Assets.CountAsync(cancellationToken);
            var result = new BackupResult(fileName, new FileInfo(destination).Length, assetCount, IsVerified: true);
            await audit.WriteAsync("Operations.BackupCreated", "DatabaseBackup", fileName, userId, null,
                result, "Verified with pg_restore --list", correlationId, cancellationToken);
            return result;
        }
        catch
        {
            File.Delete(destination);
            throw;
        }
    }

    private async Task RunAsync(
        string executable,
        NpgsqlConnectionStringBuilder connection,
        bool includeConnection,
        CancellationToken cancellationToken,
        params string[] operationArguments)
    {
        var start = new ProcessStartInfo(executable)
        {
            UseShellExecute = false,
            RedirectStandardError = true,
            RedirectStandardOutput = true,
            CreateNoWindow = true,
        };
        if (includeConnection)
        {
            start.ArgumentList.Add($"--host={connection.Host}");
            start.ArgumentList.Add($"--port={connection.Port}");
            start.ArgumentList.Add($"--username={connection.Username}");
            start.ArgumentList.Add($"--dbname={connection.Database}");
        }
        foreach (var argument in operationArguments)
            start.ArgumentList.Add(argument);
        start.Environment["PGPASSWORD"] = connection.Password;
        using var process = Process.Start(start) ?? throw new InvalidOperationException($"Could not start {executable}.");
        var errorTask = process.StandardError.ReadToEndAsync(cancellationToken);
        await process.WaitForExitAsync(cancellationToken);
        var error = await errorTask;
        if (process.ExitCode != 0)
            throw new InvalidOperationException($"PostgreSQL backup verification failed: {error.Trim()}");
    }

    private string FindPostgresTool(string fileName, string? preferredDirectory = null)
    {
        var configured = configuration[$"Backup:{Path.GetFileNameWithoutExtension(fileName)}Path"];
        var candidates = new List<string?>
        {
            configured,
            preferredDirectory is null ? null : Path.Combine(preferredDirectory, fileName),
        };
        var programFiles = Environment.GetFolderPath(Environment.SpecialFolder.ProgramFiles);
        var postgresRoot = Path.Combine(programFiles, "PostgreSQL");
        if (Directory.Exists(postgresRoot))
            candidates.AddRange(Directory.EnumerateDirectories(postgresRoot)
                .OrderByDescending(path => path)
                .Select(path => Path.Combine(path, "bin", fileName)));
        var found = candidates.FirstOrDefault(path => !string.IsNullOrWhiteSpace(path) && File.Exists(path));
        return found ?? throw new InvalidOperationException(
            $"{fileName} was not found. Install PostgreSQL command-line tools or configure Backup:{Path.GetFileNameWithoutExtension(fileName)}Path.");
    }

    private string BackupDirectory()
    {
        var path = configuration["Backup:Path"];
        return Path.GetFullPath(Path.Combine(environment.ContentRootPath,
            string.IsNullOrWhiteSpace(path) ? Path.Combine("App_Data", "Backups") : path));
    }
}
