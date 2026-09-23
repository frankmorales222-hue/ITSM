namespace AssetPilot.Application.Security;

public sealed record PermissionDefinition(string Key, string ModuleCode, string Name, string Description, bool IsSensitive = false);
