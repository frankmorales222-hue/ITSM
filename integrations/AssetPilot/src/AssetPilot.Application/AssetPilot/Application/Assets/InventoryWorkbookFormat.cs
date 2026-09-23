using System;
using System.Collections.Generic;
using System.Linq;

namespace AssetPilot.Application.Assets;

public static class InventoryWorkbookFormat
{
	public const string SheetName = "US Master Inventory";

	public static IReadOnlyList<string> Headers { get; } = new[]
	{
		"Asset Type",
		"Asset Tag / Hostname",
		"Serial number",
		"Duplicate Sr No.",
		"MAC Address",
		"Asset Tag / Hostname For Monitor No. 1",
		"Monitor Serial Number - No. 1",
		"Asset Tag / Hostname For Monitor No. 2",
		"Monitor Serial Number - No. 2",
		"Asset Tag / Hostname For Monitor No. 3",
		"Monitor Serial Number - No. 3",
		"Asset Status",
		"In Office / WFH-OOO (Out Of Office)",
		"Workstation",
		"Location",
		"Current Location",
		"Employee ID",
		"User Name",
		"User Email ID",
		"Department",
		"Designation",
		"Date Of Allocation",
		"Service Request Ticket No",
		"Signed Allocation Form Status (Availabe / Not Available / Pending)",
		"Date Of Received",
		"Old User Employee ID",
		"Old User Name",
		"Company Name (For Laptop) ",
		"Owner Name (HOD Name)",
		"Owner Email ID",
		"Purpose",
		"Classifications",
		"Severity / Identification",
		"Projects",
		"Remarks",
		"Status NEW / Replacment"
	};

	public static IReadOnlyList<string> LegacyHeaders { get; } = Headers
		.Take(1)
		.Concat(new[] { "Asset Type 1" })
		.Concat(Headers.Skip(1))
		.ToArray();

	public static bool HasExactHeaders(IReadOnlyList<string> headers) =>
		headers.Count == Headers.Count
		&& headers
			.Zip(Headers)
			.All(pair => string.Equals(
				pair.First?.TrimEnd(),
				pair.Second.TrimEnd(),
				StringComparison.Ordinal));

	public static bool HasLegacyHeaders(IReadOnlyList<string> headers) =>
		headers.Count == LegacyHeaders.Count
		&& headers
			.Zip(LegacyHeaders)
			.All(pair => string.Equals(
				pair.First?.TrimEnd(),
				pair.Second.TrimEnd(),
				StringComparison.Ordinal));
}
