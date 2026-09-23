using System.Runtime.CompilerServices;
using System.Threading.Tasks;
using AssetPilot.Application.Operations;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.Razor.Internal;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.AspNetCore.Mvc.Rendering;
using Microsoft.AspNetCore.Mvc.TagHelpers;
using Microsoft.AspNetCore.Mvc.ViewFeatures;
using Microsoft.AspNetCore.Razor.Hosting;
using Microsoft.AspNetCore.Razor.Runtime.TagHelpers;
using Microsoft.AspNetCore.Razor.TagHelpers;

namespace AssetPilot.Web.Pages.System.Backups;

[RazorCompiledItemMetadata("Identifier", "/Pages/System/Backups/Index.cshtml")]
[CreateNewOnMetadataUpdate]
internal sealed class Pages_System_Backups_Index : Page
{
	private static readonly TagHelperAttribute __tagHelperAttribute_0 = new TagHelperAttribute("method", "post", HtmlAttributeValueStyle.DoubleQuotes);

	private static readonly TagHelperAttribute __tagHelperAttribute_1 = new TagHelperAttribute("asp-page-handler", "Create", HtmlAttributeValueStyle.DoubleQuotes);

	private TagHelperExecutionContext __tagHelperExecutionContext;

	private TagHelperRunner __tagHelperRunner = new TagHelperRunner();

	private string __tagHelperStringValueBuffer;

	private TagHelperScopeManager __backed__tagHelperScopeManager;

	private FormTagHelper __Microsoft_AspNetCore_Mvc_TagHelpers_FormTagHelper;

	private RenderAtEndOfFormTagHelper __Microsoft_AspNetCore_Mvc_TagHelpers_RenderAtEndOfFormTagHelper;

	private TagHelperScopeManager __tagHelperScopeManager
	{
		get
		{
			if (__backed__tagHelperScopeManager == null)
			{
				__backed__tagHelperScopeManager = new TagHelperScopeManager(base.StartTagHelperWritingScope, base.EndTagHelperWritingScope);
			}
			return __backed__tagHelperScopeManager;
		}
	}

	[RazorInject]
	public IModelExpressionProvider ModelExpressionProvider { get; private set; }

	[RazorInject]
	public IUrlHelper Url { get; private set; }

	[RazorInject]
	public IViewComponentHelper Component { get; private set; }

	[RazorInject]
	public IJsonHelper Json { get; private set; }

	[RazorInject]
	public IHtmlHelper<IndexModel> Html { get; private set; }

	public ViewDataDictionary<IndexModel> ViewData => (ViewDataDictionary<IndexModel>)(base.PageContext?.ViewData);

	public IndexModel Model => ViewData.Model;

	public override async Task ExecuteAsync()
	{
		ViewData["Title"] = "Backups";
		ViewData["Section"] = "System";
		if (base.TempData["Success"] is string value)
		{
			WriteLiteral(" <div class=\"toast success\">");
			Write(value);
			WriteLiteral("</div> ");
		}
		WriteLiteral("<div class=\"page-heading\">\n    <div><p class=\"eyebrow\">SYSTEM</p><h1>Database backups</h1><p class=\"muted\">Create a consistent SQLite backup and verify its integrity before it is retained.</p></div>\n");
		if (Model.CanRunBackup)
		{
			WriteLiteral(" ");
			__tagHelperExecutionContext = __tagHelperScopeManager.Begin("form", TagMode.StartTagAndEndTag, "bc5cc9cde390083592fb42332ca6548ea51de97fb05536b6ff8cf9f6e75702df5766", async delegate
			{
				WriteLiteral("<button class=\"button primary\" type=\"submit\">Create verified backup</button>");
			});
			__Microsoft_AspNetCore_Mvc_TagHelpers_FormTagHelper = CreateTagHelper<FormTagHelper>();
			__tagHelperExecutionContext.Add(__Microsoft_AspNetCore_Mvc_TagHelpers_FormTagHelper);
			__Microsoft_AspNetCore_Mvc_TagHelpers_RenderAtEndOfFormTagHelper = CreateTagHelper<RenderAtEndOfFormTagHelper>();
			__tagHelperExecutionContext.Add(__Microsoft_AspNetCore_Mvc_TagHelpers_RenderAtEndOfFormTagHelper);
			__Microsoft_AspNetCore_Mvc_TagHelpers_FormTagHelper.Method = (string)__tagHelperAttribute_0.Value;
			__tagHelperExecutionContext.AddTagHelperAttribute(__tagHelperAttribute_0);
			__Microsoft_AspNetCore_Mvc_TagHelpers_FormTagHelper.PageHandler = (string)__tagHelperAttribute_1.Value;
			__tagHelperExecutionContext.AddTagHelperAttribute(__tagHelperAttribute_1);
			await __tagHelperRunner.RunAsync(__tagHelperExecutionContext);
			if (!__tagHelperExecutionContext.Output.IsContentModified)
			{
				await __tagHelperExecutionContext.SetOutputContentAsync();
			}
			Write(__tagHelperExecutionContext.Output);
			__tagHelperExecutionContext = __tagHelperScopeManager.End();
			WriteLiteral(" ");
		}
		WriteLiteral("</div>\n<section class=\"panel\">\n    <div class=\"panel-heading\"><div><h2>Available backups</h2><p>Stored in the configured local backup directory.</p></div></div>\n    <div class=\"table-wrap\">\n        <table class=\"data-table\">\n            <thead><tr><th>File</th><th>Created</th><th>Size</th><th>Verification</th></tr></thead>\n            <tbody>\n");
		foreach (BackupInfo backup in Model.Backups)
		{
			WriteLiteral("                <tr><td><strong>");
			Write(backup.FileName);
			WriteLiteral("</strong></td><td>");
			Write(backup.CreatedUtc.ToLocalTime().ToString("g"));
			WriteLiteral("</td><td>");
			Write(((double)backup.SizeBytes / 1024.0 / 1024.0).ToString("N2"));
			WriteLiteral(" MB</td><td><span class=\"status-chip active\">Verified when created</span></td></tr>\n");
		}
		if (Model.Backups.Count == 0)
		{
			WriteLiteral(" <tr><td colspan=\"4\"><div class=\"empty-state compact\"><h2>No backups yet</h2><p>Create the first verified backup before making major operational changes.</p></div></td></tr> ");
		}
		WriteLiteral("            </tbody>\n        </table>\n    </div>\n</section>\n<section class=\"form-section restore-note\">\n    <div class=\"section-title\"><span class=\"section-icon\">↺</span><div><h2>Restore procedure</h2><p>Restores are intentionally performed while AssetPilot is stopped.</p></div></div>\n    <ol><li>Stop every AssetPilot process using the database.</li><li>Copy the current database to a safe recovery location.</li><li>Replace it with the selected verified backup file.</li><li>Start AssetPilot and confirm <code>/health</code> and the dashboard counts.</li></ol>\n</section>\n");
	}
}
