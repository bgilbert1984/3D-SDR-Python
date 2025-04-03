# Patrol Mode Controller Documentation

## Overview
The Patrol Mode Controller is a sophisticated system that manages autonomous drone operations for signal detection and monitoring. It integrates Software Defined Radio (SDR) capabilities with drone control to perform various patrol patterns while scanning for radio signals and potential violations.

## Features

### Patrol Modes
The controller supports multiple patrol patterns:
- **Grid**: Systematic coverage using a configurable grid pattern
- **Spiral**: Outward spiral pattern from center point
- **Hotspot**: AI-optimized route based on historical violation locations
- **Perimeter**: Boundary patrol of the designated area
- **Custom**: User-defined waypoint sequences

### Operation Modes
- **PATROL**: Normal patrol operations following configured patterns
- **PURSUIT**: Active pursuit of detected violations
- **TRIANGULATION**: Supporting multi-drone signal source location
- **RETURNING**: Returning to base location
- **STANDBY**: Awaiting commands

### SDR Integration
- Continuous spectrum monitoring during patrol
- Configurable frequency bands
- Signal classification and violation detection
- Real-time signal strength monitoring
- Historical signal tracking

### Safety Features
- Collision avoidance system for multi-drone operations
- Altitude adjustment for drone separation
- Timeout mechanisms for pursuit operations
- Battery level monitoring
- Safe return-to-home capabilities

### Smart Features
- Dynamic hotspot generation from violation history
- Adaptive pursuit with real-time target updates
- Inter-drone coordination for efficient violation tracking
- Optimized route planning for maximum coverage
- WebSocket-based real-time status updates and visualization

## Configuration

### Patrol Zone Configuration
```json
{
    "name": "Zone Name",
    "boundaries": [lat_min, lon_min, lat_max, lon_max],
    "altitude_range": [min_alt, max_alt],
    "priority": priority_level
}
```

### Spectrum Configuration
```json
{
    "frequency_bands": [
        [start_freq, end_freq],
        ...
    ],
    "center_freq": center_frequency,
    "sample_rate": sample_rate,
    "gain": gain_value
}
```

## Operation

### Initialization
1. Environment setup for SDR libraries
2. Drone connection establishment
3. WebSocket connection for coordination
4. Patrol zone and configuration loading

### Normal Operation Flow
1. Takeoff to designated altitude
2. Generate patrol route based on selected mode
3. Navigate through waypoints while scanning
4. Process detected signals
5. Handle violations when detected
6. Coordinate with other drones as needed

### Violation Response
1. Signal detection and classification
2. Violation confirmation
3. Mode switch to pursuit if warranted
4. Coordinate with other drones
5. Track and monitor violation
6. Return to patrol after resolution

### Safety Procedures
1. Regular collision risk assessment
2. Altitude adjustment for separation
3. Timeout-based operation limits
4. Emergency return procedures
5. Landing protocols

## Integration

### WebSocket Messages
The controller communicates using JSON messages for:
- Drone registration
- Status updates
- Violation reports
- Pursuit coordination
- Command reception

### Visualization Integration
Provides real-time data for:
- Drone positions
- Patrol routes
- Signal detections
- Violation locations
- Pursuit tracking

### Multi-Drone Coordination
- Shared violation detection
- Coordinated pursuit decisions
- Dynamic task allocation
- Collision avoidance

## Command Interface

### Available Commands
- `takeoff`: Start drone operations
- `start_patrol`: Begin patrol operations
- `stop_patrol`: Halt patrol operations
- `change_zone`: Switch patrol zones
- `change_patrol_mode`: Switch patrol patterns
- `goto`: Direct movement command
- `return_home`: Return to base
- `land`: End operations and land