using System;

namespace AssetPilot.Domain.Operations;

public sealed class OperationalJob
{
	public int OperationalJobId { get; set; }

	public required string JobType { get; set; }

	public required string Status { get; set; }

	public DateTime RequestedUtc { get; set; }

	public string? RequestedByUserId { get; set; }

	public DateTime? CompletedUtc { get; set; }

	public string? ResultSummary { get; set; }

	public string? CorrelationId { get; set; }
}
