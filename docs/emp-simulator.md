# EMP Simulator Documentation

## Overview

The EMP (Electromagnetic Pulse) Simulator is an advanced feature of the SDR Drone Pursuit System that enables users to simulate, detect, and visualize electromagnetic pulse events. This module operates within the geolocation-integrated.py script and provides both manual simulation control and automatic detection capabilities.

## Key Features

- **Adjustable Yield Settings**: Configure EMP simulations from small tactical (kilotons) to large strategic (megatons) yields
- **Distance Modeling**: Simulate EMPs at varying distances from the detector
- **Real-time Signal Disruption**: Observe how EMPs affect RF signal detection and classification
- **Auto-detection**: Automatically identify potential EMP signatures in SDR data
- **Scientific Modeling**: Based on empirical formulas for EMP propagation and effects
- **Multi-phase Simulation**: Models E1, E2, and E3 phases of electromagnetic pulse events

## EMP Simulator Integration

The EMP simulator is integrated with the SDR signal processing pipeline in `geolocation-integrated.py` and can be controlled via the WebSocket API.

### EMP_Simulator Class

The core of the simulator is implemented in the `EMP_Simulator` class, which provides the following functionality:

```python
class EMP_Simulator:
    def __init__(self, yield_kt=50):
        """Initialize with yield in kilotons"""
        
    def calculate_emp_radius(self):
        """Calculate the effective radius of the EMP"""
        
    def emp_field_strength(self, distance_km):
        """Calculate field strength at given distance"""
        
    def trigger_emp_event(self, yield_kt=None, distance_km=10):
        """Trigger an EMP event with specified parameters"""
        
    def apply_emp_effect_to_signal(self, fft_data, duration_sec=5):
        """Apply EMP effects to FFT data"""
        
    def detect_emp_signature(self, fft_data, prev_fft_data):
        """Detect potential EMP signatures in signal data"""
        
    def plot_emp_effect(self):
        """Generate visualization of EMP effect vs distance"""
```

## Configuration Parameters

The EMP simulator can be configured through the `CONFIG['emp']` dictionary in `geolocation-integrated.py`:

| Parameter | Description | Default |
|-----------|-------------|---------|
| `enabled` | Whether EMP simulation is active | `False` |
| `yield_kt` | EMP yield in kilotons | `50` |
| `distance_km` | Distance from EMP source in kilometers | `10` |
| `duration_sec` | Duration of EMP effects in seconds | `5` |
| `auto_detect` | Enables automatic EMP detection | `True` |

## Using the EMP Simulator

### Via WebSocket API

The EMP simulator can be controlled through WebSocket messages sent to the server running on port 8080:

#### 1. Trigger an EMP Event

Send a JSON message with the following format:

```json
{
  "type": "emp_simulate",
  "yield_kt": 100,
  "distance_km": 5
}
```

This will:
- Trigger an EMP event with 100kT yield at 5km distance
- Apply EMP effects to incoming SDR data
- Generate a visualization plot
- Return confirmation with event details

#### 2. Configure EMP Parameters

```json
{
  "type": "emp_configure",
  "enabled": true,
  "yield_kt": 75,
  "distance_km": 8,
  "duration_sec": 10,
  "auto_detect": true
}
```

This updates the simulator configuration without triggering an event.

#### 3. Stop EMP Simulation

```json
{
  "type": "emp_stop"
}
```

This will immediately stop any active EMP simulation.

### Response Data

When an EMP event is triggered, the server will respond with:

```json
{
  "type": "emp_simulation_started",
  "event": {
    "event": "emp_triggered",
    "yield_kt": 100,
    "radius_km": 9.5,
    "distance_km": 5,
    "field_strength": 24563.2,
    "timestamp": 1621234567.89
  },
  "plot_file": "emp_simulation_20230415_123045.png"
}
```

Regular signal data during an active EMP event will include an additional `emp` object:

```json
{
  "freqs": [...],
  "amplitudes": [...],
  "signals": [...],
  "timestamp": 1621234567.89,
  "emp": {
    "active": true,
    "yield_kt": 100,
    "distance_km": 5,
    "radius_km": 9.5,
    "elapsed_sec": 2.3,
    "auto_detected": false,
    "confidence": null
  }
}
```

## EMP Effects on Signal Detection

The EMP simulator models several effects on RF signals:

1. **Noise Floor Elevation**: The baseline noise level increases dramatically
2. **Signal Masking**: Weaker signals become obscured by EMP-induced noise
3. **Modulation Classification Degradation**: Signal types become harder to identify
4. **Dynamic Range Compression**: Reduced distinction between signal levels
5. **Random Impulse Noise**: Characteristic spikes appear across the spectrum

### Signal Classification Under EMP

During an active EMP event, signal classification accuracy degrades based on:
- Proximity to the EMP source
- Yield of the EMP event
- Time elapsed since the EMP event (phase-dependent)
- Original signal strength and characteristics

## EMP Detection Algorithm

The auto-detection feature analyzes SDR data for EMP signatures using these criteria:

- **Sudden noise floor elevation** (>10dB increase)
- **Abrupt power level changes** (>15dB shifts)
- **Characteristic spectral patterns** (high variability across spectrum)

Detection sensitivity can be adjusted by modifying the `detection_threshold` property (default: 0.75).

## EMP Physics Model

The EMP simulator uses these key formulas:

- **EMP Radius Calculation**: `R = 4.4 * (yield_kt ^ (1/3))` kilometers
- **Field Strength**: `E = E0 * exp(-d / (R/2))` where:
  - `E0` is field strength at 1km (approximately 50 kV/m)
  - `d` is distance in km
  - `R` is the EMP radius

## Time-Phased EMP Effects

The simulator models the three phases of an EMP:

1. **E1 Phase** (0-100ms in simulation time):
   - Highest intensity (100%)
   - Extremely rapid rise
   - Broad spectral impact

2. **E2 Phase** (100ms-1s):
   - Moderate intensity (70%)
   - Characteristic of lightning effects
   - Mid-frequency disruption

3. **E3 Phase** (1s-5s):
   - Declining intensity (40% → 0%)
   - Slower, longer-lasting components
   - Low-frequency disturbances

## Visualization

Each EMP simulation generates a plot showing field strength vs. distance, saved as a PNG file in the working directory. The plot shows:

- Field strength curve from the epicenter
- Maximum EMP radius as a vertical line
- Yield information in the legend

## Example Usage Scenarios

### Scenario 1: Manual Simulation for Testing

1. Start the geolocation-integrated.py script
2. Connect to WebSocket server at ws://localhost:8080
3. Send EMP simulation command with 50kT yield at 10km
4. Observe signal disruption in visualizer
5. After 5 seconds, observe signal recovery

### Scenario 2: Automatic Detection Testing

1. Configure system with `auto_detect: true`
2. Generate an artificial EMP-like signature in the RF environment
3. Observe if the system automatically detects and reports the event

## Performance Considerations

- EMP simulation adds computational overhead to signal processing
- Higher FFT resolutions increase EMP detection accuracy but require more processing power
- Visualization plot generation may cause brief processing delays

## Troubleshooting

| Issue | Solution |
|-------|----------|
| EMP effects not visible | Ensure `CONFIG['emp']['enabled']` is `True` |
| No auto-detection | Check `CONFIG['emp']['auto_detect']` setting |
| Weak EMP effect | Increase yield or decrease distance |
| Plot file not generated | Verify matplotlib is installed and working |

## Advanced Usage

### Custom EMP Profiles

You can create custom EMP profiles by modifying the `apply_emp_effect_to_signal` method to implement different attenuation and noise patterns.

### Integration with Other Systems

The EMP simulator can be integrated with other components by subscribing to WebSocket events from geolocation-integrated.py and monitoring for messages with EMP-related data.

### EMP Database

For research purposes, you can log EMP events and their characteristics by adding data collection code to the `trigger_emp_event` method.