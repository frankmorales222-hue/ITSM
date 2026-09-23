using System.IO.Compression;
using System.Xml.Linq;
using AssetPilot.Application.Assets;
using AssetPilot.Infrastructure.Assets;
using AssetPilot.Infrastructure.Auditing;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Xunit;

namespace AssetPilot.IntegrationTests;

public sealed class InventoryRoundTripTests
{
	[Fact]
	public async Task Workbook_import_is_deduplicated_and_export_round_trips_one_row_per_asset()
	{
		string templatePath = Path.Combine(
			AppContext.BaseDirectory,
			"SeedData",
			"Asset inventory US.xlsx");
		string exportTemplatePath = Path.Combine(
			AppContext.BaseDirectory,
			"SeedData",
			"Asset inventory US template.xlsx");
		Assert.True(File.Exists(templatePath), templatePath);
		Assert.True(File.Exists(exportTemplatePath), exportTemplatePath);

		await using var connection = new SqliteConnection("Data Source=:memory:");
		await connection.OpenAsync();
		var options = new DbContextOptionsBuilder<AssetPilotDbContext>()
			.UseSqlite(connection)
			.Options;
		await using var db = new AssetPilotDbContext(options);
		await db.Database.EnsureCreatedAsync();
		var importer = new AssetImportService(db, new AuditService(db));

		await using (FileStream first = File.OpenRead(templatePath))
		{
			var result = await importer.ImportAsync(
				first, Path.GetFileName(templatePath), false, null, "test-first");
			Assert.Equal(327, result.Created);
			Assert.Equal(8, result.Skipped);
			Assert.Equal(6, result.Rejected);
		}
		Assert.Equal(327, await db.Assets.CountAsync());

		await using (FileStream second = File.OpenRead(templatePath))
		{
			var result = await importer.ImportAsync(
				second, Path.GetFileName(templatePath), false, null, "test-second");
			Assert.Equal(0, result.Created);
			Assert.Equal(8, result.Updated);
			Assert.Equal(327, result.Skipped);
			Assert.Equal(6, result.Rejected);
		}
		Assert.Equal(327, await db.Assets.CountAsync());
		Assert.Equal(335, await db.AssetImportReviews.CountAsync());

		await using (FileStream third = File.OpenRead(templatePath))
		{
			var result = await importer.ImportAsync(
				third, Path.GetFileName(templatePath), false, null, "test-third");
			Assert.Equal(0, result.Created);
			Assert.Equal(335, result.Skipped);
			Assert.Equal(6, result.Rejected);
		}
		Assert.Equal(327, await db.Assets.CountAsync());
		Assert.Equal(335, await db.AssetImportReviews.CountAsync());

		var exporter = new InventoryAuditExportService(db);
		await using MemoryStream output = await exporter.ExportAsync(exportTemplatePath);
		string? verificationPath = Environment.GetEnvironmentVariable("ASSETPILOT_EXPORT_VERIFY_PATH");
		if (!string.IsNullOrWhiteSpace(verificationPath))
		{
			Directory.CreateDirectory(Path.GetDirectoryName(verificationPath)!);
			await File.WriteAllBytesAsync(verificationPath, output.ToArray());
		}
		using var archive = new ZipArchive(output, ZipArchiveMode.Read, leaveOpen: true);
		using Stream sheetStream = archive.GetEntry("xl/worksheets/sheet1.xml")!.Open();
		XDocument sheet = XDocument.Load(sheetStream);
		XNamespace ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
		Assert.Equal(328, sheet.Descendants(ns + "row").Count());
		Assert.Equal(36, sheet.Descendants(ns + "row").Skip(1).First().Elements(ns + "c").Count());
	}

	[Fact]
	public async Task Repeat_import_fills_missing_monitor_fields_without_overwriting_existing_values()
	{
		string workbookPath = Path.Combine(AppContext.BaseDirectory, "SeedData", "Asset inventory US.xlsx");
		await using var connection = new SqliteConnection("Data Source=:memory:");
		await connection.OpenAsync();
		var options = new DbContextOptionsBuilder<AssetPilotDbContext>().UseSqlite(connection).Options;
		await using var db = new AssetPilotDbContext(options);
		await db.Database.EnsureCreatedAsync();
		var importer = new AssetImportService(db, new AuditService(db));

		await using (FileStream first = File.OpenRead(workbookPath))
		{
			await importer.ImportAsync(first, Path.GetFileName(workbookPath), false, null, "monitor-initial");
		}

		var asset = await db.Assets.FirstAsync(x =>
			x.Monitor1AssetTag != null && x.Monitor1SerialNumber != null
			&& x.Monitor2AssetTag != null && x.Monitor2SerialNumber != null
			&& x.Monitor3AssetTag != null && x.Monitor3SerialNumber != null);
		string expectedMonitor1Tag = asset.Monitor1AssetTag!;
		string expectedMonitor1Serial = asset.Monitor1SerialNumber!;
		string expectedMonitor2Tag = asset.Monitor2AssetTag!;
		string expectedMonitor2Serial = asset.Monitor2SerialNumber!;
		string expectedMonitor3Tag = asset.Monitor3AssetTag!;
		string expectedMonitor3Serial = asset.Monitor3SerialNumber!;
		asset.Monitor1AssetTag = null;
		asset.Monitor1SerialNumber = null;
		asset.Monitor2AssetTag = null;
		asset.Monitor2SerialNumber = null;
		asset.Monitor3AssetTag = null;
		asset.Monitor3SerialNumber = null;
		await db.SaveChangesAsync();

		await using FileStream second = File.OpenRead(workbookPath);
		AssetImportResult result = await importer.ImportAsync(
			second, Path.GetFileName(workbookPath), false, null, "monitor-repeat");

		Assert.True(result.Updated > 0);
		Assert.Equal(expectedMonitor1Tag, asset.Monitor1AssetTag);
		Assert.Equal(expectedMonitor1Serial, asset.Monitor1SerialNumber);
		Assert.Equal(expectedMonitor2Tag, asset.Monitor2AssetTag);
		Assert.Equal(expectedMonitor2Serial, asset.Monitor2SerialNumber);
		Assert.Equal(expectedMonitor3Tag, asset.Monitor3AssetTag);
		Assert.Equal(expectedMonitor3Serial, asset.Monitor3SerialNumber);
	}

	[Fact]
	public async Task Startup_import_treats_archived_identifiers_as_duplicates()
	{
		string workbookPath = Path.Combine(AppContext.BaseDirectory, "SeedData", "Asset inventory US.xlsx");
		await using var connection = new SqliteConnection("Data Source=:memory:");
		await connection.OpenAsync();
		var options = new DbContextOptionsBuilder<AssetPilotDbContext>().UseSqlite(connection).Options;
		await using var db = new AssetPilotDbContext(options);
		await db.Database.EnsureCreatedAsync();
		var importer = new AssetImportService(db, new AuditService(db));

		await using (FileStream first = File.OpenRead(workbookPath))
		{
			await importer.ImportAsync(first, Path.GetFileName(workbookPath), false, null, "initial-import");
		}
		var archived = await db.Assets.OrderBy(x => x.AssetId).FirstAsync();
		archived.IsArchived = true;
		await db.SaveChangesAsync();

		await using FileStream second = File.OpenRead(workbookPath);
		AssetImportResult result = await importer.ImportAsync(
			second, Path.GetFileName(workbookPath), false, null, "startup-inventory-seed");

		Assert.Equal(0, result.Created);
		Assert.Equal(8, result.Updated);
		Assert.Equal(327, result.Skipped);
		Assert.Equal(327, await db.Assets.CountAsync());
	}

	[Fact]
	public void Canonical_template_has_the_exact_sheet_and_36_headers()
	{
		string templatePath = Path.Combine(
			AppContext.BaseDirectory,
			"SeedData",
			"Asset inventory US template.xlsx");
		using var archive = ZipFile.OpenRead(templatePath);
		using Stream workbookStream = archive.GetEntry("xl/workbook.xml")!.Open();
		XDocument workbook = XDocument.Load(workbookStream);
		XNamespace spreadsheet = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
		Assert.Equal(
			InventoryWorkbookFormat.SheetName,
			(string?)workbook.Descendants(spreadsheet + "sheet").Single().Attribute("name"));

		List<string> sharedStrings;
		using (Stream sharedStringsStream = archive.GetEntry("xl/sharedStrings.xml")!.Open())
		{
			XDocument shared = XDocument.Load(sharedStringsStream);
			sharedStrings = shared
				.Descendants(spreadsheet + "si")
				.Select(item => string.Concat(item.Descendants(spreadsheet + "t").Select(text => text.Value)))
				.ToList();
		}
		using Stream sheetStream = archive.GetEntry("xl/worksheets/sheet1.xml")!.Open();
		XDocument sheet = XDocument.Load(sheetStream);
		List<string> headers = sheet
			.Descendants(spreadsheet + "row")
			.First()
			.Elements(spreadsheet + "c")
			.Select(cell => (string?)cell.Attribute("t") switch
			{
				"inlineStr" => string.Concat(cell.Descendants(spreadsheet + "t").Select(text => text.Value)),
				"str" => cell.Element(spreadsheet + "v")?.Value ?? "",
				_ => sharedStrings[int.Parse(cell.Element(spreadsheet + "v")!.Value)]
			})
			.ToList();
		Assert.True(InventoryWorkbookFormat.HasExactHeaders(headers));
	}

	[Fact]
	public async Task Import_rejects_a_workbook_with_a_renamed_template_header()
	{
		string sourcePath = Path.Combine(
			AppContext.BaseDirectory,
			"SeedData",
			"Asset inventory US.xlsx");
		var altered = new MemoryStream();
		await using (FileStream source = File.OpenRead(sourcePath))
		{
			await source.CopyToAsync(altered);
		}
		altered.Position = 0;
		using (var archive = new ZipArchive(altered, ZipArchiveMode.Update, leaveOpen: true))
		{
			ZipArchiveEntry sharedEntry = archive.GetEntry("xl/sharedStrings.xml")!;
			XDocument shared;
			using (Stream input = sharedEntry.Open())
			{
				shared = XDocument.Load(input);
			}
			XNamespace ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
			XElement assetTypeHeader = shared
				.Descendants(ns + "si")
				.Single(item =>
					string.Concat(item.Descendants(ns + "t").Select(text => text.Value))
					== "Asset Type");
			assetTypeHeader.Descendants(ns + "t").First().Value = "Renamed Asset Type";
			sharedEntry.Delete();
			using Stream output = archive.CreateEntry("xl/sharedStrings.xml").Open();
			shared.Save(output);
		}
		altered.Position = 0;

		await using var connection = new SqliteConnection("Data Source=:memory:");
		await connection.OpenAsync();
		var options = new DbContextOptionsBuilder<AssetPilotDbContext>()
			.UseSqlite(connection)
			.Options;
		await using var db = new AssetPilotDbContext(options);
		await db.Database.EnsureCreatedAsync();
		var importer = new AssetImportService(db, new AuditService(db));

		var result = await importer.ImportAsync(
			altered,
			"wrong-format.xlsx",
			false,
			null,
			"test-wrong-template");

		Assert.Equal(0, result.Created);
		Assert.Equal(341, result.Rejected);
		Assert.Contains(
			result.Messages,
			message => message.Contains("does not match", StringComparison.OrdinalIgnoreCase));
		Assert.Empty(db.Assets);
	}
}
