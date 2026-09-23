using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Auditing;
using AssetPilot.Domain.Assets;
using AssetPilot.Domain.MasterData;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Infrastructure.Persistence;

public sealed class PhaseOneDataSeeder(AssetPilotDbContext db, IAuditService audit)
{
	public async Task SeedAsync(CancellationToken cancellationToken = default(CancellationToken))
	{
		HashSet<string> existingKeys = (await db.ReferenceDataItems.Select((ReferenceDataItem referenceDataItem) => new { referenceDataItem.Kind, referenceDataItem.Name }).ToListAsync(cancellationToken)).Select(anon => Key(anon.Kind, anon.Name)).ToHashSet<string>(StringComparer.OrdinalIgnoreCase);
		DateTime now = DateTime.UtcNow;
		int addedReferenceItems = 0;
		AddMany("LifecycleStatus", new global::_003C_003Ez__ReadOnlyArray<string>(new string[5] { "Active", "In Stock", "Pending Receipt", "Repair", "Retired" }));
		AddMany("Condition", new global::_003C_003Ez__ReadOnlyArray<string>(new string[5] { "Good", "Fair", "Poor", "Damaged", "Unknown" }));
		AddMany("Classification", new global::_003C_003Ez__ReadOnlyArray<string>(new string[4] { "Business Use", "Shared", "Restricted", "Confidential" }));
		AddMany("Severity", new global::_003C_003Ez__ReadOnlyArray<string>(new string[4] { "Low", "Medium", "High", "Critical" }));
		var assets = await (from asset in db.Assets.AsNoTracking()
			where !asset.IsArchived
			select new
			{
				asset.AssetId, asset.Status, asset.Condition, asset.Category, asset.AssetType, asset.Manufacturer, asset.Model, asset.Vendor, asset.Project, asset.Department,
				asset.Location, asset.Company, asset.Purpose, asset.MacAddress, asset.CreatedUtc
			}).ToListAsync(cancellationToken);
		foreach (var item2 in assets)
		{
			Add("LifecycleStatus", item2.Status);
			Add("Condition", item2.Condition);
			Add("Category", item2.Category);
			Add("AssetType", item2.AssetType);
			Add("Manufacturer", item2.Manufacturer);
			Add("Model", item2.Model);
			Add("Vendor", item2.Vendor);
			Add("Project", item2.Project);
			Add("Department", item2.Department);
			Add("Location", item2.Location);
			Add("Organization", item2.Company);
			Add("Purpose", item2.Purpose);
		}
		if (addedReferenceItems > 0)
		{
			await db.SaveChangesAsync(cancellationToken);
		}
		HashSet<int> historyAssetIds = await db.AssetStatusHistory.Select((AssetStatusHistory history) => history.AssetId).Distinct().ToHashSetAsync(cancellationToken);
		int addedHistory = 0;
		foreach (var item3 in assets.Where(asset => !historyAssetIds.Contains(asset.AssetId)))
		{
			db.AssetStatusHistory.Add(new AssetStatusHistory
			{
				AssetId = item3.AssetId,
				ToStatus = item3.Status,
				ChangedUtc = item3.CreatedUtc,
				Reason = "Initial lifecycle state"
			});
			addedHistory++;
		}
		HashSet<string> hashSet = (await db.AssetNetworkAddresses.Select((AssetNetworkAddress address) => new { address.AssetId, address.AddressType, address.Address }).ToListAsync(cancellationToken)).Select(address => $"{address.AssetId}\0{address.AddressType}\0{address.Address}").ToHashSet<string>(StringComparer.OrdinalIgnoreCase);
		int addedNetworkAddresses = 0;
		foreach (var item4 in assets.Where(asset => !string.IsNullOrWhiteSpace(asset.MacAddress)))
		{
			string[] array = item4.MacAddress.Split(new char[3] { ',', ';', '\n' }, StringSplitOptions.RemoveEmptyEntries | StringSplitOptions.TrimEntries);
			foreach (string text in array)
			{
				string item = $"{item4.AssetId}\0MAC\0{text}";
				if (hashSet.Add(item))
				{
					db.AssetNetworkAddresses.Add(new AssetNetworkAddress
					{
						AssetId = item4.AssetId,
						AddressType = "MAC",
						Address = text,
						IsPrimary = true,
						CreatedUtc = now,
						ModifiedUtc = now
					});
					addedNetworkAddresses++;
				}
			}
		}
		if (addedHistory > 0 || addedNetworkAddresses > 0)
		{
			await db.SaveChangesAsync(cancellationToken);
		}
		if (addedReferenceItems > 0 || addedHistory > 0 || addedNetworkAddresses > 0)
		{
			await audit.WriteAsync("Phase1.DataSeeded", "System", "phase1", null, null, new
			{
				ReferenceItems = addedReferenceItems,
				StatusHistory = addedHistory,
				NetworkAddresses = addedNetworkAddresses
			}, "Completed governed Phase 1 data", "phase1-data-seed", cancellationToken);
		}
		void Add(string kind, string? name)
		{
			string text2 = (string.IsNullOrWhiteSpace(name) ? null : name.Trim());
			if (text2 != null && existingKeys.Add(Key(kind, text2)))
			{
				db.ReferenceDataItems.Add(new ReferenceDataItem
				{
					Kind = kind,
					Name = text2,
					IsActive = true,
					CreatedUtc = now,
					ModifiedUtc = now
				});
				addedReferenceItems++;
			}
		}
		void AddMany(string kind, IEnumerable<string> names)
		{
			foreach (string name in names)
			{
				Add(kind, name);
			}
		}
	}

	private static string Key(string kind, string name)
	{
		return kind + "\0" + name;
	}
}
