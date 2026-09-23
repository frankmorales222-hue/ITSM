using Microsoft.AspNetCore.Authorization;

namespace AssetPilot.Infrastructure.Security;

public sealed record PermissionRequirement(string PermissionKey) : IAuthorizationRequirement;
