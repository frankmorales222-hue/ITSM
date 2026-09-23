using System;
using System.Collections.Generic;
using AssetPilot.Domain.Common;
using AssetPilot.Domain.People;
using AssetPilot.Domain.Shipments;

namespace AssetPilot.Domain.Assets;

public sealed class Asset : AuditableEntity
{
	public int AssetId { get; set; }

	public required string AssetTag { get; set; }

	public string? Hostname { get; set; }

	public string? SerialNumber { get; set; }

	public required string Name { get; set; }

	public required string Status { get; set; } = "Active";

	public required string Condition { get; set; } = "Good";

	public required string Category { get; set; } = "Computer";

	public required string AssetType { get; set; } = "Laptop";

	public string? Manufacturer { get; set; }

	public string? Model { get; set; }

	public string? AssignedTo { get; set; }

	public string? Department { get; set; }

	public string? Location { get; set; }

	public string? Vendor { get; set; }

	public string? Purpose { get; set; }

	public string? Company { get; set; }

	public string? Project { get; set; }

	public string? MacAddress { get; set; }

	public string? AssignedToEmail { get; set; }

	public string? SourceReference { get; set; }

	public string? DuplicateSerialNumber { get; set; }

	public string? Monitor1AssetTag { get; set; }

	public string? Monitor1SerialNumber { get; set; }

	public string? Monitor2AssetTag { get; set; }

	public string? Monitor2SerialNumber { get; set; }

	public string? Monitor3AssetTag { get; set; }

	public string? Monitor3SerialNumber { get; set; }

	public string? OfficeWorkMode { get; set; }

	public string? Workstation { get; set; }

	public string? CurrentLocation { get; set; }

	public string? EmployeeNumber { get; set; }

	public string? Designation { get; set; }

	public DateOnly? AllocationDate { get; set; }

	public string? ServiceRequestTicket { get; set; }

	public string? SignedAllocationFormStatus { get; set; }

	public DateOnly? ReceivedDate { get; set; }

	public string? OldEmployeeNumber { get; set; }

	public string? OldUserName { get; set; }

	public string? OwnerName { get; set; }

	public string? OwnerEmail { get; set; }

	public string? Classification { get; set; }

	public string? Severity { get; set; }

	public string? Remarks { get; set; }

	public string? NewReplacementStatus { get; set; }

	public string? DockingStation { get; set; }

	public string? Keyboard { get; set; }

	public string? Mouse { get; set; }

	public string? Headset { get; set; }

	public string? Printer { get; set; }

	public DateOnly? PurchaseDate { get; set; }

	public long? PurchaseCostCents { get; set; }

	public DateOnly? WarrantyExpiration { get; set; }

	public bool IsArchived { get; set; }

	public ICollection<AssetNetworkAddress> NetworkAddresses { get; set; } = new List<AssetNetworkAddress>();

	public ICollection<AssetStatusHistory> StatusHistory { get; set; } = new List<AssetStatusHistory>();

	public ICollection<AssetAssignment> Assignments { get; set; } = new List<AssetAssignment>();

	public ICollection<ShipmentItem> ShipmentItems { get; set; } = new List<ShipmentItem>();
}
