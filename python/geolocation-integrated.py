#!/usr/bin/env python3

import os
import sys
import json
import time
import asyncio
import numpy as np
import websockets

# Try importing GNU Radio modules with error handling
try:
    from gnuradio import gr, blocks, analog, fft, filter
    from gnuradio.fft import window
    from gnuradio.filter import firdes
    import osmosdr
except ImportError as e:
    print(f"Error importing GNU Radio modules: {e}")
    print("Please ensure GNU Radio and gr-osmosdr are installed:")
    print("sudo apt-get install gnuradio gr-osmosdr")
    sys.exit(1)

# Configuration
CONFIG = {
    'sdr': {
        'sample_rate': 2.048e6,  # 2.048 MHz
        'center_freq': 100e6,    # 100 MHz
        'gain': 20,
        'fft_size': 4096,
        'frame_rate': 30,        # FPS for visualization updates
        'decimation': 8,         # Decimation factor for signal processing
    },
    'websocket': {
        'port': 8080,
        'fosphor_port': 8090
    }
}

FFT_SIZE = CONFIG['sdr']['fft_size']
THRESHOLD = -70  # dBm threshold for signal detection

class SDRFlowgraph(gr.top_block):
    def __init__(self):
        gr.top_block.__init__(self, "SDR Signal Processing")
        
        ##################################################
        # Variables
        ##################################################
        self.samp_rate = CONFIG['sdr']['sample_rate']
        self.center_freq = CONFIG['sdr']['center_freq']
        self.gain = CONFIG['sdr']['gain']
        self.decimation = CONFIG['sdr']['decimation']
        
        ##################################################
        # Blocks
        ##################################################
        
        # SDR Source
        self.src = osmosdr.source(args="rtl=0")
        self.src.set_sample_rate(self.samp_rate)
        self.src.set_center_freq(self.center_freq)
        self.src.set_gain(self.gain)
        self.src.set_bandwidth(self.samp_rate)
        
        # Decimation for more efficient processing
        self.decim = filter.fir_filter_ccf(
            self.decimation,
            firdes.low_pass(1, self.samp_rate, self.samp_rate/(2*self.decimation), 2000)
        )
        
        # FFT for spectrum analysis
        self.fft = fft.fft_vcc(FFT_SIZE, True, window.blackmanharris(FFT_SIZE))
        
        # Magnitude squared conversion
        self.mag_squared = blocks.complex_to_mag_squared(FFT_SIZE)
        
        # Log10 conversion for dB scale
        self.log = blocks.nlog10_ff(10, FFT_SIZE)
        
        # Moving average for noise reduction
        self.avg = filter.single_pole_iir_filter_ff(0.1, FFT_SIZE)
        
        # Threshold detector for signal detection
        self.threshold = blocks.threshold_ff(THRESHOLD, THRESHOLD, 0)
        
        # Peak detector for signal frequency identification
        self.peaks = blocks.peak_detector_fb(0.7, 0.5, 0, 0.001)
        
        # Stream to vector for batch processing
        self.s2v = blocks.stream_to_vector(gr.sizeof_float, FFT_SIZE)
        
        # UDP sink for sending data to visualization
        self.udp = blocks.udp_sink(gr.sizeof_float*FFT_SIZE, '127.0.0.1', 12345)
        
        # Fosphor integration
        self.fosphor = fft.fosphor_c(FFT_SIZE)
        self.fosphor.set_frame_rate(CONFIG['sdr']['frame_rate'])
        
        ##################################################
        # Async Message Passing
        ##################################################
        self.msg_q = gr.msg_queue(2)
        self.msg_sink = blocks.message_sink(gr.sizeof_float*FFT_SIZE, self.msg_q, True)
        
        ##################################################
        # Connections
        ##################################################
        
        # Main signal path
        self.connect(self.src, self.decim, self.fft, self.mag_squared)
        self.connect(self.mag_squared, self.log, self.avg)
        
        # Threshold detection path
        self.connect(self.avg, self.threshold, self.peaks)
        
        # Data output paths
        self.connect(self.avg, self.s2v, self.udp)
        self.connect(self.avg, self.msg_sink)
        
        # Fosphor visualization path
        self.connect(self.decim, self.fosphor)

class SignalProcessor:
    def __init__(self):
        self.tb = SDRFlowgraph()
        self.loop = asyncio.get_event_loop()
        self.websocket_clients = set()
        
    async def start(self):
        """Start the flowgraph and WebSocket server"""
        print("Starting SDR flowgraph...")
        self.tb.start()
        
        # Start WebSocket servers
        main_server = websockets.serve(
            self.handle_client,
            'localhost',
            CONFIG['websocket']['port']
        )
        
        fosphor_server = websockets.serve(
            self.handle_fosphor_client,
            'localhost',
            CONFIG['websocket']['fosphor_port']
        )
        
        await asyncio.gather(main_server, fosphor_server)
        
    async def handle_client(self, websocket, path):
        """Handle main WebSocket client connection"""
        self.websocket_clients.add(websocket)
        try:
            while True:
                # Process queue data
                while not self.tb.msg_q.empty_p():
                    msg = self.tb.msg_q.delete_head()
                    data = self.process_fft_data(msg.to_string())
                    await self.broadcast_data(data)
                await asyncio.sleep(1.0 / CONFIG['sdr']['frame_rate'])
        finally:
            self.websocket_clients.remove(websocket)
    
    async def handle_fosphor_client(self, websocket, path):
        """Handle Fosphor WebSocket client connection"""
        try:
            while True:
                # Get Fosphor data
                data = self.tb.fosphor.get_data()
                if data:
                    await websocket.send(data)
                await asyncio.sleep(1.0 / CONFIG['sdr']['frame_rate'])
        except websockets.exceptions.ConnectionClosed:
            pass
    
    def process_fft_data(self, data):
        """Process FFT data and detect signals"""
        # Convert bytes to numpy array
        fft_data = np.frombuffer(data, dtype=np.float32)
        
        # Find peaks above threshold
        peaks = self.find_peaks(fft_data)
        
        # Detect modulation types
        signals = self.classify_signals(fft_data, peaks)
        
        # Format data for visualization
        return {
            'freqs': self.get_frequency_array(),
            'amplitudes': fft_data.tolist(),
            'signals': signals,
            'timestamp': time.time()
        }
    
    def find_peaks(self, fft_data):
        """Find signal peaks in FFT data"""
        # Simple peak detection algorithm
        peak_indices = []
        for i in range(1, len(fft_data) - 1):
            if (fft_data[i] > fft_data[i-1] and 
                fft_data[i] > fft_data[i+1] and 
                fft_data[i] > THRESHOLD):
                peak_indices.append(i)
        return peak_indices
    
    def classify_signals(self, fft_data, peaks):
        """Classify detected signals"""
        signals = []
        for peak_idx in peaks:
            freq = self.index_to_frequency(peak_idx)
            bw = self.estimate_bandwidth(fft_data, peak_idx)
            mod = self.detect_modulation(fft_data, peak_idx)
            
            signals.append({
                'frequency_mhz': freq / 1e6,
                'power': fft_data[peak_idx],
                'bandwidth': bw,
                'modulation': mod
            })
        return signals
    
    def get_frequency_array(self):
        """Generate frequency array for visualization"""
        return np.linspace(
            self.tb.center_freq - self.tb.samp_rate/2,
            self.tb.center_freq + self.tb.samp_rate/2,
            FFT_SIZE
        ).tolist()
    
    async def broadcast_data(self, data):
        """Broadcast data to all connected clients"""
        if self.websocket_clients:
            message = json.dumps(data)
            await asyncio.gather(*[
                client.send(message)
                for client in self.websocket_clients
            ])
    
    def index_to_frequency(self, index):
        """Convert FFT bin index to frequency"""
        freq_resolution = self.tb.samp_rate / FFT_SIZE
        freq_offset = index * freq_resolution
        return self.tb.center_freq - (self.tb.samp_rate / 2) + freq_offset
    
    def estimate_bandwidth(self, fft_data, peak_idx):
        """Estimate signal bandwidth using -3dB points"""
        peak_power = fft_data[peak_idx]
        threshold = peak_power - 3  # -3dB points
        
        # Find lower bound
        lower_idx = peak_idx
        while lower_idx > 0 and fft_data[lower_idx] > threshold:
            lower_idx -= 1
            
        # Find upper bound
        upper_idx = peak_idx
        while upper_idx < len(fft_data) - 1 and fft_data[upper_idx] > threshold:
            upper_idx += 1
        
        # Convert to frequency
        lower_freq = self.index_to_frequency(lower_idx)
        upper_freq = self.index_to_frequency(upper_idx)
        
        return abs(upper_freq - lower_freq)
    
    def detect_modulation(self, fft_data, peak_idx):
        """Detect signal modulation type based on spectral characteristics"""
        # Get signal segment around peak
        window_size = 20
        start_idx = max(0, peak_idx - window_size)
        end_idx = min(len(fft_data), peak_idx + window_size)
        segment = fft_data[start_idx:end_idx]
        
        # Calculate spectral features
        bandwidth = self.estimate_bandwidth(fft_data, peak_idx)
        peak_power = fft_data[peak_idx]
        std_dev = np.std(segment)
        skewness = np.mean((segment - np.mean(segment))**3) / std_dev**3
        
        # Simple modulation classification based on spectral features
        if bandwidth < 10e3:  # Narrow signal
            if std_dev < 2:
                return 'CW'
            else:
                return 'SSB'
        elif bandwidth < 50e3:  # Medium bandwidth
            if skewness > 1:
                return 'AM'
            else:
                return 'PSK'
        else:  # Wide bandwidth
            if std_dev > 5:
                return 'FM'
            else:
                return 'FSK'

if __name__ == '__main__':
    processor = SignalProcessor()
    try:
        asyncio.get_event_loop().run_until_complete(processor.start())
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        processor.tb.stop()
        processor.tb.wait()
