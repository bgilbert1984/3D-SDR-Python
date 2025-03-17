import numpy as np
import json
import time
import math
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional, Union
from scipy.optimize import minimize
from haversine import haversine, Unit

@dataclass
class SDRReceiver:
    """Represents an SDR receiver with known coordinates"""
    id: str
    latitude: float
    longitude: float
    altitude: float = 0.0
    timestamp: float = 0.0
    active: bool = True
    
    def get_coordinates(self) -> Tuple[float, float, float]:
        """Get position as (latitude, longitude, altitude)"""
        return (self.latitude, self.longitude, self.altitude)
    
    def distance_to(self, other_receiver: 'SDRReceiver') -> float:
        """Calculate distance in meters to another receiver"""
        return haversine(
            (self.latitude, self.longitude),
            (other_receiver.latitude, other_receiver.longitude),
            unit=Unit.METERS
        )
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            "id": self.id,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "altitude": self.altitude,
            "timestamp": self.timestamp,
            "active": self.active
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'SDRReceiver':
        """Create from dictionary representation"""
        return cls(
            id=data["id"],
            latitude=data["latitude"],
            longitude=data["longitude"],
            altitude=data.get("altitude", 0.0),
            timestamp=data.get("timestamp", 0.0),
            active=data.get("active", True)
        )

@dataclass
class SignalMeasurement:
    """Signal measurement from an SDR receiver"""
    receiver_id: str
    frequency: float  # in Hz
    power: float      # normalized power (0-1)
    timestamp: float
    tdoa: Optional[float] = None  # Time Difference of Arrival in seconds (relative to reference)
    snr: Optional[float] = None   # Signal-to-Noise Ratio in dB
    modulation: Optional[str] = None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary for serialization"""
        return {
            "receiver_id": self.receiver_id,
            "frequency": self.frequency,
            "power": self.power,
            "timestamp": self.timestamp,
            "tdoa": self.tdoa,
            "snr": self.snr,
            "modulation": self.modulation
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'SignalMeasurement':
        """Create from dictionary representation"""
        return cls(
            receiver_id=data["receiver_id"],
            frequency=data["frequency"],
            power=data["power"],
            timestamp=data["timestamp"],
            tdoa=data.get("tdoa"),
            snr=data.get("snr"),
            modulation=data.get("modulation")
        )

class SDRGeolocation:
    """SDR Geolocation Engine using various techniques"""
    
    # Speed of light in meters per second
    SPEED_OF_LIGHT = 299792458
    
    def __init__(self):
        """Initialize geolocation engine"""
        self.receivers: Dict[str, SDRReceiver] = {}
        self.reference_receiver: Optional[str] = None
    
    def add_receiver(self, receiver: SDRReceiver) -> None:
        """Add or update an SDR receiver"""
        self.receivers[receiver.id] = receiver
        
        # If this is the first receiver, make it the reference by default
        if len(self.receivers) == 1:
            self.reference_receiver = receiver.id
    
    def remove_receiver(self, receiver_id: str) -> None:
        """Remove an SDR receiver"""
        if receiver_id in self.receivers:
            del self.receivers[receiver_id]
            
            # If removed receiver was the reference, choose a new one if possible
            if self.reference_receiver == receiver_id and self.receivers:
                self.reference_receiver = next(iter(self.receivers.keys()))
    
    def set_reference_receiver(self, receiver_id: str) -> bool:
        """Set the reference receiver for TDoA calculations"""
        if receiver_id in self.receivers:
            self.reference_receiver = receiver_id
            return True
        return False
    
    def get_active_receivers(self) -> List[SDRReceiver]:
        """Get list of active receivers"""
        return [r for r in self.receivers.values() if r.active]
    
    def calculate_tdoa(self, signal_measurements: List[SignalMeasurement]) -> List[SignalMeasurement]:
        """
        Calculate Time Difference of Arrival (TDoA) for signal measurements
        relative to the reference receiver
        """
        if not self.reference_receiver:
            return signal_measurements
        
        # Group measurements by receiver
        measurements_by_receiver = {}
        for measurement in signal_measurements:
            measurements_by_receiver[measurement.receiver_id] = measurement
        
        # If we don't have a measurement from the reference receiver, can't calculate TDoA
        if self.reference_receiver not in measurements_by_receiver:
            return signal_measurements
        
        reference_time = measurements_by_receiver[self.reference_receiver].timestamp
        
        # Calculate TDoA for each measurement
        for measurement in signal_measurements:
            if measurement.receiver_id != self.reference_receiver:
                measurement.tdoa = measurement.timestamp - reference_time
        
        return signal_measurements
    
    def geolocate_tdoa(self, signal_measurements: List[SignalMeasurement]) -> Optional[Tuple[float, float, float]]:
        """
        Geolocate a signal source using Time Difference of Arrival (TDoA)
        
        Returns:
            Optional tuple of (latitude, longitude, altitude)
        """
        # Need at least 4 receivers for 3D positioning, 3 for 2D
        active_receivers = self.get_active_receivers()
        if len(active_receivers) < 3:
            return None
        
        # Group measurements by receiver
        measurements_by_receiver = {}
        for measurement in signal_measurements:
            if measurement.tdoa is not None:
                measurements_by_receiver[measurement.receiver_id] = measurement
        
        # Need TDoA measurements from at least 3 receivers (including reference)
        if len(measurements_by_receiver) < 3:
            return None
        
        # Function to minimize: sum of squared differences between measured and predicted TDoA
        def error_function(coords):
            lat, lon, alt = coords
            error_sum = 0
            
            # Get reference receiver coordinates
            ref_receiver = self.receivers[self.reference_receiver]
            ref_coords = (ref_receiver.latitude, ref_receiver.longitude, ref_receiver.altitude)
            
            # Calculate distance from hypothesized transmitter to reference receiver
            ref_distance = self._calculate_distance(ref_coords, (lat, lon, alt))
            
            # Calculate expected TDoA for each receiver and compare to measured
            for receiver_id, measurement in measurements_by_receiver.items():
                if receiver_id == self.reference_receiver:
                    continue
                
                receiver = self.receivers[receiver_id]
                receiver_coords = (receiver.latitude, receiver.longitude, receiver.altitude)
                
                # Distance from hypothesized transmitter to this receiver
                distance = self._calculate_distance(receiver_coords, (lat, lon, alt))
                
                # Expected time difference (TDoA) based on distance difference
                expected_tdoa = (distance - ref_distance) / self.SPEED_OF_LIGHT
                
                # Add squared error
                error_sum += (expected_tdoa - measurement.tdoa) ** 2
            
            return error_sum
        
        # Initial guess: average of receiver positions
        avg_lat = sum(r.latitude for r in active_receivers) / len(active_receivers)
        avg_lon = sum(r.longitude for r in active_receivers) / len(active_receivers)
        avg_alt = sum(r.altitude for r in active_receivers) / len(active_receivers)
        
        initial_guess = [avg_lat, avg_lon, avg_alt]
        
        # Use optimization to find the transmitter location that minimizes the error
        result = minimize(error_function, initial_guess, method='Powell')
        
        if result.success:
            return tuple(result.x)
        
        return None
    
    def geolocate_rssi(self, signal_measurements: List[SignalMeasurement]) -> Optional[Tuple[float, float, float]]:
        """
        Estimate transmitter location using Received Signal Strength (RSSI)
        This is less accurate than TDoA but can work with fewer receivers
        
        Returns:
            Optional tuple of (latitude, longitude, altitude)
        """
        # Need measurements from at least 3 receivers for triangulation
        if len(signal_measurements) < 3:
            return None
        
        # Function to minimize: weighted sum of squared differences between expected and measured power
        def error_function(coords):
            lat, lon, alt = coords
            error_sum = 0
            
            for measurement in signal_measurements:
                receiver = self.receivers.get(measurement.receiver_id)
                if not receiver or not receiver.active:
                    continue
                
                receiver_coords = (receiver.latitude, receiver.longitude, receiver.altitude)
                
                # Distance from hypothesized transmitter to this receiver
                distance = self._calculate_distance(receiver_coords, (lat, lon, alt))
                
                # Expected power based on inverse square law (simplified model)
                # Power ∝ 1/d²
                expected_power = 1.0 / (distance ** 2)
                
                # Normalize expected power to range 0-1
                max_expected = 1.0  # At distance=1
                expected_power = expected_power / max_expected
                
                # Add squared error, weighted by SNR if available
                weight = 1.0
                if measurement.snr is not None:
                    # Higher SNR means more reliable measurement
                    weight = 10 ** (measurement.snr / 10)
                
                error_sum += weight * ((expected_power - measurement.power) ** 2)
            
            return error_sum
        
        # Initial guess: weighted average of receiver positions by signal strength
        total_power = sum(m.power for m in signal_measurements)
        if total_power == 0:
            return None
        
        avg_lat = 0.0
        avg_lon = 0.0
        avg_alt = 0.0
        
        for measurement in signal_measurements:
            receiver = self.receivers.get(measurement.receiver_id)
            if not receiver or not receiver.active:
                continue
            
            weight = measurement.power / total_power
            avg_lat += receiver.latitude * weight
            avg_lon += receiver.longitude * weight
            avg_alt += receiver.altitude * weight
        
        initial_guess = [avg_lat, avg_lon, avg_alt]
        
        # Use optimization to find the transmitter location that minimizes the error
        result = minimize(error_function, initial_guess, method='Powell')
        
        if result.success:
            return tuple(result.x)
        
        return None
    
    def geolocate_hybrid(self, signal_measurements: List[SignalMeasurement]) -> Optional[Tuple[float, float, float]]:
        """
        Hybrid geolocation using both TDoA and RSSI data when available
        Falls back to either method if needed
        
        Returns:
            Optional tuple of (latitude, longitude, altitude)
        """
        # Try TDoA first as it's generally more accurate
        tdoa_result = self.geolocate_tdoa(signal_measurements)
        if tdoa_result:
            return tdoa_result
        
        # Fall back to RSSI if TDoA failed
        return self.geolocate_rssi(signal_measurements)
    
    def estimate_single_receiver(self, measurement: SignalMeasurement, 
                                estimated_transmit_power: float = 1.0) -> List[Dict]:
        """
        For a single receiver, estimate possible transmitter locations
        based on signal strength. Returns a list of possible locations
        forming a circle around the receiver.
        
        Args:
            measurement: Signal measurement from a single receiver
            estimated_transmit_power: Estimated power of the transmitter (normalized)
            
        Returns:
            List of possible locations (lat/lon pairs) representing a probability circle
        """
        if measurement.receiver_id not in self.receivers:
            return []
        
        receiver = self.receivers[measurement.receiver_id]
        
        # Calculate estimated distance based on signal power
        # using inverse square law (simplified model)
        # Distance ∝ sqrt(1/power)
        # This is highly approximate and depends on many factors
        
        # Normalize power to avoid division by zero
        power = max(measurement.power, 0.001)
        
        # Calculate approximate distance in meters
        # The multiplier is a tunable parameter depending on transmitter power
        estimated_distance = math.sqrt(estimated_transmit_power / power) * 1000
        
        # Generate points on a circle around the receiver
        circle_points = []
        num_points = 36  # Number of points to generate (every 10 degrees)
        
        for i in range(num_points):
            angle = (2 * math.pi * i) / num_points
            
            # Calculate point at given angle and distance
            lat, lon = self._get_point_at_distance(
                receiver.latitude, 
                receiver.longitude, 
                estimated_distance, 
                angle
            )
            
            circle_points.append({
                "latitude": lat,
                "longitude": lon,
                "probability": 1.0 / num_points  # Equal probability for all points
            })
        
        return circle_points
    
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
    
    def to_dict(self) -> Dict:
        """Convert geolocation engine state to dictionary for serialization"""
        return {
            "receivers": {id: receiver.to_dict() for id, receiver in self.receivers.items()},
            "reference_receiver": self.reference_receiver
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'SDRGeolocation':
        """Create from dictionary representation"""
        geo = cls()
        
        for id, receiver_data in data.get("receivers", {}).items():
            geo.add_receiver(SDRReceiver.from_dict(receiver_data))
        
        geo.reference_receiver = data.get("reference_receiver")
        
        return geo

# Utility class for simulating geolocation data
class GeoSimulator:
    """
    Utility class for simulating geolocation data for testing
    """
    
    def __init__(self, speed_of_light=SDRGeolocation.SPEED_OF_LIGHT):
        """Initialize the simulator"""
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

# Test and demo code
if __name__ == "__main__":
    # Create a simulator
    simulator = GeoSimulator()
    
    # Generate test receivers around San Francisco
    center_lat = 37.7749
    center_lon = -122.4194
    receivers = simulator.generate_receivers(center_lat, center_lon, 10, 5)
    
    print(f"Generated {len(receivers)} test receivers around ({center_lat}, {center_lon})")
    for receiver in receivers:
        print(f"  {receiver.id}: ({receiver.latitude}, {receiver.longitude})")
    
    # Create a simulated transmitter
    transmitter_lat = 37.8199
    transmitter_lon = -122.4783
    transmitter_alt = 0.0
    
    print(f"\nSimulated transmitter at ({transmitter_lat}, {transmitter_lon})")
    
    # Generate simulated signal measurements
    measurements = simulator.simulate_signal(
        transmitter_lat, transmitter_lon, transmitter_alt,
        frequency=100e6,  # 100 MHz
        power=1.0,
        receivers=receivers
    )
    
    print(f"\nGenerated {len(measurements)} signal measurements")
    
    # Create geolocation engine
    geo = SDRGeolocation()
    
    # Add receivers to engine
    for receiver in receivers:
        geo.add_receiver(receiver)
    
    # Calculate TDoA
    measurements_with_tdoa = geo.calculate_tdoa(measurements)
    
    # Geolocate using TDoA
    tdoa_result = geo.geolocate_tdoa(measurements_with_tdoa)
    if tdoa_result:
        tdoa_lat, tdoa_lon, tdoa_alt = tdoa_result
        tdoa_error = haversine((tdoa_lat, tdoa_lon), (transmitter_lat, transmitter_lon), unit=Unit.KILOMETERS)
        print(f"\nTDoA geolocation result: ({tdoa_lat}, {tdoa_lon})")
        print(f"Error: {tdoa_error:.2f} km")
    else:
        print("\nTDoA geolocation failed")
    
    # Geolocate using RSSI
    rssi_result = geo.geolocate_rssi(measurements)
    if rssi_result:
        rssi_lat, rssi_lon, rssi_alt = rssi_result
        rssi_error = haversine((rssi_lat, rssi_lon), (transmitter_lat, transmitter_lon), unit=Unit.KILOMETERS)
        print(f"\nRSSI geolocation result: ({rssi_lat}, {rssi_lon})")
        print(f"Error: {rssi_error:.2f} km")
    else:
        print("\nRSSI geolocation failed")
    
    # Single receiver estimate
    print("\nSingle receiver estimate:")
    possible_locations = geo.estimate_single_receiver(measurements[0])
    print(f"Generated {len(possible_locations)} possible locations")
