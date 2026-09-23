using System.Security.Claims;
using System.Reflection;
using AssetPilot.Application.Shipments;
using AssetPilot.Domain.Assets;
using AssetPilot.Domain.People;
using AssetPilot.Domain.Operations;
using AssetPilot.Domain.Shipments;
using AssetPilot.Infrastructure.Assets;
using AssetPilot.Infrastructure.Auditing;
using AssetPilot.Infrastructure.Persistence;
using AssetPilot.Web.Pages.Employees;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Authorization.Policy;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.AspNetCore.Mvc.ViewFeatures;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.FileProviders;
using Microsoft.Extensions.Hosting;
using Microsoft.Extensions.Configuration;
using Xunit;

namespace AssetPilot.IntegrationTests;

public sealed class PhaseThreeBehaviorTests
{
	[Fact]
	public void Security_forms_do_not_require_fields_from_other_actions()
	{
		Type modelType = typeof(AssetPilot.Web.Pages.Security.IndexModel);
		var nullability = new NullabilityInfoContext();
		string[] actionSpecificFields =
		[
			"UserId",
			"RoleName",
			"NewRoleName",
			"NewUserDisplayName",
			"NewUserEmail",
			"NewUserPassword",
			"NewUserRoleName"
		];

		foreach (string field in actionSpecificFields)
		{
			var property = modelType.GetProperty(field);
			Assert.NotNull(property);
			Assert.Equal(NullabilityState.Nullable, nullability.Create(property).WriteState);
		}
	}

	[Fact]
	public async Task Shipment_list_uses_carrier_website_when_api_credentials_are_missing()
	{
		await using var database = await TestDatabase.CreateAsync();
		database.Db.Shipments.Add(new Shipment
		{
			ShipmentNumber = "SHP-PUBLIC-TRACKING",
			Direction = "Outgoing",
			Status = "Shipped",
			Carrier = "UPS",
			TrackingNumber = "1Z TEST 123",
			CreatedUtc = DateTime.UtcNow,
			ModifiedUtc = DateTime.UtcNow
		});
		await database.Db.SaveChangesAsync();
		var configuration = new ConfigurationBuilder()
			.AddInMemoryCollection(new Dictionary<string, string?>())
			.Build();
		var model = new AssetPilot.Web.Pages.Shipments.IndexModel(database.Db, configuration);

		await model.OnGetAsync(CancellationToken.None);

		var row = Assert.Single(model.Shipments);
		Assert.False(row.CanAutoUpdate);
		Assert.Equal("UPS", row.CarrierDisplayName);
		Assert.Equal("https://www.ups.com/track?tracknum=1Z%20TEST%20123", row.PublicTrackingUrl);
	}

	[Fact]
	public async Task Shipment_list_enables_automatic_updates_for_admin_configured_credentials()
	{
		await using var database = await TestDatabase.CreateAsync();
		database.Db.Shipments.Add(new Shipment
		{
			ShipmentNumber = "SHP-AUTO-TRACKING",
			Direction = "Outgoing",
			Status = "Shipped",
			Carrier = "UPS",
			TrackingNumber = "1ZAUTO123",
			CreatedUtc = DateTime.UtcNow,
			ModifiedUtc = DateTime.UtcNow
		});
		database.Db.SystemSettings.AddRange(
			new SystemSetting
			{
				SettingKey = "Tracking.UPS.ClientId",
				Value = "encrypted-client-id",
				Description = "Encrypted UPS tracking API client ID.",
				IsSensitive = true,
				CreatedUtc = DateTime.UtcNow,
				ModifiedUtc = DateTime.UtcNow
			},
			new SystemSetting
			{
				SettingKey = "Tracking.UPS.ClientSecret",
				Value = "encrypted-client-secret",
				Description = "Encrypted UPS tracking API client secret.",
				IsSensitive = true,
				CreatedUtc = DateTime.UtcNow,
				ModifiedUtc = DateTime.UtcNow
			});
		await database.Db.SaveChangesAsync();
		var configuration = new ConfigurationBuilder().Build();
		var model = new AssetPilot.Web.Pages.Shipments.IndexModel(database.Db, configuration);

		await model.OnGetAsync(CancellationToken.None);

		Assert.True(Assert.Single(model.Shipments).CanAutoUpdate);
	}

	[Fact]
	public async Task Create_shipment_from_asset_preselects_that_asset()
	{
		await using var database = await TestDatabase.CreateAsync();
		var asset = new Asset
		{
			AssetTag = "SHIP-LAP-1",
			Hostname = "HOU-SHIP-LAP-1",
			SerialNumber = "SERIAL-SHIP-1",
			Name = "Laptop",
			Status = "Active",
			Condition = "Good",
			Category = "Computer",
			AssetType = "Laptop",
			Location = "Houston",
			CreatedUtc = DateTime.UtcNow,
			ModifiedUtc = DateTime.UtcNow
		};
		database.Db.Assets.Add(asset);
		await database.Db.SaveChangesAsync();
		var model = new AssetPilot.Web.Pages.Shipments.CreateModel(
			database.Db,
			new AuditService(database.Db));
		AttachPageContext(model);

		var result = await model.OnGetAsync(asset.AssetId, CancellationToken.None);

		Assert.IsType<PageResult>(result);
		Assert.Equal(asset.AssetId, Assert.Single(model.AssetIds));
		Assert.Equal(asset.AssetTag, Assert.Single(model.Assets).AssetTag);
	}

	[Fact]
	public async Task Asset_search_is_partial_case_insensitive_and_covers_peripheral_fields()
	{
		await using var database = await TestDatabase.CreateAsync();
		database.Db.Assets.AddRange(
			new Asset
			{
				AssetTag = "LAP-100",
				Hostname = "HOU-LAPTOP-100",
				Name = "Laptop",
				Status = "Active",
				Condition = "Good",
				Category = "Computer",
				AssetType = "Laptop",
				Headset = "Plantronics Voyager",
				CreatedUtc = DateTime.UtcNow,
				ModifiedUtc = DateTime.UtcNow
			},
			new Asset
			{
				AssetTag = "LAP-200",
				Hostname = "HOU-LAPTOP-200",
				Name = "Laptop",
				Status = "In Stock",
				Condition = "Good",
				Category = "Computer",
				AssetType = "Laptop",
				CreatedUtc = DateTime.UtcNow,
				ModifiedUtc = DateTime.UtcNow
			});
		await database.Db.SaveChangesAsync();

		var model = new AssetPilot.Web.Pages.Assets.IndexModel(
			database.Db,
			new InventoryAuditExportService(database.Db),
			new AllowAuthorizationService(),
			new TestHostEnvironment())
		{
			Query = "vOyAg"
		};
		await model.OnGetAsync(CancellationToken.None);

		Asset result = Assert.Single(model.Assets);
		Assert.Equal("LAP-100", result.AssetTag);
	}

	[Fact]
	public async Task Active_employee_is_protected_and_disabled_employee_can_be_deleted()
	{
		await using var database = await TestDatabase.CreateAsync();
		var employee = new Employee
		{
			EmployeeNumber = "E-100",
			DisplayName = "Protected Employee",
			Email = "protected@example.test",
			IsActive = true,
			CreatedUtc = DateTime.UtcNow,
			ModifiedUtc = DateTime.UtcNow
		};
		database.Db.Employees.Add(employee);
		await database.Db.SaveChangesAsync();

		var model = new IndexModel(
			database.Db,
			new AuditService(database.Db),
			new AllowAuthorizationService());
		AttachPageContext(model);

		await model.OnPostDeleteAsync(employee.EmployeeId, CancellationToken.None);
		Assert.False(employee.IsDeleted);

		employee.IsActive = false;
		await database.Db.SaveChangesAsync();
		await model.OnPostDeleteAsync(employee.EmployeeId, CancellationToken.None);
		Assert.True(employee.IsDeleted);
		Assert.Single(database.Db.AuditEvents.Where(x => x.EventTypeCode == "Employee.Deleted"));
	}

	[Fact]
	public async Task Employee_search_is_partial_and_case_insensitive_across_employee_fields()
	{
		await using var database = await TestDatabase.CreateAsync();
		database.Db.Employees.AddRange(
			new Employee
			{
				EmployeeNumber = "E-ALL-1",
				DisplayName = "Allison Parker",
				Email = "allison@example.test",
				Department = "Accounting",
				Location = "Houston",
				IsActive = true,
				CreatedUtc = DateTime.UtcNow,
				ModifiedUtc = DateTime.UtcNow
			},
			new Employee
			{
				EmployeeNumber = "E-OTHER-1",
				DisplayName = "Other Person",
				Email = "other@example.test",
				IsActive = true,
				CreatedUtc = DateTime.UtcNow,
				ModifiedUtc = DateTime.UtcNow
			});
		await database.Db.SaveChangesAsync();

		var model = new IndexModel(
			database.Db,
			new AuditService(database.Db),
			new AllowAuthorizationService())
		{
			Query = "aLLis"
		};
		await model.OnGetAsync(CancellationToken.None);

		Assert.Equal("Allison Parker", Assert.Single(model.Employees).Name);
	}

	[Fact]
	public async Task Assigning_and_returning_an_asset_updates_available_stock_immediately()
	{
		await using var database = await TestDatabase.CreateAsync();
		var employee = new Employee
		{
			EmployeeNumber = "E-STOCK-1",
			DisplayName = "Stock User",
			Email = "stock.user@example.test",
			Location = "Houston",
			IsActive = true,
			CreatedUtc = DateTime.UtcNow,
			ModifiedUtc = DateTime.UtcNow
		};
		var asset = new Asset
		{
			AssetTag = "STOCK-LAP-1",
			Hostname = "STOCK-LAP-1",
			Name = "Available laptop",
			Status = "In Stock",
			Condition = "Good",
			Category = "Computer",
			AssetType = "Laptop",
			Location = "Houston",
			CurrentLocation = "Houston",
			CreatedUtc = DateTime.UtcNow,
			ModifiedUtc = DateTime.UtcNow
		};
		database.Db.AddRange(employee, asset);
		await database.Db.SaveChangesAsync();
		var details = new AssetPilot.Web.Pages.Assets.DetailsModel(
			database.Db,
			new AuditService(database.Db),
			new AllowAuthorizationService())
		{
			EmployeeId = employee.EmployeeId
		};
		AttachPageContext(details);

		await details.OnPostAssignAsync(asset.AssetId, CancellationToken.None);
		var stock = CreateStockModel(database.Db);
		await stock.OnGetAsync(CancellationToken.None);
		Assert.Equal(0, stock.TotalInStock);
		Assert.Equal("Active", asset.Status);
		Assert.Equal(employee.DisplayName, asset.AssignedTo);

		await details.OnPostReturnToStockAsync(asset.AssetId, CancellationToken.None);
		stock = CreateStockModel(database.Db);
		await stock.OnGetAsync(CancellationToken.None);
		Assert.Equal(1, stock.TotalInStock);
		Assert.Equal("In Stock", asset.Status);
		Assert.Null(asset.AssignedTo);
	}

	[Fact]
	public async Task Stock_threshold_alert_calculates_reorder_quantity()
	{
		await using var database = await TestDatabase.CreateAsync();
		for (int index = 1; index <= 4; index++)
		{
			database.Db.Assets.Add(new Asset
			{
				AssetTag = $"THRESHOLD-{index}",
				Name = "Laptop",
				Status = "In Stock",
				Condition = "Good",
				Category = "Computer",
				AssetType = "Laptop",
				Location = "Houston",
				CreatedUtc = DateTime.UtcNow,
				ModifiedUtc = DateTime.UtcNow
			});
		}
		database.Db.StockLevelTargets.Add(new StockLevelTarget
		{
			AssetType = "Laptop",
			Location = "Houston",
			TargetQuantity = 50,
			ThresholdPercent = 50,
			CreatedUtc = DateTime.UtcNow,
			ModifiedUtc = DateTime.UtcNow
		});
		await database.Db.SaveChangesAsync();

		var stock = CreateStockModel(database.Db);
		await stock.OnGetAsync(CancellationToken.None);

		var alert = Assert.Single(stock.Alerts);
		Assert.Equal(4, alert.Available);
		Assert.Equal(25, alert.AlertAt);
		Assert.Equal(46, alert.ReorderQuantity);
		Assert.Equal(8, alert.AvailablePercent);
	}

	[Fact]
	public async Task Asset_inventory_defaults_to_active_computers()
	{
		await using var database = await TestDatabase.CreateAsync();
		database.Db.Assets.AddRange(
			NewAsset("ACTIVE-LAP", "Active", "Laptop", "Laptop"),
			NewAsset("STOCK-LAP", "In Stock", "Laptop", "Laptop"),
			NewAsset("ACTIVE-PRINTER", "Active", "Printer", "Printer"));
		await database.Db.SaveChangesAsync();
		var model = new AssetPilot.Web.Pages.Assets.IndexModel(
			database.Db,
			new InventoryAuditExportService(database.Db),
			new AllowAuthorizationService(),
			new TestHostEnvironment());

		await model.OnGetAsync(CancellationToken.None);

		Assert.Equal("Active", model.Status);
		Assert.Equal("ACTIVE-LAP", Assert.Single(model.Assets).AssetTag);
	}

	[Fact]
	public async Task Dashboard_reports_detailed_equipment_categories()
	{
		await using var database = await TestDatabase.CreateAsync();
		Asset laptop = NewAsset("DASH-LAP", "Active", "Laptop", "Laptop");
		laptop.Monitor1SerialNumber = "ASSOCIATED-MONITOR";
		laptop.DockingStation = "ASSOCIATED-DOCK";
		database.Db.Assets.AddRange(
			laptop,
			NewAsset("DASH-MAC", "In Stock", "MacBook", "MacBook"),
			NewAsset("DASH-MON-1", "In Stock", "Monitor", "Monitor"),
			NewAsset("DASH-MON-2", "Repair", "Monitor", "Monitor"),
			NewAsset("DASH-DOCK", "In Stock", "Docking Station", "Docking Station"));
		await database.Db.SaveChangesAsync();
		var dashboard = new AssetPilot.Web.Pages.IndexModel(database.Db);

		await dashboard.OnGetAsync(CancellationToken.None);

		Assert.Equal(1, dashboard.EquipmentInventory.Single(x => x.Label == "Laptops").Total);
		Assert.Equal(1, dashboard.EquipmentInventory.Single(x => x.Label == "MacBooks").Available);
		Assert.Equal(3, dashboard.EquipmentInventory.Single(x => x.Label == "Monitors").Total);
		Assert.Equal(1, dashboard.EquipmentInventory.Single(x => x.Label == "Monitors").Attention);
		Assert.Equal(2, dashboard.EquipmentInventory.Single(x => x.Label == "Docking stations").Total);
	}

	[Fact]
	public async Task Stock_matrix_groups_by_workstation_classification_and_status()
	{
		await using var database = await TestDatabase.CreateAsync();
		database.Db.Assets.AddRange(
			NewAsset("MATRIX-ACTIVE", "Active", "Computer", "Desktop"),
			NewAsset("MATRIX-STOCK", "In Stock", "Computer", "Desktop"),
			NewAsset("MATRIX-REPAIR", "Repair", "Computer", "Desktop"),
			NewAsset("MATRIX-LOST", "Lost", "Computer", "Desktop"));
		await database.Db.SaveChangesAsync();
		var stock = CreateStockModel(database.Db);

		await stock.OnGetAsync(CancellationToken.None);

		var desktop = Assert.Single(stock.InventoryMatrix);
		Assert.Equal("Desktop", desktop.AssetType);
		Assert.Equal(1, desktop.Allocated);
		Assert.Equal(1, desktop.InStock);
		Assert.Equal(1, desktop.UnderRepair);
		Assert.Equal(1, desktop.Lost);
		Assert.Equal(4, desktop.GrandTotal);
	}

	[Fact]
	public async Task Stock_planning_automatically_includes_every_inventory_classification()
	{
		await using var database = await TestDatabase.CreateAsync();
		database.Db.Assets.AddRange(
			NewAsset("AUTO-DESKTOP", "Active", "Computer", "Desktop"),
			NewAsset("AUTO-PRINTER", "In Stock", "Peripheral", "Printer"));
		await database.Db.SaveChangesAsync();
		var stock = CreateStockModel(database.Db);

		await stock.OnGetAsync(CancellationToken.None);

		Assert.Equal(new[] { "Desktop", "Printer" }, stock.InventoryMatrix.Select(row => row.AssetType));
		Assert.Equal(new[] { "Desktop", "Printer" }, stock.Targets.Select(row => row.AssetType));
		Assert.Equal("Desktop", Assert.Single(stock.Alerts).AssetType);
		Assert.Equal(0, stock.Alerts[0].Available);
		Assert.Equal(1, stock.Alerts[0].TargetQuantity);
	}

	[Fact]
	public async Task Available_stock_delete_archives_only_an_unassigned_in_stock_asset()
	{
		await using var database = await TestDatabase.CreateAsync();
		Asset asset = NewAsset("DELETE-STOCK", "In Stock", "Laptop", "Laptop");
		database.Db.Assets.Add(asset);
		await database.Db.SaveChangesAsync();
		var stock = CreateStockModel(database.Db);

		await stock.OnPostDeleteAssetAsync(asset.AssetId, CancellationToken.None);

		Assert.True(asset.IsArchived);
		Assert.Single(database.Db.AuditEvents.Where(x => x.EventTypeCode == "Inventory.StockAssetDeleted"));
	}

	[Fact]
	public async Task Master_data_opens_without_false_validation_and_searches_case_insensitively()
	{
		await using var database = await TestDatabase.CreateAsync();
		database.Db.ReferenceDataItems.Add(new AssetPilot.Domain.MasterData.ReferenceDataItem
		{
			Kind = "Location",
			Name = "Houston Office",
			Code = "HOU",
			IsActive = true,
			CreatedUtc = DateTime.UtcNow,
			ModifiedUtc = DateTime.UtcNow
		});
		await database.Db.SaveChangesAsync();
		var model = new AssetPilot.Web.Pages.Administration.MasterData.IndexModel(
			database.Db,
			new AuditService(database.Db),
			new AllowAuthorizationService())
		{
			Kind = "Location",
			Query = "hOuStOn"
		};
		AttachPageContext(model);

		await model.OnGetAsync(CancellationToken.None);

		Assert.True(model.ModelState.IsValid);
		Assert.Equal("Houston Office", Assert.Single(model.Items).Name);
	}

	[Fact]
	public async Task Clearing_tracking_removes_only_tracking_information()
	{
		await using var database = await TestDatabase.CreateAsync();
		var shipment = new Shipment
		{
			ShipmentNumber = "SHP-TEST-1",
			Direction = "Outgoing",
			Status = "Shipped",
			Carrier = "UPS",
			TrackingNumber = "1ZTEST",
			TrackingLastCheckedUtc = DateTime.UtcNow,
			TrackingLastMessage = "In transit",
			TrackingUrl = "https://example.test/tracking",
			ExpectedDate = DateOnly.FromDateTime(DateTime.Today.AddDays(2)),
			CreatedUtc = DateTime.UtcNow,
			ModifiedUtc = DateTime.UtcNow
		};
		shipment.TrackingEvents.Add(new ShipmentTrackingEvent
		{
			EventUtc = DateTime.UtcNow,
			Status = "In transit",
			Source = "UPS"
		});
		database.Db.Shipments.Add(shipment);
		await database.Db.SaveChangesAsync();

		var model = new AssetPilot.Web.Pages.Shipments.DetailsModel(
			database.Db,
			new AuditService(database.Db),
			new AllowAuthorizationService(),
			new UnusedTrackingService());
		AttachPageContext(model);
		await model.OnPostClearTrackingAsync(shipment.ShipmentId, CancellationToken.None);

		Assert.Equal("UPS", shipment.Carrier);
		Assert.Equal("Shipped", shipment.Status);
		Assert.Null(shipment.TrackingNumber);
		Assert.Null(shipment.TrackingLastCheckedUtc);
		Assert.Null(shipment.TrackingLastMessage);
		Assert.Null(shipment.TrackingUrl);
		Assert.Null(shipment.ExpectedDate);
		Assert.Empty(database.Db.ShipmentTrackingEvents);
		Assert.Single(database.Db.AuditEvents.Where(x => x.EventTypeCode == "Shipment.TrackingCleared"));
	}

	[Fact]
	public async Task Deleting_an_active_shipment_archives_it_and_releases_its_asset()
	{
		await using var database = await TestDatabase.CreateAsync();
		var asset = new Asset
		{
			AssetTag = "DELETE-SHIP-ASSET",
			Name = "Laptop",
			Status = "Shipped",
			Condition = "Good",
			Category = "Computer",
			AssetType = "Laptop",
			CreatedUtc = DateTime.UtcNow,
			ModifiedUtc = DateTime.UtcNow
		};
		var shipment = new Shipment
		{
			ShipmentNumber = "SHP-DELETE-1",
			Direction = "Outgoing",
			Status = "Shipped",
			CreatedUtc = DateTime.UtcNow,
			ModifiedUtc = DateTime.UtcNow
		};
		shipment.Items.Add(new ShipmentItem { Asset = asset, ConditionAtDispatch = "Good" });
		database.Db.Shipments.Add(shipment);
		await database.Db.SaveChangesAsync();
		var model = new AssetPilot.Web.Pages.Shipments.DetailsModel(
			database.Db,
			new AuditService(database.Db),
			new AllowAuthorizationService(),
			new UnusedTrackingService());
		AttachPageContext(model);

		await model.OnPostDeleteAsync(shipment.ShipmentId, CancellationToken.None);

		Assert.True(shipment.IsArchived);
		Assert.Equal("In Stock", asset.Status);
		Assert.Single(database.Db.AuditEvents.Where(x => x.EventTypeCode == "Shipment.Deleted"));
	}

	[Fact]
	public async Task Audit_service_serializes_tracked_entities_without_navigation_cycles()
	{
		await using var database = await TestDatabase.CreateAsync();
		var asset = new Asset
		{
			AssetTag = "AUDIT-CYCLE-1",
			Name = "Audit cycle test",
			Status = "In Stock",
			Condition = "Good",
			Category = "Computer",
			AssetType = "Laptop",
			CreatedUtc = DateTime.UtcNow,
			ModifiedUtc = DateTime.UtcNow
		};
		asset.StatusHistory.Add(new AssetStatusHistory
		{
			ToStatus = "In Stock",
			ChangedUtc = DateTime.UtcNow,
			Reason = "Created"
		});
		database.Db.Assets.Add(asset);
		await database.Db.SaveChangesAsync();

		var audit = new AuditService(database.Db);
		await audit.WriteAsync(
			"Asset.Created",
			"Asset",
			asset.AssetId.ToString(),
			"test-user",
			null,
			asset,
			null,
			"audit-cycle-test");

		string afterJson = Assert.Single(database.Db.AuditEvents).AfterJson!;
		Assert.Contains("AUDIT-CYCLE-1", afterJson);
	}

	private static void AttachPageContext(PageModel model)
	{
		var http = new DefaultHttpContext
		{
			User = new ClaimsPrincipal(
				new ClaimsIdentity(
					new[] { new Claim(ClaimTypes.NameIdentifier, "phase-three-test") },
					"Test"))
		};
		model.PageContext = new PageContext { HttpContext = http };
		model.TempData = new TempDataDictionary(http, new TestTempDataProvider());
	}

	private static Asset NewAsset(string tag, string status, string assetType, string workstation) => new()
	{
		AssetTag = tag,
		Name = tag,
		Status = status,
		Condition = "Good",
		Category = "Computer",
		AssetType = assetType,
		Workstation = workstation,
		CreatedUtc = DateTime.UtcNow,
		ModifiedUtc = DateTime.UtcNow
	};

	private static AssetPilot.Web.Pages.Assets.StockModel CreateStockModel(AssetPilotDbContext db)
	{
		var model = new AssetPilot.Web.Pages.Assets.StockModel(
			db,
			new InventoryAuditExportService(db),
			new AuditService(db),
			new AllowAuthorizationService(),
			new TestHostEnvironment());
		AttachPageContext(model);
		return model;
	}

	private sealed class AllowAuthorizationService : IAuthorizationService
	{
		public Task<AuthorizationResult> AuthorizeAsync(
			ClaimsPrincipal user,
			object? resource,
			IEnumerable<IAuthorizationRequirement> requirements) =>
			Task.FromResult(AuthorizationResult.Success());

		public Task<AuthorizationResult> AuthorizeAsync(
			ClaimsPrincipal user,
			object? resource,
			string policyName) =>
			Task.FromResult(AuthorizationResult.Success());
	}

	private sealed class UnusedTrackingService : IShipmentTrackingService
	{
		public Task<ShipmentTrackingResult> GetUpdateAsync(
			string carrier,
			string trackingNumber,
			CancellationToken cancellationToken = default) =>
			throw new NotSupportedException();
	}

	private sealed class TestTempDataProvider : ITempDataProvider
	{
		public IDictionary<string, object> LoadTempData(HttpContext context) =>
			new Dictionary<string, object>();

		public void SaveTempData(HttpContext context, IDictionary<string, object> values)
		{
		}
	}

	private sealed class TestHostEnvironment : IHostEnvironment
	{
		public string EnvironmentName { get; set; } = "Test";

		public string ApplicationName { get; set; } = "AssetPilot.Tests";

		public string ContentRootPath { get; set; } = AppContext.BaseDirectory;

		public IFileProvider ContentRootFileProvider { get; set; } = new NullFileProvider();
	}

	private sealed class TestDatabase : IAsyncDisposable
	{
		private readonly SqliteConnection connection;

		private TestDatabase(SqliteConnection connection, AssetPilotDbContext db)
		{
			this.connection = connection;
			Db = db;
		}

		public AssetPilotDbContext Db { get; }

		public static async Task<TestDatabase> CreateAsync()
		{
			var connection = new SqliteConnection("Data Source=:memory:");
			await connection.OpenAsync();
			var db = new AssetPilotDbContext(
				new DbContextOptionsBuilder<AssetPilotDbContext>()
					.UseSqlite(connection)
					.Options);
			await db.Database.EnsureCreatedAsync();
			return new TestDatabase(connection, db);
		}

		public async ValueTask DisposeAsync()
		{
			await Db.DisposeAsync();
			await connection.DisposeAsync();
		}
	}
}
