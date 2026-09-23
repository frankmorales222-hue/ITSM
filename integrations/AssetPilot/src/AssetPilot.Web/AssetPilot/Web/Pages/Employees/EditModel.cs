using System;
using System.ComponentModel.DataAnnotations;
using System.Security.Claims;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Auditing;
using AssetPilot.Domain.People;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Web.Pages.Employees;

[Authorize(Policy = "Employees.Manage")]
public sealed class EditModel(AssetPilotDbContext db, IAuditService audit) : PageModel
{
	public sealed class InputModel
	{
		[Required]
		[StringLength(80)]
		public string EmployeeNumber { get; set; } = "";

		[Required]
		[StringLength(200)]
		public string DisplayName { get; set; } = "";

		[Required]
		[EmailAddress]
		[StringLength(255)]
		public string Email { get; set; } = "";

		[StringLength(150)]
		public string? Department { get; set; }

		[StringLength(200)]
		public string? Manager { get; set; }

		[StringLength(150)]
		public string? Location { get; set; }

		[StringLength(50)]
		public string? Phone { get; set; }

		public void Normalize()
		{
			EmployeeNumber = EmployeeNumber.Trim();
			DisplayName = DisplayName.Trim();
			Email = Email.Trim();
			Department = Clean(Department);
			Manager = Clean(Manager);
			Location = Clean(Location);
			Phone = Clean(Phone);
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

	[BindProperty]
	public int Id { get; set; }

	[BindProperty]
	public int Version { get; set; }

	[BindProperty]
	public InputModel Input { get; set; } = new InputModel();

	public async Task<IActionResult> OnGetAsync(int id, CancellationToken token)
	{
		Employee employee = await db.Employees.AsNoTracking().SingleOrDefaultAsync((Employee x) => x.EmployeeId == id && !x.IsDeleted, token);
		if (employee == null)
		{
			return NotFound();
		}
		Id = id;
		Version = employee.Version;
		Input = new InputModel
		{
			EmployeeNumber = employee.EmployeeNumber,
			DisplayName = employee.DisplayName,
			Email = employee.Email,
			Department = employee.Department,
			Manager = employee.Manager,
			Location = employee.Location,
			Phone = employee.Phone
		};
		return Page();
	}

	public async Task<IActionResult> OnPostAsync(CancellationToken token)
	{
		Input.Normalize();
		if (await db.Employees.AnyAsync((Employee x) => !x.IsDeleted && x.EmployeeId != Id && x.EmployeeNumber == Input.EmployeeNumber, token))
		{
			base.ModelState.AddModelError("Input.EmployeeNumber", "That employee number is already in use.");
		}
		if (await db.Employees.AnyAsync((Employee x) => !x.IsDeleted && x.EmployeeId != Id && x.Email == Input.Email, token))
		{
			base.ModelState.AddModelError("Input.Email", "That email address is already in use.");
		}
		if (!base.ModelState.IsValid)
		{
			return Page();
		}
		Employee employee = await db.Employees.SingleOrDefaultAsync((Employee x) => x.EmployeeId == Id && !x.IsDeleted, token);
		if (employee == null)
		{
			return NotFound();
		}
		if (employee.Version != Version)
		{
			base.ModelState.AddModelError(string.Empty, "This employee changed after you opened it. Reload and try again.");
			return Page();
		}
		var before = new { employee.EmployeeNumber, employee.DisplayName, employee.Email, employee.Department, employee.Manager, employee.Location, employee.Phone };
		employee.EmployeeNumber = Input.EmployeeNumber;
		employee.DisplayName = Input.DisplayName;
		employee.Email = Input.Email;
		employee.Department = Input.Department;
		employee.Manager = Input.Manager;
		employee.Location = Input.Location;
		employee.Phone = Input.Phone;
		employee.ModifiedUtc = DateTime.UtcNow;
		employee.Version++;
		await db.SaveChangesAsync(token);
		await audit.WriteAsync("Employee.Updated", "Employee", employee.EmployeeId.ToString(), base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), before, Input, null, base.HttpContext.TraceIdentifier, token);
		base.TempData["Success"] = employee.DisplayName + " was updated.";
		return RedirectToPage("Details", new
		{
			id = employee.EmployeeId
		});
	}
}
