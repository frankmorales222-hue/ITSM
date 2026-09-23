using System.Linq;
using System.Security.Claims;
using System.Threading.Tasks;
using AssetPilot.Domain.Security;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Identity;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Infrastructure.Security;

public sealed class PermissionAuthorizationHandler(AssetPilotDbContext dbContext) : AuthorizationHandler<PermissionRequirement>
{
	protected override async Task HandleRequirementAsync(AuthorizationHandlerContext context, PermissionRequirement requirement)
	{
		string userId = context.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier");
		if (!string.IsNullOrWhiteSpace(userId) && await (from userRole in dbContext.UserRoles
			join rolePermission in dbContext.RolePermissions on userRole.RoleId equals rolePermission.RoleId
			join permission in dbContext.Permissions on rolePermission.PermissionId equals permission.PermissionId
			where userRole.UserId == userId && permission.PermissionKey == requirement.PermissionKey && rolePermission.IsAllowed
			select permission.PermissionId).AnyAsync())
		{
			context.Succeed(requirement);
		}
	}
}
