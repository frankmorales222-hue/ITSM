using System;
using System.Collections.Generic;
using System.Linq;
using System.Security.Claims;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Auditing;
using AssetPilot.Domain.Assets;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.EntityFrameworkCore;

namespace AssetPilot.Web.Pages.Assets;

public sealed class DuplicatesModel(
	AssetPilotDbContext db,
	IAuditService audit,
	IAuthorizationService authorization) : PageModel
{
	public sealed record ReviewRow(
		int Id,
		string Source,
		int RowNumber,
		string AssetTag,
		string Serial,
		string AssignedTo,
		string Reason,
		string Status,
		int? MatchingAssetId,
		string? MatchingAssetTag,
		DateTime CreatedUtc);

	[BindProperty(SupportsGet = true)]
	public string Status { get; set; } = "Pending";

	public IReadOnlyList<ReviewRow> Reviews { get; private set; } = Array.Empty<ReviewRow>();

	public int PendingCount { get; private set; }

	public async Task OnGetAsync(CancellationToken cancellationToken)
	{
		PendingCount = await db.AssetImportReviews.CountAsync(x => x.Status == "Pending", cancellationToken);
		IQueryable<AssetImportReview> source = db.AssetImportReviews
			.AsNoTracking()
			.Include(x => x.MatchingAsset);
		if (!string.IsNullOrWhiteSpace(Status))
		{
			source = source.Where(x => x.Status == Status);
		}
		List<AssetImportReview> reviews = await source
			.OrderByDescending(x => x.CreatedUtc)
			.Take(1000)
			.ToListAsync(cancellationToken);
		Reviews = reviews.Select(ToRow).ToList();
	}

	public async Task<IActionResult> OnPostDismissAsync(
		int id,
		string? notes,
		CancellationToken cancellationToken)
	{
		if (!(await authorization.AuthorizeAsync(User, "Assets.Import")).Succeeded)
		{
			return Forbid();
		}
		AssetImportReview? review = await db.AssetImportReviews
			.SingleOrDefaultAsync(x => x.AssetImportReviewId == id && x.Status == "Pending", cancellationToken);
		if (review is null)
		{
			return NotFound();
		}
		DateTime now = DateTime.UtcNow;
		review.Status = "Dismissed";
		review.ResolvedUtc = now;
		review.ResolvedByUserId = User.FindFirstValue(ClaimTypes.NameIdentifier);
		review.ResolutionNotes = Clean(notes);
		review.ModifiedUtc = now;
		review.Version++;
		await db.SaveChangesAsync(cancellationToken);
		await audit.WriteAsync(
			"AssetImportReview.Dismissed",
			"AssetImportReview",
			id.ToString(),
			review.ResolvedByUserId,
			null,
			new { review.SourceFileName, review.SourceRowNumber, review.MatchReason },
			review.ResolutionNotes,
			HttpContext.TraceIdentifier,
			cancellationToken);
		TempData["Success"] = "The duplicate row was dismissed.";
		return RedirectToPage(new { Status = "Pending" });
	}

	private static ReviewRow ToRow(AssetImportReview review)
	{
		string[] values = JsonSerializer.Deserialize<string[]>(review.RowValuesJson) ?? Array.Empty<string>();
		string Value(int index) => index < values.Length ? values[index] : "";
		return new ReviewRow(
			review.AssetImportReviewId,
			review.SourceFileName,
			review.SourceRowNumber,
			Value(2),
			Value(3),
			Value(18),
			review.MatchReason,
			review.Status,
			review.MatchingAssetId,
			review.MatchingAsset?.AssetTag,
			review.CreatedUtc);
	}

	private static string? Clean(string? value) =>
		string.IsNullOrWhiteSpace(value) ? null : value.Trim();
}
