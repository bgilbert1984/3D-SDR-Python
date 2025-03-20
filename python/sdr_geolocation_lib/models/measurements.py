"""
Signal measurement models.

This module defines the SignalMeasurement class which represents
signal measurements from SDR receivers.
"""

from dataclasses import dataclass
from typing import Dict, Optional


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