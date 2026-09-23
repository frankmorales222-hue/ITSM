using System.Text;
using AssetPilot.Infrastructure.Identity;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Mvc;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.AspNetCore.WebUtilities;

namespace AssetPilot.Web.Pages.Account;

[AllowAnonymous]
public sealed class SetPasswordModel(UserManager<ApplicationUser> userManager) : PageModel
{
    [BindProperty(SupportsGet = true)] public string? UserId { get; set; }
    [BindProperty(SupportsGet = true)] public string? Code { get; set; }
    [BindProperty] public string? Password { get; set; }
    [BindProperty] public string? ConfirmPassword { get; set; }

    public IActionResult OnGet() => string.IsNullOrWhiteSpace(UserId) || string.IsNullOrWhiteSpace(Code) ? BadRequest() : Page();

    public async Task<IActionResult> OnPostAsync()
    {
        if (string.IsNullOrWhiteSpace(Password) || Password.Length < 12) ModelState.AddModelError(nameof(Password), "Use at least 12 characters.");
        if (!string.Equals(Password, ConfirmPassword, StringComparison.Ordinal)) ModelState.AddModelError(nameof(ConfirmPassword), "The passwords do not match.");
        if (!ModelState.IsValid) return Page();
        ApplicationUser? user = await userManager.FindByIdAsync(UserId!);
        if (user is null) return BadRequest();
        string token;
        try { token = Encoding.UTF8.GetString(WebEncoders.Base64UrlDecode(Code!)); }
        catch (FormatException) { return BadRequest(); }
        IdentityResult result = await userManager.ResetPasswordAsync(user, token, Password!);
        if (!result.Succeeded) { foreach (var error in result.Errors) ModelState.AddModelError(string.Empty, error.Description); return Page(); }
        user.EmailConfirmed = true;
        await userManager.UpdateAsync(user);
        TempData["Success"] = "Your password is ready. Sign in to AssetPilot.";
        return RedirectToPage("/Account/Login");
    }
}
