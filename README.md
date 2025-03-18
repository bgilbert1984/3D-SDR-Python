# SDR Drone Pursuit System

A sophisticated real-time drone-based SDR signal monitoring and pursuit system with 3D visualization.

## Features

### SDR Integration
- Real-time SDR signal processing with RTL-SDR support
- Multiple modulation type detection (AM, FM, SSB, CW)
- Signal simulation capabilities for testing
- Automated SDR device discovery and configuration

### Drone Control
- Multi-drone swarm coordination
- Intelligent pursuit algorithms with AI-driven prediction
- Collision avoidance system
- Automated patrol modes with customizable patterns
- Dynamic role assignment (Lead, Triangulation, Backup, Scout)

### Signal Analysis
- Real-time signal detection and classification
- FCC violation monitoring
- Signal geolocation using TDOA/RSSI
- AI-powered signal movement prediction
- Spectrum visualization and waterfall displays

### 3D Visualization
- Real-time 3D mapping using CesiumJS
- Drone position and path tracking
- Signal strength visualization
- Violation highlighting and pursuit visualization
- Interactive control interface

## System Architecture

### Backend Components
- Python-based SDR controller
- WebSocket server for real-time communication
- MongoDB integration for data logging
- AI processing engine for signal classification
- Geolocation engine for signal source tracking

### Frontend Components
- CesiumJS 3D globe visualization
- Real-time signal visualization
- Interactive drone control interface
- Patrol route planning interface
- Violation monitoring dashboard

## Setup

### Prerequisites
- Python 3.7+
- Node.js 14+
- RTL-SDR hardware or simulation mode
- MongoDB (optional, for data logging)

### Python Dependencies
```bash
cd python
pip install -r requirements.txt
```

### Starting the System

1. Start the WebSocket server:
```bash
cd backend
node server.js
```

2. Launch the SDR controller:
```bash
cd python
python drone-sdr-controller.py
```

3. Open the web interface:
```bash
cd frontend
python -m http.server 8000
```

Then visit `http://localhost:8000/Drone-SDR-Pursuit-Interface.html`

## Configuration

The system uses several configuration files:
- `drone_config.json`: Drone and SDR parameters
- `patrol_config.json`: Patrol patterns and zones
- `ai_models/`: AI model files for signal classification

## Network Architecture

The system uses a multi-layer communication approach:
- 4G/LTE mesh network for primary drone communication
- Starlink backup for extended range operations
- WebSocket for real-time data streaming
- MAVLink for drone control

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Documentation

For detailed documentation about specific components:
- [Drone Control System](docs/drone-control.md)
- [SDR Integration](docs/sdr-integration.md)
- [AI Subsystems](docs/ai-systems.md)
- [Visualization Guide](docs/visualization.md)