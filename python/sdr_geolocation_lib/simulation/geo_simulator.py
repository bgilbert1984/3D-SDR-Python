"""
Geolocation simulation tools.

This module provides a simulator class for generating test data to validate
geolocation algorithms without requiring physical SDR hardware.
"""

import time
import math
import numpy as np
from typing import List, Tuple
from haversine import haversine, Unit

from sdr_geolocation_lib.models import SDRReceiver, SignalMeasurement


class GeoSimulator:
    """
    Utility class for simulating geolocation data for testing
    """
    
    # Speed of light in meters per second
    SPEED_OF_LIGHT = 299792458
    
    def __init__(self, speed_of_light=SPEED_OF_LIGHT):
        """Initialize the simulator with parameters"""
        self.speed_of_light = speed_of_light
    
    def generate_receivers(self, center_lat: float, center_lon: float, 
                         radius_km: float, count: int) -> List[SDRReceiver]:
        """
        Generate simulated SDR receivers around a center point
        
        Args:
            center_lat, center_lon: Center coordinates for receiver network
            radius_km: Radius around center to distribute receivers (in km)
            count: Number of receivers to generate
            
        Returns:
            List of SDRReceiver objects
        """
        receivers = []
        
        # First receiver at center
        receivers.append(SDRReceiver(
            id="R0",
            latitude=center_lat,
            longitude=center_lon,
            altitude=0.0,
            timestamp=time.time()
        ))
        
        # Distribute remaining receivers in a circle
        for i in range(1, count):
            angle = (2 * math.pi * i) / (count - 1)
            
            # Calculate point at given angle and distance
            lat, lon = self._get_point_at_distance(
                center_lat, 
                center_lon, 
                radius_km * 1000,  # Convert to meters
                angle
            )
            
            receivers.append(SDRReceiver(
                id=f"R{i}",
                latitude=lat,
                longitude=lon,
                altitude=0.0,
                timestamp=time.time()
            ))
        
        return receivers
    
    def simulate_signal(self, transmitter_lat: float, transmitter_lon: float,
                      transmitter_alt: float, frequency: float, power: float,
                      receivers: List[SDRReceiver], noise_level: float = 0.01,
                      time_error: float = 1e-9) -> List[SignalMeasurement]:
        """
        Simulate signal measurements for a transmitter at given coordinates
        
        Args:
            transmitter_lat, transmitter_lon, transmitter_alt: Transmitter coordinates
            frequency: Signal frequency in Hz
            power: Transmitter power (normalized)
            receivers: List of SDR receivers to simulate measurements from
            noise_level: Amount of noise to add to power measurements
            time_error: Standard deviation of timing error in seconds
            
        Returns:
            List of SignalMeasurement objects
        """
        measurements = []
        transmitter_coords = (transmitter_lat, transmitter_lon, transmitter_alt)
        
        # Calculate base time
        base_time = time.time()
        
        for receiver in receivers:
            receiver_coords = (receiver.latitude, receiver.longitude, receiver.altitude)
            
            # Calculate true distance
            distance = self._calculate_distance(receiver_coords, transmitter_coords)
            
            # Calculate signal travel time
            travel_time = distance / self.speed_of_light
            
            # Add some timing error
            measured_time = base_time + travel_time + np.random.normal(0, time_error)
            
            # Calculate received power using inverse square law with some noise
            received_power = power / (distance ** 2)
            received_power += np.random.normal(0, noise_level)
            received_power = max(0.001, min(1.0, received_power))  # Clamp between 0.001 and 1.0
            
            # Calculate SNR (simplified)
            background_noise = 0.01
            snr = 10 * math.log10(received_power / background_noise)
            
            # Create measurement
            measurements.append(SignalMeasurement(
                receiver_id=receiver.id,
                frequency=frequency,
                power=received_power,
                timestamp=measured_time,
                snr=snr,
                modulation="AM"  # Example modulation
            ))
        
        return measurements
    
    def simulate_moving_transmitter(self, start_lat: float, start_lon: float, start_alt: float,
                                  frequency: float, power: float, receivers: List[SDRReceiver],
                                  speed_mps: float, heading_deg: float, duration_sec: float,
                                  sample_interval_sec: float) -> List[List[SignalMeasurement]]:
        """
        Simulate a moving transmitter with measurements at specified intervals
        
        Args:
            start_lat, start_lon, start_alt: Starting transmitter coordinates
            frequency: Signal frequency in Hz
            power: Transmitter power (normalized)
            receivers: List of SDR receivers to simulate measurements from
            speed_mps: Speed of the transmitter in meters per second
            heading_deg: Heading of the transmitter in degrees (0=North, 90=East)
            duration_sec: Total duration of simulation in seconds
            sample_interval_sec: Time between samples in seconds
            
        Returns:
            List of lists of SignalMeasurement objects, one list per time step
        """
        all_measurements = []
        heading_rad = math.radians(heading_deg)
        
        # Calculate number of samples
        num_samples = int(duration_sec / sample_interval_sec) + 1
        
        # Current position
        lat = start_lat
        lon = start_lon
        alt = start_alt
        
        for i in range(num_samples):
            # Calculate time
            t = i * sample_interval_sec
            
            # Simulate signal at current position
            measurements = self.simulate_signal(
                lat, lon, alt, frequency, power, receivers
            )
            all_measurements.append(measurements)
            
            # Move transmitter
            distance = speed_mps * sample_interval_sec
            lat, lon = self._get_point_at_distance(lat, lon, distance, heading_rad)
        
        return all_measurements
    
    def _calculate_distance(self, coords1, coords2):
        """Calculate the great-circle distance between two points in meters"""
        lat1, lon1, alt1 = coords1
        lat2, lon2, alt2 = coords2
        
        # Calculate surface distance using Haversine formula
        surface_distance = haversine((lat1, lon1), (lat2, lon2), unit=Unit.METERS)
        
        # Add altitude component using Pythagorean theorem
        altitude_diff = alt2 - alt1
        
        # Total distance
        return math.sqrt(surface_distance**2 + altitude_diff**2)
    
    def _get_point_at_distance(self, lat, lon, distance, bearing):
        """
        Calculate destination point given distance and bearing from starting point
        
        Args:
            lat, lon: Starting coordinates in degrees
            distance: Distance in meters
            bearing: Bearing in radians (0 = North, π/2 = East)
            
        Returns:
            (latitude, longitude) of destination point
        """
        # Convert to radians
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        
        # Earth's radius in meters
        R = 6371000
        
        # Calculate new latitude
        lat2_rad = math.asin(
            math.sin(lat_rad) * math.cos(distance / R) +
            math.cos(lat_rad) * math.sin(distance / R) * math.cos(bearing)
        )
        
        # Calculate new longitude
        lon2_rad = lon_rad + math.atan2(
            math.sin(bearing) * math.sin(distance / R) * math.cos(lat_rad),
            math.cos(distance / R) - math.sin(lat_rad) * math.sin(lat2_rad)
        )
        
        # Convert back to degrees
        lat2 = math.degrees(lat2_rad)
        lon2 = math.degrees(lon2_rad)
        
        return lat2, lon2