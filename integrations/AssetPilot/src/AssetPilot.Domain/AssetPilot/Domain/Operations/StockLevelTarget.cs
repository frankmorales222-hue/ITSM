using AssetPilot.Domain.Common;

namespace AssetPilot.Domain.Operations;

public sealed class StockLevelTarget : AuditableEntity
{
	public int StockLevelTargetId { get; set; }

	public required string AssetType { get; set; }

	public required string Location { get; set; }

	public int TargetQuantity { get; set; }

	public int ThresholdPercent { get; set; } = 50;
}
