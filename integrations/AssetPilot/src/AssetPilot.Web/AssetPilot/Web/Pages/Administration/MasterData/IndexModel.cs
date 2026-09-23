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

[Authorize(Policy = "MasterData.View")]
public sealed class IndexModel(AssetPilotDbContext db, IAuditService audit, IAuthorizationService authorization) : PageModel
{
	[BindProperty(SupportsGet = true)]
	public string Kind { get; set; } = "Location";

	[BindProperty(SupportsGet = true)]
	public string? Query { get; set; }

	[BindProperty(SupportsGet = true)]
	public bool ShowInactive { get; set; }

	[BindProperty]
	public ReferenceDataInput Input { get; set; } = new ReferenceDataInput();

	public IReadOnlyList<ReferenceDataItem> Items { get; private set; } = Array.Empty<ReferenceDataItem>();

	public IReadOnlyList<ReferenceDataItem> ParentOptions { get; private set; } = Array.Empty<ReferenceDataItem>();

	public IReadOnlyList<string> Kinds => ReferenceDataKinds.All;

	public bool CanManage { get; private set; }

	public async Task OnGetAsync(CancellationToken cancellationToken)
	{
		NormalizeKind();
		Input.Kind = Kind;
		ModelState.Clear();
		await LoadAsync(cancellationToken);
	}

	public async Task<IActionResult> OnPostCreateAsync(CancellationToken cancellationToken)
	{
		if (!(await CanManageAsync()))
		{
			return Forbid();
		}
		NormalizeKind();
		Input.Kind = Kind;
		base.ModelState.Remove("Input.Kind");
		NormalizeInput();
		if (await IsDuplicateAsync(null, cancellationToken))
		{
			base.ModelState.AddModelError("Input.Name", "A record with this name or code already exists in that section.");
		}
		int? parentId = Input.ParentId;
		int parentId2 = default(int);
		int num;
		if (parentId.HasValue)
		{
			parentId2 = parentId.GetValueOrDefault();
			num = 1;
		}
		else
		{
			num = 0;
		}
		bool flag = (byte)num != 0;
		if (flag)
		{
			flag = !(await db.ReferenceDataItems.AnyAsync((ReferenceDataItem referenceDataItem) => referenceDataItem.ReferenceDataItemId == parentId2, cancellationToken));
		}
		if (flag)
		{
			base.ModelState.AddModelError("Input.ParentId", "The selected parent record no longer exists.");
		}
		if (!base.ModelState.IsValid)
		{
			await LoadAsync(cancellationToken);
			return Page();
		}
		DateTime utcNow = DateTime.UtcNow;
		ReferenceDataItem item = new ReferenceDataItem
		{
			Kind = Input.Kind,
			Name = Input.Name,
			Code = Input.Code,
			Notes = Input.Notes,
			ParentId = Input.ParentId,
			IsActive = true,
			CreatedUtc = utcNow,
			ModifiedUtc = utcNow
		};
		db.ReferenceDataItems.Add(item);
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync("MasterData.Created", "ReferenceDataItem", item.ReferenceDataItemId.ToString(), base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), null, new { item.Kind, item.Name, item.Code, item.ParentId, item.IsActive }, null, base.HttpContext.TraceIdentifier, cancellationToken);
		base.TempData["Success"] = item.Name + " was added.";
		return RedirectToPage(new
		{
			kind = item.Kind
		});
	}

	public async Task<IActionResult> OnPostToggleAsync(int id, string kind, CancellationToken cancellationToken)
	{
		if (!(await CanManageAsync()))
		{
			return Forbid();
		}
		ReferenceDataItem item = await db.ReferenceDataItems.SingleOrDefaultAsync((ReferenceDataItem record) => record.ReferenceDataItemId == id, cancellationToken);
		if (item == null)
		{
			return NotFound();
		}
		var before = new { item.IsActive };
		item.IsActive = !item.IsActive;
		item.ModifiedUtc = DateTime.UtcNow;
		item.Version++;
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync(item.IsActive ? "MasterData.Activated" : "MasterData.Deactivated", "ReferenceDataItem", item.ReferenceDataItemId.ToString(), base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), before, new { item.IsActive }, null, base.HttpContext.TraceIdentifier, cancellationToken);
		base.TempData["Success"] = item.Name + " was " + (item.IsActive ? "activated" : "deactivated") + ".";
		return RedirectToPage(new
		{
			kind = kind,
			showInactive = true
		});
	}

	private async Task LoadAsync(CancellationToken cancellationToken)
	{
		CanManage = await CanManageAsync();
		IQueryable<ReferenceDataItem> source = from item in db.ReferenceDataItems.AsNoTracking().Include((ReferenceDataItem item) => item.Parent)
			where item.Kind == Kind
			select item;
		if (!ShowInactive)
		{
			source = source.Where((ReferenceDataItem item) => item.IsActive);
		}
		if (!string.IsNullOrWhiteSpace(Query))
		{
			string search = Query.Trim().ToLower();
			source = source.Where((ReferenceDataItem item) =>
				item.Name.ToLower().Contains(search)
				|| (item.Code != null && item.Code.ToLower().Contains(search)));
		}
		Items = await (from item in source
			orderby item.IsActive descending, item.Name
			select item).ToListAsync(cancellationToken);
		string parentKind = ReferenceDataKinds.ParentKind(Kind);
		List<ReferenceDataItem> parentOptions = ((parentKind != null) ? (await (from item in db.ReferenceDataItems.AsNoTracking()
			where item.IsActive && item.Kind == parentKind
			orderby item.Kind, item.Name
			select item).ToListAsync(cancellationToken)) : new List<ReferenceDataItem>());
		ParentOptions = parentOptions;
	}

	private async Task<bool> CanManageAsync()
	{
		return (await authorization.AuthorizeAsync(base.User, "MasterData.Manage")).Succeeded;
	}

	private async Task<bool> IsDuplicateAsync(int? id, CancellationToken cancellationToken)
	{
		return await db.ReferenceDataItems.AnyAsync((ReferenceDataItem item) => (int?)item.ReferenceDataItemId != id && item.Kind == Input.Kind && (item.Name == Input.Name || (Input.Code != null && item.Code == Input.Code)), cancellationToken);
	}

	private void NormalizeKind()
	{
		if (!ReferenceDataKinds.All.Contains<string>(Kind, StringComparer.Ordinal))
		{
			Kind = "Location";
		}
	}

	private void NormalizeInput()
	{
		Input.Kind = Input.Kind.Trim();
		Input.Name = Input.Name.Trim();
		Input.Code = (string.IsNullOrWhiteSpace(Input.Code) ? null : Input.Code.Trim().ToUpperInvariant());
		Input.Notes = (string.IsNullOrWhiteSpace(Input.Notes) ? null : Input.Notes.Trim());
	}
}
