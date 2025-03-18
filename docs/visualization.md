# Visualization Guide

## Overview

The visualization system uses CesiumJS for 3D rendering of drone operations, signal data, and pursuit activities.

## Main Components

### Map Display
- CesiumJS 3D globe
- Terrain visualization
- Multiple viewing modes (3D, 2D, Columbus)
- Camera controls

### UI Elements
- Drone status panel
- Signal list
- Violation alerts
- Control interface
- Layer toggles

## Visualization Features

### Drone Visualization
- Real-time position tracking
- Flight path history
- Battery status indication
- Role-based coloring
- Pursuit vectors

### Signal Display
```javascript
// Signal visualization parameters
const COLORS = {
    DRONE: Cesium.Color.DODGERBLUE,
    SIGNAL: Cesium.Color.SPRINGGREEN,
    VIOLATION: Cesium.Color.RED,
    PATH: Cesium.Color.YELLOW.withAlpha(0.5),
    PREDICTION: Cesium.Color.MAGENTA.withAlpha(0.7)
};
```

### Signal Modulation Colors
- AM: Light blue
- FM: Green
- SSB: Orange
- CW: Yellow
- Digital modes: Custom colors
- Unknown: Gray

## Interactive Features

### Camera Controls
- Drone tracking
- Signal location focus
- Smooth transitions
- Multiple viewpoints

### Control Interface
- Drone selection
- Command buttons
- Layer toggles
- Status indicators

## Layer Management

### Available Layers
- Drones
- Signals
- Violations
- Flight paths
- Predictions
- Coverage areas

### Layer Controls
```javascript
toggleLayer(layer, visible) {
    switch (layer) {
        case 'drones':
            this.droneEntities.show = visible;
            break;
        case 'signals':
            this.signalEntities.show = visible;
            break;
        // ... other layers
    }
}
```

## WebSocket Integration

### Data Flow
1. Receive real-time updates
2. Process data
3. Update visualizations
4. Refresh UI elements

### Update Types
- Drone positions
- Signal detections
- Violations
- Pursuit status
- Coverage data

## API Reference

### Visualization Methods
```javascript
updateDrone(data)           // Update drone visualization
updateSignal(data)         // Update signal marker
updateViolation(data)      // Update violation display
trackDrone(droneId)        // Focus camera on drone
toggleLayer(layer, visible) // Control layer visibility
```

### UI Update Methods
```javascript
updateDroneList()          // Refresh drone panel
updateSignalList()         // Update signal list
updateViolationList()      // Update violation alerts
updateStats()              // Update statistics
```