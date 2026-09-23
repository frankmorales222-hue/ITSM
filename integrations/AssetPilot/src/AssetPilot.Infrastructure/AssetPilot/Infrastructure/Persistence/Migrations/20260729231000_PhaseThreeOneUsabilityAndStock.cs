using System;
using AssetPilot.Infrastructure.Persistence;
using Microsoft.EntityFrameworkCore.Infrastructure;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AssetPilot.Infrastructure.AssetPilot.Infrastructure.Persistence.Migrations
{
    [DbContext(typeof(AssetPilotDbContext))]
    [Migration("20260729231000_PhaseThreeOneUsabilityAndStock")]
    public partial class PhaseThreeOneUsabilityAndStock : Migration
    {
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.CreateTable(
                name: "StockLevelTargets",
                columns: table => new
                {
                    StockLevelTargetId = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    AssetType = table.Column<string>(type: "TEXT", maxLength: 100, nullable: false, collation: "NOCASE"),
                    Location = table.Column<string>(type: "TEXT", maxLength: 150, nullable: false, collation: "NOCASE"),
                    TargetQuantity = table.Column<int>(type: "INTEGER", nullable: false),
                    ThresholdPercent = table.Column<int>(type: "INTEGER", nullable: false),
                    CreatedUtc = table.Column<DateTime>(type: "TEXT", nullable: false),
                    ModifiedUtc = table.Column<DateTime>(type: "TEXT", nullable: false),
                    Version = table.Column<int>(type: "INTEGER", nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_StockLevelTargets", x => x.StockLevelTargetId);
                });

            migrationBuilder.CreateIndex(
                name: "IX_StockLevelTargets_AssetType_Location",
                table: "StockLevelTargets",
                columns: new[] { "AssetType", "Location" },
                unique: true);
        }

        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(name: "StockLevelTargets");
        }
    }
}
