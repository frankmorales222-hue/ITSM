using System.Data.Common;
using System.Threading;
using System.Threading.Tasks;
using Microsoft.EntityFrameworkCore.Diagnostics;

namespace AssetPilot.Infrastructure.Persistence;

public sealed class SqlitePragmaConnectionInterceptor : DbConnectionInterceptor
{
	private const string ConnectionPragmas = "PRAGMA foreign_keys = ON;\nPRAGMA busy_timeout = 5000;";

	public override void ConnectionOpened(DbConnection connection, ConnectionEndEventData eventData)
	{
		ApplyPragmas(connection);
		base.ConnectionOpened(connection, eventData);
	}

	public override async Task ConnectionOpenedAsync(DbConnection connection, ConnectionEndEventData eventData, CancellationToken cancellationToken = default(CancellationToken))
	{
		await ApplyPragmasAsync(connection, cancellationToken);
		await base.ConnectionOpenedAsync(connection, eventData, cancellationToken);
	}

	private static void ApplyPragmas(DbConnection connection)
	{
		using DbCommand dbCommand = connection.CreateCommand();
		dbCommand.CommandText = "PRAGMA foreign_keys = ON;\nPRAGMA busy_timeout = 5000;";
		dbCommand.ExecuteNonQuery();
	}

	private static async Task ApplyPragmasAsync(DbConnection connection, CancellationToken cancellationToken)
	{
		await using DbCommand command = connection.CreateCommand();
		command.CommandText = "PRAGMA foreign_keys = ON;\nPRAGMA busy_timeout = 5000;";
		await command.ExecuteNonQueryAsync(cancellationToken);
	}
}
