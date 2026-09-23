using System.Threading;
using System.Threading.Tasks;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Storage;

namespace AssetPilot.Infrastructure.Persistence;

public static class DatabaseBootstrapper
{
	private const int PostgreSqlSchemaVersion = 1;

	public static async Task InitializeAsync(AssetPilotDbContext dbContext, CancellationToken cancellationToken = default(CancellationToken))
	{
		if (!dbContext.Database.IsNpgsql())
		{
			await dbContext.Database.MigrateAsync(cancellationToken);
			await dbContext.Database.ExecuteSqlRawAsync("PRAGMA foreign_keys = ON;", cancellationToken);
			await dbContext.Database.ExecuteSqlRawAsync("PRAGMA journal_mode = WAL;", cancellationToken);
			await dbContext.Database.ExecuteSqlRawAsync("PRAGMA busy_timeout = 5000;", cancellationToken);
			return;
		}

		await dbContext.Database.ExecuteSqlRawAsync("CREATE SCHEMA IF NOT EXISTS assetpilot;", cancellationToken);
		await dbContext.Database.ExecuteSqlRawAsync("CREATE EXTENSION IF NOT EXISTS citext;", cancellationToken);
		bool exists = await dbContext.Database.SqlQueryRaw<int>(
			"SELECT CASE WHEN to_regclass('assetpilot.\"Assets\"') IS NULL THEN 0 ELSE 1 END AS \"Value\"")
			.SingleAsync(cancellationToken) == 1;
		if (!exists)
		{
			IRelationalDatabaseCreator creator = dbContext.Database.GetService<IRelationalDatabaseCreator>();
			await creator.CreateTablesAsync(cancellationToken);
		}
		await dbContext.Database.ExecuteSqlRawAsync(
			"CREATE TABLE IF NOT EXISTS assetpilot.\"__SchemaVersion\" (\"Version\" integer PRIMARY KEY, \"AppliedUtc\" timestamptz NOT NULL DEFAULT now());",
			cancellationToken);
		await dbContext.Database.ExecuteSqlRawAsync(
			$"INSERT INTO assetpilot.\"__SchemaVersion\" (\"Version\") VALUES ({PostgreSqlSchemaVersion}) ON CONFLICT (\"Version\") DO NOTHING;",
			cancellationToken);
		int installedVersion = await dbContext.Database.SqlQueryRaw<int>(
			"SELECT MAX(\"Version\") AS \"Value\" FROM assetpilot.\"__SchemaVersion\"")
			.SingleAsync(cancellationToken);
		if (installedVersion != PostgreSqlSchemaVersion)
			throw new InvalidOperationException(
				$"AssetPilot PostgreSQL schema version {installedVersion} is not supported by this build (expected {PostgreSqlSchemaVersion}).");
	}
}
