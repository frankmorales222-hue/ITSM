using System;
using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Security.Claims;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Auditing;
using AssetPilot.Domain.Assets;
using AssetPilot.Domain.Auditing;
using AssetPilot.Domain.People;
using AssetPilot.Domain.Shipments;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Web.Pages.Assets;

public sealed class DetailsModel(AssetPilotDbContext db, IAuditService audit, IAuthorizationService authorization) : PageModel
{
	public sealed record MonitorSummary(int Number, string? AssetTag, string? SerialNumber)
	{
		public bool IsComplete => !string.IsNullOrWhiteSpace(AssetTag) && !string.IsNullOrWhiteSpace(SerialNumber);
		public string Warning => AssetTag is null && SerialNumber is null
			? "No monitor information recorded"
			: AssetTag is null
				? "Monitor asset tag is missing"
				: SerialNumber is null
					? "Monitor serial number is missing"
					: "";
	}
	public sealed class NetworkAddressInput
	{
		public static IReadOnlyList<string> Types { get; } = new global::_003C_003Ez__ReadOnlyArray<string>(new string[4] { "MAC", "IPv4", "IPv6", "Other" });

		public string AddressType { get; set; } = "MAC";

		[Required]
		[StringLength(200)]
		public string Address { get; set; } = "";

		public bool IsPrimary { get; set; }

		[StringLength(500)]
		public string? Notes { get; set; }
	}

	public Asset Asset { get; private set; }

	public IReadOnlyList<AuditEvent> AuditHistory { get; private set; } = Array.Empty<AuditEvent>();

	public IReadOnlyList<Employee> AvailableEmployees { get; private set; } = Array.Empty<Employee>();

	public IReadOnlyList<Asset> AssociatedAssets { get; private set; } = Array.Empty<Asset>();

	public IReadOnlyList<MonitorSummary> Monitors => new[]
	{
		new MonitorSummary(1, Asset.Monitor1AssetTag, Asset.Monitor1SerialNumber),
		new MonitorSummary(2, Asset.Monitor2AssetTag, Asset.Monitor2SerialNumber),
		new MonitorSummary(3, Asset.Monitor3AssetTag, Asset.Monitor3SerialNumber)
	};

	public int MonitorWarningCount => Monitors.Count(monitor => !monitor.IsComplete);

	[BindProperty]
	public NetworkAddressInput NetworkInput { get; set; } = new NetworkAddressInput();

	[BindProperty]
	public int EmployeeId { get; set; }

	[BindProperty]
	[StringLength(500)]
	public string? AssignmentNotes { get; set; }

	[BindProperty(SupportsGet = true)]
	public string? ReturnUrl { get; set; }

	public string BackLabel =>
		ReturnUrl?.Contains("/Assets/Stock", StringComparison.OrdinalIgnoreCase) == true
			? "Back to available stock"
			: ReturnUrl?.Contains("/Employees/", StringComparison.OrdinalIgnoreCase) == true
				? "Back to employee"
				: ReturnUrl == "/"
					? "Back to dashboard"
					: ReturnUrl?.Contains("/Search", StringComparison.OrdinalIgnoreCase) == true
						? "Back to search results"
						: ReturnUrl?.Contains("/Reports", StringComparison.OrdinalIgnoreCase) == true
							? "Back to reports"
							: "Back to asset inventory";

	public string AssetAge
	{
		get
		{
			DateOnly? purchaseDate = Asset.PurchaseDate;
			if (purchaseDate.HasValue)
			{
				DateOnly valueOrDefault = purchaseDate.GetValueOrDefault();
				return $"{Math.Max(0, DateOnly.FromDateTime(DateTime.Today).DayNumber - valueOrDefault.DayNumber)} days";
			}
			return "—";
		}
	}

	public async Task<IActionResult> OnGetAsync(int id, CancellationToken cancellationToken)
	{
		ReturnUrl = IsSafeReturnUrl(ReturnUrl) ? ReturnUrl : "/Assets";
		Asset asset = await db.Assets.AsNoTracking().AsSplitQuery().Include((Asset x) => x.NetworkAddresses)
			.Include((Asset x) => x.StatusHistory)
			.Include((Asset x) => x.Assignments)
			.ThenInclude((AssetAssignment x) => x.Employee)
			.Include((Asset x) => x.ShipmentItems)
			.ThenInclude((ShipmentItem x) => x.Shipment)
			.SingleOrDefaultAsync((Asset x) => x.AssetId == id && !x.IsArchived, cancellationToken);
		if (asset == null)
		{
			return NotFound();
		}
		Asset = asset;
		if (!string.IsNullOrWhiteSpace(asset.AssignedToEmail))
		{
			string email = asset.AssignedToEmail.ToLower();
			AssociatedAssets = await db.Assets.AsNoTracking()
				.Where(x => !x.IsArchived && x.AssetId != id
					&& x.AssignedToEmail != null && x.AssignedToEmail.ToLower() == email)
				.OrderBy(x => x.AssetType)
				.ThenBy(x => x.Hostname ?? x.AssetTag)
				.ToListAsync(cancellationToken);
		}
		else if (!string.IsNullOrWhiteSpace(asset.EmployeeNumber))
		{
			string employeeNumber = asset.EmployeeNumber.ToLower();
			AssociatedAssets = await db.Assets.AsNoTracking()
				.Where(x => !x.IsArchived && x.AssetId != id
					&& x.EmployeeNumber != null && x.EmployeeNumber.ToLower() == employeeNumber)
				.OrderBy(x => x.AssetType)
				.ThenBy(x => x.Hostname ?? x.AssetTag)
				.ToListAsync(cancellationToken);
		}
		AuditHistory = await (from item in db.AuditEvents.AsNoTracking()
			where item.EntityTypeCode == "Asset" && item.EntityId == ((int)id).ToString()
			orderby item.EventUtc descending
			select item).Take(20).ToListAsync(cancellationToken);
		AvailableEmployees = await db.Employees.AsNoTracking()
			.Where(x => x.IsActive && !x.IsDeleted)
			.OrderBy(x => x.DisplayName)
			.ToListAsync(cancellationToken);
		return Page();
	}

	public async Task<IActionResult> OnPostAssignAsync(int id, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(User, "Assets.Assign")).Succeeded)
		{
			return Forbid();
		}
		Asset? asset = await db.Assets
			.Include(x => x.Assignments.Where(a => a.ReturnedUtc == null))
			.ThenInclude(a => a.Employee)
			.SingleOrDefaultAsync(x => x.AssetId == id && !x.IsArchived, cancellationToken);
		Employee? employee = await db.Employees.SingleOrDefaultAsync(
			x => x.EmployeeId == EmployeeId && x.IsActive && !x.IsDeleted,
			cancellationToken);
		if (asset is null || employee is null)
		{
			return NotFound();
		}
		AssetAssignment? current = asset.Assignments.SingleOrDefault(a => a.ReturnedUtc == null);
		if (current?.EmployeeId == employee.EmployeeId)
		{
			TempData["Warning"] = $"{asset.AssetTag} is already assigned to {employee.DisplayName}.";
			return RedirectToPage(new { id, ReturnUrl });
		}
		DateTime now = DateTime.UtcNow;
		string? priorEmployee = current?.Employee.DisplayName;
		if (current is not null)
		{
			current.ReturnedUtc = now;
			current.ReturnedByUserId = User.FindFirstValue(ClaimTypes.NameIdentifier);
			current.ReturnCondition = asset.Condition;
			current.ReturnNotes = $"Transferred to {employee.DisplayName}. {Clean(AssignmentNotes)}".Trim();
		}
		db.AssetAssignments.Add(new AssetAssignment
		{
			Asset = asset,
			Employee = employee,
			AssignedUtc = now,
			AssignedByUserId = User.FindFirstValue(ClaimTypes.NameIdentifier),
			AssignedLocation = employee.Location,
			Notes = Clean(AssignmentNotes)
		});
		string previousStatus = asset.Status;
		asset.AssignedTo = employee.DisplayName;
		asset.AssignedToEmail = employee.Email;
		asset.EmployeeNumber = employee.EmployeeNumber;
		asset.Department = employee.Department;
		asset.Location = employee.Location;
		asset.CurrentLocation = employee.Location;
		asset.Status = "Active";
		asset.ModifiedUtc = now;
		asset.Version++;
		if (!previousStatus.Equals(asset.Status, StringComparison.OrdinalIgnoreCase))
		{
			asset.StatusHistory.Add(new AssetStatusHistory
			{
				FromStatus = previousStatus,
				ToStatus = asset.Status,
				ChangedUtc = now,
				ChangedByUserId = User.FindFirstValue(ClaimTypes.NameIdentifier),
				Reason = current is null ? "Assigned to employee" : "Transferred to employee"
			});
		}
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync(
			current is null ? "Asset.Assigned" : "Asset.Transferred",
			"Asset",
			id.ToString(),
			User.FindFirstValue(ClaimTypes.NameIdentifier),
			new { AssignedTo = priorEmployee, Status = previousStatus },
			new { employee.EmployeeId, employee.DisplayName, asset.Status },
			Clean(AssignmentNotes),
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = current is null
			? $"{asset.AssetTag} was assigned to {employee.DisplayName}."
			: $"{asset.AssetTag} was transferred from {priorEmployee} to {employee.DisplayName}.";
		return RedirectToPage(new { id, ReturnUrl });
	}

	public async Task<IActionResult> OnPostReturnToStockAsync(int id, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(User, "Assets.Assign")).Succeeded)
		{
			return Forbid();
		}
		AssetAssignment? current = await db.AssetAssignments
			.Include(x => x.Asset)
			.Include(x => x.Employee)
			.SingleOrDefaultAsync(x => x.AssetId == id && x.ReturnedUtc == null, cancellationToken);
		if (current is null)
		{
			TempData["Warning"] = "This asset has no active assignment.";
			return RedirectToPage(new { id, ReturnUrl });
		}
		DateTime now = DateTime.UtcNow;
		Asset asset = current.Asset;
		string previousStatus = asset.Status;
		current.ReturnedUtc = now;
		current.ReturnedByUserId = User.FindFirstValue(ClaimTypes.NameIdentifier);
		current.ReturnCondition = asset.Condition;
		current.ReturnNotes = Clean(AssignmentNotes);
		asset.AssignedTo = null;
		asset.AssignedToEmail = null;
		asset.EmployeeNumber = null;
		asset.Department = null;
		asset.Status = "In Stock";
		asset.ModifiedUtc = now;
		asset.Version++;
		asset.StatusHistory.Add(new AssetStatusHistory
		{
			FromStatus = previousStatus,
			ToStatus = "In Stock",
			ChangedUtc = now,
			ChangedByUserId = User.FindFirstValue(ClaimTypes.NameIdentifier),
			Reason = "Returned to available stock"
		});
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync(
			"Asset.Returned",
			"Asset",
			id.ToString(),
			User.FindFirstValue(ClaimTypes.NameIdentifier),
			new { current.EmployeeId, current.Employee.DisplayName, Status = previousStatus },
			new { asset.Status, asset.Condition },
			Clean(AssignmentNotes),
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = $"{asset.AssetTag} was returned to available stock.";
		return RedirectToPage(new { id, ReturnUrl });
	}

	public async Task<IActionResult> OnPostAddNetworkAsync(int id, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(base.User, "Assets.Edit")).Succeeded)
		{
			return Forbid();
		}
		NormalizeNetworkInput();
		if (!NetworkAddressInput.Types.Contains<string>(NetworkInput.AddressType, StringComparer.Ordinal))
		{
			base.ModelState.AddModelError("NetworkInput.AddressType", "Choose a valid address type.");
		}
		if (await db.AssetNetworkAddresses.AnyAsync((AssetNetworkAddress item) => item.AssetId == id && item.AddressType == NetworkInput.AddressType && item.Address == NetworkInput.Address, cancellationToken))
		{
			base.ModelState.AddModelError("NetworkInput.Address", "That network address is already recorded for this asset.");
		}
		if (!base.ModelState.IsValid)
		{
			await OnGetAsync(id, cancellationToken);
			return Page();
		}
		if (!(await db.Assets.AnyAsync((Asset item) => item.AssetId == id && !item.IsArchived, cancellationToken)))
		{
			return NotFound();
		}
		DateTime utcNow = DateTime.UtcNow;
		AssetNetworkAddress address = new AssetNetworkAddress
		{
			AssetId = id,
			AddressType = NetworkInput.AddressType,
			Address = NetworkInput.Address,
			IsPrimary = NetworkInput.IsPrimary,
			Notes = NetworkInput.Notes,
			CreatedUtc = utcNow,
			ModifiedUtc = utcNow
		};
		db.AssetNetworkAddresses.Add(address);
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync("Asset.NetworkAddressAdded", "Asset", id.ToString(), base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), null, new { address.AssetNetworkAddressId, address.AddressType, address.Address, address.IsPrimary }, null, base.HttpContext.TraceIdentifier, cancellationToken);
		base.TempData["Success"] = "The network address was added.";
		return RedirectToPage(new { id, ReturnUrl });
	}

	public async Task<IActionResult> OnPostRemoveNetworkAsync(int id, int addressId, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(base.User, "Assets.Edit")).Succeeded)
		{
			return Forbid();
		}
		AssetNetworkAddress assetNetworkAddress = await db.AssetNetworkAddresses.SingleOrDefaultAsync((AssetNetworkAddress item) => item.AssetNetworkAddressId == addressId && item.AssetId == id, cancellationToken);
		if (assetNetworkAddress == null)
		{
			return NotFound();
		}
		var before = new { assetNetworkAddress.AssetNetworkAddressId, assetNetworkAddress.AddressType, assetNetworkAddress.Address, assetNetworkAddress.IsPrimary };
		db.AssetNetworkAddresses.Remove(assetNetworkAddress);
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync("Asset.NetworkAddressRemoved", "Asset", id.ToString(), base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), before, null, "Removed from asset identification", base.HttpContext.TraceIdentifier, cancellationToken);
		base.TempData["Success"] = "The network address was removed.";
		return RedirectToPage(new { id, ReturnUrl });
	}

	public async Task<IActionResult> OnPostArchiveAsync(int id, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(base.User, "Assets.Archive")).Succeeded)
		{
			return Forbid();
		}
		Asset asset = await db.Assets.SingleOrDefaultAsync((Asset x) => x.AssetId == id && !x.IsArchived, cancellationToken);
		if (asset == null)
		{
			return NotFound();
		}
		var before = new { asset.AssetTag, asset.Status, asset.IsArchived };
		asset.IsArchived = true;
		asset.ModifiedUtc = DateTime.UtcNow;
		asset.Version++;
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync("Asset.Archived", "Asset", asset.AssetId.ToString(), base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), before, new { asset.AssetTag, asset.Status, asset.IsArchived }, null, base.HttpContext.TraceIdentifier, cancellationToken);
		base.TempData["Success"] = asset.AssetTag + " was archived.";
		return RedirectToPage("Index");
	}

	private void NormalizeNetworkInput()
	{
		NetworkInput.AddressType = NetworkInput.AddressType.Trim();
		NetworkInput.Address = NetworkInput.Address.Trim();
		NetworkInput.Notes = (string.IsNullOrWhiteSpace(NetworkInput.Notes) ? null : NetworkInput.Notes.Trim());
	}

	private static string? Clean(string? value) =>
		string.IsNullOrWhiteSpace(value) ? null : value.Trim();

	private bool IsSafeReturnUrl(string? value) =>
		!string.IsNullOrWhiteSpace(value) && Url.IsLocalUrl(value);
}
