using System.Collections.Generic;

namespace AssetPilot.Domain.MasterData;

public static class ReferenceDataKinds
{
	public const string Organization = "Organization";

	public const string Department = "Department";

	public const string Location = "Location";

	public const string StorageLocation = "StorageLocation";

	public const string Category = "Category";

	public const string AssetType = "AssetType";

	public const string Manufacturer = "Manufacturer";

	public const string Model = "Model";

	public const string Vendor = "Vendor";

	public const string Project = "Project";

	public const string Workstation = "Workstation";

	public const string LifecycleStatus = "LifecycleStatus";

	public const string Condition = "Condition";

	public const string Purpose = "Purpose";

	public const string Classification = "Classification";

	public const string Severity = "Severity";

	public static IReadOnlyList<string> All { get; } = new _003C_003Ez__ReadOnlyArray<string>(new string[16]
	{
		"Organization", "Department", "Location", "StorageLocation", "Category", "AssetType", "Manufacturer", "Model", "Vendor", "Project",
		"Workstation", "LifecycleStatus", "Condition", "Purpose", "Classification", "Severity"
	});

	public static string DisplayName(string kind)
	{
		return kind switch
		{
			"StorageLocation" => "Storage locations", 
			"AssetType" => "Asset types", 
			"LifecycleStatus" => "Lifecycle statuses", 
			"Category" => "Categories", 
			"Severity" => "Severities", 
			_ => kind + "s", 
		};
	}

	public static string? ParentKind(string kind)
	{
		switch (kind)
		{
		case "Department":
		case "Project":
		case "Location":
			return "Organization";
		case "StorageLocation":
		case "Workstation":
			return "Location";
		case "AssetType":
			return "Category";
		case "Model":
			return "Manufacturer";
		default:
			return null;
		}
	}
}
