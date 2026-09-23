namespace AssetPilot.Domain.Security;

public sealed class RolePermission
{
	public string RoleId { get; set; } = string.Empty;

	public int PermissionId { get; set; }

	public bool IsAllowed { get; set; }

	public Permission Permission { get; set; }
}
