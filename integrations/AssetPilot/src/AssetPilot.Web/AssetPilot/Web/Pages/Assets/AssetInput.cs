using System;
using System.ComponentModel.DataAnnotations;
using AssetPilot.Domain.Assets;

namespace AssetPilot.Web.Pages.Assets;

public sealed class AssetInput
{
	[Required]
	[StringLength(80)]
	[Display(Name = "Asset tag")]
	public string AssetTag { get; set; } = "";

	[StringLength(255)]
	public string? Hostname { get; set; }

	[StringLength(160)]
	[Display(Name = "Serial number")]
	public string? SerialNumber { get; set; }

	[Required]
	[StringLength(200)]
	[Display(Name = "Display name")]
	public string Name { get; set; } = "";

	[Required]
	public string Status { get; set; } = "Active";

	[Required]
	public string Condition { get; set; } = "Good";

	[Required]
	public string Category { get; set; } = "Computer";

	[Required]
	[Display(Name = "Asset type")]
	public string AssetType { get; set; } = "Laptop";

	public string? Manufacturer { get; set; }

	public string? Model { get; set; }

	[Display(Name = "Assigned to")]
	public string? AssignedTo { get; set; }

	[EmailAddress]
	[Display(Name = "Assigned-to email")]
	public string? AssignedToEmail { get; set; }

	public string? Department { get; set; }

	public string? Location { get; set; }

	public string? Vendor { get; set; }

	public string? Purpose { get; set; }

	public string? Company { get; set; }

	public string? Project { get; set; }

	[Display(Name = "MAC address")]
	public string? MacAddress { get; set; }

	[Display(Name = "Duplicate serial number")]
	public string? DuplicateSerialNumber { get; set; }

	[Display(Name = "Monitor 1 asset tag / hostname")]
	public string? Monitor1AssetTag { get; set; }

	[Display(Name = "Monitor 1 serial number")]
	public string? Monitor1SerialNumber { get; set; }

	[Display(Name = "Monitor 2 asset tag / hostname")]
	public string? Monitor2AssetTag { get; set; }

	[Display(Name = "Monitor 2 serial number")]
	public string? Monitor2SerialNumber { get; set; }

	[Display(Name = "Monitor 3 asset tag / hostname")]
	public string? Monitor3AssetTag { get; set; }

	[Display(Name = "Monitor 3 serial number")]
	public string? Monitor3SerialNumber { get; set; }

	[Display(Name = "In office / WFH-OOO")]
	public string? OfficeWorkMode { get; set; }

	public string? Workstation { get; set; }

	[Display(Name = "Current location")]
	public string? CurrentLocation { get; set; }

	[Display(Name = "Employee ID")]
	public string? EmployeeNumber { get; set; }

	public string? Designation { get; set; }

	[DataType(DataType.Date)]
	[Display(Name = "Date of allocation")]
	public DateOnly? AllocationDate { get; set; }

	[Display(Name = "Service request ticket")]
	public string? ServiceRequestTicket { get; set; }

	[Display(Name = "Signed allocation form status")]
	public string? SignedAllocationFormStatus { get; set; }

	[DataType(DataType.Date)]
	[Display(Name = "Date received")]
	public DateOnly? ReceivedDate { get; set; }

	[Display(Name = "Old employee ID")]
	public string? OldEmployeeNumber { get; set; }

	[Display(Name = "Old user name")]
	public string? OldUserName { get; set; }

	[Display(Name = "Owner / HOD name")]
	public string? OwnerName { get; set; }

	[EmailAddress]
	[Display(Name = "Owner email")]
	public string? OwnerEmail { get; set; }

	public string? Classification { get; set; }

	[Display(Name = "Severity / identification")]
	public string? Severity { get; set; }

	public string? Remarks { get; set; }

	[Display(Name = "New / replacement status")]
	public string? NewReplacementStatus { get; set; }

	[Display(Name = "Docking station")]
	public string? DockingStation { get; set; }

	public string? Keyboard { get; set; }

	public string? Mouse { get; set; }

	public string? Headset { get; set; }

	public string? Printer { get; set; }

	[DataType(DataType.Date)]
	[Display(Name = "Purchase date")]
	public DateOnly? PurchaseDate { get; set; }

	[Range(0, 100000000)]
	[DataType(DataType.Currency)]
	[Display(Name = "Purchase cost")]
	public decimal? PurchaseCost { get; set; }

	[DataType(DataType.Date)]
	[Display(Name = "Warranty expiration")]
	public DateOnly? WarrantyExpiration { get; set; }

	public int Version { get; set; }

	public void Normalize()
	{
		AssetTag = AssetTag.Trim();
		Name = Name.Trim();
		Hostname = NormalizeOptional(Hostname);
		SerialNumber = NormalizeSerial(SerialNumber);
		Manufacturer = NormalizeOptional(Manufacturer);
		Model = NormalizeOptional(Model);
		AssignedTo = NormalizeOptional(AssignedTo);
		AssignedToEmail = NormalizeOptional(AssignedToEmail);
		Department = NormalizeOptional(Department);
		Location = NormalizeOptional(Location);
		Vendor = NormalizeOptional(Vendor);
		Purpose = NormalizeOptional(Purpose);
		Company = NormalizeOptional(Company);
		Project = NormalizeOptional(Project);
		MacAddress = NormalizeOptional(MacAddress);
		DuplicateSerialNumber = NormalizeSerial(DuplicateSerialNumber);
		Monitor1AssetTag = NormalizeOptional(Monitor1AssetTag);
		Monitor1SerialNumber = NormalizeSerial(Monitor1SerialNumber);
		Monitor2AssetTag = NormalizeOptional(Monitor2AssetTag);
		Monitor2SerialNumber = NormalizeSerial(Monitor2SerialNumber);
		Monitor3AssetTag = NormalizeOptional(Monitor3AssetTag);
		Monitor3SerialNumber = NormalizeSerial(Monitor3SerialNumber);
		OfficeWorkMode = NormalizeOptional(OfficeWorkMode);
		Workstation = NormalizeOptional(Workstation);
		CurrentLocation = NormalizeOptional(CurrentLocation);
		EmployeeNumber = NormalizeOptional(EmployeeNumber);
		Designation = NormalizeOptional(Designation);
		ServiceRequestTicket = NormalizeOptional(ServiceRequestTicket);
		SignedAllocationFormStatus = NormalizeOptional(SignedAllocationFormStatus);
		OldEmployeeNumber = NormalizeOptional(OldEmployeeNumber);
		OldUserName = NormalizeOptional(OldUserName);
		OwnerName = NormalizeOptional(OwnerName);
		OwnerEmail = NormalizeOptional(OwnerEmail);
		Classification = NormalizeOptional(Classification);
		Severity = NormalizeOptional(Severity);
		Remarks = NormalizeOptional(Remarks);
		NewReplacementStatus = NormalizeOptional(NewReplacementStatus);
		DockingStation = NormalizeOptional(DockingStation);
		Keyboard = NormalizeOptional(Keyboard);
		Mouse = NormalizeOptional(Mouse);
		Headset = NormalizeOptional(Headset);
		Printer = NormalizeOptional(Printer);
	}

	public void ApplyTo(Asset asset)
	{
		asset.AssetTag = AssetTag;
		asset.Hostname = Hostname;
		asset.SerialNumber = SerialNumber;
		asset.Name = Name;
		asset.Status = Status;
		asset.Condition = Condition;
		asset.Category = Category;
		asset.AssetType = AssetType;
		asset.Manufacturer = Manufacturer;
		asset.Model = Model;
		asset.AssignedTo = AssignedTo;
		asset.AssignedToEmail = AssignedToEmail;
		asset.Department = Department;
		asset.Location = Location;
		asset.Vendor = Vendor;
		asset.Purpose = Purpose;
		asset.Company = Company;
		asset.Project = Project;
		asset.MacAddress = MacAddress;
		asset.DuplicateSerialNumber = DuplicateSerialNumber;
		asset.Monitor1AssetTag = Monitor1AssetTag;
		asset.Monitor1SerialNumber = Monitor1SerialNumber;
		asset.Monitor2AssetTag = Monitor2AssetTag;
		asset.Monitor2SerialNumber = Monitor2SerialNumber;
		asset.Monitor3AssetTag = Monitor3AssetTag;
		asset.Monitor3SerialNumber = Monitor3SerialNumber;
		asset.OfficeWorkMode = OfficeWorkMode;
		asset.Workstation = Workstation;
		asset.CurrentLocation = CurrentLocation;
		asset.EmployeeNumber = EmployeeNumber;
		asset.Designation = Designation;
		asset.AllocationDate = AllocationDate;
		asset.ServiceRequestTicket = ServiceRequestTicket;
		asset.SignedAllocationFormStatus = SignedAllocationFormStatus;
		asset.ReceivedDate = ReceivedDate;
		asset.OldEmployeeNumber = OldEmployeeNumber;
		asset.OldUserName = OldUserName;
		asset.OwnerName = OwnerName;
		asset.OwnerEmail = OwnerEmail;
		asset.Classification = Classification;
		asset.Severity = Severity;
		asset.Remarks = Remarks;
		asset.NewReplacementStatus = NewReplacementStatus;
		asset.DockingStation = DockingStation;
		asset.Keyboard = Keyboard;
		asset.Mouse = Mouse;
		asset.Headset = Headset;
		asset.Printer = Printer;
		asset.PurchaseDate = PurchaseDate;
		asset.PurchaseCostCents = PurchaseCost.HasValue
			? (long)Math.Round(PurchaseCost.Value * 100m)
			: null;
		asset.WarrantyExpiration = WarrantyExpiration;
	}

	public static AssetInput FromAsset(Asset asset)
	{
		var input = new AssetInput();
		foreach (var property in typeof(AssetInput).GetProperties())
		{
			var source = typeof(Asset).GetProperty(property.Name);
			if (source is not null && property.CanWrite && property.PropertyType == source.PropertyType)
			{
				property.SetValue(input, source.GetValue(asset));
			}
		}
		input.PurchaseCost = asset.PurchaseCostCents.HasValue
			? asset.PurchaseCostCents.Value / 100m
			: null;
		input.Version = asset.Version;
		return input;
	}

	public static string? NormalizeOptional(string? value)
	{
		if (!string.IsNullOrWhiteSpace(value))
		{
			return value.Trim();
		}
		return null;
	}

	public static string? NormalizeSerial(string? value)
	{
		string text = NormalizeOptional(value);
		bool flag = text != null;
		if (flag)
		{
			bool flag2;
			switch (text.ToUpperInvariant())
			{
			case "N/A":
			case "UNKNOWN":
			case "NONE":
			case "TBD":
				flag2 = true;
				break;
			default:
				flag2 = false;
				break;
			}
			flag = flag2;
		}
		if (!flag)
		{
			return text;
		}
		return null;
	}
}
