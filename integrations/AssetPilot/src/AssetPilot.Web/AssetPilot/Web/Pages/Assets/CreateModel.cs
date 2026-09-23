using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Claims;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Auditing;
using AssetPilot.Domain.Assets;
using AssetPilot.Domain.MasterData;
using AssetPilot.Domain.People;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Web.Pages.Assets;

[Authorize(Policy = "Assets.Create")]
public sealed class CreateModel(AssetPilotDbContext db, IAuditService audit) : PageModel
{
	[BindProperty]
	public AssetInput Input { get; set; } = new AssetInput();

	[BindProperty]
	public int? EmployeeId { get; set; }

	public async Task OnGetAsync(int? employeeId, bool stock, CancellationToken cancellationToken)
	{
		EmployeeId = employeeId;
		if (stock)
		{
			Input.Status = "In Stock";
		}
		if (employeeId.HasValue)
		{
			Employee? employee = await db.Employees.AsNoTracking()
				.SingleOrDefaultAsync(x => x.EmployeeId == employeeId && x.IsActive && !x.IsDeleted, cancellationToken);
			if (employee is not null)
			{
				Input.AssignedTo = employee.DisplayName;
				Input.AssignedToEmail = employee.Email;
				Input.EmployeeNumber = employee.EmployeeNumber;
				Input.Department = employee.Department;
				Input.Location = employee.Location;
				Input.CurrentLocation = employee.Location;
			}
		}
		await LoadReferenceOptionsAsync(cancellationToken);
	}

	public async Task<IActionResult> OnPostAsync(CancellationToken cancellationToken)
	{
		Normalize();
		bool flag = !base.ModelState.IsValid;
		if (!flag)
		{
			flag = !(await IsUniqueAsync(null, cancellationToken));
		}
		if (flag)
		{
			await LoadReferenceOptionsAsync(cancellationToken);
			return Page();
		}
		DateTime utcNow = DateTime.UtcNow;
		Asset asset = new Asset
		{
			AssetTag = Input.AssetTag,
			Name = Input.Name,
			Status = Input.Status,
			Condition = Input.Condition,
			Category = Input.Category,
			AssetType = Input.AssetType,
			CreatedUtc = utcNow,
			ModifiedUtc = utcNow
		};
		Input.ApplyTo(asset);
		asset.StatusHistory.Add(new AssetStatusHistory
		{
			ToStatus = asset.Status,
			ChangedUtc = utcNow,
			ChangedByUserId = base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"),
			Reason = "Asset created"
		});
		db.Assets.Add(asset);
		if (EmployeeId.HasValue)
		{
			Employee? employee = await db.Employees
				.SingleOrDefaultAsync(x => x.EmployeeId == EmployeeId && x.IsActive && !x.IsDeleted, cancellationToken);
			if (employee is null)
			{
				base.ModelState.AddModelError(string.Empty, "The selected employee is no longer available.");
				await LoadReferenceOptionsAsync(cancellationToken);
				return Page();
			}
			asset.Assignments.Add(new AssetAssignment
			{
				Employee = employee,
				AssignedUtc = utcNow,
				AssignedByUserId = base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"),
				AssignedLocation = Input.CurrentLocation ?? Input.Location,
				Notes = "Assigned while creating employee asset"
			});
		}
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync("Asset.Created", "Asset", asset.AssetId.ToString(), base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), null, asset, null, base.HttpContext.TraceIdentifier, cancellationToken);
		base.TempData["Success"] = asset.AssetTag + " was added.";
		return RedirectToPage("Details", new
		{
			id = asset.AssetId
		});
	}

	private void Normalize()
	{
		Input.Normalize();
	}

	private async Task<bool> IsUniqueAsync(int? id, CancellationToken cancellationToken)
	{
		bool duplicateTag = await db.Assets.AnyAsync((Asset x) => (int?)x.AssetId != id && x.AssetTag == Input.AssetTag, cancellationToken);
		bool flag = Input.Hostname != null;
		if (flag)
		{
			flag = await db.Assets.AnyAsync((Asset x) => (int?)x.AssetId != id && x.Hostname == Input.Hostname, cancellationToken);
		}
		bool duplicateHostname = flag;
		flag = Input.SerialNumber != null;
		if (flag)
		{
			flag = await db.Assets.AnyAsync((Asset x) => (int?)x.AssetId != id && x.SerialNumber == Input.SerialNumber, cancellationToken);
		}
		bool flag2 = flag;
		if (duplicateTag)
		{
			base.ModelState.AddModelError("Input.AssetTag", "That asset tag is already in use.");
		}
		if (duplicateHostname)
		{
			base.ModelState.AddModelError("Input.Hostname", "That hostname is already in use.");
		}
		if (flag2)
		{
			base.ModelState.AddModelError("Input.SerialNumber", "That serial number is already in use.");
		}
		return !duplicateTag && !duplicateHostname && !flag2;
	}

	private async Task LoadReferenceOptionsAsync(CancellationToken cancellationToken)
	{
		var source = await (from item in db.ReferenceDataItems.AsNoTracking()
			where item.IsActive
			orderby item.Name
			select new { item.Kind, item.Name }).ToListAsync(cancellationToken);
		base.ViewData["ReferenceOptions"] = (from item in source
			group item by item.Kind).ToDictionary(group => group.Key, group => (IReadOnlyList<string>)group.Select(item => item.Name).ToList());
	}
}
