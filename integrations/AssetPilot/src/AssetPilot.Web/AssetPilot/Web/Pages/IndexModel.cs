using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Domain.Assets;
using AssetPilot.Domain.People;
using AssetPilot.Domain.Operations;
using AssetPilot.Domain.Shipments;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;
using AssetPilot.Web.Services;

namespace AssetPilot.Web.Pages;

public sealed class IndexModel(AssetPilotDbContext db) : PageModel
{
	public sealed record RecentAsset(int AssetId, string AssetTag, string Name, string Status, string? AssignedTo, DateTime ModifiedUtc);
	public sealed record DashboardCount(string Label, int Count, int Percent);
	public sealed record EquipmentSummary(string Label, string Icon, string Query, int Total, int Assigned, int Available, int Attention);
	public sealed record StockAlert(
		string AssetType,
		string Location,
		int Available,
		int AlertAt,
		int TargetQuantity,
		int ReorderQuantity);

	public int TotalAssets { get; private set; }

	public int ActiveAssets { get; private set; }

	public int InStockAssets { get; private set; }

	public int PendingReceiptAssets { get; private set; }

	public int ActiveEmployees { get; private set; }

	public int OpenShipments { get; private set; }

	public int UnassignedAssets { get; private set; }

	public int AssignedAssets { get; private set; }

	public int UtilizationPercent { get; private set; }

	public int TotalStockTargets { get; private set; }

	public int HealthyStockTargets { get; private set; }

	public int AttentionCount => StockAlerts.Count + PendingReceiptAssets + OpenShipments;

	public IReadOnlyList<RecentAsset> RecentAssets { get; private set; } = Array.Empty<RecentAsset>();
	public IReadOnlyList<StockAlert> StockAlerts { get; private set; } = Array.Empty<StockAlert>();
	public IReadOnlyList<DashboardCount> StatusBreakdown { get; private set; } = Array.Empty<DashboardCount>();
	public IReadOnlyList<DashboardCount> StockByType { get; private set; } = Array.Empty<DashboardCount>();
	public IReadOnlyList<DashboardCount> StockByLocation { get; private set; } = Array.Empty<DashboardCount>();
	public IReadOnlyList<EquipmentSummary> EquipmentInventory { get; private set; } = Array.Empty<EquipmentSummary>();

	public async Task OnGetAsync(CancellationToken cancellationToken)
	{
		await StockTargetSynchronizer.EnsureInventoryTypesAsync(db, cancellationToken);
		IQueryable<Asset> assets = from x in db.Assets.AsNoTracking()
			where !x.IsArchived
			select x;
		List<Asset> inventory = await assets.ToListAsync(cancellationToken);
		TotalAssets = await assets.CountAsync(cancellationToken);
		ActiveAssets = await assets.CountAsync((Asset x) => x.Status == "Active", cancellationToken);
		IQueryable<Asset> availableStock = assets.Where(x =>
			x.Status == "In Stock"
			&& !db.AssetAssignments.Any(a => a.AssetId == x.AssetId && a.ReturnedUtc == null));
		InStockAssets = await availableStock.CountAsync(cancellationToken);
		PendingReceiptAssets = await assets.CountAsync((Asset x) => x.Status == "Pending Receipt", cancellationToken);
		ActiveEmployees = await db.Employees.CountAsync((Employee x) => x.IsActive && !x.IsDeleted, cancellationToken);
		OpenShipments = await db.Shipments.CountAsync((Shipment x) => !x.IsArchived && x.ReceivedUtc == null && x.Status != "Cancelled", cancellationToken);
		AssignedAssets = await db.AssetAssignments
			.Where(x => x.ReturnedUtc == null)
			.Select(x => x.AssetId)
			.Distinct()
			.CountAsync(cancellationToken);
		HashSet<int> assignedIds = (await db.AssetAssignments
			.Where(x => x.ReturnedUtc == null)
			.Select(x => x.AssetId)
			.Distinct()
			.ToListAsync(cancellationToken))
			.ToHashSet();
		EquipmentInventory = BuildEquipmentInventory(inventory, assignedIds);
		UnassignedAssets = Math.Max(0, TotalAssets - AssignedAssets);
		UtilizationPercent = TotalAssets == 0
			? 0
			: (int)Math.Round(AssignedAssets * 100m / TotalAssets);
		RecentAssets = await (from x in assets.OrderByDescending((Asset x) => x.ModifiedUtc).Take(6)
			select new RecentAsset(x.AssetId, x.AssetTag, x.Name, x.Status, x.AssignedTo, x.ModifiedUtc)).ToListAsync(cancellationToken);
		List<Asset> available = await availableStock.ToListAsync(cancellationToken);
		List<StockLevelTarget> targets = await db.StockLevelTargets.AsNoTracking().ToListAsync(cancellationToken);
		List<StockAlert> evaluatedTargets = targets
			.Select(target =>
			{
				int count = available.Count(asset =>
					StockTargetSynchronizer.Classification(asset).Equals(target.AssetType, StringComparison.OrdinalIgnoreCase)
					&& (target.Location.Equals("All locations", StringComparison.OrdinalIgnoreCase)
						|| (asset.CurrentLocation ?? asset.Location ?? "Unknown")
							.Equals(target.Location, StringComparison.OrdinalIgnoreCase)));
				int alertAt = Math.Max(1, (int)Math.Ceiling(target.TargetQuantity * target.ThresholdPercent / 100m));
				return new StockAlert(
					target.AssetType,
					target.Location,
					count,
					alertAt,
					target.TargetQuantity,
					Math.Max(0, target.TargetQuantity - count));
			})
			.ToList();
		StockAlerts = evaluatedTargets
			.Where(alert => alert.Available < alert.AlertAt)
			.OrderBy(alert => alert.Available)
			.ThenBy(alert => alert.AssetType)
			.ToList();
		TotalStockTargets = evaluatedTargets.Count;
		HealthyStockTargets = evaluatedTargets.Count - StockAlerts.Count;
		var statuses = await assets
			.GroupBy(x => x.Status)
			.Select(group => new { Label = group.Key, Count = group.Count() })
			.OrderByDescending(x => x.Count)
			.ToListAsync(cancellationToken);
		StatusBreakdown = statuses
			.Select(x => new DashboardCount(
				x.Label,
				x.Count,
				TotalAssets == 0 ? 0 : (int)Math.Round(x.Count * 100m / TotalAssets)))
			.ToList();
		int maxType = Math.Max(1, available.GroupBy(x => x.AssetType).Select(x => x.Count()).DefaultIfEmpty(0).Max());
		StockByType = available
			.GroupBy(x => x.AssetType)
			.OrderByDescending(group => group.Count())
			.ThenBy(group => group.Key)
			.Take(6)
			.Select(group => new DashboardCount(
				group.Key,
				group.Count(),
				(int)Math.Round(group.Count() * 100m / maxType)))
			.ToList();
		int maxLocation = Math.Max(1, available
			.GroupBy(x => x.CurrentLocation ?? x.Location ?? "Unknown")
			.Select(x => x.Count())
			.DefaultIfEmpty(0)
			.Max());
		StockByLocation = available
			.GroupBy(x => x.CurrentLocation ?? x.Location ?? "Unknown")
			.OrderByDescending(group => group.Count())
			.ThenBy(group => group.Key)
			.Take(5)
			.Select(group => new DashboardCount(
				group.Key,
				group.Count(),
				(int)Math.Round(group.Count() * 100m / maxLocation)))
			.ToList();
	}

	public static IReadOnlyList<EquipmentSummary> BuildEquipmentInventory(
		IReadOnlyList<Asset> assets,
		IReadOnlySet<int> assignedIds)
	{
		static string Type(Asset asset) => (asset.Workstation ?? asset.AssetType ?? "").Trim().ToLowerInvariant();
		static bool NeedsAttention(Asset asset) => asset.Status.Equals("Repair", StringComparison.OrdinalIgnoreCase)
			|| asset.Status.Equals("Lost", StringComparison.OrdinalIgnoreCase)
			|| asset.Status.Equals("Recovery Pending", StringComparison.OrdinalIgnoreCase)
			|| asset.Status.Equals("Pending Receipt", StringComparison.OrdinalIgnoreCase);
		EquipmentSummary Summary(string label, string icon, string query, Func<Asset, bool> matches)
		{
			List<Asset> items = assets.Where(matches).ToList();
			return new EquipmentSummary(
				label,
				icon,
				query,
				items.Count,
				items.Count(asset => assignedIds.Contains(asset.AssetId) || asset.Status.Equals("Active", StringComparison.OrdinalIgnoreCase)),
				items.Count(asset => asset.Status.Equals("In Stock", StringComparison.OrdinalIgnoreCase) && !assignedIds.Contains(asset.AssetId)),
				items.Count(NeedsAttention));
		}
		static bool HasIdentifier(string? value) => !string.IsNullOrWhiteSpace(value)
			&& !new[] { "N/A", "NA", "UNKNOWN", "NONE", "TBD", "-", "--" }
				.Contains(value.Trim(), StringComparer.OrdinalIgnoreCase);
		EquipmentSummary AccessorySummary(
			string label,
			string icon,
			string query,
			Func<Asset, bool> standaloneMatch,
			Func<Asset, IEnumerable<string?>> associatedIdentifiers)
		{
			Dictionary<string, (bool Assigned, bool Available, bool Attention)> devices = new(StringComparer.OrdinalIgnoreCase);
			void Add(string key, Asset owner)
			{
				bool assigned = assignedIds.Contains(owner.AssetId) || owner.Status.Equals("Active", StringComparison.OrdinalIgnoreCase);
				bool available = owner.Status.Equals("In Stock", StringComparison.OrdinalIgnoreCase) && !assignedIds.Contains(owner.AssetId);
				bool attention = NeedsAttention(owner);
				if (devices.TryGetValue(key, out var existing))
				{
					devices[key] = (existing.Assigned || assigned, existing.Available || available, existing.Attention || attention);
				}
				else
				{
					devices[key] = (assigned, available, attention);
				}
			}
			foreach (Asset asset in assets)
			{
				if (standaloneMatch(asset))
				{
					Add(HasIdentifier(asset.SerialNumber) ? asset.SerialNumber!.Trim() : asset.AssetTag.Trim(), asset);
				}
				foreach (string? identifier in associatedIdentifiers(asset).Where(HasIdentifier))
				{
					Add(identifier!.Trim(), asset);
				}
			}
			return new EquipmentSummary(
				label, icon, query, devices.Count,
				devices.Count(item => item.Value.Assigned),
				devices.Count(item => item.Value.Available),
				devices.Count(item => item.Value.Attention));
		}

		List<EquipmentSummary> summaries =
		[
			Summary("Laptops", "L", "laptop", asset => Type(asset).Contains("laptop") && !Type(asset).Contains("mac")),
			Summary("MacBooks", "M", "macbook", asset => Type(asset).Contains("macbook") || Type(asset) == "mac"),
			Summary("Desktops", "D", "desktop", asset => Type(asset).Contains("desktop")),
			AccessorySummary(
				"Monitors", "▣", "monitor",
				asset => Type(asset).Contains("monitor"),
				asset => new[]
				{
					HasIdentifier(asset.Monitor1SerialNumber) ? asset.Monitor1SerialNumber : asset.Monitor1AssetTag,
					HasIdentifier(asset.Monitor2SerialNumber) ? asset.Monitor2SerialNumber : asset.Monitor2AssetTag,
					HasIdentifier(asset.Monitor3SerialNumber) ? asset.Monitor3SerialNumber : asset.Monitor3AssetTag
				}),
			AccessorySummary(
				"Docking stations", "↔", "dock",
				asset => Type(asset).Contains("dock"),
				asset => new[] { asset.DockingStation }),
			Summary("Printers", "P", "printer", asset => Type(asset).Contains("printer"))
		];

		HashSet<int> categorized = assets
			.Where(asset => summaries.Take(6).Any(summary => summary.Query switch
			{
				"laptop" => Type(asset).Contains("laptop") && !Type(asset).Contains("mac"),
				"macbook" => Type(asset).Contains("macbook") || Type(asset) == "mac",
				"desktop" => Type(asset).Contains("desktop"),
				"monitor" => Type(asset).Contains("monitor"),
				"dock" => Type(asset).Contains("dock"),
				"printer" => Type(asset).Contains("printer"),
				_ => false
			}))
			.Select(asset => asset.AssetId)
			.ToHashSet();
		summaries.Add(Summary("Other equipment", "…", "", asset => !categorized.Contains(asset.AssetId)));
		return summaries;
	}
}
