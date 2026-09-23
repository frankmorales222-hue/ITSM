using System;
using System.Collections.Generic;
using System.Security.Claims;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Operations;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace AssetPilot.Web.Pages.System.Backups;

[Authorize(Policy = "Operations.ViewJobs")]
public sealed class IndexModel(IBackupService backupService, IAuthorizationService authorization) : PageModel
{
	public IReadOnlyList<BackupInfo> Backups { get; private set; } = Array.Empty<BackupInfo>();

	public bool CanRunBackup { get; private set; }

	public async Task OnGetAsync(CancellationToken cancellationToken)
	{
		await LoadAsync(cancellationToken);
	}

	public async Task<IActionResult> OnPostCreateAsync(CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(base.User, "Operations.RunBackup")).Succeeded)
		{
			return Forbid();
		}
		BackupResult backupResult = await backupService.CreateAndVerifyAsync(base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), base.HttpContext.TraceIdentifier, cancellationToken);
		base.TempData["Success"] = $"{backupResult.FileName} was created and verified with {backupResult.AssetCount} assets.";
		return RedirectToPage();
	}

	private async Task LoadAsync(CancellationToken cancellationToken)
	{
		Backups = await backupService.ListAsync(cancellationToken);
		CanRunBackup = (await authorization.AuthorizeAsync(base.User, "Operations.RunBackup")).Succeeded;
	}
}
