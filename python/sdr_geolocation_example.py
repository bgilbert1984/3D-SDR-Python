#!/usr/bin/env python3
"""
SDR Geolocation Example

This script demonstrates how to use the sdr_geolocation_lib library
to perform signal source geolocation using various techniques.
"""

import asyncio
from haversine import Unit
from haversine import haversine

# Import from our new modular library
from sdr_geolocation_lib import (
    SDRGeolocation, 
    SDRReceiver, 
    SignalMeasurement, 
    GeoSimulator
)


async def simulate_basic_geolocation():
    """Simulate basic geolocation of a static transmitter"""
    print("=== Basic Geolocation Simulation ===")
    
    # Create a simulator
    simulator = GeoSimulator()
    
    # Generate test receivers around San Francisco
    center_lat = 37.7749
    center_lon = -122.4194
    receivers = simulator.generate_receivers(
        center_lat=center_lat, 
        center_lon=center_lon, 
        radius_km=10, 
        count=5
    )
    
    print(f"Generated {len(receivers)} test receivers around ({center_lat}, {center_lon})")
    for receiver in receivers:
        print(f"  {receiver.id}: ({receiver.latitude}, {receiver.longitude})")
    
    # Create geolocation engine
    geo = SDRGeolocation()
    
    # Initialize remote SDR support
    # Note: For demo purposes, we won't actually connect to remote SDRs
    await geo.init_remote_handler()
    
    # Add receivers to engine
    for receiver in receivers:
        geo.add_receiver(receiver)
    
    # Simulate a transmitter
    transmitter_lat = 37.8199
    transmitter_lon = -122.4783
    transmitter_alt = 0.0
    frequency = 100e6  # 100 MHz
    
    print(f"\nSimulated transmitter at ({transmitter_lat}, {transmitter_lon})")
    
    # Generate simulated signal measurements
    measurements = simulator.simulate_signal(
        transmitter_lat=transmitter_lat, 
        transmitter_lon=transmitter_lon, 
        transmitter_alt=transmitter_alt,
        frequency=frequency,
        power=1.0,
        receivers=receivers
    )
    
    # Calculate TDoA
    measurements_with_tdoa = geo.calculate_tdoa(measurements)
    
    # Geolocate using TDoA
    tdoa_result = geo.geolocate_tdoa(measurements_with_tdoa)
    if tdoa_result:
        tdoa_lat, tdoa_lon, tdoa_alt = tdoa_result
        tdoa_error = haversine(
            (tdoa_lat, tdoa_lon), 
            (transmitter_lat, transmitter_lon), 
            unit=Unit.KILOMETERS
        )
        print(f"\nTDoA geolocation result: ({tdoa_lat:.6f}, {tdoa_lon:.6f})")
        print(f"Error: {tdoa_error:.2f} km")
    else:
        print("\nTDoA geolocation failed")
    
    # Geolocate using RSSI
    rssi_result = geo.geolocate_rssi(measurements)
    if rssi_result:
        rssi_lat, rssi_lon, rssi_alt = rssi_result
        rssi_error = haversine(
            (rssi_lat, rssi_lon), 
            (transmitter_lat, transmitter_lon), 
            unit=Unit.KILOMETERS
        )
        print(f"\nRSSI geolocation result: ({rssi_lat:.6f}, {rssi_lon:.6f})")
        print(f"Error: {rssi_error:.2f} km")
    else:
        print("\nRSSI geolocation failed")
    
    # Hybrid geolocation
    hybrid_result = geo.geolocate_hybrid(measurements)
    if hybrid_result:
        hybrid_lat, hybrid_lon, hybrid_alt = hybrid_result
        hybrid_error = haversine(
            (hybrid_lat, hybrid_lon), 
            (transmitter_lat, transmitter_lon), 
            unit=Unit.KILOMETERS
        )
        print(f"\nHybrid geolocation result: ({hybrid_lat:.6f}, {hybrid_lon:.6f})")
        print(f"Error: {hybrid_error:.2f} km")
    else:
        print("\nHybrid geolocation failed")


async def simulate_moving_transmitter():
    """Simulate geolocation of a moving transmitter"""
    print("\n=== Moving Transmitter Simulation ===")
    
    # Create a simulator
    simulator = GeoSimulator()
    
    # Generate test receivers in a wider area
    center_lat = 37.7749
    center_lon = -122.4194
    receivers = simulator.generate_receivers(
        center_lat=center_lat, 
        center_lon=center_lon, 
        radius_km=15, 
        count=6
    )
    
    print(f"Generated {len(receivers)} test receivers around ({center_lat}, {center_lon})")
    
    # Create geolocation engine
    geo = SDRGeolocation()
    
    # Add receivers to engine
    for receiver in receivers:
        geo.add_receiver(receiver)
    
    # Simulate a moving transmitter
    start_lat = 37.8199
    start_lon = -122.4783
    start_alt = 100.0  # Altitude in meters
    frequency = 100e6  # 100 MHz
    
    # Movement parameters
    speed_mps = 20  # 20 meters per second (~72 km/h)
    heading_deg = 120  # Moving southeast
    duration_sec = 60  # Simulate for 1 minute
    sample_interval_sec = 10  # Take measurements every 10 seconds
    
    print(f"\nSimulating moving transmitter starting at ({start_lat}, {start_lon})")
    print(f"Speed: {speed_mps} m/s, Heading: {heading_deg}°, Duration: {duration_sec}s")
    
    # Simulate the moving transmitter
    all_measurements = simulator.simulate_moving_transmitter(
        start_lat=start_lat,
        start_lon=start_lon,
        start_alt=start_alt,
        frequency=frequency,
        power=1.0,
        receivers=receivers,
        speed_mps=speed_mps,
        heading_deg=heading_deg,
        duration_sec=duration_sec,
        sample_interval_sec=sample_interval_sec
    )
    
    # Process each set of measurements to track the transmitter
    print("\nTracking the transmitter:")
    
    for i, measurements in enumerate(all_measurements):
        time = i * sample_interval_sec
        
        # Calculate TDoA for this set of measurements
        measurements_with_tdoa = geo.calculate_tdoa(measurements)
        
        # Geolocate using TDoA
        position = geo.geolocate_tdoa(measurements_with_tdoa)
        
        if position:
            lat, lon, alt = position
            print(f"Time {time}s: Located at ({lat:.6f}, {lon:.6f}, {alt:.1f}m)")
        else:
            print(f"Time {time}s: Unable to determine position")


async def main():
    """Main entry point"""
    # Run the basic geolocation example
    await simulate_basic_geolocation()
    
    # Run the moving transmitter example
    await simulate_moving_transmitter()


if __name__ == "__main__":
    asyncio.run(main())