using AssetPilot.Domain.Common;

namespace AssetPilot.Domain.Security;

public sealed class Permission : AuditableEntity
{
	public int PermissionId { get; set; }

	public required string PermissionKey { get; set; }

	public required string ModuleCode { get; set; }

	public required string Name { get; set; }

	public string? Description { get; set; }

	public bool IsSensitive { get; set; }
}
