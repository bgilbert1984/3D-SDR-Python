import asyncio
import numpy as np
import websockets
import time
import json
from dataclasses import dataclass
from typing import List, Optional

# WebSocket Ports
WS_PORT = 8765

@dataclass
class SimulatedSignal:
    frequency: float
    amplitude: float
    modulation: str
    bandwidth: float
    phase: float = 0.0
    message: Optional[str] = None

class SDRSimReceiver:
    def __init__(self, sample_rate=2.048e6, center_freq=100e6, gain=20):
        self.sample_rate = sample_rate
        self.center_freq = center_freq
        self.gain = gain
        self.noise_floor = -90  # dBm
        self.signals: List[SimulatedSignal] = []
        
    def add_signal(self, signal: SimulatedSignal):
        """Add a signal to be received"""
        self.signals.append(signal)
        
    def remove_signal(self, frequency: float):
        """Remove a signal by frequency"""
        self.signals = [s for s in self.signals if s.frequency != frequency]
    
    def generate_samples(self, num_samples: int) -> np.ndarray:
        """Generate complex samples for all current signals"""
        t = np.arange(num_samples) / self.sample_rate
        samples = np.zeros(num_samples, dtype=np.complex128)
        
        # Add each signal
        for signal in self.signals:
            # Calculate frequency relative to center frequency
            relative_freq = signal.frequency - self.center_freq
            
            # Generate base signal
            if signal.modulation == "AM":
                # AM modulation
                message = np.sin(2 * np.pi * 1000 * t)  # 1kHz message
                carrier = np.exp(2j * np.pi * relative_freq * t + signal.phase)
                samples += signal.amplitude * (1 + 0.5 * message) * carrier
                
            elif signal.modulation == "FM":
                # FM modulation
                message = np.sin(2 * np.pi * 1000 * t)  # 1kHz message
                phase = 2 * np.pi * relative_freq * t + 0.5 * np.cumsum(message) / self.sample_rate
                samples += signal.amplitude * np.exp(2j * phase + signal.phase)
                
            elif signal.modulation == "SSB":
                # Single sideband
                message = np.sin(2 * np.pi * 1000 * t)
                hilbert = np.imag(signal.amplitude * np.exp(2j * np.pi * relative_freq * t + signal.phase))
                samples += message * hilbert
                
            else:  # CW or default
                # Simple carrier
                samples += signal.amplitude * np.exp(2j * np.pi * relative_freq * t + signal.phase)
        
        # Add noise
        noise_power = 10 ** (self.noise_floor/10)
        noise = np.random.normal(0, np.sqrt(noise_power/2), num_samples) + \
                1j * np.random.normal(0, np.sqrt(noise_power/2), num_samples)
        samples += noise
        
        return samples

async def sdr_simulator(websocket):
    print("Client connected to simulated SDR data stream")
    
    # Create SDR receiver instance
    sdr = SDRSimReceiver()
    
    # Add some test signals
    sdr.add_signal(SimulatedSignal(
        frequency=100.1e6,  # 100.1 MHz
        amplitude=0.5,
        modulation="AM",
        bandwidth=10e3
    ))
    
    sdr.add_signal(SimulatedSignal(
        frequency=100.3e6,  # 100.3 MHz
        amplitude=0.3,
        modulation="FM",
        bandwidth=200e3
    ))
    
    try:
        while True:
            # Generate complex samples
            samples = sdr.generate_samples(1024)
            
            # Compute FFT for visualization
            fft_data = np.fft.fftshift(np.abs(np.fft.fft(samples)))
            freqs = np.fft.fftshift(np.fft.fftfreq(len(samples), 1/sdr.sample_rate)) + sdr.center_freq
            
            # Normalize FFT data for visualization
            fft_data = fft_data / np.max(fft_data) if np.max(fft_data) > 0 else fft_data
            
            # Package data for WebSocket
            data = {
                "freqs": freqs.tolist(),
                "amplitudes": fft_data.tolist(),
                "timestamp": time.time(),
                "signals": [
                    {
                        "frequency": s.frequency,
                        "amplitude": s.amplitude,
                        "modulation": s.modulation,
                        "bandwidth": s.bandwidth
                    } for s in sdr.signals
                ]
            }
            
            # Send to WebSocket
            await websocket.send(json.dumps(data))
            
            # Log data being sent
            print(f"Sent simulated SDR data: {len(sdr.signals)} active signals")
            
            # Limit update rate
            await asyncio.sleep(0.1)
            
    except websockets.exceptions.ConnectionClosed:
        print("Client disconnected")
    except Exception as e:
        print(f"Error in simulation: {e}")

async def main():
    print(f"Starting simulated SDR WebSocket server on port {WS_PORT}")
    async with websockets.serve(sdr_simulator, "0.0.0.0", WS_PORT):
        await asyncio.Future()  # Run forever

if __name__ == "__main__":
    asyncio.run(main())