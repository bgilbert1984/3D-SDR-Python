// Add these patrol mode visualization functions to the CesiumJS visualization

// Add these new properties to the DroneSDRVisualizer class constructor
patrolRoutes = {};
patrolWaypoints = {};
signalHeatmap = null;
patrolZones = {};
patrolModeLabels = {
    'GRID': 'Grid Pattern',
    'SPIRAL': 'Spiral Pattern',
    'HOTSPOT': 'Hotspot Coverage',
    'PERIMETER': 'Perimeter Scan',
    'CUSTOM': 'Custom Route'
};
visitedWaypoints = {};
coverageHistory = [];

// Add these functions to the DroneSDRVisualizer class

// Process patrol route message
processPatrolRoute(data) {
    const droneId = data.drone_id;
    const patrolMode = data.patrol_mode;
    const waypoints = data.waypoints;
    
    // Clear existing route for this drone
    this.clearPatrolRoute(droneId);
    
    // Store waypoints
    this.patrolWaypoints[droneId] = waypoints;
    
    // Create route visualization
    const routePositions = [];
    const waypointEntities = [];
    
    waypoints.forEach((waypoint, index) => {
        const position = Cesium.Cartesian3.fromDegrees(waypoint[1], waypoint[0], 100);
        routePositions.push(position);
        
        // Create waypoint marker
        const waypointEntity = viewer.entities.add({
            id: `waypoint-${droneId}-${index}`,
            position: position,
            point: {
                pixelSize: 8,
                color: this.getPatrolModeColor(patrolMode),
                outlineColor: Cesium.Color.WHITE,
                outlineWidth: 2
            },
            label: {
                text: index.toString(),
                font: '12px sans-serif',
                fillColor: Cesium.Color.WHITE,
                style: Cesium.LabelStyle.FILL,
                verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
                pixelOffset: new Cesium.Cartesian2(0, -10),
                show: false // Only show label on hover
            }
        });
        
        waypointEntities.push(waypointEntity);
    });
    
    // Create route path
    let routeEntity = null;
    if (routePositions.length > 1) {
        routeEntity = viewer.entities.add({
            id: `patrol-route-${droneId}`,
            polyline: {
                positions: routePositions,
                width: 2,
                material: new Cesium.PolylineDashMaterialProperty({
                    color: this.getPatrolModeColor(patrolMode)
                })
            }
        });
    }
    
    // Store route
    this.patrolRoutes[droneId] = {
        mode: patrolMode,
        route: routeEntity,
        waypoints: waypointEntities,
        positions: routePositions
    };
    
    // Update UI
    this.updatePatrolStatusUI(droneId, patrolMode, waypoints.length);
}

// Get color for patrol mode
getPatrolModeColor(mode) {
    switch (mode) {
        case 'GRID':
            return Cesium.Color.YELLOW;
        case 'SPIRAL':
            return Cesium.Color.MAGENTA;
        case 'HOTSPOT':
            return Cesium.Color.RED;
        case 'PERIMETER':
            return Cesium.Color.CYAN;
        case 'CUSTOM':
            return Cesium.Color.GREEN;
        default:
            return Cesium.Color.WHITE;
    }
}

// Clear patrol route
clearPatrolRoute(droneId) {
    if (this.patrolRoutes[droneId]) {
        const route = this.patrolRoutes[droneId];
        
        // Remove route
        if (route.route) {
            viewer.entities.remove(route.route);
        }
        
        // Remove waypoints
        route.waypoints.forEach(waypoint => {
            viewer.entities.remove(waypoint);
        });
        
        delete this.patrolRoutes[droneId];
    }
    
    // Clear waypoints
    delete this.patrolWaypoints[droneId];
}

// Process waypoint visit
processWaypointVisit(data) {
    const droneId = data.drone_id;
    const waypointIndex = data.waypoint_index;
    const location = data.location;
    
    // Track visited waypoints
    if (!this.visitedWaypoints[droneId]) {
        this.visitedWaypoints[droneId] = [];
    }
    
    this.visitedWaypoints[droneId].push(waypointIndex);
    
    // Create visited marker
    const visitEntity = viewer.entities.add({
        id: `visit-${droneId}-${waypointIndex}-${Date.now()}`,
        position: Cesium.Cartesian3.fromDegrees(
            location.longitude,
            location.latitude,
            location.altitude
        ),
        point: {
            pixelSize: 10,
            color: Cesium.Color.LIME,
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 1
        },
        // Automatically fade out and disappear after 60 seconds
        availability: new Cesium.TimeIntervalCollection([
            new Cesium.TimeInterval({
                start: Cesium.JulianDate.now(),
                stop: Cesium.JulianDate.addSeconds(Cesium.JulianDate.now(), 60, new Cesium.JulianDate())
            })
        ])
    });
    
    // Update coverage history for heatmap
    this.coverageHistory.push({
        position: [location.latitude, location.longitude],
        timestamp: Date.now()
    });
    
    // Limit history size
    if (this.coverageHistory.length > 1000) {
        this.coverageHistory.shift();
    }
    
    // Update coverage visualization
    this.updateCoverageVisualization();
}

// Process signal detection
processSignalDetection(data) {
    const signal = data.signal;
    
    if (!signal.location) return;
    
    // Create signal marker
    const signalEntity = viewer.entities.add({
        id: `signal-${signal.frequency}-${Date.now()}`,
        position: Cesium.Cartesian3.fromDegrees(
            signal.location.longitude,
            signal.location.latitude,
            100
        ),
        point: {
            pixelSize: 8,
            color: this.getSignalColor(signal),
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 1
        },
        label: {
            text: `${(signal.frequency / 1e6).toFixed(3)} MHz\n${signal.modulation}`,
            font: '12px sans-serif',
            fillColor: Cesium.Color.WHITE,
            style: Cesium.LabelStyle.FILL,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            pixelOffset: new Cesium.Cartesian2(0, -10),
            show: false // Only show on hover
        }
    });
}

// Process violation detection
processViolationDetection(data) {
    const violation = data.violation;
    
    if (!violation.location) return;
    
    // Create violation marker with alert effect
    const position = Cesium.Cartesian3.fromDegrees(
        violation.location.longitude,
        violation.location.latitude,
        100
    );
    
    // Create marker
    const violationEntity = viewer.entities.add({
        id: `violation-${violation.frequency}-${Date.now()}`,
        position: position,
        point: {
            pixelSize: 15,
            color: Cesium.Color.RED,
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 2
        },
        label: {
            text: `VIOLATION\n${(violation.frequency / 1e6).toFixed(3)} MHz\n${violation.modulation}`,
            font: '14px sans-serif',
            fillColor: Cesium.Color.RED,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            outlineWidth: 2,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            pixelOffset: new Cesium.Cartesian2(0, -15)
        }
    });
    
    // Create pulse effect
    const pulseEntity = viewer.entities.add({
        id: `violation-pulse-${violation.frequency}-${Date.now()}`,
        position: position,
        ellipse: {
            semiMinorAxis: new Cesium.CallbackProperty((time) => {
                const pulse = 50 + 200 * Math.abs(Math.sin(Cesium.JulianDate.secondsDifference(time, Cesium.JulianDate.now()) * 0.5));
                return pulse;
            }, false),
            semiMajorAxis: new Cesium.CallbackProperty((time) => {
                const pulse = 50 + 200 * Math.abs(Math.sin(Cesium.JulianDate.secondsDifference(time, Cesium.JulianDate.now()) * 0.5));
                return pulse;
            }, false),
            material: Cesium.Color.RED.withAlpha(0.3),
            outline: true,
            outlineColor: Cesium.Color.RED.withAlpha(0.6),
            outlineWidth: 2,
            height: 100,
            heightReference: Cesium.HeightReference.RELATIVE_TO_GROUND
        }
    });
    
    // Update violation list UI
    this.updateViolationList(violation);
}

// Get color for signal based on strength
getSignalColor(signal) {
    // RSSI is typically negative, stronger signal = closer to 0
    const rssi = signal.rssi || -90;  // Default to weak
    
    // Normalize RSSI to 0-1 range (-30 to -90 dBm)
    const normalized = Math.max(0, Math.min(1, (rssi + 90) / 60));
    
    // Colorize based on signal strength
    if (signal.is_violation) {
        return Cesium.Color.RED;
    } else if (normalized > 0.7) {
        return Cesium.Color.GREEN;
    } else if (normalized > 0.4) {
        return Cesium.Color.YELLOW;
    } else {
        return Cesium.Color.BLUE;
    }
}

// Process pursuit started message
processPursuitStarted(data) {
    const droneId = data.drone_id;
    const violation = data.violation;
    
    if (!droneId || !violation || !violation.location) return;
    
    // Get drone
    const drone = this.drones[droneId];
    if (!drone) return;
    
    // Update drone visuals to pursuit mode
    if (drone.entity) {
        drone.entity.billboard.color = Cesium.Color.RED;
        
        // Add pursuit target marker
        const targetEntity = viewer.entities.add({
            id: `pursuit-target-${droneId}`,
            position: Cesium.Cartesian3.fromDegrees(
                violation.location.longitude,
                violation.location.latitude,
                100
            ),
            billboard: {
                image: 'assets/target.png',
                scale: 0.5,
                color: Cesium.Color.RED
            },
            label: {
                text: `Pursuit Target\n${(violation.frequency / 1e6).toFixed(3)} MHz`,
                font: '14px sans-serif',
                fillColor: Cesium.Color.RED,
                style: Cesium.LabelStyle.FILL,
                verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
                pixelOffset: new Cesium.Cartesian2(0, -30)
            }
        });
        
        // Add pursuit line
        const currentPosition = drone.entity.position.getValue(Cesium.JulianDate.now());
        const targetPosition = Cesium.Cartesian3.fromDegrees(
            violation.location.longitude,
            violation.location.latitude,
            100
        );
        
        const pursuitLine = viewer.entities.add({
            id: `pursuit-line-${droneId}`,
            polyline: {
                positions: [currentPosition, targetPosition],
                width: 3,
                material: new Cesium.PolylineDashMaterialProperty({
                    color: Cesium.Color.RED
                })
            }
        });
        
        // Store pursuit entities with drone
        drone.pursuitEntities = {
            target: targetEntity,
            line: pursuitLine
        };
    }
    
    // Update UI
    this.updateDroneStatusUI(droneId, 'PURSUIT');
}

// Process pursuit arrived message
processPursuitArrived(data) {
    const droneId = data.drone_id;
    const location = data.location;
    
    if (!droneId || !location) return;
    
    // Get drone
    const drone = this.drones[droneId];
    if (!drone) return;
    
    // Create arrived marker
    const arrivedEntity = viewer.entities.add({
        id: `pursuit-arrived-${droneId}-${Date.now()}`,
        position: Cesium.Cartesian3.fromDegrees(
            location.longitude,
            location.latitude,
            100
        ),
        point: {
            pixelSize: 15,
            color: Cesium.Color.GREEN,
            outlineColor: Cesium.Color.WHITE,
            outlineWidth: 2
        },
        label: {
            text: `Violation Located`,
            font: '14px sans-serif',
            fillColor: Cesium.Color.GREEN,
            style: Cesium.LabelStyle.FILL,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            pixelOffset: new Cesium.Cartesian2(0, -15)
        },
        // Auto-hide after 30 seconds
        availability: new Cesium.TimeIntervalCollection([
            new Cesium.TimeInterval({
                start: Cesium.JulianDate.now(),
                stop: Cesium.JulianDate.addSeconds(Cesium.JulianDate.now(), 30, new Cesium.JulianDate())
            })
        ])
    });
}

// Process patrol resumed message
processPatrolResumed(data) {
    const droneId = data.drone_id;
    
    if (!droneId) return;
    
    // Get drone
    const drone = this.drones[droneId];
    if (!drone) return;
    
    // Update drone visuals to patrol mode
    if (drone.entity) {
        drone.entity.billboard.color = Cesium.Color.DODGERBLUE;
        
        // Remove pursuit entities
        if (drone.pursuitEntities) {
            if (drone.pursuitEntities.target) {
                viewer.entities.remove(drone.pursuitEntities.target);
            }
            if (drone.pursuitEntities.line) {
                viewer.entities.remove(drone.pursuitEntities.line);
            }
            delete drone.pursuitEntities;
        }
    }
    
    // Update UI
    this.updateDroneStatusUI(droneId, 'PATROL');
}

// Update drone status in UI
updateDroneStatusUI(droneId, operationMode) {
    const droneItem = document.querySelector(`.drone-item[data-id="${droneId}"]`);
    if (!droneItem) return;
    
    const statusEl = droneItem.querySelector('.operation-mode');
    if (statusEl) {
        statusEl.textContent = operationMode;
        statusEl.className = `operation-mode mode-${operationMode.toLowerCase()}`;
    }
}

// Update patrol status in UI
updatePatrolStatusUI(droneId, patrolMode, waypointCount) {
    const droneItem = document.querySelector(`.drone-item[data-id="${droneId}"]`);
    if (!droneItem) return;
    
    const patrolEl = droneItem.querySelector('.patrol-mode');
    if (patrolEl) {
        patrolEl.textContent = this.patrolModeLabels[patrolMode] || patrolMode;
    }
    
    const waypointsEl = droneItem.querySelector('.waypoint-count');
    if (waypointsEl) {
        waypointsEl.textContent = `${waypointCount} waypoints`;
    }
}

// Process patrol zone data
processPatrolZone(data) {
    const zone = data.zone;
    
    if (!zone || !zone.name || !zone.boundaries) return;
    
    // Clear existing zone if present
    this.clearPatrolZone(zone.name);
    
    // Extract boundaries
    const [lat_min, lon_min, lat_max, lon_max] = zone.boundaries;
    
    // Create zone rectangle
    const zoneEntity = viewer.entities.add({
        id: `patrol-zone-${zone.name}`,
        name: `Patrol Zone: ${zone.name}`,
        rectangle: {
            coordinates: Cesium.Rectangle.fromDegrees(lon_min, lat_min, lon_max, lat_max),
            material: new Cesium.ColorMaterialProperty(
                Cesium.Color.fromCssColorString('#3388ff').withAlpha(0.2)
            ),
            outline: true,
            outlineColor: Cesium.Color.fromCssColorString('#3388ff').withAlpha(0.7),
            outlineWidth: 2,
            height: 0,
            heightReference: Cesium.HeightReference.CLAMP_TO_GROUND
        },
        label: {
            text: zone.name,
            font: '16px sans-serif',
            fillColor: Cesium.Color.WHITE,
            style: Cesium.LabelStyle.FILL,
            verticalOrigin: Cesium.VerticalOrigin.TOP,
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            pixelOffset: new Cesium.Cartesian2(0, 10)
        }
    });
    
    // Create hotspot markers if present
    const hotspotEntities = [];
    
    if (zone.hotspots && zone.hotspots.length > 0) {
        zone.hotspots.forEach((hotspot, index) => {
            const [lat, lon, weight] = hotspot;
            
            // Scale size and color by weight
            const size = 10 + 5 * Math.min(5, weight);
            const color = this.getHotspotColor(weight);
            
            const hotspotEntity = viewer.entities.add({
                id: `hotspot-${zone.name}-${index}`,
                position: Cesium.Cartesian3.fromDegrees(lon, lat, 10),
                point: {
                    pixelSize: size,
                    color: color,
                    outlineColor: Cesium.Color.WHITE,
                    outlineWidth: 2
                },
                label: {
                    text: `Hotspot (${weight.toFixed(1)})`,
                    font: '12px sans-serif',
                    fillColor: Cesium.Color.WHITE,
                    style: Cesium.LabelStyle.FILL,
                    verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                    horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
                    pixelOffset: new Cesium.Cartesian2(0, -10),
                    show: false // Only show on hover
                }
            });
            
            hotspotEntities.push(hotspotEntity);
        });
    }
    
    // Store zone entities
    this.patrolZones[zone.name] = {
        zone: zoneEntity,
        hotspots: hotspotEntities,
        data: zone
    };
    
    // Update zone list UI
    this.updateZoneListUI();
}

// Clear patrol zone
clearPatrolZone(zoneName) {
    if (this.patrolZones[zoneName]) {
        const zone = this.patrolZones[zoneName];
        
        // Remove zone
        if (zone.zone) {
            viewer.entities.remove(zone.zone);
        }
        
        // Remove hotspots
        zone.hotspots.forEach(hotspot => {
            viewer.entities.remove(hotspot);
        });
        
        delete this.patrolZones[zoneName];
    }
}

// Get color for hotspot based on weight
getHotspotColor(weight) {
    // Normalize weight to 0-1 range
    const normalized = Math.min(1, weight / 5.0);
    
    // Color from yellow to red
    return Cesium.Color.fromHsl(
        0.1 - normalized * 0.1,  // Hue from yellow to red
        1.0,                     // Saturation
        0.5                      // Lightness
    );
}

// Update zone list UI
updateZoneListUI() {
    const zoneList = document.getElementById('zoneList');
    if (!zoneList) return;
    
    zoneList.innerHTML = '';
    
    Object.entries(this.patrolZones).forEach(([name, zone]) => {
        const zoneItem = document.createElement('div');
        zoneItem.className = 'zone-item';
        zoneItem.innerHTML = `
            <div class="zone-name">${name}</div>
            <div class="zone-stats">
                Hotspots: ${zone.data.hotspots ? zone.data.hotspots.length : 0}
            </div>
            <div class="zone-actions">
                <button class="zone-focus-btn" data-zone="${name}">Focus</button>
            </div>
        `;
        
        // Add focus button handler
        zoneItem.querySelector('.zone-focus-btn').addEventListener('click', () => {
            this.focusOnZone(name);
        });
        
        zoneList.appendChild(zoneItem);
    });
    
    // Empty state
    if (Object.keys(this.patrolZones).length === 0) {
        zoneList.innerHTML = '<div class="empty-list">No patrol zones defined</div>';
    }
}

// Focus camera on zone
focusOnZone(zoneName) {
    const zone = this.patrolZones[zoneName];
    if (!zone) return;
    
    const boundaries = zone.data.boundaries;
    const [lat_min, lon_min, lat_max, lon_max] = boundaries;
    
    // Create rectangle to focus on
    const rectangle = Cesium.Rectangle.fromDegrees(lon_min, lat_min, lon_max, lat_max);
    
    // Fly to rectangle
    viewer.camera.flyTo({
        destination: rectangle,
        duration: 2
    });
}

// Update coverage visualization (heatmap)
updateCoverageVisualization() {
    // Only update periodically to avoid performance issues
    const now = Date.now();
    if (this.lastCoverageUpdate && now - this.lastCoverageUpdate < 10000) {
        return;
    }
    
    this.lastCoverageUpdate = now;
    
    // Remove existing heatmap if any
    if (this.signalHeatmap) {
        viewer.scene.primitives.remove(this.signalHeatmap);
        this.signalHeatmap = null;
    }
    
    // Not enough data for meaningful heatmap
    if (this.coverageHistory.length < 10) {
        return;
    }
    
    // Extract positions for heatmap
    const positions = this.coverageHistory.map(h => Cesium.Cartesian3.fromDegrees(
        h.position[1], h.position[0], 10
    ));
    
    // Create primitive for heatmap
    // For simplicity, we're just showing points with varied colors instead of a true heatmap
    // In a full implementation, you might use a library like heatmap.js with CesiumJS
    const pointPrimitives = viewer.scene.primitives.add(new Cesium.PointPrimitiveCollection());
    
    positions.forEach((position, index) => {
        // Age of point (0-1, 1 being newest)
        const age = (this.coverageHistory[index].timestamp - this.coverageHistory[0].timestamp) /
                   (now - this.coverageHistory[0].timestamp);
        
        pointPrimitives.add({
            position: position,
            color: Cesium.Color.fromHsl(0.6, 0.7, 0.5, Math.max(0.2, age)),
            pixelSize: 5 + 5 * age,
            scaleByDistance: new Cesium.NearFarScalar(1000, 1, 50000, 0.5)
        });
    });
    
    this.signalHeatmap = pointPrimitives;
}

// Add this to the processData method to handle patrol-related messages
processData(data) {
    // Existing message handling code...
    
    // Add these cases
    if (data.type === 'patrol_route') {
        this.processPatrolRoute(data);
    } else if (data.type === 'waypoint_visit') {
        this.processWaypointVisit(data);
    } else if (data.type === 'signal_detected') {
        this.processSignalDetection(data);
    } else if (data.type === 'violation_detected') {
        this.processViolationDetection(data);
    } else if (data.type === 'pursuit_started') {
        this.processPursuitStarted(data);
    } else if (data.type === 'pursuit_arrived') {
        this.processPursuitArrived(data);
    } else if (data.type === 'patrol_resumed') {
        this.processPatrolResumed(data);
    } else if (data.type === 'patrol_zone') {
        this.processPatrolZone(data);
    }
}

// Update the drone UI to include patrol information
updateDroneList() {
    const droneList = document.getElementById('droneList');
    droneList.innerHTML = '';
    
    // Add each drone to the list
    Object.values(this.drones).forEach(drone => {
        const droneItem = document.createElement('div');
        droneItem.className = 'list-item drone-item';
        droneItem.dataset.id = drone.id;
        
        const statusClass = drone.isPursuing ? 'mode-pursuit' : 'mode-patrol';
        const operationMode = drone.isPursuing ? 'PURSUIT' : 'PATROL';
        
        droneItem.innerHTML = `
            <div class="item-header">
                <span class="item-title">Drone ${drone.id}</span>
                <span class="operation-mode ${statusClass}">${operationMode}</span>
            </div>
            <div class="item-details">
                <div class="battery-indicator" style="width: ${drone.battery || 0}%"></div>
                <span class="battery-value">${drone.battery || 0}%</span>
                <div class="patrol-info">
                    <span class="patrol-mode">Unknown</span>
                    <span class="waypoint-count">0 waypoints</span>
                </div>
            </div>
            <div class="item-actions">
                <button class="track-button" data-id="${drone.id}">Track</button>
                <button class="command-button" data-cmd="start_patrol" data-id="${drone.id}">Patrol</button>
            </div>
        `;
        
        // Add click handler for tracking
        droneItem.querySelector('.track-button').addEventListener('click', () => {
            this.trackDrone(drone.id);
        });
        
        // Add click handler for patrol command
        droneItem.querySelector('.command-button[data-cmd="start_patrol"]').addEventListener('click', () => {
            this.sendDroneCommand('start_patrol', drone.id);
        });
        
        droneList.appendChild(droneItem);
        
        // Update patrol info if available
        if (this.patrolRoutes[drone.id]) {
            const patrolRoute = this.patrolRoutes[drone.id];
            this.updatePatrolStatusUI(drone.id, patrolRoute.mode, patrolRoute.waypoints.length);
        }
    });
    
    // If no drones, show message
    if (Object.keys(this.drones).length === 0) {
        droneList.innerHTML = '<div class="empty-list">No drones connected</div>';
    }
}

// Send command to start patrol
sendDroneCommand(command, droneId) {
    if (!this.socket || !droneId) {
        return;
    }
    
    let data = {
        type: 'command',
        command: command,
        drone_id: droneId
    };
    
    // Add command-specific parameters
    if (command === 'start_patrol') {
        // Get patrol mode from dropdown
        const patrolModeSelect = document.getElementById('patrolModeSelect');
        if (patrolModeSelect) {
            data.patrol_mode = patrolModeSelect.value;
        }
        
        // Get zone name from dropdown
        const zoneSelect = document.getElementById('zoneSelect');
        if (zoneSelect) {
            data.zone_name = zoneSelect.value;
        }
    }
    
    this.socket.send(JSON.stringify(data));
}

// Additional UI for patrol controls (add this to HTML)
// 
// <div class="control-section">
//   <h3>Patrol Settings</h3>
//   <select id="patrolModeSelect">
//     <option value="GRID">Grid Pattern</option>
//     <option value="SPIRAL">Spiral Pattern</option>
//     <option value="PERIMETER">Perimeter Scan</option>
//     <option value="HOTSPOT">Hotspot Coverage</option>
//   </select>
//   <select id="zoneSelect">
//     <option value="">Select Zone</option>
//   </select>
// </div>
// 
// <div class="sidebar-tab" data-tab="zones">Zones</div>
// <div class="tab-content" id="zones-tab">
//   <div class="section-header">Patrol Zones</div>
//   <div id="zoneList">
//     <div class="empty-list">No zones defined</div>
//   </div>
// </div>

// Add these style definitions to your CSS:
// 
// .mode-patrol { background-color: #3498db; }
// .mode-pursuit { background-color: #e74c3c; }
// .mode-triangulation { background-color: #2ecc71; }
// .mode-returning { background-color: #f39c12; }
// .mode-standby { background-color: #7f8c8d; }
// 
// .patrol-info {
//   margin-top: 5px;
//   font-size: 12px;
//   color: #bdc3c7;
// }
// 
// .zone-item {
//   background-color: #2c3e50;
//   border-radius: 4px;
//   margin-bottom: 10px;
//   padding: 12px;
// }
// 
// .zone-name {
//   font-weight: 500;
//   margin-bottom: 5px;
// }
// 
// .zone-stats {
//   font-size: 12px;
//   color: #bdc3c7;
//   margin-bottom: 8px;
// }
// 
// .zone-actions {
//   display: flex;
//   gap: 8px;
// }
// 
// .zone-focus-btn {
//   flex: 1;
//   padding: 6px;
//   border: none;
//   border-radius: 3px;
//   background-color: #3498db;
//   color: white;
//   cursor: pointer;
//   font-size: 12px;
// }
