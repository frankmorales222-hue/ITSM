using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Domain.Assets;
using AssetPilot.Domain.People;
using AssetPilot.Domain.Shipments;
using AssetPilot.Application.Assets;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;
using AssetPilot.Web.Services;
using Microsoft.Extensions.Hosting;

namespace AssetPilot.Web.Pages.Reports;

public sealed class IndexModel(
	AssetPilotDbContext db,
	IAuthorizationService authorization,
	IInventoryAuditExportService exportService,
	IHostEnvironment environment) : PageModel
{
	public sealed record CountRow(string Label, int Count);

	public sealed record WarrantyRow(int Id, string Tag, string Name, DateOnly Expiration);

	public int TotalAssets { get; private set; }

	public int AssignedAssets { get; private set; }

	public int UnassignedAssets { get; private set; }

	public int OpenShipments { get; private set; }

	public int AvailableAssets { get; private set; }

	public int ActiveEmployees { get; private set; }

	public int UtilizationPercent { get; private set; }

	public int StockGoalsBelowWarning { get; private set; }
	public int ExceptionAssets { get; private set; }

	public IReadOnlyList<CountRow> ByStatus { get; private set; } = Array.Empty<CountRow>();

	public IReadOnlyList<CountRow> ByDepartment { get; private set; } = Array.Empty<CountRow>();

	public IReadOnlyList<CountRow> ByLocation { get; private set; } = Array.Empty<CountRow>();

	public IReadOnlyList<WarrantyRow> WarrantyExpiring { get; private set; } = Array.Empty<WarrantyRow>();
	public IReadOnlyList<AssetPilot.Web.Pages.IndexModel.EquipmentSummary> EquipmentInventory { get; private set; } = Array.Empty<AssetPilot.Web.Pages.IndexModel.EquipmentSummary>();

	public async Task OnGetAsync(CancellationToken cancellationToken)
	{
		await StockTargetSynchronizer.EnsureInventoryTypesAsync(db, cancellationToken);
		IQueryable<Asset> assets = from x in db.Assets.AsNoTracking()
			where !x.IsArchived
			select x;
		TotalAssets = await assets.CountAsync(cancellationToken);
		List<Asset> inventory = await assets.ToListAsync(cancellationToken);
		AssignedAssets = await assets.CountAsync(
			x => !string.IsNullOrWhiteSpace(x.AssignedTo)
				|| x.Assignments.Any(assignment => assignment.ReturnedUtc == null),
			cancellationToken);
		UnassignedAssets = TotalAssets - AssignedAssets;
		ExceptionAssets = inventory.Count(asset =>
			asset.Status.Equals("Repair", StringComparison.OrdinalIgnoreCase)
			|| asset.Status.Equals("Lost", StringComparison.OrdinalIgnoreCase)
			|| asset.Status.Equals("Recovery Pending", StringComparison.OrdinalIgnoreCase));
		HashSet<int> assignedIds = (await db.AssetAssignments
			.Where(assignment => assignment.ReturnedUtc == null)
			.Select(assignment => assignment.AssetId)
			.Distinct()
			.ToListAsync(cancellationToken))
			.ToHashSet();
		EquipmentInventory = AssetPilot.Web.Pages.IndexModel.BuildEquipmentInventory(inventory, assignedIds);
		UtilizationPercent = TotalAssets == 0
			? 0
			: (int)Math.Round(AssignedAssets * 100m / TotalAssets);
		IQueryable<Asset> availableStock = assets.Where(x =>
			x.Status == "In Stock"
			&& !db.AssetAssignments.Any(assignment =>
				assignment.AssetId == x.AssetId && assignment.ReturnedUtc == null));
		AvailableAssets = await availableStock.CountAsync(cancellationToken);
		ActiveEmployees = await db.Employees.CountAsync(
			employee => employee.IsActive && !employee.IsDeleted,
			cancellationToken);
		OpenShipments = await db.Shipments.CountAsync((Shipment x) => !x.IsArchived && x.ReceivedUtc == null && x.Status != "Cancelled", cancellationToken);
		List<Asset> available = await availableStock.ToListAsync(cancellationToken);
		StockGoalsBelowWarning = (await db.StockLevelTargets.AsNoTracking().ToListAsync(cancellationToken))
			.Count(target =>
			{
				int count = available.Count(asset =>
					StockTargetSynchronizer.Classification(asset).Equals(target.AssetType, StringComparison.OrdinalIgnoreCase)
					&& (target.Location.Equals("All locations", StringComparison.OrdinalIgnoreCase)
						|| (asset.CurrentLocation ?? asset.Location ?? "Unknown")
							.Equals(target.Location, StringComparison.OrdinalIgnoreCase)));
				int alertAt = Math.Max(1, (int)Math.Ceiling(
					target.TargetQuantity * target.ThresholdPercent / 100m));
				return count < alertAt;
			});
		ByStatus = await (from x in assets
			group x by x.Status into x
			orderby x.Count() descending
			select new CountRow(x.Key, x.Count())).ToListAsync(cancellationToken);
		ByDepartment = await (from x in (from x in assets
				group x by x.Department ?? "Unassigned" into x
				orderby x.Count() descending
				select x).Take(12)
			select new CountRow(x.Key, x.Count())).ToListAsync(cancellationToken);
		ByLocation = await (from x in (from x in assets
				group x by x.Location ?? "Unknown" into x
				orderby x.Count() descending
				select x).Take(12)
			select new CountRow(x.Key, x.Count())).ToListAsync(cancellationToken);
		DateOnly today = DateOnly.FromDateTime(DateTime.Today);
		DateOnly cutoff = today.AddDays(90);
		WarrantyExpiring = await (from x in (from x in assets
				where x.WarrantyExpiration >= today && x.WarrantyExpiration <= cutoff
				orderby x.WarrantyExpiration
				select x).Take(20)
			select new WarrantyRow(x.AssetId, x.AssetTag, x.Name, x.WarrantyExpiration.Value)).ToListAsync(cancellationToken);
	}

	public async Task<IActionResult> OnGetExportAsync(CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(base.User, "Reports.Export")).Succeeded)
		{
			return Forbid();
		}
		string templatePath = global::System.IO.Path.Combine(
			environment.ContentRootPath,
			"SeedData",
			"Asset inventory US template.xlsx");
		global::System.IO.MemoryStream workbook = await exportService.ExportAsync(templatePath, cancellationToken);
		return File(
			workbook.ToArray(),
			"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
			$"AssetPilot-Inventory-Audit-{DateTime.UtcNow:yyyyMMdd}.xlsx");
	}
}
