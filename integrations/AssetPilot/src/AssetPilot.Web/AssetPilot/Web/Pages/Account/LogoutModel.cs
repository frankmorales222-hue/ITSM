using System.Threading.Tasks;
using AssetPilot.Infrastructure.Identity;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace AssetPilot.Web.Pages.Account;

public sealed class LogoutModel(SignInManager<ApplicationUser> signInManager) : PageModel
{
	public async Task<IActionResult> OnPostAsync()
	{
		await signInManager.SignOutAsync();
		return RedirectToPage("/Account/Login");
	}
}
