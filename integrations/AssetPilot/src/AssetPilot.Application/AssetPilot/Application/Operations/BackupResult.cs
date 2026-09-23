namespace AssetPilot.Application.Operations;

public sealed record BackupResult(string FileName, long SizeBytes, int AssetCount, bool IsVerified);
