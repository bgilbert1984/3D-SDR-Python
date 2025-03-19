#!/usr/bin/env python3

import os
import sys
import json
import time
import asyncio
import numpy as np
import websockets
import math
import matplotlib.pyplot as plt
from datetime import datetime

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
    },
    'emp': {
        'enabled': False,        # EMP simulation enabled by default
        'yield_kt': 50,          # Default yield in kilotons
        'distance_km': 10,       # Default distance in km
        'duration_sec': 5,       # Duration of EMP effects in seconds
        'auto_detect': True      # Auto-detect EMP events
    }
}

FFT_SIZE = CONFIG['sdr']['fft_size']
THRESHOLD = -70  # dBm threshold for signal detection

class EMP_Simulator:
    """
    Simulates EMP (Electromagnetic Pulse) effects based on yield and distance.
    """
    def __init__(self, yield_kt=50):
        """
        Initialize the EMP simulator.
        :param yield_kt: EMP yield in kilotons (default: 50kT, similar to a tactical nuclear EMP).
        """
        self.yield_kt = yield_kt
        self.emp_radius_km = self.calculate_emp_radius()
        self.active = False
        self.start_time = None
        self.impact_location = None
        self.prev_fft_data = None
        self.detection_threshold = 0.75  # Confidence threshold for auto-detection
        
    def calculate_emp_radius(self):
        """
        Estimate EMP effect radius based on yield using an empirical scaling formula.
        """
        return 4.4 * (self.yield_kt ** (1/3))  # Approximate radius in km
    
    def emp_field_strength(self, distance_km):
        """
        Compute EMP field strength at a given distance.
        :param distance_km: Distance from EMP source in km.
        :return: Estimated field strength in V/m.
        """
        if distance_km > self.emp_radius_km:
            return 0  # No effect beyond EMP range
        
        E0 = 50_000  # Peak field strength in V/m at 1 km (approximate value)
        attenuation = math.exp(-distance_km / (self.emp_radius_km / 2))  # Exponential decay
        return E0 * attenuation
    
    def simulate_emp_effect(self, distances_km):
        """
        Simulate EMP field strength over a range of distances.
        """
        field_strengths = [self.emp_field_strength(d) for d in distances_km]
        return field_strengths
        
    def plot_emp_effect(self):
        """
        Generate a plot showing EMP field strength vs. distance.
        """
        distances = np.linspace(0, self.emp_radius_km * 1.2, 100)
        strengths = self.simulate_emp_effect(distances)
        
        plt.figure(figsize=(8, 5))
        plt.plot(distances, strengths, label=f'EMP Effect (Yield: {self.yield_kt} kT)')
        plt.axvline(self.emp_radius_km, color='r', linestyle='--', label='EMP Max Range')
        plt.xlabel('Distance from Source (km)')
        plt.ylabel('Field Strength (V/m)')
        plt.title('EMP Field Strength vs Distance')
        plt.legend()
        plt.grid()
        
        # Save plot to file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"emp_simulation_{timestamp}.png"
        plt.savefig(filename)
        plt.close()
        return filename
    
    def trigger_emp_event(self, yield_kt=None, distance_km=10):
        """
        Trigger an EMP event with the specified yield and distance.
        """
        if yield_kt is not None:
            self.yield_kt = yield_kt
            self.emp_radius_km = self.calculate_emp_radius()
        
        self.active = True
        self.start_time = time.time()
        self.impact_location = distance_km
        return {
            "event": "emp_triggered",
            "yield_kt": self.yield_kt,
            "radius_km": self.emp_radius_km,
            "distance_km": distance_km,
            "field_strength": self.emp_field_strength(distance_km),
            "timestamp": self.start_time
        }
    
    def is_active(self, current_time=None, duration_sec=5):
        """
        Check if the EMP event is still active.
        """
        if not self.active:
            return False
        
        if current_time is None:
            current_time = time.time()
            
        if current_time - self.start_time > duration_sec:
            self.active = False
            return False
        
        return True
    
    def apply_emp_effect_to_signal(self, fft_data, duration_sec=5):
        """
        Apply EMP effect to FFT data based on current EMP state.
        """
        if not self.active:
            return fft_data
            
        current_time = time.time()
        
        # Check if EMP is still active
        if not self.is_active(current_time, duration_sec):
            return fft_data
        
        # Calculate effect intensity based on time elapsed (E1, E2, E3 phases)
        elapsed = current_time - self.start_time
        if elapsed < 0.1:  # E1 phase (first 100ns to 1µs, but scaled to 100ms for visibility)
            intensity = 1.0  # Full intensity
        elif elapsed < 1.0:  # E2 phase (1µs to 1s, scaled)
            intensity = 0.7
        else:  # E3 phase (1s to several minutes)
            intensity = 0.4 * (1 - (elapsed - 1) / duration_sec)
            
        # Apply EMP effect to signal: increase noise floor and disrupt signal patterns
        noise_level = intensity * 30  # dB increase in noise floor
        field_strength = self.emp_field_strength(self.impact_location)
        
        # Scale effect based on field strength
        scale_factor = min(1.0, field_strength / 25_000)
        
        # Apply disruption: raise noise floor and compress dynamic range
        affected_data = fft_data.copy()
        
        # Add noise proportional to EMP intensity
        noise = np.random.normal(0, noise_level * scale_factor, len(fft_data))
        affected_data += noise
        
        # Compress dynamic range (signals become less distinct)
        mean_val = np.mean(affected_data)
        affected_data = (affected_data - mean_val) * (1 - 0.5 * intensity * scale_factor) + mean_val
        
        # Random spike patterns characteristic of EMP
        if np.random.random() < 0.3 * intensity:  # Probability of spikes
            spike_indices = np.random.choice(len(affected_data), int(len(affected_data) * 0.05 * intensity))
            affected_data[spike_indices] += np.random.uniform(10, 30, len(spike_indices))
            
        return affected_data
        
    def detect_emp_signature(self, fft_data, prev_fft_data=None):
        """
        Detect potential EMP signatures in FFT data.
        Returns confidence level (0-1) that an EMP event occurred.
        """
        if prev_fft_data is None:
            return 0.0
            
        # EMP detection criteria:
        # 1. Sudden broadband noise increase
        # 2. Characteristic spectral pattern
        # 3. Rapid change in overall power
        
        # Check for sudden noise floor increase
        curr_noise_floor = np.percentile(fft_data, 20)  # 20th percentile as noise floor
        prev_noise_floor = np.percentile(prev_fft_data, 20)
        noise_increase = curr_noise_floor - prev_noise_floor
        
        # Check for sudden power change
        curr_power = np.mean(fft_data)
        prev_power = np.mean(prev_fft_data)
        power_change = abs(curr_power - prev_power)
        
        # Check for broadband pattern (high frequency content across spectrum)
        high_freq_content = np.std(fft_data - prev_fft_data)
        
        # Combined confidence score
        confidence = 0.0
        if noise_increase > 10:  # >10 dB noise floor increase
            confidence += 0.4
        if power_change > 15:    # >15 dB power change
            confidence += 0.3
        if high_freq_content > 5:  # High variation across spectrum
            confidence += 0.3
            
        return min(1.0, confidence)

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
        self.emp_simulator = EMP_Simulator(CONFIG['emp']['yield_kt'])
        self.prev_fft_data = None
        
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
            # Handle incoming commands from client
            command_task = asyncio.create_task(self.handle_commands(websocket))
            
            # Handle data streaming to client
            while True:
                # Process queue data
                while not self.tb.msg_q.empty_p():
                    msg = self.tb.msg_q.delete_head()
                    data = self.process_fft_data(msg.to_string())
                    await self.broadcast_data(data)
                await asyncio.sleep(1.0 / CONFIG['sdr']['frame_rate'])
                
        except websockets.exceptions.ConnectionClosed:
            command_task.cancel()
        finally:
            self.websocket_clients.remove(websocket)
    
    async def handle_commands(self, websocket):
        """Handle commands from WebSocket client"""
        try:
            async for message in websocket:
                try:
                    command = json.loads(message)
                    if 'type' not in command:
                        continue
                        
                    if command['type'] == 'emp_simulate':
                        # Trigger EMP simulation
                        yield_kt = command.get('yield_kt', CONFIG['emp']['yield_kt'])
                        distance_km = command.get('distance_km', CONFIG['emp']['distance_km'])
                        
                        # Update configuration
                        CONFIG['emp']['enabled'] = True
                        CONFIG['emp']['yield_kt'] = yield_kt
                        CONFIG['emp']['distance_km'] = distance_km
                        
                        # Trigger EMP event
                        emp_event = self.emp_simulator.trigger_emp_event(yield_kt, distance_km)
                        
                        # Generate and save plot
                        plot_file = self.emp_simulator.plot_emp_effect()
                        
                        # Send confirmation back to client
                        response = {
                            'type': 'emp_simulation_started',
                            'event': emp_event,
                            'plot_file': plot_file
                        }
                        await websocket.send(json.dumps(response))
                        print(f"EMP simulation triggered: {yield_kt}kT at {distance_km}km")
                        
                    elif command['type'] == 'emp_configure':
                        # Update EMP configuration
                        CONFIG['emp']['enabled'] = command.get('enabled', CONFIG['emp']['enabled'])
                        CONFIG['emp']['yield_kt'] = command.get('yield_kt', CONFIG['emp']['yield_kt'])
                        CONFIG['emp']['distance_km'] = command.get('distance_km', CONFIG['emp']['distance_km'])
                        CONFIG['emp']['duration_sec'] = command.get('duration_sec', CONFIG['emp']['duration_sec'])
                        CONFIG['emp']['auto_detect'] = command.get('auto_detect', CONFIG['emp']['auto_detect'])
                        
                        # Update simulator settings
                        self.emp_simulator.yield_kt = CONFIG['emp']['yield_kt']
                        self.emp_simulator.emp_radius_km = self.emp_simulator.calculate_emp_radius()
                        
                        # Send confirmation back to client
                        response = {
                            'type': 'emp_config_updated',
                            'config': CONFIG['emp']
                        }
                        await websocket.send(json.dumps(response))
                        print(f"EMP configuration updated: {CONFIG['emp']}")
                        
                    elif command['type'] == 'emp_stop':
                        # Stop EMP simulation
                        self.emp_simulator.active = False
                        CONFIG['emp']['enabled'] = False
                        
                        # Send confirmation back to client
                        response = {
                            'type': 'emp_simulation_stopped',
                            'timestamp': time.time()
                        }
                        await websocket.send(json.dumps(response))
                        print("EMP simulation stopped")
                        
                except json.JSONDecodeError:
                    print(f"Invalid JSON message: {message}")
                except Exception as e:
                    print(f"Error handling command: {e}")
                    
        except websockets.exceptions.ConnectionClosed:
            pass
            
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
        
        # Detect EMP signatures if auto-detection is enabled and there's previous data
        emp_detected = False
        emp_confidence = 0.0
        
        if CONFIG['emp']['auto_detect'] and self.prev_fft_data is not None:
            emp_confidence = self.emp_simulator.detect_emp_signature(fft_data, self.prev_fft_data)
            if emp_confidence >= self.emp_simulator.detection_threshold and not self.emp_simulator.active:
                # Auto-trigger EMP event
                emp_event = self.emp_simulator.trigger_emp_event(CONFIG['emp']['yield_kt'], CONFIG['emp']['distance_km'])
                print(f"EMP automatically detected! Confidence: {emp_confidence:.2f}")
                emp_detected = True
                CONFIG['emp']['enabled'] = True
        
        # Store current data for future comparison
        self.prev_fft_data = fft_data.copy()
        
        # Apply EMP effect if active
        if CONFIG['emp']['enabled']:
            fft_data = self.emp_simulator.apply_emp_effect_to_signal(fft_data, CONFIG['emp']['duration_sec'])
        
        # Find peaks above threshold
        peaks = self.find_peaks(fft_data)
        
        # Detect modulation types
        signals = self.classify_signals(fft_data, peaks)
        
        # Format data for visualization
        result = {
            'freqs': self.get_frequency_array(),
            'amplitudes': fft_data.tolist(),
            'signals': signals,
            'timestamp': time.time()
        }
        
        # Add EMP information if active or detected
        if self.emp_simulator.active or emp_detected:
            result['emp'] = {
                'active': self.emp_simulator.active,
                'yield_kt': self.emp_simulator.yield_kt,
                'distance_km': self.emp_simulator.impact_location,
                'radius_km': self.emp_simulator.emp_radius_km,
                'elapsed_sec': time.time() - self.emp_simulator.start_time if self.emp_simulator.start_time else 0,
                'auto_detected': emp_detected,
                'confidence': emp_confidence if emp_detected else None
            }
        
        return result
    
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
        
        # Check if we're under EMP influence
        if self.emp_simulator.active:
            # Under EMP, signal classification is degraded
            elapsed = time.time() - self.emp_simulator.start_time
            if elapsed < 0.5:  # Early EMP effect causes misclassification
                # Random classification during peak EMP effect
                choices = ['AM', 'FM', 'CW', 'SSB', 'PSK', 'FSK', 'UNKNOWN']
                weights = [0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.4]  # Higher chance of UNKNOWN
                return np.random.choice(choices, p=weights)
        
        # Normal classification
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
        print("Starting SDR Signal Processor with EMP Simulation capability")
        print(f"WebSocket server available at: ws://localhost:{CONFIG['websocket']['port']}")
        print(f"Fosphor visualization at: ws://localhost:{CONFIG['websocket']['fosphor_port']}")
        print("Use the WebSocket interface to trigger and configure EMP simulations")
        print("Press Ctrl+C to exit")
        
        asyncio.get_event_loop().run_until_complete(processor.start())
        asyncio.get_event_loop().run_forever()
    except KeyboardInterrupt:
        print("\nShutting down...")
        processor.tb.stop()
        processor.tb.wait()
