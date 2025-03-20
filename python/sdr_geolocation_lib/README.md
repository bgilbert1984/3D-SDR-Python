# SDR Geolocation Library

A modular library for Software Defined Radio geolocation and signal tracking.

## Overview

This library provides tools and algorithms for locating radio signal sources using Software Defined Radio (SDR) receivers. It supports various geolocation techniques including:

- Time Difference of Arrival (TDoA)
- Received Signal Strength Indicator (RSSI)
- Hybrid approaches combining multiple techniques

The library is designed with modularity in mind, making it easy to extend with new algorithms, SDR sources, and visualization methods.

## Library Structure

```
sdr_geolocation_lib/
├── __init__.py                 # Main package initialization
├── models/                     # Data models
│   ├── __init__.py
│   ├── receivers.py            # SDR receiver models
│   └── measurements.py         # Signal measurement models
├── algorithms/                 # Geolocation algorithms
│   ├── __init__.py
│   ├── geolocation.py          # Main geolocation engine
│   ├── tdoa.py                 # Time Difference of Arrival algorithms
│   └── rssi.py                 # Signal strength-based algorithms
├── remote/                     # Remote SDR interfaces
│   ├── __init__.py
│   └── remote_handler.py       # Handler for remote SDR sources (KiwiSDR, WebSDR)
├── simulation/                 # Simulation tools
│   ├── __init__.py
│   └── geo_simulator.py        # Simulator for testing geolocation algorithms
└── utils/                      # Utility functions
    ├── __init__.py
    └── geo_utils.py            # Geographic calculation utilities
```

## Key Components

### SDR Receiver

Represents a physical or virtual SDR receiver with known coordinates.

### Signal Measurement

Contains measurement data from an SDR receiver, including frequency, power, signal-to-noise ratio, and time difference of arrival.

### SDR Geolocation Engine

Core class that implements various geolocation techniques and manages receivers.

### Remote SDR Handler

Interfaces with remote SDR providers like the KiwiSDR network and WebSDR.

### Geo Simulator

Simulates SDR receivers and signal sources for testing and development.

## Example Usage

```python
import asyncio
from sdr_geolocation_lib import SDRGeolocation, GeoSimulator

async def main():
    # Create geolocation engine
    geo = SDRGeolocation()
    
    # Create simulator for testing
    simulator = GeoSimulator()
    
    # Generate test receivers
    receivers = simulator.generate_receivers(
        center_lat=37.7749,  # San Francisco
        center_lon=-122.4194,
        radius_km=10,
        count=5
    )
    
    # Add receivers to geolocation engine
    for receiver in receivers:
        geo.add_receiver(receiver)
    
    # Simulate a transmitter
    measurements = simulator.simulate_signal(
        transmitter_lat=37.8199,
        transmitter_lon=-122.4783,
        transmitter_alt=0.0,
        frequency=100e6,  # 100 MHz
        power=1.0,
        receivers=receivers
    )
    
    # Calculate Time Difference of Arrival
    measurements_with_tdoa = geo.calculate_tdoa(measurements)
    
    # Geolocate using TDoA
    result = geo.geolocate_tdoa(measurements_with_tdoa)
    
    if result:
        lat, lon, alt = result
        print(f"Located signal source at: {lat}, {lon}, {alt}m")

if __name__ == "__main__":
    asyncio.run(main())
```

See `sdr_geolocation_example.py` for more detailed examples.

## Dependencies

- numpy
- scipy
- haversine
- aiohttp
- asyncio

## License

This project is open source software.