# Patrol Visualization Documentation

## Overview
The patrol visualization module enhances the CesiumJS-based visualization by adding features for drone patrol routes, waypoint tracking, signal detection, and violation handling. This document outlines the key functionalities and how they are implemented.

## Features

### Patrol Routes
- **Patrol Modes**: Supports multiple patrol modes, including:
  - Grid Pattern
  - Spiral Pattern
  - Hotspot Coverage
  - Perimeter Scan
  - Custom Route
- **Visualization**:
  - Waypoints are displayed as markers with labels.
  - Routes are visualized as dashed polylines.
  - Colors are used to differentiate patrol modes.

### Waypoint Tracking
- Tracks visited waypoints and marks them on the map.
- Automatically fades out visited markers after 60 seconds.

### Signal Detection
- Displays detected signals as markers with frequency and modulation labels.
- Colors indicate signal strength and whether it is a violation.

### Violation Handling
- Marks violations with red markers and labels.
- Adds a pulse effect to highlight violations.
- Supports pursuit mode visualization with target markers and pursuit lines.

### Patrol Zones
- Visualizes patrol zones as rectangles with optional hotspot markers.
- Hotspots are scaled and colored based on their weight.
- Provides UI for managing and focusing on zones.

### Heatmap Visualization
- Displays a heatmap of coverage history using point primitives.
- Updates periodically to avoid performance issues.

## UI Integration

### Drone List
- Displays a list of connected drones with their status and patrol information.
- Includes buttons for tracking drones and sending patrol commands.

### Patrol Controls
- Dropdowns for selecting patrol mode and zone.
- Buttons for starting patrols.

### Zone List
- Displays a list of defined patrol zones with hotspot statistics.
- Includes buttons for focusing on specific zones.

## Implementation Details

### Key Methods
- `processPatrolRoute(data)`: Handles patrol route messages and visualizes routes and waypoints.
- `processWaypointVisit(data)`: Tracks visited waypoints and updates the heatmap.
- `processSignalDetection(data)`: Visualizes detected signals with markers and labels.
- `processViolationDetection(data)`: Highlights violations with markers and pulse effects.
- `processPatrolZone(data)`: Visualizes patrol zones and hotspots.
- `updateCoverageVisualization()`: Updates the heatmap based on coverage history.

### Helper Methods
- `getPatrolModeColor(mode)`: Returns the color for a given patrol mode.
- `getSignalColor(signal)`: Returns the color for a signal based on its strength.
- `getHotspotColor(weight)`: Returns the color for a hotspot based on its weight.

### UI Update Methods
- `updateDroneStatusUI(droneId, operationMode)`: Updates the drone status in the UI.
- `updatePatrolStatusUI(droneId, patrolMode, waypointCount)`: Updates patrol information in the UI.
- `updateZoneListUI()`: Updates the list of patrol zones in the UI.

## CSS Styles
- Includes styles for patrol modes, zone items, and drone list elements.
- Example classes:
  - `.mode-patrol`, `.mode-pursuit`
  - `.zone-item`, `.zone-focus-btn`

## Example Usage

### Starting a Patrol
1. Select a patrol mode and zone from the dropdowns.
2. Click the "Patrol" button next to the desired drone in the drone list.

### Viewing Patrol Zones
1. Open the "Zones" tab in the sidebar.
2. Click the "Focus" button next to a zone to center the camera on it.

### Handling Violations
1. Violations are automatically highlighted on the map.
2. Use the drone list to track drones in pursuit mode.

## Future Enhancements
- Add support for dynamic heatmap generation using external libraries.
- Integrate real-time analytics for patrol efficiency.
- Expand patrol modes with additional patterns and behaviors.