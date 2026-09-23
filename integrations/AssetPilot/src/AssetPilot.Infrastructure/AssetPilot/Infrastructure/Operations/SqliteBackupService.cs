using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Auditing;
using AssetPilot.Application.Operations;
using Microsoft.Data.Sqlite;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.Hosting;

namespace AssetPilot.Infrastructure.Operations;

public sealed class SqliteBackupService(IConfiguration configuration, IHostEnvironment environment, IAuditService audit) : IBackupService
{
	public Task<IReadOnlyList<BackupInfo>> ListAsync(CancellationToken cancellationToken = default(CancellationToken))
	{
		cancellationToken.ThrowIfCancellationRequested();
		string path = BackupDirectory();
		Directory.CreateDirectory(path);
		return Task.FromResult((IReadOnlyList<BackupInfo>)(from file in new DirectoryInfo(path).EnumerateFiles("assetpilot-*.db", SearchOption.TopDirectoryOnly)
			orderby file.CreationTimeUtc descending
			select new BackupInfo(file.Name, file.Length, file.CreationTimeUtc)).ToList());
	}

	public async Task<BackupResult> CreateAndVerifyAsync(string? userId, string correlationId, CancellationToken cancellationToken = default(CancellationToken))
	{
		string text = BackupDirectory();
		Directory.CreateDirectory(text);
		string fileName = $"assetpilot-{DateTime.UtcNow:yyyyMMdd-HHmmss}-{Guid.NewGuid():N}.db";
		string destinationPath = Path.Combine(text, fileName);
		string dataSource = DatabasePath();
		await using (SqliteConnection source = new SqliteConnection(new SqliteConnectionStringBuilder
		{
			DataSource = dataSource,
			Mode = SqliteOpenMode.ReadWrite
		}.ToString()))
		{
			await source.OpenAsync(cancellationToken);
			await using SqliteCommand command = source.CreateCommand();
			command.CommandText = "VACUUM INTO $destination;";
			command.Parameters.AddWithValue("$destination", destinationPath);
			await command.ExecuteNonQueryAsync(cancellationToken);
		}
		var (flag, assetCount) = await VerifyAsync(destinationPath, cancellationToken);
		if (!flag)
		{
			File.Delete(destinationPath);
			throw new InvalidOperationException("The backup failed its SQLite integrity check.");
		}
		long length = new FileInfo(destinationPath).Length;
		BackupResult result = new BackupResult(fileName, length, assetCount, IsVerified: true);
		await audit.WriteAsync("Operations.BackupCreated", "DatabaseBackup", fileName, userId, null, result, "Verified with PRAGMA quick_check", correlationId, cancellationToken);
		return result;
	}

	private static async Task<(bool Verified, int AssetCount)> VerifyAsync(string path, CancellationToken cancellationToken)
	{
		(bool Verified, int AssetCount) result;
		await using (SqliteConnection connection = new SqliteConnection(new SqliteConnectionStringBuilder
		{
			DataSource = path,
			Mode = SqliteOpenMode.ReadOnly
		}.ToString()))
		{
			await connection.OpenAsync(cancellationToken);
			(bool Verified, int AssetCount) tuple2;
			await using (SqliteCommand check = connection.CreateCommand())
			{
				check.CommandText = "PRAGMA quick_check;";
				string checkResult = Convert.ToString(await check.ExecuteScalarAsync(cancellationToken));
				(bool Verified, int AssetCount) tuple;
				await using (SqliteCommand count = connection.CreateCommand())
				{
					count.CommandText = "SELECT COUNT(*) FROM Assets;";
					int item = Convert.ToInt32(await count.ExecuteScalarAsync(cancellationToken));
					tuple = (Verified: string.Equals(checkResult, "ok", StringComparison.OrdinalIgnoreCase), AssetCount: item);
				}
				tuple2 = tuple;
			}
			result = tuple2;
		}
		return result;
	}

	private string DatabasePath()
	{
		string text = configuration["Database:Path"];
		return Path.GetFullPath(Path.Combine(environment.ContentRootPath, string.IsNullOrWhiteSpace(text) ? Path.Combine("App_Data", "assetpilot.db") : text));
	}

	private string BackupDirectory()
	{
		string text = configuration["Backup:Path"];
		return Path.GetFullPath(Path.Combine(environment.ContentRootPath, string.IsNullOrWhiteSpace(text) ? Path.Combine("App_Data", "Backups") : text));
	}
}
