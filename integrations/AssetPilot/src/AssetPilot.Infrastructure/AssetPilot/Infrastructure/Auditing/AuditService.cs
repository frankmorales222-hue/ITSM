using System;
using System.Text.Json;
using System.Text.Json.Serialization;
using System.Threading;
using System.Threading.Tasks;
using AssetPilot.Application.Auditing;
using AssetPilot.Domain.Auditing;
using AssetPilot.Infrastructure.Persistence;

namespace AssetPilot.Infrastructure.Auditing;

public sealed class AuditService(AssetPilotDbContext dbContext) : IAuditService
{
	private static readonly JsonSerializerOptions JsonOptions = new(JsonSerializerDefaults.Web)
	{
		ReferenceHandler = ReferenceHandler.IgnoreCycles
	};

	public async Task WriteAsync(string eventTypeCode, string entityTypeCode, string entityId, string? userId, object? before, object? after, string? reason, string correlationId, CancellationToken cancellationToken = default(CancellationToken))
	{
		AuditEvent entity = new AuditEvent
		{
			EventTypeCode = eventTypeCode,
			EntityTypeCode = entityTypeCode,
			EntityId = entityId,
			UserId = userId,
			EventUtc = DateTime.UtcNow,
			BeforeJson = ((before == null) ? null : JsonSerializer.Serialize(before, JsonOptions)),
			AfterJson = ((after == null) ? null : JsonSerializer.Serialize(after, JsonOptions)),
			Reason = reason,
			CorrelationId = correlationId
		};
		dbContext.AuditEvents.Add(entity);
		await dbContext.SaveChangesAsync(cancellationToken);
	}
}
