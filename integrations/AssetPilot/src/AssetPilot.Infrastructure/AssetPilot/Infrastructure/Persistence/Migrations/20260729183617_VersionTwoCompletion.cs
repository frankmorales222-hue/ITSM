using System;
using Microsoft.EntityFrameworkCore.Migrations;

#nullable disable

namespace AssetPilot.Infrastructure.AssetPilot.Infrastructure.Persistence.Migrations
{
    /// <inheritdoc />
    public partial class VersionTwoCompletion : Migration
    {
        /// <inheritdoc />
        protected override void Up(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.AddColumn<DateTime>(
                name: "TrackingLastCheckedUtc",
                table: "Shipments",
                type: "TEXT",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "TrackingLastMessage",
                table: "Shipments",
                type: "TEXT",
                maxLength: 1000,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "TrackingUrl",
                table: "Shipments",
                type: "TEXT",
                maxLength: 500,
                nullable: true);

            migrationBuilder.AddColumn<DateOnly>(
                name: "AllocationDate",
                table: "Assets",
                type: "TEXT",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Classification",
                table: "Assets",
                type: "TEXT",
                maxLength: 150,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "CurrentLocation",
                table: "Assets",
                type: "TEXT",
                maxLength: 150,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Designation",
                table: "Assets",
                type: "TEXT",
                maxLength: 150,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "DockingStation",
                table: "Assets",
                type: "TEXT",
                maxLength: 200,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "DuplicateSerialNumber",
                table: "Assets",
                type: "TEXT",
                maxLength: 160,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "EmployeeNumber",
                table: "Assets",
                type: "TEXT",
                maxLength: 80,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Headset",
                table: "Assets",
                type: "TEXT",
                maxLength: 200,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Keyboard",
                table: "Assets",
                type: "TEXT",
                maxLength: 200,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Monitor1AssetTag",
                table: "Assets",
                type: "TEXT",
                maxLength: 80,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Monitor1SerialNumber",
                table: "Assets",
                type: "TEXT",
                maxLength: 160,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Monitor2AssetTag",
                table: "Assets",
                type: "TEXT",
                maxLength: 80,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Monitor2SerialNumber",
                table: "Assets",
                type: "TEXT",
                maxLength: 160,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Monitor3AssetTag",
                table: "Assets",
                type: "TEXT",
                maxLength: 80,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Monitor3SerialNumber",
                table: "Assets",
                type: "TEXT",
                maxLength: 160,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Mouse",
                table: "Assets",
                type: "TEXT",
                maxLength: 200,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "NewReplacementStatus",
                table: "Assets",
                type: "TEXT",
                maxLength: 100,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "OfficeWorkMode",
                table: "Assets",
                type: "TEXT",
                maxLength: 100,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "OldEmployeeNumber",
                table: "Assets",
                type: "TEXT",
                maxLength: 80,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "OldUserName",
                table: "Assets",
                type: "TEXT",
                maxLength: 200,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "OwnerEmail",
                table: "Assets",
                type: "TEXT",
                maxLength: 255,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "OwnerName",
                table: "Assets",
                type: "TEXT",
                maxLength: 200,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Printer",
                table: "Assets",
                type: "TEXT",
                maxLength: 200,
                nullable: true);

            migrationBuilder.AddColumn<DateOnly>(
                name: "ReceivedDate",
                table: "Assets",
                type: "TEXT",
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Remarks",
                table: "Assets",
                type: "TEXT",
                maxLength: 1000,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "ServiceRequestTicket",
                table: "Assets",
                type: "TEXT",
                maxLength: 150,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Severity",
                table: "Assets",
                type: "TEXT",
                maxLength: 150,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "SignedAllocationFormStatus",
                table: "Assets",
                type: "TEXT",
                maxLength: 100,
                nullable: true);

            migrationBuilder.AddColumn<string>(
                name: "Workstation",
                table: "Assets",
                type: "TEXT",
                maxLength: 150,
                nullable: true);

            migrationBuilder.CreateTable(
                name: "ShipmentTrackingEvents",
                columns: table => new
                {
                    ShipmentTrackingEventId = table.Column<int>(type: "INTEGER", nullable: false)
                        .Annotation("Sqlite:Autoincrement", true),
                    ShipmentId = table.Column<int>(type: "INTEGER", nullable: false),
                    EventUtc = table.Column<DateTime>(type: "TEXT", nullable: false),
                    Status = table.Column<string>(type: "TEXT", maxLength: 100, nullable: false),
                    Description = table.Column<string>(type: "TEXT", maxLength: 1000, nullable: true),
                    Location = table.Column<string>(type: "TEXT", maxLength: 300, nullable: true),
                    Source = table.Column<string>(type: "TEXT", maxLength: 100, nullable: false)
                },
                constraints: table =>
                {
                    table.PrimaryKey("PK_ShipmentTrackingEvents", x => x.ShipmentTrackingEventId);
                    table.ForeignKey(
                        name: "FK_ShipmentTrackingEvents_Shipments_ShipmentId",
                        column: x => x.ShipmentId,
                        principalTable: "Shipments",
                        principalColumn: "ShipmentId",
                        onDelete: ReferentialAction.Cascade);
                });

            migrationBuilder.CreateIndex(
                name: "IX_ShipmentTrackingEvents_ShipmentId_EventUtc",
                table: "ShipmentTrackingEvents",
                columns: new[] { "ShipmentId", "EventUtc" });
        }

        /// <inheritdoc />
        protected override void Down(MigrationBuilder migrationBuilder)
        {
            migrationBuilder.DropTable(
                name: "ShipmentTrackingEvents");

            migrationBuilder.DropColumn(
                name: "TrackingLastCheckedUtc",
                table: "Shipments");

            migrationBuilder.DropColumn(
                name: "TrackingLastMessage",
                table: "Shipments");

            migrationBuilder.DropColumn(
                name: "TrackingUrl",
                table: "Shipments");

            migrationBuilder.DropColumn(
                name: "AllocationDate",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "Classification",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "CurrentLocation",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "Designation",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "DockingStation",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "DuplicateSerialNumber",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "EmployeeNumber",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "Headset",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "Keyboard",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "Monitor1AssetTag",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "Monitor1SerialNumber",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "Monitor2AssetTag",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "Monitor2SerialNumber",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "Monitor3AssetTag",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "Monitor3SerialNumber",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "Mouse",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "NewReplacementStatus",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "OfficeWorkMode",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "OldEmployeeNumber",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "OldUserName",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "OwnerEmail",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "OwnerName",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "Printer",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "ReceivedDate",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "Remarks",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "ServiceRequestTicket",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "Severity",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "SignedAllocationFormStatus",
                table: "Assets");

            migrationBuilder.DropColumn(
                name: "Workstation",
                table: "Assets");
        }
    }
}
