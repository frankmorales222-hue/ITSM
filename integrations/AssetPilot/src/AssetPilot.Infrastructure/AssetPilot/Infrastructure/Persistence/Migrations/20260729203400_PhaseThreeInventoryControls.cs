using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AssetPilot.Infrastructure.AssetPilot.Infrastructure.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class PhaseThreeInventoryControls : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropIndex(
                name: "IX_Employees_Email",
                table: "Employees");

            migrationBuilder.DropIndex(
                name: "IX_Employees_EmployeeNumber",
                table: "Employees");

            migrationBuilder.AddColumn<bool>(
                name: "IsDeleted",
                table: "Employees",
                type: "INTEGER",
                nullable: false,
                defaultValue: false);

            migrationBuilder.CreateTable(
                name: "AssetImportReviews",
                columns: table => new
                {
                    AssetImportReviewId = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    Fingerprint = table.Column<string>(type: "TEXT", maxLength: 64, nullable: false),
                    SourceFileName = table.Column<string>(type: "TEXT", maxLength: 255, nullable: false),
                    SourceRowNumber = table.Column<int>(type: "INTEGER", nullable: false),
                    MatchReason = table.Column<string>(type: "TEXT", maxLength: 500, nullable: false),
                    MatchingAssetId = table.Column<int>(type: "INTEGER", nullable: true),
                    RowValuesJson = table.Column<string>(type: "TEXT", nullable: false),
                    Status = table.Column<string>(type: "TEXT", maxLength: 30, nullable: false),
                    ResolvedUtc = table.Column<DateTime>(type: "TEXT", nullable: true),
                    ResolvedByUserId = table.Column<string>(type: "TEXT", maxLength: 450, nullable: true),
                    ResolutionNotes = table.Column<string>(type: "TEXT", maxLength: 1000, nullable: true),
                    CreatedUtc = table.Column<DateTime>(type: "TEXT", nullable: false),
                    ModifiedUtc = table.Column<DateTime>(type: "TEXT", nullable: false),
                    Version = table.Column<int>(type: "INTEGER", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_AssetImportReviews", x => x.AssetImportReviewId);
                    table.ForeignKey(
                        name: "FK_AssetImportReviews_Assets_MatchingAssetId",
                        column: x => x.MatchingAssetId,
                        principalTable: "Assets",
                        principalColumn: "AssetId",
                        onDelete: ReferentialAction.SetNull);
                });

            migrationBuilder.CreateIndex(
                name: "IX_Employees_Email",
                table: "Employees",
                column: "Email",
                unique: true,
                filter: "\"IsDeleted\" = 0");

            migrationBuilder.CreateIndex(
                name: "IX_Employees_EmployeeNumber",
                table: "Employees",
                column: "EmployeeNumber",
                unique: true,
                filter: "\"IsDeleted\" = 0");

            migrationBuilder.CreateIndex(
                name: "IX_AssetImportReviews_Fingerprint",
                table: "AssetImportReviews",
                column: "Fingerprint",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_AssetImportReviews_MatchingAssetId",
                table: "AssetImportReviews",
                column: "MatchingAssetId");

            migrationBuilder.CreateIndex(
                name: "IX_AssetImportReviews_Status_CreatedUtc",
                table: "AssetImportReviews",
                columns: new[] { "Status", "CreatedUtc" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "AssetImportReviews");

            migrationBuilder.DropIndex(
                name: "IX_Employees_Email",
                table: "Employees");

            migrationBuilder.DropIndex(
                name: "IX_Employees_EmployeeNumber",
                table: "Employees");

            migrationBuilder.DropColumn(
                name: "IsDeleted",
                table: "Employees");

            migrationBuilder.CreateIndex(
                name: "IX_Employees_Email",
                table: "Employees",
                column: "Email",
                unique: true);

            migrationBuilder.CreateIndex(
                name: "IX_Employees_EmployeeNumber",
                table: "Employees",
                column: "EmployeeNumber",
                unique: true);
        }
    }
}
