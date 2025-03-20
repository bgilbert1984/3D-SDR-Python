#!/usr/bin/env python3
"""
SDR IQ Data Capture Example

This script demonstrates how to use the sdr_geolocation_lib to capture IQ data
from KiwiSDR stations for signal processing and ML model training.
"""

import os
import asyncio
import logging
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime

# Import from our modular library
from sdr_geolocation_lib.remote import RemoteSDRHandler
from sdr_geolocation_lib.models import SignalMeasurement, SDRReceiver

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('iq_capture_example')


async def capture_single_station(frequency_mhz, duration_sec):
    """Example of capturing IQ data from a single KiwiSDR station"""
    
    logger.info(f"Capturing {duration_sec}s of IQ data at {frequency_mhz} MHz from a single station")
    
    # Create timestamp for this capture session
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_dir = os.path.join("dataset", timestamp)
    os.makedirs(output_dir, exist_ok=True)
    
    # Convert MHz to Hz
    frequency_hz = frequency_mhz * 1e6
    
    async with RemoteSDRHandler() as handler:
        # Get the KiwiSDR client
        kiwi_client = handler.providers["kiwisdr"]["client"]
        
        # Update the station list
        async with kiwi_client:
            await kiwi_client.update_station_list()
            
            # Find a suitable station
            suitable_stations = [
                station for station in kiwi_client.stations.values()
                if kiwi_client._frequency_in_range(station, frequency_hz)
            ]
            
            if not suitable_stations:
                logger.error(f"No KiwiSDR stations found that cover {frequency_mhz} MHz")
                return
            
            # Use the first suitable station
            station = suitable_stations[0]
            logger.info(f"Selected station: {station.name} at ({station.latitude}, {station.longitude})")
            
            # Capture data
            capture_dir = await kiwi_client.capture_and_save_data(
                station=station,
                frequency=frequency_hz,
                sample_rate=12000,  # 12 kHz, standard for KiwiSDR
                duration=duration_sec,
                output_dir=output_dir
            )
            
            if capture_dir:
                logger.info(f"Successfully captured data to {capture_dir}")
                return capture_dir
            else:
                logger.error("Failed to capture data")
                return None


async def capture_multiple_stations(frequency_mhz, duration_sec, max_stations=3):
    """Example of capturing IQ data from multiple KiwiSDR stations simultaneously"""
    
    logger.info(f"Capturing {duration_sec}s of IQ data at {frequency_mhz} MHz from up to {max_stations} stations")
    
    # Convert MHz to Hz
    frequency_hz = frequency_mhz * 1e6
    
    # Use the RemoteSDRHandler to capture from multiple stations
    async with RemoteSDRHandler() as handler:
        saved_dirs = await handler.capture_iq_data(
            frequency=frequency_hz,
            sample_rate=12000,  # 12 kHz, standard for KiwiSDR
            duration=duration_sec,
            max_stations=max_stations
        )
        
        if saved_dirs:
            logger.info(f"Successfully captured data to {len(saved_dirs)} directories")
            return saved_dirs
        else:
            logger.error("Failed to capture any data")
            return None


def visualize_captured_data(data_dir):
    """Visualize the captured IQ data using matplotlib"""
    
    # Find all .npy files in the directory (recursively)
    iq_files = []
    for root, _, files in os.walk(data_dir):
        for file in files:
            if file.endswith('_iq.npy'):
                iq_files.append(os.path.join(root, file))
    
    if not iq_files:
        logger.error(f"No IQ data files found in {data_dir}")
        return
    
    logger.info(f"Found {len(iq_files)} IQ data files")
    
    # Create a figure with subplots based on number of files
    n_rows = (len(iq_files) + 1) // 2
    fig, axes = plt.subplots(n_rows, 2, figsize=(12, 4 * n_rows))
    axes = axes.flatten() if n_rows > 1 else [axes]
    
    # Process each IQ data file
    for i, iq_file in enumerate(iq_files):
        if i >= len(axes):
            break
            
        # Load the IQ data
        iq_data = np.load(iq_file)
        
        # Compute FFT for spectral analysis
        n_fft = 1024
        spectrum = np.abs(np.fft.fftshift(np.fft.fft(iq_data[:10000], n=n_fft)))
        freq = np.fft.fftshift(np.fft.fftfreq(n_fft, 1/12000))  # Assuming 12 kHz sample rate
        
        # Plot the spectrum
        axes[i].plot(freq, 10 * np.log10(spectrum + 1e-10))  # dB scale
        axes[i].set_title(f"Spectrum from {os.path.basename(iq_file)}")
        axes[i].set_xlabel("Frequency (Hz)")
        axes[i].set_ylabel("Power (dB)")
        axes[i].grid(True)
    
    # Hide any unused subplots
    for i in range(len(iq_files), len(axes)):
        axes[i].set_visible(False)
    
    plt.tight_layout()
    
    # Save the visualization
    vis_path = os.path.join(data_dir, "spectrum_visualization.png")
    plt.savefig(vis_path)
    logger.info(f"Saved visualization to {vis_path}")
    
    # Show the plot interactively if in an interactive environment
    plt.show()


async def main():
    # Define the frequency you want to capture (in MHz)
    target_frequency = 10.0  # 10 MHz (WWV time signal)
    
    # Example 1: Capture from a single KiwiSDR station
    capture_dir = await capture_single_station(target_frequency, duration_sec=15)
    
    if capture_dir:
        # Visualize the captured data
        visualize_captured_data(capture_dir)
    
    # Example 2: Capture from multiple KiwiSDR stations
    # saved_dirs = await capture_multiple_stations(target_frequency, duration_sec=10, max_stations=2)
    # if saved_dirs and saved_dirs[0]:
    #     visualize_captured_data(os.path.dirname(saved_dirs[0]))


if __name__ == "__main__":
    asyncio.run(main())