using System.Collections.Generic;
using AssetPilot.Domain.Common;

namespace AssetPilot.Domain.People;

public sealed class Employee : AuditableEntity
{
	public int EmployeeId { get; set; }

	public required string EmployeeNumber { get; set; }

	public required string DisplayName { get; set; }

	public required string Email { get; set; }

	public string? Department { get; set; }

	public string? Manager { get; set; }

	public string? Location { get; set; }

	public string? Phone { get; set; }

	public bool IsActive { get; set; } = true;

	public bool IsDeleted { get; set; }

	public ICollection<AssetAssignment> Assignments { get; set; } = new List<AssetAssignment>();
}
