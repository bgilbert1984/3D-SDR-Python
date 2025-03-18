// Add these collision detection functions to drone-pursuit-visualization.js

// After initializing all the main visualization components, add these methods to the DroneSDRVisualizer class:

// Add this to the DroneSDRVisualizer class constructor
visualizeSafeZones = true;
collisionWarnings = {};
safeZoneEntities = {};
minSeparationDistance = 15; // meters - must match drone controller setting

// Add these functions to the DroneSDRVisualizer class

checkCollisionRisks() {
    // Clear old warnings
    this.clearCollisionWarnings();
    
    // Get all drone positions
    const dronePositions = {};
    
    // Add this drone's positions
    Object.values(this.drones).forEach(drone => {
        const position = drone.entity.position.getValue(Cesium.JulianDate.now());
        if (position) {
            const cartographic = Cesium.Cartographic.fromCartesian(position);
            dronePositions[drone.id] = {
                position: position,
                latitude: Cesium.Math.toDegrees(cartographic.latitude),
                longitude: Cesium.Math.toDegrees(cartographic.longitude),
                altitude: cartographic.height,
                drone: drone
            };
        }
    });
    
    // Check distance between all drone pairs
    const droneIds = Object.keys(dronePositions);
    for (let i = 0; i < droneIds.length; i++) {
        for (let j = i + 1; j < droneIds.length; j++) {
            const drone1 = dronePositions[droneIds[i]];
            const drone2 = dronePositions[droneIds[j]];
            
            // Calculate horizontal distance using haversine formula
            const distance = this.calculateDistance(
                drone1.latitude, drone1.longitude,
                drone2.latitude, drone2.longitude
            );
            
            // If drones are too close, show warning
            if (distance < this.minSeparationDistance) {
                this.showCollisionWarning(drone1, drone2, distance);
            }
        }
    }
}

calculateDistance(lat1, lon1, lat2, lon2) {
    // Haversine formula for calculating distance between two points on earth
    const R = 6371000; // Earth's radius in meters
    const dLat = this.toRadians(lat2 - lat1);
    const dLon = this.toRadians(lon2 - lon1);
    const a = 
        Math.sin(dLat/2) * Math.sin(dLat/2) +
        Math.cos(this.toRadians(lat1)) * Math.cos(this.toRadians(lat2)) * 
        Math.sin(dLon/2) * Math.sin(dLon/2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1-a));
    const distance = R * c;
    return distance;
}

toRadians(degrees) {
    return degrees * Math.PI / 180;
}

showCollisionWarning(drone1, drone2, distance) {
    const warningId = `collision-${drone1.drone.id}-${drone2.drone.id}`;
    
    // If warning already exists, just update it
    if (this.collisionWarnings[warningId]) {
        this.updateCollisionWarning(warningId, drone1, drone2, distance);
        return;
    }
    
    // Create warning entity
    const midpoint = Cesium.Cartesian3.midpoint(
        drone1.position,
        drone2.position,
        new Cesium.Cartesian3()
    );
    
    // Create warning text entity
    const warningEntity = viewer.entities.add({
        id: warningId,
        position: midpoint,
        label: {
            text: `COLLISION RISK\n${distance.toFixed(1)}m`,
            font: '16px sans-serif',
            fillColor: Cesium.Color.RED,
            outlineColor: Cesium.Color.BLACK,
            outlineWidth: 2,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            verticalOrigin: Cesium.VerticalOrigin.CENTER,
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            pixelOffset: new Cesium.Cartesian2(0, 0),
            disableDepthTestDistance: Number.POSITIVE_INFINITY
        }
    });
    
    // Create line between drones
    const lineEntity = viewer.entities.add({
        id: `${warningId}-line`,
        polyline: {
            positions: [drone1.position, drone2.position],
            width: 2,
            material: new Cesium.PolylineDashMaterialProperty({
                color: Cesium.Color.RED
            })
        }
    });
    
    // Store warning entities
    this.collisionWarnings[warningId] = {
        warning: warningEntity,
        line: lineEntity,
        drone1: drone1.drone.id,
        drone2: drone2.drone.id
    };
    
    // Visualize safe zones if enabled
    if (this.visualizeSafeZones) {
        this.visualizeSafeZone(drone1.drone.id, drone1);
        this.visualizeSafeZone(drone2.drone.id, drone2);
    }
    
    // Update statistics display
    this.updateCollisionStats();
}

updateCollisionWarning(warningId, drone1, drone2, distance) {
    const warning = this.collisionWarnings[warningId];
    if (!warning) return;
    
    // Update warning text
    warning.warning.label.text = `COLLISION RISK\n${distance.toFixed(1)}m`;
    
    // Update warning position
    const midpoint = Cesium.Cartesian3.midpoint(
        drone1.position,
        drone2.position,
        new Cesium.Cartesian3()
    );
    warning.warning.position = midpoint;
    
    // Update line positions
    warning.line.polyline.positions = [drone1.position, drone2.position];
    
    // Update safe zone visuals if enabled
    if (this.visualizeSafeZones) {
        this.visualizeSafeZone(drone1.drone.id, drone1);
        this.visualizeSafeZone(drone2.drone.id, drone2);
    }
}

clearCollisionWarnings() {
    // Remove old warnings that aren't valid anymore
    Object.entries(this.collisionWarnings).forEach(([id, warning]) => {
        const drone1 = this.drones[warning.drone1];
        const drone2 = this.drones[warning.drone2];
        
        // If either drone is no longer in the scene, remove the warning
        if (!drone1 || !drone2) {
            viewer.entities.removeById(id);
            viewer.entities.removeById(`${id}-line`);
            delete this.collisionWarnings[id];
            return;
        }
        
        // Check if drones are still too close
        const position1 = drone1.entity.position.getValue(Cesium.JulianDate.now());
        const position2 = drone2.entity.position.getValue(Cesium.JulianDate.now());
        
        if (!position1 || !position2) return;
        
        const cartographic1 = Cesium.Cartographic.fromCartesian(position1);
        const cartographic2 = Cesium.Cartographic.fromCartesian(position2);
        
        const lat1 = Cesium.Math.toDegrees(cartographic1.latitude);
        const lon1 = Cesium.Math.toDegrees(cartographic1.longitude);
        const lat2 = Cesium.Math.toDegrees(cartographic2.latitude);
        const lon2 = Cesium.Math.toDegrees(cartographic2.longitude);
        
        const distance = this.calculateDistance(lat1, lon1, lat2, lon2);
        
        // If drones are now far enough apart, remove the warning
        if (distance >= this.minSeparationDistance) {
            viewer.entities.removeById(id);
            viewer.entities.removeById(`${id}-line`);
            delete this.collisionWarnings[id];
            
            // Remove safe zone visualization
            this.removeSafeZone(warning.drone1);
            this.removeSafeZone(warning.drone2);
        }
    });
    
    // Update statistics display
    this.updateCollisionStats();
}

updateCollisionStats() {
    // Update the collision count in the UI
    const collisionCount = Object.keys(this.collisionWarnings).length;
    const collisionStatsEl = document.getElementById('collisionCount');
    if (collisionStatsEl) {
        collisionStatsEl.textContent = collisionCount;
    }
    
    // Update collision warning panel
    const collisionPanel = document.getElementById('collisionPanel');
    if (collisionPanel) {
        if (collisionCount > 0) {
            collisionPanel.style.display = 'block';
            
            const collisionList = document.getElementById('collisionList');
            if (collisionList) {
                collisionList.innerHTML = '';
                
                Object.entries(this.collisionWarnings).forEach(([id, warning]) => {
                    const drone1 = this.drones[warning.drone1];
                    const drone2 = this.drones[warning.drone2];
                    
                    const warningItem = document.createElement('div');
                    warningItem.className = 'collision-item';
                    warningItem.innerHTML = `
                        <div class="collision-header">
                            <span>Collision Risk</span>
                        </div>
                        <div class="collision-details">
                            Between: ${drone1 ? drone1.id : warning.drone1} and ${drone2 ? drone2.id : warning.drone2}
                        </div>
                    `;
                    
                    collisionList.appendChild(warningItem);
                });
            }
        } else {
            collisionPanel.style.display = 'none';
        }
    }
}

visualizeSafeZone(droneId, droneInfo) {
    // Remove existing safe zone if any
    this.removeSafeZone(droneId);
    
    // Create a circle showing safe zone
    const safeZone = viewer.entities.add({
        id: `safezone-${droneId}`,
        position: droneInfo.position,
        ellipse: {
            semiMinorAxis: this.minSeparationDistance,
            semiMajorAxis: this.minSeparationDistance,
            material: Cesium.Color.RED.withAlpha(0.3),
            outline: true,
            outlineColor: Cesium.Color.RED.withAlpha(0.7),
            outlineWidth: 2,
            height: droneInfo.altitude,
            heightReference: Cesium.HeightReference.RELATIVE_TO_GROUND
        }
    });
    
    // Store reference
    this.safeZoneEntities[droneId] = safeZone;
}

removeSafeZone(droneId) {
    if (this.safeZoneEntities[droneId]) {
        viewer.entities.removeById(`safezone-${droneId}`);
        delete this.safeZoneEntities[droneId];
    }
}

// In the updateDrone method, add this section to update drone colors based on role and collision status:

drone.entity.billboard.color = this.getDroneColorByRole(data.role, data.is_pursuing, data.evasive_maneuver);
drone.entity.label.text = `Drone ${droneId} (${battery}%)\n${data.role || 'UNASSIGNED'}`;

// Add this utility method to the class
getDroneColorByRole(role, isPursuing, isEvasive) {
    if (isEvasive) {
        return Cesium.Color.RED; // Drone in evasive maneuver
    }
    
    if (role === 'LEAD') {
        return isPursuing ? Cesium.Color.YELLOW : Cesium.Color.ORANGE;
    } else if (role === 'TRIANGULATION') {
        return Cesium.Color.GREENYELLOW;
    } else if (role === 'BACKUP') {
        return Cesium.Color.DEEPSKYBLUE;
    } else if (role === 'SCOUT') {
        return Cesium.Color.MEDIUMPURPLE;
    }
    
    // Default color
    return Cesium.Color.DODGERBLUE;
}

// Add this to the animate loop to regularly check for collision risks:
function animate() {
    requestAnimationFrame(animate);
    
    // Check for collision risks
    droneVisualizer.checkCollisionRisks();
    
    // Existing render code
    renderer.render(scene, camera);
}

// Make sure to update the HTML to include collision statistics:
/*
<div class="status-item">
    <span class="status-count" id="collisionCount">0</span>
    <span>Collisions</span>
</div>

<div id="collisionPanel" style="display: none;">
    <h3>Collision Warnings</h3>
    <div id="collisionList"></div>
</div>
*/

// Add this to the existing map-controls div to toggle safe zones:
/*
<div class="toggle-row">
    <span class="toggle-label">Safe Zones</span>
    <label class="toggle-switch">
        <input type="checkbox" id="toggleSafeZones" checked>
        <span class="toggle-slider"></span>
    </label>
</div>
*/

// Add event handler for the safe zones toggle:
document.getElementById('toggleSafeZones').addEventListener('change', (e) => {
    droneVisualizer.visualizeSafeZones = e.target.checked;
    
    // Clear existing safe zones if disabled
    if (!e.target.checked) {
        Object.keys(droneVisualizer.safeZoneEntities).forEach(droneId => {
            droneVisualizer.removeSafeZone(droneId);
        });
    }
});
