import asyncio
import numpy as np
import websockets
import time
import json

# WebSocket Ports
WS_PORT = 8765

async def sdr_simulator(websocket):
    print("Client connected to simulated SDR data stream")
    
    # Configure simulated SDR parameters
    sample_rate = 2.048e6  # 2.048 MHz
    center_freq = 100e6    # 100 MHz
    
    try:
        sample_count = 0
        while True:
            # Create simulated time base
            sample_count += 1
            t = np.arange(0, 1024) / sample_rate
            
            # Generate simulated signals (multiple sine waves with varying frequencies)
            base_signal = np.sin(2 * np.pi * 0.1e6 * t)  # 100 kHz base signal
            
            # Add some dynamic frequency components
            f1 = 0.2e6 + 0.05e6 * np.sin(sample_count / 50)  # Varying frequency component
            f2 = 0.5e6 + 0.1e6 * np.sin(sample_count / 30)   # Another varying frequency component
            
            # Add noise
            noise_level = 0.1 + 0.05 * np.sin(sample_count / 20)  # Varying noise level
            noise = np.random.normal(0, noise_level, len(t))
            
            # Combine signals
            samples = base_signal + 0.7 * np.sin(2 * np.pi * f1 * t) + 0.5 * np.sin(2 * np.pi * f2 * t) + noise
            
            # Compute FFT
            fft_data = np.fft.fftshift(np.abs(np.fft.fft(samples)))
            freqs = np.fft.fftshift(np.fft.fftfreq(len(samples), 1 / sample_rate))
            
            # Normalize
            fft_data = fft_data / np.max(fft_data)
            
            # Introduce some random peaks to simulate signals
            for _ in range(3):
                if np.random.random() < 0.1:  # 10% chance of a new peak
                    idx = np.random.randint(0, len(fft_data))
                    fft_data[idx-5:idx+5] += np.random.random() * 0.5
            
            # Re-normalize after adding peaks
            fft_data = fft_data / np.max(fft_data)
            
            # Package data for WebSocket
            data = {
                "freqs": freqs.tolist(), 
                "amplitudes": fft_data.tolist(), 
                "timestamp": time.time()
            }
            
            # Convert to JSON string
            json_data = json.dumps(data)
            
            # Send to WebSocket
            await websocket.send(json_data)
            
            # Log data being sent
            print(f"Sent simulated SDR data: {len(freqs)} points, max amplitude: {np.max(fft_data):.2f}")
            
            # Limit update rate
            await asyncio.sleep(0.1)
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    except Exception as e:
        print(f"Error in simulation: {e}")

# Start WebSocket Server
async def main():
    print(f"Starting simulated SDR WebSocket server on port {WS_PORT}")
    async with websockets.serve(sdr_simulator, "0.0.0.0", WS_PORT):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())