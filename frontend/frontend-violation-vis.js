// THREE and OrbitControls are now global objects from script includes

// DOM Elements
const statsEl = document.getElementById('stats');
const violationsEl = document.createElement('div');
violationsEl.id = 'violations';
violationsEl.innerHTML = '<h3>FCC Violations: None detected</h3>';
document.getElementById('info').appendChild(violationsEl);

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
            const violations = data.violations || [];
            
            // Update stats display
            statsEl.textContent = `Connection: Active | Data points: ${freqs.length} | Update: ${((timestamp - lastTimestamp) || 0).toFixed(2)}s`;
            lastTimestamp = timestamp;
            
            // Update violations panel
            if (violations.length > 0) {
                let violationsHtml = '<h3>FCC Violations Detected:</h3><ul>';
                violations.forEach(v => {
                    violationsHtml += `<li>Frequency: ${v.frequency_mhz.toFixed(3)} MHz - Power: ${(v.power * 100).toFixed(1)}%</li>`;
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
            
            // Map incoming SDR data into a 3D spiral
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
                
                // Set color in buffer - normal signals green, but avoid red (used for violations)
                const color = getColor(amplitude);
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
    
    // Apply rotation to the point cloud for the spiral effect
    pointCloud.rotation.z += rotationSpeed;
    violationPoints.rotation.z += rotationSpeed;
    
    // Update orbit controls
    controls.update();
    
    // Render the scene
    renderer.render(scene, camera);
}

// Start animation loop
animate();