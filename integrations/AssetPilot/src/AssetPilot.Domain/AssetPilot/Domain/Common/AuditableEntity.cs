using System;

namespace AssetPilot.Domain.Common;

public abstract class AuditableEntity
{
	public DateTime CreatedUtc { get; set; }

	public DateTime ModifiedUtc { get; set; }

	public int Version { get; set; } = 1;
}
