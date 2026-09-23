using AssetPilot.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace AssetPilot.IntegrationTests;

public sealed class PostgreSqlModelTests
{
    [Fact]
    public void PostgreSql_create_script_does_not_reference_sqlite_collations()
    {
        var options = new DbContextOptionsBuilder<AssetPilotDbContext>()
            .UseNpgsql("Host=127.0.0.1;Database=release_gate;Username=release_gate;Password=redacted")
            .Options;

        using var db = new AssetPilotDbContext(options);
        var createScript = db.Database.GenerateCreateScript();

        Assert.DoesNotContain("NOCASE", createScript, System.StringComparison.OrdinalIgnoreCase);
        Assert.Contains("assetpilot", createScript, System.StringComparison.OrdinalIgnoreCase);
    }
}
