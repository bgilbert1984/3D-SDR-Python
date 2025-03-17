// drone-pursuit-visualization.js

// Initialize Cesium viewer
Cesium.Ion.defaultAccessToken = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJqdGkiOiJlYWE1OWUxNy1mMWY0LTQzN2YtODQyNC1iMWJiZmM5Njk3NTIiLCJpZCI6MjU5MiwiaWF0IjoxNjU2NDUyMzkyfQ.Wdtj-ZBZ0yt4hWY1QAx7qj06UwOkzTRYM-3_GXLlNSI';

const viewer = new Cesium.Viewer('cesiumContainer', {
    terrain: Cesium.Terrain.fromWorldTerrain(),
    timeline: false,
    animation: false,
    baseLayerPicker: true,
    geocoder: true,
    sceneModePicker: true,
    navigationHelpButton: false,
    homeButton: true,
    scene3DOnly: false,
    infoBox: true
});

// Set default view to San Francisco
viewer.camera.flyTo({
    destination: Cesium.Cartesian3.fromDegrees(-122.4194, 37.7749, 10000)
});

// Colors for different elements
const COLORS = {
    DRONE: Cesium.Color.DODGERBLUE,
    SIGNAL: Cesium.Color.SPRINGGREEN,
    VIOLATION: Cesium.Color.RED,
    PATH: Cesium.Color.YELLOW.withAlpha(0.5),
    PREDICTION: Cesium.Color.MAGENTA.withAlpha(0.7),
    UNCERTAINTY: Cesium.Color.WHITE.withAlpha(0.3)
};

// Colors for different modulation types
const MODULATION_COLORS = {
    'AM': Cesium.Color.fromCssColorString('#00AAFF'),  // Light blue
    'FM': Cesium.Color.fromCssColorString('#00FF00'),  // Green
    'SSB': Cesium.Color.fromCssColorString('#FFAA00'), // Orange
    'CW': Cesium.Color.fromCssColorString('#FFFF00'),  // Yellow
    'PSK': Cesium.Color.fromCssColorString('#FF00FF'), // Magenta
    'FSK': Cesium.Color.fromCssColorString('#00FFAA'), // Turquoise
    'NOISE': Cesium.Color.fromCssColorString('#666666'), // Gray
    'UNKNOWN': Cesium.Color.fromCssColorString('#CCCCCC') // Light gray
};

class DroneSDRVisualizer {
    constructor() {
        this.drones = {};
        this.signals = {};
        this.violations = {};
        this.activeTrackingId = null;
        this.socket = null;
        this.isConnected = false;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 10;
        
        // Create entity collections
        this.droneEntities = new Cesium.EntityCollection();
        this.signalEntities = new Cesium.EntityCollection();
        this.violationEntities = new Cesium.EntityCollection();
        this.pathEntities = new Cesium.EntityCollection();
        this.predictionEntities = new Cesium.EntityCollection();
        
        // Register UI event handlers
        this.setupUI();
    }
    
    setupUI() {
        // Set up control panel events
        document.getElementById('connectButton').addEventListener('click', () => this.connectWebSocket());
        document.getElementById('disconnectButton').addEventListener('click', () => this.disconnectWebSocket());
        document.getElementById('clearButton').addEventListener('click', () => this.clearAll());
        
        // Setup drone commands
        document.getElementById('takeoffButton').addEventListener('click', () => this.sendDroneCommand('takeoff'));
        document.getElementById('landButton').addEventListener('click', () => this.sendDroneCommand('land'));
        document.getElementById('returnHomeButton').addEventListener('click', () => this.sendDroneCommand('return_home'));
        document.getElementById('pursueButton').addEventListener('click', () => this.pursueSelectedViolation());
        
        // Setup layer visibility toggles
        document.getElementById('toggleDrones').addEventListener('change', (e) => this.toggleLayer('drones', e.target.checked));
        document.getElementById('toggleSignals').addEventListener('change', (e) => this.toggleLayer('signals', e.target.checked));
        document.getElementById('toggleViolations').addEventListener('change', (e) => this.toggleLayer('violations', e.target.checked));
        document.getElementById('togglePaths').addEventListener('change', (e) => this.toggleLayer('paths', e.target.checked));
        document.getElementById('togglePredictions').addEventListener('change', (e) => this.toggleLayer('predictions', e.target.checked));
    }
    
    connectWebSocket() {
        const serverUrl = document.getElementById('serverUrl').value || 'ws://localhost:8080';
        
        try {
            this.socket = new WebSocket(serverUrl);
            
            this.updateStatus('connecting', `Connecting to ${serverUrl}...`);
            
            this.socket.onopen = () => {
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.updateStatus('connected', `Connected to ${serverUrl}`);
                
                // Enable UI elements
                document.querySelectorAll('.requires-connection').forEach(el => {
                    el.disabled = false;
                });
            };
            
            this.socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.processData(data);
                } catch (error) {
                    console.error('Error processing WebSocket message:', error);
                }
            };
            
            this.socket.onclose = () => {
                this.isConnected = false;
                this.updateStatus('disconnected', 'WebSocket connection closed');
                
                // Disable UI elements
                document.querySelectorAll('.requires-connection').forEach(el => {
                    el.disabled = true;
                });
                
                // Attempt to reconnect
                if (this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.reconnectAttempts++;
                    this.updateStatus('connecting', `Connection lost. Reconnecting (${this.reconnectAttempts}/${this.maxReconnectAttempts})...`);
                    setTimeout(() => this.connectWebSocket(), 2000);
                }
            };
            
            this.socket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.updateStatus('error', 'WebSocket error');
            };
            
        } catch (error) {
            console.error('Error connecting to WebSocket:', error);
            this.updateStatus('error', `Error: ${error.message}`);
        }
    }
    
    disconnectWebSocket() {
        if (this.socket) {
            this.socket.close();
            this.socket = null;
        }
    }
    
    updateStatus(status, message) {
        const statusEl = document.getElementById('connectionStatus');
        statusEl.className = status;
        statusEl.textContent = message;
        
        console.log(`Status: ${message}`);
    }
    
    processData(data) {
        // Check data type
        if (data.type === 'drone_status') {
            this.updateDrone(data);
        } else if (data.type === 'signal') {
            this.updateSignal(data);
        } else if (data.type === 'violation') {
            this.updateViolation(data);
        } else if (data.type === 'geolocation_results') {
            this.updateGeolocationResults(data.results);
        } else {
            // Default handling for backward compatibility
            if (data.signals) {
                data.signals.forEach(signal => this.updateSignal({
                    type: 'signal',
                    ...signal
                }));
            }
            
            if (data.violations) {
                data.violations.forEach(violation => this.updateViolation({
                    type: 'violation',
                    ...violation
                }));
            }
            
            if (data.geolocation_results) {
                this.updateGeolocationResults(data.geolocation_results);
            }
        }
        
        // Update UI with stats
        this.updateStats();
    }
    
    updateDrone(data) {
        const droneId = data.drone_id;
        const timestamp = data.timestamp;
        const location = data.location;
        const battery = data.battery;
        const isPursuing = data.is_pursuing;
        
        // Store drone information
        if (!this.drones[droneId]) {
            this.drones[droneId] = {
                id: droneId,
                entity: null,
                pathPositions: new Cesium.SampledPositionProperty(),
                lastPosition: null,
                isPursuing: isPursuing,
                battery: battery
            };
            
            // Create drone entity
            const drone = viewer.entities.add({
                id: `drone-${droneId}`,
                name: `Drone ${droneId}`,
                position: new Cesium.Cartesian3.fromDegrees(
                    location.longitude, 
                    location.latitude, 
                    location.altitude
                ),
                path: {
                    material: COLORS.DRONE,
                    width: 2,
                    leadTime: 0,
                    trailTime: 60 * 15, // 15 minutes of history
                    resolution: 1
                },
                billboard: {
                    image: 'assets/drone.png',
                    scale: 0.5,
                    verticalOrigin: Cesium.VerticalOrigin.CENTER,
                    horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
                    color: isPursuing ? COLORS.VIOLATION : COLORS.DRONE
                },
                label: {
                    text: `Drone ${droneId} (${battery}%)`,
                    font: '14px sans-serif',
                    fillColor: Cesium.Color.WHITE,
                    outlineColor: Cesium.Color.BLACK,
                    outlineWidth: 2,
                    style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                    verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                    horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
                    pixelOffset: new Cesium.Cartesian2(0, -25)
                }
            });
            
            this.drones[droneId].entity = drone;
            this.droneEntities.add(drone);
            
            // Add to drone list in UI
            this.updateDroneList();
        } else {
            // Update existing drone
            const drone = this.drones[droneId];
            const position = Cesium.Cartesian3.fromDegrees(
                location.longitude, 
                location.latitude, 
                location.altitude
            );
            
            drone.entity.position = position;
            drone.entity.label.text = `Drone ${droneId} (${battery}%)`;
            drone.entity.billboard.color = isPursuing ? COLORS.VIOLATION : COLORS.DRONE;
            
            // Add to path
            drone.pathPositions.addSample(Cesium.JulianDate.now(), position);
            drone.lastPosition = position;
            drone.isPursuing = isPursuing;
            drone.battery = battery;
            
            // If this is the drone we're tracking, follow it
            if (this.activeTrackingId === droneId) {
                this.trackDrone(droneId);
            }
        }
        
        // If drone has a target, visualize it
        if (data.target_location) {
            const targetId = `target-${droneId}`;
            let targetEntity = viewer.entities.getById(targetId);
            
            const targetPosition = Cesium.Cartesian3.fromDegrees(
                data.target_location[1],
                data.target_location[0],
                data.target_location[2]
            );
            
            if (!targetEntity) {
                // Create target entity
                targetEntity = viewer.entities.add({
                    id: targetId,
                    name: `Target for Drone ${droneId}`,
                    position: targetPosition,
                    point: {
                        pixelSize: 15,
                        color: COLORS.PREDICTION,
                        outlineColor: Cesium.Color.WHITE,
                        outlineWidth: 2
                    }
                });
                
                this.predictionEntities.add(targetEntity);
            } else {
                // Update existing target
                targetEntity.position = targetPosition;
            }
            
            // Add line to target
            const lineId = `target-line-${droneId}`;
            let lineEntity = viewer.entities.getById(lineId);
            
            if (!lineEntity) {
                lineEntity = viewer.entities.add({
                    id: lineId,
                    name: `Pursuit line for Drone ${droneId}`,
                    polyline: {
                        positions: [this.drones[droneId].lastPosition, targetPosition],
                        width: 2,
                        material: new Cesium.PolylineDashMaterialProperty({
                            color: COLORS.PREDICTION
                        })
                    }
                });
                
                this.predictionEntities.add(lineEntity);
            } else {
                lineEntity.polyline.positions = [this.drones[droneId].lastPosition, targetPosition];
            }
        }
    }
    
    updateSignal(data) {
        const freqKey = data.frequency_mhz ? data.frequency_mhz.toFixed(3) : (data.frequency / 1e6).toFixed(3);
        const modulation = data.modulation || 'UNKNOWN';
        const color = MODULATION_COLORS[modulation] || COLORS.SIGNAL;
        
        // Only update if we have location data
        if (!data.geolocation && !data.predicted_location) {
            return;
        }
        
        // Extract location
        let lat, lon, alt;
        if (data.geolocation) {
            lat = data.geolocation.latitude;
            lon = data.geolocation.longitude;
            alt = data.geolocation.altitude || 0;
        } else if (data.predicted_location) {
            lat = data.predicted_location[0];
            lon = data.predicted_location[1];
            alt = data.predicted_location[2] || 0;
        } else {
            return;
        }
        
        // Store signal information
        if (!this.signals[freqKey]) {
            this.signals[freqKey] = {
                frequency: data.frequency || data.frequency_mhz * 1e6,
                frequency_mhz: data.frequency_mhz || data.frequency / 1e6,
                modulation: modulation,
                power: data.power,
                confidence: data.confidence,
                entity: null
            };
            
            // Create signal entity
            const signal = viewer.entities.add({
                id: `signal-${freqKey}`,
                name: `Signal ${freqKey} MHz (${modulation})`,
                position: Cesium.Cartesian3.fromDegrees(lon, lat, alt),
                point: {
                    pixelSize: 10,
                    color: color,
                    outlineColor: Cesium.Color.WHITE,
                    outlineWidth: 1
                },
                label: {
                    text: `${freqKey} MHz\n${modulation}`,
                    font: '12px sans-serif',
                    fillColor: Cesium.Color.WHITE,
                    outlineColor: Cesium.Color.BLACK,
                    outlineWidth: 2,
                    style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                    verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                    horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
                    pixelOffset: new Cesium.Cartesian2(0, -15)
                }
            });
            
            this.signals[freqKey].entity = signal;
            this.signalEntities.add(signal);
            
            // Add to signals list in UI
            this.updateSignalList();
        } else {
            // Update existing signal
            const signal = this.signals[freqKey];
            signal.modulation = modulation;
            signal.power = data.power;
            signal.confidence = data.confidence;
            
            signal.entity.position = Cesium.Cartesian3.fromDegrees(lon, lat, alt);
            signal.entity.point.color = color;
            signal.entity.label.text = `${freqKey} MHz\n${modulation}`;
        }
    }
    
    updateViolation(data) {
        const freqKey = data.frequency_mhz ? data.frequency_mhz.toFixed(3) : (data.frequency / 1e6).toFixed(3);
        const modulation = data.modulation || 'UNKNOWN';
        
        // Only update if we have location data
        if (!data.geolocation && !data.predicted_location) {
            return;
        }
        
        // Extract location
        let lat, lon, alt;
        if (data.geolocation) {
            lat = data.geolocation.latitude;
            lon = data.geolocation.longitude;
            alt = data.geolocation.altitude || 0;
        } else if (data.predicted_location) {
            lat = data.predicted_location[0];
            lon = data.predicted_location[1];
            alt = data.predicted_location[2] || 0;
        } else {
            return;
        }
        
        // Store violation information
        if (!this.violations[freqKey]) {
            this.violations[freqKey] = {
                frequency: data.frequency || data.frequency_mhz * 1e6,
                frequency_mhz: data.frequency_mhz || data.frequency / 1e6,
                modulation: modulation,
                power: data.power,
                confidence: data.confidence,
                entity: null,
                pulseEntity: null
            };
            
            // Create violation entity
            const violation = viewer.entities.add({
                id: `violation-${freqKey}`,
                name: `Violation ${freqKey} MHz (${modulation})`,
                position: Cesium.Cartesian3.fromDegrees(lon, lat, alt),
                point: {
                    pixelSize: 15,
                    color: COLORS.VIOLATION,
                    outlineColor: Cesium.Color.WHITE,
                    outlineWidth: 2
                },
                label: {
                    text: `VIOLATION\n${freqKey} MHz\n${modulation}`,
                    font: '14px sans-serif',
                    fillColor: COLORS.VIOLATION,
                    outlineColor: Cesium.Color.BLACK,
                    outlineWidth: 2,
                    style: Cesium.LabelStyle.FILL_AND_OUTLINE,
                    verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
                    horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
                    pixelOffset: new Cesium.Cartesian2(0, -15)
                }
            });
            
            // Add pulse effect
            const pulseEntity = viewer.entities.add({
                id: `violation-pulse-${freqKey}`,
                position: Cesium.Cartesian3.fromDegrees(lon, lat, alt),
                ellipse: {
                    semiMinorAxis: new Cesium.CallbackProperty((time) => {
                        const pulse = 100 + 400 * Math.abs(Math.sin(Cesium.JulianDate.secondsDifference(time, Cesium.JulianDate.now()) * 0.5));
                        return pulse;
                    }, false),
                    semiMajorAxis: new Cesium.CallbackProperty((time) => {
                        const pulse = 100 + 400 * Math.abs(Math.sin(Cesium.JulianDate.secondsDifference(time, Cesium.JulianDate.now()) * 0.5));
                        return pulse;
                    }, false),
                    material: COLORS.VIOLATION.withAlpha(0.3),
                    outline: true,
                    outlineColor: COLORS.VIOLATION.withAlpha(0.5),
                    outlineWidth: 2,
                    height: alt,
                    heightReference: Cesium.HeightReference.RELATIVE_TO_GROUND
                }
            });
            
            this.violations[freqKey].entity = violation;
            this.violations[freqKey].pulseEntity = pulseEntity;
            this.violationEntities.add(violation);
            this.violationEntities.add(pulseEntity);
            
            // Add to violations list in UI
            this.updateViolationList();
        } else {
            // Update existing violation
            const violation = this.violations[freqKey];
            violation.modulation = modulation;
            violation.power = data.power;
            violation.confidence = data.confidence;
            
            const position = Cesium.Cartesian3.fromDegrees(lon, lat, alt);
            violation.entity.position = position;
            violation.entity.label.text = `VIOLATION\n${freqKey} MHz\n${modulation}`;
            
            if (violation.pulseEntity) {
                violation.pulseEntity.position = position;
                violation.pulseEntity.ellipse.height = alt;
            }
        }
    }
    
    updateGeolocationResults(results) {
        if (!Array.isArray(results)) {
            return;
        }
        
        results.forEach(result => {
            const freqKey = result.frequency_mhz.toFixed(3);
            const method = result.method || 'unknown';
            
            // Update a signal or violation if it exists
            if (this.signals[freqKey]) {
                this.updateSignal({
                    ...this.signals[freqKey],
                    geolocation: {
                        latitude: result.latitude,
                        longitude: result.longitude,
                        altitude: result.altitude || 0
                    }
                });
            } else if (this.violations[freqKey]) {
                this.updateViolation({
                    ...this.violations[freqKey],
                    geolocation: {
                        latitude: result.latitude,
                        longitude: result.longitude,
                        altitude: result.altitude || 0
                    }
                });
            }
            
            // Add uncertainty circle based on method
            const circleId = `uncertainty-${freqKey}`;
            let circleEntity = viewer.entities.getById(circleId);
            
            // Size depends on method precision
            let radius = 250; // Default
            if (method === 'rssi') {
                radius = 750; // RSSI is less precise
            } else if (method === 'single_receiver') {
                radius = 1500; // Even less precise
            }
            
            const isViolation = this.violations[freqKey] !== undefined;
            const circleColor = isViolation ? COLORS.VIOLATION.withAlpha(0.3) : COLORS.UNCERTAINTY;
            
            if (!circleEntity && result.latitude && result.longitude) {
                circleEntity = viewer.entities.add({
                    id: circleId,
                    position: Cesium.Cartesian3.fromDegrees(result.longitude, result.latitude, result.altitude || 0),
                    ellipse: {
                        semiMinorAxis: radius,
                        semiMajorAxis: radius,
                        material: circleColor,
                        outline: true,
                        outlineColor: isViolation ? COLORS.VIOLATION : COLORS.UNCERTAINTY.withAlpha(0.7),
                        outlineWidth: 2,
                        height: result.altitude || 0,
                        heightReference: Cesium.HeightReference.RELATIVE_TO_GROUND
                    }
                });
            } else if (circleEntity && result.latitude && result.longitude) {
                circleEntity.position = Cesium.Cartesian3.fromDegrees(result.longitude, result.latitude, result.altitude || 0);
                circleEntity.ellipse.semiMinorAxis = radius;
                circleEntity.ellipse.semiMajorAxis = radius;
                circleEntity.ellipse.material = circleColor;
                circleEntity.ellipse.outlineColor = isViolation ? COLORS.VIOLATION : COLORS.UNCERTAINTY.withAlpha(0.7);
                circleEntity.ellipse.height = result.altitude || 0;
            }
        });
    }
    
    updateDroneList() {
        const droneList = document.getElementById('droneList');
        droneList.innerHTML = '';
        
        // Add each drone to the list
        Object.values(this.drones).forEach(drone => {
            const droneItem = document.createElement('div');
            droneItem.className = 'list-item drone-item';
            droneItem.innerHTML = `
                <div class="item-header">
                    <span class="item-title">Drone ${drone.id}</span>
                    <span class="item-status ${drone.isPursuing ? 'pursuing' : 'idle'}">${drone.isPursuing ? 'PURSUING' : 'IDLE'}</span>
                </div>
                <div class="item-details">
                    <div class="battery-indicator" style="width: ${drone.battery || 0}%"></div>
                    <span class="battery-value">${drone.battery || 0}%</span>
                </div>
                <div class="item-actions">
                    <button class="track-button" data-id="${drone.id}">Track</button>
                </div>
            `;
            
            // Add click handler for tracking
            droneItem.querySelector('.track-button').addEventListener('click', () => {
                this.trackDrone(drone.id);
            });
            
            droneList.appendChild(droneItem);
        });
        
        // If no drones, show message
        if (Object.keys(this.drones).length === 0) {
            droneList.innerHTML = '<div class="empty-list">No drones connected</div>';
        }
    }
    
    updateSignalList() {
        const signalList = document.getElementById('signalList');
        signalList.innerHTML = '';
        
        // Add each signal to the list
        Object.values(this.signals).forEach(signal => {
            const signalItem = document.createElement('div');
            signalItem.className = 'list-item signal-item';
            
            const modColor = MODULATION_COLORS[signal.modulation] ? 
                MODULATION_COLORS[signal.modulation].toCssColorString() : '#CCCCCC';
            
            signalItem.innerHTML = `
                <div class="item-header">
                    <span class="item-title">${signal.frequency_mhz.toFixed(3)} MHz</span>
                    <span class="modulation-tag" style="background-color: ${modColor}">${signal.modulation}</span>
                </div>
                <div class="item-details">
                    <div class="signal-strength" style="width: ${(signal.power || 0) * 100}%"></div>
                    <span class="confidence-value">Confidence: ${((signal.confidence || 0) * 100).toFixed(0)}%</span>
                </div>
                <div class="item-actions">
                    <button class="locate-button" data-freq="${signal.frequency_mhz.toFixed(3)}">Locate</button>
                </div>
            `;
            
            // Add click handler for locating
            signalItem.querySelector('.locate-button').addEventListener('click', () => {
                this.locateSignal(signal.frequency_mhz.toFixed(3));
            });
            
            signalList.appendChild(signalItem);
        });
        
        // If no signals, show message
        if (Object.keys(this.signals).length === 0) {
            signalList.innerHTML = '<div class="empty-list">No signals detected</div>';
        }
    }
    
    updateViolationList() {
        const violationList = document.getElementById('violationList');
        violationList.innerHTML = '';
        
        // Add each violation to the list
        Object.values(this.violations).forEach(violation => {
            const violationItem = document.createElement('div');
            violationItem.className = 'list-item violation-item';
            
            const modColor = MODULATION_COLORS[violation.modulation] ? 
                MODULATION_COLORS[violation.modulation].toCssColorString() : '#CCCCCC';
            
            violationItem.innerHTML = `
                <div class="item-header">
                    <span class="item-title">${violation.frequency_mhz.toFixed(3)} MHz</span>
                    <span class="modulation-tag" style="background-color: ${modColor}">${violation.modulation}</span>
                </div>
                <div class="item-details">
                    <div class="signal-strength violation-strength" style="width: ${(violation.power || 0) * 100}%"></div>
                    <span class="confidence-value">Confidence: ${((violation.confidence || 0) * 100).toFixed(0)}%</span>
                </div>
                <div class="item-actions">
                    <button class="locate-button" data-freq="${violation.frequency_mhz.toFixed(3)}">Locate</button>
                    <button class="pursue-button" data-freq="${violation.frequency_mhz.toFixed(3)}">Pursue</button>
                </div>
            `;
            
            // Add click handlers
            violationItem.querySelector('.locate-button').addEventListener('click', () => {
                this.locateSignal(violation.frequency_mhz.toFixed(3));
            });
            
            violationItem.querySelector('.pursue-button').addEventListener('click', () => {
                this.pursueViolation(violation.frequency_mhz.toFixed(3));
            });
            
            violationList.appendChild(violationItem);
        });
        
        // If no violations, show message
        if (Object.keys(this.violations).length === 0) {
            violationList.innerHTML = '<div class="empty-list">No violations detected</div>';
        }
    }
    
    updateStats() {
        document.getElementById('droneCount').textContent = Object.keys(this.drones).length;
        document.getElementById('signalCount').textContent = Object.keys(this.signals).length;
        document.getElementById('violationCount').textContent = Object.keys(this.violations).length;
    }
    
    trackDrone(droneId) {
        if (!this.drones[droneId]) {
            return;
        }
        
        this.activeTrackingId = droneId;
        
        // Highlight in drone list
        document.querySelectorAll('.drone-item').forEach(item => {
            item.classList.remove('active');
        });
        
        const activeDroneItem = document.querySelector(`.drone-item .track-button[data-id="${droneId}"]`).closest('.drone-item');
        if (activeDroneItem) {
            activeDroneItem.classList.add('active');
        }
        
        // Get drone position
        const drone = this.drones[droneId];
        if (drone.entity) {
            const position = drone.entity.position.getValue(Cesium.JulianDate.now());
            
            if (position) {
                // Set camera to follow drone from behind and above
                viewer.camera.flyTo({
                    destination: Cesium.Cartesian3.add(
                        position,
                        new Cesium.Cartesian3(0, -100, 50),
                        new Cesium.Cartesian3()
                    ),
                    orientation: {
                        heading: 0,
                        pitch: Cesium.Math.toRadians(-30),
                        roll: 0
                    }
                });
            }
        }
    }
    
    locateSignal(freqKey) {
        // Locate the signal on the map
        let entity;
        
        if (this.violations[freqKey]) {
            entity = this.violations[freqKey].entity;
        } else if (this.signals[freqKey]) {
            entity = this.signals[freqKey].entity;
        }
        
        if (entity) {
            viewer.flyTo(entity, {
                duration: 2,
                offset: new Cesium.HeadingPitchRange(0, Cesium.Math.toRadians(-45), 1000)
            });
        }
    }
    
    pursueViolation(freqKey) {
        if (!this.socket || !this.violations[freqKey]) {
            return;
        }
        
        // Select a drone to pursue (use first available)
        const droneIds = Object.keys(this.drones);
        if (droneIds.length === 0) {
            alert('No drones available for pursuit');
            return;
        }
        
        const droneId = document.getElementById('selectedDrone').value || droneIds[0];
        
        // Send pursuit command
        const command = {
            type: 'command',
            command: 'pursue',
            drone_id: droneId,
            frequency: this.violations[freqKey].frequency
        };
        
        this.socket.send(JSON.stringify(command));
        
        // Track the drone
        this.trackDrone(droneId);
        
        // Highlight the violation
        this.locateSignal(freqKey);
    }
    
    pursueSelectedViolation() {
        // Get selected violation and drone
        const violationFreq = document.getElementById('selectedViolation').value;
        
        if (violationFreq) {
            this.pursueViolation(violationFreq);
        } else {
            alert('Please select a violation to pursue');
        }
    }
    
    sendDroneCommand(command) {
        if (!this.socket) {
            return;
        }
        
        const droneId = document.getElementById('selectedDrone').value;
        if (!droneId) {
            alert('Please select a drone');
            return;
        }
        
        const cmd = {
            type: 'command',
            command: command,
            drone_id: droneId
        };
        
        // Add altitude for takeoff
        if (command === 'takeoff') {
            cmd.altitude = parseFloat(document.getElementById('takeoffAltitude').value || 50);
        }
        
        this.socket.send(JSON.stringify(cmd));
    }
    
    toggleLayer(layer, visible) {
        switch (layer) {
            case 'drones':
                this.droneEntities.values.forEach(entity => {
                    entity.show = visible;
                });
                break;
                
            case 'signals':
                this.signalEntities.values.forEach(entity => {
                    entity.show = visible;
                });
                break;
                
            case 'violations':
                this.violationEntities.values.forEach(entity => {
                    entity.show = visible;
                });
                break;
                
            case 'paths':
                this.pathEntities.values.forEach(entity => {
                    entity.show = visible;
                });
                break;
                
            case 'predictions':
                this.predictionEntities.values.forEach(entity => {
                    entity.show = visible;
                });
                break;
        }
    }
    
    clearAll() {
        // Remove all entities
        viewer.entities.removeAll();
        
        // Clear collections
        this.drones = {};
        this.signals = {};
        this.violations = {};
        
        // Reset entity collections
        this.droneEntities = new Cesium.EntityCollection();
        this.signalEntities = new Cesium.EntityCollection();
        this.violationEntities = new Cesium.EntityCollection();
        this.pathEntities = new Cesium.EntityCollection();
        this.predictionEntities = new Cesium.EntityCollection();
        
        // Reset UI
        this.updateDroneList();
        this.updateSignalList();
        this.updateViolationList();
        this.updateStats();
    }
}

// Initialize the visualizer
const droneVisualizer = new DroneSDRVisualizer();

// Auto-connect to WebSocket if URL is provided
window.addEventListener('load', () => {
    // Auto-connect if server URL is provided
    if (document.getElementById('serverUrl').value) {
        droneVisualizer.connectWebSocket();
    }
});
