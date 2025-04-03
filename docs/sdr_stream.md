# SDR Stream

## Overview
The `sdr_stream.py` module provides real-time streaming of Software Defined Radio (SDR) data over WebSockets. It captures raw IQ samples from an RTL-SDR device, computes FFT for spectrum analysis, and transmits the processed data to connected clients.

## Features
- Real-time SDR signal capture using RTL-SDR hardware
- Fast Fourier Transform (FFT) processing for spectrum visualization
- WebSocket-based data streaming to web clients
- Configurable sample rate and frequency settings

## Technical Details

### Dependencies
- `rtlsdr`: Python wrapper for librtlsdr
- `numpy`: For numerical processing and FFT computation
- `websockets`: For WebSocket server implementation
- `asyncio`: For asynchronous I/O operations

### Configuration
The module uses the following default parameters:
- WebSocket Port: 8765
- Sample Rate: 2.048 MHz
- Center Frequency: 100 MHz (adjustable)
- Gain: 10 dB (adjustable)

### Data Format
Data is streamed as JSON with the following structure:
```json
{
  "freqs": [...],       // Frequency array in Hz
  "amplitudes": [...],  // Normalized FFT magnitudes
  "timestamp": 1234567  // Timestamp of data capture
}
```

## Usage
1. Connect an RTL-SDR device to your system
2. Run the script: `python sdr_stream.py`
3. Connect clients to the WebSocket server at `ws://server-ip:8765`

## Integration
The `sdr_stream.py` module is designed to work with the frontend visualization components. The data format is compatible with the ThreeJS-based spectrum displays in the frontend.

## Future Improvements
- Support for additional SDR hardware types
- Dynamic frequency and gain adjustment via WebSocket commands
- Signal classification and identification features