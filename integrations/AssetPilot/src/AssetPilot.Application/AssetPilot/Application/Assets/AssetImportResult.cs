using System.Collections.Generic;

namespace AssetPilot.Application.Assets;

public sealed record AssetImportResult(int SourceRows, int Created, int Updated, int Skipped, int Rejected, IReadOnlyList<string> Messages);
