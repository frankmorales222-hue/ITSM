using System;
using System.Collections.Generic;

namespace AssetPilot.Application.Security;

public static class RoleTemplates
{
	public const string Administrator = "Administrator";

	public const string AssetManager = "Asset Manager";

	public const string Technician = "Technician";

	public const string ReportUser = "Report User";

	public const string Auditor = "Auditor";

	public static IReadOnlyList<string> All { get; } = new _003C_003Ez__ReadOnlyArray<string>(new string[5] { "Administrator", "Asset Manager", "Technician", "Report User", "Auditor" });

	public static IReadOnlyDictionary<string, IReadOnlySet<string>> DefaultPermissions { get; } =
		new Dictionary<string, IReadOnlySet<string>>(StringComparer.OrdinalIgnoreCase)
		{
			[Administrator] = new HashSet<string>(PermissionKeys.All, StringComparer.Ordinal),
			[AssetManager] = new HashSet<string>(StringComparer.Ordinal)
			{
				PermissionKeys.AssetsView,
				PermissionKeys.AssetsCreate,
				PermissionKeys.AssetsEdit,
				PermissionKeys.AssetsArchive,
				PermissionKeys.AssetsChangeStatus,
				PermissionKeys.AssetsAssign,
				PermissionKeys.AssetsImport,
				PermissionKeys.AssetsExport,
				PermissionKeys.MasterDataView,
				PermissionKeys.MasterDataManage,
				PermissionKeys.EmployeesView,
				PermissionKeys.EmployeesManage,
				PermissionKeys.EmployeesImport,
				PermissionKeys.ShipmentsView,
				PermissionKeys.ShipmentsCreate,
				PermissionKeys.ShipmentsEdit,
				PermissionKeys.ShipmentsConfirmReceipt,
				PermissionKeys.ReportsView,
				PermissionKeys.ReportsExport
			},
			[Technician] = new HashSet<string>(StringComparer.Ordinal)
			{
				PermissionKeys.AssetsView,
				PermissionKeys.AssetsEdit,
				PermissionKeys.AssetsChangeStatus,
				PermissionKeys.AssetsAssign,
				PermissionKeys.MasterDataView,
				PermissionKeys.EmployeesView,
				PermissionKeys.ShipmentsView,
				PermissionKeys.ShipmentsCreate,
				PermissionKeys.ShipmentsEdit,
				PermissionKeys.ShipmentsConfirmReceipt
			},
			[ReportUser] = new HashSet<string>(StringComparer.Ordinal)
			{
				PermissionKeys.AssetsView,
				PermissionKeys.EmployeesView,
				PermissionKeys.ShipmentsView,
				PermissionKeys.ReportsView,
				PermissionKeys.ReportsExport
			},
			[Auditor] = new HashSet<string>(StringComparer.Ordinal)
			{
				PermissionKeys.AssetsView,
				PermissionKeys.AssetsExport,
				PermissionKeys.EmployeesView,
				PermissionKeys.ShipmentsView,
				PermissionKeys.ReportsView,
				PermissionKeys.ReportsExport,
				PermissionKeys.SecurityViewAudit,
				PermissionKeys.OperationsViewJobs
			}
		};
}
