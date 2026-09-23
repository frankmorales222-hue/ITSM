using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Claims;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Auditing;
using AssetPilot.Domain.MasterData;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Web.Pages.Administration.MasterData;

[Authorize(Policy = "MasterData.Manage")]
public sealed class EditModel(AssetPilotDbContext db, IAuditService audit) : PageModel
{
	[BindProperty]
	public int Id { get; set; }

	[BindProperty]
	public ReferenceDataInput Input { get; set; } = new ReferenceDataInput();

	public IReadOnlyList<ReferenceDataItem> ParentOptions { get; private set; } = Array.Empty<ReferenceDataItem>();

	public IReadOnlyList<string> Kinds => ReferenceDataKinds.All;

	public async Task<IActionResult> OnGetAsync(int id, CancellationToken cancellationToken)
	{
		ReferenceDataItem referenceDataItem = await db.ReferenceDataItems.AsNoTracking().SingleOrDefaultAsync((ReferenceDataItem record) => record.ReferenceDataItemId == id, cancellationToken);
		if (referenceDataItem == null)
		{
			return NotFound();
		}
		Id = id;
		Input = new ReferenceDataInput
		{
			Kind = referenceDataItem.Kind,
			Name = referenceDataItem.Name,
			Code = referenceDataItem.Code,
			Notes = referenceDataItem.Notes,
			ParentId = referenceDataItem.ParentId,
			Version = referenceDataItem.Version
		};
		await LoadParentsAsync(cancellationToken);
		return Page();
	}

	public async Task<IActionResult> OnPostAsync(CancellationToken cancellationToken)
	{
		Normalize();
		if (!ReferenceDataKinds.All.Contains<string>(Input.Kind, StringComparer.Ordinal))
		{
			base.ModelState.AddModelError("Input.Kind", "Choose a valid master-data section.");
		}
		if (Input.ParentId == Id)
		{
			base.ModelState.AddModelError("Input.ParentId", "A record cannot be its own parent.");
		}
		if (await db.ReferenceDataItems.AnyAsync((ReferenceDataItem referenceDataItem) => referenceDataItem.ReferenceDataItemId != Id && referenceDataItem.Kind == Input.Kind && (referenceDataItem.Name == Input.Name || (Input.Code != null && referenceDataItem.Code == Input.Code)), cancellationToken))
		{
			base.ModelState.AddModelError("Input.Name", "A record with this name or code already exists in that section.");
		}
		if (!base.ModelState.IsValid)
		{
			await LoadParentsAsync(cancellationToken);
			return Page();
		}
		ReferenceDataItem item = await db.ReferenceDataItems.SingleOrDefaultAsync((ReferenceDataItem record) => record.ReferenceDataItemId == Id, cancellationToken);
		if (item == null)
		{
			return NotFound();
		}
		if (item.Version != Input.Version)
		{
			base.ModelState.AddModelError(string.Empty, "This record changed after you opened it. Reload and try again.");
			await LoadParentsAsync(cancellationToken);
			return Page();
		}
		var before = new { item.Kind, item.Name, item.Code, item.ParentId, item.Notes, item.Version };
		item.Kind = Input.Kind;
		item.Name = Input.Name;
		item.Code = Input.Code;
		item.ParentId = Input.ParentId;
		item.Notes = Input.Notes;
		item.ModifiedUtc = DateTime.UtcNow;
		item.Version++;
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync("MasterData.Updated", "ReferenceDataItem", item.ReferenceDataItemId.ToString(), base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), before, new { item.Kind, item.Name, item.Code, item.ParentId, item.Notes, item.Version }, null, base.HttpContext.TraceIdentifier, cancellationToken);
		base.TempData["Success"] = item.Name + " was updated.";
		return RedirectToPage("Index", new
		{
			kind = item.Kind
		});
	}

	private async Task LoadParentsAsync(CancellationToken cancellationToken)
	{
		string parentKind = ReferenceDataKinds.ParentKind(Input.Kind);
		List<ReferenceDataItem> parentOptions = ((parentKind != null) ? (await (from item in db.ReferenceDataItems.AsNoTracking()
			where item.ReferenceDataItemId != Id && item.IsActive && item.Kind == parentKind
			orderby item.Name
			select item).ToListAsync(cancellationToken)) : new List<ReferenceDataItem>());
		ParentOptions = parentOptions;
	}

	private void Normalize()
	{
		Input.Kind = Input.Kind.Trim();
		Input.Name = Input.Name.Trim();
		Input.Code = (string.IsNullOrWhiteSpace(Input.Code) ? null : Input.Code.Trim().ToUpperInvariant());
		Input.Notes = (string.IsNullOrWhiteSpace(Input.Notes) ? null : Input.Notes.Trim());
	}
}
