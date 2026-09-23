using System;
using System.Collections.Generic;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Domain.Shipments;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;

namespace AssetPilot.Web.Pages.Shipments;

public sealed class IndexModel(AssetPilotDbContext db, IConfiguration configuration) : PageModel
{
	public sealed record Row(
		int Id,
		string Number,
		string Direction,
		string Status,
		string? Carrier,
		string? Tracking,
		string? Recipient,
		DateOnly? ExpectedDate,
		int Items,
		bool CanAutoUpdate,
		string? PublicTrackingUrl,
		string? CarrierDisplayName);

	[BindProperty(SupportsGet = true)]
	public string? Direction { get; set; }

	[BindProperty(SupportsGet = true)]
	public string? Query { get; set; }

	public IReadOnlyList<Row> Shipments { get; private set; } = Array.Empty<Row>();

	public async Task OnGetAsync(CancellationToken cancellationToken)
	{
		IQueryable<Shipment> source = from x in db.Shipments.AsNoTracking()
			where !x.IsArchived
			select x;
		if (!string.IsNullOrWhiteSpace(Direction))
		{
			source = source.Where((Shipment x) => x.Direction == Direction);
		}
		if (!string.IsNullOrWhiteSpace(Query))
		{
			string value = Query.Trim();
			source = source.Where((Shipment x) => x.ShipmentNumber.Contains(value) || (x.TrackingNumber != null && x.TrackingNumber.Contains(value)) || (x.Recipient != null && x.Recipient.Contains(value)));
		}
		var shipments = await (from x in source
			orderby x.CreatedUtc descending
			select new
			{
				x.ShipmentId,
				x.ShipmentNumber,
				x.Direction,
				x.Status,
				x.Carrier,
				x.TrackingNumber,
				x.Recipient,
				x.ExpectedDate,
				Items = x.Items.Count
			}).ToListAsync(cancellationToken);
		HashSet<string> storedCredentialKeys = await db.SystemSettings.AsNoTracking()
			.Where(x => x.IsSensitive && x.Value != "" && x.SettingKey.StartsWith("Tracking."))
			.Select(x => x.SettingKey)
			.ToHashSetAsync(StringComparer.OrdinalIgnoreCase, cancellationToken);
		Shipments = shipments.Select(x =>
		{
			string? carrierKey = CarrierKey(x.Carrier);
			string? trackingUrl = PublicTrackingUrl(carrierKey, x.TrackingNumber);
			bool configuredInEnvironment = carrierKey is not null
				&& !string.IsNullOrWhiteSpace(configuration[$"Tracking:{carrierKey}:ClientId"])
				&& !string.IsNullOrWhiteSpace(configuration[$"Tracking:{carrierKey}:ClientSecret"]);
			bool configuredInSettings = carrierKey is not null
				&& storedCredentialKeys.Contains($"Tracking.{carrierKey}.ClientId")
				&& storedCredentialKeys.Contains($"Tracking.{carrierKey}.ClientSecret");
			bool canAutoUpdate = configuredInEnvironment || configuredInSettings;
			return new Row(
				x.ShipmentId,
				x.ShipmentNumber,
				x.Direction,
				x.Status,
				x.Carrier,
				x.TrackingNumber,
				x.Recipient,
				x.ExpectedDate,
				x.Items,
				canAutoUpdate,
				trackingUrl,
				carrierKey);
		}).ToList();
	}

	private static string? CarrierKey(string? carrier) => carrier?.Trim().ToUpperInvariant() switch
	{
		"UPS" => "UPS",
		"FEDEX" or "FED EX" => "FedEx",
		"USPS" => "USPS",
		_ => null
	};

	private static string? PublicTrackingUrl(string? carrier, string? trackingNumber)
	{
		if (carrier is null || string.IsNullOrWhiteSpace(trackingNumber))
		{
			return null;
		}
		string number = Uri.EscapeDataString(trackingNumber.Trim());
		return carrier switch
		{
			"UPS" => "https://www.ups.com/track?tracknum=" + number,
			"FedEx" => "https://www.fedex.com/fedextrack/?trknbr=" + number,
			"USPS" => "https://tools.usps.com/go/TrackConfirmAction?tLabels=" + number,
			_ => null
		};
	}
}
