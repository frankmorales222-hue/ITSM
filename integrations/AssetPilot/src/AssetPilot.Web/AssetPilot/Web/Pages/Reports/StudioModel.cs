using System.Security.Claims;
using System.Text.Json;
using AssetPilot.Domain.Assets;
using AssetPilot.Domain.Operations;
using AssetPilot.Domain.Shipments;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Web.Pages.Reports;

public sealed class StudioModel(AssetPilotDbContext db) : PageModel
{
    public sealed record MetricRow(string Label, int Count, int Percent);
    public sealed record WidgetData(string Id, string Title, string Description, IReadOnlyList<MetricRow> Rows);
    public sealed record WidgetPreference(string Id, bool Visible, string Display, int Limit);

    [BindProperty] public string? LayoutJson { get; set; }
    public IReadOnlyList<WidgetData> Widgets { get; private set; } = Array.Empty<WidgetData>();
    public IReadOnlyList<WidgetPreference> Layout { get; private set; } = Array.Empty<WidgetPreference>();

    private string SettingKey => $"DashboardStudio.User.{User.FindFirstValue(ClaimTypes.NameIdentifier)}";

    public async Task OnGetAsync(CancellationToken cancellationToken)
    {
        await LoadDataAsync(cancellationToken);
        Layout = await LoadLayoutAsync(cancellationToken);
    }

    public async Task<IActionResult> OnPostSaveAsync(CancellationToken cancellationToken)
    {
        await LoadDataAsync(cancellationToken);
        List<WidgetPreference>? requested = null;
        try { requested = JsonSerializer.Deserialize<List<WidgetPreference>>(LayoutJson ?? ""); } catch (JsonException) { }
        HashSet<string> validIds = Widgets.Select(x => x.Id).ToHashSet(StringComparer.OrdinalIgnoreCase);
        List<WidgetPreference> sanitized = (requested ?? []).Where(x => validIds.Contains(x.Id)).Select(x => new WidgetPreference(x.Id, x.Visible, x.Display is "bars" or "numbers" or "table" ? x.Display : "bars", Math.Clamp(x.Limit, 3, 20))).DistinctBy(x => x.Id, StringComparer.OrdinalIgnoreCase).ToList();
        foreach (string id in validIds.Where(id => sanitized.All(x => !x.Id.Equals(id, StringComparison.OrdinalIgnoreCase)))) sanitized.Add(new WidgetPreference(id, true, "bars", 8));
        string json = JsonSerializer.Serialize(sanitized);
        SystemSetting? setting = await db.SystemSettings.SingleOrDefaultAsync(x => x.SettingKey == SettingKey, cancellationToken);
        if (setting is null)
        {
            setting = new SystemSetting { SettingKey = SettingKey, Value = json, Description = "Per-user Dashboard Studio layout.", IsSensitive = false, CreatedUtc = DateTime.UtcNow, ModifiedUtc = DateTime.UtcNow };
            db.SystemSettings.Add(setting);
        }
        else { setting.Value = json; setting.ModifiedUtc = DateTime.UtcNow; setting.Version++; }
        await db.SaveChangesAsync(cancellationToken);
        TempData["Success"] = "Your dashboard layout was saved.";
        return RedirectToPage();
    }

    public async Task<IActionResult> OnPostResetAsync(CancellationToken cancellationToken)
    {
        SystemSetting? setting = await db.SystemSettings.SingleOrDefaultAsync(x => x.SettingKey == SettingKey, cancellationToken);
        if (setting is not null) { db.SystemSettings.Remove(setting); await db.SaveChangesAsync(cancellationToken); }
        TempData["Success"] = "The default dashboard layout was restored.";
        return RedirectToPage();
    }

    private async Task<IReadOnlyList<WidgetPreference>> LoadLayoutAsync(CancellationToken cancellationToken)
    {
        string? json = await db.SystemSettings.Where(x => x.SettingKey == SettingKey).Select(x => x.Value).SingleOrDefaultAsync(cancellationToken);
        try
        {
            List<WidgetPreference>? saved = JsonSerializer.Deserialize<List<WidgetPreference>>(json ?? "");
            if (saved is { Count: > 0 }) return saved;
        }
        catch (JsonException) { }
        return Widgets.Select(x => new WidgetPreference(x.Id, true, "bars", 8)).ToList();
    }

    private async Task LoadDataAsync(CancellationToken cancellationToken)
    {
        List<Asset> assets = await db.Assets.AsNoTracking().Where(x => !x.IsArchived).ToListAsync(cancellationToken);
        int total = Math.Max(1, assets.Count);
        static string Value(string? value, string fallback) => string.IsNullOrWhiteSpace(value) ? fallback : value.Trim();
        WidgetData Make(string id, string title, string description, IEnumerable<IGrouping<string, Asset>> groups) => new(id, title, description, groups.OrderByDescending(x => x.Count()).Select(x => new MetricRow(x.Key, x.Count(), (int)Math.Round(x.Count() * 100m / total))).ToList());
        WidgetData Counts(string id, string title, string description, IEnumerable<(string Label, int Count)> rows)
        {
            List<(string Label, int Count)> values = rows.Where(x => x.Count > 0).OrderByDescending(x => x.Count).ToList();
            int denominator = Math.Max(1, values.Sum(x => x.Count));
            return new WidgetData(id, title, description, values.Select(x => new MetricRow(x.Label, x.Count, (int)Math.Round(x.Count * 100m / denominator))).ToList());
        }
        List<Shipment> shipments = await db.Shipments.AsNoTracking().Where(x => !x.IsArchived).ToListAsync(cancellationToken);
        DateOnly today = DateOnly.FromDateTime(DateTime.Today);
        Widgets = new[]
        {
            Make("location", "Inventory by location", "Where equipment is physically recorded.", assets.GroupBy(x => Value(x.Location, "Unknown"), StringComparer.OrdinalIgnoreCase)),
            Make("status", "Inventory by status", "Lifecycle status across all equipment.", assets.GroupBy(x => Value(x.Status, "Unknown"), StringComparer.OrdinalIgnoreCase)),
            Make("type", "Inventory by equipment type", "Computers, monitors, peripherals, and other equipment.", assets.GroupBy(x => Value(x.AssetType, "Other"), StringComparer.OrdinalIgnoreCase)),
            Make("condition", "Inventory by condition", "Recorded physical condition of equipment.", assets.GroupBy(x => Value(x.Condition, "Unknown"), StringComparer.OrdinalIgnoreCase)),
            Make("workstation", "Inventory by classification", "Operational classification from the workstation field.", assets.GroupBy(x => Value(x.Workstation, "Unclassified"), StringComparer.OrdinalIgnoreCase)),
            Make("department", "Custody by department", "Equipment currently recorded against each department.", assets.GroupBy(x => Value(x.Department, "Unassigned"), StringComparer.OrdinalIgnoreCase)),
            Counts("assignment", "Assignment utilization", "Assigned and unassigned equipment.", new[] { ("Assigned", assets.Count(x => !string.IsNullOrWhiteSpace(x.AssignedTo))), ("Unassigned", assets.Count(x => string.IsNullOrWhiteSpace(x.AssignedTo))) }),
            Counts("availability", "Stock availability", "Equipment ready to assign compared with the rest of inventory.", new[] { ("Available", assets.Count(x => x.Status.Equals("In Stock", StringComparison.OrdinalIgnoreCase) && string.IsNullOrWhiteSpace(x.AssignedTo))), ("Not available", assets.Count(x => !x.Status.Equals("In Stock", StringComparison.OrdinalIgnoreCase) || !string.IsNullOrWhiteSpace(x.AssignedTo))) }),
            Counts("warranty", "Warranty outlook", "Warranty exposure based on recorded expiration dates.", new[] { ("Expired", assets.Count(x => x.WarrantyExpiration < today)), ("Next 90 days", assets.Count(x => x.WarrantyExpiration >= today && x.WarrantyExpiration <= today.AddDays(90))), ("More than 90 days", assets.Count(x => x.WarrantyExpiration > today.AddDays(90))), ("Not recorded", assets.Count(x => x.WarrantyExpiration == null)) }),
            Counts("shipments", "Shipments by status", "Current logistics workload and completed movements.", shipments.GroupBy(x => Value(x.Status, "Unknown"), StringComparer.OrdinalIgnoreCase).Select(x => (x.Key, x.Count())))
        };
    }
}
