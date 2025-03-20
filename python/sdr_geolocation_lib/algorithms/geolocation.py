"""
Core geolocation engine.

This module contains the main SDRGeolocation class which combines
different geolocation techniques.
"""

import time
import math
from typing import Dict, List, Optional, Tuple

from sdr_geolocation_lib.models import SDRReceiver, SignalMeasurement
from sdr_geolocation_lib.remote import RemoteSDRHandler
from .tdoa import calculate_tdoa, geolocate_tdoa
from .rssi import geolocate_rssi


class SDRGeolocation:
    """SDR Geolocation Engine using various techniques"""
    
    # Speed of light in meters per second
    SPEED_OF_LIGHT = 299792458
    
    def __init__(self):
        """Initialize geolocation engine"""
        self.receivers: Dict[str, SDRReceiver] = {}
        self.reference_receiver: Optional[str] = None
        self.remote_handler: Optional[RemoteSDRHandler] = None
    
    async def init_remote_handler(self):
        """Initialize the remote SDR handler"""
        self.remote_handler = RemoteSDRHandler()
        return self.remote_handler
    
    async def add_remote_measurements(self, frequency: float, measurements: List[SignalMeasurement]):
        """Add measurements from remote SDR providers"""
        if not self.remote_handler:
            return
            
        async with self.remote_handler:
            remote_results = await self.remote_handler.fetch_data(frequency)
            
            for result in remote_results:
                # Add virtual receiver
                receiver = self.remote_handler.create_virtual_receiver(result)
                self.add_receiver(receiver)
                
                # Add measurement
                if 'measurement' in result:
                    measurements.append(result['measurement'])
    
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
            
        return calculate_tdoa(signal_measurements, self.reference_receiver)
    
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
            
        return geolocate_tdoa(signal_measurements, 
                             self.receivers, 
                             self.reference_receiver,
                             self.SPEED_OF_LIGHT)
    
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
            
        return geolocate_rssi(signal_measurements, self.get_active_receivers())
    
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