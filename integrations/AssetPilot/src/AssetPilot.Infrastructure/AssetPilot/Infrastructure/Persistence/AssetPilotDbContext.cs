using System;
using System.Linq;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Domain.Assets;
using AssetPilot.Domain.Auditing;
using AssetPilot.Domain.MasterData;
using AssetPilot.Domain.Operations;
using AssetPilot.Domain.People;
using AssetPilot.Domain.Security;
using AssetPilot.Domain.Shipments;
using AssetPilot.Infrastructure.Identity;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.Identity.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.ChangeTracking;
using Microsoft.EntityFrameworkCore.Metadata.Builders;

namespace AssetPilot.Infrastructure.Persistence;

public sealed class AssetPilotDbContext : IdentityDbContext<ApplicationUser>
{
	public DbSet<Permission> Permissions => Set<Permission>();

	public DbSet<RolePermission> RolePermissions => Set<RolePermission>();

	public DbSet<AuditEvent> AuditEvents => Set<AuditEvent>();

	public DbSet<Asset> Assets => Set<Asset>();

	public DbSet<AssetImportReview> AssetImportReviews => Set<AssetImportReview>();

	public DbSet<AssetNetworkAddress> AssetNetworkAddresses => Set<AssetNetworkAddress>();

	public DbSet<AssetStatusHistory> AssetStatusHistory => Set<AssetStatusHistory>();

	public DbSet<ReferenceDataItem> ReferenceDataItems => Set<ReferenceDataItem>();

	public DbSet<Employee> Employees => Set<Employee>();

	public DbSet<AssetAssignment> AssetAssignments => Set<AssetAssignment>();

	public DbSet<Shipment> Shipments => Set<Shipment>();

	public DbSet<ShipmentItem> ShipmentItems => Set<ShipmentItem>();

	public DbSet<ShipmentTrackingEvent> ShipmentTrackingEvents => Set<ShipmentTrackingEvent>();

	public DbSet<SystemSetting> SystemSettings => Set<SystemSetting>();

	public DbSet<StockLevelTarget> StockLevelTargets => Set<StockLevelTarget>();

	public DbSet<OperationalJob> OperationalJobs => Set<OperationalJob>();

	public AssetPilotDbContext(DbContextOptions<AssetPilotDbContext> options)
		: base((DbContextOptions)options)
	{
	}

	protected override void OnModelCreating(ModelBuilder builder)
	{
		base.OnModelCreating(builder);
		if (Database.IsNpgsql())
		{
			builder.HasDefaultSchema("assetpilot");
			builder.HasPostgresExtension("citext");
		}
		builder.Entity(delegate(EntityTypeBuilder<Permission> entity)
		{
			entity.HasKey((Permission x) => x.PermissionId);
			entity.HasIndex((Permission x) => x.PermissionKey).IsUnique();
			entity.Property((Permission x) => x.PermissionKey).HasMaxLength(150);
			entity.Property((Permission x) => x.ModuleCode).HasMaxLength(50);
			entity.Property((Permission x) => x.Name).HasMaxLength(150);
			entity.Property((Permission x) => x.Version).IsConcurrencyToken();
		});
		builder.Entity(delegate(EntityTypeBuilder<RolePermission> entity)
		{
			entity.HasKey((RolePermission x) => new { x.RoleId, x.PermissionId });
			entity.HasOne<IdentityRole>().WithMany().HasForeignKey((RolePermission x) => x.RoleId)
				.OnDelete(DeleteBehavior.Restrict);
			entity.HasOne((RolePermission x) => x.Permission).WithMany().HasForeignKey((RolePermission x) => x.PermissionId)
				.OnDelete(DeleteBehavior.Restrict);
		});
		builder.Entity(delegate(EntityTypeBuilder<AuditEvent> entity)
		{
			entity.HasKey((AuditEvent x) => x.AuditEventId);
			entity.HasIndex((AuditEvent x) => new { x.EntityTypeCode, x.EntityId, x.EventUtc });
			entity.Property((AuditEvent x) => x.EventTypeCode).HasMaxLength(100);
			entity.Property((AuditEvent x) => x.EntityTypeCode).HasMaxLength(100);
			entity.Property((AuditEvent x) => x.EntityId).HasMaxLength(100);
			entity.Property((AuditEvent x) => x.CorrelationId).HasMaxLength(100);
		});
		builder.Entity(delegate(EntityTypeBuilder<Asset> entity)
		{
			entity.HasKey((Asset x) => x.AssetId);
			entity.HasIndex((Asset x) => x.AssetTag).IsUnique();
			entity.HasIndex((Asset x) => x.Hostname).IsUnique();
			entity.HasIndex((Asset x) => x.SerialNumber).IsUnique();
			entity.Property((Asset x) => x.AssetTag).HasMaxLength(80).UseCollation("NOCASE");
			entity.Property((Asset x) => x.Hostname).HasMaxLength(255).UseCollation("NOCASE");
			entity.Property((Asset x) => x.SerialNumber).HasMaxLength(160).UseCollation("NOCASE");
			entity.Property((Asset x) => x.Name).HasMaxLength(200);
			entity.Property((Asset x) => x.Status).HasMaxLength(50);
			entity.Property((Asset x) => x.Condition).HasMaxLength(50);
			entity.Property((Asset x) => x.Category).HasMaxLength(100);
			entity.Property((Asset x) => x.AssetType).HasMaxLength(100);
			entity.Property((Asset x) => x.Manufacturer).HasMaxLength(100);
			entity.Property((Asset x) => x.Model).HasMaxLength(150);
			entity.Property((Asset x) => x.AssignedTo).HasMaxLength(200);
			entity.Property((Asset x) => x.Department).HasMaxLength(150);
			entity.Property((Asset x) => x.Location).HasMaxLength(150);
			entity.Property((Asset x) => x.Vendor).HasMaxLength(150);
			entity.Property((Asset x) => x.Purpose).HasMaxLength(150);
			entity.Property((Asset x) => x.Company).HasMaxLength(150);
			entity.Property((Asset x) => x.Project).HasMaxLength(150);
			entity.Property((Asset x) => x.MacAddress).HasMaxLength(200);
			entity.Property((Asset x) => x.AssignedToEmail).HasMaxLength(255);
			entity.Property((Asset x) => x.SourceReference).HasMaxLength(255);
			entity.Property((Asset x) => x.DuplicateSerialNumber).HasMaxLength(160);
			entity.Property((Asset x) => x.Monitor1AssetTag).HasMaxLength(80);
			entity.Property((Asset x) => x.Monitor1SerialNumber).HasMaxLength(160);
			entity.Property((Asset x) => x.Monitor2AssetTag).HasMaxLength(80);
			entity.Property((Asset x) => x.Monitor2SerialNumber).HasMaxLength(160);
			entity.Property((Asset x) => x.Monitor3AssetTag).HasMaxLength(80);
			entity.Property((Asset x) => x.Monitor3SerialNumber).HasMaxLength(160);
			entity.Property((Asset x) => x.OfficeWorkMode).HasMaxLength(100);
			entity.Property((Asset x) => x.Workstation).HasMaxLength(150);
			entity.Property((Asset x) => x.CurrentLocation).HasMaxLength(150);
			entity.Property((Asset x) => x.EmployeeNumber).HasMaxLength(80);
			entity.Property((Asset x) => x.Designation).HasMaxLength(150);
			entity.Property((Asset x) => x.ServiceRequestTicket).HasMaxLength(150);
			entity.Property((Asset x) => x.SignedAllocationFormStatus).HasMaxLength(100);
			entity.Property((Asset x) => x.OldEmployeeNumber).HasMaxLength(80);
			entity.Property((Asset x) => x.OldUserName).HasMaxLength(200);
			entity.Property((Asset x) => x.OwnerName).HasMaxLength(200);
			entity.Property((Asset x) => x.OwnerEmail).HasMaxLength(255);
			entity.Property((Asset x) => x.Classification).HasMaxLength(150);
			entity.Property((Asset x) => x.Severity).HasMaxLength(150);
			entity.Property((Asset x) => x.Remarks).HasMaxLength(1000);
			entity.Property((Asset x) => x.NewReplacementStatus).HasMaxLength(100);
			entity.Property((Asset x) => x.DockingStation).HasMaxLength(200);
			entity.Property((Asset x) => x.Keyboard).HasMaxLength(200);
			entity.Property((Asset x) => x.Mouse).HasMaxLength(200);
			entity.Property((Asset x) => x.Headset).HasMaxLength(200);
			entity.Property((Asset x) => x.Printer).HasMaxLength(200);
			entity.Property((Asset x) => x.Version).IsConcurrencyToken();
		});
		builder.Entity(delegate(EntityTypeBuilder<AssetImportReview> entity)
		{
			entity.HasKey(x => x.AssetImportReviewId);
			entity.HasIndex(x => x.Fingerprint).IsUnique();
			entity.HasIndex(x => new { x.Status, x.CreatedUtc });
			entity.Property(x => x.Fingerprint).HasMaxLength(64);
			entity.Property(x => x.SourceFileName).HasMaxLength(255);
			entity.Property(x => x.MatchReason).HasMaxLength(500);
			entity.Property(x => x.Status).HasMaxLength(30);
			entity.Property(x => x.ResolvedByUserId).HasMaxLength(450);
			entity.Property(x => x.ResolutionNotes).HasMaxLength(1000);
			entity.Property(x => x.Version).IsConcurrencyToken();
			entity.HasOne(x => x.MatchingAsset)
				.WithMany()
				.HasForeignKey(x => x.MatchingAssetId)
				.OnDelete(DeleteBehavior.SetNull);
		});
		builder.Entity(delegate(EntityTypeBuilder<AssetNetworkAddress> entity)
		{
			entity.HasKey((AssetNetworkAddress x) => x.AssetNetworkAddressId);
			entity.HasIndex((AssetNetworkAddress x) => new { x.AssetId, x.AddressType, x.Address }).IsUnique();
			entity.Property((AssetNetworkAddress x) => x.AddressType).HasMaxLength(30);
			entity.Property((AssetNetworkAddress x) => x.Address).HasMaxLength(200).UseCollation("NOCASE");
			entity.Property((AssetNetworkAddress x) => x.Notes).HasMaxLength(500);
			entity.Property((AssetNetworkAddress x) => x.Version).IsConcurrencyToken();
			entity.HasOne((AssetNetworkAddress x) => x.Asset).WithMany((Asset x) => x.NetworkAddresses).HasForeignKey((AssetNetworkAddress x) => x.AssetId)
				.OnDelete(DeleteBehavior.Cascade);
		});
		builder.Entity(delegate(EntityTypeBuilder<AssetStatusHistory> entity)
		{
			entity.HasKey((AssetStatusHistory x) => x.AssetStatusHistoryId);
			entity.HasIndex((AssetStatusHistory x) => new { x.AssetId, x.ChangedUtc });
			entity.Property((AssetStatusHistory x) => x.FromStatus).HasMaxLength(50);
			entity.Property((AssetStatusHistory x) => x.ToStatus).HasMaxLength(50);
			entity.Property((AssetStatusHistory x) => x.ChangedByUserId).HasMaxLength(450);
			entity.Property((AssetStatusHistory x) => x.Reason).HasMaxLength(500);
			entity.HasOne((AssetStatusHistory x) => x.Asset).WithMany((Asset x) => x.StatusHistory).HasForeignKey((AssetStatusHistory x) => x.AssetId)
				.OnDelete(DeleteBehavior.Cascade);
		});
		builder.Entity(delegate(EntityTypeBuilder<ReferenceDataItem> entity)
		{
			entity.HasKey((ReferenceDataItem x) => x.ReferenceDataItemId);
			entity.HasIndex((ReferenceDataItem x) => new { x.Kind, x.Name }).IsUnique();
			entity.HasIndex((ReferenceDataItem x) => new { x.Kind, x.Code }).IsUnique();
			entity.Property((ReferenceDataItem x) => x.Kind).HasMaxLength(50).UseCollation("NOCASE");
			entity.Property((ReferenceDataItem x) => x.Name).HasMaxLength(150).UseCollation("NOCASE");
			entity.Property((ReferenceDataItem x) => x.Code).HasMaxLength(50).UseCollation("NOCASE");
			entity.Property((ReferenceDataItem x) => x.Notes).HasMaxLength(500);
			entity.Property((ReferenceDataItem x) => x.Version).IsConcurrencyToken();
			entity.HasOne((ReferenceDataItem x) => x.Parent).WithMany().HasForeignKey((ReferenceDataItem x) => x.ParentId)
				.OnDelete(DeleteBehavior.Restrict);
		});
		builder.Entity(delegate(EntityTypeBuilder<Employee> entity)
		{
			entity.HasKey((Employee x) => x.EmployeeId);
			entity.HasIndex((Employee x) => x.EmployeeNumber)
				.IsUnique()
				.HasFilter(Database.IsNpgsql() ? "\"IsDeleted\" = FALSE" : "\"IsDeleted\" = 0");
			entity.HasIndex((Employee x) => x.Email)
				.IsUnique()
				.HasFilter(Database.IsNpgsql() ? "\"IsDeleted\" = FALSE" : "\"IsDeleted\" = 0");
			entity.Property((Employee x) => x.EmployeeNumber).HasMaxLength(80).UseCollation("NOCASE");
			entity.Property((Employee x) => x.DisplayName).HasMaxLength(200);
			entity.Property((Employee x) => x.Email).HasMaxLength(255).UseCollation("NOCASE");
			entity.Property((Employee x) => x.Department).HasMaxLength(150);
			entity.Property((Employee x) => x.Manager).HasMaxLength(200);
			entity.Property((Employee x) => x.Location).HasMaxLength(150);
			entity.Property((Employee x) => x.Phone).HasMaxLength(50);
			entity.Property((Employee x) => x.Version).IsConcurrencyToken();
		});
		builder.Entity(delegate(EntityTypeBuilder<AssetAssignment> entity)
		{
			entity.HasKey((AssetAssignment x) => x.AssetAssignmentId);
			entity.HasIndex((AssetAssignment x) => new { x.AssetId, x.ReturnedUtc });
			entity.HasIndex((AssetAssignment x) => new { x.EmployeeId, x.ReturnedUtc });
			entity.Property((AssetAssignment x) => x.AssignedByUserId).HasMaxLength(450);
			entity.Property((AssetAssignment x) => x.ReturnedByUserId).HasMaxLength(450);
			entity.Property((AssetAssignment x) => x.AssignedLocation).HasMaxLength(150);
			entity.Property((AssetAssignment x) => x.Notes).HasMaxLength(500);
			entity.Property((AssetAssignment x) => x.ReturnCondition).HasMaxLength(50);
			entity.Property((AssetAssignment x) => x.ReturnNotes).HasMaxLength(500);
			entity.HasOne((AssetAssignment x) => x.Asset).WithMany((Asset x) => x.Assignments).HasForeignKey((AssetAssignment x) => x.AssetId)
				.OnDelete(DeleteBehavior.Restrict);
			entity.HasOne((AssetAssignment x) => x.Employee).WithMany((Employee x) => x.Assignments).HasForeignKey((AssetAssignment x) => x.EmployeeId)
				.OnDelete(DeleteBehavior.Restrict);
		});
		builder.Entity(delegate(EntityTypeBuilder<Shipment> entity)
		{
			entity.HasKey((Shipment x) => x.ShipmentId);
			entity.HasIndex((Shipment x) => x.ShipmentNumber).IsUnique();
			entity.HasIndex((Shipment x) => x.TrackingNumber);
			entity.Property((Shipment x) => x.ShipmentNumber).HasMaxLength(80).UseCollation("NOCASE");
			entity.Property((Shipment x) => x.Direction).HasMaxLength(30);
			entity.Property((Shipment x) => x.Status).HasMaxLength(50);
			entity.Property((Shipment x) => x.Carrier).HasMaxLength(100);
			entity.Property((Shipment x) => x.TrackingNumber).HasMaxLength(150).UseCollation("NOCASE");
			entity.Property((Shipment x) => x.Sender).HasMaxLength(200);
			entity.Property((Shipment x) => x.Recipient).HasMaxLength(200);
			entity.Property((Shipment x) => x.Origin).HasMaxLength(200);
			entity.Property((Shipment x) => x.Destination).HasMaxLength(200);
			entity.Property((Shipment x) => x.ReceivedByUserId).HasMaxLength(450);
			entity.Property((Shipment x) => x.Notes).HasMaxLength(1000);
			entity.Property((Shipment x) => x.TrackingLastMessage).HasMaxLength(1000);
			entity.Property((Shipment x) => x.TrackingUrl).HasMaxLength(500);
			entity.Property((Shipment x) => x.Version).IsConcurrencyToken();
		});
		builder.Entity(delegate(EntityTypeBuilder<ShipmentTrackingEvent> entity)
		{
			entity.HasKey((ShipmentTrackingEvent x) => x.ShipmentTrackingEventId);
			entity.HasIndex((ShipmentTrackingEvent x) => new { x.ShipmentId, x.EventUtc });
			entity.Property((ShipmentTrackingEvent x) => x.Status).HasMaxLength(100);
			entity.Property((ShipmentTrackingEvent x) => x.Description).HasMaxLength(1000);
			entity.Property((ShipmentTrackingEvent x) => x.Location).HasMaxLength(300);
			entity.Property((ShipmentTrackingEvent x) => x.Source).HasMaxLength(100);
			entity.HasOne((ShipmentTrackingEvent x) => x.Shipment)
				.WithMany((Shipment x) => x.TrackingEvents)
				.HasForeignKey((ShipmentTrackingEvent x) => x.ShipmentId)
				.OnDelete(DeleteBehavior.Cascade);
		});
		builder.Entity(delegate(EntityTypeBuilder<ShipmentItem> entity)
		{
			entity.HasKey((ShipmentItem x) => x.ShipmentItemId);
			entity.HasIndex((ShipmentItem x) => new { x.ShipmentId, x.AssetId }).IsUnique();
			entity.Property((ShipmentItem x) => x.ConditionAtDispatch).HasMaxLength(50);
			entity.Property((ShipmentItem x) => x.ConditionAtReceipt).HasMaxLength(50);
			entity.Property((ShipmentItem x) => x.Notes).HasMaxLength(500);
			entity.HasOne((ShipmentItem x) => x.Shipment).WithMany((Shipment x) => x.Items).HasForeignKey((ShipmentItem x) => x.ShipmentId)
				.OnDelete(DeleteBehavior.Cascade);
			entity.HasOne((ShipmentItem x) => x.Asset).WithMany((Asset x) => x.ShipmentItems).HasForeignKey((ShipmentItem x) => x.AssetId)
				.OnDelete(DeleteBehavior.Restrict);
		});
		builder.Entity(delegate(EntityTypeBuilder<SystemSetting> entity)
		{
			entity.HasKey((SystemSetting x) => x.SystemSettingId);
			entity.HasIndex((SystemSetting x) => x.SettingKey).IsUnique();
			entity.Property((SystemSetting x) => x.SettingKey).HasMaxLength(150).UseCollation("NOCASE");
			entity.Property((SystemSetting x) => x.Value);
			entity.Property((SystemSetting x) => x.Description).HasMaxLength(500);
			entity.Property((SystemSetting x) => x.Version).IsConcurrencyToken();
		});
		builder.Entity(delegate(EntityTypeBuilder<StockLevelTarget> entity)
		{
			entity.HasKey(x => x.StockLevelTargetId);
			entity.HasIndex(x => new { x.AssetType, x.Location }).IsUnique();
			entity.Property(x => x.AssetType).HasMaxLength(100).UseCollation("NOCASE");
			entity.Property(x => x.Location).HasMaxLength(150).UseCollation("NOCASE");
			entity.Property(x => x.Version).IsConcurrencyToken();
		});
		builder.Entity(delegate(EntityTypeBuilder<OperationalJob> entity)
		{
			entity.HasKey((OperationalJob x) => x.OperationalJobId);
			entity.HasIndex((OperationalJob x) => x.RequestedUtc);
			entity.Property((OperationalJob x) => x.JobType).HasMaxLength(100);
			entity.Property((OperationalJob x) => x.Status).HasMaxLength(30);
			entity.Property((OperationalJob x) => x.RequestedByUserId).HasMaxLength(450);
			entity.Property((OperationalJob x) => x.ResultSummary).HasMaxLength(1000);
			entity.Property((OperationalJob x) => x.CorrelationId).HasMaxLength(100);
		});

		if (Database.IsNpgsql())
		{
			foreach (var property in builder.Model.GetEntityTypes()
				.SelectMany(entity => entity.GetProperties())
				.Where(property => string.Equals(property.GetCollation(), "NOCASE", StringComparison.OrdinalIgnoreCase)))
			{
				property.SetCollation(null);
				property.SetColumnType("citext");
			}
		}
	}

	public override int SaveChanges(bool acceptAllChangesOnSuccess)
	{
		RejectAuditMutation();
		return base.SaveChanges(acceptAllChangesOnSuccess);
	}

	public override Task<int> SaveChangesAsync(bool acceptAllChangesOnSuccess, CancellationToken cancellationToken = default(CancellationToken))
	{
		RejectAuditMutation();
		return base.SaveChangesAsync(acceptAllChangesOnSuccess, cancellationToken);
	}

	private void RejectAuditMutation()
	{
		if (ChangeTracker.Entries<AuditEvent>().Any(delegate(EntityEntry<AuditEvent> entry)
		{
			EntityState state = entry.State;
			return (uint)(state - 2) <= 1u;
		}))
		{
			throw new InvalidOperationException("Audit events are append-only.");
		}
		if (ChangeTracker.Entries<AssetStatusHistory>().Any(delegate(EntityEntry<AssetStatusHistory> entry)
		{
			EntityState state = entry.State;
			return (uint)(state - 2) <= 1u;
		}))
		{
			throw new InvalidOperationException("Asset status history is append-only.");
		}
		if (ChangeTracker.Entries<ReferenceDataItem>().Any((EntityEntry<ReferenceDataItem> entry) => entry.State == EntityState.Deleted))
		{
			throw new InvalidOperationException("Master data cannot be deleted; deactivate it instead.");
		}
		if (ChangeTracker.Entries<AssetAssignment>().Any((EntityEntry<AssetAssignment> entry) => entry.State == EntityState.Deleted))
		{
			throw new InvalidOperationException("Assignment history cannot be deleted.");
		}
		if (ChangeTracker.Entries<OperationalJob>().Any((EntityEntry<OperationalJob> entry) => entry.State == EntityState.Deleted))
		{
			throw new InvalidOperationException("Operational job history cannot be deleted.");
		}
	}
}
