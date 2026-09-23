using System.ComponentModel.DataAnnotations;
using System.Linq;
using System.Threading.Tasks;
using AssetPilot.Infrastructure.Identity;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;

namespace AssetPilot.Web.Pages;

public sealed class SetupModel(UserManager<ApplicationUser> userManager, SignInManager<ApplicationUser> signInManager) : PageModel
{
	public sealed class SetupInput
	{
		[Required]
		[StringLength(100)]
		[Display(Name = "Your name")]
		public string DisplayName { get; set; } = "";

		[Required]
		[EmailAddress]
		public string Email { get; set; } = "";

		[Required]
		[DataType(DataType.Password)]
		[MinLength(12)]
		public string Password { get; set; } = "";

		[Required]
		[DataType(DataType.Password)]
		[Compare("Password")]
		[Display(Name = "Confirm password")]
		public string ConfirmPassword { get; set; } = "";
	}

	[BindProperty]
	public SetupInput Input { get; set; } = new SetupInput();

	public IActionResult OnGet()
	{
		if (!userManager.Users.Any())
		{
			return Page();
		}
		return RedirectToPage("/Index");
	}

	public async Task<IActionResult> OnPostAsync()
	{
		if (userManager.Users.Any())
		{
			return RedirectToPage("/Index");
		}
		if (!base.ModelState.IsValid)
		{
			return Page();
		}
		ApplicationUser user = new ApplicationUser
		{
			UserName = Input.Email.Trim(),
			Email = Input.Email.Trim(),
			DisplayName = Input.DisplayName.Trim(),
			EmailConfirmed = true
		};
		IdentityResult identityResult = await userManager.CreateAsync(user, Input.Password);
		if (identityResult.Succeeded)
		{
			await userManager.AddToRoleAsync(user, "Administrator");
			await signInManager.SignInAsync(user, isPersistent: false);
			return RedirectToPage("/Index");
		}
		foreach (IdentityError error in identityResult.Errors)
		{
			base.ModelState.AddModelError(string.Empty, error.Description);
		}
		return Page();
	}
}
