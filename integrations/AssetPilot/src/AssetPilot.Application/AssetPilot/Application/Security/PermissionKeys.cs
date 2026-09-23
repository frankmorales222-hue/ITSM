using System.Collections.Generic;

namespace AssetPilot.Application.Security;

public static class PermissionKeys
{
	public const string AssetsView = "Assets.View";

	public const string AssetsCreate = "Assets.Create";

	public const string AssetsEdit = "Assets.Edit";

	public const string AssetsArchive = "Assets.Archive";

	public const string AssetsChangeStatus = "Assets.ChangeStatus";

	public const string AssetsAssign = "Assets.Assign";

	public const string AssetsImport = "Assets.Import";

	public const string AssetsExport = "Assets.Export";

	public const string MasterDataView = "MasterData.View";

	public const string MasterDataManage = "MasterData.Manage";

	public const string EmployeesView = "Employees.View";

	public const string EmployeesManage = "Employees.Manage";

	public const string EmployeesImport = "Employees.Import";

	public const string ShipmentsView = "Shipments.View";

	public const string ShipmentsCreate = "Shipments.Create";

	public const string ShipmentsEdit = "Shipments.Edit";

	public const string ShipmentsConfirmReceipt = "Shipments.ConfirmReceipt";

	public const string ReportsView = "Reports.View";

	public const string ReportsExport = "Reports.Export";

	public const string SettingsManage = "Settings.Manage";

	public const string SecurityManageUsers = "Security.ManageUsers";

	public const string SecurityManageRoles = "Security.ManageRoles";

	public const string SecurityManagePermissions = "Security.ManagePermissions";

	public const string SecurityViewAudit = "Security.ViewAudit";

	public const string OperationsRunBackup = "Operations.RunBackup";

	public const string OperationsViewJobs = "Operations.ViewJobs";

	public const string OperationsOverrideLocks = "Operations.OverrideLocks";

	public const string LicensingView = "Licensing.View";

	public const string LicensingInstall = "Licensing.Install";

	public static IReadOnlyList<string> All { get; } = new _003C_003Ez__ReadOnlyArray<string>(new string[29]
	{
		"Assets.View", "Assets.Create", "Assets.Edit", "Assets.Archive", "Assets.ChangeStatus", "Assets.Assign", "Assets.Import", "Assets.Export", "MasterData.View", "MasterData.Manage",
		"Employees.View", "Employees.Manage", "Employees.Import", "Shipments.View", "Shipments.Create", "Shipments.Edit", "Shipments.ConfirmReceipt", "Reports.View", "Reports.Export", "Settings.Manage",
		"Security.ManageUsers", "Security.ManageRoles", "Security.ManagePermissions", "Security.ViewAudit", "Operations.RunBackup", "Operations.ViewJobs", "Operations.OverrideLocks", "Licensing.View", "Licensing.Install"
	});
}
