using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Assets;
using AssetPilot.Domain.Assets;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Hosting;

namespace AssetPilot.Web.Pages.Assets;

public sealed class IndexModel(
	AssetPilotDbContext db,
	IInventoryAuditExportService exportService,
	IAuthorizationService authorization,
	IHostEnvironment environment) : PageModel
{
	public static IReadOnlyList<string> Statuses { get; } = new global::_003C_003Ez__ReadOnlyArray<string>(new string[7] { "Active", "In Stock", "Pending Receipt", "Repair", "Lost", "Recovery Pending", "Retired" });

	[BindProperty(SupportsGet = true)]
	public string? Query { get; set; }

	[BindProperty(SupportsGet = true)]
	public string? Status { get; set; } = "Active";

	[BindProperty(SupportsGet = true)]
	public string View { get; set; } = "Computers";

	public IReadOnlyList<Asset> Assets { get; private set; } = Array.Empty<Asset>();
	public IReadOnlyList<AssetInventoryGroup> Groups { get; private set; } = Array.Empty<AssetInventoryGroup>();

	public async Task OnGetAsync(CancellationToken cancellationToken)
	{
		IQueryable<Asset> source = ApplyFilters(db.Assets.AsNoTracking().Where(asset => !asset.IsArchived));
		Assets = await source
			.OrderBy((Asset asset) => asset.AssignedToEmail == null)
			.ThenBy((Asset asset) => asset.AssignedToEmail)
			.ThenBy((Asset asset) => asset.Hostname ?? asset.AssetTag)
			.ToListAsync(cancellationToken);
		Groups = Assets
			.GroupBy(GroupKey, StringComparer.OrdinalIgnoreCase)
			.Select(group => CreateGroup(group.ToList()))
			.OrderBy(group => group.Email == null)
			.ThenBy(group => group.Email ?? group.DisplayName, StringComparer.OrdinalIgnoreCase)
			.ToList();
	}

	private static string GroupKey(Asset asset)
	{
		if (!string.IsNullOrWhiteSpace(asset.AssignedToEmail))
		{
			return "email:" + asset.AssignedToEmail.Trim();
		}
		if (!string.IsNullOrWhiteSpace(asset.AssignedTo))
		{
			return "name:" + asset.AssignedTo.Trim();
		}
		return "asset:" + asset.AssetId;
	}

	private static AssetInventoryGroup CreateGroup(IReadOnlyList<Asset> assets)
	{
		Asset first = assets[0];
		string typeSummary = string.Join(
			", ",
			assets
				.GroupBy(asset => asset.AssetType, StringComparer.OrdinalIgnoreCase)
				.OrderByDescending(group => group.Count())
				.ThenBy(group => group.Key)
				.Select(group => group.Count() == 1 ? group.Key : $"{group.Key} ×{group.Count()}"));
		string[] locations = assets
			.Select(asset => asset.CurrentLocation ?? asset.Location)
			.Where(location => !string.IsNullOrWhiteSpace(location))
			.Distinct(StringComparer.OrdinalIgnoreCase)
			.OrderBy(location => location)
			.Cast<string>()
			.ToArray();
		string locationSummary = locations.Length switch
		{
			0 => "—",
			1 => locations[0],
			_ => $"{locations.Length} locations"
		};
		int monitorCount = assets.Sum(CountMonitors);
		string[] statuses = assets
			.Select(asset => asset.Status)
			.Distinct(StringComparer.OrdinalIgnoreCase)
			.OrderBy(status => status)
			.ToArray();
		string statusSummary = statuses.Length == 1
			? statuses[0]
			: string.Join(", ", statuses.Select(status =>
				$"{status} ×{assets.Count(asset => asset.Status.Equals(status, StringComparison.OrdinalIgnoreCase))}"));
		return new AssetInventoryGroup(
			first.AssignedToEmail?.Trim(),
			first.AssignedTo?.Trim() ?? "Unassigned",
			assets.OrderBy(asset => asset.Hostname ?? asset.AssetTag, StringComparer.OrdinalIgnoreCase).ToList(),
			typeSummary,
			locationSummary,
			monitorCount,
			statusSummary,
			statuses.Length == 1 ? statuses[0].ToLowerInvariant().Replace(" ", "-") : "mixed");
	}

	private static int HasMonitor(string? assetTag, string? serialNumber) =>
		IsRecorded(assetTag) || IsRecorded(serialNumber) ? 1 : 0;

	public static int CountMonitors(Asset asset) =>
		HasMonitor(asset.Monitor1AssetTag, asset.Monitor1SerialNumber)
		+ HasMonitor(asset.Monitor2AssetTag, asset.Monitor2SerialNumber)
		+ HasMonitor(asset.Monitor3AssetTag, asset.Monitor3SerialNumber);

	private static bool IsRecorded(string? value) =>
		!string.IsNullOrWhiteSpace(value)
		&& value.Trim() is not "N/A" and not "NA" and not "-" and not "--";

	public async Task<IActionResult> OnGetExportAsync(CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(User, "Assets.Export")).Succeeded)
		{
			return Forbid();
		}
		int[] assetIds = await ApplyFilters(
				db.Assets.AsNoTracking().Where(asset => !asset.IsArchived))
			.Select(asset => asset.AssetId)
			.ToArrayAsync(cancellationToken);
		string templatePath = Path.Combine(
			environment.ContentRootPath,
			"SeedData",
			"Asset inventory US template.xlsx");
		await using MemoryStream workbook = await exportService.ExportAsync(
			templatePath,
			cancellationToken,
			assetIds);
		return File(
			workbook.ToArray(),
			"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
			$"AssetPilot-Inventory-{DateTime.UtcNow:yyyyMMdd}.xlsx");
	}

	private IQueryable<Asset> ApplyFilters(IQueryable<Asset> source)
	{
		if (!string.Equals(View, "All", StringComparison.OrdinalIgnoreCase))
		{
			source = source.Where(asset =>
				asset.AssetType.ToLower().Contains("laptop")
				|| asset.AssetType.ToLower().Contains("desktop")
				|| asset.AssetType.ToLower().Contains("macbook")
				|| asset.AssetType.ToLower() == "mac"
				|| (asset.Workstation != null
					&& (asset.Workstation.ToLower().Contains("laptop")
						|| asset.Workstation.ToLower().Contains("desktop")
						|| asset.Workstation.ToLower().Contains("macbook")
						|| asset.Workstation.ToLower() == "mac")));
		}
		if (!string.IsNullOrWhiteSpace(Query))
		{
			string query = Query.Trim().ToLower();
			source = source.Where(asset =>
				asset.AssetTag.ToLower().Contains(query)
				|| (asset.Hostname != null && asset.Hostname.ToLower().Contains(query))
				|| (asset.SerialNumber != null && asset.SerialNumber.ToLower().Contains(query))
				|| asset.Name.ToLower().Contains(query)
				|| asset.Status.ToLower().Contains(query)
				|| asset.Condition.ToLower().Contains(query)
				|| asset.Category.ToLower().Contains(query)
				|| asset.AssetType.ToLower().Contains(query)
				|| (asset.Manufacturer != null && asset.Manufacturer.ToLower().Contains(query))
				|| (asset.Model != null && asset.Model.ToLower().Contains(query))
				|| (asset.AssignedTo != null && asset.AssignedTo.ToLower().Contains(query))
				|| (asset.AssignedToEmail != null && asset.AssignedToEmail.ToLower().Contains(query))
				|| (asset.EmployeeNumber != null && asset.EmployeeNumber.ToLower().Contains(query))
				|| (asset.Department != null && asset.Department.ToLower().Contains(query))
				|| (asset.Designation != null && asset.Designation.ToLower().Contains(query))
				|| (asset.Location != null && asset.Location.ToLower().Contains(query))
				|| (asset.CurrentLocation != null && asset.CurrentLocation.ToLower().Contains(query))
				|| (asset.Vendor != null && asset.Vendor.ToLower().Contains(query))
				|| (asset.Purpose != null && asset.Purpose.ToLower().Contains(query))
				|| (asset.Company != null && asset.Company.ToLower().Contains(query))
				|| (asset.Project != null && asset.Project.ToLower().Contains(query))
				|| (asset.MacAddress != null && asset.MacAddress.ToLower().Contains(query))
				|| (asset.Monitor1AssetTag != null && asset.Monitor1AssetTag.ToLower().Contains(query))
				|| (asset.Monitor1SerialNumber != null && asset.Monitor1SerialNumber.ToLower().Contains(query))
				|| (asset.Monitor2AssetTag != null && asset.Monitor2AssetTag.ToLower().Contains(query))
				|| (asset.Monitor2SerialNumber != null && asset.Monitor2SerialNumber.ToLower().Contains(query))
				|| (asset.Monitor3AssetTag != null && asset.Monitor3AssetTag.ToLower().Contains(query))
				|| (asset.Monitor3SerialNumber != null && asset.Monitor3SerialNumber.ToLower().Contains(query))
				|| (asset.OfficeWorkMode != null && asset.OfficeWorkMode.ToLower().Contains(query))
				|| (asset.Workstation != null && asset.Workstation.ToLower().Contains(query))
				|| (asset.ServiceRequestTicket != null && asset.ServiceRequestTicket.ToLower().Contains(query))
				|| (asset.OwnerName != null && asset.OwnerName.ToLower().Contains(query))
				|| (asset.OwnerEmail != null && asset.OwnerEmail.ToLower().Contains(query))
				|| (asset.Classification != null && asset.Classification.ToLower().Contains(query))
				|| (asset.Severity != null && asset.Severity.ToLower().Contains(query))
				|| (asset.Remarks != null && asset.Remarks.ToLower().Contains(query))
				|| (asset.NewReplacementStatus != null && asset.NewReplacementStatus.ToLower().Contains(query))
				|| (asset.DockingStation != null && asset.DockingStation.ToLower().Contains(query))
				|| (asset.Keyboard != null && asset.Keyboard.ToLower().Contains(query))
				|| (asset.Mouse != null && asset.Mouse.ToLower().Contains(query))
				|| (asset.Headset != null && asset.Headset.ToLower().Contains(query))
				|| (asset.Printer != null && asset.Printer.ToLower().Contains(query)));
		}
		if (!string.IsNullOrWhiteSpace(Status))
		{
			source = source.Where((Asset asset) => asset.Status == Status);
		}
		return source;
	}
}

public sealed record AssetInventoryGroup(
	string? Email,
	string DisplayName,
	IReadOnlyList<Asset> Assets,
	string TypeSummary,
	string LocationSummary,
	int MonitorCount,
	string StatusSummary,
	string StatusClass);
