using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Claims;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Assets;
using AssetPilot.Application.Auditing;
using AssetPilot.Domain.Assets;
using AssetPilot.Domain.Operations;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Hosting;
using AssetPilot.Web.Services;

namespace AssetPilot.Web.Pages.Assets;

public sealed class StockModel(
	AssetPilotDbContext db,
	IInventoryAuditExportService exportService,
	IAuditService audit,
	IAuthorizationService authorization,
	IHostEnvironment environment) : PageModel
{
	public sealed record CountRow(string Label, int Count);
	public sealed record StockStatusRow(
		string AssetType,
		int Allocated,
		int InStock,
		int Lost,
		int UnderRepair,
		int Retired,
		int RecoveryPending)
	{
		public int GrandTotal => Allocated + InStock + Lost + UnderRepair + Retired + RecoveryPending;
	}
	public sealed record TargetRow(
		int Id,
		string AssetType,
		string Location,
		int TargetQuantity,
		int ThresholdPercent,
		int AlertAt,
		int Available,
		int ReorderQuantity)
	{
		public bool IsBelowThreshold => Available < AlertAt;
		public int AvailablePercent => TargetQuantity == 0
			? 0
			: (int)Math.Round(Available * 100m / TargetQuantity);
	}

	[BindProperty(SupportsGet = true)]
	public string? Query { get; set; }

	[BindProperty(SupportsGet = true)]
	public string? AssetType { get; set; }

	[BindProperty(SupportsGet = true)]
	public string? Location { get; set; }

	[BindProperty(SupportsGet = true)]
	public string? Condition { get; set; }

	[BindProperty]
	public int TargetId { get; set; }

	[BindProperty]
	public string TargetAssetType { get; set; } = "";

	[BindProperty]
	public string TargetLocation { get; set; } = "";

	[BindProperty]
	public int TargetQuantity { get; set; }

	[BindProperty]
	public int ThresholdPercent { get; set; } = 50;

	public IReadOnlyList<string> AssetTypes { get; private set; } = Array.Empty<string>();

	public IReadOnlyList<string> Locations { get; private set; } = Array.Empty<string>();

	public IReadOnlyList<string> Conditions { get; private set; } = Array.Empty<string>();

	public IReadOnlyList<Asset> Assets { get; private set; } = Array.Empty<Asset>();

	public IReadOnlyList<CountRow> ByType { get; private set; } = Array.Empty<CountRow>();

	public IReadOnlyList<CountRow> ByLocation { get; private set; } = Array.Empty<CountRow>();

	public IReadOnlyList<StockStatusRow> InventoryMatrix { get; private set; } = Array.Empty<StockStatusRow>();

	public StockStatusRow InventoryTotals { get; private set; } = new("Grand Total", 0, 0, 0, 0, 0, 0);

	public int TotalInStock { get; private set; }

	public IReadOnlyList<TargetRow> Targets { get; private set; } = Array.Empty<TargetRow>();

	public IReadOnlyList<TargetRow> Alerts => Targets.Where(x => x.IsBelowThreshold).ToList();

	public bool CanManageTargets { get; private set; }

	public async Task OnGetAsync(CancellationToken cancellationToken)
	{
		await StockTargetSynchronizer.EnsureInventoryTypesAsync(db, cancellationToken);
		CanManageTargets = (await authorization.AuthorizeAsync(User, "Settings.Manage")).Succeeded;
		if (TargetId == 0)
		{
			string? configuredPercent = await db.SystemSettings.AsNoTracking()
				.Where(x => x.SettingKey == "Inventory.DefaultThresholdPercent")
				.Select(x => x.Value)
				.SingleOrDefaultAsync(cancellationToken);
			if (int.TryParse(configuredPercent, out int defaultPercent))
			{
				ThresholdPercent = Math.Clamp(defaultPercent, 1, 100);
			}
		}
		IQueryable<Asset> inventory = BaseInventory();
		AssetTypes = await inventory.Select(x => x.Workstation ?? x.AssetType).Distinct().OrderBy(x => x).ToListAsync(cancellationToken);
		Locations = await inventory
			.Select(x => x.CurrentLocation ?? x.Location ?? "Unknown")
			.Distinct()
			.OrderBy(x => x)
			.ToListAsync(cancellationToken);
		Conditions = await inventory.Select(x => x.Condition).Distinct().OrderBy(x => x).ToListAsync(cancellationToken);

		List<Asset> inventoryAssets = await ApplyFilters(inventory).ToListAsync(cancellationToken);
		InventoryMatrix = inventoryAssets
			.GroupBy(Classification, StringComparer.OrdinalIgnoreCase)
			.OrderBy(group => group.Key)
			.Select(group => new StockStatusRow(
				group.Key,
				group.Count(asset => IsStatus(asset, "Active", "Allocated")),
				group.Count(asset => IsStatus(asset, "In Stock")),
				group.Count(asset => IsStatus(asset, "Lost")),
				group.Count(asset => IsStatus(asset, "Repair", "Under Repair")),
				group.Count(asset => IsStatus(asset, "Retired")),
				group.Count(asset => IsStatus(asset, "Recovery Pending", "Unreturned"))))
			.Where(row => row.GrandTotal > 0)
			.ToList();
		InventoryTotals = new StockStatusRow(
			"Grand Total",
			InventoryMatrix.Sum(row => row.Allocated),
			InventoryMatrix.Sum(row => row.InStock),
			InventoryMatrix.Sum(row => row.Lost),
			InventoryMatrix.Sum(row => row.UnderRepair),
			InventoryMatrix.Sum(row => row.Retired),
			InventoryMatrix.Sum(row => row.RecoveryPending));

		IQueryable<Asset> stock = BaseStock();

		IQueryable<Asset> filtered = ApplyFilters(stock);
		Assets = await filtered
			.OrderBy(x => x.CurrentLocation ?? x.Location)
			.ThenBy(x => x.Workstation ?? x.AssetType)
			.ThenBy(x => x.Hostname ?? x.AssetTag)
			.ToListAsync(cancellationToken);
		TotalInStock = Assets.Count;
		ByType = Assets
			.GroupBy(Classification, StringComparer.OrdinalIgnoreCase)
			.OrderByDescending(group => group.Count())
			.ThenBy(group => group.Key)
			.Select(group => new CountRow(group.Key, group.Count()))
			.ToList();
		ByLocation = Assets
			.GroupBy(x => x.CurrentLocation ?? x.Location ?? "Unknown")
			.OrderByDescending(group => group.Count())
			.ThenBy(group => group.Key)
			.Select(group => new CountRow(group.Key, group.Count()))
			.ToList();
		await LoadTargetsAsync(cancellationToken);
	}

	public async Task<IActionResult> OnPostSaveTargetAsync(CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(User, "Settings.Manage")).Succeeded)
		{
			return Forbid();
		}
		TargetAssetType = TargetAssetType.Trim();
		TargetLocation = string.IsNullOrWhiteSpace(TargetLocation) ? "All locations" : TargetLocation.Trim();
		if (TargetAssetType.Length == 0)
		{
			ModelState.AddModelError(nameof(TargetAssetType), "Asset type is required.");
		}
		if (TargetQuantity < 1)
		{
			ModelState.AddModelError(nameof(TargetQuantity), "Desired quantity must be at least 1.");
		}
		if (ThresholdPercent is < 1 or > 100)
		{
			ModelState.AddModelError(nameof(ThresholdPercent), "Threshold must be between 1% and 100%.");
		}
		if (!ModelState.IsValid)
		{
			await OnGetAsync(cancellationToken);
			return Page();
		}
		StockLevelTarget? target = TargetId == 0
			? null
			: await db.StockLevelTargets.SingleOrDefaultAsync(x => x.StockLevelTargetId == TargetId, cancellationToken);
		var before = target is null
			? null
			: new { target.AssetType, target.Location, target.TargetQuantity, target.ThresholdPercent };
		if (target is null)
		{
			target = await db.StockLevelTargets.SingleOrDefaultAsync(
				x => x.AssetType == TargetAssetType && x.Location == TargetLocation,
				cancellationToken);
		}
		if (target is null)
		{
			target = new StockLevelTarget
			{
				AssetType = TargetAssetType,
				Location = TargetLocation,
				TargetQuantity = TargetQuantity,
				ThresholdPercent = ThresholdPercent,
				CreatedUtc = DateTime.UtcNow,
				ModifiedUtc = DateTime.UtcNow
			};
			db.StockLevelTargets.Add(target);
		}
		else
		{
			target.AssetType = TargetAssetType;
			target.Location = TargetLocation;
			target.TargetQuantity = TargetQuantity;
			target.ThresholdPercent = ThresholdPercent;
			target.ModifiedUtc = DateTime.UtcNow;
			target.Version++;
		}
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync(
			"Inventory.StockTargetSaved",
			"StockLevelTarget",
			target.StockLevelTargetId.ToString(),
			User.FindFirstValue(ClaimTypes.NameIdentifier),
			before,
			new { target.AssetType, target.Location, target.TargetQuantity, target.ThresholdPercent },
			null,
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = $"Stock target saved for {target.AssetType} at {target.Location}.";
		return RedirectToPage();
	}

	public async Task<IActionResult> OnPostDeleteTargetAsync(int id, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(User, "Settings.Manage")).Succeeded)
		{
			return Forbid();
		}
		StockLevelTarget? target = await db.StockLevelTargets.SingleOrDefaultAsync(
			x => x.StockLevelTargetId == id,
			cancellationToken);
		if (target is null)
		{
			return NotFound();
		}
		var before = new { target.AssetType, target.Location, target.TargetQuantity, target.ThresholdPercent };
		db.StockLevelTargets.Remove(target);
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync(
			"Inventory.StockTargetDeleted",
			"StockLevelTarget",
			id.ToString(),
			User.FindFirstValue(ClaimTypes.NameIdentifier),
			before,
			null,
			null,
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = "Stock target removed.";
		return RedirectToPage();
	}

	public async Task<IActionResult> OnPostDeleteAssetAsync(int id, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(User, "Assets.Archive")).Succeeded)
		{
			return Forbid();
		}
		Asset? asset = await db.Assets.SingleOrDefaultAsync(x =>
			x.AssetId == id && !x.IsArchived && x.Status == "In Stock", cancellationToken);
		if (asset is null)
		{
			return NotFound();
		}
		if (await db.AssetAssignments.AnyAsync(x => x.AssetId == id && x.ReturnedUtc == null, cancellationToken))
		{
			TempData["Warning"] = "Assigned equipment cannot be deleted from Available Stock.";
			return RedirectToPage();
		}
		var before = new { asset.AssetTag, asset.Hostname, asset.Status, asset.IsArchived };
		asset.IsArchived = true;
		asset.ModifiedUtc = DateTime.UtcNow;
		asset.Version++;
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync(
			"Inventory.StockAssetDeleted", "Asset", id.ToString(), User.FindFirstValue(ClaimTypes.NameIdentifier),
			before, new { asset.AssetTag, asset.Hostname, asset.Status, asset.IsArchived },
			"Deleted from Available Stock", HttpContext.TraceIdentifier, cancellationToken);
		TempData["Success"] = $"{asset.Hostname ?? asset.AssetTag} was removed from available stock.";
		return RedirectToPage(new { Query, AssetType, Location, Condition });
	}

	public async Task<IActionResult> OnGetExportAsync(CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(User, "Assets.Export")).Succeeded)
		{
			return Forbid();
		}
		int[] ids = await ApplyFilters(BaseStock())
			.Select(x => x.AssetId)
			.ToArrayAsync(cancellationToken);
		string templatePath = Path.Combine(
			environment.ContentRootPath,
			"SeedData",
			"Asset inventory US template.xlsx");
		await using MemoryStream workbook = await exportService.ExportAsync(
			templatePath,
			cancellationToken,
			ids);
		return File(
			workbook.ToArray(),
			"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
			$"AssetPilot-Stock-Inventory-{DateTime.UtcNow:yyyyMMdd}.xlsx");
	}

	private IQueryable<Asset> BaseStock() =>
		db.Assets.AsNoTracking().Where(x =>
			!x.IsArchived
			&& x.Status == "In Stock"
			&& !db.AssetAssignments.Any(a => a.AssetId == x.AssetId && a.ReturnedUtc == null));

	private IQueryable<Asset> BaseInventory() =>
		db.Assets.AsNoTracking().Where(x => !x.IsArchived);

	private async Task LoadTargetsAsync(CancellationToken cancellationToken)
	{
		List<StockLevelTarget> targets = await db.StockLevelTargets.AsNoTracking()
			.OrderBy(x => x.AssetType)
			.ThenBy(x => x.Location)
			.ToListAsync(cancellationToken);
		List<Asset> available = await BaseStock().ToListAsync(cancellationToken);
		Targets = targets.Select(target =>
		{
			int count = available.Count(asset =>
				Classification(asset).Equals(target.AssetType, StringComparison.OrdinalIgnoreCase)
				&& (target.Location.Equals("All locations", StringComparison.OrdinalIgnoreCase)
					|| (asset.CurrentLocation ?? asset.Location ?? "Unknown")
						.Equals(target.Location, StringComparison.OrdinalIgnoreCase)));
			int alertAt = Math.Max(1, (int)Math.Ceiling(target.TargetQuantity * target.ThresholdPercent / 100m));
			return new TargetRow(
				target.StockLevelTargetId,
				target.AssetType,
				target.Location,
				target.TargetQuantity,
				target.ThresholdPercent,
				alertAt,
				count,
				Math.Max(0, target.TargetQuantity - count));
		}).ToList();
	}

	private IQueryable<Asset> ApplyFilters(IQueryable<Asset> source)
	{
		if (!string.IsNullOrWhiteSpace(Query))
		{
			string query = Query.Trim().ToLower();
			source = source.Where(x =>
				x.AssetTag.ToLower().Contains(query)
				|| (x.Hostname != null && x.Hostname.ToLower().Contains(query))
				|| (x.SerialNumber != null && x.SerialNumber.ToLower().Contains(query))
				|| x.Name.ToLower().Contains(query)
				|| x.AssetType.ToLower().Contains(query)
				|| (x.Workstation != null && x.Workstation.ToLower().Contains(query))
				|| (x.Model != null && x.Model.ToLower().Contains(query))
				|| (x.Location != null && x.Location.ToLower().Contains(query))
				|| (x.CurrentLocation != null && x.CurrentLocation.ToLower().Contains(query)));
		}
		if (!string.IsNullOrWhiteSpace(AssetType))
		{
			source = source.Where(x => (x.Workstation ?? x.AssetType) == AssetType);
		}
		if (!string.IsNullOrWhiteSpace(Location))
		{
			source = source.Where(x => (x.CurrentLocation ?? x.Location ?? "Unknown") == Location);
		}
		if (!string.IsNullOrWhiteSpace(Condition))
		{
			source = source.Where(x => x.Condition == Condition);
		}
		return source;
	}

	private static string Classification(Asset asset) =>
		string.IsNullOrWhiteSpace(asset.Workstation) ? asset.AssetType : asset.Workstation;

	private static bool IsStatus(Asset asset, params string[] statuses) =>
		statuses.Any(status => asset.Status.Equals(status, StringComparison.OrdinalIgnoreCase));
}
