using Microsoft.AspNetCore.Hosting;
using Microsoft.AspNetCore.Mvc.Testing;
using Xunit;

namespace AssetPilot.IntegrationTests;

public sealed class HealthEndpointTests : IClassFixture<HealthEndpointTests.AssetPilotFactory>
{
	private readonly HttpClient client;

	public HealthEndpointTests(AssetPilotFactory factory)
	{
		client = factory.CreateClient();
	}

	[Fact]
	public async Task Health_endpoint_returns_success()
	{
		using HttpResponseMessage response = await client.GetAsync("/health");
		response.EnsureSuccessStatusCode();
		string body = await response.Content.ReadAsStringAsync();
		Assert.Contains("\"status\":\"Healthy\"", body);
		Assert.Contains("\"version\":\"3.7.0\"", body);
	}

	public sealed class AssetPilotFactory : WebApplicationFactory<Program>
	{
		private readonly string databasePath = Path.Combine(
			Path.GetTempPath(),
			$"assetpilot-health-{Guid.NewGuid():N}.db");

		protected override void ConfigureWebHost(IWebHostBuilder builder)
		{
			builder.UseSetting("Database:Path", databasePath);
			builder.UseSetting("Import:SeedExistingInventory", "false");
		}

		protected override void Dispose(bool disposing)
		{
			base.Dispose(disposing);
			if (!disposing)
			{
				return;
			}
			foreach (string path in new[] { databasePath, databasePath + "-shm", databasePath + "-wal" })
			{
				try
				{
					if (File.Exists(path))
					{
						File.Delete(path);
					}
				}
				catch (IOException)
				{
					// The operating system will clear remaining test temp files.
				}
			}
		}
	}
}

