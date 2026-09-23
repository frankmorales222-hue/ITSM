using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using System.Security.Claims;
using System.Text;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Assets;
using AssetPilot.Application.Auditing;
using AssetPilot.Domain.Assets;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Web.Pages.Assets;

public sealed class DuplicateEditModel(
	AssetPilotDbContext db,
	IAssetImportService importer,
	IAuditService audit,
	IAuthorizationService authorization) : PageModel
{
	public AssetImportReview Review { get; private set; } = null!;

	public IReadOnlyList<string> Headers => InventoryWorkbookFormat.Headers;

	[BindProperty]
	public List<string> Values { get; set; } = new();

	[BindProperty]
	public string? ResolutionNotes { get; set; }

	public async Task<IActionResult> OnGetAsync(int id, CancellationToken cancellationToken)
	{
		AssetImportReview? review = await db.AssetImportReviews
			.AsNoTracking()
			.Include(x => x.MatchingAsset)
			.SingleOrDefaultAsync(x => x.AssetImportReviewId == id, cancellationToken);
		if (review is null)
		{
			return NotFound();
		}
		Review = review;
		Values = Normalize(JsonSerializer.Deserialize<string[]>(review.RowValuesJson));
		return Page();
	}

	public Task<IActionResult> OnPostRetryAsync(int id, CancellationToken cancellationToken) =>
		ResolveAsync(id, updateExisting: false, cancellationToken);

	public Task<IActionResult> OnPostUpdateExistingAsync(int id, CancellationToken cancellationToken) =>
		ResolveAsync(id, updateExisting: true, cancellationToken);

	private async Task<IActionResult> ResolveAsync(
		int id,
		bool updateExisting,
		CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(User, "Assets.Import")).Succeeded)
		{
			return Forbid();
		}
		AssetImportReview? review = await db.AssetImportReviews
			.Include(x => x.MatchingAsset)
			.SingleOrDefaultAsync(x => x.AssetImportReviewId == id && x.Status == "Pending", cancellationToken);
		if (review is null)
		{
			return NotFound();
		}
		Values = Normalize(Values);
		review.RowValuesJson = JsonSerializer.Serialize(Values);
		string csv = Csv(InventoryWorkbookFormat.Headers) + Environment.NewLine + Csv(Values);
		await using var stream = new MemoryStream(Encoding.UTF8.GetBytes(csv));
		var result = await importer.ImportAsync(
			stream,
			$"duplicate-review-{id}.csv",
			updateExisting,
			User.FindFirstValue(ClaimTypes.NameIdentifier),
			$"duplicate-review-{id}",
			cancellationToken);
		bool succeeded = updateExisting ? result.Updated > 0 : result.Created > 0;
		if (!succeeded)
		{
			Review = review;
			ModelState.AddModelError(
				string.Empty,
				updateExisting
					? "No matching asset was updated. Check the identifying fields."
					: "The row still matches an existing asset. Correct the highlighted identifying fields or update the matching asset.");
			return Page();
		}
		DateTime now = DateTime.UtcNow;
		review.Status = updateExisting ? "Updated" : "Imported";
		review.ResolvedUtc = now;
		review.ResolvedByUserId = User.FindFirstValue(ClaimTypes.NameIdentifier);
		review.ResolutionNotes = Clean(ResolutionNotes);
		review.ModifiedUtc = now;
		review.Version++;
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync(
			updateExisting ? "AssetImportReview.UpdatedExisting" : "AssetImportReview.Imported",
			"AssetImportReview",
			id.ToString(),
			review.ResolvedByUserId,
			new { review.MatchReason, review.MatchingAssetId },
			new { review.Status, Result = result.Messages.FirstOrDefault() },
			review.ResolutionNotes,
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = updateExisting
			? "The matching asset was updated and the duplicate was resolved."
			: "The corrected row was imported.";
		return RedirectToPage("Duplicates");
	}

	private static List<string> Normalize(IEnumerable<string>? values) =>
		(values ?? Array.Empty<string>())
			.Concat(Enumerable.Repeat("", InventoryWorkbookFormat.Headers.Count))
			.Take(InventoryWorkbookFormat.Headers.Count)
			.Select(value => value?.Trim() ?? "")
			.ToList();

	private static string Csv(IEnumerable<string> values) =>
		string.Join(",", values.Select(value => $"\"{value.Replace("\"", "\"\"")}\""));

	private static string? Clean(string? value) =>
		string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
