using System;
using Microsoft.AspNetCore.Identity;

namespace AssetPilot.Infrastructure.Identity;

public sealed class ApplicationUser : IdentityUser
{
	public required string DisplayName { get; set; }

	public bool IsActive { get; set; } = true;

	public DateTime? LastSignInUtc { get; set; }
}
