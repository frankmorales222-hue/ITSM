using System;
using AssetPilot.Domain.Common;

namespace AssetPilot.Domain.Assets;

public sealed class AssetImportReview : AuditableEntity
{
	public int AssetImportReviewId { get; set; }

	public required string Fingerprint { get; set; }

	public required string SourceFileName { get; set; }

	public int SourceRowNumber { get; set; }

	public required string MatchReason { get; set; }

	public int? MatchingAssetId { get; set; }

	public Asset? MatchingAsset { get; set; }

	public required string RowValuesJson { get; set; }

	public required string Status { get; set; } = "Pending";

	public DateTime? ResolvedUtc { get; set; }

	public string? ResolvedByUserId { get; set; }

	public string? ResolutionNotes { get; set; }
}
