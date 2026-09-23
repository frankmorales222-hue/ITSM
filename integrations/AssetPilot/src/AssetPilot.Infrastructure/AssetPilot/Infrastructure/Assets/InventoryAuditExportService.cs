using System;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using System.Xml.Linq;
using AssetPilot.Application.Assets;
using AssetPilot.Domain.Assets;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Infrastructure.Assets;

public sealed class InventoryAuditExportService(AssetPilotDbContext db) : IInventoryAuditExportService
{
	public async Task<MemoryStream> ExportAsync(
		string templatePath,
		CancellationToken cancellationToken = default,
		IReadOnlyCollection<int>? assetIds = null)
	{
		if (!File.Exists(templatePath))
		{
			throw new FileNotFoundException("The inventory export template was not found.", templatePath);
		}

		IQueryable<Asset> query = db.Assets
			.AsNoTracking()
			.Where(x => !x.IsArchived);
		if (assetIds is not null)
		{
			query = query.Where(x => assetIds.Contains(x.AssetId));
		}
		List<Asset> assets = await query
			.OrderBy(x => x.AssignedTo ?? "")
			.ThenBy(x => x.Hostname ?? x.AssetTag)
			.ToListAsync(cancellationToken);

		var output = new MemoryStream();
		await using (FileStream template = File.OpenRead(templatePath))
		{
			await template.CopyToAsync(output, cancellationToken);
		}
		output.Position = 0;

		using (var archive = new ZipArchive(output, ZipArchiveMode.Update, leaveOpen: true))
		{
			string sheetPath = FirstSheetPath(archive);
			ZipArchiveEntry sheetEntry = archive.GetEntry(sheetPath)
				?? throw new InvalidOperationException("The export template contains no readable worksheet.");

			XDocument document;
			using (Stream input = sheetEntry.Open())
			{
				document = XDocument.Load(input);
			}

			XNamespace ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
			XElement sheetData = document.Root?.Element(ns + "sheetData")
				?? throw new InvalidOperationException("The export template worksheet is invalid.");
			XElement header = sheetData.Elements(ns + "row").First();
			XElement? sample = sheetData.Elements(ns + "row").Skip(1).FirstOrDefault();
			Dictionary<int, string?> styles = ReadStyles(sample, ns);
			string? dateStyle = sheetData
				.Descendants(ns + "c")
				.FirstOrDefault(cell =>
				{
					string reference = (string?)cell.Attribute("r") ?? "";
					return (reference.StartsWith("V", StringComparison.Ordinal)
							|| reference.StartsWith("Y", StringComparison.Ordinal))
						&& cell.Element(ns + "v") is not null;
				})
				?.Attribute("s")?.Value;
			dateStyle ??= EnsureDateStyle(archive);

			sheetData.RemoveNodes();
			sheetData.Add(header);
			int rowNumber = 2;
			foreach (Asset asset in assets)
			{
				var row = new XElement(ns + "row", new XAttribute("r", rowNumber));
				object?[] values = Values(asset);
				for (int column = 0; column < values.Length; column++)
				{
					string? style = values[column] is DateOnly
						? dateStyle
						: styles.GetValueOrDefault(column);
					row.Add(CreateCell(ns, rowNumber, column, values[column], style));
				}
				sheetData.Add(row);
				rowNumber++;
			}

			XElement? dimension = document.Root?.Element(ns + "dimension");
			dimension?.SetAttributeValue("ref", $"A1:AJ{Math.Max(1, rowNumber - 1)}");

			sheetEntry.Delete();
			ZipArchiveEntry replacement = archive.CreateEntry(sheetPath, CompressionLevel.Optimal);
			using Stream target = replacement.Open();
			document.Save(target);
		}

		output.Position = 0;
		return output;
	}

	private static object?[] Values(Asset x) =>
	[
		x.AssetType,
		x.Hostname ?? x.AssetTag,
		x.SerialNumber,
		x.DuplicateSerialNumber,
		x.MacAddress,
		x.Monitor1AssetTag,
		x.Monitor1SerialNumber,
		x.Monitor2AssetTag,
		x.Monitor2SerialNumber,
		x.Monitor3AssetTag,
		x.Monitor3SerialNumber,
		x.Status,
		x.OfficeWorkMode,
		x.Workstation,
		x.Location,
		x.CurrentLocation,
		x.EmployeeNumber,
		x.AssignedTo,
		x.AssignedToEmail,
		x.Department,
		x.Designation,
		x.AllocationDate,
		x.ServiceRequestTicket,
		x.SignedAllocationFormStatus,
		x.ReceivedDate,
		x.OldEmployeeNumber,
		x.OldUserName,
		x.Company,
		x.OwnerName,
		x.OwnerEmail,
		x.Purpose,
		x.Classification,
		x.Severity,
		x.Project,
		x.Remarks,
		x.NewReplacementStatus
	];

	private static XElement CreateCell(
		XNamespace ns,
		int row,
		int column,
		object? value,
		string? style)
	{
		var cell = new XElement(ns + "c", new XAttribute("r", $"{ColumnName(column)}{row}"));
		if (!string.IsNullOrWhiteSpace(style))
		{
			cell.SetAttributeValue("s", style);
		}
		if (value is DateOnly date)
		{
			cell.Add(new XElement(ns + "v",
				date.ToDateTime(TimeOnly.MinValue).ToOADate().ToString(CultureInfo.InvariantCulture)));
		}
		else if (value is not null)
		{
			cell.SetAttributeValue("t", "inlineStr");
			cell.Add(new XElement(ns + "is",
				new XElement(ns + "t",
					new XAttribute(XNamespace.Xml + "space", "preserve"),
					value.ToString() ?? "")));
		}
		return cell;
	}

	private static Dictionary<int, string?> ReadStyles(XElement? row, XNamespace ns)
	{
		var result = new Dictionary<int, string?>();
		if (row is null)
		{
			return result;
		}
		foreach (XElement cell in row.Elements(ns + "c"))
		{
			result[ColumnIndex((string?)cell.Attribute("r") ?? "")] =
				(string?)cell.Attribute("s");
		}
		return result;
	}

	private static string EnsureDateStyle(ZipArchive archive)
	{
		const string stylesPath = "xl/styles.xml";
		ZipArchiveEntry stylesEntry = archive.GetEntry(stylesPath)
			?? throw new InvalidOperationException("The export template contains no styles.");
		XDocument styles;
		using (Stream input = stylesEntry.Open())
		{
			styles = XDocument.Load(input);
		}
		XNamespace ns = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
		XElement cellFormats = styles.Root?.Element(ns + "cellXfs")
			?? throw new InvalidOperationException("The export template contains no cell formats.");
		int styleIndex = cellFormats.Elements(ns + "xf").Count();
		cellFormats.Add(
			new XElement(
				ns + "xf",
				new XAttribute("numFmtId", 14),
				new XAttribute("fontId", 0),
				new XAttribute("fillId", 0),
				new XAttribute("borderId", 0),
				new XAttribute("xfId", 0),
				new XAttribute("applyNumberFormat", 1)));
		cellFormats.SetAttributeValue("count", styleIndex + 1);
		stylesEntry.Delete();
		ZipArchiveEntry replacement = archive.CreateEntry(stylesPath, CompressionLevel.Optimal);
		using Stream output = replacement.Open();
		styles.Save(output);
		return styleIndex.ToString(CultureInfo.InvariantCulture);
	}

	private static string FirstSheetPath(ZipArchive archive)
	{
		XNamespace spreadsheet = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
		XNamespace officeRelationships = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
		XNamespace packageRelationships = "http://schemas.openxmlformats.org/package/2006/relationships";
		using Stream workbookStream = archive.GetEntry("xl/workbook.xml")?.Open()
			?? throw new InvalidOperationException("Invalid .xlsx template.");
		string relationshipId = (string?)XDocument.Load(workbookStream)
			.Descendants(spreadsheet + "sheet")
			.First()
			.Attribute(officeRelationships + "id")
			?? throw new InvalidOperationException("The template contains no worksheets.");
		using Stream relationshipsStream = archive.GetEntry("xl/_rels/workbook.xml.rels")?.Open()
			?? throw new InvalidOperationException("Invalid template relationships.");
		string target = (string?)XDocument.Load(relationshipsStream)
			.Descendants(packageRelationships + "Relationship")
			.Single(x => (string?)x.Attribute("Id") == relationshipId)
			.Attribute("Target")
			?? throw new InvalidOperationException("The template worksheet cannot be resolved.");
		return target.StartsWith("/")
			? target.TrimStart('/')
			: "xl/" + target.Replace('\\', '/');
	}

	private static int ColumnIndex(string reference)
	{
		int result = 0;
		foreach (char character in reference.TakeWhile(char.IsLetter))
		{
			result = result * 26 + char.ToUpperInvariant(character) - 'A' + 1;
		}
		return Math.Max(0, result - 1);
	}

	private static string ColumnName(int index)
	{
		string result = "";
		for (int value = index + 1; value > 0; value = (value - 1) / 26)
		{
			result = (char)('A' + (value - 1) % 26) + result;
		}
		return result;
	}
}
