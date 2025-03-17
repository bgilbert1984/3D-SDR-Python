import asyncio
import numpy as np
import websockets
import requests
import json
import time
import os
import sys
from rtlsdr import RtlSdr
from pymongo import MongoClient
from signal_classifier import SignalClassifier, MODULATION_TYPES
from sdr_geolocation import SDRGeolocation, SDRReceiver, SignalMeasurement, GeoSimulator

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
        'port': 8765
    },
    'eibi': {
        'url': 'https://www.eibispace.de/dx/freq-a.txt',
        'refresh_hours': 24  # Refresh EIBI database every 24 hours
    },
    'mongodb': {
        'uri': 'mongodb://localhost:27017/',
        'db_name': 'fcc_monitor',
        'violations_collection': 'violations',
        'signals_collection': 'signals',
        'locations_collection': 'locations'
    },
    'detection': {
        'signal_threshold': 0.3,  # Minimum amplitude to consider as a signal
        'freq_tolerance_khz': 5,  # Frequency matching tolerance in kHz
        'window_size': 20,        # Window size for signal analysis
        'min_confidence': 0.6     # Minimum classifier confidence to accept
    },
    'classifier': {
        'model_path': 'signal_classifier_model.pkl'
    },
    'geolocation': {
        'receivers_file': 'receivers.json',  # File to save/load receiver configurations
        'default_receivers': [
            # Default receivers if no file exists (example locations)
            {
                'id': 'main',
                'latitude': 37.7749,
                'longitude': -122.4194,
                'altitude': 0.0,
                'active': True
            },
            {
                'id': 'remote1',
                'latitude': 37.8044,
                'longitude': -122.2712,
                'altitude': 0.0,
                'active': True
            },
            {
                'id': 'remote2',
                'latitude': 37.5630,
                'longitude': -122.3255,
                'altitude': 0.0,
                'active': True
            },
            {
                'id': 'remote3',
                'latitude': 37.8716,
                'longitude': -122.2727,
                'altitude': 0.0,
                'active': True
            }
        ],
        'simulation': {
            'enabled': True,      # Enable simulation mode for testing
            'transmitters': [
                # Simulated transmitters (only used in simulation mode)
                {
                    'id': 'tx1',
                    'latitude': 37.7952,
                    'longitude': -122.3994,
                    'altitude': 0.0,
                    'frequency': 98.5e6,
                    'power': 0.9,
                    'modulation': 'FM',
                    'authorized': True
                },
                {
                    'id': 'tx2',
                    'latitude': 37.7430,
                    'longitude': -122.4330,
                    'altitude': 0.0,
                    'frequency': 104.3e6,
                    'power': 0.7,
                    'modulation': 'FM',
                    'authorized': False  # Unauthorized transmitter
                }
            ]
        }
    }
}

# MongoDB Connection Setup
def setup_mongodb():
    try:
        client = MongoClient(CONFIG['mongodb']['uri'])
        db = client[CONFIG['mongodb']['db_name']]
        violations_collection = db[CONFIG['mongodb']['violations_collection']]
        signals_collection = db[CONFIG['mongodb']['signals_collection']]
        locations_collection = db[CONFIG['mongodb']['locations_collection']]
        
        print("Connected to MongoDB successfully")
        return {
            'violations': violations_collection,
            'signals': signals_collection,
            'locations': locations_collection
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

# Load or initialize geolocation engine
def setup_geolocation():
    receivers_file = CONFIG['geolocation']['receivers_file']
    
    geo = SDRGeolocation()
    
    # Try to load existing receivers configuration
    if os.path.exists(receivers_file):
        try:
            with open(receivers_file, 'r') as f:
                geo_data = json.load(f)
                geo = SDRGeolocation.from_dict(geo_data)
                print(f"Loaded {len(geo.receivers)} receivers from {receivers_file}")
        except Exception as e:
            print(f"Error loading receivers configuration: {e}")
    
    # If no receivers loaded, use defaults
    if not geo.receivers:
        print("Using default receivers configuration")
        for receiver_data in CONFIG['geolocation']['default_receivers']:
            receiver = SDRReceiver(
                id=receiver_data['id'],
                latitude=receiver_data['latitude'],
                longitude=receiver_data['longitude'],
                altitude=receiver_data.get('altitude', 0.0),
                timestamp=time.time(),
                active=receiver_data.get('active', True)
            )
            geo.add_receiver(receiver)
        
        # Save default configuration
        try:
            with open(receivers_file, 'w') as f:
                json.dump(geo.to_dict(), f, indent=2)
            print(f"Saved default receivers configuration to {receivers_file}")
        except Exception as e:
            print(f"Error saving receivers configuration: {e}")
    
    # Print current receivers
    print("\nActive receivers:")
    for receiver in geo.get_active_receivers():
        print(f"  {receiver.id}: ({receiver.latitude}, {receiver.longitude})")
    
    return geo

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

# Process signals and detect violations
def analyze_signals(freqs, fft_data, eibi_db, classifier, geo_engine, receiver_id):
    threshold = CONFIG['detection']['signal_threshold']
    tolerance_khz = CONFIG['detection']['freq_tolerance_khz']
    signals = []
    violations = []
    geo_measurements = []
    
    # Current timestamp
    current_time = time.time()
    
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
        
        # Classify the signal
        classification = classifier.predict(peak_freqs, peak_amplitudes, threshold=threshold)
        modulation = classification['modulation']
        confidence = classification['confidence']
        
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
            "timestamp": current_time,
            "matched": match is not None,
            "receiver_id": receiver_id
        }
        
        # If match found, add station information
        if match:
            signal_record["station"] = match["station"]
            signal_record["country"] = match["country"]
            signal_record["eibi_mode"] = match["mode"]
        
        # Add to signals list
        signals.append(signal_record)
        
        # Create geolocation measurement
        geo_measurement = SignalMeasurement(
            receiver_id=receiver_id,
            frequency=freqs[idx],
            power=power,
            timestamp=current_time,
            snr=10.0 * np.log10(power / 0.01) if power > 0.01 else 0,  # Simplified SNR estimation
            modulation=modulation
        )
        
        # Add to geolocation measurements
        geo_measurements.append(geo_measurement)
        
        # If no match found and signal is strong, consider it a potential violation
        if not match and power > threshold:
            violations.append(signal_record)
    
    return signals, violations, geo_measurements

# Geolocate signals
def geolocate_signals(geo_engine, measurements_by_frequency, collections=None):
    """
    Attempt to geolocate signals based on measurements from multiple receivers
    
    Args:
        geo_engine: SDRGeolocation engine
        measurements_by_frequency: Dictionary mapping frequencies to lists of measurements
        collections: MongoDB collections for logging
        
    Returns:
        Dictionary of geolocation results by frequency
    """
    geolocation_results = {}
    
    for freq, measurements in measurements_by_frequency.items():
        # Need measurements from at least 3 receivers for accurate geolocation
        if len(measurements) < 3:
            # For single receiver, estimate possible locations as a circle
            if len(measurements) == 1:
                single_measurement = measurements[0]
                possible_locations = geo_engine.estimate_single_receiver(single_measurement)
                
                geolocation_results[freq] = {
                    "frequency": freq,
                    "frequency_mhz": freq / 1e6,
                    "timestamp": time.time(),
                    "single_receiver_id": single_measurement.receiver_id,
                    "method": "single_receiver",
                    "possible_locations": possible_locations,
                    "modulation": single_measurement.modulation
                }
            continue
        
        # Calculate TDoA for these measurements
        measurements_with_tdoa = geo_engine.calculate_tdoa(measurements)
        
        # Try TDoA geolocation first
        tdoa_result = geo_engine.geolocate_tdoa(measurements_with_tdoa)
        
        if tdoa_result:
            lat, lon, alt = tdoa_result
            result = {
                "frequency": freq,
                "frequency_mhz": freq / 1e6,
                "latitude": lat,
                "longitude": lon,
                "altitude": alt,
                "timestamp": time.time(),
                "method": "tdoa",
                "receiver_count": len(measurements),
                "modulation": measurements[0].modulation if measurements else "UNKNOWN"
            }
            geolocation_results[freq] = result
            
            # Log to database if available
            if collections and collections.get('locations'):
                try:
                    collections['locations'].insert_one(result)
                except Exception as e:
                    print(f"Error logging geolocation to MongoDB: {e}")
        else:
            # Fall back to RSSI-based geolocation
            rssi_result = geo_engine.geolocate_rssi(measurements)
            
            if rssi_result:
                lat, lon, alt = rssi_result
                result = {
                    "frequency": freq,
                    "frequency_mhz": freq / 1e6,
                    "latitude": lat,
                    "longitude": lon,
                    "altitude": alt,
                    "timestamp": time.time(),
                    "method": "rssi",
                    "receiver_count": len(measurements),
                    "modulation": measurements[0].modulation if measurements else "UNKNOWN"
                }
                geolocation_results[freq] = result
                
                # Log to database if available
                if collections and collections.get('locations'):
                    try:
                        collections['locations'].insert_one(result)
                    except Exception as e:
                        print(f"Error logging geolocation to MongoDB: {e}")
    
    return geolocation_results

# WebSocket handler for SDR streaming with violation detection and geolocation
async def sdr_stream_with_detection(websocket, path, eibi_db, classifier, geo_engine, collections):
    print("Client connected to SDR data stream with violation detection and geolocation")
    
    # Get the receiver ID for this SDR (using the first active receiver by default)
    active_receivers = geo_engine.get_active_receivers()
    if not active_receivers:
        print("No active receivers configured. Please add at least one receiver.")
        return
    
    # Use the first active receiver for this SDR
    receiver_id = active_receivers[0].id
    print(f"Using receiver ID: {receiver_id}")
    
    # Dictionary to store measurements by frequency for geolocation
    measurements_by_frequency = {}
    
    # Initialize RTL-SDR
    sdr = setup_sdr()
    if not sdr:
        # Fallback to simulation mode if SDR is not available
        await simulate_sdr_with_detection(websocket, eibi_db, classifier, geo_engine, collections)
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
            
            # Analyze signals and detect violations
            signals, violations, geo_measurements = analyze_signals(
                freqs, fft_data, eibi_db, classifier, geo_engine, receiver_id
            )
            
            # Group geolocation measurements by frequency
            for measurement in geo_measurements:
                freq = measurement.frequency
                if freq not in measurements_by_frequency:
                    measurements_by_frequency[freq] = []
                
                # Add or update measurement for this frequency
                measurements_by_frequency[freq] = [m for m in measurements_by_frequency[freq] 
                                              if m.receiver_id != measurement.receiver_id]
                measurements_by_frequency[freq].append(measurement)
            
            # Clean up old measurements (older than 10 seconds)
            current_time = time.time()
            for freq in list(measurements_by_frequency.keys()):
                measurements_by_frequency[freq] = [m for m in measurements_by_frequency[freq] 
                                              if current_time - m.timestamp < 10.0]
                
                # Remove frequencies with no measurements
                if not measurements_by_frequency[freq]:
                    del measurements_by_frequency[freq]
            
            # Attempt geolocation for signals with measurements from multiple receivers
            geolocation_results = geolocate_signals(
                geo_engine, measurements_by_frequency, collections
            )
            
            # Log to MongoDB if available
            if collections:
                try:
                    if violations:
                        violations_with_location = violations.copy()
                        
                        # Add geolocation data to violations if available
                        for violation in violations_with_location:
                            freq = violation.get("frequency_khz") * 1000  # Convert to Hz
                            if freq in geolocation_results:
                                violation["geolocation"] = geolocation_results[freq]
                        
                        collections['violations'].insert_many(violations_with_location)
                    
                    # Log detected signals periodically (1 in 10 updates to save space)
                    if signals and np.random.random() < 0.1:
                        signals_with_location = signals.copy()
                        
                        # Add geolocation data to signals if available
                        for signal in signals_with_location:
                            freq = signal.get("frequency_khz") * 1000  # Convert to Hz
                            if freq in geolocation_results:
                                signal["geolocation"] = geolocation_results[freq]
                        
                        collections['signals'].insert_many(signals_with_location)
                except Exception as e:
                    print(f"Error logging to MongoDB: {e}")
            
            # Package data for WebSocket
            data = {
                "freqs": freqs.tolist(),
                "amplitudes": fft_data.tolist(),
                "signals": signals,
                "violations": violations,
                "geolocation_results": list(geolocation_results.values()),
                "timestamp": time.time(),
                "receiver_id": receiver_id
            }
            
            # Send to WebSocket
            await websocket.send(json.dumps(data))
            
            # Output stats
            if violations:
                print(f"Detected {len(violations)} potential violations")
            
            if geolocation_results:
                print(f"Geolocated {len(geolocation_results)} signals")
                for freq, result in geolocation_results.items():
                    if "latitude" in result:
                        print(f"  {result['frequency_mhz']:.3f} MHz: ({result['latitude']:.6f}, {result['longitude']:.6f}) [method: {result['method']}]")
            
            # Limit update rate
            await asyncio.sleep(0.1)
    
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    except Exception as e:
        print(f"Error in SDR stream: {e}")
    finally:
        if sdr:
            sdr.close()
            print("SDR closed")

# Fallback: Simulate SDR data with violations and geolocation for testing
async def simulate_sdr_with_detection(websocket, eibi_db, classifier, geo_engine, collections):
    print("FALLBACK: Using simulated SDR data with geolocation")
    
    # Create simulator
    simulator = GeoSimulator()
    
    # Get active receivers
    receivers = geo_engine.get_active_receivers()
    if not receivers:
        print("No active receivers configured. Please add at least one receiver.")
        return
    
    # This SDR is the first active receiver
    receiver_id = receivers[0].id
    
    # Configure simulated SDR parameters
    sample_rate = CONFIG['sdr']['sample_rate']
    center_freq = CONFIG['sdr']['center_freq']
    
    # Dictionary to store measurements by frequency for geolocation
    measurements_by_frequency = {}
    
    # Simulated transmitters
    transmitters = CONFIG['geolocation']['simulation']['transmitters']
    print(f"Simulating {len(transmitters)} transmitters")
    for tx in transmitters:
        print(f"  {tx['id']}: ({tx['latitude']}, {tx['longitude']}) at {tx['frequency']/1e6:.2f} MHz")
    
    try:
        while True:
            # Generate base signal (noise)
            t = np.arange(0, 1024) / sample_rate
            samples = np.random.normal(0, 0.05, len(t))
            
            # Generate simulated measurements from each transmitter
            all_geo_measurements = []
            for transmitter in transmitters:
                # Simulate signal measurements for this transmitter
                geo_measurements = simulator.simulate_signal(
                    transmitter_lat=transmitter['latitude'],
                    transmitter_lon=transmitter['longitude'],
                    transmitter_alt=transmitter.get('altitude', 0.0),
                    frequency=transmitter['frequency'],
                    power=transmitter['power'],
                    receivers=receivers,
                    noise_level=0.02,
                    time_error=1e-8
                )
                
                # Add simulated modulation type
                for measurement in geo_measurements:
                    measurement.modulation = transmitter.get('modulation', 'FM')
                
                all_geo_measurements.extend(geo_measurements)
                
                # Add the signal to our simulated samples
                # Calculate signal offset from center frequency
                signal_offset = transmitter['frequency'] - center_freq
                
                # Generate a simplified signal for this transmitter
                tx_signal = transmitter['power'] * np.sin(2 * np.pi * signal_offset * t)
                
                # Add to samples
                samples += tx_signal
            
            # Compute FFT of the combined signal
            fft_data = np.fft.fftshift(np.abs(np.fft.fft(samples)))
            freqs = np.fft.fftshift(np.fft.fftfreq(len(samples), 1 / sample_rate)) + center_freq
            
            # Normalize FFT data
            fft_data = fft_data / np.max(fft_data) if np.max(fft_data) > 0 else fft_data
            
            # Analyze signals and detect violations
            signals, violations, _ = analyze_signals(
                freqs, fft_data, eibi_db, classifier, geo_engine, receiver_id
            )
            
            # Group geolocation measurements by frequency and update our collection
            for measurement in all_geo_measurements:
                freq = measurement.frequency
                if freq not in measurements_by_frequency:
                    measurements_by_frequency[freq] = []
                
                # Add or update measurement for this frequency
                measurements_by_frequency[freq] = [m for m in measurements_by_frequency[freq] 
                                              if m.receiver_id != measurement.receiver_id]
                measurements_by_frequency[freq].append(measurement)
            
            # Clean up old measurements (older than 10 seconds)
            current_time = time.time()
            for freq in list(measurements_by_frequency.keys()):
                measurements_by_frequency[freq] = [m for m in measurements_by_frequency[freq] 
                                              if current_time - m.timestamp < 10.0]
                
                # Remove frequencies with no measurements
                if not measurements_by_frequency[freq]:
                    del measurements_by_frequency[freq]
            
            # Attempt geolocation for signals with measurements from multiple receivers
            geolocation_results = geolocate_signals(
                geo_engine, measurements_by_frequency, collections
            )
            
            # Add unauthorized flag to violations based on simulated transmitters
            for violation in violations:
                freq_mhz = violation.get("frequency_mhz")
                for tx in transmitters:
                    tx_freq_mhz = tx['frequency'] / 1e6
                    if abs(freq_mhz - tx_freq_mhz) < 0.1:  # Within 100 kHz
                        violation["simulated"] = True
                        violation["transmitter_id"] = tx['id']
                        violation["authorized"] = tx.get('authorized', True)
            
            # Log to MongoDB if available
            if collections:
                try:
                    if violations:
                        violations_with_location = violations.copy()
                        
                        # Add geolocation data to violations if available
                        for violation in violations_with_location:
                            freq = violation.get("frequency_khz") * 1000  # Convert to Hz
                            if freq in geolocation_results:
                                violation["geolocation"] = geolocation_results[freq]
                        
                        collections['violations'].insert_many(violations_with_location)
                    
                    # Log geolocation results directly
                    if geolocation_results and collections.get('locations'):
                        collections['locations'].insert_many(list(geolocation_results.values()))
                except Exception as e:
                    print(f"Error logging to MongoDB: {e}")
            
            # Package data for WebSocket
            data = {
                "freqs": freqs.tolist(),
                "amplitudes": fft_data.tolist(),
                "signals": signals,
                "violations": violations,
                "geolocation_results": list(geolocation_results.values()),
                "timestamp": time.time(),
                "receiver_id": receiver_id,
                "simulated": True
            }
            
            # Send to WebSocket
            await websocket.send(json.dumps(data))
            
            # Output stats
            geolocation_count = len(geolocation_results)
            if geolocation_count > 0:
                print(f"Simulated data: {len(signals)} signals, {len(violations)} violations, {geolocation_count} geolocated")
                for freq, result in geolocation_results.items():
                    if "latitude" in result:
                        # Find the original transmitter for comparison
                        for tx in transmitters:
                            if abs(freq - tx['frequency']) < 1000:  # Within 1 kHz
                                tx_lat = tx['latitude']
                                tx_lon = tx['longitude']
                                result_lat = result['latitude']
                                result_lon = result['longitude']
                                error_km = haversine((tx_lat, tx_lon), (result_lat, result_lon), unit='km')
                                print(f"  {result['frequency_mhz']:.3f} MHz: Predicted ({result_lat:.6f}, {result_lon:.6f}), "
                                     f"Actual ({tx_lat:.6f}, {tx_lon:.6f}), Error: {error_km:.2f} km")
            
            # Limit update rate
            await asyncio.sleep(0.5)
    
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    except Exception as e:
        print(f"Error in simulation: {e}")

# Start WebSocket Server
async def main():
    # Load EIBI database
    eibi_db = load_eibi_data()
    
    # Load or train signal classifier
    model_path = CONFIG['classifier']['model_path']
    if os.path.exists(model_path):
        print(f"Loading signal classifier model from {model_path}")
        classifier = SignalClassifier(model_path)
    else:
        print(f"Training new signal classifier model")
        from signal_classifier import train_new_model
        classifier = train_new_model(model_path)
    
    # Setup geolocation engine
    geo_engine = setup_geolocation()
    
    # Setup MongoDB connection
    collections = setup_mongodb()
    
    # Start WebSocket server
    host = CONFIG['websocket']['host']
    port = CONFIG['websocket']['port']
    
    print(f"Starting SDR WebSocket server with geolocation on {host}:{port}")
    async with websockets.serve(
        lambda ws, path: sdr_stream_with_detection(ws, path, eibi_db, classifier, geo_engine, collections),
        host, port
    ):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    # Make sure haversine is installed
    try:
        import haversine
    except ImportError:
        print("Haversine package not found. Installing...")
        import subprocess
        subprocess.check_call([sys.executable, "-m", "pip", "install", "haversine"])
        import haversine
    
    asyncio.run(main())
