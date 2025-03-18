# Drone Control System Documentation

## Overview

The drone control system is built around the DroneSDRController class, which manages individual drones, and the DroneSwarmController class for coordinating multiple drones.

## Features

### Swarm Coordination
- Dynamic role assignment (Lead, Triangulation, Backup, Scout)
- Collision avoidance with configurable safe distances
- Automated leader election for pursuit operations
- Formation control for optimal signal triangulation

### Flight Control
- Automated takeoff and landing
- Return-to-home functionality
- Configurable altitude and speed limits
- MAVLink-based command and control
- Real-time telemetry monitoring

### Patrol Modes
- Grid search pattern
- Spiral search pattern
- Hotspot coverage
- Perimeter scanning
- Custom waypoint routes

## Configuration

### drone_config.json
```json
{
    "drone_id": "drone1",
    "connection_string": "udp:127.0.0.1:14550",
    "websocket_url": "ws://localhost:8766",
    "flight_parameters": {
        "altitude": 100,
        "speed": 10,
        "max_distance": 2000,
        "home_location": [37.7749, -122.4194, 0]
    }
}
```

## Safety Features

### Collision Avoidance
- Minimum separation distance: 15 meters
- Dynamic altitude adjustment
- Predictive trajectory analysis
- Emergency maneuver system

### Failsafes
- Low battery return-to-home
- Signal loss contingency
- Geofencing
- Maximum range limits
- Emergency landing protocols

## API Reference

### DroneSDRController Methods
```python
connect_drone()      # Initialize drone connection
takeoff()           # Automated takeoff sequence
pursue_signal()     # Begin signal pursuit
return_to_home()    # Return to launch point
process_sdr_data()  # Handle incoming SDR data
```

### DroneSwarmController Methods
```python
elect_swarm_leader()         # Leader election process
set_role()                   # Assign drone roles
start_pursuit()              # Coordinate pursuit
triangulation_behavior()     # Position for triangulation
calculate_backup_position()  # Calculate support positions
```