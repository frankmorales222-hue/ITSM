using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Linq;
using System.Security.Claims;
using System.Text;
using System.Threading;
using System.Threading.Tasks;
using System.Xml.Linq;
using AssetPilot.Application.Auditing;
using AssetPilot.Domain.People;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Web.Pages.Employees;

[Authorize(Policy = "Employees.Import")]
public sealed class ImportModel(AssetPilotDbContext db, IAuditService audit) : PageModel
{
	public sealed record ImportResult(int Rows, int Created, int Updated, int Skipped, int Rejected);

	[BindProperty]
	public IFormFile? Upload { get; set; }

	[BindProperty]
	public bool UpdateExisting { get; set; }

	public ImportResult? Result { get; private set; }

	public void OnGet()
	{
	}

	public async Task<IActionResult> OnPostAsync(CancellationToken cancellationToken)
	{
		if (Upload == null || Upload.Length == 0L)
		{
			base.ModelState.AddModelError("Upload", "Choose a non-empty .xlsx or .csv file.");
			return Page();
		}
		string extension = Path.GetExtension(Upload.FileName);
		if (!extension.Equals(".csv", StringComparison.OrdinalIgnoreCase) && !extension.Equals(".xlsx", StringComparison.OrdinalIgnoreCase))
		{
			base.ModelState.AddModelError("Upload", "Only .xlsx and .csv files are supported.");
			return Page();
		}
		IActionResult result;
		await using (Stream stream = Upload.OpenReadStream())
		{
			List<List<string>> list = (List<List<string>>)((!extension.Equals(".csv", StringComparison.OrdinalIgnoreCase)) ? ((IList)ReadXlsx(stream)) : ((IList)(await ReadCsvAsync(stream, cancellationToken))));
			List<List<string>> rows = list;
			if (rows.Count < 2)
			{
				base.ModelState.AddModelError("Upload", "The file has no data rows.");
				result = Page();
			}
			else
			{
				Dictionary<string, int> headers = (from x in rows[0].Select((string value, int index) => (Key: Key(value), index: index))
					where x.Key.Length > 0
					group x by x.Key).ToDictionary((IGrouping<string, (string Key, int index)> x) => x.Key, (IGrouping<string, (string Key, int index)> x) => x.First().index);
				if (!headers.ContainsKey("email") && !headers.ContainsKey("emailaddress"))
				{
					base.ModelState.AddModelError("Upload", "The file must contain an Email column.");
					result = Page();
				}
				else
				{
					List<Employee> list2 = await db.Employees.Where(x => !x.IsDeleted).ToListAsync(cancellationToken);
					int created = 0;
					int updated = 0;
					int skipped = 0;
					int rejected = 0;
					DateTime utcNow = DateTime.UtcNow;
					for (int num = 1; num < rows.Count; num++)
					{
						List<string> list3 = rows[num];
						string email = Get(list3, headers, "email", "emailaddress")?.Trim();
						string text = Get(list3, headers, "displayname", "name", "employee")?.Trim();
						if (string.IsNullOrWhiteSpace(email) || !email.Contains('@') || string.IsNullOrWhiteSpace(text))
						{
							if (list3.Any((string x) => !string.IsNullOrWhiteSpace(x)))
							{
								rejected++;
							}
							continue;
						}
						string number = Get(list3, headers, "employeenumber", "employeeid", "number")?.Trim();
						Employee employee = list2.FirstOrDefault((Employee x) => x.Email.Equals(email, StringComparison.OrdinalIgnoreCase) || (!string.IsNullOrWhiteSpace(number) && x.EmployeeNumber.Equals(number, StringComparison.OrdinalIgnoreCase)));
						if (employee != null && !UpdateExisting)
						{
							skipped++;
							continue;
						}
						if (employee == null)
						{
							number = (string.IsNullOrWhiteSpace(number) ? $"EMP-{list2.Count + 1:D5}" : number);
							while (list2.Any((Employee x) => x.EmployeeNumber.Equals(number, StringComparison.OrdinalIgnoreCase)))
							{
								number = $"EMP-{list2.Count + 1:D5}-{created + 1}";
							}
							employee = new Employee
							{
								EmployeeNumber = number,
								DisplayName = text,
								Email = email,
								CreatedUtc = utcNow,
								ModifiedUtc = utcNow
							};
							db.Employees.Add(employee);
							list2.Add(employee);
							created++;
						}
						else
						{
							updated++;
							employee.Version++;
						}
						employee.DisplayName = text;
						employee.Email = email;
						employee.Department = Clean(Get(list3, headers, "department"));
						employee.Manager = Clean(Get(list3, headers, "manager"));
						employee.Location = Clean(Get(list3, headers, "location", "office"));
						employee.Phone = Clean(Get(list3, headers, "phone", "phonenumber"));
						employee.IsActive = !string.Equals(Get(list3, headers, "status"), "Inactive", StringComparison.OrdinalIgnoreCase);
						employee.ModifiedUtc = utcNow;
					}
					await db.SaveChangesAsync(cancellationToken);
					string traceIdentifier = base.HttpContext.TraceIdentifier;
					await audit.WriteAsync("Employees.Imported", "EmployeeImport", traceIdentifier, base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), null, new
					{
						FileName = Path.GetFileName(Upload.FileName),
						Created = created,
						Updated = updated,
						Skipped = skipped,
						Rejected = rejected
					}, null, traceIdentifier, cancellationToken);
					Result = new ImportResult(rows.Count - 1, created, updated, skipped, rejected);
					result = Page();
				}
			}
		}
		return result;
	}

	private static string Key(string value)
	{
		return new string(value.Where(char.IsLetterOrDigit).Select(char.ToLowerInvariant).ToArray());
	}

	private static string? Get(IReadOnlyList<string> row, IReadOnlyDictionary<string, int> headers, params string[] names)
	{
		foreach (string key in names)
		{
			if (headers.TryGetValue(key, out var value) && value < row.Count)
			{
				return row[value];
			}
		}
		return null;
	}

	private static string? Clean(string? value)
	{
		if (!string.IsNullOrWhiteSpace(value))
		{
			return value.Trim();
		}
		return null;
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
		using Stream stream2 = (zipArchive.GetEntry(FirstSheetPath(zipArchive)) ?? throw new InvalidOperationException("No readable worksheet.")).Open();
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
				string? text = (string?)item2.Attribute("t");
				string text2 = ((text == "inlineStr") ? string.Concat(from x in item2.Descendants(xNamespace + "t")
					select x.Value) : (item2.Element(xNamespace + "v")?.Value ?? ""));
				if (text == "s" && int.TryParse(text2, out var result) && result < list.Count)
				{
					text2 = list[result];
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
		return (from x in xDocument.Descendants(ns + "si")
			select string.Concat(from t in x.Descendants(ns + "t")
				select t.Value)).ToList();
	}

	private static string FirstSheetPath(ZipArchive archive)
	{
		XNamespace xNamespace = "http://schemas.openxmlformats.org/spreadsheetml/2006/main";
		XNamespace xNamespace2 = "http://schemas.openxmlformats.org/officeDocument/2006/relationships";
		XNamespace xNamespace3 = "http://schemas.openxmlformats.org/package/2006/relationships";
		using Stream stream = archive.GetEntry("xl/workbook.xml")?.Open() ?? throw new InvalidOperationException("Invalid workbook.");
		XDocument xDocument = XDocument.Load(stream);
		string id = (string?)xDocument.Descendants(xNamespace + "sheet").First().Attribute(xNamespace2 + "id");
		using Stream stream2 = archive.GetEntry("xl/_rels/workbook.xml.rels")?.Open() ?? throw new InvalidOperationException("Invalid workbook.");
		string text = ((string?)XDocument.Load(stream2).Descendants(xNamespace3 + "Relationship").Single((XElement x) => (string?)x.Attribute("Id") == id)
			.Attribute("Target")) ?? throw new InvalidOperationException("Worksheet not found.");
		return text.StartsWith('/') ? text.TrimStart('/') : ("xl/" + text.Replace('\\', '/'));
	}

	private static int ColumnIndex(string reference)
	{
		int num = 0;
		foreach (char item in reference.TakeWhile(char.IsLetter))
		{
			num = num * 26 + char.ToUpperInvariant(item) - 65 + 1;
		}
		return Math.Max(0, num - 1);
	}
}
