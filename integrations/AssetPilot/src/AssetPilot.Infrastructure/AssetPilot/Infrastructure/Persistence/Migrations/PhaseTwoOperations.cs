using System;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using Microsoft.EntityFrameworkCore.Migrations;
using Microsoft.EntityFrameworkCore.Migrations.Operations;
using Microsoft.EntityFrameworkCore.Migrations.Operations.Builders;

namespace AssetPilot.Infrastructure.Persistence.Migrations;

[DbContext(typeof(AssetPilotDbContext))]
[Migration("20260729164226_PhaseTwoOperations")]
public class PhaseTwoOperations : Migration
{
	protected override void Up(MigrationBuilder migrationBuilder)
	{
		migrationBuilder.CreateTable("Employees", delegate(ColumnsBuilder table)
		{
			OperationBuilder<AddColumnOperation> employeeId = table.Column<int>("INTEGER").Annotation("Sqlite:Autoincrement", true);
			int? maxLength = 80;
			OperationBuilder<AddColumnOperation> employeeNumber = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: false, null, null, null, null, null, "NOCASE");
			maxLength = 200;
			OperationBuilder<AddColumnOperation> displayName = table.Column<string>("TEXT", null, maxLength);
			maxLength = 255;
			OperationBuilder<AddColumnOperation> email = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: false, null, null, null, null, null, "NOCASE");
			maxLength = 150;
			OperationBuilder<AddColumnOperation> department = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 200;
			OperationBuilder<AddColumnOperation> manager = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 150;
			OperationBuilder<AddColumnOperation> location = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 50;
			return new
			{
				EmployeeId = employeeId,
				EmployeeNumber = employeeNumber,
				DisplayName = displayName,
				Email = email,
				Department = department,
				Manager = manager,
				Location = location,
				Phone = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true),
				IsActive = table.Column<bool>("INTEGER"),
				CreatedUtc = table.Column<DateTime>("TEXT"),
				ModifiedUtc = table.Column<DateTime>("TEXT"),
				Version = table.Column<int>("INTEGER")
			};
		}, null, table =>
		{
			table.PrimaryKey("PK_Employees", x => x.EmployeeId);
		});
		migrationBuilder.CreateTable("OperationalJobs", delegate(ColumnsBuilder table)
		{
			OperationBuilder<AddColumnOperation> operationalJobId = table.Column<int>("INTEGER").Annotation("Sqlite:Autoincrement", true);
			int? maxLength = 100;
			OperationBuilder<AddColumnOperation> jobType = table.Column<string>("TEXT", null, maxLength);
			maxLength = 30;
			OperationBuilder<AddColumnOperation> status = table.Column<string>("TEXT", null, maxLength);
			OperationBuilder<AddColumnOperation> requestedUtc = table.Column<DateTime>("TEXT");
			maxLength = 450;
			OperationBuilder<AddColumnOperation> requestedByUserId = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			OperationBuilder<AddColumnOperation> completedUtc = table.Column<DateTime>("TEXT", null, null, rowVersion: false, null, nullable: true);
			maxLength = 1000;
			OperationBuilder<AddColumnOperation> resultSummary = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 100;
			return new
			{
				OperationalJobId = operationalJobId,
				JobType = jobType,
				Status = status,
				RequestedUtc = requestedUtc,
				RequestedByUserId = requestedByUserId,
				CompletedUtc = completedUtc,
				ResultSummary = resultSummary,
				CorrelationId = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true)
			};
		}, null, table =>
		{
			table.PrimaryKey("PK_OperationalJobs", x => x.OperationalJobId);
		});
		migrationBuilder.CreateTable("Shipments", delegate(ColumnsBuilder table)
		{
			OperationBuilder<AddColumnOperation> shipmentId = table.Column<int>("INTEGER").Annotation("Sqlite:Autoincrement", true);
			int? maxLength = 80;
			OperationBuilder<AddColumnOperation> shipmentNumber = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: false, null, null, null, null, null, "NOCASE");
			maxLength = 30;
			OperationBuilder<AddColumnOperation> direction = table.Column<string>("TEXT", null, maxLength);
			maxLength = 50;
			OperationBuilder<AddColumnOperation> status = table.Column<string>("TEXT", null, maxLength);
			maxLength = 100;
			OperationBuilder<AddColumnOperation> carrier = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 150;
			OperationBuilder<AddColumnOperation> trackingNumber = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true, null, null, null, null, null, "NOCASE");
			maxLength = 200;
			OperationBuilder<AddColumnOperation> sender = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 200;
			OperationBuilder<AddColumnOperation> recipient = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 200;
			OperationBuilder<AddColumnOperation> origin = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 200;
			OperationBuilder<AddColumnOperation> destination = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			OperationBuilder<AddColumnOperation> shipDate = table.Column<DateOnly>("TEXT", null, null, rowVersion: false, null, nullable: true);
			OperationBuilder<AddColumnOperation> expectedDate = table.Column<DateOnly>("TEXT", null, null, rowVersion: false, null, nullable: true);
			OperationBuilder<AddColumnOperation> receivedUtc = table.Column<DateTime>("TEXT", null, null, rowVersion: false, null, nullable: true);
			maxLength = 450;
			OperationBuilder<AddColumnOperation> receivedByUserId = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 1000;
			return new
			{
				ShipmentId = shipmentId,
				ShipmentNumber = shipmentNumber,
				Direction = direction,
				Status = status,
				Carrier = carrier,
				TrackingNumber = trackingNumber,
				Sender = sender,
				Recipient = recipient,
				Origin = origin,
				Destination = destination,
				ShipDate = shipDate,
				ExpectedDate = expectedDate,
				ReceivedUtc = receivedUtc,
				ReceivedByUserId = receivedByUserId,
				Notes = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true),
				IsArchived = table.Column<bool>("INTEGER"),
				CreatedUtc = table.Column<DateTime>("TEXT"),
				ModifiedUtc = table.Column<DateTime>("TEXT"),
				Version = table.Column<int>("INTEGER")
			};
		}, null, table =>
		{
			table.PrimaryKey("PK_Shipments", x => x.ShipmentId);
		});
		migrationBuilder.CreateTable("SystemSettings", delegate(ColumnsBuilder table)
		{
			OperationBuilder<AddColumnOperation> systemSettingId = table.Column<int>("INTEGER").Annotation("Sqlite:Autoincrement", true);
			int? maxLength = 150;
			OperationBuilder<AddColumnOperation> settingKey = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: false, null, null, null, null, null, "NOCASE");
			maxLength = 1000;
			OperationBuilder<AddColumnOperation> value = table.Column<string>("TEXT", null, maxLength);
			maxLength = 500;
			return new
			{
				SystemSettingId = systemSettingId,
				SettingKey = settingKey,
				Value = value,
				Description = table.Column<string>("TEXT", null, maxLength),
				IsSensitive = table.Column<bool>("INTEGER"),
				CreatedUtc = table.Column<DateTime>("TEXT"),
				ModifiedUtc = table.Column<DateTime>("TEXT"),
				Version = table.Column<int>("INTEGER")
			};
		}, null, table =>
		{
			table.PrimaryKey("PK_SystemSettings", x => x.SystemSettingId);
		});
		migrationBuilder.CreateTable("AssetAssignments", delegate(ColumnsBuilder table)
		{
			OperationBuilder<AddColumnOperation> assetAssignmentId = table.Column<int>("INTEGER").Annotation("Sqlite:Autoincrement", true);
			OperationBuilder<AddColumnOperation> assetId = table.Column<int>("INTEGER");
			OperationBuilder<AddColumnOperation> employeeId = table.Column<int>("INTEGER");
			OperationBuilder<AddColumnOperation> assignedUtc = table.Column<DateTime>("TEXT");
			int? maxLength = 450;
			OperationBuilder<AddColumnOperation> assignedByUserId = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 150;
			OperationBuilder<AddColumnOperation> assignedLocation = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 500;
			OperationBuilder<AddColumnOperation> notes = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			OperationBuilder<AddColumnOperation> returnedUtc = table.Column<DateTime>("TEXT", null, null, rowVersion: false, null, nullable: true);
			maxLength = 450;
			OperationBuilder<AddColumnOperation> returnedByUserId = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 50;
			OperationBuilder<AddColumnOperation> returnCondition = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 500;
			return new
			{
				AssetAssignmentId = assetAssignmentId,
				AssetId = assetId,
				EmployeeId = employeeId,
				AssignedUtc = assignedUtc,
				AssignedByUserId = assignedByUserId,
				AssignedLocation = assignedLocation,
				Notes = notes,
				ReturnedUtc = returnedUtc,
				ReturnedByUserId = returnedByUserId,
				ReturnCondition = returnCondition,
				ReturnNotes = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true)
			};
		}, null, table =>
		{
			table.PrimaryKey("PK_AssetAssignments", x => x.AssetAssignmentId);
			table.ForeignKey("FK_AssetAssignments_Assets_AssetId", x => x.AssetId, "Assets", "AssetId", null, ReferentialAction.NoAction, ReferentialAction.Restrict);
			table.ForeignKey("FK_AssetAssignments_Employees_EmployeeId", x => x.EmployeeId, "Employees", "EmployeeId", null, ReferentialAction.NoAction, ReferentialAction.Restrict);
		});
		migrationBuilder.CreateTable("ShipmentItems", delegate(ColumnsBuilder table)
		{
			OperationBuilder<AddColumnOperation> shipmentItemId = table.Column<int>("INTEGER").Annotation("Sqlite:Autoincrement", true);
			OperationBuilder<AddColumnOperation> shipmentId = table.Column<int>("INTEGER");
			OperationBuilder<AddColumnOperation> assetId = table.Column<int>("INTEGER");
			int? maxLength = 50;
			OperationBuilder<AddColumnOperation> conditionAtDispatch = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 50;
			OperationBuilder<AddColumnOperation> conditionAtReceipt = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 500;
			return new
			{
				ShipmentItemId = shipmentItemId,
				ShipmentId = shipmentId,
				AssetId = assetId,
				ConditionAtDispatch = conditionAtDispatch,
				ConditionAtReceipt = conditionAtReceipt,
				Notes = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true)
			};
		}, null, table =>
		{
			table.PrimaryKey("PK_ShipmentItems", x => x.ShipmentItemId);
			table.ForeignKey("FK_ShipmentItems_Assets_AssetId", x => x.AssetId, "Assets", "AssetId", null, ReferentialAction.NoAction, ReferentialAction.Restrict);
			table.ForeignKey("FK_ShipmentItems_Shipments_ShipmentId", x => x.ShipmentId, "Shipments", "ShipmentId", null, ReferentialAction.NoAction, ReferentialAction.Cascade);
		});
		migrationBuilder.CreateIndex("IX_AssetAssignments_AssetId_ReturnedUtc", "AssetAssignments", new string[2] { "AssetId", "ReturnedUtc" });
		migrationBuilder.CreateIndex("IX_AssetAssignments_EmployeeId_ReturnedUtc", "AssetAssignments", new string[2] { "EmployeeId", "ReturnedUtc" });
		migrationBuilder.Sql("CREATE UNIQUE INDEX \"IX_AssetAssignments_CurrentAsset\"\nON \"AssetAssignments\" (\"AssetId\")\nWHERE \"ReturnedUtc\" IS NULL;");
		migrationBuilder.CreateIndex("IX_Employees_Email", "Employees", "Email", null, unique: true);
		migrationBuilder.CreateIndex("IX_Employees_EmployeeNumber", "Employees", "EmployeeNumber", null, unique: true);
		migrationBuilder.CreateIndex("IX_OperationalJobs_RequestedUtc", "OperationalJobs", "RequestedUtc");
		migrationBuilder.CreateIndex("IX_ShipmentItems_AssetId", "ShipmentItems", "AssetId");
		migrationBuilder.CreateIndex("IX_ShipmentItems_ShipmentId_AssetId", "ShipmentItems", new string[2] { "ShipmentId", "AssetId" }, null, unique: true);
		migrationBuilder.CreateIndex("IX_Shipments_ShipmentNumber", "Shipments", "ShipmentNumber", null, unique: true);
		migrationBuilder.CreateIndex("IX_Shipments_TrackingNumber", "Shipments", "TrackingNumber");
		migrationBuilder.CreateIndex("IX_SystemSettings_SettingKey", "SystemSettings", "SettingKey", null, unique: true);
	}

	protected override void Down(MigrationBuilder migrationBuilder)
	{
		migrationBuilder.DropTable("AssetAssignments");
		migrationBuilder.DropTable("OperationalJobs");
		migrationBuilder.DropTable("ShipmentItems");
		migrationBuilder.DropTable("SystemSettings");
		migrationBuilder.DropTable("Employees");
		migrationBuilder.DropTable("Shipments");
	}

	protected override void BuildTargetModel(ModelBuilder modelBuilder)
	{
		modelBuilder.HasAnnotation("ProductVersion", "10.0.10");
		modelBuilder.Entity("AssetPilot.Domain.Assets.Asset", delegate(EntityTypeBuilder b)
		{
			b.Property<int>("AssetId").ValueGeneratedOnAdd().HasColumnType("INTEGER");
			b.Property<string>("AssetTag").IsRequired().HasMaxLength(80)
				.HasColumnType("TEXT")
				.UseCollation("NOCASE");
			b.Property<string>("AssetType").IsRequired().HasMaxLength(100)
				.HasColumnType("TEXT");
			b.Property<string>("AssignedTo").HasMaxLength(200).HasColumnType("TEXT");
			b.Property<string>("AssignedToEmail").HasMaxLength(255).HasColumnType("TEXT");
			b.Property<string>("Category").IsRequired().HasMaxLength(100)
				.HasColumnType("TEXT");
			b.Property<string>("Company").HasMaxLength(150).HasColumnType("TEXT");
			b.Property<string>("Condition").IsRequired().HasMaxLength(50)
				.HasColumnType("TEXT");
			b.Property<DateTime>("CreatedUtc").HasColumnType("TEXT");
			b.Property<string>("Department").HasMaxLength(150).HasColumnType("TEXT");
			b.Property<string>("Hostname").HasMaxLength(255).HasColumnType("TEXT")
				.UseCollation("NOCASE");
			b.Property<bool>("IsArchived").HasColumnType("INTEGER");
			b.Property<string>("Location").HasMaxLength(150).HasColumnType("TEXT");
			b.Property<string>("MacAddress").HasMaxLength(200).HasColumnType("TEXT");
			b.Property<string>("Manufacturer").HasMaxLength(100).HasColumnType("TEXT");
			b.Property<string>("Model").HasMaxLength(150).HasColumnType("TEXT");
			b.Property<DateTime>("ModifiedUtc").HasColumnType("TEXT");
			b.Property<string>("Name").IsRequired().HasMaxLength(200)
				.HasColumnType("TEXT");
			b.Property<string>("Project").HasMaxLength(150).HasColumnType("TEXT");
			b.Property<long?>("PurchaseCostCents").HasColumnType("INTEGER");
			b.Property<DateOnly?>("PurchaseDate").HasColumnType("TEXT");
			b.Property<string>("Purpose").HasMaxLength(150).HasColumnType("TEXT");
			b.Property<string>("SerialNumber").HasMaxLength(160).HasColumnType("TEXT")
				.UseCollation("NOCASE");
			b.Property<string>("SourceReference").HasMaxLength(255).HasColumnType("TEXT");
			b.Property<string>("Status").IsRequired().HasMaxLength(50)
				.HasColumnType("TEXT");
			b.Property<string>("Vendor").HasMaxLength(150).HasColumnType("TEXT");
			b.Property<int>("Version").IsConcurrencyToken().HasColumnType("INTEGER");
			b.Property<DateOnly?>("WarrantyExpiration").HasColumnType("TEXT");
			b.HasKey("AssetId");
			b.HasIndex("AssetTag").IsUnique();
			b.HasIndex("Hostname").IsUnique();
			b.HasIndex("SerialNumber").IsUnique();
			b.ToTable("Assets");
		});
		modelBuilder.Entity("AssetPilot.Domain.Assets.AssetNetworkAddress", delegate(EntityTypeBuilder b)
		{
			b.Property<int>("AssetNetworkAddressId").ValueGeneratedOnAdd().HasColumnType("INTEGER");
			b.Property<string>("Address").IsRequired().HasMaxLength(200)
				.HasColumnType("TEXT")
				.UseCollation("NOCASE");
			b.Property<string>("AddressType").IsRequired().HasMaxLength(30)
				.HasColumnType("TEXT");
			b.Property<int>("AssetId").HasColumnType("INTEGER");
			b.Property<DateTime>("CreatedUtc").HasColumnType("TEXT");
			b.Property<bool>("IsPrimary").HasColumnType("INTEGER");
			b.Property<DateTime>("ModifiedUtc").HasColumnType("TEXT");
			b.Property<string>("Notes").HasMaxLength(500).HasColumnType("TEXT");
			b.Property<int>("Version").IsConcurrencyToken().HasColumnType("INTEGER");
			b.HasKey("AssetNetworkAddressId");
			b.HasIndex("AssetId", "AddressType", "Address").IsUnique();
			b.ToTable("AssetNetworkAddresses");
		});
		modelBuilder.Entity("AssetPilot.Domain.Assets.AssetStatusHistory", delegate(EntityTypeBuilder b)
		{
			b.Property<long>("AssetStatusHistoryId").ValueGeneratedOnAdd().HasColumnType("INTEGER");
			b.Property<int>("AssetId").HasColumnType("INTEGER");
			b.Property<string>("ChangedByUserId").HasMaxLength(450).HasColumnType("TEXT");
			b.Property<DateTime>("ChangedUtc").HasColumnType("TEXT");
			b.Property<string>("FromStatus").HasMaxLength(50).HasColumnType("TEXT");
			b.Property<string>("Reason").HasMaxLength(500).HasColumnType("TEXT");
			b.Property<string>("ToStatus").IsRequired().HasMaxLength(50)
				.HasColumnType("TEXT");
			b.HasKey("AssetStatusHistoryId");
			b.HasIndex("AssetId", "ChangedUtc");
			b.ToTable("AssetStatusHistory");
		});
		modelBuilder.Entity("AssetPilot.Domain.Auditing.AuditEvent", delegate(EntityTypeBuilder b)
		{
			b.Property<long>("AuditEventId").ValueGeneratedOnAdd().HasColumnType("INTEGER");
			b.Property<string>("AfterJson").HasColumnType("TEXT");
			b.Property<string>("BeforeJson").HasColumnType("TEXT");
			b.Property<string>("CorrelationId").IsRequired().HasMaxLength(100)
				.HasColumnType("TEXT");
			b.Property<string>("EntityId").IsRequired().HasMaxLength(100)
				.HasColumnType("TEXT");
			b.Property<string>("EntityTypeCode").IsRequired().HasMaxLength(100)
				.HasColumnType("TEXT");
			b.Property<string>("EventTypeCode").IsRequired().HasMaxLength(100)
				.HasColumnType("TEXT");
			b.Property<DateTime>("EventUtc").HasColumnType("TEXT");
			b.Property<string>("Reason").HasColumnType("TEXT");
			b.Property<string>("UserId").HasColumnType("TEXT");
			b.HasKey("AuditEventId");
			b.HasIndex("EntityTypeCode", "EntityId", "EventUtc");
			b.ToTable("AuditEvents");
		});
		modelBuilder.Entity("AssetPilot.Domain.MasterData.ReferenceDataItem", delegate(EntityTypeBuilder b)
		{
			b.Property<int>("ReferenceDataItemId").ValueGeneratedOnAdd().HasColumnType("INTEGER");
			b.Property<string>("Code").HasMaxLength(50).HasColumnType("TEXT")
				.UseCollation("NOCASE");
			b.Property<DateTime>("CreatedUtc").HasColumnType("TEXT");
			b.Property<bool>("IsActive").HasColumnType("INTEGER");
			b.Property<string>("Kind").IsRequired().HasMaxLength(50)
				.HasColumnType("TEXT")
				.UseCollation("NOCASE");
			b.Property<DateTime>("ModifiedUtc").HasColumnType("TEXT");
			b.Property<string>("Name").IsRequired().HasMaxLength(150)
				.HasColumnType("TEXT")
				.UseCollation("NOCASE");
			b.Property<string>("Notes").HasMaxLength(500).HasColumnType("TEXT");
			b.Property<int?>("ParentId").HasColumnType("INTEGER");
			b.Property<int>("Version").IsConcurrencyToken().HasColumnType("INTEGER");
			b.HasKey("ReferenceDataItemId");
			b.HasIndex("ParentId");
			b.HasIndex("Kind", "Code").IsUnique();
			b.HasIndex("Kind", "Name").IsUnique();
			b.ToTable("ReferenceDataItems");
		});
		modelBuilder.Entity("AssetPilot.Domain.Operations.OperationalJob", delegate(EntityTypeBuilder b)
		{
			b.Property<int>("OperationalJobId").ValueGeneratedOnAdd().HasColumnType("INTEGER");
			b.Property<DateTime?>("CompletedUtc").HasColumnType("TEXT");
			b.Property<string>("CorrelationId").HasMaxLength(100).HasColumnType("TEXT");
			b.Property<string>("JobType").IsRequired().HasMaxLength(100)
				.HasColumnType("TEXT");
			b.Property<string>("RequestedByUserId").HasMaxLength(450).HasColumnType("TEXT");
			b.Property<DateTime>("RequestedUtc").HasColumnType("TEXT");
			b.Property<string>("ResultSummary").HasMaxLength(1000).HasColumnType("TEXT");
			b.Property<string>("Status").IsRequired().HasMaxLength(30)
				.HasColumnType("TEXT");
			b.HasKey("OperationalJobId");
			b.HasIndex("RequestedUtc");
			b.ToTable("OperationalJobs");
		});
		modelBuilder.Entity("AssetPilot.Domain.Operations.SystemSetting", delegate(EntityTypeBuilder b)
		{
			b.Property<int>("SystemSettingId").ValueGeneratedOnAdd().HasColumnType("INTEGER");
			b.Property<DateTime>("CreatedUtc").HasColumnType("TEXT");
			b.Property<string>("Description").IsRequired().HasMaxLength(500)
				.HasColumnType("TEXT");
			b.Property<bool>("IsSensitive").HasColumnType("INTEGER");
			b.Property<DateTime>("ModifiedUtc").HasColumnType("TEXT");
			b.Property<string>("SettingKey").IsRequired().HasMaxLength(150)
				.HasColumnType("TEXT")
				.UseCollation("NOCASE");
			b.Property<string>("Value").IsRequired().HasMaxLength(1000)
				.HasColumnType("TEXT");
			b.Property<int>("Version").IsConcurrencyToken().HasColumnType("INTEGER");
			b.HasKey("SystemSettingId");
			b.HasIndex("SettingKey").IsUnique();
			b.ToTable("SystemSettings");
		});
		modelBuilder.Entity("AssetPilot.Domain.People.AssetAssignment", delegate(EntityTypeBuilder b)
		{
			b.Property<int>("AssetAssignmentId").ValueGeneratedOnAdd().HasColumnType("INTEGER");
			b.Property<int>("AssetId").HasColumnType("INTEGER");
			b.Property<string>("AssignedByUserId").HasMaxLength(450).HasColumnType("TEXT");
			b.Property<string>("AssignedLocation").HasMaxLength(150).HasColumnType("TEXT");
			b.Property<DateTime>("AssignedUtc").HasColumnType("TEXT");
			b.Property<int>("EmployeeId").HasColumnType("INTEGER");
			b.Property<string>("Notes").HasMaxLength(500).HasColumnType("TEXT");
			b.Property<string>("ReturnCondition").HasMaxLength(50).HasColumnType("TEXT");
			b.Property<string>("ReturnNotes").HasMaxLength(500).HasColumnType("TEXT");
			b.Property<string>("ReturnedByUserId").HasMaxLength(450).HasColumnType("TEXT");
			b.Property<DateTime?>("ReturnedUtc").HasColumnType("TEXT");
			b.HasKey("AssetAssignmentId");
			b.HasIndex("AssetId", "ReturnedUtc");
			b.HasIndex("EmployeeId", "ReturnedUtc");
			b.ToTable("AssetAssignments");
		});
		modelBuilder.Entity("AssetPilot.Domain.People.Employee", delegate(EntityTypeBuilder b)
		{
			b.Property<int>("EmployeeId").ValueGeneratedOnAdd().HasColumnType("INTEGER");
			b.Property<DateTime>("CreatedUtc").HasColumnType("TEXT");
			b.Property<string>("Department").HasMaxLength(150).HasColumnType("TEXT");
			b.Property<string>("DisplayName").IsRequired().HasMaxLength(200)
				.HasColumnType("TEXT");
			b.Property<string>("Email").IsRequired().HasMaxLength(255)
				.HasColumnType("TEXT")
				.UseCollation("NOCASE");
			b.Property<string>("EmployeeNumber").IsRequired().HasMaxLength(80)
				.HasColumnType("TEXT")
				.UseCollation("NOCASE");
			b.Property<bool>("IsActive").HasColumnType("INTEGER");
			b.Property<string>("Location").HasMaxLength(150).HasColumnType("TEXT");
			b.Property<string>("Manager").HasMaxLength(200).HasColumnType("TEXT");
			b.Property<DateTime>("ModifiedUtc").HasColumnType("TEXT");
			b.Property<string>("Phone").HasMaxLength(50).HasColumnType("TEXT");
			b.Property<int>("Version").IsConcurrencyToken().HasColumnType("INTEGER");
			b.HasKey("EmployeeId");
			b.HasIndex("Email").IsUnique();
			b.HasIndex("EmployeeNumber").IsUnique();
			b.ToTable("Employees");
		});
		modelBuilder.Entity("AssetPilot.Domain.Security.Permission", delegate(EntityTypeBuilder b)
		{
			b.Property<int>("PermissionId").ValueGeneratedOnAdd().HasColumnType("INTEGER");
			b.Property<DateTime>("CreatedUtc").HasColumnType("TEXT");
			b.Property<string>("Description").HasColumnType("TEXT");
			b.Property<bool>("IsSensitive").HasColumnType("INTEGER");
			b.Property<DateTime>("ModifiedUtc").HasColumnType("TEXT");
			b.Property<string>("ModuleCode").IsRequired().HasMaxLength(50)
				.HasColumnType("TEXT");
			b.Property<string>("Name").IsRequired().HasMaxLength(150)
				.HasColumnType("TEXT");
			b.Property<string>("PermissionKey").IsRequired().HasMaxLength(150)
				.HasColumnType("TEXT");
			b.Property<int>("Version").IsConcurrencyToken().HasColumnType("INTEGER");
			b.HasKey("PermissionId");
			b.HasIndex("PermissionKey").IsUnique();
			b.ToTable("Permissions");
		});
		modelBuilder.Entity("AssetPilot.Domain.Security.RolePermission", delegate(EntityTypeBuilder b)
		{
			b.Property<string>("RoleId").HasColumnType("TEXT");
			b.Property<int>("PermissionId").HasColumnType("INTEGER");
			b.Property<bool>("IsAllowed").HasColumnType("INTEGER");
			b.HasKey("RoleId", "PermissionId");
			b.HasIndex("PermissionId");
			b.ToTable("RolePermissions");
		});
		modelBuilder.Entity("AssetPilot.Domain.Shipments.Shipment", delegate(EntityTypeBuilder b)
		{
			b.Property<int>("ShipmentId").ValueGeneratedOnAdd().HasColumnType("INTEGER");
			b.Property<string>("Carrier").HasMaxLength(100).HasColumnType("TEXT");
			b.Property<DateTime>("CreatedUtc").HasColumnType("TEXT");
			b.Property<string>("Destination").HasMaxLength(200).HasColumnType("TEXT");
			b.Property<string>("Direction").IsRequired().HasMaxLength(30)
				.HasColumnType("TEXT");
			b.Property<DateOnly?>("ExpectedDate").HasColumnType("TEXT");
			b.Property<bool>("IsArchived").HasColumnType("INTEGER");
			b.Property<DateTime>("ModifiedUtc").HasColumnType("TEXT");
			b.Property<string>("Notes").HasMaxLength(1000).HasColumnType("TEXT");
			b.Property<string>("Origin").HasMaxLength(200).HasColumnType("TEXT");
			b.Property<string>("ReceivedByUserId").HasMaxLength(450).HasColumnType("TEXT");
			b.Property<DateTime?>("ReceivedUtc").HasColumnType("TEXT");
			b.Property<string>("Recipient").HasMaxLength(200).HasColumnType("TEXT");
			b.Property<string>("Sender").HasMaxLength(200).HasColumnType("TEXT");
			b.Property<DateOnly?>("ShipDate").HasColumnType("TEXT");
			b.Property<string>("ShipmentNumber").IsRequired().HasMaxLength(80)
				.HasColumnType("TEXT")
				.UseCollation("NOCASE");
			b.Property<string>("Status").IsRequired().HasMaxLength(50)
				.HasColumnType("TEXT");
			b.Property<string>("TrackingNumber").HasMaxLength(150).HasColumnType("TEXT")
				.UseCollation("NOCASE");
			b.Property<int>("Version").IsConcurrencyToken().HasColumnType("INTEGER");
			b.HasKey("ShipmentId");
			b.HasIndex("ShipmentNumber").IsUnique();
			b.HasIndex("TrackingNumber");
			b.ToTable("Shipments");
		});
		modelBuilder.Entity("AssetPilot.Domain.Shipments.ShipmentItem", delegate(EntityTypeBuilder b)
		{
			b.Property<int>("ShipmentItemId").ValueGeneratedOnAdd().HasColumnType("INTEGER");
			b.Property<int>("AssetId").HasColumnType("INTEGER");
			b.Property<string>("ConditionAtDispatch").HasMaxLength(50).HasColumnType("TEXT");
			b.Property<string>("ConditionAtReceipt").HasMaxLength(50).HasColumnType("TEXT");
			b.Property<string>("Notes").HasMaxLength(500).HasColumnType("TEXT");
			b.Property<int>("ShipmentId").HasColumnType("INTEGER");
			b.HasKey("ShipmentItemId");
			b.HasIndex("AssetId");
			b.HasIndex("ShipmentId", "AssetId").IsUnique();
			b.ToTable("ShipmentItems");
		});
		modelBuilder.Entity("AssetPilot.Infrastructure.Identity.ApplicationUser", delegate(EntityTypeBuilder b)
		{
			b.Property<string>("Id").HasColumnType("TEXT");
			b.Property<int>("AccessFailedCount").HasColumnType("INTEGER");
			b.Property<string>("ConcurrencyStamp").IsConcurrencyToken().HasColumnType("TEXT");
			b.Property<string>("DisplayName").IsRequired().HasColumnType("TEXT");
			b.Property<string>("Email").HasMaxLength(256).HasColumnType("TEXT");
			b.Property<bool>("EmailConfirmed").HasColumnType("INTEGER");
			b.Property<bool>("IsActive").HasColumnType("INTEGER");
			b.Property<DateTime?>("LastSignInUtc").HasColumnType("TEXT");
			b.Property<bool>("LockoutEnabled").HasColumnType("INTEGER");
			b.Property<DateTimeOffset?>("LockoutEnd").HasColumnType("TEXT");
			b.Property<string>("NormalizedEmail").HasMaxLength(256).HasColumnType("TEXT");
			b.Property<string>("NormalizedUserName").HasMaxLength(256).HasColumnType("TEXT");
			b.Property<string>("PasswordHash").HasColumnType("TEXT");
			b.Property<string>("PhoneNumber").HasColumnType("TEXT");
			b.Property<bool>("PhoneNumberConfirmed").HasColumnType("INTEGER");
			b.Property<string>("SecurityStamp").HasColumnType("TEXT");
			b.Property<bool>("TwoFactorEnabled").HasColumnType("INTEGER");
			b.Property<string>("UserName").HasMaxLength(256).HasColumnType("TEXT");
			b.HasKey("Id");
			b.HasIndex("NormalizedEmail").HasDatabaseName("EmailIndex");
			b.HasIndex("NormalizedUserName").IsUnique().HasDatabaseName("UserNameIndex");
			b.ToTable("AspNetUsers", (string?)null);
		});
		modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityRole", delegate(EntityTypeBuilder b)
		{
			b.Property<string>("Id").HasColumnType("TEXT");
			b.Property<string>("ConcurrencyStamp").IsConcurrencyToken().HasColumnType("TEXT");
			b.Property<string>("Name").HasMaxLength(256).HasColumnType("TEXT");
			b.Property<string>("NormalizedName").HasMaxLength(256).HasColumnType("TEXT");
			b.HasKey("Id");
			b.HasIndex("NormalizedName").IsUnique().HasDatabaseName("RoleNameIndex");
			b.ToTable("AspNetRoles", (string?)null);
		});
		modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityRoleClaim<string>", delegate(EntityTypeBuilder b)
		{
			b.Property<int>("Id").ValueGeneratedOnAdd().HasColumnType("INTEGER");
			b.Property<string>("ClaimType").HasColumnType("TEXT");
			b.Property<string>("ClaimValue").HasColumnType("TEXT");
			b.Property<string>("RoleId").IsRequired().HasColumnType("TEXT");
			b.HasKey("Id");
			b.HasIndex("RoleId");
			b.ToTable("AspNetRoleClaims", (string?)null);
		});
		modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityUserClaim<string>", delegate(EntityTypeBuilder b)
		{
			b.Property<int>("Id").ValueGeneratedOnAdd().HasColumnType("INTEGER");
			b.Property<string>("ClaimType").HasColumnType("TEXT");
			b.Property<string>("ClaimValue").HasColumnType("TEXT");
			b.Property<string>("UserId").IsRequired().HasColumnType("TEXT");
			b.HasKey("Id");
			b.HasIndex("UserId");
			b.ToTable("AspNetUserClaims", (string?)null);
		});
		modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityUserLogin<string>", delegate(EntityTypeBuilder b)
		{
			b.Property<string>("LoginProvider").HasColumnType("TEXT");
			b.Property<string>("ProviderKey").HasColumnType("TEXT");
			b.Property<string>("ProviderDisplayName").HasColumnType("TEXT");
			b.Property<string>("UserId").IsRequired().HasColumnType("TEXT");
			b.HasKey("LoginProvider", "ProviderKey");
			b.HasIndex("UserId");
			b.ToTable("AspNetUserLogins", (string?)null);
		});
		modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityUserRole<string>", delegate(EntityTypeBuilder b)
		{
			b.Property<string>("UserId").HasColumnType("TEXT");
			b.Property<string>("RoleId").HasColumnType("TEXT");
			b.HasKey("UserId", "RoleId");
			b.HasIndex("RoleId");
			b.ToTable("AspNetUserRoles", (string?)null);
		});
		modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityUserToken<string>", delegate(EntityTypeBuilder b)
		{
			b.Property<string>("UserId").HasColumnType("TEXT");
			b.Property<string>("LoginProvider").HasColumnType("TEXT");
			b.Property<string>("Name").HasColumnType("TEXT");
			b.Property<string>("Value").HasColumnType("TEXT");
			b.HasKey("UserId", "LoginProvider", "Name");
			b.ToTable("AspNetUserTokens", (string?)null);
		});
		modelBuilder.Entity("AssetPilot.Domain.Assets.AssetNetworkAddress", delegate(EntityTypeBuilder b)
		{
			b.HasOne("AssetPilot.Domain.Assets.Asset", "Asset").WithMany("NetworkAddresses").HasForeignKey("AssetId")
				.OnDelete(DeleteBehavior.Cascade)
				.IsRequired();
			b.Navigation("Asset");
		});
		modelBuilder.Entity("AssetPilot.Domain.Assets.AssetStatusHistory", delegate(EntityTypeBuilder b)
		{
			b.HasOne("AssetPilot.Domain.Assets.Asset", "Asset").WithMany("StatusHistory").HasForeignKey("AssetId")
				.OnDelete(DeleteBehavior.Cascade)
				.IsRequired();
			b.Navigation("Asset");
		});
		modelBuilder.Entity("AssetPilot.Domain.MasterData.ReferenceDataItem", delegate(EntityTypeBuilder b)
		{
			b.HasOne("AssetPilot.Domain.MasterData.ReferenceDataItem", "Parent").WithMany().HasForeignKey("ParentId")
				.OnDelete(DeleteBehavior.Restrict);
			b.Navigation("Parent");
		});
		modelBuilder.Entity("AssetPilot.Domain.People.AssetAssignment", delegate(EntityTypeBuilder b)
		{
			b.HasOne("AssetPilot.Domain.Assets.Asset", "Asset").WithMany("Assignments").HasForeignKey("AssetId")
				.OnDelete(DeleteBehavior.Restrict)
				.IsRequired();
			b.HasOne("AssetPilot.Domain.People.Employee", "Employee").WithMany("Assignments").HasForeignKey("EmployeeId")
				.OnDelete(DeleteBehavior.Restrict)
				.IsRequired();
			b.Navigation("Asset");
			b.Navigation("Employee");
		});
		modelBuilder.Entity("AssetPilot.Domain.Security.RolePermission", delegate(EntityTypeBuilder b)
		{
			b.HasOne("AssetPilot.Domain.Security.Permission", "Permission").WithMany().HasForeignKey("PermissionId")
				.OnDelete(DeleteBehavior.Restrict)
				.IsRequired();
			b.HasOne("Microsoft.AspNetCore.Identity.IdentityRole", null).WithMany().HasForeignKey("RoleId")
				.OnDelete(DeleteBehavior.Restrict)
				.IsRequired();
			b.Navigation("Permission");
		});
		modelBuilder.Entity("AssetPilot.Domain.Shipments.ShipmentItem", delegate(EntityTypeBuilder b)
		{
			b.HasOne("AssetPilot.Domain.Assets.Asset", "Asset").WithMany("ShipmentItems").HasForeignKey("AssetId")
				.OnDelete(DeleteBehavior.Restrict)
				.IsRequired();
			b.HasOne("AssetPilot.Domain.Shipments.Shipment", "Shipment").WithMany("Items").HasForeignKey("ShipmentId")
				.OnDelete(DeleteBehavior.Cascade)
				.IsRequired();
			b.Navigation("Asset");
			b.Navigation("Shipment");
		});
		modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityRoleClaim<string>", delegate(EntityTypeBuilder b)
		{
			b.HasOne("Microsoft.AspNetCore.Identity.IdentityRole", null).WithMany().HasForeignKey("RoleId")
				.OnDelete(DeleteBehavior.Cascade)
				.IsRequired();
		});
		modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityUserClaim<string>", delegate(EntityTypeBuilder b)
		{
			b.HasOne("AssetPilot.Infrastructure.Identity.ApplicationUser", null).WithMany().HasForeignKey("UserId")
				.OnDelete(DeleteBehavior.Cascade)
				.IsRequired();
		});
		modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityUserLogin<string>", delegate(EntityTypeBuilder b)
		{
			b.HasOne("AssetPilot.Infrastructure.Identity.ApplicationUser", null).WithMany().HasForeignKey("UserId")
				.OnDelete(DeleteBehavior.Cascade)
				.IsRequired();
		});
		modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityUserRole<string>", delegate(EntityTypeBuilder b)
		{
			b.HasOne("Microsoft.AspNetCore.Identity.IdentityRole", null).WithMany().HasForeignKey("RoleId")
				.OnDelete(DeleteBehavior.Cascade)
				.IsRequired();
			b.HasOne("AssetPilot.Infrastructure.Identity.ApplicationUser", null).WithMany().HasForeignKey("UserId")
				.OnDelete(DeleteBehavior.Cascade)
				.IsRequired();
		});
		modelBuilder.Entity("Microsoft.AspNetCore.Identity.IdentityUserToken<string>", delegate(EntityTypeBuilder b)
		{
			b.HasOne("AssetPilot.Infrastructure.Identity.ApplicationUser", null).WithMany().HasForeignKey("UserId")
				.OnDelete(DeleteBehavior.Cascade)
				.IsRequired();
		});
		modelBuilder.Entity("AssetPilot.Domain.Assets.Asset", delegate(EntityTypeBuilder b)
		{
			b.Navigation("Assignments");
			b.Navigation("NetworkAddresses");
			b.Navigation("ShipmentItems");
			b.Navigation("StatusHistory");
		});
		modelBuilder.Entity("AssetPilot.Domain.People.Employee", delegate(EntityTypeBuilder b)
		{
			b.Navigation("Assignments");
		});
		modelBuilder.Entity("AssetPilot.Domain.Shipments.Shipment", delegate(EntityTypeBuilder b)
		{
			b.Navigation("Items");
		});
	}
}
