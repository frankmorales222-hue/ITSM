using System;
using System.Collections.Generic;

namespace AssetPilot.Application.Shipments;

public sealed record ShipmentTrackingEventResult(
	DateTime EventUtc,
	string Status,
	string? Description,
	string? Location);

public sealed record ShipmentTrackingResult(
	bool Success,
	string Status,
	string Message,
	DateOnly? ExpectedDate,
	string TrackingUrl,
	IReadOnlyList<ShipmentTrackingEventResult> Events);
