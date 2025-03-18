// Enhancements to existing frontend to support WebSDR integration
// Add this code to your existing frontend visualization script.js or create a new file

// WebSDR control panel component
class WebSDRControls {
    constructor(parentElement, websocket) {
        this.parentElement = parentElement;
        this.websocket = websocket;
        this.isConnected = false;
        this.currentFrequency = 14200; // Default to 20m band
        this.currentMode = 'usb';
        this.currentBand = '20m';
        
        // Available bands on KF5JMD WebSDR
        this.availableBands = [
            { name: '630m', range: [0.462, 1.998], label: "630m (0.462-1.998 MHz)" },
            { name: '80m', range: [3.126, 5.174], label: "80m (3.126-5.174 MHz)" },
            { name: '40m', range: [5.750, 7.798], label: "40m (5.750-7.798 MHz)" },
            { name: '20m', range: [13.546, 15.594], label: "20m (13.546-15.594 MHz)" },
            { name: '10m', range: [26.711, 28.759], label: "10m (26.711-28.759 MHz)" },
            { name: '2m', range: [144.896, 146.944], label: "2m (144.896-146.944 MHz)" }
        ];
        
        // Available modes
        this.availableModes = [
            { value: 'am', label: 'AM' },
            { value: 'fm', label: 'FM' },
            { value: 'lsb', label: 'LSB' },
            { value: 'usb', label: 'USB' },
            { value: 'cw', label: 'CW' }
        ];
        
        this.setupEventListeners();
    }
    
    setupEventListeners() {
        // Band selection
        const bandSelect = document.getElementById('websdr-band');
        bandSelect.value = this.currentBand;
        bandSelect.addEventListener('change', (e) => {
            this.currentBand = e.target.value;
            this.sendCommand('band', this.currentBand);
            
            // Update frequency range based on band
            const band = this.availableBands.find(b => b.name === this.currentBand);
            if (band) {
                const midFreq = Math.floor((band.range[0] + band.range[1]) / 2 * 1000);
                document.getElementById('websdr-freq').value = midFreq;
                this.currentFrequency = midFreq;
                this.sendCommand('frequency', midFreq);
            }
        });
        
        // Frequency tuning
        const freqInput = document.getElementById('websdr-freq');
        const tuneButton = document.getElementById('websdr-tune');
        
        tuneButton.addEventListener('click', () => {
            this.currentFrequency = parseInt(freqInput.value, 10);
            this.sendCommand('frequency', this.currentFrequency);
        });
        
        freqInput.addEventListener('keypress', (e) => {
            if (e.key === 'Enter') {
                this.currentFrequency = parseInt(freqInput.value, 10);
                this.sendCommand('frequency', this.currentFrequency);
            }
        });
        
        // Mode selection
        const modeSelect = document.getElementById('websdr-mode');
        modeSelect.value = this.currentMode;
        modeSelect.addEventListener('change', (e) => {
            this.currentMode = e.target.value;
            this.sendCommand('mode', this.currentMode);
        });
    }
    
    sendCommand(type, value) {
        if (!this.websocket || this.websocket.readyState !== WebSocket.OPEN) {
            console.error('WebSocket not connected');
            return;
        }
        
        const command = {
            type: 'websdr_command',
            command: type,
            value: value
        };
        
        this.websocket.send(JSON.stringify(command));
        console.log(`Sent WebSDR command: ${type} = ${value}`);
    }
    
    updateStatus(isConnected, message = '') {
        const statusElement = document.querySelector('.websdr-status');
        if (statusElement) {
            this.isConnected = isConnected;
            statusElement.textContent = `Status: ${isConnected ? message : 'Disconnected'}`;
            statusElement.style.color = isConnected ? '#2ecc71' : '#e74c3c';
        }
    }
    
    updateFromData(data) {
        if (data.websdr_info) {
            // Update frequency display
            const freqInput = document.getElementById('websdr-freq');
            freqInput.value = data.websdr_info.frequency;
            this.currentFrequency = data.websdr_info.frequency;
            
            // Update mode selector
            const modeSelect = document.getElementById('websdr-mode');
            modeSelect.value = data.websdr_info.mode;
            this.currentMode = data.websdr_info.mode;
            
            // Update band selector
            if (data.websdr_info.band) {
                const bandSelect = document.getElementById('websdr-band');
                bandSelect.value = data.websdr_info.band;
                this.currentBand = data.websdr_info.band;
            }
            
            // Update connection status
            this.updateStatus(true, `${data.websdr_info.frequency} kHz ${data.websdr_info.mode.toUpperCase()}`);
        }
    }
}

// ----- Main WebSDR Integration Code -----

// Add this to your existing WebSocket message handler
function processWebSocketMessage(event) {
    try {
        const data = JSON.parse(event.data);
        
        // Regular SDR data processing (your existing code)
        // ...
        
        // Check if this is WebSDR data
        if (data.source === 'websdr' && webSDRControls) {
            webSDRControls.updateFromData(data);
            
            // You may want to add special visualization elements for WebSDR data
            if (data.waterfall) {
                // If the bridge was able to extract waterfall data
                visualizeWaterfall(data.waterfall);
            }
            
            // Add a WebSDR indicator on the visualization
            showWebSDRIndicator(data.websdr_info);
        }
        
        // Continue with your regular visualization
        updateVisualization(data.freqs, data.amplitudes);
        
    } catch (error) {
        console.error("Error processing WebSocket message:", error);
    }
}

// Add WebSDR indicator to visualization
function showWebSDRIndicator(info) {
    if (!info) return;
    
    // Create or update WebSDR indicator overlay
    let indicator = document.getElementById('websdr-indicator');
    if (!indicator) {
        indicator = document.createElement('div');
        indicator.id = 'websdr-indicator';
        indicator.className = 'websdr-indicator';
        document.body.appendChild(indicator);
    }
    
    // Update indicator content
    indicator.innerHTML = `
        <div class="websdr-indicator-content">
            <div class="websdr-indicator-title">WebSDR Source</div>
            <div class="websdr-indicator-info">
                <span>${info.frequency} kHz</span>
                <span>${info.mode.toUpperCase()}</span>
                <span>${info.band || ''}</span>
            </div>
            <div class="websdr-indicator-source">KF5JMD (Gatesville, TX)</div>
        </div>
    `;
    
    // Show indicator
    indicator.style.display = 'block';
    
    // Hide after a few seconds
    setTimeout(() => {
        indicator.style.opacity = '0.3';
    }, 5000);
}

// Function to visualize WebSDR waterfall data if available
function visualizeWaterfall(waterfallData) {
    // This is optional and depends on your visualization setup
    // If the bridge successfully extracted waterfall data from the WebSDR
    console.log('WebSDR waterfall data available:', waterfallData.length + ' points');
}

// Add CSS styles for WebSDR controls and indicators
function addWebSDRStyles() {
    const style = document.createElement('style');
    style.textContent = `
        #websdr-controls {
            background-color: #2c3e50;
            padding: 15px;
            border-radius: 5px;
            margin-top: 15px;
        }
        
        #websdr-controls h3 {
            color: #3498db;
            margin-top: 0;
            margin-bottom: 10px;
        }
        
        .websdr-status {
            padding: 5px;
            margin-bottom: 10px;
            border-radius: 3px;
            text-align: center;
            font-weight: bold;
        }
        
        .websdr-status.connected {
            background-color: #27ae60;
        }
        
        .websdr-status.disconnected {
            background-color: #e74c3c;
        }
        
        .control-row {
            display: flex;
            align-items: center;
            margin-bottom: 10px;
        }
        
        .control-row label {
            width: 120px;
            margin-right: 10px;
            color: #bdc3c7;
        }
        
        .control-row select, .control-row input {
            flex: 1;
            padding: 5px;
            background-color: #34495e;
            border: 1px solid #2c3e50;
            color: white;
            border-radius: 3px;
        }
        
        .control-row button {
            padding: 5px 10px;
            margin-left: 10px;
            background-color: #3498db;
            border: none;
            color: white;
            border-radius: 3px;
            cursor: pointer;
        }
        
        .websdr-info {
            font-size: 12px;
            color: #bdc3c7;
            margin-top: 10px;
            padding-top: 10px;
            border-top: 1px solid #34495e;
        }
        
        .websdr-indicator {
            position: absolute;
            top: 10px;
            right: 10px;
            background-color: rgba(44, 62, 80, 0.8);
            color: white;
            padding: 10px;
            border-radius: 5px;
            z-index: 1000;
            font-family: monospace;
            transition: opacity 0.5s ease;
        }
        
        .websdr-indicator-title {
            font-weight: bold;
            color: #3498db;
            margin-bottom: 5px;
        }
        
        .websdr-indicator-info {
            display: flex;
            justify-content: space-between;
            margin-bottom: 5px;
        }
        
        .websdr-indicator-info span {
            background-color: #34495e;
            padding: 2px 5px;
            border-radius: 3px;
            margin-right: 5px;
        }
        
        .websdr-indicator-source {
            font-size: 12px;
            color: #bdc3c7;
        }
    `;
    document.head.appendChild(style);
}

// Initialize WebSDR controls when page loads
let webSDRControls;
let websocket;

// Modify your existing WebSocket initialization to add WebSDR support
function initWebSocket() {
    // Your existing WebSocket setup code
    const wsURL = 'ws://localhost:8080'; // Your WebSocket server URL
    websocket = new WebSocket(wsURL);
    
    websocket.onopen = () => {
        console.log('WebSocket connected');
        // Initialize WebSDR controls after WebSocket is connected
        if (!webSDRControls) {
            // Find appropriate parent element for controls
            const controlsContainer = document.getElementById('controls') || 
                                     document.querySelector('.control-panel') || 
                                     document.body;
            
            // Initialize WebSDR controls
            webSDRControls = new WebSDRControls(controlsContainer, websocket);
            webSDRControls.updateStatus(false, 'Waiting for WebSDR data');
        }
    };
    
    websocket.onmessage = processWebSocketMessage;
    
    websocket.onclose = () => {
        console.log('WebSocket disconnected');
        // Update WebSDR controls status if they exist
        if (webSDRControls) {
            webSDRControls.updateStatus(false, 'Connection lost');
        }
        
        // Reconnect logic
        setTimeout(initWebSocket, 2000);
    };
    
    websocket.onerror = (error) => {
        console.error('WebSocket error:', error);
    };
}

// Call this when your application initializes
function initWebSDRIntegration() {
    addWebSDRStyles();
    initWebSocket();
}

// Start initialization when the DOM is ready
document.addEventListener('DOMContentLoaded', initWebSDRIntegration);
