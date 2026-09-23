using System;
using System.Collections.Generic;
using System.Linq;
using System.Net.Http;
using System.Net.Http.Headers;
using System.Net.Http.Json;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Shipments;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;

namespace AssetPilot.Infrastructure.Shipments;

public sealed class CarrierShipmentTrackingService(
	IHttpClientFactory httpClientFactory,
	IConfiguration configuration,
	AssetPilotDbContext db,
	IDataProtectionProvider dataProtectionProvider) : IShipmentTrackingService
{
	private readonly IDataProtector credentialProtector =
		dataProtectionProvider.CreateProtector("AssetPilot.CarrierTrackingCredentials.v1");

	public async Task<ShipmentTrackingResult> GetUpdateAsync(
		string carrier,
		string trackingNumber,
		CancellationToken cancellationToken = default)
	{
		string normalized = carrier.Trim().ToUpperInvariant();
		string number = trackingNumber.Trim();
		string trackingUrl = PublicTrackingUrl(normalized, number);
		try
		{
			return normalized switch
			{
				"UPS" => await TrackUpsAsync(number, trackingUrl, cancellationToken),
				"FEDEX" or "FED EX" => await TrackFedExAsync(number, trackingUrl, cancellationToken),
				"USPS" => await TrackUspsAsync(number, trackingUrl, cancellationToken),
				_ => new(false, "Unknown", $"Automatic updates are not configured for {carrier}.",
					null, trackingUrl, Array.Empty<ShipmentTrackingEventResult>())
			};
		}
		catch (Exception exception) when (exception is HttpRequestException or JsonException or TaskCanceledException)
		{
			return new(false, "Unavailable", $"The carrier update could not be retrieved: {exception.Message}",
				null, trackingUrl, Array.Empty<ShipmentTrackingEventResult>());
		}
	}

	private async Task<ShipmentTrackingResult> TrackUpsAsync(
		string number,
		string trackingUrl,
		CancellationToken cancellationToken)
	{
		(string clientId, string clientSecret) = await CredentialsAsync("UPS", cancellationToken);
		if (clientId.Length == 0 || clientSecret.Length == 0)
		{
			return MissingCredentials("UPS", trackingUrl);
		}
		HttpClient client = httpClientFactory.CreateClient();
		string token = await FormTokenAsync(
			client,
			configuration["Tracking:UPS:TokenUrl"] ?? "https://onlinetools.ups.com/security/v1/oauth/token",
			new Dictionary<string, string> { ["grant_type"] = "client_credentials" },
			clientId,
			clientSecret,
			cancellationToken);
		using var request = new HttpRequestMessage(
			HttpMethod.Get,
			(configuration["Tracking:UPS:TrackUrl"] ?? "https://onlinetools.ups.com/api/track/v1/details/")
				+ Uri.EscapeDataString(number)
				+ "?locale=en_US&returnSignature=false");
		request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
		request.Headers.TryAddWithoutValidation("transId", Guid.NewGuid().ToString("N"));
		request.Headers.TryAddWithoutValidation("transactionSrc", "AssetPilot");
		using HttpResponseMessage response = await client.SendAsync(request, cancellationToken);
		await EnsureSuccessAsync(response, cancellationToken);
		using JsonDocument json = await JsonDocument.ParseAsync(
			await response.Content.ReadAsStreamAsync(cancellationToken),
			cancellationToken: cancellationToken);
		JsonElement package = json.RootElement
			.GetProperty("trackResponse").GetProperty("shipment")[0].GetProperty("package")[0];
		string status = Text(package, "currentStatus", "description") ?? "Unknown";
		DateOnly? expected = ParseCompactDate(
			package.TryGetProperty("deliveryDate", out JsonElement dates) && dates.GetArrayLength() > 0
				? Text(dates[0], "date")
				: null);
		var events = new List<ShipmentTrackingEventResult>();
		if (package.TryGetProperty("activity", out JsonElement activities))
		{
			foreach (JsonElement item in activities.EnumerateArray())
			{
				DateTime when = ParseUpsDateTime(Text(item, "date"), Text(item, "time"));
				string eventStatus = Text(item, "status", "description") ?? status;
				string? location = Text(item, "location", "address", "city");
				events.Add(new(when, eventStatus, eventStatus, location));
			}
		}
		return new(true, status, status, expected, trackingUrl, events);
	}

	private async Task<ShipmentTrackingResult> TrackFedExAsync(
		string number,
		string trackingUrl,
		CancellationToken cancellationToken)
	{
		(string clientId, string clientSecret) = await CredentialsAsync("FedEx", cancellationToken);
		if (clientId.Length == 0 || clientSecret.Length == 0)
		{
			return MissingCredentials("FedEx", trackingUrl);
		}
		HttpClient client = httpClientFactory.CreateClient();
		string token = await FormTokenAsync(
			client,
			configuration["Tracking:FedEx:TokenUrl"] ?? "https://apis.fedex.com/oauth/token",
			new Dictionary<string, string>
			{
				["grant_type"] = "client_credentials",
				["client_id"] = clientId,
				["client_secret"] = clientSecret
			},
			null,
			null,
			cancellationToken);
		using var request = new HttpRequestMessage(
			HttpMethod.Post,
			configuration["Tracking:FedEx:TrackUrl"] ?? "https://apis.fedex.com/track/v1/trackingnumbers");
		request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
		request.Content = JsonContent.Create(new
		{
			includeDetailedScans = true,
			trackingInfo = new[] { new { trackingNumberInfo = new { trackingNumber = number } } }
		});
		using HttpResponseMessage response = await client.SendAsync(request, cancellationToken);
		await EnsureSuccessAsync(response, cancellationToken);
		using JsonDocument json = await JsonDocument.ParseAsync(
			await response.Content.ReadAsStreamAsync(cancellationToken),
			cancellationToken: cancellationToken);
		JsonElement result = json.RootElement.GetProperty("output")
			.GetProperty("completeTrackResults")[0].GetProperty("trackResults")[0];
		string status = Text(result, "latestStatusDetail", "description")
			?? Text(result, "latestStatusDetail", "statusByLocale")
			?? "Unknown";
		DateOnly? expected = null;
		if (result.TryGetProperty("dateAndTimes", out JsonElement dateTimes))
		{
			foreach (JsonElement item in dateTimes.EnumerateArray())
			{
				if (string.Equals(Text(item, "type"), "ESTIMATED_DELIVERY", StringComparison.OrdinalIgnoreCase)
					&& DateTimeOffset.TryParse(Text(item, "dateTime"), out DateTimeOffset estimate))
				{
					expected = DateOnly.FromDateTime(estimate.LocalDateTime);
					break;
				}
			}
		}
		var events = new List<ShipmentTrackingEventResult>();
		if (result.TryGetProperty("scanEvents", out JsonElement scanEvents))
		{
			foreach (JsonElement item in scanEvents.EnumerateArray())
			{
				DateTime when = DateTimeOffset.TryParse(Text(item, "date"), out DateTimeOffset parsed)
					? parsed.UtcDateTime
					: DateTime.UtcNow;
				string eventStatus = Text(item, "eventDescription") ?? Text(item, "derivedStatus") ?? status;
				string? location = Text(item, "scanLocation", "city");
				events.Add(new(when, eventStatus, eventStatus, location));
			}
		}
		return new(true, status, status, expected, trackingUrl, events);
	}

	private async Task<ShipmentTrackingResult> TrackUspsAsync(
		string number,
		string trackingUrl,
		CancellationToken cancellationToken)
	{
		(string clientId, string clientSecret) = await CredentialsAsync("USPS", cancellationToken);
		if (clientId.Length == 0 || clientSecret.Length == 0)
		{
			return MissingCredentials("USPS", trackingUrl);
		}
		HttpClient client = httpClientFactory.CreateClient();
		using HttpResponseMessage tokenResponse = await client.PostAsJsonAsync(
			configuration["Tracking:USPS:TokenUrl"] ?? "https://apis.usps.com/oauth2/v3/token",
			new { grant_type = "client_credentials", client_id = clientId, client_secret = clientSecret },
			cancellationToken);
		await EnsureSuccessAsync(tokenResponse, cancellationToken);
		using JsonDocument tokenJson = await JsonDocument.ParseAsync(
			await tokenResponse.Content.ReadAsStreamAsync(cancellationToken),
			cancellationToken: cancellationToken);
		string token = tokenJson.RootElement.GetProperty("access_token").GetString() ?? "";
		using var request = new HttpRequestMessage(
			HttpMethod.Get,
			(configuration["Tracking:USPS:TrackUrl"] ?? "https://apis.usps.com/tracking/v3/tracking/")
				+ Uri.EscapeDataString(number)
				+ "?expand=DETAIL");
		request.Headers.Authorization = new AuthenticationHeaderValue("Bearer", token);
		using HttpResponseMessage response = await client.SendAsync(request, cancellationToken);
		await EnsureSuccessAsync(response, cancellationToken);
		using JsonDocument json = await JsonDocument.ParseAsync(
			await response.Content.ReadAsStreamAsync(cancellationToken),
			cancellationToken: cancellationToken);
		JsonElement root = json.RootElement;
		string status = Text(root, "status")
			?? (root.TryGetProperty("eventSummaries", out JsonElement summaries) && summaries.GetArrayLength() > 0
				? summaries[0].GetString()
				: null)
			?? "Unknown";
		DateOnly? expected = DateOnly.TryParse(Text(root, "expectedDeliveryDate"), out DateOnly date)
			? date
			: null;
		var events = new List<ShipmentTrackingEventResult>();
		if (root.TryGetProperty("trackingEvents", out JsonElement trackingEvents))
		{
			foreach (JsonElement item in trackingEvents.EnumerateArray())
			{
				DateTime when = DateTimeOffset.TryParse(Text(item, "eventTimestamp"), out DateTimeOffset parsed)
					? parsed.UtcDateTime
					: DateTime.UtcNow;
				string eventStatus = Text(item, "eventType") ?? Text(item, "eventSummary") ?? status;
				events.Add(new(when, eventStatus, Text(item, "eventSummary"), Text(item, "eventCity")));
			}
		}
		return new(true, status, status, expected, trackingUrl, events);
	}

	private async Task<(string ClientId, string ClientSecret)> CredentialsAsync(
		string carrier,
		CancellationToken cancellationToken)
	{
		string configuredClientId = configuration[$"Tracking:{carrier}:ClientId"] ?? "";
		string configuredClientSecret = configuration[$"Tracking:{carrier}:ClientSecret"] ?? "";
		if (configuredClientId.Length > 0 && configuredClientSecret.Length > 0)
		{
			return (configuredClientId, configuredClientSecret);
		}

		string[] keys = [$"Tracking.{carrier}.ClientId", $"Tracking.{carrier}.ClientSecret"];
		Dictionary<string, string> stored = await db.SystemSettings.AsNoTracking()
			.Where(x => keys.Contains(x.SettingKey) && x.IsSensitive)
			.ToDictionaryAsync(x => x.SettingKey, x => x.Value, cancellationToken);
		try
		{
			return (
				stored.TryGetValue(keys[0], out string? clientId) ? credentialProtector.Unprotect(clientId) : "",
				stored.TryGetValue(keys[1], out string? secret) ? credentialProtector.Unprotect(secret) : "");
		}
		catch (System.Security.Cryptography.CryptographicException)
		{
			return ("", "");
		}
	}

	private static ShipmentTrackingResult MissingCredentials(string carrier, string trackingUrl) =>
		new(false, "Configuration required",
			$"{carrier} API credentials are not configured. The carrier tracking page is available below.",
			null, trackingUrl, Array.Empty<ShipmentTrackingEventResult>());

	private static string PublicTrackingUrl(string carrier, string number) => carrier switch
	{
		"UPS" => "https://www.ups.com/track?tracknum=" + Uri.EscapeDataString(number),
		"FEDEX" or "FED EX" => "https://www.fedex.com/fedextrack/?trknbr=" + Uri.EscapeDataString(number),
		"USPS" => "https://tools.usps.com/go/TrackConfirmAction?tLabels=" + Uri.EscapeDataString(number),
		_ => ""
	};

	private static async Task<string> FormTokenAsync(
		HttpClient client,
		string url,
		IReadOnlyDictionary<string, string> form,
		string? basicUser,
		string? basicPassword,
		CancellationToken cancellationToken)
	{
		using var request = new HttpRequestMessage(HttpMethod.Post, url)
		{
			Content = new FormUrlEncodedContent(form)
		};
		if (basicUser is not null)
		{
			string basic = Convert.ToBase64String(Encoding.ASCII.GetBytes($"{basicUser}:{basicPassword}"));
			request.Headers.Authorization = new AuthenticationHeaderValue("Basic", basic);
		}
		using HttpResponseMessage response = await client.SendAsync(request, cancellationToken);
		await EnsureSuccessAsync(response, cancellationToken);
		using JsonDocument json = await JsonDocument.ParseAsync(
			await response.Content.ReadAsStreamAsync(cancellationToken),
			cancellationToken: cancellationToken);
		return json.RootElement.GetProperty("access_token").GetString() ?? "";
	}

	private static async Task EnsureSuccessAsync(HttpResponseMessage response, CancellationToken cancellationToken)
	{
		if (response.IsSuccessStatusCode)
		{
			return;
		}
		string body = await response.Content.ReadAsStringAsync(cancellationToken);
		throw new HttpRequestException(
			$"{(int)response.StatusCode} {response.ReasonPhrase}: {body[..Math.Min(body.Length, 400)]}");
	}

	private static string? Text(JsonElement element, params string[] path)
	{
		foreach (string name in path)
		{
			if (element.ValueKind != JsonValueKind.Object || !element.TryGetProperty(name, out element))
			{
				return null;
			}
		}
		return element.ValueKind == JsonValueKind.String ? element.GetString() : element.ToString();
	}

	private static DateOnly? ParseCompactDate(string? value) =>
		DateOnly.TryParseExact(value, "yyyyMMdd", out DateOnly result) ? result : null;

	private static DateTime ParseUpsDateTime(string? date, string? time)
	{
		string value = (date ?? "") + (time ?? "");
		return DateTime.TryParseExact(value, "yyyyMMddHHmmss", null,
			System.Globalization.DateTimeStyles.AssumeLocal, out DateTime parsed)
			? parsed.ToUniversalTime()
			: DateTime.UtcNow;
	}
}
