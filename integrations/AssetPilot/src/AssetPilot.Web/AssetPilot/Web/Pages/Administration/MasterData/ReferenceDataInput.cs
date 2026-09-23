using System.ComponentModel.DataAnnotations;

namespace AssetPilot.Web.Pages.Administration.MasterData;

public sealed class ReferenceDataInput
{
	[Required]
	[StringLength(50)]
	public string Kind { get; set; } = "Location";

	[Required]
	[StringLength(150)]
	public string Name { get; set; } = "";

	[StringLength(50)]
	public string? Code { get; set; }

	[StringLength(500)]
	public string? Notes { get; set; }

	[Display(Name = "Parent record")]
	public int? ParentId { get; set; }

	public int Version { get; set; }
}
