using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Razor.Internal;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.AspNetCore.Mvc.Rendering;
using Microsoft.AspNetCore.Mvc.ViewFeatures;
using Microsoft.AspNetCore.Razor.Hosting;

namespace AssetPilot.Web.Pages.Account;

[RazorCompiledItemMetadata("Identifier", "/Pages/Account/Logout.cshtml")]
[CreateNewOnMetadataUpdate]
internal sealed class Pages_Account_Logout : Page
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
	public IHtmlHelper<LogoutModel> Html { get; private set; }

	public ViewDataDictionary<LogoutModel> ViewData => (ViewDataDictionary<LogoutModel>)(base.PageContext?.ViewData);

	public LogoutModel Model => ViewData.Model;

	public override async Task ExecuteAsync()
	{
	}
}
