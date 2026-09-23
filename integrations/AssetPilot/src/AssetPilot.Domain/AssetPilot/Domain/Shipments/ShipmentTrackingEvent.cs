using System;

namespace AssetPilot.Domain.Shipments;

public sealed class ShipmentTrackingEvent
{
	public int ShipmentTrackingEventId { get; set; }

	public int ShipmentId { get; set; }

	public Shipment Shipment { get; set; } = null!;

	public DateTime EventUtc { get; set; }

	public string Status { get; set; } = "";

	public string? Description { get; set; }

	public string? Location { get; set; }

	public string Source { get; set; } = "";
}
