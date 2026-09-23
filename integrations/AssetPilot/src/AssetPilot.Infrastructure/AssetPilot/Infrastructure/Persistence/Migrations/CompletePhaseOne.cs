using System;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using Microsoft.EntityFrameworkCore.Migrations;
using Microsoft.EntityFrameworkCore.Migrations.Operations;
using Microsoft.EntityFrameworkCore.Migrations.Operations.Builders;

namespace AssetPilot.Infrastructure.Persistence.Migrations;

[DbContext(typeof(AssetPilotDbContext))]
[Migration("20260729160658_CompletePhaseOne")]
public class CompletePhaseOne : Migration
{
	protected override void Up(MigrationBuilder migrationBuilder)
	{
		migrationBuilder.CreateTable("AssetNetworkAddresses", delegate(ColumnsBuilder table)
		{
			OperationBuilder<AddColumnOperation> assetNetworkAddressId = table.Column<int>("INTEGER").Annotation("Sqlite:Autoincrement", true);
			OperationBuilder<AddColumnOperation> assetId = table.Column<int>("INTEGER");
			int? maxLength = 30;
			OperationBuilder<AddColumnOperation> addressType = table.Column<string>("TEXT", null, maxLength);
			maxLength = 200;
			OperationBuilder<AddColumnOperation> address = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: false, null, null, null, null, null, "NOCASE");
			OperationBuilder<AddColumnOperation> isPrimary = table.Column<bool>("INTEGER");
			maxLength = 500;
			return new
			{
				AssetNetworkAddressId = assetNetworkAddressId,
				AssetId = assetId,
				AddressType = addressType,
				Address = address,
				IsPrimary = isPrimary,
				Notes = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true),
				CreatedUtc = table.Column<DateTime>("TEXT"),
				ModifiedUtc = table.Column<DateTime>("TEXT"),
				Version = table.Column<int>("INTEGER")
			};
		}, null, table =>
		{
			table.PrimaryKey("PK_AssetNetworkAddresses", x => x.AssetNetworkAddressId);
			table.ForeignKey("FK_AssetNetworkAddresses_Assets_AssetId", x => x.AssetId, "Assets", "AssetId", null, ReferentialAction.NoAction, ReferentialAction.Cascade);
		});
		migrationBuilder.CreateTable("AssetStatusHistory", delegate(ColumnsBuilder table)
		{
			OperationBuilder<AddColumnOperation> assetStatusHistoryId = table.Column<long>("INTEGER").Annotation("Sqlite:Autoincrement", true);
			OperationBuilder<AddColumnOperation> assetId = table.Column<int>("INTEGER");
			int? maxLength = 50;
			OperationBuilder<AddColumnOperation> fromStatus = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 50;
			OperationBuilder<AddColumnOperation> toStatus = table.Column<string>("TEXT", null, maxLength);
			OperationBuilder<AddColumnOperation> changedUtc = table.Column<DateTime>("TEXT");
			maxLength = 450;
			OperationBuilder<AddColumnOperation> changedByUserId = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 500;
			return new
			{
				AssetStatusHistoryId = assetStatusHistoryId,
				AssetId = assetId,
				FromStatus = fromStatus,
				ToStatus = toStatus,
				ChangedUtc = changedUtc,
				ChangedByUserId = changedByUserId,
				Reason = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true)
			};
		}, null, table =>
		{
			table.PrimaryKey("PK_AssetStatusHistory", x => x.AssetStatusHistoryId);
			table.ForeignKey("FK_AssetStatusHistory_Assets_AssetId", x => x.AssetId, "Assets", "AssetId", null, ReferentialAction.NoAction, ReferentialAction.Cascade);
		});
		migrationBuilder.CreateTable("ReferenceDataItems", delegate(ColumnsBuilder table)
		{
			OperationBuilder<AddColumnOperation> referenceDataItemId = table.Column<int>("INTEGER").Annotation("Sqlite:Autoincrement", true);
			int? maxLength = 50;
			OperationBuilder<AddColumnOperation> kind = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: false, null, null, null, null, null, "NOCASE");
			maxLength = 150;
			OperationBuilder<AddColumnOperation> name = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: false, null, null, null, null, null, "NOCASE");
			maxLength = 50;
			OperationBuilder<AddColumnOperation> code = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true, null, null, null, null, null, "NOCASE");
			maxLength = 500;
			return new
			{
				ReferenceDataItemId = referenceDataItemId,
				Kind = kind,
				Name = name,
				Code = code,
				Notes = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true),
				IsActive = table.Column<bool>("INTEGER"),
				ParentId = table.Column<int>("INTEGER", null, null, rowVersion: false, null, nullable: true),
				CreatedUtc = table.Column<DateTime>("TEXT"),
				ModifiedUtc = table.Column<DateTime>("TEXT"),
				Version = table.Column<int>("INTEGER")
			};
		}, null, table =>
		{
			table.PrimaryKey("PK_ReferenceDataItems", x => x.ReferenceDataItemId);
			table.ForeignKey("FK_ReferenceDataItems_ReferenceDataItems_ParentId", x => x.ParentId, "ReferenceDataItems", "ReferenceDataItemId", null, ReferentialAction.NoAction, ReferentialAction.Restrict);
		});
		migrationBuilder.CreateIndex("IX_AssetNetworkAddresses_AssetId_AddressType_Address", "AssetNetworkAddresses", new string[3] { "AssetId", "AddressType", "Address" }, null, unique: true);
		migrationBuilder.CreateIndex("IX_AssetStatusHistory_AssetId_ChangedUtc", "AssetStatusHistory", new string[2] { "AssetId", "ChangedUtc" });
		migrationBuilder.CreateIndex("IX_ReferenceDataItems_Kind_Code", "ReferenceDataItems", new string[2] { "Kind", "Code" }, null, unique: true);
		migrationBuilder.CreateIndex("IX_ReferenceDataItems_Kind_Name", "ReferenceDataItems", new string[2] { "Kind", "Name" }, null, unique: true);
		migrationBuilder.CreateIndex("IX_ReferenceDataItems_ParentId", "ReferenceDataItems", "ParentId");
	}

	protected override void Down(MigrationBuilder migrationBuilder)
	{
		migrationBuilder.DropTable("AssetNetworkAddresses");
		migrationBuilder.DropTable("AssetStatusHistory");
		migrationBuilder.DropTable("ReferenceDataItems");
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
			b.Navigation("NetworkAddresses");
			b.Navigation("StatusHistory");
		});
	}
}
