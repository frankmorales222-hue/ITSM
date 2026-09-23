using System;

namespace AssetPilot.Application.Operations;

public sealed record BackupInfo(string FileName, long SizeBytes, DateTime CreatedUtc);
