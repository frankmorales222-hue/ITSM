using AssetPilot.Domain.Assets;

namespace AssetPilot.Domain.Shipments;

public sealed class ShipmentItem
{
	public int ShipmentItemId { get; set; }

	public int ShipmentId { get; set; }

	public Shipment Shipment { get; set; }

	public int AssetId { get; set; }

	public Asset Asset { get; set; }

	public string? ConditionAtDispatch { get; set; }

	public string? ConditionAtReceipt { get; set; }

	public string? Notes { get; set; }
}
