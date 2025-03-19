# WebSDR Frontend Integration

## Overview

The WebSDR Frontend Integration provides a user interface and connection handling for interacting with WebSDR instances within the SDR Drone Pursuit System. This integration allows users to connect to public WebSDR stations, tune to specific frequencies, select operating modes, and visualize the received signal data in the 3D environment.

## Main Components

The `websdr-frontend-integration.js` file implements the following core components:

1. **WebSDRControls Class**: Manages the UI controls for WebSDR interaction
2. **WebSocket Integration**: Handles communication between the frontend and the WebSDR bridge
3. **Data Visualization**: Displays WebSDR-specific information in the 3D visualization
4. **UI Styling**: Dynamically adds WebSDR-related styles to the page

## WebSDRControls Class

The WebSDRControls class creates and manages a control panel for WebSDR interactions. It provides a user interface for:

- Selecting frequency bands (630m, 80m, 40m, 20m, 10m, 2m)
- Fine-tuning to specific frequencies
- Choosing signal modes (AM, FM, LSB, USB, CW)
- Displaying connection status

### Key Properties

```javascript
this.availableBands = [
    { name: '630m', range: [0.462, 1.998], label: "630m (0.462-1.998 MHz)" },
    { name: '80m', range: [3.126, 5.174], label: "80m (3.126-5.174 MHz)" },
    { name: '40m', range: [5.750, 7.798], label: "40m (5.750-7.798 MHz)" },
    { name: '20m', range: [13.546, 15.594], label: "20m (13.546-15.594 MHz)" },
    { name: '10m', range: [26.711, 28.759], label: "10m (26.711-28.759 MHz)" },
    { name: '2m', range: [144.896, 146.944], label: "2m (144.896-146.944 MHz)" }
];

this.availableModes = [
    { value: 'am', label: 'AM' },
    { value: 'fm', label: 'FM' },
    { value: 'lsb', label: 'LSB' },
    { value: 'usb', label: 'USB' },
    { value: 'cw', label: 'CW' }
];
```

### Event Handling

The WebSDRControls class sets up event listeners to respond to user interactions:

- **Band Selection**: Automatically adjusts the frequency when a new band is selected
- **Frequency Input**: Allows direct entry of a frequency in kHz
- **Mode Selection**: Changes the reception mode (AM, FM, etc.)

### Command Communication

When user inputs are changed, the controls send commands through the WebSocket to the backend bridge:

```javascript
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
```

### Status Updates

The WebSDRControls updates its display based on the connection status and incoming data:

```javascript
updateStatus(isConnected, message = '') {
    const statusElement = document.querySelector('.websdr-status');
    if (statusElement) {
        this.isConnected = isConnected;
        statusElement.textContent = `Status: ${isConnected ? message : 'Disconnected'}`;
        statusElement.style.color = isConnected ? '#2ecc71' : '#e74c3c';
    }
}

updateFromData(data) {
    // Updates UI controls based on received WebSDR data
    // ...
}
```

## WebSocket Message Handling

The integration processes WebSocket messages to handle both standard SDR data and WebSDR-specific information:

```javascript
function processWebSocketMessage(event) {
    try {
        const data = JSON.parse(event.data);
        
        // Check if this is WebSDR data
        if (data.source === 'websdr' && webSDRControls) {
            webSDRControls.updateFromData(data);
            
            // Process waterfall data if available
            if (data.waterfall) {
                visualizeWaterfall(data.waterfall);
            }
            
            // Add a WebSDR indicator on the visualization
            showWebSDRIndicator(data.websdr_info);
        }
        
        // Continue with regular visualization
        updateVisualization(data.freqs, data.amplitudes);
        
    } catch (error) {
        console.error("Error processing WebSocket message:", error);
    }
}
```

## Visual Indicators

The integration provides visual feedback about the WebSDR connection:

### WebSDR Status Indicator

A floating indicator appears showing:
- Current frequency
- Operating mode
- Band information
- Source information

```javascript
function showWebSDRIndicator(info) {
    // Creates or updates a floating indicator showing WebSDR information
    // ...
}
```

### Waterfall Visualization

If waterfall data is available from the WebSDR bridge, it can be visualized:

```javascript
function visualizeWaterfall(waterfallData) {
    // Visualizes WebSDR waterfall data
    console.log('WebSDR waterfall data available:', waterfallData.length + ' points');
}
```

## Dynamic Styling

The integration dynamically adds CSS styles for the WebSDR controls and indicators:

```javascript
function addWebSDRStyles() {
    const style = document.createElement('style');
    style.textContent = `
        // WebSDR-specific CSS styling
        // ...
    `;
    document.head.appendChild(style);
}
```

## Initialization Process

The integration follows this initialization sequence:

1. Adds CSS styles for WebSDR elements
2. Initializes the WebSocket connection
3. Creates WebSDR controls when the WebSocket is connected
4. Sets up message handling and reconnection logic

```javascript
function initWebSDRIntegration() {
    addWebSDRStyles();
    initWebSocket();
}

document.addEventListener('DOMContentLoaded', initWebSDRIntegration);
```

## Connection Flow

1. User selects the WebSDR option in the control panel
2. WebSocket connection is established with the backend bridge
3. User selects a band, frequency, and mode
4. Commands are sent to the WebSDR bridge
5. Bridge connects to the WebSDR server and starts streaming data
6. Data is processed and visualized in the 3D environment
7. Status indicators are updated to show connection state

## Integration with Main Application

To use the WebSDR integration:

1. Include the script in your HTML:
   ```html
   <script src="websdr-frontend-integration.js"></script>
   ```

2. Ensure your HTML has appropriate container elements:
   ```html
   <div id="controls">
       <!-- Other controls... -->
       <div id="websdr-controls">
           <div class="websdr-status">Status: Disconnected</div>
           <div class="control-row">
               <label for="websdr-band">Band:</label>
               <select id="websdr-band">
                   <option value="630m">630m (0.462-1.998 MHz)</option>
                   <option value="80m">80m (3.126-5.174 MHz)</option>
                   <option value="40m">40m (5.750-7.798 MHz)</option>
                   <option value="20m" selected>20m (13.546-15.594 MHz)</option>
                   <option value="10m">10m (26.711-28.759 MHz)</option>
                   <option value="2m">2m (144.896-146.944 MHz)</option>
               </select>
           </div>
           <div class="control-row">
               <label for="websdr-freq">Frequency (kHz):</label>
               <input type="number" id="websdr-freq" value="14200">
               <button id="websdr-tune">Tune</button>
           </div>
           <div class="control-row">
               <label for="websdr-mode">Mode:</label>
               <select id="websdr-mode">
                   <option value="am">AM</option>
                   <option value="fm">FM</option>
                   <option value="lsb">LSB</option>
                   <option value="usb" selected>USB</option>
                   <option value="cw">CW</option>
               </select>
           </div>
       </div>
   </div>
   ```

3. Ensure your WebSocket message handler integrates with the WebSDR data flow

## Error Handling

The integration includes robust error handling:

- WebSocket connection failures trigger automatic reconnection attempts
- WebSocket message parsing errors are caught and logged
- Control interactions are validated before sending commands

## Bandwidth and Performance Considerations

- WebSDR data is typically more lightweight than direct SDR streams
- The waterfall visualization is optional and only processed when available
- Status indicators auto-fade to reduce visual clutter after displaying briefly

## Future Enhancements

Possible improvements to the WebSDR frontend integration:

1. **Multiple WebSDR Support**: Connect to multiple WebSDR stations simultaneously
2. **Dynamic Station Discovery**: Auto-populate WebSDR stations from online directory
3. **Preset Management**: Save and recall favorite frequencies and modes
4. **Audio Support**: Add WebAudio API integration for listening to signals
5. **Signal Analysis**: Add FFT and spectrogram analysis of WebSDR signals
6. **Recording**: Add ability to record and playback WebSDR sessions