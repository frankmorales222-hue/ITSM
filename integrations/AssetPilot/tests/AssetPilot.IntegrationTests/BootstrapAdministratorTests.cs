using System.Text.Json;
using AssetPilot.Infrastructure.Identity;
using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc.Testing;
using Microsoft.Extensions.DependencyInjection;
using Xunit;

namespace AssetPilot.IntegrationTests;

public sealed class BootstrapAdministratorTests : IClassFixture<BootstrapAdministratorTests.AssetPilotFactory>
{
    private readonly AssetPilotFactory factory;

    public BootstrapAdministratorTests(AssetPilotFactory factory)
    {
        this.factory = factory;
    }

    [Fact]
    public async Task One_time_bootstrap_creates_admin_and_deletes_credential_file()
    {
        using HttpClient client = factory.CreateClient();
        using HttpResponseMessage response = await client.GetAsync("/health");
        response.EnsureSuccessStatusCode();

        using IServiceScope scope = factory.Services.CreateScope();
        UserManager<ApplicationUser> users = scope.ServiceProvider.GetRequiredService<UserManager<ApplicationUser>>();
        ApplicationUser administrator = Assert.Single(users.Users);
        Assert.Equal("asset-admin@example.test", administrator.Email);
        Assert.Contains("Administrator", await users.GetRolesAsync(administrator));
        Assert.False(File.Exists(factory.CredentialPath));
    }

    public sealed class AssetPilotFactory : WebApplicationFactory<Program>
    {
        private readonly string databasePath = Path.Combine(
            Path.GetTempPath(), $"assetpilot-bootstrap-{Guid.NewGuid():N}.db");

        public string CredentialPath { get; } = Path.Combine(
            Path.GetTempPath(), $"assetpilot-bootstrap-{Guid.NewGuid():N}.json");

        public AssetPilotFactory()
        {
            File.WriteAllText(CredentialPath, JsonSerializer.Serialize(new
            {
                displayName = "Asset Administrator",
                email = "asset-admin@example.test",
                password = "AssetPilot!Bootstrap2026"
            }));
        }

        protected override void ConfigureWebHost(IWebHostBuilder builder)
        {
            builder.UseSetting("Database:Path", databasePath);
            builder.UseSetting("Import:SeedExistingInventory", "false");
            builder.UseSetting("Bootstrap:AdminCredentialFile", CredentialPath);
        }

        protected override void Dispose(bool disposing)
        {
            base.Dispose(disposing);
            if (!disposing) return;
            foreach (string path in new[]
            {
                databasePath, databasePath + "-shm", databasePath + "-wal", CredentialPath
            })
            {
                try { if (File.Exists(path)) File.Delete(path); }
                catch (IOException) { }
            }
        }
    }
}
