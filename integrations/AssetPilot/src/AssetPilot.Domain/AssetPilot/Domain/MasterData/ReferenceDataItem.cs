using AssetPilot.Domain.Common;

namespace AssetPilot.Domain.MasterData;

public sealed class ReferenceDataItem : AuditableEntity
{
	public int ReferenceDataItemId { get; set; }

	public required string Kind { get; set; }

	public required string Name { get; set; }

	public string? Code { get; set; }

	public string? Notes { get; set; }

	public bool IsActive { get; set; } = true;

	public int? ParentId { get; set; }

	public ReferenceDataItem? Parent { get; set; }
}
