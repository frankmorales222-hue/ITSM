using System;
using System.IO;
using System.Linq;
using System.Text.Json;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Assets;
using AssetPilot.Application.Auditing;
using AssetPilot.Application.Operations;
using AssetPilot.Application.Security;
using AssetPilot.Application.Shipments;
using AssetPilot.Domain.Assets;
using AssetPilot.Infrastructure.Assets;
using AssetPilot.Infrastructure.Auditing;
using AssetPilot.Infrastructure.Identity;
using AssetPilot.Infrastructure.Operations;
using AssetPilot.Infrastructure.Persistence;
using AssetPilot.Infrastructure.Security;
using AssetPilot.Infrastructure.Shipments;
using AssetPilot.Web.Services;
using Microsoft.AspNetCore.Authentication;
using Microsoft.AspNetCore.Authentication.Cookies;
using Microsoft.AspNetCore.Authorization;
using Microsoft.AspNetCore.Builder;
using Microsoft.AspNetCore.Http;
using Microsoft.AspNetCore.Identity;
using Microsoft.AspNetCore.HttpOverrides;
using Microsoft.AspNetCore.Mvc.RazorPages;
using Microsoft.Data.Sqlite;
using Microsoft.EntityFrameworkCore;
using Microsoft.EntityFrameworkCore.Diagnostics;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;

public class Program
{
	private sealed class BootstrapAdminCredentials
	{
		public string DisplayName { get; set; } = "";
		public string Email { get; set; } = "";
		public string Password { get; set; } = "";
	}

	private static async Task BootstrapAdministratorAsync(IServiceProvider services, IConfiguration configuration)
	{
		string? path = configuration["Bootstrap:AdminCredentialFile"];
		if (string.IsNullOrWhiteSpace(path) || !File.Exists(path))
		{
			return;
		}
		UserManager<ApplicationUser> userManager = services.GetRequiredService<UserManager<ApplicationUser>>();
		if (userManager.Users.Any())
		{
			File.Delete(path);
			return;
		}
		BootstrapAdminCredentials? credentials = JsonSerializer.Deserialize<BootstrapAdminCredentials>(
			await File.ReadAllTextAsync(path),
			new JsonSerializerOptions { PropertyNameCaseInsensitive = true });
		if (credentials is null || string.IsNullOrWhiteSpace(credentials.Email) ||
			string.IsNullOrWhiteSpace(credentials.Password))
		{
			throw new InvalidOperationException("AssetPilot administrator bootstrap credentials are invalid.");
		}
		ApplicationUser administrator = new ApplicationUser
		{
			UserName = credentials.Email.Trim(),
			Email = credentials.Email.Trim(),
			DisplayName = string.IsNullOrWhiteSpace(credentials.DisplayName)
				? "System Administrator" : credentials.DisplayName.Trim(),
			EmailConfirmed = true
		};
		IdentityResult created = await userManager.CreateAsync(administrator, credentials.Password);
		if (!created.Succeeded)
		{
			throw new InvalidOperationException(
				"AssetPilot administrator bootstrap failed: " +
				string.Join("; ", created.Errors.Select(error => error.Description)));
		}
		IdentityResult assigned = await userManager.AddToRoleAsync(administrator, "Administrator");
		if (!assigned.Succeeded)
		{
			await userManager.DeleteAsync(administrator);
			throw new InvalidOperationException(
				"AssetPilot administrator role assignment failed: " +
				string.Join("; ", assigned.Errors.Select(error => error.Description)));
		}
		File.Delete(path);
	}

	public static Task Main(string[] args)
	{
		return _003CMain_003E_0024(args);
	}

	private static async Task _003CMain_003E_0024(string[] args)
	{
		WebApplicationBuilder webApplicationBuilder = WebApplication.CreateBuilder(args);
		webApplicationBuilder.Services.AddRazorPages(delegate(RazorPagesOptions options)
		{
			options.Conventions.AuthorizeFolder("/");
			options.Conventions.AuthorizeFolder("/Assets", "Assets.View");
			options.Conventions.AuthorizeFolder("/Employees", "Employees.View");
			options.Conventions.AuthorizeFolder("/Shipments", "Shipments.View");
			options.Conventions.AuthorizeFolder("/Reports", "Reports.View");
			options.Conventions.AllowAnonymousToPage("/Account/Login");
			options.Conventions.AllowAnonymousToPage("/Account/SetPassword");
			options.Conventions.AllowAnonymousToPage("/Setup");
			options.Conventions.AllowAnonymousToPage("/Error");
		});
		webApplicationBuilder.Services.AddHealthChecks();
		webApplicationBuilder.Services.AddHttpClient();
		webApplicationBuilder.Services.AddSingleton<SqlitePragmaConnectionInterceptor>();
		webApplicationBuilder.Services.AddDbContext<AssetPilotDbContext>(delegate(IServiceProvider services, DbContextOptionsBuilder options)
		{
			IConfiguration requiredService2 = services.GetRequiredService<IConfiguration>();
			IHostEnvironment requiredService3 = services.GetRequiredService<IHostEnvironment>();
			string provider = requiredService2["Database:Provider"] ?? "Sqlite";
			if (string.Equals(provider, "PostgreSQL", StringComparison.OrdinalIgnoreCase) ||
				string.Equals(provider, "Postgres", StringComparison.OrdinalIgnoreCase))
			{
				string postgresConnection = requiredService2["Database:ConnectionString"] ??
					throw new InvalidOperationException("Database:ConnectionString is required for PostgreSQL.");
				options.UseNpgsql(postgresConnection, npgsql =>
					npgsql.MigrationsHistoryTable("__EFMigrationsHistory", requiredService2["Database:Schema"] ?? "assetpilot"));
				return;
			}
			string text = requiredService2["Database:Path"];
			string fullPath = Path.GetFullPath(Path.Combine(requiredService3.ContentRootPath, string.IsNullOrWhiteSpace(text) ? Path.Combine("App_Data", "assetpilot.db") : text));
			Directory.CreateDirectory(Path.GetDirectoryName(fullPath) ?? throw new InvalidOperationException("The configured database path has no parent directory."));
			string connectionString = new SqliteConnectionStringBuilder
			{
				DataSource = fullPath,
				Cache = SqliteCacheMode.Shared,
				ForeignKeys = true,
				DefaultTimeout = 5
			}.ToString();
			options
				.UseSqlite(connectionString)
				.ConfigureWarnings(warnings => warnings.Ignore(RelationalEventId.PendingModelChangesWarning))
				.AddInterceptors(services.GetRequiredService<SqlitePragmaConnectionInterceptor>());
		});
		webApplicationBuilder.Services.AddIdentity<ApplicationUser, IdentityRole>(delegate(IdentityOptions options)
		{
			options.Password.RequiredLength = 12;
			options.Lockout.MaxFailedAccessAttempts = 5;
			options.User.RequireUniqueEmail = true;
		}).AddEntityFrameworkStores<AssetPilotDbContext>().AddDefaultTokenProviders();
		webApplicationBuilder.Services.ConfigureApplicationCookie(delegate(CookieAuthenticationOptions options)
		{
			options.LoginPath = "/Account/Login";
			options.AccessDeniedPath = "/Account/AccessDenied";
			options.Events.OnRedirectToLogin = delegate(RedirectContext<CookieAuthenticationOptions> context)
			{
				if (context.Request.Path.StartsWithSegments("/api"))
				{
					context.Response.StatusCode = 401;
					return Task.CompletedTask;
				}
				context.Response.Redirect(context.RedirectUri);
				return Task.CompletedTask;
			};
			options.Events.OnRedirectToAccessDenied = delegate(RedirectContext<CookieAuthenticationOptions> context)
			{
				if (context.Request.Path.StartsWithSegments("/api"))
				{
					context.Response.StatusCode = 403;
					return Task.CompletedTask;
				}
				context.Response.Redirect(context.RedirectUri);
				return Task.CompletedTask;
			};
		});
		webApplicationBuilder.Services.AddAuthorization(delegate(AuthorizationOptions options)
		{
			foreach (string permissionKey in PermissionKeys.All)
			{
				options.AddPolicy(permissionKey, delegate(AuthorizationPolicyBuilder policy)
				{
					policy.RequireAuthenticatedUser().AddRequirements(new PermissionRequirement(permissionKey));
				});
			}
		});
		webApplicationBuilder.Services.AddScoped<IAuditService, AuditService>();
		webApplicationBuilder.Services.AddScoped<IAssetImportService, AssetImportService>();
		webApplicationBuilder.Services.AddScoped<IInventoryAuditExportService, InventoryAuditExportService>();
		webApplicationBuilder.Services.AddScoped<IShipmentTrackingService, CarrierShipmentTrackingService>();
		if (string.Equals(webApplicationBuilder.Configuration["Database:Provider"], "PostgreSQL", StringComparison.OrdinalIgnoreCase) ||
			string.Equals(webApplicationBuilder.Configuration["Database:Provider"], "Postgres", StringComparison.OrdinalIgnoreCase))
		{
			webApplicationBuilder.Services.AddScoped<IBackupService, PostgresBackupService>();
		}
		else
		{
			webApplicationBuilder.Services.AddScoped<IBackupService, SqliteBackupService>();
		}
		webApplicationBuilder.Services.AddScoped<IRolePermissionService, RolePermissionService>();
		webApplicationBuilder.Services.AddScoped<IUserInvitationEmailSender, UserInvitationEmailSender>();
		webApplicationBuilder.Services.AddScoped<IAuthorizationHandler, PermissionAuthorizationHandler>();
		webApplicationBuilder.Services.AddScoped<SecurityDataSeeder>();
		webApplicationBuilder.Services.AddScoped<PhaseOneDataSeeder>();
		webApplicationBuilder.Services.AddScoped<PhaseTwoDataSeeder>();
		WebApplication app = webApplicationBuilder.Build();
		if (app.Configuration.GetValue("Hosting:UseForwardedHeaders", defaultValue: false))
		{
			app.UseForwardedHeaders(new ForwardedHeadersOptions
			{
				ForwardedHeaders = ForwardedHeaders.XForwardedFor | ForwardedHeaders.XForwardedProto
			});
		}
		if (!app.Environment.IsDevelopment())
		{
			app.UseExceptionHandler("/Error");
			app.UseHsts();
		}
		if (app.Configuration.GetValue("Hosting:UseHttpsRedirection", defaultValue: false))
		{
			app.UseHttpsRedirection();
		}
		app.UseStaticFiles();
		app.UseRouting();
		app.Use(async delegate(HttpContext context, Func<Task> next)
		{
			if (context.Request.Path.StartsWithSegments("/health") || context.Request.Path.StartsWithSegments("/api") || context.Request.Path.StartsWithSegments("/css") || context.Request.Path.StartsWithSegments("/js") || context.Request.Path.StartsWithSegments("/Setup") || context.RequestServices.GetRequiredService<UserManager<ApplicationUser>>().Users.Any())
			{
				await next();
			}
			else
			{
				context.Response.Redirect("/Setup");
			}
		});
		app.UseAuthentication();
		app.UseAuthorization();
		app.MapGet("/health", async (AssetPilotDbContext db, CancellationToken cancellationToken) =>
			await db.Database.CanConnectAsync(cancellationToken)
				? Results.Ok(new { status = "Healthy", version = "3.7.0" })
				: Results.StatusCode(StatusCodes.Status503ServiceUnavailable))
			.AllowAnonymous();
		app.MapGet("/api/assets", (Func<AssetPilotDbContext, CancellationToken, Task<IResult>>)(async (AssetPilotDbContext db, CancellationToken cancellationToken) => Results.Ok(await (from asset in db.Assets
			where !asset.IsArchived
			orderby asset.AssetTag
			select new { asset.AssetId, asset.AssetTag, asset.Name, asset.Status }).ToListAsync(cancellationToken)))).RequireAuthorization("Assets.View");
		app.MapRazorPages();
		using (IServiceScope scope = app.Services.CreateScope())
		{
			await DatabaseBootstrapper.InitializeAsync(scope.ServiceProvider.GetRequiredService<AssetPilotDbContext>());
			await scope.ServiceProvider.GetRequiredService<SecurityDataSeeder>().SeedAsync();
			await BootstrapAdministratorAsync(scope.ServiceProvider, app.Configuration);
			if (app.Configuration.GetValue("Import:SeedExistingInventory", defaultValue: true))
			{
				string path = Path.Combine(app.Environment.ContentRootPath, "SeedData", "Asset inventory US.xlsx");
				if (File.Exists(path))
				{
					IAssetImportService requiredService = scope.ServiceProvider.GetRequiredService<IAssetImportService>();
					await using FileStream seedStream = File.OpenRead(path);
						try
						{
							await requiredService.ImportAsync(seedStream, Path.GetFileName(path), updateExisting: false, null, "startup-inventory-seed");
						}
						catch (Exception exception)
						{
							app.Logger.LogError(exception, "The optional bundled inventory seed could not be imported. AssetPilot will continue starting; use Bulk Import to review the workbook.");
						}
				}
			}
			await scope.ServiceProvider.GetRequiredService<PhaseOneDataSeeder>().SeedAsync();
			await scope.ServiceProvider.GetRequiredService<PhaseTwoDataSeeder>().SeedAsync();
		}
		app.Run();
	}
}

