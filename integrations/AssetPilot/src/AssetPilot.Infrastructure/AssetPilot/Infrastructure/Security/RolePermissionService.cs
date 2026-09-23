using System;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Auditing;
using AssetPilot.Application.Security;
using AssetPilot.Domain.Security;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Storage;

namespace AssetPilot.Infrastructure.Security;

public sealed class RolePermissionService(AssetPilotDbContext dbContext, IAuditService auditService) : IRolePermissionService
{
	public async Task SetPermissionAsync(string roleId, int permissionId, bool isAllowed, string? userId, string? reason, string correlationId, CancellationToken cancellationToken = default(CancellationToken))
	{
		ArgumentException.ThrowIfNullOrWhiteSpace(roleId, "roleId");
		ArgumentException.ThrowIfNullOrWhiteSpace(correlationId, "correlationId");
		RolePermission rolePermission = await dbContext.RolePermissions.SingleOrDefaultAsync((RolePermission item) => item.RoleId == roleId && item.PermissionId == permissionId, cancellationToken);
		bool? previousValue = rolePermission?.IsAllowed;
		if (previousValue == isAllowed)
		{
			return;
		}
		if (rolePermission == null)
		{
			dbContext.RolePermissions.Add(new RolePermission
			{
				RoleId = roleId,
				PermissionId = permissionId,
				IsAllowed = isAllowed
			});
		}
		else
		{
			rolePermission.IsAllowed = isAllowed;
		}
		await using IDbContextTransaction transaction = await dbContext.Database.BeginTransactionAsync(cancellationToken);
		await auditService.WriteAsync("Security.RolePermissionChanged", "IdentityRole", roleId, userId, new
		{
			PermissionId = permissionId,
			IsAllowed = previousValue
		}, new
		{
			PermissionId = permissionId,
			IsAllowed = isAllowed
		}, reason, correlationId, cancellationToken);
		await transaction.CommitAsync(cancellationToken);
	}
}
