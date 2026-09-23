using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Security.Claims;
using AssetPilot.Application.Auditing;
using AssetPilot.Domain.People;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Web.Pages.Employees;

public sealed class IndexModel(
	AssetPilotDbContext db,
	IAuditService audit,
	IAuthorizationService authorization) : PageModel
{
	public sealed record EmployeeRow(int Id, string Number, string Name, string Email, string? Department, string? Location, bool IsActive, int AssignedAssets);

	[BindProperty(SupportsGet = true)]
	public string? Query { get; set; }

	[BindProperty(SupportsGet = true)]
	public bool ShowInactive { get; set; }

	public IReadOnlyList<EmployeeRow> Employees { get; private set; } = Array.Empty<EmployeeRow>();

	public async Task OnGetAsync(CancellationToken cancellationToken)
	{
		IQueryable<Employee> source = db.Employees.AsNoTracking().Where(x => !x.IsDeleted);
		if (!ShowInactive)
		{
			source = source.Where((Employee x) => x.IsActive);
		}
		if (!string.IsNullOrWhiteSpace(Query))
		{
			string value = Query.Trim().ToLower();
			source = source.Where(x =>
				x.DisplayName.ToLower().Contains(value)
				|| x.Email.ToLower().Contains(value)
				|| x.EmployeeNumber.ToLower().Contains(value)
				|| (x.Department != null && x.Department.ToLower().Contains(value))
				|| (x.Location != null && x.Location.ToLower().Contains(value))
				|| (x.Manager != null && x.Manager.ToLower().Contains(value))
				|| (x.Phone != null && x.Phone.ToLower().Contains(value)));
		}
		Employees = await (from x in source
			orderby x.DisplayName
			select new EmployeeRow(x.EmployeeId, x.EmployeeNumber, x.DisplayName, x.Email, x.Department, x.Location, x.IsActive, x.Assignments.Count((AssetAssignment a) => a.ReturnedUtc == null))).ToListAsync(cancellationToken);
	}

	public async Task<IActionResult> OnPostDeleteAsync(int id, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(User, "Employees.Manage")).Succeeded)
		{
			return Forbid();
		}
		Employee? employee = await db.Employees
			.SingleOrDefaultAsync(x => x.EmployeeId == id && !x.IsDeleted, cancellationToken);
		if (employee is null)
		{
			return NotFound();
		}
		if (employee.IsActive)
		{
			TempData["Error"] = "Active employees cannot be deleted. Disable the employee first.";
			return RedirectToPage(new { ShowInactive = true });
		}
		if (await db.AssetAssignments.AnyAsync(
			x => x.EmployeeId == id && x.ReturnedUtc == null,
			cancellationToken))
		{
			TempData["Error"] = "Return or transfer this employee's assets before deleting the employee.";
			return RedirectToPage(new { ShowInactive = true });
		}
		employee.IsDeleted = true;
		employee.ModifiedUtc = DateTime.UtcNow;
		employee.Version++;
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync(
			"Employee.Deleted",
			"Employee",
			id.ToString(),
			User.FindFirstValue(ClaimTypes.NameIdentifier),
			new { employee.EmployeeNumber, employee.DisplayName, employee.Email, employee.IsActive },
			new { employee.IsDeleted },
			"Disabled employee removed from employee management",
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = employee.DisplayName + " was deleted.";
		return RedirectToPage(new { ShowInactive = true });
	}
}
