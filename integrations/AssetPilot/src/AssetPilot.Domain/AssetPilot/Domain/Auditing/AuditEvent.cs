using System;

namespace AssetPilot.Domain.Auditing;

public sealed class AuditEvent
{
	public long AuditEventId { get; set; }

	public required string EventTypeCode { get; set; }

	public required string EntityTypeCode { get; set; }

	public required string EntityId { get; set; }

	public string? UserId { get; set; }

	public DateTime EventUtc { get; set; }

	public string? BeforeJson { get; set; }

	public string? AfterJson { get; set; }

	public string? Reason { get; set; }

	public required string CorrelationId { get; set; }
}
