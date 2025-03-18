# SDR Integration Documentation

## Overview

The SDR integration system provides real-time signal processing and analysis capabilities using RTL-SDR hardware or a simulation mode for testing.

## Hardware Support

### Supported SDR Devices
- RTL-SDR (RTL2832U)
- Support for additional devices via osmosdr interface
- Software simulation mode for development

### Device Configuration
```python
# Default SDR parameters
sample_rate = 2.048e6  # 2.048 MHz
center_freq = 100e6    # 100 MHz
gain = 20              # Configurable gain
```

## Signal Processing

### Modulation Types
- AM (Amplitude Modulation)
- FM (Frequency Modulation)
- SSB (Single Side Band)
- CW (Continuous Wave)
- Digital modes (PSK, FSK)

### Signal Analysis
- Real-time FFT processing
- Waterfall display generation
- Signal strength measurement
- Modulation classification
- Bandwidth analysis

## Signal Simulation

### Simulated Signal Generation
```python
# Example signal parameters
signal = SimulatedSignal(
    frequency=100.1e6,  # 100.1 MHz
    amplitude=0.5,
    modulation="AM",
    bandwidth=10e3
)
```

### Available Simulation Features
- Multiple simultaneous signals
- Realistic noise modeling
- Variable signal strength
- Doppler effect simulation
- Interference patterns

## WebSocket Interface

### Data Format
```json
{
    "freqs": [...],       // Frequency array
    "amplitudes": [...],  // Signal strength array
    "signals": [         // Detected signals
        {
            "frequency": 100.1e6,
            "amplitude": 0.5,
            "modulation": "AM",
            "bandwidth": 10000
        }
    ]
}
```

## API Reference

### SDR Control Methods
```python
setup_sdr()              # Initialize SDR hardware
detect_all_sdr_devices() # Discover available devices
process_samples()        # Process raw IQ data
analyze_signal()         # Perform signal analysis
generate_waterfall()     # Create waterfall data
```

### Simulation Methods
```python
generate_samples()       # Generate IQ samples
add_signal_component()   # Add signal to simulation
add_noise()             # Add realistic noise
simulate_doppler()      # Add doppler effects
```