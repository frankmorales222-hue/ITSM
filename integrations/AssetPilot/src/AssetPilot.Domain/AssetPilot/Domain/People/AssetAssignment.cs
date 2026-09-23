using System;
using AssetPilot.Domain.Assets;

namespace AssetPilot.Domain.People;

public sealed class AssetAssignment
{
	public int AssetAssignmentId { get; set; }

	public int AssetId { get; set; }

	public Asset Asset { get; set; }

	public int EmployeeId { get; set; }

	public Employee Employee { get; set; }

	public DateTime AssignedUtc { get; set; }

	public string? AssignedByUserId { get; set; }

	public string? AssignedLocation { get; set; }

	public string? Notes { get; set; }

	public DateTime? ReturnedUtc { get; set; }

	public string? ReturnedByUserId { get; set; }

	public string? ReturnCondition { get; set; }

	public string? ReturnNotes { get; set; }
}
