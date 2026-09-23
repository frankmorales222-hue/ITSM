using System.Threading;
using System.Threading.Tasks;

namespace AssetPilot.Application.Security;

public interface IRolePermissionService
{
	Task SetPermissionAsync(string roleId, int permissionId, bool isAllowed, string? userId, string? reason, string correlationId, CancellationToken cancellationToken = default(CancellationToken));
}
