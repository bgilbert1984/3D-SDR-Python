import * as THREE from 'three';
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls';

// Global state for service status
const serviceStatus = {
    pythonSdr: false,
    nodeRelay: false,
    websdrBridge: false
};

// Debug logging function
function debugLog(message) {
    const debugOutput = document.getElementById('debug-output');
    const timestamp = new Date().toLocaleTimeString();
    debugOutput.innerHTML += `[${timestamp}] ${message}\n`;
    debugOutput.scrollTop = debugOutput.scrollHeight;
}

// Update status indicators
function updateStatusIndicators() {
    document.getElementById('status-py-sdr').classList.toggle('status-active', serviceStatus.pythonSdr);
    document.getElementById('status-nodejs').classList.toggle('status-active', serviceStatus.nodeRelay);
    document.getElementById('status-websdr').classList.toggle('status-active', serviceStatus.websdrBridge);
}

// Service management functions
async function startPythonSdrSim() {
    try {
        const response = await fetch('/api/start-sdr-sim', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ type: 'sim' })
        });
        const data = await response.json();
        debugLog(`SDR Sim Start Response: ${JSON.stringify(data)}`);
        if (data.success) {
            serviceStatus.pythonSdr = true;
            updateStatusIndicators();
        }
    } catch (error) {
        console.error('Error starting SDR Sim:', error);
        debugLog(`Error starting SDR Sim: ${error}`);
    }
}

async function startNodeRelay() {
    try {
        const response = await fetch('/api/start-relay', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        });
        const data = await response.json();
        debugLog(`Node Relay Start Response: ${JSON.stringify(data)}`);
        if (data.success) {
            serviceStatus.nodeRelay = true;
            updateStatusIndicators();
        }
    } catch (error) {
        console.error('Error starting relay:', error);
        debugLog(`Error starting relay: ${error}`);
    }
}

async function startWebsdrBridge() {
    try {
        const response = await fetch('/api/start-websdr-bridge', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        });
        const data = await response.json();
        debugLog(`WebSDR Bridge Start Response: ${JSON.stringify(data)}`);
        if (data.success) {
            serviceStatus.websdrBridge = true;
            updateStatusIndicators();
        }
    } catch (error) {
        console.error('Error starting WebSDR bridge:', error);
        debugLog(`Error starting WebSDR bridge: ${error}`);
    }
}

async function checkServiceStatus() {
    try {
        const response = await fetch('/api/service-status');
        const data = await response.json();
        serviceStatus.pythonSdr = data.pythonSdr;
        serviceStatus.nodeRelay = data.nodeRelay;
        serviceStatus.websdrBridge = data.websdrBridge;
        updateStatusIndicators();
    } catch (error) {
        console.error('Error checking service status:', error);
        debugLog(`Error checking service status: ${error}`);
    }
}

// Add functions for starting and stopping all services
async function startAllServices() {
    debugLog('Starting all services...');
    
    // Start Node.js relay first
    try {
        const relayResponse = await fetch('/api/start-relay', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        });
        const relayData = await relayResponse.json();
        if (relayData.success) {
            serviceStatus.nodeRelay = true;
            debugLog(`Node.js Relay: ${relayData.message}`);
        } else {
            debugLog(`Error starting relay: ${relayData.error}`);
        }
    } catch (error) {
        debugLog(`Error starting relay: ${error}`);
    }
    
    // Wait a moment for the relay to initialize
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    // Start SDR Sim
    try {
        const sdrResponse = await fetch('/api/start-sdr-sim', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ type: 'sim' })
        });
        const sdrData = await sdrResponse.json();
        if (sdrData.success) {
            serviceStatus.pythonSdr = true;
            debugLog(`SDR Sim: ${sdrData.message}`);
        } else {
            debugLog(`Error starting SDR Sim: ${sdrData.error}`);
        }
    } catch (error) {
        debugLog(`Error starting SDR Sim: ${error}`);
    }
    
    updateStatusIndicators();
}

async function stopAllServices() {
    debugLog('Stopping all services...');
    
    try {
        const response = await fetch('/api/stop-all-services', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        });
        const data = await response.json();
        if (data.success) {
            serviceStatus.pythonSdr = false;
            serviceStatus.nodeRelay = false;
            serviceStatus.websdrBridge = false;
            debugLog(`All services stopped: ${data.message}`);
        } else {
            debugLog(`Error stopping services: ${data.error}`);
        }
        
        updateStatusIndicators();
    } catch (error) {
        debugLog(`Error stopping services: ${error}`);
    }
}

// DOM Elements
const statsEl = document.getElementById('stats');
const pointSizeControl = document.getElementById('pointSize');
const rotationSpeedControl = document.getElementById('rotationSpeed');

// Scene setup
const scene = new THREE.Scene();
scene.background = new THREE.Color(0x000011);

const camera = new THREE.PerspectiveCamera(75, window.innerWidth / window.innerHeight, 0.1, 1000);
camera.position.z = 100;
camera.position.y = 50;
camera.lookAt(0, 0, 0);

const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setSize(window.innerWidth, window.innerHeight);
document.body.appendChild(renderer.domElement);

// Add orbit controls for user interaction
const controls = new OrbitControls(camera, renderer.domElement);
controls.enableDamping = true;
controls.dampingFactor = 0.05;

// Add simple ambient lighting
const ambientLight = new THREE.AmbientLight(0xffffff, 0.5);
scene.add(ambientLight);

// Add a directional light to enhance depth perception
const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
directionalLight.position.set(1, 1, 1);
scene.add(directionalLight);

// Add a grid for reference
const gridHelper = new THREE.GridHelper(200, 50, 0x555555, 0x333333);
scene.add(gridHelper);

// Add axes helper
const axesHelper = new THREE.AxesHelper(20);
scene.add(axesHelper);

// Data visualization setup
const maxPoints = 1000000; // Support for up to 1 million points
const positions = new Float32Array(maxPoints * 3);
const colors = new Float32Array(maxPoints * 3);
const geometry = new THREE.BufferGeometry();
geometry.setAttribute('position', new THREE.BufferAttribute(positions, 3));
geometry.setAttribute('color', new THREE.BufferAttribute(colors, 3));

// Point cloud material with size and vertex colors
const material = new THREE.PointsMaterial({
    size: parseFloat(pointSizeControl.value),
    vertexColors: true,
    transparent: true,
    opacity: 0.8,
    sizeAttenuation: true
});

// Create point cloud and add to scene
const pointCloud = new THREE.Points(geometry, material);
scene.add(pointCloud);

// Data processing variables
let index = 0;
let lastTimestamp = 0;
let rotationSpeed = parseFloat(rotationSpeedControl.value);

// Color mapping function for frequency visualization
function getColor(amplitude) {
    if (amplitude < 0.3) {
        return new THREE.Color(0, 0, amplitude * 3);
    } else if (amplitude < 0.6) {
        return new THREE.Color(0, amplitude * 1.5, 1 - amplitude);
    } else {
        return new THREE.Color(amplitude, 1 - amplitude * 0.5, 0);
    }
}

// WebSocket connection
let socket;
let reconnectAttempts = 0;
const maxReconnectAttempts = 10;

function connectWebSocket() {
    socket = new WebSocket('ws://localhost:8080');
    
    socket.onopen = () => {
        statsEl.textContent = 'Connection: Connected to WebSocket server';
        reconnectAttempts = 0;
    };
    
    socket.onmessage = async (event) => {
        try {
            let rawData = event.data;
            if (rawData instanceof Blob) {
                rawData = await new Response(rawData).text();
            } else if (rawData instanceof ArrayBuffer) {
                rawData = new TextDecoder().decode(rawData);
            }
            const data = JSON.parse(rawData.replace(/'/g, '"'));
            
            const freqs = data.freqs;
            const amplitudes = data.amplitudes;
            const timestamp = data.timestamp;
            
            statsEl.textContent = `Connection: Active | Data points: ${freqs.length} | Update: ${(timestamp - lastTimestamp).toFixed(2)}s`;
            lastTimestamp = timestamp;
            
            const pointsToUpdate = Math.min(freqs.length, maxPoints);
            
            for (let i = 0; i < pointsToUpdate; i++) {
                const t = (index + i) / 1000 * 40 * Math.PI;
                const amplitude = amplitudes[i];
                const freq = freqs[i];
                
                const r = 30 + 20 * Math.sin(t * 0.2);
                const x = r * Math.cos(t) * amplitude * 2;
                const y = r * Math.sin(t) * amplitude * 2;
                const z = (t * 0.5) % 100;
                
                const posIndex = (index + i) % maxPoints;
                positions[posIndex * 3] = x;
                positions[posIndex * 3 + 1] = y;
                positions[posIndex * 3 + 2] = z;
                
                const color = getColor(amplitude);
                colors[posIndex * 3] = color.r;
                colors[posIndex * 3 + 1] = color.g;
                colors[posIndex * 3 + 2] = color.b;
            }
            
            index = (index + pointsToUpdate) % maxPoints;
            
            geometry.attributes.position.needsUpdate = true;
            geometry.attributes.color.needsUpdate = true;
            
        } catch (error) {
            console.error('Error processing data:', error);
        }
    };
    
    socket.onclose = () => {
        statsEl.textContent = 'Connection: Disconnected, attempting to reconnect...';
        if (reconnectAttempts < maxReconnectAttempts) {
            reconnectAttempts++;
            setTimeout(connectWebSocket, 2000);
        } else {
            statsEl.textContent = 'Connection: Failed after multiple attempts. Please refresh the page.';
        }
    };
    
    socket.onerror = (error) => {
        console.error('WebSocket error:', error);
        statsEl.textContent = 'Connection: Error connecting to WebSocket server';
    };
}

// Start WebSocket connection
connectWebSocket();

// Handle control inputs
pointSizeControl.addEventListener('input', function() {
    material.size = parseFloat(this.value);
});

rotationSpeedControl.addEventListener('input', function() {
    rotationSpeed = parseFloat(this.value);
});

// Handle window resize
window.addEventListener('resize', () => {
    camera.aspect = window.innerWidth / window.innerHeight;
    camera.updateProjectionMatrix();
    renderer.setSize(window.innerWidth, window.innerHeight);
});

// Animation loop
function animate() {
    requestAnimationFrame(animate);
    pointCloud.rotation.z += rotationSpeed;
    controls.update();
    renderer.render(scene, camera);
}

// Start animation loop
animate();

// Add KiwiSDR connect/disconnect functions
async function connectKiwiSDR(serverAddress, port, frequency) {
    try {
        const response = await fetch('/api/connect-kiwisdr', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                server_address: serverAddress,
                port: port,
                frequency: frequency
            })
        });
        
        const data = await response.json();
        if (data.success) {
            serviceStatus.kiwiSdr = true;
            updateStatusIndicators();
            return { success: true, message: data.message };
        } else {
            return { success: false, error: data.error };
        }
    } catch (error) {
        console.error("Error connecting to KiwiSDR:", error);
        return { success: false, error: error.message };
    }
}

async function disconnectKiwiSDR() {
    try {
        const response = await fetch('/api/disconnect-kiwisdr', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({})
        });
        
        const data = await response.json();
        if (data.success) {
            serviceStatus.kiwiSdr = false;
            updateStatusIndicators();
            return { success: true, message: data.message };
        } else {
            return { success: false, error: data.error };
        }
    } catch (error) {
        console.error("Error disconnecting from KiwiSDR:", error);
        return { success: false, error: error.message };
    }
}

// Handle signal filtering
async function applyFilters() {
    const frequencyMin = parseFloat(document.getElementById('filter-frequency-min').value) || null;
    const frequencyMax = parseFloat(document.getElementById('filter-frequency-max').value) || null;
    const modulation = document.getElementById('filter-modulation').value || null;
    const powerMin = parseFloat(document.getElementById('filter-power-min').value) || null;
    const powerMax = parseFloat(document.getElementById('filter-power-max').value) || null;

    try {
        const response = await fetch(`/api/get-historical-data?` +
            new URLSearchParams({
                frequency_min: frequencyMin,
                frequency_max: frequencyMax,
                modulation: modulation,
                power_min: powerMin,
                power_max: powerMax
            }), {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();
        debugLog(`Filtered Data: ${JSON.stringify(data)}`);
        updateVisualization(data.signals, data.violations);
    } catch (error) {
        console.error('Error applying filters:', error);
        debugLog(`Error applying filters: ${error}`);
    }
}

// Handle historical data playback
async function startPlayback() {
    const startTime = document.getElementById('playback-start-time').value;
    const endTime = document.getElementById('playback-end-time').value;

    try {
        const response = await fetch(`/api/get-historical-data?` +
            new URLSearchParams({
                start_time: startTime,
                end_time: endTime
            }), {
            method: 'GET',
            headers: {
                'Content-Type': 'application/json'
            }
        });

        const data = await response.json();
        debugLog(`Playback Data: ${JSON.stringify(data)}`);
        playbackVisualization(data.signals, data.violations);
    } catch (error) {
        console.error('Error starting playback:', error);
        debugLog(`Error starting playback: ${error}`);
    }
}

// Update visualization with filtered data
function updateVisualization(signals, violations) {
    // Clear existing markers and add new ones based on filtered data
    console.log('Updating visualization with filtered data:', signals, violations);
    // Implementation for updating the map or 3D visualization
}

// Playback visualization
function playbackVisualization(signals, violations) {
    // Iterate through historical data and visualize it sequentially
    console.log('Playing back historical data:', signals, violations);
    // Implementation for animating historical data playback
}

// Set up button click handlers
document.addEventListener('DOMContentLoaded', () => {
    // RF Simulations
    document.getElementById('btn-rf-basic').addEventListener('click', () => {
        debugLog('Simple RF Sim button clicked');
    });
    
    document.getElementById('btn-rf-complex').addEventListener('click', () => {
        debugLog('Complex RF Sim button clicked');
    });
    
    document.getElementById('btn-rf-fcc').addEventListener('click', () => {
        debugLog('FCC Violations button clicked');
    });
    
    document.getElementById('btn-rf-emp').addEventListener('click', () => {
        debugLog('EMP Simulation button clicked');
    });
    
    // SDR Sources
    document.getElementById('btn-sdr-sim').addEventListener('click', () => {
        debugLog('SDR Simulator button clicked');
        startPythonSdrSim();
    });
    
    document.getElementById('btn-sdr-rtl').addEventListener('click', () => {
        debugLog('RTL-SDR button clicked');
    });
    
    document.getElementById('btn-sdr-kiwi').addEventListener('click', () => {
        debugLog('KiwiSDR button clicked');
        document.getElementById('kiwisdr-modal').style.display = 'block';
    });
    
    document.getElementById('btn-sdr-websdr').addEventListener('click', () => {
        debugLog('WebSDR button clicked');
        startWebsdrBridge();
    });

    // KiwiSDR Modal handlers
    document.getElementById('kiwisdr-close').addEventListener('click', () => {
        document.getElementById('kiwisdr-modal').style.display = 'none';
    });

    // Connect button
    document.getElementById('kiwisdr-connect').addEventListener('click', async () => {
        const serverAddress = document.getElementById('server_address').value;
        const port = parseInt(document.getElementById('port').value);
        const frequency = parseFloat(document.getElementById('frequency').value);
        
        debugLog(`KiwiSDR Connect clicked - Server: ${serverAddress}, Port: ${port}, Freq: ${frequency}kHz`);
        
        // Update status display
        const statusElement = document.getElementById('kiwisdr-status');
        statusElement.textContent = `Attempting to connect to ${serverAddress}:${port} at ${frequency}kHz...`;
        
        // Disable connect button and enable disconnect button
        document.getElementById('kiwisdr-connect').disabled = true;
        document.getElementById('kiwisdr-disconnect').disabled = false;
        
        // Try to connect to KiwiSDR
        const result = await connectKiwiSDR(serverAddress, port, frequency);
        
        if (result.success) {
            debugLog(`KiwiSDR connected: ${result.message}`);
            statusElement.textContent = `Connected: ${result.message}`;
        } else {
            debugLog(`KiwiSDR connection failed: ${result.error}`);
            statusElement.textContent = `Connection failed: ${result.error}`;
            // Re-enable connect button if connection failed
            document.getElementById('kiwisdr-connect').disabled = false;
            document.getElementById('kiwisdr-disconnect').disabled = true;
        }
    });
    
    // Disconnect button
    document.getElementById('kiwisdr-disconnect').addEventListener('click', async () => {
        debugLog('KiwiSDR Disconnect clicked');
        
        // Disable disconnect button
        document.getElementById('kiwisdr-disconnect').disabled = true;
        
        // Try to disconnect from KiwiSDR
        const result = await disconnectKiwiSDR();
        
        // Update status display
        const statusElement = document.getElementById('kiwisdr-status');
        
        if (result.success) {
            debugLog(`KiwiSDR disconnected: ${result.message}`);
            statusElement.textContent = `Disconnected: ${result.message}`;
        } else {
            debugLog(`KiwiSDR disconnect failed: ${result.error}`);
            statusElement.textContent = `Disconnect failed: ${result.error}`;
        }
        
        // Re-enable connect button
        document.getElementById('kiwisdr-connect').disabled = false;
        document.getElementById('kiwisdr-disconnect').disabled = true;
    });

    // Close modal when clicking outside
    window.addEventListener('click', (event) => {
        const modal = document.getElementById('kiwisdr-modal');
        if (event.target === modal) {
            modal.style.display = 'none';
        }
    });
    
    // Service controls
    document.getElementById('btn-start-all').addEventListener('click', () => {
        debugLog('Start All Services button clicked');
        startAllServices();
    });
    
    document.getElementById('btn-stop-all').addEventListener('click', () => {
        debugLog('Stop All button clicked');
        stopAllServices();
    });
    
    // Setup polling for service status updates every 5 seconds
    setInterval(checkServiceStatus, 5000);
    
    // Initial status check
    checkServiceStatus();

    // Add event listeners for new controls
    document.getElementById('apply-filters').addEventListener('click', applyFilters);
    document.getElementById('start-playback').addEventListener('click', startPlayback);
});