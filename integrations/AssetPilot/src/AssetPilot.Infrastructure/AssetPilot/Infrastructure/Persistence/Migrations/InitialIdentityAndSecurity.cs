using System;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using Microsoft.EntityFrameworkCore.Migrations;
using Microsoft.EntityFrameworkCore.Migrations.Operations;
using Microsoft.EntityFrameworkCore.Migrations.Operations.Builders;

namespace AssetPilot.Infrastructure.Persistence.Migrations;

[DbContext(typeof(AssetPilotDbContext))]
[Migration("20260729023609_InitialIdentityAndSecurity")]
public class InitialIdentityAndSecurity : Migration
{
	protected override void Up(MigrationBuilder migrationBuilder)
	{
		migrationBuilder.CreateTable("AspNetRoles", delegate(ColumnsBuilder table)
		{
			OperationBuilder<AddColumnOperation> id = table.Column<string>("TEXT");
			int? maxLength = 256;
			OperationBuilder<AddColumnOperation> name = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 256;
			return new
			{
				Id = id,
				Name = name,
				NormalizedName = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true),
				ConcurrencyStamp = table.Column<string>("TEXT", null, null, rowVersion: false, null, nullable: true)
			};
		}, null, table =>
		{
			table.PrimaryKey("PK_AspNetRoles", x => x.Id);
		});
		migrationBuilder.CreateTable("AspNetUsers", delegate(ColumnsBuilder table)
		{
			OperationBuilder<AddColumnOperation> id = table.Column<string>("TEXT");
			OperationBuilder<AddColumnOperation> displayName = table.Column<string>("TEXT");
			OperationBuilder<AddColumnOperation> isActive = table.Column<bool>("INTEGER");
			OperationBuilder<AddColumnOperation> lastSignInUtc = table.Column<DateTime>("TEXT", null, null, rowVersion: false, null, nullable: true);
			int? maxLength = 256;
			OperationBuilder<AddColumnOperation> userName = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 256;
			OperationBuilder<AddColumnOperation> normalizedUserName = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 256;
			OperationBuilder<AddColumnOperation> email = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true);
			maxLength = 256;
			return new
			{
				Id = id,
				DisplayName = displayName,
				IsActive = isActive,
				LastSignInUtc = lastSignInUtc,
				UserName = userName,
				NormalizedUserName = normalizedUserName,
				Email = email,
				NormalizedEmail = table.Column<string>("TEXT", null, maxLength, rowVersion: false, null, nullable: true),
				EmailConfirmed = table.Column<bool>("INTEGER"),
				PasswordHash = table.Column<string>("TEXT", null, null, rowVersion: false, null, nullable: true),
				SecurityStamp = table.Column<string>("TEXT", null, null, rowVersion: false, null, nullable: true),
				ConcurrencyStamp = table.Column<string>("TEXT", null, null, rowVersion: false, null, nullable: true),
				PhoneNumber = table.Column<string>("TEXT", null, null, rowVersion: false, null, nullable: true),
				PhoneNumberConfirmed = table.Column<bool>("INTEGER"),
				TwoFactorEnabled = table.Column<bool>("INTEGER"),
				LockoutEnd = table.Column<DateTimeOffset>("TEXT", null, null, rowVersion: false, null, nullable: true),
				LockoutEnabled = table.Column<bool>("INTEGER"),
				AccessFailedCount = table.Column<int>("INTEGER")
			};
		}, null, table =>
		{
			table.PrimaryKey("PK_AspNetUsers", x => x.Id);
		});
		migrationBuilder.CreateTable("AuditEvents", delegate(ColumnsBuilder table)
		{
			OperationBuilder<AddColumnOperation> auditEventId = table.Column<long>("INTEGER").Annotation("Sqlite:Autoincrement", true);
			int? maxLength = 100;
			OperationBuilder<AddColumnOperation> eventTypeCode = table.Column<string>("TEXT", null, maxLength);
			maxLength = 100;
			OperationBuilder<AddColumnOperation> entityTypeCode = table.Column<string>("TEXT", null, maxLength);
			maxLength = 100;
			OperationBuilder<AddColumnOperation> entityId = table.Column<string>("TEXT", null, maxLength);
			OperationBuilder<AddColumnOperation> userId = table.Column<string>("TEXT", null, null, rowVersion: false, null, nullable: true);
			OperationBuilder<AddColumnOperation> eventUtc = table.Column<DateTime>("TEXT");
			OperationBuilder<AddColumnOperation> beforeJson = table.Column<string>("TEXT", null, null, rowVersion: false, null, nullable: true);
			OperationBuilder<AddColumnOperation> afterJson = table.Column<string>("TEXT", null, null, rowVersion: false, null, nullable: true);
			OperationBuilder<AddColumnOperation> reason = table.Column<string>("TEXT", null, null, rowVersion: false, null, nullable: true);
			maxLength = 100;
			return new
			{
				AuditEventId = auditEventId,
				EventTypeCode = eventTypeCode,
				EntityTypeCode = entityTypeCode,
				EntityId = entityId,
				UserId = userId,
				EventUtc = eventUtc,
				BeforeJson = beforeJson,
				AfterJson = afterJson,
				Reason = reason,
				CorrelationId = table.Column<string>("TEXT", null, maxLength)
			};
		}, null, table =>
		{
			table.PrimaryKey("PK_AuditEvents", x => x.AuditEventId);
		});
		migrationBuilder.CreateTable("Permissions", delegate(ColumnsBuilder table)
		{
			OperationBuilder<AddColumnOperation> permissionId = table.Column<int>("INTEGER").Annotation("Sqlite:Autoincrement", true);
			int? maxLength = 150;
			OperationBuilder<AddColumnOperation> permissionKey = table.Column<string>("TEXT", null, maxLength);
			maxLength = 50;
			OperationBuilder<AddColumnOperation> moduleCode = table.Column<string>("TEXT", null, maxLength);
			maxLength = 150;
			return new
			{
				PermissionId = permissionId,
				PermissionKey = permissionKey,
				ModuleCode = moduleCode,
				Name = table.Column<string>("TEXT", null, maxLength),
				Description = table.Column<string>("TEXT", null, null, rowVersion: false, null, nullable: true),
				IsSensitive = table.Column<bool>("INTEGER"),
				CreatedUtc = table.Column<DateTime>("TEXT"),
				ModifiedUtc = table.Column<DateTime>("TEXT"),
				Version = table.Column<int>("INTEGER")
			};
		}, null, table =>
		{
			table.PrimaryKey("PK_Permissions", x => x.PermissionId);
		});
		migrationBuilder.CreateTable("AspNetRoleClaims", (ColumnsBuilder table) => new
		{
			Id = table.Column<int>("INTEGER").Annotation("Sqlite:Autoincrement", true),
			RoleId = table.Column<string>("TEXT"),
			ClaimType = table.Column<string>("TEXT", null, null, rowVersion: false, null, nullable: true),
			ClaimValue = table.Column<string>("TEXT", null, null, rowVersion: false, null, nullable: true)
		}, null, table =>
		{
			table.PrimaryKey("PK_AspNetRoleClaims", x => x.Id);
			table.ForeignKey("FK_AspNetRoleClaims_AspNetRoles_RoleId", x => x.RoleId, "AspNetRoles", "Id", null, ReferentialAction.NoAction, ReferentialAction.Cascade);
		});
		migrationBuilder.CreateTable("AspNetUserClaims", (ColumnsBuilder table) => new
		{
			Id = table.Column<int>("INTEGER").Annotation("Sqlite:Autoincrement", true),
			UserId = table.Column<string>("TEXT"),
			ClaimType = table.Column<string>("TEXT", null, null, rowVersion: false, null, nullable: true),
			ClaimValue = table.Column<string>("TEXT", null, null, rowVersion: false, null, nullable: true)
		}, null, table =>
		{
			table.PrimaryKey("PK_AspNetUserClaims", x => x.Id);
			table.ForeignKey("FK_AspNetUserClaims_AspNetUsers_UserId", x => x.UserId, "AspNetUsers", "Id", null, ReferentialAction.NoAction, ReferentialAction.Cascade);
		});
		migrationBuilder.CreateTable("AspNetUserLogins", (ColumnsBuilder table) => new
		{
			LoginProvider = table.Column<string>("TEXT"),
			ProviderKey = table.Column<string>("TEXT"),
			ProviderDisplayName = table.Column<string>("TEXT", null, null, rowVersion: false, null, nullable: true),
			UserId = table.Column<string>("TEXT")
		}, null, table =>
		{
			table.PrimaryKey("PK_AspNetUserLogins", x => new { x.LoginProvider, x.ProviderKey });
			table.ForeignKey("FK_AspNetUserLogins_AspNetUsers_UserId", x => x.UserId, "AspNetUsers", "Id", null, ReferentialAction.NoAction, ReferentialAction.Cascade);
		});
		migrationBuilder.CreateTable("AspNetUserRoles", (ColumnsBuilder table) => new
		{
			UserId = table.Column<string>("TEXT"),
			RoleId = table.Column<string>("TEXT")
		}, null, table =>
		{
			table.PrimaryKey("PK_AspNetUserRoles", x => new { x.UserId, x.RoleId });
			table.ForeignKey("FK_AspNetUserRoles_AspNetRoles_RoleId", x => x.RoleId, "AspNetRoles", "Id", null, ReferentialAction.NoAction, ReferentialAction.Cascade);
			table.ForeignKey("FK_AspNetUserRoles_AspNetUsers_UserId", x => x.UserId, "AspNetUsers", "Id", null, ReferentialAction.NoAction, ReferentialAction.Cascade);
		});
		migrationBuilder.CreateTable("AspNetUserTokens", (ColumnsBuilder table) => new
		{
			UserId = table.Column<string>("TEXT"),
			LoginProvider = table.Column<string>("TEXT"),
			Name = table.Column<string>("TEXT"),
			Value = table.Column<string>("TEXT", null, null, rowVersion: false, null, nullable: true)
		}, null, table =>
		{
			table.PrimaryKey("PK_AspNetUserTokens", x => new { x.UserId, x.LoginProvider, x.Name });
			table.ForeignKey("FK_AspNetUserTokens_AspNetUsers_UserId", x => x.UserId, "AspNetUsers", "Id", null, ReferentialAction.NoAction, ReferentialAction.Cascade);
		});
		migrationBuilder.CreateTable("RolePermissions", (ColumnsBuilder table) => new
		{
			RoleId = table.Column<string>("TEXT"),
			PermissionId = table.Column<int>("INTEGER"),
			IsAllowed = table.Column<bool>("INTEGER")
		}, null, table =>
		{
			table.PrimaryKey("PK_RolePermissions", x => new { x.RoleId, x.PermissionId });
			table.ForeignKey("FK_RolePermissions_AspNetRoles_RoleId", x => x.RoleId, "AspNetRoles", "Id", null, ReferentialAction.NoAction, ReferentialAction.Restrict);
			table.ForeignKey("FK_RolePermissions_Permissions_PermissionId", x => x.PermissionId, "Permissions", "PermissionId", null, ReferentialAction.NoAction, ReferentialAction.Restrict);
		});
		migrationBuilder.CreateIndex("IX_AspNetRoleClaims_RoleId", "AspNetRoleClaims", "RoleId");
		migrationBuilder.CreateIndex("RoleNameIndex", "AspNetRoles", "NormalizedName", null, unique: true);
		migrationBuilder.CreateIndex("IX_AspNetUserClaims_UserId", "AspNetUserClaims", "UserId");
		migrationBuilder.CreateIndex("IX_AspNetUserLogins_UserId", "AspNetUserLogins", "UserId");
		migrationBuilder.CreateIndex("IX_AspNetUserRoles_RoleId", "AspNetUserRoles", "RoleId");
		migrationBuilder.CreateIndex("EmailIndex", "AspNetUsers", "NormalizedEmail");
		migrationBuilder.CreateIndex("UserNameIndex", "AspNetUsers", "NormalizedUserName", null, unique: true);
		migrationBuilder.CreateIndex("IX_AuditEvents_EntityTypeCode_EntityId_EventUtc", "AuditEvents", new string[3] { "EntityTypeCode", "EntityId", "EventUtc" });
		migrationBuilder.CreateIndex("IX_Permissions_PermissionKey", "Permissions", "PermissionKey", null, unique: true);
		migrationBuilder.CreateIndex("IX_RolePermissions_PermissionId", "RolePermissions", "PermissionId");
	}

	protected override void Down(MigrationBuilder migrationBuilder)
	{
		migrationBuilder.DropTable("AspNetRoleClaims");
		migrationBuilder.DropTable("AspNetUserClaims");
		migrationBuilder.DropTable("AspNetUserLogins");
		migrationBuilder.DropTable("AspNetUserRoles");
		migrationBuilder.DropTable("AspNetUserTokens");
		migrationBuilder.DropTable("AuditEvents");
		migrationBuilder.DropTable("RolePermissions");
		migrationBuilder.DropTable("AspNetUsers");
		migrationBuilder.DropTable("AspNetRoles");
		migrationBuilder.DropTable("Permissions");
	}

	protected override void BuildTargetModel(ModelBuilder modelBuilder)
	{
		modelBuilder.HasAnnotation("ProductVersion", "10.0.10");
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
	}
}
