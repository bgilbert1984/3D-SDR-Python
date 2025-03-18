import asyncio
import numpy as np
import websockets
import requests
import json
import time
import os
from rtlsdr import RtlSdr

# Optional dependencies
try:
    from pymongo import MongoClient
    HAVE_MONGODB = True
except ImportError:
    HAVE_MONGODB = False
    print("MongoDB not available - logging will be disabled")

try:
    from signal_classifier import SignalClassifier, MODULATION_TYPES
    HAVE_CLASSIFIER = True
except ImportError:
    HAVE_CLASSIFIER = False
    print("Signal classifier not available - using basic classification")
    MODULATION_TYPES = {
        'AM': 'Amplitude Modulation',
        'FM': 'Frequency Modulation',
        'SSB': 'Single Sideband',
        'CW': 'Continuous Wave',
        'UNKNOWN': 'Unknown Modulation'
    }

# Global configuration
CONFIG = {
    'sdr': {
        'sample_rate': 2.048e6,  # 2.048 MHz
        'center_freq': 100e6,    # 100 MHz (FM broadcast band)
        'gain': 20,              # Gain setting
        'num_samples': 256 * 1024  # Number of samples to read
    },
    'websocket': {
        'host': '0.0.0.0',
        'port': 8765,
        'fosphor_port': 8090    # Port for Fosphor visualization
    },
    'visualization': {
        'waterfall_height': 512,
        'waterfall_width': 1024,
        'frame_rate': 30,
        'colormap': 'viridis'
    },
    'eibi': {
        'url': 'https://www.eibispace.de/dx/freq-a.txt',
        'refresh_hours': 24  # Refresh EIBI database every 24 hours
    },
    'mongodb': {
        'uri': 'mongodb://localhost:27017/',
        'db_name': 'fcc_monitor',
        'violations_collection': 'violations',
        'signals_collection': 'signals'
    },
    'detection': {
        'signal_threshold': 0.3,  # Minimum amplitude to consider as a signal
        'freq_tolerance_khz': 5,  # Frequency matching tolerance in kHz
        'window_size': 20,        # Window size for signal analysis
        'min_confidence': 0.6     # Minimum classifier confidence to accept
    },
    'classifier': {
        'model_path': 'signal_classifier_model.pkl'
    }
}

# MongoDB Connection Setup
def setup_mongodb():
    if not HAVE_MONGODB:
        return None
    try:
        client = MongoClient(CONFIG['mongodb']['uri'])
        db = client[CONFIG['mongodb']['db_name']]
        violations_collection = db[CONFIG['mongodb']['violations_collection']]
        signals_collection = db[CONFIG['mongodb']['signals_collection']]
        
        print("Connected to MongoDB successfully")
        return {
            'violations': violations_collection,
            'signals': signals_collection
        }
    except Exception as e:
        print(f"MongoDB connection error: {e}")
        print("Continuing without database logging...")
        return None

# Load EIBI Database with caching
def load_eibi_data(force_refresh=False):
    cache_file = "eibi_cache.json"
    cache_max_age = CONFIG['eibi']['refresh_hours'] * 3600  # Convert hours to seconds
    
    # Check if cache exists and is recent enough
    if not force_refresh and os.path.exists(cache_file):
        try:
            with open(cache_file, 'r') as f:
                cache_data = json.load(f)
                
            # Check cache age
            cache_time = cache_data.get('timestamp', 0)
            if time.time() - cache_time < cache_max_age:
                print(f"Using cached EIBI data (age: {(time.time() - cache_time) / 3600:.1f} hours)")
                return cache_data.get('data', [])
        except Exception as e:
            print(f"Error reading cache: {e}")
    
    print("Fetching fresh EIBI database...")
    try:
        response = requests.get(CONFIG['eibi']['url'], timeout=30)
        
        if response.status_code != 200:
            print(f"Failed to retrieve EIBI data: HTTP {response.status_code}")
            # Try to use cache even if expired
            if os.path.exists(cache_file):
                with open(cache_file, 'r') as f:
                    return json.load(f).get('data', [])
            return []
        
        eibi_data = []
        for line in response.text.splitlines():
            # EIBI format: freq(kHz);ITU;station;country;etc...
            parts = line.split(';')
            if len(parts) >= 5 and parts[0].strip().isdigit():
                eibi_data.append({
                    "frequency_kHz": float(parts[0]),
                    "itu_code": parts[1],
                    "station": parts[2],
                    "country": parts[3],
                    "mode": parts[4]
                })
        
        # Save to cache
        with open(cache_file, 'w') as f:
            json.dump({
                'timestamp': time.time(),
                'data': eibi_data
            }, f)
        
        print(f"Loaded {len(eibi_data)} entries from EIBI database")
        return eibi_data
    except Exception as e:
        print(f"Error loading EIBI database: {e}")
        # Try to use cache even if expired
        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r') as f:
                    return json.load(f).get('data', [])
            except:
                pass
        return []

# SDR Configuration
def setup_sdr():
    try:
        sdr = RtlSdr()
        sdr.sample_rate = CONFIG['sdr']['sample_rate']
        sdr.center_freq = CONFIG['sdr']['center_freq']
        sdr.gain = CONFIG['sdr']['gain']
        print(f"SDR initialized at {sdr.center_freq/1e6:.3f} MHz")
        return sdr
    except Exception as e:
        print(f"Error initializing SDR: {e}")
        return None

# Find peaks in FFT data
def find_signal_peaks(freqs, fft_data, threshold=0.3):
    peaks = []
    window_size = CONFIG['detection']['window_size']
    
    # Find local maxima
    for i in range(window_size, len(fft_data) - window_size):
        if fft_data[i] > threshold:
            # Check if it's a local maximum
            if fft_data[i] > max(fft_data[i-window_size:i]) and fft_data[i] > max(fft_data[i+1:i+window_size+1]):
                peaks.append(i)
    
    return peaks

# Detect violations by comparing with EIBI database and classifying signals
def analyze_signals(freqs, fft_data, eibi_db, classifier):
    threshold = CONFIG['detection']['signal_threshold']
    tolerance_khz = CONFIG['detection']['freq_tolerance_khz']
    signals = []
    violations = []
    
    # Find signal peaks
    peak_indices = find_signal_peaks(freqs, fft_data, threshold)
    
    # Convert Hz to kHz for comparison with EIBI database
    freqs_khz = freqs / 1000.0
    
    # Analyze each peak
    for idx in peak_indices:
        freq_khz = freqs_khz[idx]
        power = fft_data[idx]
        
        # Extract window around the peak for classification
        window_start = max(0, idx - CONFIG['detection']['window_size'])
        window_end = min(len(fft_data), idx + CONFIG['detection']['window_size'] + 1)
        peak_freqs = freqs[window_start:window_end]
        peak_amplitudes = fft_data[window_start:window_end]
        
        # Classify the signal - use basic classification if classifier not available
        if HAVE_CLASSIFIER and classifier:
            classification = classifier.predict(peak_freqs, peak_amplitudes, threshold=threshold)
            modulation = classification['modulation']
            confidence = classification['confidence']
        else:
            # Basic classification based on spectral shape
            modulation, confidence = basic_classify_signal(peak_freqs, peak_amplitudes)
        
        # Only accept classification if confidence is high enough
        if confidence < CONFIG['detection']['min_confidence']:
            modulation = 'UNKNOWN'
        
        # Look for a match in EIBI database
        match = None
        for entry in eibi_db:
            if abs(entry["frequency_kHz"] - freq_khz) < tolerance_khz:
                match = entry
                break
        
        # Create signal record
        signal_record = {
            "frequency_khz": freq_khz,
            "frequency_mhz": freq_khz / 1000.0,
            "power": float(power),
            "modulation": modulation,
            "confidence": float(confidence),
            "timestamp": time.time(),
            "matched": match is not None
        }
        
        # If match found, add station information
        if match:
            signal_record["station"] = match["station"]
            signal_record["country"] = match["country"]
            signal_record["eibi_mode"] = match["mode"]
        
        # Add to signals list
        signals.append(signal_record)
        
        # If no match found and signal is strong, consider it a potential violation
        if not match and power > threshold:
            violations.append(signal_record)
    
    return signals, violations

def basic_classify_signal(freqs, amplitudes):
    """Basic signal classification when ML classifier is not available"""
    # Calculate basic spectral features
    bandwidth = np.abs(freqs[-1] - freqs[0])
    peak_amp = np.max(amplitudes)
    mean_amp = np.mean(amplitudes)
    std_amp = np.std(amplitudes)
    
    # Simple classification rules
    if bandwidth < 5000:  # Very narrow signal
        if std_amp < 0.1:
            return 'CW', 0.7
        else:
            return 'SSB', 0.6
    elif bandwidth < 15000:  # Medium bandwidth
        if peak_amp > 2 * mean_amp:
            return 'AM', 0.65
        else:
            return 'SSB', 0.6
    else:  # Wide bandwidth
        if std_amp > 0.2:
            return 'FM', 0.7
        else:
            return 'UNKNOWN', 0.5

def setup_visualization_backend():
    """Set up the best available visualization backend"""
    try:
        # Try to import fosphor for GPU-accelerated visualization
        import gr_fosphor
        print("Using Fosphor for GPU-accelerated visualization")
        return create_fosphor_backend()
    except ImportError:
        print("Fosphor not available, falling back to standard visualization")
        return create_standard_backend()

def create_fosphor_backend():
    """Create a Fosphor-based visualization backend"""
    try:
        import gr_fosphor
        backend = {
            'type': 'fosphor',
            'fft_size': CONFIG['sdr']['num_samples'],
            'height': CONFIG['visualization']['waterfall_height'],
            'width': CONFIG['visualization']['waterfall_width'],
            'frame_rate': CONFIG['visualization']['frame_rate']
        }
        
        # Initialize Fosphor block
        fosphor = gr_fosphor.fosphor_qt()
        fosphor.set_frequency_range(CONFIG['sdr']['center_freq'], CONFIG['sdr']['sample_rate'])
        fosphor.set_palette(CONFIG['visualization']['colormap'])
        
        backend['fosphor'] = fosphor
        return backend
    except Exception as e:
        print(f"Error creating Fosphor backend: {e}")
        return create_standard_backend()

def create_standard_backend():
    """Create a standard CPU-based visualization backend"""
    return {
        'type': 'standard',
        'fft_size': CONFIG['sdr']['num_samples'],
        'height': CONFIG['visualization']['waterfall_height'],
        'width': CONFIG['visualization']['waterfall_width'],
        'frame_rate': CONFIG['visualization']['frame_rate'],
        'waterfall_data': np.zeros((
            CONFIG['visualization']['waterfall_height'],
            CONFIG['visualization']['waterfall_width']
        ), dtype=np.float32)
    }

def update_visualization(backend, fft_data):
    """Update visualization data based on backend type"""
    if backend['type'] == 'fosphor':
        # Fosphor handles the visualization internally
        backend['fosphor'].update_data(fft_data)
        return None
    else:
        # Standard visualization - roll waterfall and add new line
        backend['waterfall_data'] = np.roll(backend['waterfall_data'], -1, axis=0)
        backend['waterfall_data'][-1] = fft_data
        return backend['waterfall_data']

# WebSocket handler for SDR streaming with violation detection
async def sdr_stream_with_detection(websocket, path, eibi_db, classifier, collections):
    print("Client connected to SDR data stream with violation detection")
    
    # Set up visualization backend
    vis_backend = setup_visualization_backend()
    
    sdr = setup_sdr()
    if not sdr:
        # Fallback to simulation mode if SDR is not available
        await simulate_sdr_with_detection(websocket, eibi_db, classifier, collections)
        return
    
    try:
        while True:
            # Read samples from SDR
            samples = sdr.read_samples(CONFIG['sdr']['num_samples'])
            
            # Compute FFT
            fft_data = np.fft.fftshift(np.abs(np.fft.fft(samples)))
            freqs = np.fft.fftshift(np.fft.fftfreq(len(samples), 
                                   1 / CONFIG['sdr']['sample_rate'])) + CONFIG['sdr']['center_freq']
            
            # Normalize FFT data
            fft_data = fft_data / np.max(fft_data) if np.max(fft_data) > 0 else fft_data
            
            # Update visualization
            waterfall_data = update_visualization(vis_backend, fft_data)
            
            # Analyze signals and detect violations
            signals, violations = analyze_signals(freqs, fft_data, eibi_db, classifier)
            
            # Log to MongoDB if available
            if collections:
                try:
                    if violations:
                        collections['violations'].insert_many(violations)
                    
                    # Log detected signals periodically (1 in 10 updates to save space)
                    if signals and np.random.random() < 0.1:
                        collections['signals'].insert_many(signals)
                except Exception as e:
                    print(f"Error logging to MongoDB: {e}")
            
            # Package data for WebSocket
            data = {
                "freqs": freqs.tolist(),
                "amplitudes": fft_data.tolist(),
                "signals": signals,
                "violations": violations,
                "timestamp": time.time()
            }
            
            # Add waterfall data if using standard backend
            if waterfall_data is not None:
                data["waterfall"] = waterfall_data.tolist()
            
            # Send to WebSocket
            await websocket.send(json.dumps(data))
            
            # Output stats
            if violations:
                print(f"Detected {len(violations)} potential violations:")
                for v in violations[:3]:  # Show first 3 at most
                    print(f"  - {v['frequency_mhz']:.3f} MHz ({v['modulation']}, {v['confidence']:.2f})")
                if len(violations) > 3:
                    print(f"  - ...and {len(violations) - 3} more")
            
            # Limit update rate
            await asyncio.sleep(1.0 / CONFIG['visualization']['frame_rate'])
    
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    except Exception as e:
        print(f"Error in SDR stream: {e}")
    finally:
        if sdr:
            sdr.close()
            print("SDR closed")

# Fallback: Simulate SDR data with violations for testing
async def simulate_sdr_with_detection(websocket, eibi_db, classifier, collections):
    print("FALLBACK: Using simulated SDR data with signal classification")
    
    # Configure simulated SDR parameters
    sample_rate = CONFIG['sdr']['sample_rate']
    center_freq = CONFIG['sdr']['center_freq']
    
    # Define possible modulation types to simulate
    modulation_types = list(MODULATION_TYPES.keys())
    modulation_types.remove('UNKNOWN')  # Don't generate UNKNOWN
    
    try:
        sample_count = 0
        while True:
            # Create simulated time base
            sample_count += 1
            t = np.arange(0, 1024) / sample_rate
            
            # Generate base signal (noise)
            noise_level = 0.05 + 0.02 * np.sin(sample_count / 20)
            samples = np.random.normal(0, noise_level, len(t))
            
            # Add some signal components
            num_signals = np.random.randint(2, 6)  # 2-5 signals
            
            simulated_signals = []
            
            for i in range(num_signals):
                # Choose a modulation type for this signal
                modulation = np.random.choice(modulation_types)
                
                # Parameters for this signal
                center_offset = np.random.uniform(-0.8e6, 0.8e6)  # Offset from center frequency
                bandwidth = np.random.randint(10e3, 100e3) if modulation != 'CW' else np.random.randint(1e3, 5e3)
                amplitude = np.random.uniform(0.3, 1.0)
                
                # Generate simulated frequency and signal strength
                freq = center_freq + center_offset
                freq_khz = freq / 1000.0
                
                # Find if this frequency is in EIBI database
                match = None
                for entry in eibi_db:
                    if abs(entry["frequency_kHz"] - freq_khz) < CONFIG['detection']['freq_tolerance_khz']:
                        match = entry
                        break
                
                # Record the simulated signal
                signal_record = {
                    "frequency_khz": freq_khz,
                    "frequency_mhz": freq_khz / 1000,
                    "power": float(amplitude),
                    "modulation": modulation,
                    "confidence": np.random.uniform(0.7, 0.95),
                    "matched": match is not None,
                    "simulated": True
                }
                
                if match:
                    signal_record["station"] = match["station"]
                    signal_record["country"] = match["country"]
                    signal_record["eibi_mode"] = match["mode"]
                
                simulated_signals.append(signal_record)
                
                # Calculate indices for this signal in the FFT
                fft_length = 1024
                center_idx = fft_length // 2
                signal_idx = center_idx + int(center_offset / (sample_rate / fft_length))
                bandwidth_idx = int(bandwidth / (sample_rate / fft_length))
                
                # Ensure indices are within bounds
                low_idx = max(0, signal_idx - bandwidth_idx // 2)
                high_idx = min(fft_length - 1, signal_idx + bandwidth_idx // 2)
                
                # Create the signal shape based on modulation type
                if modulation == 'AM':
                    # AM: strong carrier with sidebands
                    carrier_width = bandwidth_idx // 10
                    # Carrier
                    samples = add_signal_component(samples, t, freq, amplitude, bandwidth_idx // 5)
                    # Sidebands
                    samples = add_signal_component(samples, t, freq - bandwidth // 2, amplitude * 0.3, bandwidth_idx // 2)
                    samples = add_signal_component(samples, t, freq + bandwidth // 2, amplitude * 0.3, bandwidth_idx // 2)
                
                elif modulation == 'FM':
                    # FM: wider bandwidth, more uniform
                    samples = add_signal_component(samples, t, freq, amplitude, bandwidth_idx)
                
                elif modulation == 'CW':
                    # CW: very narrow
                    samples = add_signal_component(samples, t, freq, amplitude, bandwidth_idx)
                
                elif modulation == 'SSB':
                    # SSB: one sideband only
                    if np.random.random() > 0.5:
                        # Upper sideband
                        samples = add_signal_component(samples, t, freq + bandwidth // 4, amplitude, bandwidth_idx // 2)
                    else:
                        # Lower sideband
                        samples = add_signal_component(samples, t, freq - bandwidth // 4, amplitude, bandwidth_idx // 2)
                
                else:
                    # Generic signal
                    samples = add_signal_component(samples, t, freq, amplitude, bandwidth_idx)
            
            # Compute FFT of the combined signal
            fft_data = np.fft.fftshift(np.abs(np.fft.fft(samples)))
            freqs = np.fft.fftshift(np.fft.fftfreq(len(samples), 1 / sample_rate)) + center_freq
            
            # Normalize FFT data
            fft_data = fft_data / np.max(fft_data) if np.max(fft_data) > 0 else fft_data
            
            # Separate violations (signals with no EIBI match)
            violations = [s for s in simulated_signals if not s["matched"]]
            
            # Log to MongoDB if available
            if collections:
                try:
                    if violations:
                        collections['violations'].insert_many(violations)
                    
                    # Log signals periodically
                    if simulated_signals and np.random.random() < 0.1:
                        collections['signals'].insert_many(simulated_signals)
                except Exception as e:
                    print(f"Error logging to MongoDB: {e}")
            
            # Package data for WebSocket
            data = {
                "freqs": freqs.tolist(),
                "amplitudes": fft_data.tolist(),
                "signals": simulated_signals,
                "violations": violations,
                "timestamp": time.time()
            }
            
            # Send to WebSocket
            await websocket.send(json.dumps(data))
            
            # Output stats
            signal_counts = {}
            for s in simulated_signals:
                mod = s['modulation']
                signal_counts[mod] = signal_counts.get(mod, 0) + 1
            
            mod_str = ", ".join([f"{m}:{c}" for m, c in signal_counts.items()])
            print(f"Sent simulated data: {len(simulated_signals)} signals ({mod_str}), {len(violations)} violations")
            
            # Limit update rate
            await asyncio.sleep(0.1)
    
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    except Exception as e:
        print(f"Error in simulation: {e}")

# Helper function to add signal components to simulated data
def add_signal_component(samples, t, freq, amplitude, bandwidth_idx):
    # Create signal component
    signal_freq = freq - CONFIG['sdr']['center_freq']  # Relative to center freq
    signal = amplitude * np.sin(2 * np.pi * signal_freq * t)
    
    # Add some random phase modulation for realism
    phase_mod = 0.1 * np.sin(2 * np.pi * 10 * t)
    signal *= np.cos(phase_mod)
    
    # Add to samples
    samples += signal
    return samples

# Start WebSocket Server
async def main():
    # Load EIBI database
    eibi_db = load_eibi_data()
    
    # Load or train signal classifier if available
    classifier = None
    if HAVE_CLASSIFIER:
        model_path = CONFIG['classifier']['model_path']
        if os.path.exists(model_path):
            print(f"Loading signal classifier model from {model_path}")
            classifier = SignalClassifier(model_path)
        else:
            print(f"Training new signal classifier model")
            from signal_classifier import train_new_model
            classifier = train_new_model(model_path)
    else:
        print("Using basic signal classification")
    
    # Setup MongoDB connection if available
    collections = setup_mongodb() if HAVE_MONGODB else None
    
    # Start WebSocket server
    host = CONFIG['websocket']['host']
    port = CONFIG['websocket']['port']
    
    print(f"Starting SDR WebSocket server with signal classification on {host}:{port}")
    async with websockets.serve(
        lambda ws, path: sdr_stream_with_detection(ws, path, eibi_db, classifier, collections),
        host, port
    ):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
