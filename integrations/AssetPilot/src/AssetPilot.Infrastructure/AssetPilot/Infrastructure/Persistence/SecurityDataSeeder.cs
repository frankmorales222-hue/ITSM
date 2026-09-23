using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Security;
using AssetPilot.Domain.Security;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Infrastructure.Persistence;

public sealed class SecurityDataSeeder(AssetPilotDbContext dbContext, RoleManager<IdentityRole> roleManager)
{
	public async Task SeedAsync(CancellationToken cancellationToken = default(CancellationToken))
	{
		foreach (string roleName in RoleTemplates.All)
		{
			if (!(await roleManager.RoleExistsAsync(roleName)))
			{
				EnsureSucceeded(await roleManager.CreateAsync(new IdentityRole(roleName)), "create role '" + roleName + "'");
			}
		}
		HashSet<string> existingKeys = await dbContext.Permissions.Select((Permission permission) => permission.PermissionKey).ToHashSetAsync<string>(StringComparer.Ordinal, cancellationToken);
		DateTime utcNow = DateTime.UtcNow;
		foreach (PermissionDefinition item in PermissionCatalog.All.Where((PermissionDefinition item) => !existingKeys.Contains(item.Key)))
		{
			dbContext.Permissions.Add(new Permission
			{
				PermissionKey = item.Key,
				ModuleCode = item.ModuleCode,
				Name = item.Name,
				Description = item.Description,
				IsSensitive = item.IsSensitive,
				CreatedUtc = utcNow,
				ModifiedUtc = utcNow
			});
		}
		await dbContext.SaveChangesAsync(cancellationToken);
		Dictionary<string, Permission> permissions = await dbContext.Permissions
			.ToDictionaryAsync(x => x.PermissionKey, StringComparer.Ordinal, cancellationToken);
		foreach (string roleName in RoleTemplates.All)
		{
			IdentityRole role = (await roleManager.FindByNameAsync(roleName))
				?? throw new InvalidOperationException($"The {roleName} role was not created.");
			List<RolePermission> existing = await dbContext.RolePermissions
				.Where(x => x.RoleId == role.Id)
				.ToListAsync(cancellationToken);
			bool seedTemplate = roleName.Equals(RoleTemplates.Administrator, StringComparison.OrdinalIgnoreCase)
				|| existing.Count == 0;
			if (!seedTemplate)
			{
				continue;
			}
			IReadOnlySet<string> defaults = RoleTemplates.DefaultPermissions[roleName];
			foreach (Permission permission in permissions.Values)
			{
				bool allowed = defaults.Contains(permission.PermissionKey);
				RolePermission? assignment = existing.FirstOrDefault(x => x.PermissionId == permission.PermissionId);
				if (assignment is null)
				{
					dbContext.RolePermissions.Add(new RolePermission
					{
						RoleId = role.Id,
						PermissionId = permission.PermissionId,
						IsAllowed = allowed
					});
				}
				else if (roleName.Equals(RoleTemplates.Administrator, StringComparison.OrdinalIgnoreCase))
				{
					assignment.IsAllowed = true;
				}
			}
		}
		await dbContext.SaveChangesAsync(cancellationToken);
	}

	private static void EnsureSucceeded(IdentityResult result, string operation)
	{
		if (result.Succeeded)
		{
			return;
		}
		string text = string.Join("; ", result.Errors.Select((IdentityError error) => error.Description));
		throw new InvalidOperationException("Unable to " + operation + ": " + text);
	}
}
