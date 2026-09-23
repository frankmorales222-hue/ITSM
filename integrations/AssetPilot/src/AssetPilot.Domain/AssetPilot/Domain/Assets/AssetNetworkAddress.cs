using AssetPilot.Domain.Common;

namespace AssetPilot.Domain.Assets;

public sealed class AssetNetworkAddress : AuditableEntity
{
	public int AssetNetworkAddressId { get; set; }

	public int AssetId { get; set; }

	public Asset Asset { get; set; }

	public required string AddressType { get; set; }

	public required string Address { get; set; }

	public bool IsPrimary { get; set; }

	public string? Notes { get; set; }
}
