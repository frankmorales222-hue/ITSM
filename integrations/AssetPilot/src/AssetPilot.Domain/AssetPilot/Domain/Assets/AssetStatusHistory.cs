using System;

namespace AssetPilot.Domain.Assets;

public sealed class AssetStatusHistory
{
	public long AssetStatusHistoryId { get; set; }

	public int AssetId { get; set; }

	public Asset Asset { get; set; }

	public string? FromStatus { get; set; }

	public required string ToStatus { get; set; }

	public DateTime ChangedUtc { get; set; }

	public string? ChangedByUserId { get; set; }

	public string? Reason { get; set; }
}
