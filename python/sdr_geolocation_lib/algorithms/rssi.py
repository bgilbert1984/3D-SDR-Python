"""
Received Signal Strength Indicator (RSSI) geolocation algorithms.

This module provides functions for signal source geolocation using the 
Received Signal Strength method.
"""

from typing import Dict, List, Optional, Tuple
from scipy.optimize import minimize

from sdr_geolocation_lib.models import SDRReceiver, SignalMeasurement
from .tdoa import calculate_distance


def geolocate_rssi(signal_measurements: List[SignalMeasurement],
                  active_receivers: List[SDRReceiver]) -> Optional[Tuple[float, float, float]]:
    """
    Estimate transmitter location using Received Signal Strength (RSSI)
    This is less accurate than TDoA but can work with fewer receivers
    
    Args:
        signal_measurements: List of signal measurements with power values
        active_receivers: List of active receivers
        
    Returns:
        Optional tuple of (latitude, longitude, altitude)
    """
    # Need measurements from at least 3 receivers for triangulation
    if len(signal_measurements) < 3:
        return None
    
    # Create dictionary of receivers for quick lookup
    receivers_dict = {r.id: r for r in active_receivers}
    
    # Function to minimize: weighted sum of squared differences between expected and measured power
    def error_function(coords):
        lat, lon, alt = coords
        error_sum = 0
        
        for measurement in signal_measurements:
            receiver = receivers_dict.get(measurement.receiver_id)
            if not receiver:
                continue
            
            receiver_coords = (receiver.latitude, receiver.longitude, receiver.altitude)
            
            # Distance from hypothesized transmitter to this receiver
            distance = calculate_distance(receiver_coords, (lat, lon, alt))
            
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
        receiver = receivers_dict.get(measurement.receiver_id)
        if not receiver:
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