using System;
using System.Collections.Generic;
using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Security.Claims;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Auditing;
using AssetPilot.Domain.Assets;
using AssetPilot.Domain.Shipments;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Web.Pages.Shipments;

[Authorize(Policy = "Shipments.Create")]
public sealed class CreateModel(AssetPilotDbContext db, IAuditService audit) : PageModel
{
	public sealed class InputModel
	{
		[Required]
		[StringLength(80)]
		public string ShipmentNumber { get; set; } = "";

		[Required]
		public string Direction { get; set; } = "Outgoing";

		[StringLength(100)]
		public string? Carrier { get; set; }

		[StringLength(150)]
		public string? TrackingNumber { get; set; }

		[StringLength(200)]
		public string? Sender { get; set; }

		[StringLength(200)]
		public string? Recipient { get; set; }

		[StringLength(200)]
		public string? Origin { get; set; }

		[StringLength(200)]
		public string? Destination { get; set; }

		public DateOnly? ShipDate { get; set; } = DateOnly.FromDateTime(DateTime.Today);

		public DateOnly? ExpectedDate { get; set; }

		[StringLength(1000)]
		public string? Notes { get; set; }
	}

	[BindProperty]
	public InputModel Input { get; set; } = new InputModel();

	[BindProperty]
	public List<int> AssetIds { get; set; } = new List<int>();

	public IReadOnlyList<Asset> Assets { get; private set; } = Array.Empty<Asset>();

	public async Task<IActionResult> OnGetAsync(int? assetId, CancellationToken cancellationToken)
	{
		Input.ShipmentNumber = $"SHP-{DateTime.UtcNow:yyyyMMdd-HHmmss}";
		await LoadAssetsAsync(cancellationToken);
		if (assetId.HasValue)
		{
			if (!Assets.Any(x => x.AssetId == assetId.Value))
			{
				return NotFound();
			}
			AssetIds = [assetId.Value];
		}
		return Page();
	}

	public async Task<IActionResult> OnPostAsync(CancellationToken cancellationToken)
	{
		Normalize();
		if (AssetIds.Count == 0)
		{
			base.ModelState.AddModelError("AssetIds", "Choose at least one asset.");
		}
		if (await db.Shipments.AnyAsync((Shipment x) => x.ShipmentNumber == Input.ShipmentNumber, cancellationToken))
		{
			base.ModelState.AddModelError("Input.ShipmentNumber", "That shipment number already exists.");
		}
		if (!base.ModelState.IsValid)
		{
			await LoadAssetsAsync(cancellationToken);
			return Page();
		}
		List<Asset> assets = await db.Assets.Where((Asset x) => AssetIds.Contains(x.AssetId) && !x.IsArchived).ToListAsync(cancellationToken);
		if (assets.Count != AssetIds.Distinct().Count())
		{
			return BadRequest();
		}
		DateTime utcNow = DateTime.UtcNow;
		string text = ((Input.Direction == "Incoming") ? "Pending Receipt" : "Shipped");
		Shipment shipment = new Shipment
		{
			ShipmentNumber = Input.ShipmentNumber,
			Direction = Input.Direction,
			Status = text,
			Carrier = Input.Carrier,
			TrackingNumber = Input.TrackingNumber,
			Sender = Input.Sender,
			Recipient = Input.Recipient,
			Origin = Input.Origin,
			Destination = Input.Destination,
			ShipDate = Input.ShipDate,
			ExpectedDate = Input.ExpectedDate,
			Notes = Input.Notes,
			CreatedUtc = utcNow,
			ModifiedUtc = utcNow
		};
		foreach (Asset item in assets)
		{
			shipment.Items.Add(new ShipmentItem
			{
				Asset = item,
				ConditionAtDispatch = item.Condition
			});
			string status = item.Status;
			item.Status = text;
			item.ModifiedUtc = utcNow;
			item.Version++;
			item.StatusHistory.Add(new AssetStatusHistory
			{
				Asset = item,
				FromStatus = status,
				ToStatus = text,
				ChangedUtc = utcNow,
				ChangedByUserId = base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"),
				Reason = "Added to " + shipment.ShipmentNumber
			});
		}
		db.Shipments.Add(shipment);
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync("Shipment.Created", "Shipment", shipment.ShipmentId.ToString(), base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), null, new
		{
			ShipmentNumber = shipment.ShipmentNumber,
			Direction = shipment.Direction,
			Status = shipment.Status,
			Assets = assets.Select((Asset x) => x.AssetTag)
		}, shipment.Notes, base.HttpContext.TraceIdentifier, cancellationToken);
		base.TempData["Success"] = shipment.ShipmentNumber + " was created.";
		return RedirectToPage("Details", new
		{
			id = shipment.ShipmentId
		});
	}

	private async Task LoadAssetsAsync(CancellationToken token)
	{
		Assets = await (from x in db.Assets.AsNoTracking()
			where !x.IsArchived
			orderby x.AssetTag
			select x).Take(1000).ToListAsync(token);
	}

	private void Normalize()
	{
		Input.ShipmentNumber = Input.ShipmentNumber.Trim();
		Input.Direction = Input.Direction.Trim();
		Input.Carrier = Clean(Input.Carrier);
		Input.TrackingNumber = Clean(Input.TrackingNumber);
		Input.Sender = Clean(Input.Sender);
		Input.Recipient = Clean(Input.Recipient);
		Input.Origin = Clean(Input.Origin);
		Input.Destination = Clean(Input.Destination);
		Input.Notes = Clean(Input.Notes);
	}

	private static string? Clean(string? value)
	{
		if (!string.IsNullOrWhiteSpace(value))
		{
			return value.Trim();
		}
		return null;
	}
}
