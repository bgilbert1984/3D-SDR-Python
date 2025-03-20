"""
Geographic utility functions.

This module provides helper functions for geographic calculations.
"""

import math
from haversine import haversine, Unit


def calculate_distance(coords1, coords2):
    """
    Calculate the great-circle distance between two points in meters
    
    Args:
        coords1: Tuple of (latitude, longitude, altitude) for first point
        coords2: Tuple of (latitude, longitude, altitude) for second point
        
    Returns:
        Distance in meters
    """
    lat1, lon1, alt1 = coords1
    lat2, lon2, alt2 = coords2
    
    # Calculate surface distance using Haversine formula
    surface_distance = haversine((lat1, lon1), (lat2, lon2), unit=Unit.METERS)
    
    # Add altitude component using Pythagorean theorem
    altitude_diff = alt2 - alt1
    
    # Total distance
    return math.sqrt(surface_distance**2 + altitude_diff**2)


def get_point_at_distance(lat, lon, distance, bearing):
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