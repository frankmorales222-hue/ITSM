using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Claims;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Auditing;
using AssetPilot.Domain.Assets;
using AssetPilot.Domain.MasterData;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Web.Pages.Assets;

[Authorize(Policy = "Assets.Edit")]
public sealed class EditModel(AssetPilotDbContext db, IAuditService audit, IAuthorizationService authorization) : PageModel
{
	[BindProperty]
	public int Id { get; set; }

	[BindProperty]
	public int Version { get; set; }

	[BindProperty]
	public AssetInput Input { get; set; } = new AssetInput();

	public async Task<IActionResult> OnGetAsync(int id, CancellationToken cancellationToken)
	{
		Asset asset = await db.Assets.AsNoTracking().SingleOrDefaultAsync((Asset x) => x.AssetId == id && !x.IsArchived, cancellationToken);
		if (asset == null)
		{
			return NotFound();
		}
		Id = id;
		Input = AssetInput.FromAsset(asset);
		Version = asset.Version;
		await LoadReferenceOptionsAsync(cancellationToken);
		return Page();
	}

	public async Task<IActionResult> OnPostAsync(CancellationToken cancellationToken)
	{
		Normalize();
		bool flag = !base.ModelState.IsValid;
		if (!flag)
		{
			flag = !(await IsUniqueAsync(cancellationToken));
		}
		if (flag)
		{
			await LoadReferenceOptionsAsync(cancellationToken);
			return Page();
		}
		Asset asset = await db.Assets.SingleOrDefaultAsync((Asset x) => x.AssetId == Id && !x.IsArchived, cancellationToken);
		if (asset == null)
		{
			return NotFound();
		}
		if (asset.Version != Version)
		{
			base.ModelState.AddModelError(string.Empty, "This asset changed after you opened it. Review the latest values and try again.");
			Input = AssetInput.FromAsset(asset);
			Version = asset.Version;
			await LoadReferenceOptionsAsync(cancellationToken);
			return Page();
		}
		flag = !string.Equals(asset.Status, Input.Status, StringComparison.OrdinalIgnoreCase);
		if (flag)
		{
			flag = !(await authorization.AuthorizeAsync(base.User, "Assets.ChangeStatus")).Succeeded;
		}
		if (flag)
		{
			return Forbid();
		}
		var before = new
		{
			asset.AssetTag, asset.Hostname, asset.SerialNumber, asset.Name, asset.Status, asset.Condition, asset.Category, asset.AssetType, asset.AssignedTo, asset.Location,
			asset.Version
		};
		string status = asset.Status;
		Apply(asset);
		if (!string.Equals(status, asset.Status, StringComparison.OrdinalIgnoreCase))
		{
			asset.StatusHistory.Add(new AssetStatusHistory
			{
				FromStatus = status,
				ToStatus = asset.Status,
				ChangedUtc = DateTime.UtcNow,
				ChangedByUserId = base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"),
				Reason = "Asset edited"
			});
		}
		asset.ModifiedUtc = DateTime.UtcNow;
		asset.Version++;
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync("Asset.Updated", "Asset", asset.AssetId.ToString(), base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), before, new
		{
			asset.AssetTag, asset.Hostname, asset.SerialNumber, asset.Name, asset.Status, asset.Condition, asset.Category, asset.AssetType, asset.AssignedTo, asset.Location,
			asset.Version
		}, null, base.HttpContext.TraceIdentifier, cancellationToken);
		base.TempData["Success"] = asset.AssetTag + " was updated.";
		return RedirectToPage("Details", new
		{
			id = asset.AssetId
		});
	}

	private void Apply(Asset x)
	{
		Input.ApplyTo(x);
	}

	private void Normalize()
	{
		Input.Normalize();
	}

	private async Task<bool> IsUniqueAsync(CancellationToken cancellationToken)
	{
		bool duplicateTag = await db.Assets.AnyAsync((Asset x) => x.AssetId != Id && x.AssetTag == Input.AssetTag, cancellationToken);
		bool flag = Input.Hostname != null;
		if (flag)
		{
			flag = await db.Assets.AnyAsync((Asset x) => x.AssetId != Id && x.Hostname == Input.Hostname, cancellationToken);
		}
		bool duplicateHostname = flag;
		flag = Input.SerialNumber != null;
		if (flag)
		{
			flag = await db.Assets.AnyAsync((Asset x) => x.AssetId != Id && x.SerialNumber == Input.SerialNumber, cancellationToken);
		}
		bool flag2 = flag;
		if (duplicateTag)
		{
			base.ModelState.AddModelError("Input.AssetTag", "That asset tag is already in use.");
		}
		if (duplicateHostname)
		{
			base.ModelState.AddModelError("Input.Hostname", "That hostname is already in use.");
		}
		if (flag2)
		{
			base.ModelState.AddModelError("Input.SerialNumber", "That serial number is already in use.");
		}
		return !duplicateTag && !duplicateHostname && !flag2;
	}

	private async Task LoadReferenceOptionsAsync(CancellationToken cancellationToken)
	{
		var source = await (from item in db.ReferenceDataItems.AsNoTracking()
			where item.IsActive
			orderby item.Name
			select new { item.Kind, item.Name }).ToListAsync(cancellationToken);
		base.ViewData["ReferenceOptions"] = (from item in source
			group item by item.Kind).ToDictionary(group => group.Key, group => (IReadOnlyList<string>)group.Select(item => item.Name).ToList());
	}
}
