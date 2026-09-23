using AssetPilot.Domain.Operations;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Web.Services;

public static class StockTargetSynchronizer
{
	public static async Task EnsureInventoryTypesAsync(
		AssetPilotDbContext db,
		CancellationToken cancellationToken)
	{
		var inventoryTypes = await db.Assets.AsNoTracking()
			.Where(asset => !asset.IsArchived)
			.GroupBy(asset => asset.Workstation ?? asset.AssetType)
			.Select(group => new { AssetType = group.Key, QuantityOwned = group.Count() })
			.ToListAsync(cancellationToken);
		if (inventoryTypes.Count == 0)
		{
			return;
		}

		List<string> configuredTypes = await db.StockLevelTargets.AsNoTracking()
			.Select(target => target.AssetType)
			.Distinct()
			.ToListAsync(cancellationToken);
		var configured = configuredTypes.ToHashSet(StringComparer.OrdinalIgnoreCase);
		string? configuredPercent = await db.SystemSettings.AsNoTracking()
			.Where(setting => setting.SettingKey == "Inventory.DefaultThresholdPercent")
			.Select(setting => setting.Value)
			.SingleOrDefaultAsync(cancellationToken);
		int thresholdPercent = int.TryParse(configuredPercent, out int parsed)
			? Math.Clamp(parsed, 1, 100)
			: 50;
		DateTime now = DateTime.UtcNow;

		foreach (var item in inventoryTypes.Where(item =>
			!string.IsNullOrWhiteSpace(item.AssetType) && !configured.Contains(item.AssetType)))
		{
			db.StockLevelTargets.Add(new StockLevelTarget
			{
				AssetType = item.AssetType,
				Location = "All locations",
				TargetQuantity = Math.Max(1, item.QuantityOwned),
				ThresholdPercent = thresholdPercent,
				CreatedUtc = now,
				ModifiedUtc = now
			});
		}

		if (db.ChangeTracker.HasChanges())
		{
			await db.SaveChangesAsync(cancellationToken);
		}
	}

	public static string Classification(AssetPilot.Domain.Assets.Asset asset) =>
		string.IsNullOrWhiteSpace(asset.Workstation) ? asset.AssetType : asset.Workstation;
}
