using AssetPilot.Domain.Common;

namespace AssetPilot.Domain.Operations;

public sealed class SystemSetting : AuditableEntity
{
	public int SystemSettingId { get; set; }

	public required string SettingKey { get; set; }

	public required string Value { get; set; }

	public required string Description { get; set; }

	public bool IsSensitive { get; set; }
}
