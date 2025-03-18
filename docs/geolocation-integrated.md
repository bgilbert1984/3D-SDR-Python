# Geolocation Integration

## Overview
The `geolocation-integrated.py` script is a core component of the SDR Drone Pursuit System. It integrates GNU Radio signal processing with WebSocket-based real-time data streaming to enable geolocation and visualization of RF signals. This script processes SDR data, detects signals, and provides geolocation insights for visualization and analysis.

## Key Features

1. **GNU Radio Integration**:
   - Uses GNU Radio blocks for signal processing, including FFT, filtering, and decimation.
   - Supports real-time spectrum analysis and signal detection.

2. **WebSocket Communication**:
   - Streams processed signal data to connected clients for visualization.
   - Supports multiple WebSocket endpoints for different data streams (e.g., main data and Fosphor visualization).

3. **Signal Detection and Classification**:
   - Detects signal peaks in the spectrum.
   - Classifies signals based on spectral characteristics (e.g., bandwidth, skewness).

4. **Fosphor Integration**:
   - Provides GPU-accelerated spectrum visualization using Fosphor.

5. **Real-Time Processing**:
   - Processes SDR data in real-time with configurable frame rates and thresholds.

## Configuration

The script uses a configuration dictionary (`CONFIG`) to define key parameters:

### SDR Settings
- `sample_rate`: The sampling rate of the SDR (default: 2.048 MHz).
- `center_freq`: The center frequency for signal processing (default: 100 MHz).
- `gain`: The gain setting for the SDR (default: 20).
- `fft_size`: The size of the FFT for spectrum analysis (default: 4096).
- `frame_rate`: The frame rate for visualization updates (default: 30 FPS).
- `decimation`: The decimation factor for reducing the sampling rate (default: 8).

### WebSocket Settings
- `port`: The port for the main WebSocket server (default: 8080).
- `fosphor_port`: The port for the Fosphor WebSocket server (default: 8090).

## GNU Radio Flowgraph

The `SDRFlowgraph` class defines the GNU Radio signal processing flowgraph. Key components include:

1. **SDR Source**:
   - Configures the SDR hardware (e.g., RTL-SDR) for data acquisition.

2. **Decimation**:
   - Reduces the sampling rate for more efficient processing.

3. **FFT**:
   - Performs Fast Fourier Transform for spectrum analysis.

4. **Magnitude Squared and Log Conversion**:
   - Converts complex FFT output to magnitude squared and applies log scaling for dB representation.

5. **Threshold and Peak Detection**:
   - Identifies signal peaks above a configurable threshold.

6. **Fosphor Visualization**:
   - Integrates Fosphor for GPU-accelerated spectrum visualization.

## Signal Processing

The `SignalProcessor` class manages the GNU Radio flowgraph and WebSocket communication. Key methods include:

### `start`
Starts the GNU Radio flowgraph and WebSocket servers for real-time data streaming.

### `handle_client`
Handles WebSocket connections for the main data stream. Processes FFT data and broadcasts it to connected clients.

### `handle_fosphor_client`
Handles WebSocket connections for Fosphor visualization data.

### `process_fft_data`
Processes FFT data to detect signals and classify them based on spectral characteristics. Returns a dictionary containing:
- Frequencies
- Amplitudes
- Detected signals
- Timestamp

### `find_peaks`
Detects signal peaks in the FFT data using a simple peak detection algorithm.

### `classify_signals`
Classifies detected signals based on spectral features such as bandwidth, power, and skewness. Supported modulation types include:
- CW (Continuous Wave)
- SSB (Single Sideband)
- AM (Amplitude Modulation)
- PSK (Phase Shift Keying)
- FM (Frequency Modulation)
- FSK (Frequency Shift Keying)

## Example Workflow

1. **Start the Script**:
   ```bash
   python geolocation-integrated.py
   ```

2. **Connect to WebSocket**:
   - Main data stream: `ws://localhost:8080`
   - Fosphor visualization: `ws://localhost:8090`

3. **Visualize Data**:
   - Use a WebSocket client or visualization tool to display the spectrum and detected signals.

## Future Enhancements

1. **Advanced Geolocation**:
   - Integrate Time Difference of Arrival (TDOA) or multilateration for precise geolocation.

2. **Improved Modulation Classification**:
   - Use machine learning models for more accurate signal classification.

3. **Dynamic Configuration**:
   - Allow runtime updates to configuration parameters via WebSocket commands.

4. **Enhanced Visualization**:
   - Add support for 3D spectrum visualization and interactive controls.