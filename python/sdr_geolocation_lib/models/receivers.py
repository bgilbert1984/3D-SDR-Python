"""
SDR Receiver models.

This module defines the SDRReceiver class which represents an SDR receiver with known coordinates.
"""

from dataclasses import dataclass
from typing import Dict, Tuple
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