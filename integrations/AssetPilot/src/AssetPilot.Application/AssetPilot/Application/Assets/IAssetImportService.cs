using System.IO;
using System.Threading;
using System.Threading.Tasks;

namespace AssetPilot.Application.Assets;

public interface IAssetImportService
{
	Task<AssetImportResult> ImportAsync(Stream stream, string fileName, bool updateExisting, string? userId, string correlationId, CancellationToken cancellationToken = default(CancellationToken));
}
