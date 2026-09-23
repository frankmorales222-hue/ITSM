using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace AssetPilot.Application.Operations;

public interface IBackupService
{
	Task<IReadOnlyList<BackupInfo>> ListAsync(CancellationToken cancellationToken = default(CancellationToken));

	Task<BackupResult> CreateAndVerifyAsync(string? userId, string correlationId, CancellationToken cancellationToken = default(CancellationToken));
}
