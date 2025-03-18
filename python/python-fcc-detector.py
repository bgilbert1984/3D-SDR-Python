import asyncio
import numpy as np
import websockets
import requests
import json
import time
from rtlsdr import RtlSdr

# Handle optional MongoDB import
try:
    from pymongo import MongoClient
    HAVE_MONGODB = True
except ImportError:
    HAVE_MONGODB = False
    print("MongoDB not available - violation logging will be disabled")

import os
import sys

def setup_environment():
    """Set up environment variables for reliable SDR library operation"""
    # Add library paths for SDR libraries
    lib_paths = [
        os.path.join(os.path.dirname(sys.executable), 'Lib', 'site-packages', 'rtlsdr'),
        os.path.join(os.path.dirname(sys.executable), 'Library', 'bin'),
        # Linux-specific paths
        '/usr/local/lib/python3/dist-packages/rtlsdr',
        '/usr/lib/python3/dist-packages/rtlsdr',
        '/usr/local/lib',
        '/usr/lib'
    ]
    
    for path in lib_paths:
        if os.path.exists(path) and path not in os.environ.get('PATH', '').split(os.pathsep):
            os.environ['PATH'] = path + os.pathsep + os.environ.get('PATH', '')
            print(f"Added SDR library path: {path}")

# MongoDB Connection Setup
def setup_mongodb():
    """Connect to MongoDB if available"""
    if not HAVE_MONGODB:
        return None
        
    try:
        client = MongoClient("mongodb://localhost:27017/")
        db = client["fcc_monitor"]
        violations_collection = db["violations"]
        print("Connected to MongoDB successfully")
        return violations_collection
    except Exception as e:
        print(f"MongoDB connection error: {e}")
        print("Continuing without violation logging...")
        return None

# Load EIBI Database
def load_eibi_data():
    print("Loading EIBI database...")
    try:
        eibi_url = "https://www.eibispace.de/dx/freq-a.txt"  # EIBI frequency list URL
        response = requests.get(eibi_url, timeout=10)
        
        if response.status_code != 200:
            print(f"Failed to retrieve EIBI data: HTTP {response.status_code}")
            return []
        
        eibi_data = []
        for line in response.text.splitlines():
            # EIBI format: freq(kHz);ITU;station;country;etc...
            parts = line.split(";")
            if len(parts) >= 5 and parts[0].strip().isdigit():
                eibi_data.append({
                    "frequency_kHz": float(parts[0]),
                    "itu_code": parts[1],
                    "station": parts[2],
                    "country": parts[3],
                    "mode": parts[4]
                })
        
        print(f"Loaded {len(eibi_data)} entries from EIBI database")
        return eibi_data
    except Exception as e:
        print(f"Error loading EIBI database: {e}")
        return []

# SDR Configuration
def setup_sdr():
    try:
        # Set up environment before initializing SDR
        setup_environment()
        
        sdr = RtlSdr()
        sdr.sample_rate = 2.048e6  # 2.048 MHz
        sdr.center_freq = 100e6    # 100 MHz (FM broadcast band)
        sdr.gain = 20              # Adjust gain for better signal
        print(f"SDR initialized at {sdr.center_freq/1e6:.3f} MHz")
        return sdr
    except Exception as e:
        print(f"Error initializing SDR: {e}")
        return None

# Detect violations by comparing with EIBI database
def detect_violations(freqs, fft_data, eibi_db, threshold=0.3):
    violations = []
    
    # Convert Hz to kHz for comparison with EIBI database
    freqs_khz = freqs / 1000.0
    
    # Find peaks in the FFT data (potential signals)
    peak_indices = []
    for i in range(1, len(fft_data) - 1):
        if fft_data[i] > threshold and fft_data[i] > fft_data[i-1] and fft_data[i] > fft_data[i+1]:
            peak_indices.append(i)
    
    for idx in peak_indices:
        freq_khz = freqs_khz[idx]
        power = fft_data[idx]
        
        # Look for a match in EIBI database (with some tolerance)
        tolerance_khz = 5  # 5 kHz tolerance
        match = None
        
        for entry in eibi_db:
            if abs(entry["frequency_kHz"] - freq_khz) < tolerance_khz:
                match = entry
                break
        
        # If no match found and signal is strong, consider it a potential violation
        if not match and power > threshold:
            violations.append({
                "frequency_khz": freq_khz,
                "frequency_mhz": freq_khz / 1000.0,
                "power": float(power),
                "timestamp": time.time()
            })
    
    return violations

# WebSocket handler for SDR streaming with violation detection
async def sdr_stream_with_detection(websocket, path, eibi_db, violations_collection):
    print("Client connected to SDR data stream with violation detection")
    
    sdr = setup_sdr()
    if not sdr:
        # Fallback to simulation mode if SDR is not available
        await simulate_sdr_with_detection(websocket, eibi_db, violations_collection)
        return
    
    try:
        while True:
            # Read samples from SDR
            samples = sdr.read_samples(256 * 1024)
            
            # Compute FFT
            fft_data = np.fft.fftshift(np.abs(np.fft.fft(samples)))
            freqs = np.fft.fftshift(np.fft.fftfreq(len(samples), 1 / sdr.sample_rate)) + sdr.center_freq
            
            # Normalize FFT data
            fft_data = fft_data / np.max(fft_data) if np.max(fft_data) > 0 else fft_data
            
            # Detect violations
            violations = detect_violations(freqs, fft_data, eibi_db)
            
            # Log violations to MongoDB if available
            if violations_collection and violations:
                try:
                    violations_collection.insert_many(violations)
                    print(f"Logged {len(violations)} violations to MongoDB")
                except Exception as e:
                    print(f"Error logging to MongoDB: {e}")
            
            # Package data for WebSocket
            data = {
                "freqs": freqs.tolist(),
                "amplitudes": fft_data.tolist(),
                "violations": violations,
                "timestamp": time.time()
            }
            
            # Send to WebSocket
            await websocket.send(json.dumps(data))
            
            # Output stats
            if violations:
                print(f"Detected {len(violations)} potential FCC violations")
            
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

# Fallback: Simulate SDR data with violations for testing
async def simulate_sdr_with_detection(websocket, eibi_db, violations_collection):
    print("FALLBACK: Using simulated SDR data with violation detection")
    
    # Configure simulated SDR parameters
    sample_rate = 2.048e6  # 2.048 MHz
    center_freq = 100e6    # 100 MHz
    
    try:
        sample_count = 0
        while True:
            # Create simulated time base
            sample_count += 1
            t = np.arange(0, 1024) / sample_rate
            
            # Generate simulated signals
            base_signal = np.sin(2 * np.pi * 0.1e6 * t)
            
            # Add some dynamic frequency components
            f1 = 0.2e6 + 0.05e6 * np.sin(sample_count / 50)
            f2 = 0.5e6 + 0.1e6 * np.sin(sample_count / 30)
            
            # Add noise
            noise_level = 0.1 + 0.05 * np.sin(sample_count / 20)
            noise = np.random.normal(0, noise_level, len(t))
            
            # Combine signals
            samples = base_signal + 0.7 * np.sin(2 * np.pi * f1 * t) + 0.5 * np.sin(2 * np.pi * f2 * t) + noise
            
            # Compute FFT
            fft_data = np.fft.fftshift(np.abs(np.fft.fft(samples)))
            freqs = np.fft.fftshift(np.fft.fftfreq(len(samples), 1 / sample_rate)) + center_freq
            
            # Normalize
            fft_data = fft_data / np.max(fft_data)
            
            # Introduce some random peaks to simulate signals
            for _ in range(3):
                if np.random.random() < 0.1:  # 10% chance of a new peak
                    idx = np.random.randint(0, len(fft_data))
                    fft_data[idx-5:idx+5] += np.random.random() * 0.5
            
            # Re-normalize after adding peaks
            fft_data = fft_data / np.max(fft_data)
            
            # Add simulated violations randomly
            simulated_violations = []
            if np.random.random() < 0.3:  # 30% chance of a violation
                violation_idx = np.random.randint(0, len(fft_data))
                violation_freq = freqs[violation_idx] / 1000.0  # Convert to kHz
                
                # Make sure this frequency is not in EIBI database (truly a violation)
                is_violation = True
                for entry in eibi_db:
                    if abs(entry["frequency_kHz"] - violation_freq) < 5:
                        is_violation = False
                        break
                
                if is_violation:
                    simulated_violations.append({
                        "frequency_khz": violation_freq,
                        "frequency_mhz": violation_freq / 1000.0,
                        "power": float(fft_data[violation_idx]),
                        "timestamp": time.time(),
                        "simulated": True
                    })
                    
                    # Increase the signal strength at violation point for visibility
                    fft_data[violation_idx-3:violation_idx+4] *= 1.5
            
            # Log simulated violations to MongoDB if available
            if violations_collection and simulated_violations:
                try:
                    violations_collection.insert_many(simulated_violations)
                except Exception as e:
                    print(f"Error logging to MongoDB: {e}")
            
            # Package data for WebSocket
            data = {
                "freqs": freqs.tolist(),
                "amplitudes": fft_data.tolist(),
                "violations": simulated_violations,
                "timestamp": time.time()
            }
            
            # Convert to JSON string
            json_data = json.dumps(data)
            
            # Send to WebSocket
            await websocket.send(json_data)
            
            # Log data being sent with violation information
            if simulated_violations:
                print(f"Sent simulated SDR data with {len(simulated_violations)} violations")
            else:
                print(f"Sent simulated SDR data: {len(freqs)} points, no violations")
            
            # Limit update rate
            await asyncio.sleep(0.1)
    
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    except Exception as e:
        print(f"Error in simulation: {e}")

# Start WebSocket Server
async def main():
    WS_PORT = 8765
    
    # Load EIBI database
    eibi_db = load_eibi_data()
    
    # Setup MongoDB connection
    violations_collection = setup_mongodb()
    
    print(f"Starting SDR WebSocket server with violation detection on port {WS_PORT}")
    async with websockets.serve(
        lambda ws, path: sdr_stream_with_detection(ws, path, eibi_db, violations_collection),
        "0.0.0.0", 
        WS_PORT
    ):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())
