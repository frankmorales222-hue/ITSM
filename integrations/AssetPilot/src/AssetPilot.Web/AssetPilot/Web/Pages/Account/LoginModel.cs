using System.ComponentModel.DataAnnotations;
using System.Security.Principal;
using System.Threading.Tasks;
using AssetPilot.Infrastructure.Identity;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace AssetPilot.Web.Pages.Account;

public sealed class LoginModel(SignInManager<ApplicationUser> signInManager) : PageModel
{
	public sealed class LoginInput
	{
		[Required]
		[EmailAddress]
		public string Email { get; set; } = "";

		[Required]
		[DataType(DataType.Password)]
		public string Password { get; set; } = "";

		[Display(Name = "Remember me")]
		public bool RememberMe { get; set; }
	}

	[BindProperty]
	public LoginInput Input { get; set; } = new LoginInput();

	[BindProperty(SupportsGet = true)]
	public string? ReturnUrl { get; set; }

	public IActionResult OnGet()
	{
		IIdentity? identity = base.User.Identity;
		if (identity == null || !identity.IsAuthenticated)
		{
			return Page();
		}
		return RedirectToPage("/Index");
	}

	public async Task<IActionResult> OnPostAsync()
	{
		if (!base.ModelState.IsValid)
		{
			return Page();
		}
		Microsoft.AspNetCore.Identity.SignInResult signInResult = await signInManager.PasswordSignInAsync(Input.Email.Trim(), Input.Password, Input.RememberMe, lockoutOnFailure: true);
		if (signInResult.Succeeded)
		{
			string destination = !string.IsNullOrWhiteSpace(ReturnUrl) && Url.IsLocalUrl(ReturnUrl)
				? ReturnUrl
				: "/";
			return LocalRedirect(destination);
		}
		base.ModelState.AddModelError(string.Empty, signInResult.IsLockedOut ? "Account locked. Try again later." : "Email or password is incorrect.");
		return Page();
	}
}
