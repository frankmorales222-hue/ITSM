using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Cryptography;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using System.Xml.Linq;
using AssetPilot.Application.Assets;
using AssetPilot.Application.Auditing;
using AssetPilot.Domain.Assets;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Infrastructure.Assets;

public sealed class AssetImportService(AssetPilotDbContext db, IAuditService audit) : IAssetImportService
{
	private sealed record ImportAsset(string AssetTag, string? Hostname, string? SerialNumber, string Name, string Status, string Condition, string Category, string AssetType, string? AssignedTo, string? AssignedToEmail, string? Department, string? Location, string? Purpose, string? Company, string? Project, string? MacAddress, string SourceReference)
	{
		public string? DuplicateSerialNumber { get; init; }
		public string? Monitor1AssetTag { get; init; }
		public string? Monitor1SerialNumber { get; init; }
		public string? Monitor2AssetTag { get; init; }
		public string? Monitor2SerialNumber { get; init; }
		public string? Monitor3AssetTag { get; init; }
		public string? Monitor3SerialNumber { get; init; }
		public string? OfficeWorkMode { get; init; }
		public string? Workstation { get; init; }
		public string? CurrentLocation { get; init; }
		public string? EmployeeNumber { get; init; }
		public string? Designation { get; init; }
		public DateOnly? AllocationDate { get; init; }
		public string? ServiceRequestTicket { get; init; }
		public string? SignedAllocationFormStatus { get; init; }
		public DateOnly? ReceivedDate { get; init; }
		public string? OldEmployeeNumber { get; init; }
		public string? OldUserName { get; init; }
		public string? OwnerName { get; init; }
		public string? OwnerEmail { get; init; }
		public string? Classification { get; init; }
		public string? Severity { get; init; }
		public string? Remarks { get; init; }
		public string? NewReplacementStatus { get; init; }
	}

	private static readonly HashSet<string> EmptyIdentifiers = new HashSet<string>(StringComparer.OrdinalIgnoreCase) { "N/A", "NA", "UNKNOWN", "NONE", "TBD", "-", "--" };

	public async Task<AssetImportResult> ImportAsync(Stream stream, string fileName, bool updateExisting, string? userId, string correlationId, CancellationToken cancellationToken = default(CancellationToken))
	{
		string extension = Path.GetExtension(fileName);
		List<List<string>> list;
		if (extension.Equals(".csv", StringComparison.OrdinalIgnoreCase))
		{
			list = await ReadCsvAsync(stream, cancellationToken);
		}
		else
		{
			if (!extension.Equals(".xlsx", StringComparison.OrdinalIgnoreCase))
			{
				throw new InvalidOperationException("Only .xlsx and .csv files are supported.");
			}
			list = ReadXlsx(stream);
		}
		List<List<string>> rows = list;
		if (rows.Count == 0)
		{
			return new AssetImportResult(0, 0, 0, 0, 0, new global::_003C_003Ez__ReadOnlySingleElementList<string>("The file is empty."));
		}
		bool canonicalFormat = InventoryWorkbookFormat.HasExactHeaders(rows[0]);
		bool legacyFormat = InventoryWorkbookFormat.HasLegacyHeaders(rows[0]);
		if (!canonicalFormat && !legacyFormat)
		{
			int dataRows = Math.Max(0, rows.Count - 1);
			return new AssetImportResult(
				dataRows,
				0,
				0,
				0,
				dataRows,
				new global::_003C_003Ez__ReadOnlySingleElementList<string>(
					"The workbook does not match the Asset inventory US.xlsx template. Use the 36 columns from Asset Type through Status NEW / Replacment without renaming or reordering them."));
		}
		if (legacyFormat)
		{
			rows = rows
				.Select(row => row.Where((_, index) => index != 1).ToList())
				.ToList();
		}
		if (rows.Count < 2)
		{
			return new AssetImportResult(0, 0, 0, 0, 0, new global::_003C_003Ez__ReadOnlySingleElementList<string>("The file contains no data rows."));
		}
		Dictionary<string, int> headers = (from item in rows[0].Select((string value, int index) => (Key: HeaderKey(value), Index: index))
			where item.Key.Length > 0
			select item).GroupBy<(string, int), string>(((string Key, int Index) item) => item.Key, StringComparer.OrdinalIgnoreCase).ToDictionary<IGrouping<string, (string, int)>, string, int>((IGrouping<string, (string Key, int Index)> group) => group.Key, (IGrouping<string, (string Key, int Index)> group) => group.First().Index, StringComparer.OrdinalIgnoreCase);
		if (!HasAny(headers, "assettaghostname", "assettag", "hostname"))
		{
			return new AssetImportResult(rows.Count - 1, 0, 0, 0, rows.Count - 1, new global::_003C_003Ez__ReadOnlySingleElementList<string>("Missing required column: Asset Tag / Hostname."));
		}
		// Archived records still own their unique tag, hostname, and serial number.
		// Include them in duplicate detection so a later import cannot attempt to
		// insert a conflicting replacement record and fail the entire transaction.
		List<Asset> source = await db.Assets.ToListAsync(cancellationToken);
		HashSet<Asset> assetsExistingAtStart = source.ToHashSet();
		Dictionary<string, Asset> byTag = source.ToDictionary<Asset, string>((Asset x) => x.AssetTag, StringComparer.OrdinalIgnoreCase);
		Dictionary<string, Asset> byHostname = source.Where((Asset x) => HasIdentifier(x.Hostname)).GroupBy<Asset, string>((Asset x) => x.Hostname, StringComparer.OrdinalIgnoreCase).ToDictionary<IGrouping<string, Asset>, string, Asset>((IGrouping<string, Asset> x) => x.Key, (IGrouping<string, Asset> x) => x.First(), StringComparer.OrdinalIgnoreCase);
		Dictionary<string, Asset> bySerial = source.Where((Asset x) => HasIdentifier(x.SerialNumber)).GroupBy<Asset, string>((Asset x) => x.SerialNumber, StringComparer.OrdinalIgnoreCase).ToDictionary<IGrouping<string, Asset>, string, Asset>((IGrouping<string, Asset> x) => x.Key, (IGrouping<string, Asset> x) => x.First(), StringComparer.OrdinalIgnoreCase);
		HashSet<string> reviewFingerprints = new(
			await db.AssetImportReviews
				.Select(x => x.Fingerprint)
				.ToListAsync(cancellationToken),
			StringComparer.OrdinalIgnoreCase);
		bool queueDuplicates = !updateExisting
			&& !correlationId.Equals("startup-inventory-seed", StringComparison.OrdinalIgnoreCase)
			&& !correlationId.StartsWith("duplicate-review-", StringComparison.OrdinalIgnoreCase);
		int created = 0;
		int updated = 0;
		int enriched = 0;
		int skipped = 0;
		int rejected = 0;
		int queued = 0;
		int monitorWarnings = 0;
		List<string> messages = new List<string>();
		DateTime now = DateTime.UtcNow;
		for (int num = 1; num < rows.Count; num++)
		{
			List<string> list2 = rows[num];
			ImportAsset importAsset = MapPrimary(list2, headers, fileName, num + 1);
			if ((object)importAsset == null)
			{
				if (list2.Any((string value) => !string.IsNullOrWhiteSpace(value)))
				{
					rejected++;
				}
				continue;
			}
			if (HasIncompleteMonitorInformation(importAsset))
			{
				monitorWarnings++;
			}
			Process(importAsset, list2, num + 1);
		}
		await db.SaveChangesAsync(cancellationToken);
		if (created > 0 || updated > 0)
		{
			await audit.WriteAsync("Assets.Imported", "AssetImport", correlationId, userId, null, new
			{
				FileName = Path.GetFileName(fileName),
				SourceRows = rows.Count - 1,
				Created = created,
				Updated = updated,
				Skipped = skipped,
				Rejected = rejected
			}, null, correlationId, cancellationToken);
		}
		messages.Insert(0, $"Processed {rows.Count - 1} source rows from {Path.GetFileName(fileName)}.");
		if (queued > 0)
		{
			messages.Insert(1, $"{queued} duplicate row(s) were added to Duplicate Review.");
		}
		if (enriched > 0)
		{
			messages.Insert(1, $"{enriched} existing asset(s) had blank fields safely filled from the workbook.");
		}
		if (monitorWarnings > 0)
		{
			messages.Insert(1, $"{monitorWarnings} row(s) have incomplete monitor information and are flagged on the asset details page.");
		}
		return new AssetImportResult(rows.Count - 1, created, updated, skipped, rejected, messages.Take(50).ToList());
		void Process(ImportAsset importAsset2, IReadOnlyList<string> rowValues, int rowNumber)
		{
			if (!HasIdentifier(importAsset2.AssetTag))
			{
				rejected++;
				if (messages.Count < 49)
				{
					messages.Add("Skipped " + importAsset2.SourceReference + ": asset tag is blank.");
				}
			}
			else
			{
				Asset asset = null;
				string? matchReason = null;
				Asset value2;
				Asset value3;
				if (byTag.TryGetValue(importAsset2.AssetTag, out var value))
				{
					asset = value;
					matchReason = $"Asset tag/hostname matches {value.AssetTag}.";
				}
				else if (HasIdentifier(importAsset2.Hostname) && byHostname.TryGetValue(importAsset2.Hostname, out value2))
				{
					asset = value2;
					matchReason = $"Hostname matches {value2.Hostname}.";
				}
				else if (HasIdentifier(importAsset2.SerialNumber) && bySerial.TryGetValue(importAsset2.SerialNumber, out value3))
				{
					asset = value3;
					matchReason = $"Serial number matches {value3.SerialNumber}.";
				}
				if (asset != null)
				{
					if (!updateExisting)
					{
						if (assetsExistingAtStart.Contains(asset) && FillMissing(asset, importAsset2))
						{
							asset.ModifiedUtc = now;
							asset.Version++;
							updated++;
							enriched++;
						}
						else
						{
							skipped++;
							if (queueDuplicates)
							{
								string fingerprint = Fingerprint(rowValues);
								if (reviewFingerprints.Add(fingerprint))
								{
									db.AssetImportReviews.Add(new AssetImportReview
									{
										Fingerprint = fingerprint,
										SourceFileName = Path.GetFileName(fileName),
										SourceRowNumber = rowNumber,
										MatchReason = matchReason ?? "The row matches an existing asset.",
										MatchingAsset = asset,
										RowValuesJson = JsonSerializer.Serialize(
											rowValues
												.Take(InventoryWorkbookFormat.Headers.Count)
												.Concat(Enumerable.Repeat(
													"",
													Math.Max(0, InventoryWorkbookFormat.Headers.Count - rowValues.Count)))
												.Take(InventoryWorkbookFormat.Headers.Count)
												.ToArray()),
										Status = "Pending",
										CreatedUtc = now,
										ModifiedUtc = now
									});
									queued++;
								}
							}
						}
					}
					else
					{
						string status = asset.Status;
						Apply(asset, importAsset2);
						if (!string.Equals(status, asset.Status, StringComparison.OrdinalIgnoreCase))
						{
							asset.StatusHistory.Add(new AssetStatusHistory
							{
								FromStatus = status,
								ToStatus = asset.Status,
								ChangedUtc = now,
								ChangedByUserId = userId,
								Reason = "Updated from " + Path.GetFileName(fileName)
							});
						}
						asset.ModifiedUtc = now;
						asset.Version++;
						updated++;
					}
				}
				else
				{
					Asset asset2 = new Asset
					{
						AssetTag = importAsset2.AssetTag,
						Name = importAsset2.Name,
						Status = importAsset2.Status,
						Condition = importAsset2.Condition,
						Category = importAsset2.Category,
						AssetType = importAsset2.AssetType,
						CreatedUtc = now,
						ModifiedUtc = now
					};
					Apply(asset2, importAsset2);
					asset2.StatusHistory.Add(new AssetStatusHistory
					{
						ToStatus = asset2.Status,
						ChangedUtc = now,
						ChangedByUserId = userId,
						Reason = "Imported from " + Path.GetFileName(fileName)
					});
					db.Assets.Add(asset2);
					byTag[asset2.AssetTag] = asset2;
					if (HasIdentifier(asset2.Hostname))
					{
						byHostname[asset2.Hostname] = asset2;
					}
					if (HasIdentifier(asset2.SerialNumber))
					{
						bySerial[asset2.SerialNumber] = asset2;
					}
					created++;
				}
			}
		}
	}

	private static bool FillMissing(Asset target, ImportAsset source)
	{
		bool changed = false;

		void Fill(string? current, string? incoming, Action<string?> assign)
		{
			if (!HasIdentifier(current) && HasIdentifier(incoming))
			{
				assign(incoming);
				changed = true;
			}
		}

		void FillDate(DateOnly? current, DateOnly? incoming, Action<DateOnly?> assign)
		{
			if (!current.HasValue && incoming.HasValue)
			{
				assign(incoming);
				changed = true;
			}
		}

		Fill(target.Hostname, source.Hostname, value => target.Hostname = value);
		Fill(target.SerialNumber, source.SerialNumber, value => target.SerialNumber = value);
		Fill(target.AssignedTo, source.AssignedTo, value => target.AssignedTo = value);
		Fill(target.AssignedToEmail, source.AssignedToEmail, value => target.AssignedToEmail = value);
		Fill(target.Department, source.Department, value => target.Department = value);
		Fill(target.Location, source.Location, value => target.Location = value);
		Fill(target.Purpose, source.Purpose, value => target.Purpose = value);
		Fill(target.Company, source.Company, value => target.Company = value);
		Fill(target.Project, source.Project, value => target.Project = value);
		Fill(target.MacAddress, source.MacAddress, value => target.MacAddress = value);
		Fill(target.SourceReference, source.SourceReference, value => target.SourceReference = value);
		Fill(target.DuplicateSerialNumber, source.DuplicateSerialNumber, value => target.DuplicateSerialNumber = value);
		Fill(target.Monitor1AssetTag, source.Monitor1AssetTag, value => target.Monitor1AssetTag = value);
		Fill(target.Monitor1SerialNumber, source.Monitor1SerialNumber, value => target.Monitor1SerialNumber = value);
		Fill(target.Monitor2AssetTag, source.Monitor2AssetTag, value => target.Monitor2AssetTag = value);
		Fill(target.Monitor2SerialNumber, source.Monitor2SerialNumber, value => target.Monitor2SerialNumber = value);
		Fill(target.Monitor3AssetTag, source.Monitor3AssetTag, value => target.Monitor3AssetTag = value);
		Fill(target.Monitor3SerialNumber, source.Monitor3SerialNumber, value => target.Monitor3SerialNumber = value);
		Fill(target.OfficeWorkMode, source.OfficeWorkMode, value => target.OfficeWorkMode = value);
		Fill(target.Workstation, source.Workstation, value => target.Workstation = value);
		Fill(target.CurrentLocation, source.CurrentLocation, value => target.CurrentLocation = value);
		Fill(target.EmployeeNumber, source.EmployeeNumber, value => target.EmployeeNumber = value);
		Fill(target.Designation, source.Designation, value => target.Designation = value);
		FillDate(target.AllocationDate, source.AllocationDate, value => target.AllocationDate = value);
		Fill(target.ServiceRequestTicket, source.ServiceRequestTicket, value => target.ServiceRequestTicket = value);
		Fill(target.SignedAllocationFormStatus, source.SignedAllocationFormStatus, value => target.SignedAllocationFormStatus = value);
		FillDate(target.ReceivedDate, source.ReceivedDate, value => target.ReceivedDate = value);
		Fill(target.OldEmployeeNumber, source.OldEmployeeNumber, value => target.OldEmployeeNumber = value);
		Fill(target.OldUserName, source.OldUserName, value => target.OldUserName = value);
		Fill(target.OwnerName, source.OwnerName, value => target.OwnerName = value);
		Fill(target.OwnerEmail, source.OwnerEmail, value => target.OwnerEmail = value);
		Fill(target.Classification, source.Classification, value => target.Classification = value);
		Fill(target.Severity, source.Severity, value => target.Severity = value);
		Fill(target.Remarks, source.Remarks, value => target.Remarks = value);
		Fill(target.NewReplacementStatus, source.NewReplacementStatus, value => target.NewReplacementStatus = value);

		return changed;
	}

	private static bool HasIncompleteMonitorInformation(ImportAsset asset) =>
		!HasIdentifier(asset.Monitor1AssetTag) || !HasIdentifier(asset.Monitor1SerialNumber)
		|| !HasIdentifier(asset.Monitor2AssetTag) || !HasIdentifier(asset.Monitor2SerialNumber)
		|| !HasIdentifier(asset.Monitor3AssetTag) || !HasIdentifier(asset.Monitor3SerialNumber);

	private static void Apply(Asset target, ImportAsset source)
	{
		target.AssetTag = source.AssetTag;
		target.Hostname = source.Hostname;
		target.SerialNumber = source.SerialNumber;
		target.Name = source.Name;
		target.Status = source.Status;
		target.Condition = source.Condition;
		target.Category = source.Category;
		target.AssetType = source.AssetType;
		target.AssignedTo = source.AssignedTo;
		target.AssignedToEmail = source.AssignedToEmail;
		target.Department = source.Department;
		target.Location = source.Location;
		target.Purpose = source.Purpose;
		target.Company = source.Company;
		target.Project = source.Project;
		target.MacAddress = source.MacAddress;
		target.SourceReference = source.SourceReference;
		target.DuplicateSerialNumber = source.DuplicateSerialNumber;
		target.Monitor1AssetTag = source.Monitor1AssetTag;
		target.Monitor1SerialNumber = source.Monitor1SerialNumber;
		target.Monitor2AssetTag = source.Monitor2AssetTag;
		target.Monitor2SerialNumber = source.Monitor2SerialNumber;
		target.Monitor3AssetTag = source.Monitor3AssetTag;
		target.Monitor3SerialNumber = source.Monitor3SerialNumber;
		target.OfficeWorkMode = source.OfficeWorkMode;
		target.Workstation = source.Workstation;
		target.CurrentLocation = source.CurrentLocation;
		target.EmployeeNumber = source.EmployeeNumber;
		target.Designation = source.Designation;
		target.AllocationDate = source.AllocationDate;
		target.ServiceRequestTicket = source.ServiceRequestTicket;
		target.SignedAllocationFormStatus = source.SignedAllocationFormStatus;
		target.ReceivedDate = source.ReceivedDate;
		target.OldEmployeeNumber = source.OldEmployeeNumber;
		target.OldUserName = source.OldUserName;
		target.OwnerName = source.OwnerName;
		target.OwnerEmail = source.OwnerEmail;
		target.Classification = source.Classification;
		target.Severity = source.Severity;
		target.Remarks = source.Remarks;
		target.NewReplacementStatus = source.NewReplacementStatus;
	}

	private static ImportAsset? MapPrimary(IReadOnlyList<string> row, IReadOnlyDictionary<string, int> headers, string fileName, int rowNumber)
	{
		string text = Get(row, headers, "assettaghostname", "assettag", "hostname");
		if (!HasIdentifier(text))
		{
			return null;
		}
		string hostname = Meaningful(Get(row, headers, "hostname")) ?? text.Trim();
		string text2 = Clean(Get(row, headers, "assettype", "type")) ?? "Other";
		string text3 = Clean(Get(row, headers, "remarks"));
		return new ImportAsset(
			text.Trim(),
			hostname,
			Meaningful(Get(row, headers, "serialnumber", "serial")),
			text2 + " - " + text.Trim(),
			MapStatus(Get(row, headers, "assetstatus", "status")),
			MapCondition(Get(row, headers, "condition") ?? text3),
			MapCategory(text2),
			text2,
			Clean(Get(row, headers, "username", "assignedto", "employee")),
			Clean(Get(row, headers, "useremailid", "assignedtoemail", "email")),
			Clean(Get(row, headers, "department")),
			Clean(Get(row, headers, "location")),
			Clean(Get(row, headers, "purpose")),
			Clean(Get(row, headers, "companynameforlaptop", "companyname", "company")),
			Clean(Get(row, headers, "projects", "project")),
			Clean(Get(row, headers, "macaddress")),
			$"{Path.GetFileName(fileName)} row {rowNumber}")
		{
			DuplicateSerialNumber = Meaningful(Get(row, headers, "duplicatesrno", "duplicateserialnumber")),
			Monitor1AssetTag = Meaningful(Get(row, headers, "assettaghostnameformonitornumber1", "assettaghostnameformonitorno1")),
			Monitor1SerialNumber = Meaningful(Get(row, headers, "monitorserialnumbernumber1", "monitorserialnumberno1")),
			Monitor2AssetTag = Meaningful(Get(row, headers, "assettaghostnameformonitornumber2", "assettaghostnameformonitorno2")),
			Monitor2SerialNumber = Meaningful(Get(row, headers, "monitorserialnumbernumber2", "monitorserialnumberno2")),
			Monitor3AssetTag = Meaningful(Get(row, headers, "assettaghostnameformonitornumber3", "assettaghostnameformonitorno3")),
			Monitor3SerialNumber = Meaningful(Get(row, headers, "monitorserialnumbernumber3", "monitorserialnumberno3")),
			OfficeWorkMode = Clean(Get(row, headers, "inofficewfhooooutofoffice")),
			Workstation = Clean(Get(row, headers, "workstation")),
			CurrentLocation = Clean(Get(row, headers, "currentlocation")),
			EmployeeNumber = Clean(Get(row, headers, "employeeid")),
			Designation = Clean(Get(row, headers, "designation")),
			AllocationDate = ParseDate(Get(row, headers, "dateofallocation")),
			ServiceRequestTicket = Clean(Get(row, headers, "servicerequestticketno")),
			SignedAllocationFormStatus = Clean(Get(row, headers, "signedallocationformstatusavailabenotavailablepending")),
			ReceivedDate = ParseDate(Get(row, headers, "dateofreceived")),
			OldEmployeeNumber = Clean(Get(row, headers, "olduseremployeeid")),
			OldUserName = Clean(Get(row, headers, "oldusername")),
			OwnerName = Clean(Get(row, headers, "ownernamehodname")),
			OwnerEmail = Clean(Get(row, headers, "owneremailid")),
			Classification = Clean(Get(row, headers, "classifications")),
			Severity = Clean(Get(row, headers, "severityidentification")),
			Remarks = Clean(Get(row, headers, "remarks")),
			NewReplacementStatus = Clean(Get(row, headers, "statusnewreplacment", "statusnewreplacement"))
		};
	}

	private static string Fingerprint(IReadOnlyList<string> values)
	{
		string normalized = string.Join(
			"\u001f",
			values
				.Take(InventoryWorkbookFormat.Headers.Count)
				.Select(value => value.Trim().ToUpperInvariant()));
		return Convert.ToHexString(SHA256.HashData(Encoding.UTF8.GetBytes(normalized)));
	}

	private static DateOnly? ParseDate(string? value)
	{
		string? clean = Clean(value);
		if (clean is null)
		{
			return null;
		}
		if (double.TryParse(clean, System.Globalization.NumberStyles.Float, System.Globalization.CultureInfo.InvariantCulture, out double serial))
		{
			try
			{
				return DateOnly.FromDateTime(DateTime.FromOADate(serial));
			}
			catch (ArgumentException)
			{
			}
		}
		return DateOnly.TryParse(clean, out DateOnly date) ? date : null;
	}

	private static string MapStatus(string? value)
	{
		string text = Clean(value)?.ToUpperInvariant() ?? "";
		if (text.Contains("STOCK") || text.Contains("AVAILABLE") || text.Contains("SPARE"))
		{
			return "In Stock";
		}
		if (text.Contains("PENDING") || text.Contains("RECEIPT"))
		{
			return "Pending Receipt";
		}
		if (text.Contains("REPAIR"))
		{
			return "Repair";
		}
		if (text.Contains("LOST"))
		{
			return "Lost";
		}
		if (text.Contains("UNRETURN") || text.Contains("RECOVERY"))
		{
			return "Recovery Pending";
		}
		if (text.Contains("RETIRED") || text.Contains("DISPOS") || text.Contains("SCRAP"))
		{
			return "Retired";
		}
		return "Active";
	}

	private static string MapCondition(string? value)
	{
		string text = Clean(value)?.ToUpperInvariant() ?? "";
		if (text.Contains("DAMAG"))
		{
			return "Damaged";
		}
		if (text.Contains("POOR"))
		{
			return "Poor";
		}
		if (text.Contains("FAIR"))
		{
			return "Fair";
		}
		if (text.Contains("UNKNOWN"))
		{
			return "Unknown";
		}
		return "Good";
	}

	private static string MapCategory(string type)
	{
		string text = type.ToUpperInvariant();
		if (text.Contains("LAPTOP") || text.Contains("DESKTOP") || text.Contains("SERVER"))
		{
			return "Computer";
		}
		if (text.Contains("PHONE") || text.Contains("MOBILE") || text.Contains("TABLET"))
		{
			return "Mobile Device";
		}
		if (text.Contains("PRINTER"))
		{
			return "Printer";
		}
		if (text.Contains("MONITOR") || text.Contains("KEYBOARD") || text.Contains("MOUSE"))
		{
			return "Peripheral";
		}
		return "Other";
	}

	private static string? Get(IReadOnlyList<string> row, IReadOnlyDictionary<string, int> headers, params string[] aliases)
	{
		foreach (string value in aliases)
		{
			if (headers.TryGetValue(HeaderKey(value), out var value2) && value2 < row.Count)
			{
				return row[value2];
			}
		}
		return null;
	}

	private static bool HasAny(IReadOnlyDictionary<string, int> headers, params string[] aliases)
	{
		return aliases.Any((string alias) => headers.ContainsKey(HeaderKey(alias)));
	}

	private static bool HasIdentifier(string? value)
	{
		if (!string.IsNullOrWhiteSpace(value))
		{
			return !EmptyIdentifiers.Contains(value.Trim());
		}
		return false;
	}

	private static string? Meaningful(string? value)
	{
		if (!HasIdentifier(value))
		{
			return null;
		}
		return value.Trim();
	}

	private static string? Clean(string? value)
	{
		if (!string.IsNullOrWhiteSpace(value) && !EmptyIdentifiers.Contains(value.Trim()))
		{
			return value.Trim();
		}
		return null;
	}

	private static string HeaderKey(string? value)
	{
		return new string((value ?? "").Where(char.IsLetterOrDigit).Select(char.ToLowerInvariant).ToArray());
	}

	private static async Task<List<List<string>>> ReadCsvAsync(Stream stream, CancellationToken cancellationToken)
	{
		using StreamReader reader = new StreamReader(stream, Encoding.UTF8, detectEncodingFromByteOrderMarks: true, -1, leaveOpen: true);
		string text = await reader.ReadToEndAsync(cancellationToken);
		List<List<string>> list = new List<List<string>>();
		List<string> list2 = new List<string>();
		StringBuilder stringBuilder = new StringBuilder();
		bool flag = false;
		for (int i = 0; i < text.Length; i++)
		{
			char c = text[i];
			switch (c)
			{
			case '"':
				if (flag && i + 1 < text.Length && text[i + 1] == '"')
				{
					stringBuilder.Append('"');
					i++;
				}
				else
				{
					flag = !flag;
				}
				continue;
			case ',':
				if (!flag)
				{
					list2.Add(stringBuilder.ToString());
					stringBuilder.Clear();
					continue;
				}
				break;
			}
			if ((c == '\r' || c == '\n') && !flag)
			{
				if (c == '\r' && i + 1 < text.Length && text[i + 1] == '\n')
				{
					i++;
				}
				list2.Add(stringBuilder.ToString());
				stringBuilder.Clear();
				list.Add(list2);
				list2 = new List<string>();
			}
			else
			{
				stringBuilder.Append(c);
			}
		}
		if (stringBuilder.Length > 0 || list2.Count > 0)
		{
			list2.Add(stringBuilder.ToString());
			list.Add(list2);
		}
		return list;
	}

	private static List<List<string>> ReadXlsx(Stream stream)
	{
		using ZipArchive zipArchive = new ZipArchive(stream, ZipArchiveMode.Read, leaveOpen: true);
		List<string> list = ReadSharedStrings(zipArchive);
		string entryName = FirstSheetPath(zipArchive);
		using Stream stream2 = (zipArchive.GetEntry(entryName) ?? throw new InvalidOperationException("The workbook has no readable worksheet.")).Open();
		XDocument xDocument = XDocument.Load(stream2);
		XNamespace xNamespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
		List<List<string>> list2 = new List<List<string>>();
		foreach (XElement item in xDocument.Descendants(xNamespace + "row"))
		{
			List<string> list3 = new List<string>();
			foreach (XElement item2 in item.Elements(xNamespace + "c"))
			{
				int num = ColumnIndex(((string?)item2.Attribute("r")) ?? "");
				while (list3.Count <= num)
				{
					list3.Add("");
				}
				string text = (string?)item2.Attribute("t");
				string text2;
				if (text == "inlineStr")
				{
					text2 = string.Concat(from x in item2.Descendants(xNamespace + "t")
						select x.Value);
				}
				else
				{
					text2 = item2.Element(xNamespace + "v")?.Value ?? "";
					if (text == "s" && int.TryParse(text2, out var result) && result < list.Count)
					{
						text2 = list[result];
					}
				}
				list3[num] = text2;
			}
			list2.Add(list3);
		}
		return list2;
	}

	private static List<string> ReadSharedStrings(ZipArchive archive)
	{
		ZipArchiveEntry entry = archive.GetEntry("xl/sharedStrings.xml");
		if (entry == null)
		{
			return new List<string>();
		}
		using Stream stream = entry.Open();
		XDocument xDocument = XDocument.Load(stream);
		XNamespace ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
		return (from item in xDocument.Descendants(ns + "si")
			select string.Concat(from text in item.Descendants(ns + "t")
				select text.Value)).ToList();
	}

	private static string FirstSheetPath(ZipArchive archive)
	{
		XNamespace xNamespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
		XNamespace xNamespace2 = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
		XNamespace xNamespace3 = "http://schemas.openxmlformats.org/package/2006/relationships";
		using Stream stream = archive.GetEntry("xl/workbook.xml")?.Open() ?? throw new InvalidOperationException("Invalid .xlsx workbook.");
		XDocument xDocument = XDocument.Load(stream);
		string relationshipId = ((string?)xDocument.Descendants(xNamespace + "sheet").FirstOrDefault()?.Attribute(xNamespace2 + "id")) ?? throw new InvalidOperationException("The workbook contains no worksheets.");
		using Stream stream2 = archive.GetEntry("xl/_rels/workbook.xml.rels")?.Open() ?? throw new InvalidOperationException("Invalid workbook relationships.");
		string text = ((string?)XDocument.Load(stream2).Descendants(xNamespace3 + "Relationship").Single((XElement item) => (string?)item.Attribute("Id") == relationshipId)
			.Attribute("Target")) ?? throw new InvalidOperationException("The first worksheet cannot be resolved.");
		return text.StartsWith("/") ? text.TrimStart('/') : ("xl/" + text.Replace('\\', '/'));
	}

	private static int ColumnIndex(string reference)
	{
		int num = 0;
		foreach (char item in reference.TakeWhile(char.IsLetter))
		{
			num = num * 26 + (char.ToUpperInvariant(item) - 65 + 1);
		}
		return Math.Max(0, num - 1);
	}
}
