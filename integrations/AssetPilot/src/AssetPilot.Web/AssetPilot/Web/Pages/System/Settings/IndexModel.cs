using System;
using System.Collections.Generic;
using System.Data.Common;
using System.IO;
using System.Linq;
using System.Security.Claims;
using System.Text.RegularExpressions;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Auditing;
using AssetPilot.Application.Operations;
using AssetPilot.Domain.Operations;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.DataProtection;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;
using Microsoft.Extensions.Configuration;

namespace AssetPilot.Web.Pages.System.Settings;

[Authorize(Policy = "Operations.ViewJobs")]
public sealed class IndexModel(AssetPilotDbContext db, IBackupService backup, IAuditService audit, IAuthorizationService authorization, PhaseOneDataSeeder phaseOneSeeder, PhaseTwoDataSeeder phaseTwoSeeder, IDataProtectionProvider dataProtectionProvider, IConfiguration configuration) : PageModel
{
	public const string ResetPhrase = "DELETE ALL ASSETPILOT DATA";
	private static readonly string[] SupportedCarriers = ["UPS", "FedEx", "USPS"];
	private readonly IDataProtector credentialProtector =
		dataProtectionProvider.CreateProtector("AssetPilot.CarrierTrackingCredentials.v1");

	public sealed class BrandingInput
	{
		public string ApplicationName { get; set; } = "AssetPilot";
		public string OrganizationName { get; set; } = "";
		public string AccentColor { get; set; } = "#0969da";
		public bool RemoveLogo { get; set; }
	}

	public sealed class CarrierCredentialInput
	{
		public string? Carrier { get; set; }
		public string? ClientId { get; set; }
		public string? ClientSecret { get; set; }
	}

	public IReadOnlyList<SystemSetting> Settings { get; private set; } = Array.Empty<SystemSetting>();

	public IReadOnlyList<OperationalJob> Jobs { get; private set; } = Array.Empty<OperationalJob>();

	public IReadOnlyDictionary<string, bool> CarrierConfiguration { get; private set; } =
		new Dictionary<string, bool>(StringComparer.OrdinalIgnoreCase);

	[BindProperty]
	public int SettingId { get; set; }

	[BindProperty]
	public string? SettingValue { get; set; }

	[BindProperty]
	public BrandingInput Branding { get; set; } = new();

	[BindProperty]
	public IFormFile? LogoFile { get; set; }

	[BindProperty]
	public CarrierCredentialInput CarrierCredential { get; set; } = new();

	[BindProperty]
	public bool ResetAcknowledged { get; set; }

	[BindProperty]
	public string? ResetConfirmation { get; set; }

	public string? CurrentLogoDataUrl { get; private set; }

	public async Task OnGetAsync(CancellationToken cancellationToken)
	{
		await LoadAsync(cancellationToken);
	}

	public async Task<IActionResult> OnPostSettingAsync(CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(base.User, "Settings.Manage")).Succeeded)
		{
			return Forbid();
		}
		SystemSetting setting = await db.SystemSettings.SingleOrDefaultAsync((SystemSetting x) => x.SystemSettingId == SettingId, cancellationToken);
		if (setting == null)
		{
			return NotFound();
		}
		if (setting.IsSensitive)
		{
			return Forbid();
		}
		var before = new { setting.Value };
		if (string.IsNullOrWhiteSpace(SettingValue))
		{
			ModelState.AddModelError(nameof(SettingValue), "Setting value cannot be blank.");
			await LoadAsync(cancellationToken);
			return Page();
		}
		setting.Value = SettingValue.Trim();
		setting.ModifiedUtc = DateTime.UtcNow;
		setting.Version++;
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync("Setting.Changed", "SystemSetting", setting.SystemSettingId.ToString(), base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), before, new { setting.Value }, null, base.HttpContext.TraceIdentifier, cancellationToken);
		base.TempData["Success"] = setting.SettingKey + " was updated.";
		return RedirectToPage();
	}

	public async Task<IActionResult> OnPostBrandingAsync(CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(User, "Settings.Manage")).Succeeded)
		{
			return Forbid();
		}
		Branding.ApplicationName = Branding.ApplicationName.Trim();
		Branding.OrganizationName = Branding.OrganizationName.Trim();
		Branding.AccentColor = Branding.AccentColor.Trim();
		if (Branding.ApplicationName.Length is < 2 or > 80)
		{
			ModelState.AddModelError("Branding.ApplicationName", "Application name must be between 2 and 80 characters.");
		}
		if (!Regex.IsMatch(Branding.AccentColor, "^#[0-9a-fA-F]{6}$"))
		{
			ModelState.AddModelError("Branding.AccentColor", "Use a six-digit color such as #0969da.");
		}
		string? logoDataUrl = null;
		if (LogoFile is not null && LogoFile.Length > 0)
		{
			string[] allowedTypes = ["image/png", "image/jpeg", "image/webp", "image/svg+xml"];
			if (LogoFile.Length > 1_500_000)
			{
				ModelState.AddModelError(nameof(LogoFile), "Logo must be 1.5 MB or smaller.");
			}
			else if (!allowedTypes.Contains(LogoFile.ContentType, StringComparer.OrdinalIgnoreCase))
			{
				ModelState.AddModelError(nameof(LogoFile), "Upload a PNG, JPG, WebP, or SVG logo.");
			}
			else
			{
				await using MemoryStream stream = new();
				await LogoFile.CopyToAsync(stream, cancellationToken);
				logoDataUrl = $"data:{LogoFile.ContentType};base64,{Convert.ToBase64String(stream.ToArray())}";
			}
		}
		if (!ModelState.IsValid)
		{
			await LoadAsync(cancellationToken, populateBranding: false);
			return Page();
		}
		var before = await db.SystemSettings.AsNoTracking()
			.Where(x => x.SettingKey == "Application.Name"
				|| x.SettingKey == "Organization.Name"
				|| x.SettingKey == "Branding.AccentColor"
				|| x.SettingKey == "Branding.LogoDataUrl")
			.ToDictionaryAsync(x => x.SettingKey, x => x.Value, cancellationToken);
		await SetValueAsync("Application.Name", Branding.ApplicationName, "Application name shown throughout the interface.", cancellationToken);
		await SetValueAsync("Organization.Name", Branding.OrganizationName, "Organization name shown in reports.", cancellationToken);
		await SetValueAsync("Branding.AccentColor", Branding.AccentColor, "Primary interface color.", cancellationToken);
		if (Branding.RemoveLogo)
		{
			await SetValueAsync("Branding.LogoDataUrl", "", "Uploaded application logo.", cancellationToken);
		}
		else if (logoDataUrl is not null)
		{
			await SetValueAsync("Branding.LogoDataUrl", logoDataUrl, "Uploaded application logo.", cancellationToken);
		}
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync(
			"Branding.Changed",
			"SystemSetting",
			"branding",
			User.FindFirstValue(ClaimTypes.NameIdentifier),
			before,
			new
			{
				Branding.ApplicationName,
				Branding.OrganizationName,
				Branding.AccentColor,
				LogoChanged = Branding.RemoveLogo || logoDataUrl is not null
			},
			null,
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = "Application branding was updated.";
		return RedirectToPage();
	}

	public async Task<IActionResult> OnPostCarrierCredentialAsync(CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(User, "Settings.Manage")).Succeeded)
		{
			return Forbid();
		}
		string carrier = NormalizeCarrier(CarrierCredential.Carrier);
		if (carrier.Length == 0)
		{
			return BadRequest();
		}
		string clientId = CarrierCredential.ClientId?.Trim() ?? "";
		string clientSecret = CarrierCredential.ClientSecret?.Trim() ?? "";
		bool alreadyConfigured = await HasStoredCredentialAsync(carrier, cancellationToken);
		if (clientId.Length == 0)
		{
			ModelState.AddModelError("CarrierCredential.ClientId", "Client ID is required.");
		}
		if (!alreadyConfigured && clientSecret.Length == 0)
		{
			ModelState.AddModelError("CarrierCredential.ClientSecret", "Client secret is required the first time a carrier is configured.");
		}
		if (!ModelState.IsValid)
		{
			await LoadAsync(cancellationToken);
			return Page();
		}

		await SetSensitiveValueAsync(
			$"Tracking.{carrier}.ClientId",
			credentialProtector.Protect(clientId),
			$"Encrypted {carrier} tracking API client ID.",
			cancellationToken);
		if (clientSecret.Length > 0)
		{
			await SetSensitiveValueAsync(
				$"Tracking.{carrier}.ClientSecret",
				credentialProtector.Protect(clientSecret),
				$"Encrypted {carrier} tracking API client secret.",
				cancellationToken);
		}
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync(
			"Tracking.CredentialsChanged",
			"CarrierIntegration",
			carrier,
			User.FindFirstValue(ClaimTypes.NameIdentifier),
			null,
			new { Carrier = carrier, Configured = true, SecretChanged = clientSecret.Length > 0 },
			"Carrier tracking credentials updated in Application Settings",
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = $"{carrier} automatic tracking is configured.";
		return RedirectToPage();
	}

	public async Task<IActionResult> OnPostRemoveCarrierCredentialAsync(string carrier, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(User, "Settings.Manage")).Succeeded)
		{
			return Forbid();
		}
		carrier = NormalizeCarrier(carrier);
		if (carrier.Length == 0)
		{
			return BadRequest();
		}
		string[] keys = [$"Tracking.{carrier}.ClientId", $"Tracking.{carrier}.ClientSecret"];
		List<SystemSetting> stored = await db.SystemSettings
			.Where(x => keys.Contains(x.SettingKey) && x.IsSensitive)
			.ToListAsync(cancellationToken);
		db.SystemSettings.RemoveRange(stored);
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync(
			"Tracking.CredentialsRemoved",
			"CarrierIntegration",
			carrier,
			User.FindFirstValue(ClaimTypes.NameIdentifier),
			new { Carrier = carrier, Configured = stored.Count > 0 },
			new { Carrier = carrier, Configured = false },
			"Carrier tracking credentials removed in Application Settings",
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = $"{carrier} automatic tracking credentials were removed.";
		return RedirectToPage();
	}

	public async Task<IActionResult> OnPostRunJobAsync(string jobType, CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(base.User, "Operations.RunBackup")).Succeeded)
		{
			return Forbid();
		}
		bool flag;
		switch (jobType)
		{
		case "DatabaseCheck":
		case "Backup":
		case "SynchronizeData":
			flag = true;
			break;
		default:
			flag = false;
			break;
		}
		if (!flag)
		{
			return BadRequest();
		}
		string correlationId = base.HttpContext.TraceIdentifier;
		OperationalJob job = new OperationalJob
		{
			JobType = jobType,
			Status = "Running",
			RequestedUtc = DateTime.UtcNow,
			RequestedByUserId = base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"),
			CorrelationId = correlationId
		};
		db.OperationalJobs.Add(job);
		await db.SaveChangesAsync(cancellationToken);
		try
		{
			OperationalJob operationalJob = job;
			string resultSummary = ((jobType == "DatabaseCheck") ? (await DatabaseCheckAsync(cancellationToken)) : ((!(jobType == "Backup")) ? (await SynchronizeAsync(cancellationToken)) : (await BackupAsync(correlationId, cancellationToken))));
			operationalJob.ResultSummary = resultSummary;
			job.Status = "Completed";
		}
		catch (Exception ex)
		{
			job.Status = "Failed";
			job.ResultSummary = ((ex.Message.Length > 900) ? ex.Message.Substring(0, 900) : ex.Message);
		}
		job.CompletedUtc = DateTime.UtcNow;
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync("Operations.JobCompleted", "OperationalJob", job.OperationalJobId.ToString(), job.RequestedByUserId, null, new { job.JobType, job.Status, job.ResultSummary }, null, correlationId, cancellationToken);
		base.TempData[(job.Status == "Completed") ? "Success" : "Warning"] = job.JobType + ": " + job.ResultSummary;
		return RedirectToPage();
	}

	public async Task<IActionResult> OnPostResetBusinessDataAsync(CancellationToken cancellationToken)
	{
		if (!User.IsInRole("Administrator") || !(await authorization.AuthorizeAsync(User, "Settings.Manage")).Succeeded)
		{
			return Forbid();
		}
		if (!ResetAcknowledged || !string.Equals(ResetConfirmation?.Trim(), ResetPhrase, StringComparison.Ordinal))
		{
			ModelState.AddModelError(nameof(ResetConfirmation), $"Acknowledge the warning and type {ResetPhrase} exactly.");
			await LoadAsync(cancellationToken);
			return Page();
		}

		string? userId = User.FindFirstValue(ClaimTypes.NameIdentifier);
		string correlationId = HttpContext.TraceIdentifier;
		BackupResult recoveryBackup = await backup.CreateAndVerifyAsync(userId, correlationId, cancellationToken);
		if (!recoveryBackup.IsVerified)
		{
			ModelState.AddModelError(string.Empty, "The safety backup could not be verified. No data was deleted.");
			await LoadAsync(cancellationToken);
			return Page();
		}

		int assets = await db.Assets.CountAsync(cancellationToken);
		int employees = await db.Employees.CountAsync(cancellationToken);
		int shipments = await db.Shipments.CountAsync(cancellationToken);
		await using var transaction = await db.Database.BeginTransactionAsync(cancellationToken);
		string[] deleteCommands =
		[
			"DELETE FROM \"ShipmentTrackingEvents\";", "DELETE FROM \"ShipmentItems\";",
			"DELETE FROM \"AssetAssignments\";", "DELETE FROM \"AssetNetworkAddresses\";",
			"DELETE FROM \"AssetStatusHistory\";", "DELETE FROM \"AssetImportReviews\";",
			"DELETE FROM \"Shipments\";", "DELETE FROM \"Assets\";", "DELETE FROM \"Employees\";",
			"DELETE FROM \"StockLevelTargets\";", "DELETE FROM \"OperationalJobs\";", "DELETE FROM \"AuditEvents\";"
		];
		foreach (string command in deleteCommands)
		{
			await db.Database.ExecuteSqlRawAsync(command, cancellationToken);
		}
		await transaction.CommitAsync(cancellationToken);
		db.ChangeTracker.Clear();

		await audit.WriteAsync(
			"System.BusinessDataReset", "System", "business-data", userId, null,
			new { AssetsDeleted = assets, EmployeesDeleted = employees, ShipmentsDeleted = shipments, RecoveryBackup = recoveryBackup.FileName },
			"Administrator-confirmed fresh start", correlationId, cancellationToken);
		TempData["Success"] = $"Business data was reset. Recovery backup: {recoveryBackup.FileName}. Accounts and application settings were preserved.";
		return RedirectToPage();
	}

	private async Task<string> DatabaseCheckAsync(CancellationToken token)
	{
		await db.Database.OpenConnectionAsync(token);
		string result;
		await using (DbCommand command = db.Database.GetDbConnection().CreateCommand())
		{
			command.CommandText = "PRAGMA quick_check;";
			string text = (await command.ExecuteScalarAsync(token))?.ToString() ?? "No result";
			object arg = text;
			result = $"SQLite quick check: {arg}. {await db.Assets.CountAsync(token)} assets verified.";
		}
		return result;
	}

	private async Task<string> BackupAsync(string correlationId, CancellationToken token)
	{
		BackupResult backupResult = await backup.CreateAndVerifyAsync(base.User.FindFirstValue("http://schemas.xmlsoap.org/ws/2005/05/identity/claims/nameidentifier"), correlationId, token);
		return $"Verified backup {backupResult.FileName} containing {backupResult.AssetCount} assets.";
	}

	private async Task<string> SynchronizeAsync(CancellationToken token)
	{
		await phaseOneSeeder.SeedAsync(token);
		await phaseTwoSeeder.SeedAsync(token);
		return "Reference data, employees, assignments, and system defaults synchronized.";
	}

	private async Task LoadAsync(CancellationToken token, bool populateBranding = true)
	{
		Settings = await (from x in db.SystemSettings.AsNoTracking()
			orderby x.SettingKey
			select x).ToListAsync(token);
		Jobs = await (from x in db.OperationalJobs.AsNoTracking()
			orderby x.RequestedUtc descending
			select x).Take(50).ToListAsync(token);
		CurrentLogoDataUrl = Settings.FirstOrDefault(x => x.SettingKey == "Branding.LogoDataUrl")?.Value;
		CarrierConfiguration = SupportedCarriers.ToDictionary(
			carrier => carrier,
			carrier =>
				(!string.IsNullOrWhiteSpace(configuration[$"Tracking:{carrier}:ClientId"])
					&& !string.IsNullOrWhiteSpace(configuration[$"Tracking:{carrier}:ClientSecret"]))
				|| (Settings.Any(x => x.IsSensitive && x.SettingKey == $"Tracking.{carrier}.ClientId" && x.Value.Length > 0)
					&& Settings.Any(x => x.IsSensitive && x.SettingKey == $"Tracking.{carrier}.ClientSecret" && x.Value.Length > 0)),
			StringComparer.OrdinalIgnoreCase);
		if (populateBranding)
		{
			Branding.ApplicationName = Value("Application.Name", "AssetPilot");
			Branding.OrganizationName = Value("Organization.Name", "");
			Branding.AccentColor = Value("Branding.AccentColor", "#0969da");
		}
	}

	private string Value(string key, string fallback) =>
		Settings.FirstOrDefault(x => x.SettingKey.Equals(key, StringComparison.OrdinalIgnoreCase))?.Value ?? fallback;

	private async Task SetValueAsync(string key, string value, string description, CancellationToken token)
	{
		SystemSetting? setting = await db.SystemSettings.SingleOrDefaultAsync(
			x => x.SettingKey == key,
			token);
		if (setting is null)
		{
			db.SystemSettings.Add(new SystemSetting
			{
				SettingKey = key,
				Value = value,
				Description = description,
				CreatedUtc = DateTime.UtcNow,
				ModifiedUtc = DateTime.UtcNow
			});
			return;
		}
		setting.Value = value;
		setting.ModifiedUtc = DateTime.UtcNow;
		setting.Version++;
	}

	private async Task<bool> HasStoredCredentialAsync(string carrier, CancellationToken token)
	{
		string secretKey = $"Tracking.{carrier}.ClientSecret";
		return !string.IsNullOrWhiteSpace(configuration[$"Tracking:{carrier}:ClientSecret"])
			|| await db.SystemSettings.AnyAsync(
				x => x.SettingKey == secretKey && x.IsSensitive && x.Value != "",
				token);
	}

	private async Task SetSensitiveValueAsync(string key, string value, string description, CancellationToken token)
	{
		SystemSetting? setting = await db.SystemSettings.SingleOrDefaultAsync(x => x.SettingKey == key, token);
		if (setting is null)
		{
			db.SystemSettings.Add(new SystemSetting
			{
				SettingKey = key,
				Value = value,
				Description = description,
				IsSensitive = true,
				CreatedUtc = DateTime.UtcNow,
				ModifiedUtc = DateTime.UtcNow
			});
			return;
		}
		setting.Value = value;
		setting.Description = description;
		setting.IsSensitive = true;
		setting.ModifiedUtc = DateTime.UtcNow;
		setting.Version++;
	}

	private static string NormalizeCarrier(string? carrier) => carrier?.Trim().ToUpperInvariant() switch
	{
		"UPS" => "UPS",
		"FEDEX" or "FED EX" => "FedEx",
		"USPS" => "USPS",
		_ => ""
	};
}
