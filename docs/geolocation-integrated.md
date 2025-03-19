# Geolocation Integration Documentation

## Overview

The geolocation integration in the SDR Drone Pursuit System provides advanced capabilities for locating signal sources using Time Difference of Arrival (TDoA) and multilateration methods. This system leverages data from multiple SDR receivers to estimate the position of transmitters, enabling precise geolocation of signals and detection of unauthorized transmissions.

## Key Features

1. **TDoA Geolocation**:
   - Calculates Time Difference of Arrival (TDoA) for signal measurements relative to a reference receiver.
   - Uses TDoA data to estimate the transmitter's location with high accuracy.

2. **Multilateration**:
   - Combines TDoA data from multiple receivers to perform multilateration.
   - Provides 2D or 3D geolocation based on the number of active receivers.

3. **Hybrid Geolocation**:
   - Combines TDoA and RSSI (Received Signal Strength Indicator) methods.
   - Falls back to RSSI when TDoA data is insufficient.

4. **Simulation Support**:
   - Includes a `GeoSimulator` class for testing geolocation algorithms.
   - Simulates receivers, transmitters, and signal measurements.

## Backend Implementation

The geolocation engine is implemented in `sdr_geolocation.py` and includes the following components:

### SDRGeolocation Class

The `SDRGeolocation` class provides methods for:

- Adding and managing SDR receivers.
- Calculating TDoA for signal measurements.
- Performing geolocation using TDoA, RSSI, or hybrid methods.

#### TDoA Calculation

```python
def calculate_tdoa(self, signal_measurements: List[SignalMeasurement]) -> List[SignalMeasurement]:
    """
    Calculate Time Difference of Arrival (TDoA) for signal measurements
    relative to the reference receiver.
    """
    # Implementation details...
```

#### TDoA Geolocation

```python
def geolocate_tdoa(self, signal_measurements: List[SignalMeasurement]) -> Optional[Tuple[float, float, float]]:
    """
    Geolocate a signal source using Time Difference of Arrival (TDoA).
    """
    # Implementation details...
```

#### Hybrid Geolocation

```python
def geolocate_hybrid(self, signal_measurements: List[SignalMeasurement]) -> Optional[Tuple[float, float, float]]:
    """
    Hybrid geolocation using both TDoA and RSSI data when available.
    """
    # Implementation details...
```

### GeoSimulator Class

The `GeoSimulator` class provides methods for:

- Generating simulated SDR receivers around a center point.
- Simulating signal measurements for a transmitter.

#### Example Usage

```python
async def main():
    simulator = GeoSimulator()
    receivers = simulator.generate_receivers(37.7749, -122.4194, 10, 5)
    measurements = simulator.simulate_signal(37.8199, -122.4783, 0.0, 100e6, 1.0, receivers)
    # Add measurements to geolocation engine...
```

## Frontend Integration

The frontend visualizes geolocation results on a map using `map-visualization.html`. Key features include:

1. **Geolocation Markers**:
   - Displays markers for estimated transmitter locations.
   - Differentiates between legal signals and violations using colors and animations.

2. **Uncertainty Circles**:
   - Adds circles to represent the uncertainty of TDoA and RSSI estimates.
   - Larger circles for RSSI (less accurate) and smaller for TDoA.

3. **Single Receiver Estimates**:
   - Displays polygons for possible transmitter locations when only one receiver is available.

4. **Dynamic Updates**:
   - Clears and redraws markers and circles based on incoming geolocation results.

### Example Visualization Code

```javascript
function updateGeolocation(geoResults) {
    geoResults.forEach(result => {
        if (result.method === 'tdoa' || result.method === 'rssi') {
            const circle = L.circle([result.latitude, result.longitude], {
                radius: result.method === 'rssi' ? 750 : 250,
                className: 'uncertainty-circle'
            }).addTo(map);
        }
    });
}
```

## Usage

1. Add SDR receivers to the geolocation engine using the `add_receiver` method.
2. Collect signal measurements from SDR receivers.
3. Use the `calculate_tdoa` method to compute TDoA values.
4. Perform geolocation using `geolocate_tdoa`, `geolocate_rssi`, or `geolocate_hybrid`.
5. Visualize the results on the map using the frontend.

## Future Enhancements

1. **Advanced Geolocation**:
   - Add support for TDoA and multilateration methods.
   - Improve accuracy with additional receivers and better algorithms.

2. **Signal Filtering**:
   - Allow users to filter signals by frequency, modulation, or power.

3. **Historical Data**:
   - Enable playback of past signal and violation data.

4. **Mobile Support**:
   - Optimize the interface for smaller screens.

5. **Custom Map Layers**:
   - Add satellite imagery or heatmaps for better visualization.