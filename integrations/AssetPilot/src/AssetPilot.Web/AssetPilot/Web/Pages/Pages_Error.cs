using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Razor.Internal;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.AspNetCore.Mvc.Rendering;
using Microsoft.AspNetCore.Mvc.ViewFeatures;
using Microsoft.AspNetCore.Razor.Hosting;

namespace AssetPilot.Web.Pages;

[RazorCompiledItemMetadata("Identifier", "/Pages/Error.cshtml")]
[CreateNewOnMetadataUpdate]
internal sealed class Pages_Error : Page
{
	[RazorInject]
	public IModelExpressionProvider ModelExpressionProvider { get; private set; }

	[RazorInject]
	public IUrlHelper Url { get; private set; }

	[RazorInject]
	public IViewComponentHelper Component { get; private set; }

	[RazorInject]
	public IJsonHelper Json { get; private set; }

	[RazorInject]
	public IHtmlHelper<ErrorModel> Html { get; private set; }

	public ViewDataDictionary<ErrorModel> ViewData => (ViewDataDictionary<ErrorModel>)(base.PageContext?.ViewData);

	public ErrorModel Model => ViewData.Model;

	public override async Task ExecuteAsync()
	{
		ViewData["Title"] = "Error";
		WriteLiteral("<h1>Something went wrong</h1>\n<p>Please provide the correlation ID to your administrator.</p>\n<p><strong>");
		Write(Model.CorrelationId);
		WriteLiteral("</strong></p>\n");
	}
}
