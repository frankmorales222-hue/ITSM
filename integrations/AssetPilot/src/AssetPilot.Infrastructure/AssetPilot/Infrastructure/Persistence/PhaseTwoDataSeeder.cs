using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Domain.Assets;
using AssetPilot.Domain.Operations;
using AssetPilot.Domain.People;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Infrastructure.Persistence;

public sealed class PhaseTwoDataSeeder(AssetPilotDbContext db)
{
	public async Task SeedAsync(CancellationToken cancellationToken = default(CancellationToken))
	{
		DateTime now = DateTime.UtcNow;
		(string, string, string)[] settings = new(string, string, string)[8]
		{
			("Organization.Name", "AssetPilot Organization", "Organization name shown in reports."),
			("Inventory.LowStockThreshold", "10", "Number of in-stock assets that triggers a low-stock warning."),
			("Shipments.DefaultCarrier", "", "Default carrier for new shipments."),
			("Operations.BackupReminderDays", "7", "Recommended maximum days between backups."),
			("Application.Name", "AssetPilot", "Application name shown throughout the interface."),
			("Branding.LogoDataUrl", "", "Uploaded application logo."),
			("Branding.AccentColor", "#0969da", "Primary interface color."),
			("Inventory.DefaultThresholdPercent", "50", "Default percentage used for new stock targets.")
		};
		List<string> existingKeys = await db.SystemSettings.Select((SystemSetting x) => x.SettingKey).ToListAsync(cancellationToken);
		foreach (var item in settings.Where(((string, string, string) x) => !existingKeys.Contains<string>(x.Item1, StringComparer.OrdinalIgnoreCase)))
		{
			db.SystemSettings.Add(new SystemSetting
			{
				SettingKey = item.Item1,
				Value = item.Item2,
				Description = item.Item3,
				CreatedUtc = now,
				ModifiedUtc = now
			});
		}
		var sourcePeople = await (from x in db.Assets.AsNoTracking()
			where !x.IsArchived && x.AssignedTo != null && x.AssignedTo != ""
			select new { x.AssignedTo, x.AssignedToEmail, x.Department, x.Location }).ToListAsync(cancellationToken);
		List<Employee> employees = await db.Employees.ToListAsync(cancellationToken);
		foreach (var item2 in from @group in Enumerable.GroupBy(sourcePeople, x => x.AssignedToEmail ?? x.AssignedTo, StringComparer.OrdinalIgnoreCase)
			select @group.First())
		{
			string email = NormalizeEmail(item2.AssignedToEmail, item2.AssignedTo);
			if (!employees.Any((Employee x) => x.Email.Equals(email, StringComparison.OrdinalIgnoreCase)))
			{
				Employee employee = new Employee
				{
					EmployeeNumber = $"EMP-{employees.Count + 1:D5}",
					DisplayName = item2.AssignedTo,
					Email = email,
					Department = item2.Department,
					Location = item2.Location,
					CreatedUtc = now,
					ModifiedUtc = now
				};
				db.Employees.Add(employee);
				employees.Add(employee);
			}
		}
		await db.SaveChangesAsync(cancellationToken);
		List<int> assignedAssetIds = await (from x in db.AssetAssignments
			where x.ReturnedUtc == null
			select x.AssetId).ToListAsync(cancellationToken);
		foreach (Asset asset in await db.Assets.Where((Asset x) => !x.IsArchived && x.AssignedTo != null && !assignedAssetIds.Contains(x.AssetId)).ToListAsync(cancellationToken))
		{
			Employee employee2 = employees.FirstOrDefault((Employee x) => (!string.IsNullOrWhiteSpace(asset.AssignedToEmail) && x.Email.Equals(asset.AssignedToEmail, StringComparison.OrdinalIgnoreCase)) || x.DisplayName.Equals(asset.AssignedTo, StringComparison.OrdinalIgnoreCase));
			if (employee2 != null)
			{
				db.AssetAssignments.Add(new AssetAssignment
				{
					Asset = asset,
					Employee = employee2,
					AssignedUtc = asset.CreatedUtc,
					AssignedLocation = asset.Location,
					Notes = "Initial assignment imported from inventory"
				});
			}
		}
		await db.SaveChangesAsync(cancellationToken);
		if (!await db.StockLevelTargets.AnyAsync(cancellationToken))
		{
			var availableBaseline = await db.Assets.AsNoTracking()
				.Where(x => !x.IsArchived
					&& x.Status == "In Stock"
					&& !db.AssetAssignments.Any(a => a.AssetId == x.AssetId && a.ReturnedUtc == null))
				.GroupBy(x => new
				{
					x.AssetType,
					Location = x.CurrentLocation ?? x.Location ?? "Unknown"
				})
				.Select(group => new
				{
					group.Key.AssetType,
					group.Key.Location,
					Count = group.Count()
				})
				.ToListAsync(cancellationToken);
			foreach (var group in availableBaseline)
			{
				db.StockLevelTargets.Add(new StockLevelTarget
				{
					AssetType = group.AssetType,
					Location = group.Location,
					TargetQuantity = group.Count,
					ThresholdPercent = 50,
					CreatedUtc = now,
					ModifiedUtc = now
				});
			}
			await db.SaveChangesAsync(cancellationToken);
		}
	}

	private static string NormalizeEmail(string? email, string name)
	{
		if (!string.IsNullOrWhiteSpace(email) && email.Contains('@'))
		{
			return email.Trim();
		}
		string text = new string((from character in name.ToLowerInvariant()
			select (!char.IsLetterOrDigit(character)) ? '.' : character).ToArray()).Trim('.');
		while (text.Contains("..", StringComparison.Ordinal))
		{
			text = text.Replace("..", ".", StringComparison.Ordinal);
		}
		return text + "@inventory.local";
	}
}
