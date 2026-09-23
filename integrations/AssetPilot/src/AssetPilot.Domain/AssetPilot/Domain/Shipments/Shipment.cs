using System;
using System.Collections.Generic;
using AssetPilot.Domain.Common;

namespace AssetPilot.Domain.Shipments;

public sealed class Shipment : AuditableEntity
{
	public int ShipmentId { get; set; }

	public required string ShipmentNumber { get; set; }

	public required string Direction { get; set; }

	public required string Status { get; set; }

	public string? Carrier { get; set; }

	public string? TrackingNumber { get; set; }

	public string? Sender { get; set; }

	public string? Recipient { get; set; }

	public string? Origin { get; set; }

	public string? Destination { get; set; }

	public DateOnly? ShipDate { get; set; }

	public DateOnly? ExpectedDate { get; set; }

	public DateTime? ReceivedUtc { get; set; }

	public string? ReceivedByUserId { get; set; }

	public string? Notes { get; set; }

	public DateTime? TrackingLastCheckedUtc { get; set; }

	public string? TrackingLastMessage { get; set; }

	public string? TrackingUrl { get; set; }

	public bool IsArchived { get; set; }

	public ICollection<ShipmentItem> Items { get; set; } = new List<ShipmentItem>();

	public ICollection<ShipmentTrackingEvent> TrackingEvents { get; set; } = new List<ShipmentTrackingEvent>();
}
