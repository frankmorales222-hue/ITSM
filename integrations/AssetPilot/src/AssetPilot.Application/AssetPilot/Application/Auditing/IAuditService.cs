using System.Threading;
using System.Threading.Tasks;

namespace AssetPilot.Application.Auditing;

public interface IAuditService
{
	Task WriteAsync(string eventTypeCode, string entityTypeCode, string entityId, string? userId, object? before, object? after, string? reason, string correlationId, CancellationToken cancellationToken = default(CancellationToken));
}
