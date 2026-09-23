using System;
using System.ComponentModel.DataAnnotations;
using System.IO;
using System.Security.Claims;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Assets;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.Extensions.Hosting;

namespace AssetPilot.Web.Pages.Assets;

[Authorize(Policy = "Assets.Import")]
[RequestSizeLimit(20971520L)]
public sealed class ImportModel(IAssetImportService importer, IHostEnvironment environment) : PageModel
{
	[BindProperty]
	[Required]
	[Display(Name = "Inventory file")]
	public IFormFile? Upload { get; set; }

	[BindProperty]
	public bool UpdateExisting { get; set; }

	public AssetImportResult? Result { get; private set; }

	public IActionResult OnGetTemplate()
	{
		string path = Path.Combine(
			environment.ContentRootPath,
			"SeedData",
			"Asset inventory US template.xlsx");
		return PhysicalFile(
			path,
			"application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
			"Asset inventory US.xlsx");
	}

	public async Task<IActionResult> OnPostAsync(CancellationToken cancellationToken)
	{
		if (Upload == null || Upload.Length == 0L)
		{
			base.ModelState.AddModelError("Upload", "Choose a non-empty .xlsx or .csv file.");
			return Page();
		}
		string extension = Path.GetExtension(Upload.FileName);
		if (!extension.Equals(".xlsx", StringComparison.OrdinalIgnoreCase) && !extension.Equals(".csv", StringComparison.OrdinalIgnoreCase))
		{
			base.ModelState.AddModelError("Upload", "Only .xlsx and .csv files are supported.");
			return Page();
		}
		if (Upload.Length > 20971520)
		{
			base.ModelState.AddModelError("Upload", "The file must be 20 MB or smaller.");
			return Page();
		}
		try
		{
			await using Stream stream = Upload.OpenReadStream();
			Result = await importer.ImportAsync(stream, Path.GetFileName(Upload.FileName), UpdateExisting, base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), base.HttpContext.TraceIdentifier, cancellationToken);
		}
		catch (InvalidDataException)
		{
			base.ModelState.AddModelError("Upload", "That Excel file is damaged or is not a valid .xlsx workbook.");
		}
		catch (InvalidOperationException ex2)
		{
			base.ModelState.AddModelError("Upload", ex2.Message);
		}
		return Page();
	}
}
