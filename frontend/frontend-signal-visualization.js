// THREE and OrbitControls are now global objects from script includes

// DOM Elements
const statsEl = document.getElementById('stats');
const violationsEl = document.createElement('div');
violationsEl.id = 'violations';
violationsEl.innerHTML = '<h3>FCC Violations: None detected</h3>';
document.getElementById('info').appendChild(violationsEl);

// Add signal classification panel
const signalClassEl = document.createElement('div');
signalClassEl.id = 'signal-classification';
signalClassEl.innerHTML = '<h3>Signal Classification</h3><div id="signal-types"></div>';
document.getElementById('info').appendChild(signalClassEl);

const pointSizeControl = document.getElementById('pointSize');
const rotationSpeedControl = document.getElementById('rotationSpeed');

// Add legend for signal types
const legendEl = document.createElement('div');
legendEl.id = 'legend';
legendEl.style.position = 'absolute';
legendEl.style.bottom = '10px';
legendEl.style.right = '10px';
legendEl.style.backgroundColor = 'rgba(0,0,0,0.7)';
legendEl.style.padding = '10px';
legendEl.style.borderRadius = '5px';
legendEl.style.color = 'white';
legendEl.style.fontFamily = 'monospace';
legendEl.innerHTML = '<h3>Signal Types</h3><div id="legend-items"></div>';
document.body.appendChild(legendEl);

// Define colors for different modulation types
const MODULATION_COLORS = {
    'AM': new THREE.Color(0x00AAFF),    // Light blue
    'FM': new THREE.Color(0x00FF00),    // Green
    'SSB': new THREE.Color(0xFFAA00),   // Orange
    'CW': new THREE.Color(0xFFFF00),    // Yellow
    'PSK': new THREE.Color(0xFF00FF),   // Magenta
    'FSK': new THREE.Color(0x00FFAA),   // Turquoise
    'NOISE': new THREE.Color(0x666666), // Gray
    'UNKNOWN': new THREE.Color(0xCCCCCC) // Light gray
};

// Create legend items
const legendItemsEl = document.getElementById('legend-items');
Object.entries(MODULATION_COLORS).forEach(([mod, color]) => {
    const itemEl = document.createElement('div');
    itemEl.style.margin = '5px 0';
    
    const colorBox = document.createElement('span');
    colorBox.style.display = 'inline-block';
    colorBox.style.width = '15px';
    colorBox.style.height = '15px';
    colorBox.style.backgroundColor = `#${color.getHexString()}`;
    colorBox.style.marginRight = '10px';
    
    itemEl.appendChild(colorBox);
    itemEl.appendChild(document.createTextNode(mod));
    legendItemsEl.appendChild(itemEl);
});

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
const controls = new THREE.OrbitControls(camera, renderer.domElement);
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

// Create separate geometries for each modulation type
const modulationGeometries = {};
const modulationPoints = {};

Object.entries(MODULATION_COLORS).forEach(([mod, color]) => {
    modulationGeometries[mod] = new THREE.BufferGeometry();
    
    const modMaterial = new THREE.PointsMaterial({
        size: 3.0,
        color: color,
        transparent: true,
        opacity: 0.9,
        sizeAttenuation: true
    });
    
    modulationPoints[mod] = new THREE.Points(modulationGeometries[mod], modMaterial);
    scene.add(modulationPoints[mod]);
});

// Create a separate geometry for violations (larger, red points)
const violationGeometry = new THREE.BufferGeometry();
const violationMaterial = new THREE.PointsMaterial({
    size: 5.0, // Larger points for violations
    color: 0xff0000, // Red color
    transparent: true,
    opacity: 0.9,
    sizeAttenuation: true
});

// Initially empty
const violationPoints = new THREE.Points(violationGeometry, violationMaterial);
scene.add(violationPoints);

// Data processing variables
let index = 0;
let lastTimestamp = 0;
let rotationSpeed = parseFloat(rotationSpeedControl.value);

// Color mapping function for frequency visualization
function getColor(amplitude) {
    // Create a color gradient based on amplitude
    if (amplitude < 0.3) {
        return new THREE.Color(0, 0, amplitude * 3); // Blue for low amplitudes
    } else if (amplitude < 0.6) {
        return new THREE.Color(0, amplitude * 1.5, 1 - amplitude); // Cyan to Green transition
    } else {
        return new THREE.Color(amplitude, 1 - amplitude * 0.5, 0); // Green to Red for high amplitudes
    }
}

// Signal counts for statistics
let signalCounts = {};

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
            // Parse the incoming data
            let rawData = event.data;
            if (rawData instanceof Blob) {
                // Handle Blob data
                rawData = await new Response(rawData).text();
            } else if (rawData instanceof ArrayBuffer) {
                // Handle ArrayBuffer data
                rawData = new TextDecoder().decode(rawData);
            }
            
            // At this point rawData should be a string
            // Convert Python single quotes to JSON double quotes if needed
            if (rawData.indexOf("'") !== -1) {
                rawData = rawData.replace(/'/g, '"');
            }
            
            const data = JSON.parse(rawData);
            
            const freqs = data.freqs;
            const amplitudes = data.amplitudes;
            const timestamp = data.timestamp;
            const signals = data.signals || [];
            const violations = data.violations || [];
            
            // Reset signal counts
            signalCounts = {};
            
            // Update signal classification display
            if (signals.length > 0) {
                // Count signals per modulation type
                signals.forEach(signal => {
                    const mod = signal.modulation;
                    signalCounts[mod] = (signalCounts[mod] || 0) + 1;
                });
                
                // Update display
                let signalTypesHtml = '';
                Object.entries(signalCounts).forEach(([mod, count]) => {
                    const color = MODULATION_COLORS[mod] || new THREE.Color(0xCCCCCC);
                    signalTypesHtml += `<div style="margin:5px 0">
                        <span style="display:inline-block;width:15px;height:15px;background-color:#${color.getHexString()};margin-right:10px"></span>
                        ${mod}: ${count}
                    </div>`;
                });
                
                document.getElementById('signal-types').innerHTML = signalTypesHtml;
            } else {
                document.getElementById('signal-types').innerHTML = '<div>No signals detected</div>';
            }
            
            // Update stats display
            statsEl.textContent = `Connection: Active | Data points: ${freqs.length} | Signals: ${signals.length} | Update: ${((timestamp - lastTimestamp) || 0).toFixed(2)}s`;
            lastTimestamp = timestamp;
            
            // Update violations panel
            if (violations.length > 0) {
                let violationsHtml = '<h3>FCC Violations Detected:</h3><ul>';
                violations.forEach(v => {
                    violationsHtml += `
                    <li>
                        Frequency: ${v.frequency_mhz.toFixed(3)} MHz | 
                        Type: ${v.modulation} | 
                        Power: ${(v.power * 100).toFixed(1)}%
                    </li>`;
                });
                violationsHtml += '</ul>';
                violationsEl.innerHTML = violationsHtml;
                violationsEl.style.color = 'red';
                
                // Update violation markers
                const violationPositions = new Float32Array(violations.length * 3);
                
                for (let i = 0; i < violations.length; i++) {
                    const v = violations[i];
                    
                    // Find the closest frequency index
                    let closestIdx = 0;
                    let minDiff = Infinity;
                    for (let j = 0; j < freqs.length; j++) {
                        const diff = Math.abs(freqs[j]/1000 - v.frequency_khz);
                        if (diff < minDiff) {
                            minDiff = diff;
                            closestIdx = j;
                        }
                    }
                    
                    // Use the same spiral coordinates as the main point cloud
                    const t = (index + closestIdx) / 1000 * 40 * Math.PI;
                    const r = 30 + 20 * Math.sin(t * 0.2);
                    const x = r * Math.cos(t) * v.power * 3; // Make violation points more pronounced
                    const y = r * Math.sin(t) * v.power * 3;
                    const z = (t * 0.5) % 100;
                    
                    violationPositions[i * 3] = x;
                    violationPositions[i * 3 + 1] = y;
                    violationPositions[i * 3 + 2] = z;
                }
                
                // Update violation geometry
                violationGeometry.setAttribute('position', new THREE.BufferAttribute(violationPositions, 3));
                violationGeometry.attributes.position.needsUpdate = true;
                violationPoints.visible = true;
            } else {
                violationsEl.innerHTML = '<h3>FCC Violations: None detected</h3>';
                violationsEl.style.color = 'white';
                violationPoints.visible = false;
            }
            
            // Update modulation type points
            if (signals.length > 0) {
                // Prepare positions for each modulation type
                const modPositions = {};
                Object.keys(MODULATION_COLORS).forEach(mod => {
                    modPositions[mod] = [];
                });
                
                // Group signals by modulation type
                signals.forEach(signal => {
                    const mod = signal.modulation;
                    if (!modPositions[mod]) {
                        modPositions[mod] = [];
                    }
                    
                    // Find the closest frequency index
                    let closestIdx = 0;
                    let minDiff = Infinity;
                    for (let j = 0; j < freqs.length; j++) {
                        const diff = Math.abs(freqs[j]/1000 - signal.frequency_khz);
                        if (diff < minDiff) {
                            minDiff = diff;
                            closestIdx = j;
                        }
                    }
                    
                    // Calculate spiral coordinates for this signal
                    const t = (index + closestIdx) / 1000 * 40 * Math.PI;
                    const r = 30 + 20 * Math.sin(t * 0.2);
                    const x = r * Math.cos(t) * signal.power * 2;
                    const y = r * Math.sin(t) * signal.power * 2;
                    const z = (t * 0.5) % 100;
                    
                    modPositions[mod].push(x, y, z);
                });
                
                // Update geometries for each modulation type
                Object.entries(modPositions).forEach(([mod, positions]) => {
                    if (positions.length > 0) {
                        const modGeom = modulationGeometries[mod];
                        modGeom.setAttribute('position', new THREE.Float32BufferAttribute(positions, 3));
                        modGeom.attributes.position.needsUpdate = true;
                        modulationPoints[mod].visible = true;
                    } else {
                        modulationPoints[mod].visible = false;
                    }
                });
            } else {
                // Hide all modulation points if no signals
                Object.values(modulationPoints).forEach(points => {
                    points.visible = false;
                });
            }
            
            // Map incoming SDR data into a 3D spiral for background visualization
            const pointsToUpdate = Math.min(freqs.length, maxPoints);
            
            for (let i = 0; i < pointsToUpdate; i++) {
                const t = (index + i) / 1000 * 40 * Math.PI; // Spiral parameter
                const amplitude = amplitudes[i];
                const freq = freqs[i];
                
                // Calculate spiral coordinates
                const r = 30 + 20 * Math.sin(t * 0.2); // Base radius plus oscillation
                const x = r * Math.cos(t) * amplitude * 2;
                const y = r * Math.sin(t) * amplitude * 2;
                const z = (t * 0.5) % 100; // Limit the z range to prevent going too far
                
                // Set position in buffer
                const posIndex = (index + i) % maxPoints;
                positions[posIndex * 3] = x;
                positions[posIndex * 3 + 1] = y;
                positions[posIndex * 3 + 2] = z;
                
                // Set color in buffer - with reduced opacity for background
                const color = getColor(amplitude * 0.5);  // Reduce amplitude for coloring
                colors[posIndex * 3] = color.r;
                colors[posIndex * 3 + 1] = color.g;
                colors[posIndex * 3 + 2] = color.b;
            }
            
            index = (index + pointsToUpdate) % maxPoints;
            
            // Mark attributes for update
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
    
    // Apply rotation to all point clouds
    pointCloud.rotation.z += rotationSpeed;
    violationPoints.rotation.z += rotationSpeed;
    
    Object.values(modulationPoints).forEach(points => {
        points.rotation.z += rotationSpeed;
    });
    
    // Update orbit controls
    controls.update();
    
    // Render the scene
    renderer.render(scene, camera);
}

// Start animation loop
animate();

// Create Fosphor visualization setup after the existing WebGL setup
const fosphorCanvas = document.createElement('canvas');
fosphorCanvas.id = 'fosphorCanvas';
fosphorCanvas.style.position = 'absolute';
fosphorCanvas.style.top = '10px';
fosphorCanvas.style.right = '10px';
fosphorCanvas.style.width = '400px';
fosphorCanvas.style.height = '300px';
fosphorCanvas.style.backgroundColor = 'rgba(0,0,0,0.7)';
document.body.appendChild(fosphorCanvas);

// Fosphor WebSocket handler
function setupFosphorWebsocket() {
    const fosphorSocket = new WebSocket('ws://localhost:8090/fosphor');
    
    fosphorSocket.onmessage = async (event) => {
        try {
            const buffer = await event.data.arrayBuffer();
            updateHeatmapTexture(buffer);
        } catch (error) {
            console.error('Error processing Fosphor data:', error);
        }
    };
    
    fosphorSocket.onerror = (error) => {
        console.error('Fosphor WebSocket error:', error);
    };
    
    return fosphorSocket;
}

// Initialize WebGL for Fosphor heatmap
const fosphorGl = fosphorCanvas.getContext('webgl2');
let fosphorTexture = null;
let fosphorShaderProgram = null;

function initFosphorGL() {
    // Create and initialize WebGL resources for Fosphor
    const vertexShader = fosphorGl.createShader(fosphorGl.VERTEX_SHADER);
    fosphorGl.shaderSource(vertexShader, `
        attribute vec2 position;
        attribute vec2 texCoord;
        varying vec2 vTexCoord;
        void main() {
            gl_Position = vec4(position, 0.0, 1.0);
            vTexCoord = texCoord;
        }
    `);
    fosphorGl.compileShader(vertexShader);

    const fragmentShader = fosphorGl.createShader(fosphorGl.FRAGMENT_SHADER);
    fosphorGl.shaderSource(fragmentShader, `
        precision mediump float;
        uniform sampler2D uTexture;
        varying vec2 vTexCoord;
        
        vec3 heatmapGradient(float value) {
            vec3 color;
            value = clamp(value, 0.0, 1.0);
            
            if (value < 0.33) {
                color = mix(vec3(0,0,0.5), vec3(0,1,1), value * 3.0);
            } else if (value < 0.66) {
                color = mix(vec3(0,1,1), vec3(1,1,0), (value - 0.33) * 3.0);
            } else {
                color = mix(vec3(1,1,0), vec3(1,0,0), (value - 0.66) * 3.0);
            }
            return color;
        }
        
        void main() {
            float value = texture2D(uTexture, vTexCoord).r;
            vec3 color = heatmapGradient(value);
            gl_FragColor = vec4(color, 1.0);
        }
    `);
    fosphorGl.compileShader(fragmentShader);

    fosphorShaderProgram = fosphorGl.createProgram();
    fosphorGl.attachShader(fosphorShaderProgram, vertexShader);
    fosphorGl.attachShader(fosphorShaderProgram, fragmentShader);
    fosphorGl.linkProgram(fosphorShaderProgram);
    fosphorGl.useProgram(fosphorShaderProgram);

    // Create texture for waterfall data
    fosphorTexture = fosphorGl.createTexture();
    fosphorGl.bindTexture(fosphorGl.TEXTURE_2D, fosphorTexture);
    fosphorGl.texParameteri(fosphorGl.TEXTURE_2D, fosphorGl.TEXTURE_MIN_FILTER, fosphorGl.LINEAR);
    fosphorGl.texParameteri(fosphorGl.TEXTURE_2D, fosphorGl.TEXTURE_MAG_FILTER, fosphorGl.LINEAR);
    fosphorGl.texParameteri(fosphorGl.TEXTURE_2D, fosphorGl.TEXTURE_WRAP_S, fosphorGl.CLAMP_TO_EDGE);
    fosphorGl.texParameteri(fosphorGl.TEXTURE_2D, fosphorGl.TEXTURE_WRAP_T, fosphorGl.CLAMP_TO_EDGE);
}

function updateHeatmapTexture(buffer) {
    const data = new Float32Array(buffer);
    const width = 1024;  // Fosphor default width
    const height = 512;  // Fosphor default height
    
    fosphorGl.bindTexture(fosphorGl.TEXTURE_2D, fosphorTexture);
    fosphorGl.texImage2D(
        fosphorGl.TEXTURE_2D,
        0,
        fosphorGl.R32F,
        width,
        height,
        0,
        fosphorGl.RED,
        fosphorGl.FLOAT,
        data
    );
    
    // Render updated texture
    fosphorGl.drawArrays(fosphorGl.TRIANGLE_STRIP, 0, 4);
}

// Initialize Fosphor visualization
initFosphorGL();
const fosphorWs = setupFosphorWebsocket();

// Add Fosphor toggle control
const fosphorToggle = document.createElement('div');
fosphorToggle.style.position = 'absolute';
fosphorToggle.style.top = '320px';
fosphorToggle.style.right = '10px';
fosphorToggle.innerHTML = `
    <label class="toggle-switch">
        <input type="checkbox" id="toggleFosphor" checked>
        <span class="toggle-slider"></span>
        <span style="color: white; margin-left: 10px;">Fosphor View</span>
    </label>
`;
document.body.appendChild(fosphorToggle);

document.getElementById('toggleFosphor').addEventListener('change', (e) => {
    fosphorCanvas.style.display = e.target.checked ? 'block' : 'none';
});