using System.Threading;
using System.Threading.Tasks;

namespace AssetPilot.Application.Shipments;

public interface IShipmentTrackingService
{
	Task<ShipmentTrackingResult> GetUpdateAsync(
		string carrier,
		string trackingNumber,
		CancellationToken cancellationToken = default);
}
