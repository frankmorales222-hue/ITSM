using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Web.Pages;

public sealed class SearchModel(
	AssetPilotDbContext db,
	IAuthorizationService authorization) : PageModel
{
	public sealed record AssetResult(
		int Id,
		string Title,
		string AssetTag,
		string AssetType,
		string Status,
		string? AssignedTo,
		string? Location);

	public sealed record EmployeeResult(
		int Id,
		string Name,
		string EmployeeNumber,
		string Email,
		string? Department,
		string? Location,
		int AssignedAssets);

	public sealed record ShipmentResult(
		int Id,
		string Number,
		string Direction,
		string Status,
		string? Carrier,
		string? TrackingNumber,
		string? Recipient);

	[BindProperty(SupportsGet = true)]
	public string? Q { get; set; }

	public IReadOnlyList<AssetResult> Assets { get; private set; } = Array.Empty<AssetResult>();

	public IReadOnlyList<EmployeeResult> Employees { get; private set; } = Array.Empty<EmployeeResult>();

	public IReadOnlyList<ShipmentResult> Shipments { get; private set; } = Array.Empty<ShipmentResult>();

	public int TotalResults => Assets.Count + Employees.Count + Shipments.Count;

	public async Task OnGetAsync(CancellationToken cancellationToken)
	{
		if (string.IsNullOrWhiteSpace(Q))
		{
			return;
		}
		Q = Q.Trim();
		string query = Q.ToLower();
		if ((await authorization.AuthorizeAsync(User, "Assets.View")).Succeeded)
		{
			Assets = await db.Assets.AsNoTracking()
				.Where(x => !x.IsArchived
					&& (x.AssetTag.ToLower().Contains(query)
						|| (x.Hostname != null && x.Hostname.ToLower().Contains(query))
						|| (x.SerialNumber != null && x.SerialNumber.ToLower().Contains(query))
						|| x.Name.ToLower().Contains(query)
						|| x.AssetType.ToLower().Contains(query)
						|| (x.AssignedTo != null && x.AssignedTo.ToLower().Contains(query))
						|| (x.AssignedToEmail != null && x.AssignedToEmail.ToLower().Contains(query))
						|| (x.Location != null && x.Location.ToLower().Contains(query))
						|| (x.CurrentLocation != null && x.CurrentLocation.ToLower().Contains(query))
						|| (x.Model != null && x.Model.ToLower().Contains(query))
						|| (x.Manufacturer != null && x.Manufacturer.ToLower().Contains(query))))
				.OrderBy(x => x.Hostname ?? x.AssetTag)
				.Take(50)
				.Select(x => new AssetResult(
					x.AssetId,
					x.Hostname ?? x.AssetTag,
					x.AssetTag,
					x.AssetType,
					x.Status,
					x.AssignedTo,
					x.CurrentLocation ?? x.Location))
				.ToListAsync(cancellationToken);
		}
		if ((await authorization.AuthorizeAsync(User, "Employees.View")).Succeeded)
		{
			Employees = await db.Employees.AsNoTracking()
				.Where(x => !x.IsDeleted
					&& (x.DisplayName.ToLower().Contains(query)
						|| x.EmployeeNumber.ToLower().Contains(query)
						|| x.Email.ToLower().Contains(query)
						|| (x.Department != null && x.Department.ToLower().Contains(query))
						|| (x.Location != null && x.Location.ToLower().Contains(query))
						|| (x.Manager != null && x.Manager.ToLower().Contains(query))))
				.OrderBy(x => x.DisplayName)
				.Take(50)
				.Select(x => new EmployeeResult(
					x.EmployeeId,
					x.DisplayName,
					x.EmployeeNumber,
					x.Email,
					x.Department,
					x.Location,
					x.Assignments.Count(a => a.ReturnedUtc == null)))
				.ToListAsync(cancellationToken);
		}
		if ((await authorization.AuthorizeAsync(User, "Shipments.View")).Succeeded)
		{
			Shipments = await db.Shipments.AsNoTracking()
				.Where(x => !x.IsArchived
					&& (x.ShipmentNumber.ToLower().Contains(query)
						|| (x.TrackingNumber != null && x.TrackingNumber.ToLower().Contains(query))
						|| (x.Carrier != null && x.Carrier.ToLower().Contains(query))
						|| (x.Recipient != null && x.Recipient.ToLower().Contains(query))
						|| (x.Sender != null && x.Sender.ToLower().Contains(query))
						|| (x.Destination != null && x.Destination.ToLower().Contains(query))))
				.OrderByDescending(x => x.CreatedUtc)
				.Take(50)
				.Select(x => new ShipmentResult(
					x.ShipmentId,
					x.ShipmentNumber,
					x.Direction,
					x.Status,
					x.Carrier,
					x.TrackingNumber,
					x.Recipient))
				.ToListAsync(cancellationToken);
		}
	}
}
