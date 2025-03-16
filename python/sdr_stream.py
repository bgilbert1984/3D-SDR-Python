import asyncio
import numpy as np
import websockets
from rtlsdr import RtlSdr

# WebSocket Port
WS_PORT = 8765

async def sdr_stream(websocket, path):
    sdr = RtlSdr()

    # Configure SDR parameters
    sdr.sample_rate = 2.048e6  # 2.048 MHz
    sdr.center_freq = 100e6  # 100 MHz (Adjust as needed)
    sdr.gain = 10  # Set gain (adjust for better signal)

    try:
        while True:
            # Read samples
            samples = sdr.read_samples(256 * 1024)

            # Compute FFT
            fft_data = np.fft.fftshift(np.abs(np.fft.fft(samples)))
            freqs = np.fft.fftshift(np.fft.fftfreq(len(samples), 1 / sdr.sample_rate))

            # Normalize
            fft_data = fft_data / np.max(fft_data)

            # Package data for WebSocket
            data = {"freqs": freqs.tolist(), "amplitudes": fft_data.tolist(), "timestamp": asyncio.get_event_loop().time()}
            
            # Send to WebSocket
            await websocket.send(str(data))

            # Limit update rate
            await asyncio.sleep(0.1)
    except Exception as e:
        print("Error:", e)
    finally:
        sdr.close()

# Start WebSocket Server
start_server = websockets.serve(sdr_stream, "0.0.0.0", WS_PORT)
asyncio.get_event_loop().run_until_complete(start_server)
asyncio.get_event_loop().run_forever()