# Map Visualization Documentation

## Overview

The `map-visualization.html` file provides a user interface for visualizing SDR FCC violation geolocation data. It integrates a map-based visualization using Leaflet.js to display receivers, signals, and violations in real-time. The interface also includes a sidebar for detailed information and a control panel for WebSDR interactions.

## Structure

The file is structured into three main sections:

1. **Sidebar**: Displays connection status, receiver information, detected signals, and violations.
2. **Map Container**: Hosts the Leaflet.js map for geolocation visualization.
3. **Control Panel**: Provides controls for interacting with WebSDR and other SDR features.

### Sidebar

The sidebar contains:

- **Connection Status**: Displays the current WebSocket connection state (e.g., Connected, Disconnected).
- **Receivers List**: Shows active receivers and their locations.
- **Signals List**: Displays detected signals with details such as frequency, modulation, and power.
- **Violations List**: Highlights unauthorized transmissions.

### Map Container

The map container uses Leaflet.js to visualize:

- **Receivers**: Marked with custom icons.
- **Signals**: Displayed as markers with frequency and modulation details.
- **Violations**: Highlighted with animated markers and uncertainty circles.

### Control Panel

The control panel includes:

- **WebSDR Controls**: Allows users to select bands, tune frequencies, and choose modes.
- **Status Indicators**: Show the connection state of WebSDR.

## Key Features

### Real-Time Data Visualization

The map updates dynamically based on WebSocket messages. It supports:

- Adding and updating receiver markers.
- Displaying detected signals with modulation and power details.
- Highlighting violations with animated markers and uncertainty circles.

### WebSDR Integration

The WebSDR controls allow users to:

- Select frequency bands (e.g., 20m, 40m).
- Tune to specific frequencies.
- Choose signal modes (e.g., AM, USB).

Commands are sent to the backend via WebSocket for real-time interaction.

### Dynamic Styling

The file includes extensive CSS for:

- Styling the sidebar and control panel.
- Customizing map markers for receivers, signals, and violations.
- Animating violation markers and uncertainty circles.

## Initialization

The map and WebSocket connection are initialized in the `<script>` section:

1. **Map Setup**:
   ```javascript
   const map = L.map('map').setView([37.7749, -122.4194], 11);
   L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
       attribution: '&copy; OpenStreetMap contributors'
   }).addTo(map);
   ```

2. **WebSocket Connection**:
   ```javascript
   function connectWebSocket() {
       const socket = new WebSocket('ws://localhost:8080');
       socket.onopen = () => { console.log('WebSocket connected'); };
       socket.onmessage = (event) => { /* Handle incoming data */ };
       socket.onclose = () => { console.log('WebSocket disconnected'); };
   }
   connectWebSocket();
   ```

3. **Layer Groups**:
   ```javascript
   const receiversLayer = L.layerGroup().addTo(map);
   const signalsLayer = L.layerGroup().addTo(map);
   const violationsLayer = L.layerGroup().addTo(map);
   ```

## Usage

1. Open the `map-visualization.html` file in a browser.
2. Ensure the WebSocket server is running on `ws://localhost:8080`.
3. Monitor the sidebar for connection status, receivers, signals, and violations.
4. Use the WebSDR controls to interact with remote SDR stations.

## Future Enhancements

1. **Advanced Geolocation**: Add support for TDoA and multilateration methods.
2. **Signal Filtering**: Allow users to filter signals by frequency, modulation, or power.
3. **Historical Data**: Enable playback of past signal and violation data.
4. **Mobile Support**: Optimize the interface for smaller screens.
5. **Custom Map Layers**: Add satellite imagery or heatmaps for better visualization.