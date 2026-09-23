using System.Security.Claims;
using System.Text;
using AssetPilot.Application.Auditing;
using AssetPilot.Application.Security;
using AssetPilot.Domain.Security;
using AssetPilot.Infrastructure.Identity;
using AssetPilot.Infrastructure.Persistence;
using AssetPilot.Web.Services;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;
using Microsoft.AspNetCore.WebUtilities;

namespace AssetPilot.Web.Pages.Security;

[Authorize(Policy = "Security.ManagePermissions")]
public sealed class IndexModel(
	AssetPilotDbContext db,
	UserManager<ApplicationUser> userManager,
	RoleManager<IdentityRole> roleManager,
	IRolePermissionService rolePermissionService,
	IAuditService audit,
	IUserInvitationEmailSender invitationEmailSender) : PageModel
{
	public sealed record UserRow(
		string Id,
		string DisplayName,
		string Email,
		bool IsActive,
		IReadOnlyList<string> Roles);

	public sealed record RoleRow(
		string Id,
		string Name,
		int UserCount,
		bool IsBuiltIn,
		bool IsCustom,
		int AllowedPermissionCount);

	public sealed record PermissionRow(
		int Id,
		string Key,
		string Module,
		string Name,
		string Description,
		bool IsSensitive,
		bool IsAllowed);

	[BindProperty(SupportsGet = true)]
	public string? SelectedRoleId { get; set; }

	[BindProperty]
	public string? UserId { get; set; }

	[BindProperty]
	public string? RoleName { get; set; }

	[BindProperty]
	public int PermissionId { get; set; }

	[BindProperty]
	public bool IsAllowed { get; set; }

	[BindProperty]
	public string? NewRoleName { get; set; }

	[BindProperty]
	public string? NewUserDisplayName { get; set; }

	[BindProperty]
	public string? NewUserEmail { get; set; }

	[BindProperty]
	public string? NewUserPassword { get; set; }

	[BindProperty]
	public string? NewUserRoleName { get; set; } = RoleTemplates.AssetManager;

	public IReadOnlyList<UserRow> Users { get; private set; } = Array.Empty<UserRow>();

	public IReadOnlyList<RoleRow> Roles { get; private set; } = Array.Empty<RoleRow>();

	public IReadOnlyList<PermissionRow> Permissions { get; private set; } = Array.Empty<PermissionRow>();

	public string? SelectedRoleName { get; private set; }

	public bool SelectedRoleIsAdministrator =>
		SelectedRoleName?.Equals(RoleTemplates.Administrator, StringComparison.OrdinalIgnoreCase) == true;

	public bool SelectedRoleIsBuiltIn =>
		SelectedRoleName is not null && RoleTemplates.DefaultPermissions.ContainsKey(SelectedRoleName);

	public bool SelectedRoleIsCustom { get; private set; }

	public async Task OnGetAsync(CancellationToken cancellationToken) =>
		await LoadAsync(cancellationToken);

	public async Task<IActionResult> OnPostSetPermissionAsync(CancellationToken cancellationToken)
	{
		IdentityRole? selectedRole = string.IsNullOrWhiteSpace(SelectedRoleId)
			? null
			: await roleManager.FindByIdAsync(SelectedRoleId);
		if (selectedRole is null
			|| !await db.Permissions.AnyAsync(x => x.PermissionId == PermissionId, cancellationToken))
		{
			return BadRequest();
		}
		if (selectedRole.Name?.Equals(RoleTemplates.Administrator, StringComparison.OrdinalIgnoreCase) == true)
		{
			TempData["Warning"] = "Administrator always has every permission and cannot be restricted.";
			return RedirectToPage(new { SelectedRoleId });
		}
		await rolePermissionService.SetPermissionAsync(
			SelectedRoleId,
			PermissionId,
			IsAllowed,
			User.FindFirstValue(ClaimTypes.NameIdentifier),
			"Changed in Security administration",
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = "Role permission updated.";
		return RedirectToPage(new { SelectedRoleId });
	}

	public async Task<IActionResult> OnPostResetRoleAsync(CancellationToken cancellationToken)
	{
		IdentityRole? role = string.IsNullOrWhiteSpace(SelectedRoleId)
			? null
			: await roleManager.FindByIdAsync(SelectedRoleId);
		if (role?.Name is null || !RoleTemplates.DefaultPermissions.TryGetValue(role.Name, out IReadOnlySet<string>? defaults))
		{
			return BadRequest();
		}
		if (role.Name.Equals(RoleTemplates.Administrator, StringComparison.OrdinalIgnoreCase))
		{
			TempData["Success"] = "Administrator already has the complete permission set.";
			return RedirectToPage(new { SelectedRoleId });
		}
		List<Permission> permissions = await db.Permissions.ToListAsync(cancellationToken);
		foreach (Permission permission in permissions)
		{
			await rolePermissionService.SetPermissionAsync(
				role.Id,
				permission.PermissionId,
				defaults.Contains(permission.PermissionKey),
				User.FindFirstValue(ClaimTypes.NameIdentifier),
				"Reset to built-in role template",
				HttpContext.TraceIdentifier,
				cancellationToken);
		}
		TempData["Success"] = $"{role.Name} was reset to its built-in permission template.";
		return RedirectToPage(new { SelectedRoleId });
	}

	public async Task<IActionResult> OnPostSetUserRoleAsync(CancellationToken cancellationToken)
	{
		if (string.IsNullOrWhiteSpace(UserId) || string.IsNullOrWhiteSpace(RoleName))
		{
			return BadRequest();
		}
		ApplicationUser? user = await userManager.FindByIdAsync(UserId);
		if (user is null || !await roleManager.RoleExistsAsync(RoleName))
		{
			return BadRequest();
		}
		IList<string> beforeRoles = await userManager.GetRolesAsync(user);
		if (beforeRoles.Contains(RoleTemplates.Administrator)
			&& !RoleName.Equals(RoleTemplates.Administrator, StringComparison.OrdinalIgnoreCase))
		{
			IList<ApplicationUser> administrators = await userManager.GetUsersInRoleAsync(RoleTemplates.Administrator);
			if (administrators.Count(x => x.IsActive) <= 1)
			{
				TempData["Warning"] = "The last active administrator cannot be removed from the Administrator role.";
				return RedirectToPage(new { SelectedRoleId });
			}
		}
		IdentityResult remove = await userManager.RemoveFromRolesAsync(user, beforeRoles);
		if (!remove.Succeeded)
		{
			AddErrors(remove);
			await LoadAsync(cancellationToken);
			return Page();
		}
		IdentityResult add = await userManager.AddToRoleAsync(user, RoleName);
		if (!add.Succeeded)
		{
			await userManager.AddToRolesAsync(user, beforeRoles);
			AddErrors(add);
			await LoadAsync(cancellationToken);
			return Page();
		}
		await audit.WriteAsync(
			"Security.UserRoleChanged",
			"ApplicationUser",
			user.Id,
			User.FindFirstValue(ClaimTypes.NameIdentifier),
			new { Roles = beforeRoles },
			new { Role = RoleName },
			null,
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = $"{user.DisplayName} is now assigned to {RoleName}.";
		return RedirectToPage(new { SelectedRoleId });
	}

	public async Task<IActionResult> OnPostToggleUserAsync(CancellationToken cancellationToken)
	{
		if (string.IsNullOrWhiteSpace(UserId))
		{
			return BadRequest();
		}
		ApplicationUser? user = await userManager.FindByIdAsync(UserId);
		if (user is null)
		{
			return NotFound();
		}
		if (user.Id == User.FindFirstValue(ClaimTypes.NameIdentifier) && user.IsActive)
		{
			TempData["Warning"] = "You cannot disable your own account.";
			return RedirectToPage(new { SelectedRoleId });
		}
		IList<string> roles = await userManager.GetRolesAsync(user);
		if (user.IsActive && roles.Contains(RoleTemplates.Administrator))
		{
			IList<ApplicationUser> administrators = await userManager.GetUsersInRoleAsync(RoleTemplates.Administrator);
			if (administrators.Count(x => x.IsActive) <= 1)
			{
				TempData["Warning"] = "The last active administrator cannot be disabled.";
				return RedirectToPage(new { SelectedRoleId });
			}
		}
		bool before = user.IsActive;
		user.IsActive = !user.IsActive;
		IdentityResult result = await userManager.UpdateAsync(user);
		if (!result.Succeeded)
		{
			AddErrors(result);
			await LoadAsync(cancellationToken);
			return Page();
		}
		await audit.WriteAsync(
			"Security.UserStatusChanged",
			"ApplicationUser",
			user.Id,
			User.FindFirstValue(ClaimTypes.NameIdentifier),
			new { IsActive = before },
			new { user.IsActive },
			null,
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = $"{user.DisplayName} was {(user.IsActive ? "enabled" : "disabled")}.";
		return RedirectToPage(new { SelectedRoleId });
	}

	public async Task<IActionResult> OnPostCreateRoleAsync(CancellationToken cancellationToken)
	{
		NewRoleName = NewRoleName?.Trim();
		if (string.IsNullOrWhiteSpace(NewRoleName))
		{
			ModelState.AddModelError(nameof(NewRoleName), "Enter a role name.");
			await LoadAsync(cancellationToken);
			return Page();
		}
		if (NewRoleName.Length is < 2 or > 80)
		{
			ModelState.AddModelError(nameof(NewRoleName), "Role name must be between 2 and 80 characters.");
			await LoadAsync(cancellationToken);
			return Page();
		}
		if (await roleManager.RoleExistsAsync(NewRoleName))
		{
			ModelState.AddModelError(nameof(NewRoleName), "That role already exists.");
			await LoadAsync(cancellationToken);
			return Page();
		}
		IdentityRole role = new(NewRoleName);
		IdentityResult result = await roleManager.CreateAsync(role);
		if (!result.Succeeded)
		{
			AddErrors(result);
			await LoadAsync(cancellationToken);
			return Page();
		}
		await audit.WriteAsync(
			"Security.RoleCreated",
			"IdentityRole",
			role.Id,
			User.FindFirstValue(ClaimTypes.NameIdentifier),
			null,
			new { role.Name },
			null,
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = $"Role {role.Name} was created.";
		return RedirectToPage(new { SelectedRoleId = role.Id });
	}

	public async Task<IActionResult> OnPostCreateUserAsync(CancellationToken cancellationToken)
	{
		NewUserDisplayName = NewUserDisplayName?.Trim();
		NewUserEmail = NewUserEmail?.Trim();
		if (string.IsNullOrWhiteSpace(NewUserDisplayName))
		{
			ModelState.AddModelError(nameof(NewUserDisplayName), "Enter a display name.");
		}
		if (string.IsNullOrWhiteSpace(NewUserEmail))
		{
			ModelState.AddModelError(nameof(NewUserEmail), "Enter an email address.");
		}
		if (!invitationEmailSender.IsConfigured) ModelState.AddModelError(string.Empty, "Email invitations are not configured. Ask an administrator to add Email__Smtp settings to the server.");
		if (string.IsNullOrWhiteSpace(NewUserRoleName))
		{
			ModelState.AddModelError(nameof(NewUserRoleName), "Choose an initial role.");
		}
		if (!ModelState.IsValid)
		{
			await LoadAsync(cancellationToken);
			return Page();
		}
		if (NewUserDisplayName.Length is < 2 or > 100)
		{
			ModelState.AddModelError(nameof(NewUserDisplayName), "Display name must be between 2 and 100 characters.");
		}
		if (!NewUserEmail.Contains('@') || NewUserEmail.Length > 255)
		{
			ModelState.AddModelError(nameof(NewUserEmail), "Enter a valid email address.");
		}
		if (!await roleManager.RoleExistsAsync(NewUserRoleName))
		{
			ModelState.AddModelError(nameof(NewUserRoleName), "Choose an existing role.");
		}
		if (!ModelState.IsValid)
		{
			await LoadAsync(cancellationToken);
			return Page();
		}
		ApplicationUser user = new()
		{
			UserName = NewUserEmail,
			Email = NewUserEmail,
			DisplayName = NewUserDisplayName,
			EmailConfirmed = false,
			IsActive = true
		};
		IdentityResult created = await userManager.CreateAsync(user);
		if (!created.Succeeded)
		{
			AddErrors(created);
			await LoadAsync(cancellationToken);
			return Page();
		}
		IdentityResult assigned = await userManager.AddToRoleAsync(user, NewUserRoleName);
		if (!assigned.Succeeded)
		{
			await userManager.DeleteAsync(user);
			AddErrors(assigned);
			await LoadAsync(cancellationToken);
			return Page();
		}
		string token = await userManager.GeneratePasswordResetTokenAsync(user);
		string code = WebEncoders.Base64UrlEncode(Encoding.UTF8.GetBytes(token));
		string invitationUrl = Url.Page("/Account/SetPassword", null, new { UserId = user.Id, Code = code }, Request.Scheme)!;
		try { await invitationEmailSender.SendAsync(user.Email!, user.DisplayName, invitationUrl, cancellationToken); }
		catch (Exception exception)
		{
			await userManager.DeleteAsync(user);
			ModelState.AddModelError(string.Empty, $"The invitation could not be sent: {exception.Message}");
			await LoadAsync(cancellationToken);
			return Page();
		}
		await audit.WriteAsync(
			"Security.UserCreated",
			"ApplicationUser",
			user.Id,
			User.FindFirstValue(ClaimTypes.NameIdentifier),
			null,
			new { user.DisplayName, user.Email, Role = NewUserRoleName },
			null,
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = $"An invitation was emailed to {user.Email}.";
		return RedirectToPage(new { SelectedRoleId });
	}

	private async Task LoadAsync(CancellationToken cancellationToken)
	{
		List<IdentityRole> roles = await roleManager.Roles.OrderBy(x => x.Name).ToListAsync(cancellationToken);
		if (string.IsNullOrWhiteSpace(SelectedRoleId) || roles.All(x => x.Id != SelectedRoleId))
		{
			SelectedRoleId = roles.FirstOrDefault(x => x.Name == RoleTemplates.Administrator)?.Id
				?? roles.FirstOrDefault()?.Id;
		}
		SelectedRoleName = roles.FirstOrDefault(x => x.Id == SelectedRoleId)?.Name;
		List<ApplicationUser> users = await userManager.Users.OrderBy(x => x.DisplayName).ToListAsync(cancellationToken);
		List<UserRow> userRows = [];
		foreach (ApplicationUser user in users)
		{
			userRows.Add(new UserRow(
				user.Id,
				user.DisplayName,
				user.Email ?? user.UserName ?? "",
				user.IsActive,
				(await userManager.GetRolesAsync(user)).OrderBy(x => x).ToList()));
		}
		Users = userRows;
		var userCounts = await db.UserRoles.GroupBy(x => x.RoleId)
			.Select(group => new { RoleId = group.Key, Count = group.Count() })
			.ToDictionaryAsync(x => x.RoleId, x => x.Count, cancellationToken);
		Dictionary<int, string> permissionKeys = await db.Permissions.AsNoTracking()
			.ToDictionaryAsync(x => x.PermissionId, x => x.PermissionKey, cancellationToken);
		Dictionary<string, HashSet<int>> allowedByRole = await db.RolePermissions.AsNoTracking()
			.Where(x => x.IsAllowed)
			.GroupBy(x => x.RoleId)
			.ToDictionaryAsync(group => group.Key, group => group.Select(x => x.PermissionId).ToHashSet(), cancellationToken);
		Roles = roles.Select(role =>
		{
			string name = role.Name ?? "Unnamed role";
			HashSet<string> currentKeys = allowedByRole.GetValueOrDefault(role.Id, [])
				.Where(permissionKeys.ContainsKey)
				.Select(id => permissionKeys[id])
				.ToHashSet(StringComparer.Ordinal);
			bool builtIn = RoleTemplates.DefaultPermissions.TryGetValue(name, out IReadOnlySet<string>? defaults);
			bool custom = !builtIn || !currentKeys.SetEquals(defaults!);
			return new RoleRow(role.Id, name, userCounts.GetValueOrDefault(role.Id), builtIn, custom, currentKeys.Count);
		}).ToList();
		HashSet<int> allowed = string.IsNullOrWhiteSpace(SelectedRoleId)
			? []
			: allowedByRole.GetValueOrDefault(SelectedRoleId, []);
		SelectedRoleIsCustom = Roles.FirstOrDefault(x => x.Id == SelectedRoleId)?.IsCustom ?? false;
		Permissions = await db.Permissions.AsNoTracking()
			.OrderBy(x => x.ModuleCode)
			.ThenBy(x => x.Name)
			.Select(x => new PermissionRow(
				x.PermissionId,
				x.PermissionKey,
				x.ModuleCode,
				x.Name,
				x.Description,
				x.IsSensitive,
				allowed.Contains(x.PermissionId)))
			.ToListAsync(cancellationToken);
	}

	private void AddErrors(IdentityResult result)
	{
		foreach (IdentityError error in result.Errors)
		{
			ModelState.AddModelError(string.Empty, error.Description);
		}
	}
}
