"""
Time Difference of Arrival (TDOA) geolocation algorithms.

This module provides functions for signal source geolocation using the 
Time Difference of Arrival method.
"""

from typing import Dict, List, Optional, Tuple
from scipy.optimize import minimize
from haversine import haversine, Unit

from sdr_geolocation_lib.models import SDRReceiver, SignalMeasurement


def calculate_tdoa(signal_measurements: List[SignalMeasurement], 
                  reference_receiver_id: str) -> List[SignalMeasurement]:
    """
    Calculate Time Difference of Arrival (TDoA) for signal measurements
    relative to the reference receiver
    
    Args:
        signal_measurements: List of signal measurements
        reference_receiver_id: ID of the reference receiver
        
    Returns:
        Signal measurements with TDoA values updated
    """
    # Group measurements by receiver
    measurements_by_receiver = {}
    for measurement in signal_measurements:
        measurements_by_receiver[measurement.receiver_id] = measurement
    
    # If we don't have a measurement from the reference receiver, can't calculate TDoA
    if reference_receiver_id not in measurements_by_receiver:
        return signal_measurements
    
    reference_time = measurements_by_receiver[reference_receiver_id].timestamp
    
    # Calculate TDoA for each measurement
    for measurement in signal_measurements:
        if measurement.receiver_id != reference_receiver_id:
            measurement.tdoa = measurement.timestamp - reference_time
    
    return signal_measurements


def geolocate_tdoa(signal_measurements: List[SignalMeasurement],
                 receivers: Dict[str, SDRReceiver],
                 reference_receiver_id: str,
                 speed_of_light: float) -> Optional[Tuple[float, float, float]]:
    """
    Geolocate a signal source using Time Difference of Arrival (TDoA)
    
    Args:
        signal_measurements: List of signal measurements with TDoA values
        receivers: Dictionary of available receivers keyed by ID
        reference_receiver_id: ID of the reference receiver
        speed_of_light: Speed of light in meters per second
    
    Returns:
        Optional tuple of (latitude, longitude, altitude)
    """
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
        ref_receiver = receivers[reference_receiver_id]
        ref_coords = (ref_receiver.latitude, ref_receiver.longitude, ref_receiver.altitude)
        
        # Calculate distance from hypothesized transmitter to reference receiver
        ref_distance = calculate_distance(ref_coords, (lat, lon, alt))
        
        # Calculate expected TDoA for each receiver and compare to measured
        for receiver_id, measurement in measurements_by_receiver.items():
            if receiver_id == reference_receiver_id:
                continue
            
            receiver = receivers[receiver_id]
            receiver_coords = (receiver.latitude, receiver.longitude, receiver.altitude)
            
            # Distance from hypothesized transmitter to this receiver
            distance = calculate_distance(receiver_coords, (lat, lon, alt))
            
            # Expected time difference (TDoA) based on distance difference
            expected_tdoa = (distance - ref_distance) / speed_of_light
            
            # Add squared error
            error_sum += (expected_tdoa - measurement.tdoa) ** 2
        
        return error_sum
    
    # Get all active receivers
    active_receivers = [r for r in receivers.values() if r.active]
    
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


def calculate_distance(coords1, coords2):
    """Calculate the great-circle distance between two points in meters"""
    lat1, lon1, alt1 = coords1
    lat2, lon2, alt2 = coords2
    
    # Calculate surface distance using Haversine formula
    surface_distance = haversine((lat1, lon1), (lat2, lon2), unit=Unit.METERS)
    
    # Add altitude component using Pythagorean theorem
    altitude_diff = alt2 - alt1
    
    # Total distance
    return (surface_distance**2 + altitude_diff**2) ** 0.5