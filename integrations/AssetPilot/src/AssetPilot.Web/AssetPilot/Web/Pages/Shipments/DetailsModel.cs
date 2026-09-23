using System;
using System.Linq;
using System.Security.Claims;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Auditing;
using AssetPilot.Application.Shipments;
using AssetPilot.Domain.Assets;
using AssetPilot.Domain.Shipments;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Web.Pages.Shipments;

public sealed class DetailsModel(
	AssetPilotDbContext db,
	IAuditService audit,
	IAuthorizationService authorization,
	IShipmentTrackingService trackingService) : PageModel
{
	public Shipment Shipment { get; private set; }

	[BindProperty]
	public string ReceiptCondition { get; set; } = "Good";

	[BindProperty]
	public string? ReceiptNotes { get; set; }

	public async Task<IActionResult> OnGetAsync(int id, CancellationToken cancellationToken)
	{
		Shipment shipment = await db.Shipments.AsNoTracking()
			.Include((Shipment x) => x.Items).ThenInclude((ShipmentItem x) => x.Asset)
			.Include((Shipment x) => x.TrackingEvents)
			.SingleOrDefaultAsync((Shipment x) => x.ShipmentId == id && !x.IsArchived, cancellationToken);
		if (shipment == null)
		{
			return NotFound();
		}
		Shipment = shipment;
		return Page();
	}

	public async Task<IActionResult> OnPostUpdateShippingAsync(int id, CancellationToken cancellationToken, string? returnUrl = null)
	{
		if (!(await authorization.AuthorizeAsync(base.User, "Shipments.Edit")).Succeeded)
		{
			return Forbid();
		}
		Shipment shipment = await db.Shipments
			.Include(x => x.TrackingEvents)
			.SingleOrDefaultAsync(x => x.ShipmentId == id && !x.IsArchived, cancellationToken);
		if (shipment is null)
		{
			return NotFound();
		}
		if (string.IsNullOrWhiteSpace(shipment.Carrier) || string.IsNullOrWhiteSpace(shipment.TrackingNumber))
		{
			base.TempData["Error"] = "Add a carrier and tracking number before updating shipping.";
			return RedirectAfterUpdate(id, returnUrl);
		}

		ShipmentTrackingResult result = await trackingService.GetUpdateAsync(
			shipment.Carrier,
			shipment.TrackingNumber,
			cancellationToken);
		DateTime now = DateTime.UtcNow;
		shipment.TrackingLastCheckedUtc = now;
		shipment.TrackingLastMessage = result.Message;
		shipment.TrackingUrl = result.TrackingUrl;
		if (result.Success)
		{
			shipment.Status = result.Status;
			shipment.ExpectedDate = result.ExpectedDate ?? shipment.ExpectedDate;
			foreach (ShipmentTrackingEventResult item in result.Events)
			{
				bool exists = shipment.TrackingEvents.Any(x =>
					x.EventUtc == item.EventUtc && x.Status == item.Status);
				if (!exists)
				{
					shipment.TrackingEvents.Add(new ShipmentTrackingEvent
					{
						EventUtc = item.EventUtc,
						Status = item.Status,
						Description = item.Description,
						Location = item.Location,
						Source = shipment.Carrier
					});
				}
			}
		}
		shipment.ModifiedUtc = now;
		shipment.Version++;
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync(
			"Shipment.TrackingUpdated",
			"Shipment",
			id.ToString(),
			base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"),
			null,
			new { result.Success, result.Status, result.Message, Events = result.Events.Count },
			null,
			base.HttpContext.TraceIdentifier,
			cancellationToken);
		base.TempData[result.Success ? "Success" : "Error"] = result.Message;
		return RedirectAfterUpdate(id, returnUrl);
	}

	private IActionResult RedirectAfterUpdate(int id, string? returnUrl)
	{
		return !string.IsNullOrWhiteSpace(returnUrl) && Url.IsLocalUrl(returnUrl)
			? LocalRedirect(returnUrl)
			: RedirectToPage(new { id });
	}

	public async Task<IActionResult> OnPostClearTrackingAsync(int id, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(User, "Shipments.Edit")).Succeeded)
		{
			return Forbid();
		}
		Shipment? shipment = await db.Shipments
			.Include(x => x.TrackingEvents)
			.SingleOrDefaultAsync(x => x.ShipmentId == id && !x.IsArchived, cancellationToken);
		if (shipment is null)
		{
			return NotFound();
		}
		var before = new
		{
			shipment.Carrier,
			shipment.TrackingNumber,
			shipment.TrackingLastCheckedUtc,
			TrackingEvents = shipment.TrackingEvents.Count
		};
		db.ShipmentTrackingEvents.RemoveRange(shipment.TrackingEvents);
		shipment.TrackingNumber = null;
		shipment.TrackingLastCheckedUtc = null;
		shipment.TrackingLastMessage = null;
		shipment.TrackingUrl = null;
		shipment.ExpectedDate = null;
		shipment.ModifiedUtc = DateTime.UtcNow;
		shipment.Version++;
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync(
			"Shipment.TrackingCleared",
			"Shipment",
			id.ToString(),
			User.FindFirstValue(ClaimTypes.NameIdentifier),
			before,
			new { shipment.Carrier, shipment.TrackingNumber },
			"Incorrect tracking information removed",
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = "Tracking information and carrier events were removed.";
		return RedirectToPage(new { id });
	}

	public async Task<IActionResult> OnPostReceiveAsync(int id, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(base.User, "Shipments.ConfirmReceipt")).Succeeded)
		{
			return Forbid();
		}
		Shipment shipment = await db.Shipments.Include((Shipment x) => x.Items).ThenInclude((ShipmentItem x) => x.Asset).SingleOrDefaultAsync((Shipment x) => x.ShipmentId == id && !x.IsArchived, cancellationToken);
		if (shipment == null)
		{
			return NotFound();
		}
		if (shipment.ReceivedUtc.HasValue)
		{
			return RedirectToPage(new { id });
		}
		DateTime utcNow = DateTime.UtcNow;
		shipment.Status = ((shipment.Direction == "Outgoing") ? "Delivered" : "Received");
		shipment.ReceivedUtc = utcNow;
		shipment.ReceivedByUserId = base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier");
		shipment.ModifiedUtc = utcNow;
		shipment.Version++;
		foreach (ShipmentItem item in shipment.Items)
		{
			item.ConditionAtReceipt = (string.IsNullOrWhiteSpace(ReceiptCondition) ? item.Asset.Condition : ReceiptCondition.Trim());
			item.Notes = (string.IsNullOrWhiteSpace(ReceiptNotes) ? null : ReceiptNotes.Trim());
			Asset asset = item.Asset;
			string status = asset.Status;
			asset.Condition = item.ConditionAtReceipt;
			asset.Status = ((shipment.Direction == "Outgoing") ? (string.IsNullOrWhiteSpace(asset.AssignedTo) ? "In Stock" : "Active") : "In Stock");
			asset.Location = shipment.Destination ?? asset.Location;
			asset.ModifiedUtc = utcNow;
			asset.Version++;
			asset.StatusHistory.Add(new AssetStatusHistory
			{
				Asset = asset,
				FromStatus = status,
				ToStatus = asset.Status,
				ChangedUtc = utcNow,
				ChangedByUserId = shipment.ReceivedByUserId,
				Reason = shipment.ShipmentNumber + " receipt confirmed"
			});
		}
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync("Shipment.Received", "Shipment", id.ToString(), shipment.ReceivedByUserId, null, new { shipment.ShipmentNumber, shipment.Status, shipment.ReceivedUtc, ReceiptCondition }, ReceiptNotes, base.HttpContext.TraceIdentifier, cancellationToken);
		base.TempData["Success"] = shipment.ShipmentNumber + " receipt was confirmed.";
		return RedirectToPage(new { id });
	}

	public async Task<IActionResult> OnPostCancelAsync(int id, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(base.User, "Shipments.Edit")).Succeeded)
		{
			return Forbid();
		}
		Shipment shipment = await db.Shipments.Include((Shipment x) => x.Items).ThenInclude((ShipmentItem x) => x.Asset).SingleOrDefaultAsync((Shipment x) => x.ShipmentId == id && !x.IsArchived, cancellationToken);
		if (shipment == null)
		{
			return NotFound();
		}
		if (shipment.ReceivedUtc.HasValue)
		{
			return BadRequest();
		}
		DateTime utcNow = DateTime.UtcNow;
		shipment.Status = "Cancelled";
		shipment.ModifiedUtc = utcNow;
		shipment.Version++;
		foreach (Asset item in shipment.Items.Select((ShipmentItem x) => x.Asset))
		{
			string status = item.Status;
			item.Status = (string.IsNullOrWhiteSpace(item.AssignedTo) ? "In Stock" : "Active");
			item.ModifiedUtc = utcNow;
			item.Version++;
			item.StatusHistory.Add(new AssetStatusHistory
			{
				Asset = item,
				FromStatus = status,
				ToStatus = item.Status,
				ChangedUtc = utcNow,
				ChangedByUserId = base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"),
				Reason = shipment.ShipmentNumber + " cancelled"
			});
		}
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync("Shipment.Cancelled", "Shipment", id.ToString(), base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), null, new { shipment.ShipmentNumber, shipment.Status }, null, base.HttpContext.TraceIdentifier, cancellationToken);
		return RedirectToPage(new { id });
	}

	public async Task<IActionResult> OnPostDeleteAsync(int id, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(User, "Shipments.Edit")).Succeeded)
		{
			return Forbid();
		}
		Shipment? shipment = await db.Shipments
			.Include(x => x.Items)
			.ThenInclude(x => x.Asset)
			.SingleOrDefaultAsync(x => x.ShipmentId == id && !x.IsArchived, cancellationToken);
		if (shipment is null)
		{
			return NotFound();
		}

		DateTime now = DateTime.UtcNow;
		if (!shipment.ReceivedUtc.HasValue && shipment.Status != "Cancelled")
		{
			foreach (Asset asset in shipment.Items.Select(x => x.Asset))
			{
				string previousStatus = asset.Status;
				asset.Status = string.IsNullOrWhiteSpace(asset.AssignedTo) ? "In Stock" : "Active";
				asset.ModifiedUtc = now;
				asset.Version++;
				asset.StatusHistory.Add(new AssetStatusHistory
				{
					Asset = asset,
					FromStatus = previousStatus,
					ToStatus = asset.Status,
					ChangedUtc = now,
					ChangedByUserId = User.FindFirstValue(ClaimTypes.NameIdentifier),
					Reason = shipment.ShipmentNumber + " deleted"
				});
			}
		}

		shipment.IsArchived = true;
		shipment.ModifiedUtc = now;
		shipment.Version++;
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync(
			"Shipment.Deleted",
			"Shipment",
			id.ToString(),
			User.FindFirstValue(ClaimTypes.NameIdentifier),
			new { shipment.ShipmentNumber, shipment.Status },
			new { shipment.IsArchived },
			"Shipment removed from active records",
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = shipment.ShipmentNumber + " was deleted.";
		return RedirectToPage("Index");
	}
}
