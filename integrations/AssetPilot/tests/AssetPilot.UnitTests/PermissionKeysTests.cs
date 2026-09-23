using AssetPilot.Application.Security;
using Xunit;

namespace AssetPilot.UnitTests;

public sealed class PermissionKeysTests
{
    [Fact]
    public void Permission_keys_are_unique()
    {
        var values = typeof(PermissionKeys)
            .GetFields()
            .Select(field => field.GetRawConstantValue())
            .OfType<string>()
            .ToArray();

        Assert.Equal(values.Length, values.Distinct(StringComparer.Ordinal).Count());
    }

    [Fact]
    public void Built_in_role_templates_only_reference_known_permissions()
    {
        HashSet<string> knownPermissions = PermissionCatalog.All
            .Select(permission => permission.Key)
            .ToHashSet(StringComparer.Ordinal);

        Assert.Equal(knownPermissions, RoleTemplates.DefaultPermissions[RoleTemplates.Administrator]);
        foreach ((string role, IReadOnlySet<string> permissions) in RoleTemplates.DefaultPermissions)
        {
            Assert.NotEmpty(permissions);
            Assert.All(permissions, permission => Assert.Contains(permission, knownPermissions));
        }
    }
}
