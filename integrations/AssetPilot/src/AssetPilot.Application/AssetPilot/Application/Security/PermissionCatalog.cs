using System.Collections.Generic;

namespace AssetPilot.Application.Security;

public static class PermissionCatalog
{
	public static IReadOnlyList<PermissionDefinition> All { get; } = new _003C_003Ez__ReadOnlyArray<PermissionDefinition>(new PermissionDefinition[29]
	{
		new PermissionDefinition("Assets.View", "Assets", "View assets", "View asset records."),
		new PermissionDefinition("Assets.Create", "Assets", "Create assets", "Create asset records."),
		new PermissionDefinition("Assets.Edit", "Assets", "Edit assets", "Edit asset records."),
		new PermissionDefinition("Assets.Archive", "Assets", "Archive assets", "Archive asset records.", IsSensitive: true),
		new PermissionDefinition("Assets.ChangeStatus", "Assets", "Change asset status", "Change asset lifecycle status."),
		new PermissionDefinition("Assets.Assign", "Assets", "Assign assets", "Assign assets to people or locations."),
		new PermissionDefinition("Assets.Import", "Assets", "Import assets", "Import asset records.", IsSensitive: true),
		new PermissionDefinition("Assets.Export", "Assets", "Export assets", "Export asset records.", IsSensitive: true),
		new PermissionDefinition("MasterData.View", "Master Data", "View master data", "View governed reference data."),
		new PermissionDefinition("MasterData.Manage", "Master Data", "Manage master data", "Create, edit, and deactivate reference data.", IsSensitive: true),
		new PermissionDefinition("Employees.View", "Employees", "View employees", "View employees and assignment history."),
		new PermissionDefinition("Employees.Manage", "Employees", "Manage employees", "Create and update employee records.", IsSensitive: true),
		new PermissionDefinition("Employees.Import", "Employees", "Import employees", "Import employee records from files.", IsSensitive: true),
		new PermissionDefinition("Shipments.View", "Shipments", "View shipments", "View shipment records."),
		new PermissionDefinition("Shipments.Create", "Shipments", "Create shipments", "Create shipment records."),
		new PermissionDefinition("Shipments.Edit", "Shipments", "Edit shipments", "Edit shipment records."),
		new PermissionDefinition("Shipments.ConfirmReceipt", "Shipments", "Confirm receipt", "Confirm receipt of shipments."),
		new PermissionDefinition("Reports.View", "Reports", "View reports", "View operational reports."),
		new PermissionDefinition("Reports.Export", "Reports", "Export reports", "Export operational report data.", IsSensitive: true),
		new PermissionDefinition("Settings.Manage", "Operations", "Manage settings", "Change application settings.", IsSensitive: true),
		new PermissionDefinition("Security.ManageUsers", "Security", "Manage users", "Create and administer users.", IsSensitive: true),
		new PermissionDefinition("Security.ManageRoles", "Security", "Manage roles", "Create and administer roles.", IsSensitive: true),
		new PermissionDefinition("Security.ManagePermissions", "Security", "Manage permissions", "Assign permissions to roles.", IsSensitive: true),
		new PermissionDefinition("Security.ViewAudit", "Security", "View audit", "View security and application audit events.", IsSensitive: true),
		new PermissionDefinition("Operations.RunBackup", "Operations", "Run backup", "Run an application backup.", IsSensitive: true),
		new PermissionDefinition("Operations.ViewJobs", "Operations", "View jobs", "View background and maintenance jobs."),
		new PermissionDefinition("Operations.OverrideLocks", "Operations", "Override locks", "Override application locks.", IsSensitive: true),
		new PermissionDefinition("Licensing.View", "Licensing", "View licensing", "View license state."),
		new PermissionDefinition("Licensing.Install", "Licensing", "Install license", "Install or replace a license.", IsSensitive: true)
	});
}
