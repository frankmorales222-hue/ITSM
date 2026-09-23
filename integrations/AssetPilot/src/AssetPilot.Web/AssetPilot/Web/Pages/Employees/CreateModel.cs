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
public sealed class CreateModel(AssetPilotDbContext db, IAuditService audit) : PageModel
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
	public InputModel Input { get; set; } = new InputModel();

	[BindProperty]
	public bool AddAssetNext { get; set; }

	public void OnGet()
	{
	}

	public async Task<IActionResult> OnPostAsync(CancellationToken cancellationToken)
	{
		Input.Normalize();
		if (await db.Employees.AnyAsync((Employee x) => !x.IsDeleted && x.EmployeeNumber == Input.EmployeeNumber, cancellationToken))
		{
			base.ModelState.AddModelError("Input.EmployeeNumber", "That employee number is already in use.");
		}
		if (await db.Employees.AnyAsync((Employee x) => !x.IsDeleted && x.Email == Input.Email, cancellationToken))
		{
			base.ModelState.AddModelError("Input.Email", "That email address is already in use.");
		}
		if (!base.ModelState.IsValid)
		{
			return Page();
		}
		DateTime utcNow = DateTime.UtcNow;
		Employee employee = new Employee
		{
			EmployeeNumber = Input.EmployeeNumber,
			DisplayName = Input.DisplayName,
			Email = Input.Email,
			Department = Input.Department,
			Manager = Input.Manager,
			Location = Input.Location,
			Phone = Input.Phone,
			CreatedUtc = utcNow,
			ModifiedUtc = utcNow
		};
		db.Employees.Add(employee);
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync("Employee.Created", "Employee", employee.EmployeeId.ToString(), base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), null, employee, null, base.HttpContext.TraceIdentifier, cancellationToken);
		base.TempData["Success"] = employee.DisplayName + " was added.";
		if (AddAssetNext)
		{
			return RedirectToPage("/Assets/Create", new { employeeId = employee.EmployeeId });
		}
		return RedirectToPage("Details", new
		{
			id = employee.EmployeeId
		});
	}
}
