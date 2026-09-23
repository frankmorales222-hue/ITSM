using System.IO;
using System.Collections.Generic;
using System.Threading;
using System.Threading.Tasks;

namespace AssetPilot.Application.Assets;

public interface IInventoryAuditExportService
{
	Task<MemoryStream> ExportAsync(
		string templatePath,
		CancellationToken cancellationToken = default,
		IReadOnlyCollection<int>? assetIds = null);
}
