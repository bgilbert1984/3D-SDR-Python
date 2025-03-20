"""
SDR Geolocation Library

A modular library for Software Defined Radio geolocation and signal tracking.
"""

__version__ = "0.1.0"

# Import core components for easy access
from sdr_geolocation_lib.models import SDRReceiver, SignalMeasurement
from sdr_geolocation_lib.algorithms import SDRGeolocation
from sdr_geolocation_lib.remote import RemoteSDRHandler
from sdr_geolocation_lib.simulation import GeoSimulator

# Expose the main geolocation class and its required components
__all__ = [
    "SDRReceiver",
    "SignalMeasurement",
    "SDRGeolocation",
    "RemoteSDRHandler",
    "GeoSimulator",
]