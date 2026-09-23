using System;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Metadata.Builders;
using Microsoft.EntityFrameworkCore.Migrations;

namespace AssetPilot.Infrastructure.Persistence.Migrations;

[DbContext(typeof(AssetPilotDbContext))]
[Migration("20260729135052_AssetImportMetadata")]
public class AssetImportMetadata : Migration
{
	protected override void Up(MigrationBuilder migrationBuilder)
	{
		int? maxLength = 160;
		Type typeFromHandle = typeof(string);
		int? oldMaxLength = 160;
		migrationBuilder.AlterColumn<string>("SerialNumber", "Assets", "TEXT", null, maxLength, rowVersion: false, null, nullable: true, null, null, null, typeFromHandle, "TEXT", null, oldMaxLength, oldRowVersion: false, oldNullable: true, null, null, null, null, null, null, null, "NOCASE");
		oldMaxLength = 255;
		typeFromHandle = typeof(string);
		maxLength = 255;
		migrationBuilder.AlterColumn<string>("Hostname", "Assets", "TEXT", null, oldMaxLength, rowVersion: false, null, nullable: true, null, null, null, typeFromHandle, "TEXT", null, maxLength, oldRowVersion: false, oldNullable: true, null, null, null, null, null, null, null, "NOCASE");
		maxLength = 80;
		typeFromHandle = typeof(string);
		oldMaxLength = 80;
		migrationBuilder.AlterColumn<string>("AssetTag", "Assets", "TEXT", null, maxLength, rowVersion: false, null, nullable: false, null, null, null, typeFromHandle, "TEXT", null, oldMaxLength, oldRowVersion: false, oldNullable: false, null, null, null, null, null, null, null, "NOCASE");
		oldMaxLength = 255;
		migrationBuilder.AddColumn<string>("AssignedToEmail", "Assets", "TEXT", null, oldMaxLength, rowVersion: false, null, nullable: true);
		oldMaxLength = 150;
		migrationBuilder.AddColumn<string>("Company", "Assets", "TEXT", null, oldMaxLength, rowVersion: false, null, nullable: true);
		oldMaxLength = 200;
		migrationBuilder.AddColumn<string>("MacAddress", "Assets", "TEXT", null, oldMaxLength, rowVersion: false, null, nullable: true);
		oldMaxLength = 150;
		migrationBuilder.AddColumn<string>("Project", "Assets", "TEXT", null, oldMaxLength, rowVersion: false, null, nullable: true);
		oldMaxLength = 255;
		migrationBuilder.AddColumn<string>("SourceReference", "Assets", "TEXT", null, oldMaxLength, rowVersion: false, null, nullable: true);
	}

	protected override void Down(MigrationBuilder migrationBuilder)
	{
		migrationBuilder.DropColumn("AssignedToEmail", "Assets");
		migrationBuilder.DropColumn("Company", "Assets");
		migrationBuilder.DropColumn("MacAddress", "Assets");
		migrationBuilder.DropColumn("Project", "Assets");
		migrationBuilder.DropColumn("SourceReference", "Assets");
		int? maxLength = 160;
		Type typeFromHandle = typeof(string);
		int? oldMaxLength = 160;
		migrationBuilder.AlterColumn<string>("SerialNumber", "Assets", "TEXT", null, maxLength, rowVersion: false, null, nullable: true, null, null, null, typeFromHandle, "TEXT", null, oldMaxLength, oldRowVersion: false, oldNullable: true, null, null, null, null, null, null, null, null, "NOCASE");
		oldMaxLength = 255;
		typeFromHandle = typeof(string);
		maxLength = 255;
		migrationBuilder.AlterColumn<string>("Hostname", "Assets", "TEXT", null, oldMaxLength, rowVersion: false, null, nullable: true, null, null, null, typeFromHandle, "TEXT", null, maxLength, oldRowVersion: false, oldNullable: true, null, null, null, null, null, null, null, null, "NOCASE");
		maxLength = 80;
		typeFromHandle = typeof(string);
		oldMaxLength = 80;
		migrationBuilder.AlterColumn<string>("AssetTag", "Assets", "TEXT", null, maxLength, rowVersion: false, null, nullable: false, null, null, null, typeFromHandle, "TEXT", null, oldMaxLength, oldRowVersion: false, oldNullable: false, null, null, null, null, null, null, null, null, "NOCASE");
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
