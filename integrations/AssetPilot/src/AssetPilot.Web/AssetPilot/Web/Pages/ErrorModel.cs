using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace AssetPilot.Web.Pages;

[ResponseCache(Duration = 0, Location = ResponseCacheLocation.None, NoStore = true)]
public sealed class ErrorModel : PageModel
{
	public string CorrelationId { get; private set; } = string.Empty;

	public void OnGet()
	{
		CorrelationId = base.HttpContext.TraceIdentifier;
	}
}
