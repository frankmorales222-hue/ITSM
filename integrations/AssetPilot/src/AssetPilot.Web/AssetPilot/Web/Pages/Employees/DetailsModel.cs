using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Claims;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Auditing;
using AssetPilot.Domain.Assets;
using AssetPilot.Domain.People;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Web.Pages.Employees;

public sealed class DetailsModel(AssetPilotDbContext db, IAuditService audit, IAuthorizationService authorization) : PageModel
{
	public Employee Employee { get; private set; }

	public IReadOnlyList<Asset> AvailableAssets { get; private set; } = Array.Empty<Asset>();

	[BindProperty]
	public int AssetId { get; set; }

	[BindProperty]
	public string? Notes { get; set; }

	[BindProperty]
	public string ReturnCondition { get; set; } = "Good";

	public async Task<IActionResult> OnGetAsync(int id, CancellationToken cancellationToken)
	{
		Employee employee = await db.Employees.AsNoTracking().AsSplitQuery().Include((Employee x) => x.Assignments)
			.ThenInclude((AssetAssignment x) => x.Asset)
			.SingleOrDefaultAsync((Employee x) => x.EmployeeId == id && !x.IsDeleted, cancellationToken);
		if (employee == null)
		{
			return NotFound();
		}
		Employee = employee;
		List<int> assignedIds = await (from x in db.AssetAssignments
			where x.ReturnedUtc == null
			select x.AssetId).ToListAsync(cancellationToken);
		AvailableAssets = await (from x in db.Assets.AsNoTracking()
			where !x.IsArchived && x.Status == "In Stock" && !assignedIds.Contains(x.AssetId)
			orderby x.AssetTag
			select x).Take(1000).ToListAsync(cancellationToken);
		return Page();
	}

	public async Task<IActionResult> OnPostAssignAsync(int id, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(base.User, "Assets.Assign")).Succeeded)
		{
			return Forbid();
		}
		Employee employee = await db.Employees.SingleOrDefaultAsync((Employee x) => x.EmployeeId == id && x.IsActive && !x.IsDeleted, cancellationToken);
		Asset asset = await db.Assets.SingleOrDefaultAsync((Asset x) => x.AssetId == AssetId && !x.IsArchived, cancellationToken);
		if (employee == null || asset == null)
		{
			return NotFound();
		}
		if (await db.AssetAssignments.AnyAsync((AssetAssignment x) => x.AssetId == AssetId && x.ReturnedUtc == null, cancellationToken))
		{
			base.ModelState.AddModelError(string.Empty, "That asset is already assigned.");
			return await OnGetAsync(id, cancellationToken);
		}
		DateTime utcNow = DateTime.UtcNow;
		db.AssetAssignments.Add(new AssetAssignment
		{
			Asset = asset,
			Employee = employee,
			AssignedUtc = utcNow,
			AssignedByUserId = base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"),
			AssignedLocation = employee.Location,
			Notes = Clean(Notes)
		});
		string status = asset.Status;
		asset.AssignedTo = employee.DisplayName;
		asset.AssignedToEmail = employee.Email;
		asset.EmployeeNumber = employee.EmployeeNumber;
		asset.Department = employee.Department;
		asset.Location = employee.Location;
		asset.CurrentLocation = employee.Location;
		asset.Status = "Active";
		asset.ModifiedUtc = utcNow;
		asset.Version++;
		if (!status.Equals(asset.Status, StringComparison.OrdinalIgnoreCase))
		{
			asset.StatusHistory.Add(History(asset, status, "Active", utcNow, "Assigned to employee"));
		}
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync("Asset.Assigned", "Asset", asset.AssetId.ToString(), base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), null, new { employee.EmployeeId, employee.DisplayName, asset.AssetTag }, Clean(Notes), base.HttpContext.TraceIdentifier, cancellationToken);
		base.TempData["Success"] = asset.AssetTag + " was assigned to " + employee.DisplayName + ".";
		return RedirectToPage(new { id });
	}

	public async Task<IActionResult> OnPostReturnAsync(int id, int assignmentId, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(base.User, "Assets.Assign")).Succeeded)
		{
			return Forbid();
		}
		AssetAssignment assignment = await db.AssetAssignments.Include((AssetAssignment x) => x.Asset).Include((AssetAssignment x) => x.Employee).SingleOrDefaultAsync((AssetAssignment x) => x.AssetAssignmentId == assignmentId && x.EmployeeId == id && x.ReturnedUtc == null, cancellationToken);
		if (assignment == null)
		{
			return NotFound();
		}
		DateTime utcNow = DateTime.UtcNow;
		assignment.ReturnedUtc = utcNow;
		assignment.ReturnedByUserId = base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier");
		assignment.ReturnCondition = Clean(ReturnCondition) ?? "Good";
		assignment.ReturnNotes = Clean(Notes);
		Asset asset = assignment.Asset;
		string status = asset.Status;
		asset.AssignedTo = null;
		asset.AssignedToEmail = null;
		asset.EmployeeNumber = null;
		asset.Department = null;
		asset.Status = "In Stock";
		asset.Condition = assignment.ReturnCondition;
		asset.ModifiedUtc = utcNow;
		asset.Version++;
		asset.StatusHistory.Add(History(asset, status, "In Stock", utcNow, "Returned from employee"));
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync("Asset.Returned", "Asset", asset.AssetId.ToString(), base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), new { assignment.Employee.DisplayName }, new { asset.AssetTag, asset.Status, asset.Condition }, assignment.ReturnNotes, base.HttpContext.TraceIdentifier, cancellationToken);
		base.TempData["Success"] = asset.AssetTag + " was returned to stock.";
		return RedirectToPage(new { id });
	}

	public async Task<IActionResult> OnPostToggleActiveAsync(int id, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(base.User, "Employees.Manage")).Succeeded)
		{
			return Forbid();
		}
		Employee employee = await db.Employees.SingleOrDefaultAsync((Employee x) => x.EmployeeId == id && !x.IsDeleted, cancellationToken);
		if (employee == null)
		{
			return NotFound();
		}
		bool flag = employee.IsActive;
		if (flag)
		{
			flag = await db.AssetAssignments.AnyAsync((AssetAssignment x) => x.EmployeeId == id && x.ReturnedUtc == null, cancellationToken);
		}
		if (flag)
		{
			base.ModelState.AddModelError(string.Empty, "Return or transfer this employee's assets before deactivating them.");
			return await OnGetAsync(id, cancellationToken);
		}
		employee.IsActive = !employee.IsActive;
		employee.ModifiedUtc = DateTime.UtcNow;
		employee.Version++;
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync("Employee.StatusChanged", "Employee", id.ToString(), base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), null, new { employee.IsActive }, null, base.HttpContext.TraceIdentifier, cancellationToken);
		return RedirectToPage(new { id });
	}

	private AssetStatusHistory History(Asset asset, string from, string to, DateTime now, string reason)
	{
		return new AssetStatusHistory
		{
			Asset = asset,
			FromStatus = from,
			ToStatus = to,
			ChangedUtc = now,
			ChangedByUserId = base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"),
			Reason = reason
		};
	}

	private static string? Clean(string? value)
	{
		if (!string.IsNullOrWhiteSpace(value))
		{
			return value.Trim();
		}
		return null;
	}
}
