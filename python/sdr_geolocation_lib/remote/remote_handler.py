"""
Remote SDR interfaces and handlers.

This module contains classes for connecting to remote SDR providers
like KiwiSDR network and WebSDR.
"""

import time
import aiohttp
import asyncio
import logging
import json
import os
import numpy as np
from datetime import datetime
from typing import Dict, List, Optional, Tuple, BinaryIO, Union
from dataclasses import dataclass

# Import from local modules
from sdr_geolocation_lib.models import SDRReceiver, SignalMeasurement
from sdr_geolocation_lib.capture import DataCapture

# Configure logging
logger = logging.getLogger('remote_sdr')


@dataclass
class KiwiStation:
    """Represents a KiwiSDR station"""
    station_id: str
    name: str
    url: str
    latitude: float
    longitude: float
    band_coverage: List[Dict[str, float]]
    active: bool = True
    last_seen: float = None


class KiwiSDRClient:
    """Client for interacting with KiwiSDR network"""
    
    def __init__(self):
        self.session: Optional[aiohttp.ClientSession] = None
        self.stations: Dict[str, KiwiStation] = {}
        self.station_list_url = "https://sdr.hu/api/stations"
        self.last_update = 0
        self.update_interval = 3600  # Update station list every hour
        self.websocket = None
        self.iq_data_buffer = bytearray()
        
    async def __aenter__(self):
        """Context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()
            self.websocket = None
            
        if self.session:
            await self.session.close()
            self.session = None
            
    async def update_station_list(self, force: bool = False) -> None:
        """Update the list of available KiwiSDR stations"""
        now = time.time()
        if not force and (now - self.last_update) < self.update_interval:
            return
            
        if not self.session:
            raise RuntimeError("Client not initialized - use as context manager")
            
        try:
            async with self.session.get(self.station_list_url) as response:
                if response.status == 200:
                    data = await response.json()
                    stations = []
                    for station in data.get('stations', []):
                        if station.get('status') == 'online':
                            stations.append(KiwiStation(
                                station_id=station['id'],
                                name=station['name'],
                                url=station['url'],
                                latitude=float(station.get('lat', 0)),
                                longitude=float(station.get('lon', 0)),
                                band_coverage=self._parse_band_coverage(station.get('bands', '')),
                                last_seen=now
                            ))
                    
                    # Update stations dict
                    self.stations = {s.station_id: s for s in stations}
                    self.last_update = now
                    logger.info(f"Updated KiwiSDR station list: {len(self.stations)} active stations")
                else:
                    logger.error(f"Failed to fetch station list: HTTP {response.status}")
                    
        except Exception as e:
            logger.error(f"Error updating station list: {e}")
            
    async def get_station_data(self, station: KiwiStation, frequency: float) -> Optional[Dict]:
        """Get data from a specific KiwiSDR station for a given frequency"""
        if not self.session:
            raise RuntimeError("Client not initialized - use as context manager")
            
        if not self._frequency_in_range(station, frequency):
            return None
            
        try:
            url = f"{station.url}/api/data"
            params = {
                "freq": frequency/1e6,  # Convert to MHz
                "compression": "none",
                "output": "json"
            }
            
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    data = await response.json()
                    return {
                        "station_id": station.station_id,
                        "station_name": station.name,
                        "latitude": station.latitude,
                        "longitude": station.longitude,
                        "frequency": frequency,
                        "signal_strength": data.get("signal_strength", 0),
                        "snr": data.get("snr", 0),
                        "timestamp": time.time()
                    }
                else:
                    logger.warning(f"Failed to get data from {station.name}: HTTP {response.status}")
                    return None
                    
        except Exception as e:
            logger.error(f"Error getting data from {station.name}: {e}")
            return None
            
    async def get_measurements(self, frequency: float, max_stations: int = 5) -> List[Dict]:
        """Get measurements from multiple KiwiSDR stations for a frequency"""
        await self.update_station_list()
        
        # Find stations that can receive this frequency
        suitable_stations = [
            station for station in self.stations.values()
            if self._frequency_in_range(station, frequency)
        ]
        
        # Sort by last seen time and limit number of stations
        suitable_stations.sort(key=lambda s: s.last_seen or 0, reverse=True)
        suitable_stations = suitable_stations[:max_stations]
        
        # Get data from each station
        tasks = [
            self.get_station_data(station, frequency)
            for station in suitable_stations
        ]
        
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]
        
    def _parse_band_coverage(self, bands_str: str) -> List[Dict[str, float]]:
        """Parse band coverage string into frequency ranges"""
        coverage = []
        try:
            for band in bands_str.split(','):
                if '-' in band:
                    start, end = band.split('-')
                    coverage.append({
                        'start': float(start),
                        'end': float(end)
                    })
        except Exception:
            pass
        return coverage
        
    def _frequency_in_range(self, station: KiwiStation, frequency: float) -> bool:
        """Check if a frequency is within a station's coverage"""
        freq_mhz = frequency / 1e6
        return any(
            coverage['start'] <= freq_mhz <= coverage['end']
            for coverage in station.band_coverage
        )

    async def connect_to_kiwi_websocket(self, station: KiwiStation) -> bool:
        """
        Establish a WebSocket connection to a KiwiSDR station
        
        Args:
            station: The KiwiStation to connect to
            
        Returns:
            bool: True if connection was successful, False otherwise
        """
        if self.websocket and not self.websocket.closed:
            await self.websocket.close()
        
        try:
            ws_url = f"ws://{station.url.replace('http://', '')}/kiwi/ws/"
            self.websocket = await self.session.ws_connect(ws_url, timeout=10)
            
            # Send initial connection message
            await self.websocket.send_str('SET auth t=kiwi p=sdrgeo')
            
            # Wait for confirmation
            for _ in range(10):  # Try a few times with timeout
                msg = await self.websocket.receive(timeout=5)
                if msg.type == aiohttp.WSMsgType.TEXT and "connection_opened" in msg.data:
                    logger.info(f"WebSocket connection established to {station.name}")
                    return True
            
            logger.error(f"Failed to get connection confirmation from {station.name}")
            return False
            
        except Exception as e:
            logger.error(f"Error connecting to WebSocket for {station.name}: {e}")
            return False

    async def get_iq_data(self, station: KiwiStation, frequency: float, 
                        sample_rate: float = 12000, duration: float = 10.0) -> Optional[np.ndarray]:
        """
        Gets raw IQ data from a KiwiSDR station.

        Args:
            station: The KiwiStation object.
            frequency: Center frequency in Hz.
            sample_rate: Desired sample rate in Hz (default: 12 kHz).
            duration: Capture duration in seconds (default: 10 seconds).

        Returns:
            A NumPy array of complex64 samples, or None on error.
        """
        if not self.session:
            raise RuntimeError("Client not initialized - use as context manager")

        if not self._frequency_in_range(station, frequency):
            logger.warning(f"Frequency {frequency/1e6} MHz is not in range for station {station.name}")
            return None
        
        # Clear any existing data in buffer
        self.iq_data_buffer.clear()
        
        try:
            # Connect via WebSocket
            connected = await self.connect_to_kiwi_websocket(station)
            if not connected:
                return None
                
            # Configure the SDR for IQ data
            freq_mhz = frequency / 1e6
            await self.websocket.send_str(f'SET mod=iq_f low_cut=-5000 high_cut=5000')
            await self.websocket.send_str(f'SET freq={freq_mhz}')
            await self.websocket.send_str(f'SET compression=0')  # No compression
            await self.websocket.send_str(f'SET zoom=0')         # No zoom
            await self.websocket.send_str(f'SET AGC=0')          # Disable AGC
            await self.websocket.send_str(f'SET AR_OFF=1')       # Disable auto-reconnect
            await self.websocket.send_str(f'SET IQ=1')           # Enable IQ mode
            
            # Start the data streaming
            await self.websocket.send_str('SET start=1')
            
            logger.info(f"Starting IQ data collection from {station.name} at {freq_mhz} MHz")
            
            # Collect data for specified duration
            start_time = time.time()
            while time.time() - start_time < duration:
                msg = await self.websocket.receive(timeout=1.0)
                if msg.type == aiohttp.WSMsgType.BINARY:
                    self.iq_data_buffer.extend(msg.data)
                elif msg.type == aiohttp.WSMsgType.TEXT:
                    # Process any text messages if needed
                    pass
                elif msg.type in [aiohttp.WSMsgType.CLOSED, aiohttp.WSMsgType.ERROR]:
                    logger.error(f"WebSocket closed or error while collecting data")
                    break
            
            # Stop the data streaming
            await self.websocket.send_str('SET stop=1')
            
            # Process the collected data
            if len(self.iq_data_buffer) < 100:  # Sanity check
                logger.warning(f"Received too little data: {len(self.iq_data_buffer)} bytes")
                return None
            
            # Convert the binary data to complex samples
            # The format is typically interleaved I/Q 16-bit samples
            # Note: The exact format may vary depending on the KiwiSDR server
            samples = np.frombuffer(self.iq_data_buffer, dtype=np.int16)
            
            # Reshape into I and Q components (even indices are I, odd indices are Q)
            i_samples = samples[0::2]
            q_samples = samples[1::2]
            
            # Convert to complex data (normalize to float and create complex numbers)
            complex_samples = (i_samples.astype(np.float32) + 1j * q_samples.astype(np.float32)) / 32768.0
            
            logger.info(f"Collected {len(complex_samples)} IQ samples from {station.name}")
            return complex_samples
            
        except Exception as e:
            logger.error(f"Error getting IQ data from {station.name}: {e}")
            return None
        finally:
            # Ensure the WebSocket is closed
            if self.websocket and not self.websocket.closed:
                await self.websocket.close()
                self.websocket = None
    
    async def capture_and_save_data(self, station: KiwiStation, frequency: float, 
                                  sample_rate: float = 12000, duration: float = 10.0,
                                  output_dir: str = None) -> Optional[str]:
        """
        Captures IQ data from a KiwiSDR station and saves it with metadata.

        Args:
            station: The KiwiStation object.
            frequency: Center frequency in Hz.
            sample_rate: Desired sample rate in Hz.
            duration: Capture duration in seconds.
            output_dir: Directory to save data (default: creates a timestamped directory).

        Returns:
            The directory path where data was saved, or None on error.
        """
        # Create output directory if not specified
        if not output_dir:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join("dataset", timestamp)
        
        os.makedirs(output_dir, exist_ok=True)
        
        # Generate unique filename based on timestamp and frequency
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        freq_mhz = frequency / 1e6
        base_filename = f"{timestamp}_{station.station_id}_{freq_mhz:.3f}MHz"
        
        # Capture IQ data
        iq_data = await self.get_iq_data(station, frequency, sample_rate, duration)
        if iq_data is None:
            logger.error(f"Failed to capture IQ data from {station.name}")
            return None
        
        # Save IQ data to .npy file
        iq_filename = os.path.join(output_dir, f"{base_filename}_iq.npy")
        np.save(iq_filename, iq_data)
        logger.info(f"Saved IQ data to {iq_filename}")
        
        # Create and save metadata
        metadata = {
            "timestamp": time.time(),
            "datetime": timestamp,
            "station_id": station.station_id,
            "station_name": station.name,
            "frequency": frequency,
            "sample_rate": sample_rate,
            "duration": duration,
            "latitude": station.latitude,
            "longitude": station.longitude,
            "samples_count": len(iq_data),
            "file_format": "numpy complex64"
        }
        
        metadata_filename = os.path.join(output_dir, f"{base_filename}_metadata.json")
        with open(metadata_filename, 'w') as f:
            json.dump(metadata, f, indent=4)
        logger.info(f"Saved metadata to {metadata_filename}")
        
        return output_dir
    
    async def capture_with_screen_ocr(self, station: KiwiStation, frequency: float, 
                                    sample_rate: float = 12000, duration: float = 10.0,
                                    output_dir: str = None, region: Tuple[int, int, int, int] = None,
                                    ssim_threshold: float = 0.95, capture_interval: float = 1.0,
                                    monitor_number: int = 1) -> Optional[Dict]:
        """
        Captures IQ data along with screenshots and OCR text from the KiwiSDR web interface.
        
        This method combines IQ data acquisition with screen capture and OCR to generate
        a comprehensive dataset suitable for machine learning training.
        
        Args:
            station: The KiwiStation object
            frequency: Center frequency in Hz
            sample_rate: Sample rate in Hz (default: 12 kHz)
            duration: Capture duration in seconds
            output_dir: Directory to save data (default: creates a timestamped directory)
            region: Optional tuple of (left, top, width, height) for screen capture region
            ssim_threshold: Threshold for detecting changes between frames (0-1)
            capture_interval: Time between screen captures in seconds
            monitor_number: Monitor to capture from (typically 1)
            
        Returns:
            Dict with paths to saved data or None on error
        """
        if not self.session:
            raise RuntimeError("Client not initialized - use as context manager")

        if not self._frequency_in_range(station, frequency):
            logger.warning(f"Frequency {frequency/1e6} MHz is not in range for station {station.name}")
            return None
        
        # Create output directory if not specified
        if not output_dir:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join("dataset", timestamp)
        
        # Create specific directories for different data types
        iq_data_dir = os.path.join(output_dir, "iq_data")
        screen_data_dir = os.path.join(output_dir, "screen_data")
        os.makedirs(iq_data_dir, exist_ok=True)
        os.makedirs(screen_data_dir, exist_ok=True)
        
        # Generate unique base filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        freq_mhz = frequency / 1e6
        base_filename = f"{timestamp}_{station.station_id}_{freq_mhz:.3f}MHz"
        
        # Initialize screen capture system
        data_capture = DataCapture(
            ssim_threshold=ssim_threshold,
            capture_interval=capture_interval,
            monitor_number=monitor_number,
            region=region
        )
        
        # Start screen capture in a separate task
        screen_capture_task = asyncio.create_task(
            self._capture_screen_task(
                data_capture,
                screen_data_dir,
                duration,
                frequency
            )
        )
        
        # Capture IQ data (main task)
        iq_data = await self.get_iq_data(
            station,
            frequency,
            sample_rate,
            duration
        )
        
        # Wait for the screen capture task to complete
        ocr_results = await screen_capture_task
        
        if iq_data is None:
            logger.error(f"Failed to capture IQ data from {station.name}")
            return None
        
        # Save IQ data to .npy file
        iq_filename = os.path.join(iq_data_dir, f"{base_filename}_iq.npy")
        np.save(iq_filename, iq_data)
        logger.info(f"Saved IQ data to {iq_filename}")
        
        # Create and save metadata including OCR results
        metadata = {
            "timestamp": time.time(),
            "datetime": timestamp,
            "station_id": station.station_id,
            "station_name": station.name,
            "frequency": frequency,
            "sample_rate": sample_rate,
            "duration": duration,
            "latitude": station.latitude,
            "longitude": station.longitude,
            "samples_count": len(iq_data),
            "file_format": "numpy complex64",
            "ocr_results": ocr_results,
            "screen_capture_dir": screen_data_dir,
        }
        
        metadata_filename = os.path.join(output_dir, f"{base_filename}_metadata.json")
        with open(metadata_filename, 'w') as f:
            json.dump(metadata, f, indent=4)
        logger.info(f"Saved combined metadata to {metadata_filename}")
        
        # Return paths to the saved data
        return {
            "output_dir": output_dir,
            "iq_data_path": iq_filename,
            "screen_data_dir": screen_data_dir,
            "metadata_path": metadata_filename,
            "ocr_results": ocr_results
        }
    
    async def _capture_screen_task(self, data_capture: DataCapture, output_dir: str, 
                                duration: float, frequency: float) -> List[Tuple]:
        """
        Helper method for capturing screen data in a separate task.
        
        Args:
            data_capture: DataCapture object
            output_dir: Directory to save screen capture data
            duration: Duration to capture in seconds
            frequency: Frequency in Hz (for metadata)
            
        Returns:
            List of OCR results (timestamp, image_filename, ocr_text)
        """
        return data_capture.capture_and_process(
            output_dir=output_dir,
            duration=duration,
            frequency=frequency,
            include_preprocessing=True
        )


class RemoteSDRHandler:
    """Handles connections to remote SDR providers"""
    
    def __init__(self):
        self.providers = {
            "kiwisdr": {
                "enabled": True,
                "client": KiwiSDRClient(),
                "max_stations": 5  # Max number of KiwiSDR stations to use per frequency
            },
            "websdr": {
                "url": "http://websdr.org/api", 
                "enabled": True
            }
        }
        self.session: Optional[aiohttp.ClientSession] = None
    
    async def __aenter__(self):
        """Context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
        if self.session:
            await self.session.close()
            self.session = None
    
    async def fetch_data(self, frequency: float) -> List[Dict]:
        """Fetch data from remote SDR providers for the given frequency"""
        if not self.session:
            raise RuntimeError("RemoteSDRHandler must be used as context manager")
            
        results = []
        
        # Fetch from KiwiSDR network
        if self.providers["kiwisdr"]["enabled"]:
            try:
                async with self.providers["kiwisdr"]["client"] as kiwi:
                    measurements = await kiwi.get_measurements(
                        frequency,
                        max_stations=self.providers["kiwisdr"]["max_stations"]
                    )
                    
                    for data in measurements:
                        measurement = SignalMeasurement(
                            receiver_id=f"kiwisdr_{data['station_id']}",
                            frequency=frequency,
                            power=data['signal_strength'],
                            timestamp=data['timestamp'],
                            snr=data['snr']
                        )
                        results.append({
                            "provider": "kiwisdr",
                            "data": data,
                            "measurement": measurement
                        })
            except Exception as e:
                logger.error(f"Error fetching from KiwiSDR network: {e}")
        
        # Fetch from WebSDR network
        if self.providers["websdr"]["enabled"]:
            try:
                async with self.session.get(
                    f"{self.providers['websdr']['url']}/data",
                    params={"freq": frequency/1e6},
                    timeout=aiohttp.ClientTimeout(total=10)
                ) as response:
                    if response.status == 200:
                        data = await response.json()
                        measurement = SignalMeasurement(
                            receiver_id=f"websdr_{data.get('station_id', 'unknown')}",
                            frequency=frequency,
                            power=data.get('power', 0.0),
                            timestamp=time.time(),
                            snr=data.get('snr')
                        )
                        results.append({
                            "provider": "websdr",
                            "data": data,
                            "measurement": measurement
                        })
            except Exception as e:
                logger.error(f"Error fetching from WebSDR: {e}")
                
        return results
    
    def create_virtual_receiver(self, provider_data: Dict) -> SDRReceiver:
        """Create a virtual SDR receiver from provider data"""
        provider = provider_data['provider']
        data = provider_data['data']
        
        if provider == "kiwisdr":
            return SDRReceiver(
                id=f"kiwisdr_{data['station_id']}",
                latitude=data['latitude'],
                longitude=data['longitude'],
                altitude=0.0,  # KiwiSDR stations typically don't provide altitude
                timestamp=data['timestamp'],
                active=True
            )
        else:  # websdr
            return SDRReceiver(
                id=f"websdr_{data.get('station_id', 'unknown')}",
                latitude=data.get('latitude', 0.0),
                longitude=data.get('longitude', 0.0),
                altitude=data.get('altitude', 0.0),
                timestamp=time.time(),
                active=True
            )
        
    async def capture_iq_data(self, frequency: float, sample_rate: float = 12000, 
                            duration: float = 10.0, output_dir: str = None,
                            max_stations: int = 3) -> List[str]:
        """
        Capture IQ data from multiple remote SDR stations.
        
        Args:
            frequency: Center frequency in Hz
            sample_rate: Sample rate in Hz
            duration: Capture duration in seconds
            output_dir: Base directory to save data (will create subdirectories)
            max_stations: Maximum number of stations to use
            
        Returns:
            List of directory paths where data was saved
        """
        if not self.session:
            raise RuntimeError("RemoteSDRHandler must be used as context manager")
        
        # Create timestamped base directory if not specified
        if not output_dir:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join("dataset", timestamp)
            os.makedirs(output_dir, exist_ok=True)
        
        saved_dirs = []
        
        # Capture from KiwiSDR network
        if self.providers["kiwisdr"]["enabled"]:
            try:
                async with self.providers["kiwisdr"]["client"] as kiwi:
                    await kiwi.update_station_list()
                    
                    # Find stations that can receive this frequency
                    suitable_stations = [
                        station for station in kiwi.stations.values()
                        if kiwi._frequency_in_range(station, frequency)
                    ]
                    
                    # Sort by last seen time and limit number of stations
                    suitable_stations.sort(key=lambda s: s.last_seen or 0, reverse=True)
                    suitable_stations = suitable_stations[:max_stations]
                    
                    logger.info(f"Found {len(suitable_stations)} suitable KiwiSDR stations for {frequency/1e6} MHz")
                    
                    # Capture data from each station sequentially
                    for idx, station in enumerate(suitable_stations):
                        station_dir = os.path.join(output_dir, f"station_{station.station_id}")
                        os.makedirs(station_dir, exist_ok=True)
                        
                        logger.info(f"Capturing from station {idx+1}/{len(suitable_stations)}: {station.name}")
                        result_dir = await kiwi.capture_and_save_data(
                            station, frequency, sample_rate, duration, station_dir
                        )
                        
                        if result_dir:
                            saved_dirs.append(result_dir)
                        else:
                            logger.warning(f"Failed to capture data from {station.name}")
            
            except Exception as e:
                logger.error(f"Error capturing IQ data from KiwiSDR network: {e}")
        
        # Could add WebSDR or other provider support here
        
        return saved_dirs
    
    async def capture_iq_with_screen(self, frequency: float, sample_rate: float = 12000, 
                                   duration: float = 10.0, output_dir: str = None,
                                   max_stations: int = 1, region: Tuple[int, int, int, int] = None) -> List[Dict]:
        """
        Capture IQ data along with screenshots and OCR from multiple KiwiSDR stations.
        
        This method captures both IQ data and screen captures with OCR text from KiwiSDR stations,
        and organizes them into a dataset suitable for machine learning.
        
        Args:
            frequency: Center frequency in Hz
            sample_rate: Sample rate in Hz
            duration: Capture duration in seconds
            output_dir: Base directory to save data
            max_stations: Maximum number of stations to use (recommend 1 for screen capture)
            region: Screen region to capture (left, top, width, height)
            
        Returns:
            List of dictionaries with paths to saved data
        """
        if not self.session:
            raise RuntimeError("RemoteSDRHandler must be used as context manager")
        
        # Create timestamped base directory if not specified
        if not output_dir:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_dir = os.path.join("dataset", timestamp)
            os.makedirs(output_dir, exist_ok=True)
        
        results = []
        
        # Capture from KiwiSDR network
        if self.providers["kiwisdr"]["enabled"]:
            try:
                async with self.providers["kiwisdr"]["client"] as kiwi:
                    await kiwi.update_station_list()
                    
                    # Find stations that can receive this frequency
                    suitable_stations = [
                        station for station in kiwi.stations.values()
                        if kiwi._frequency_in_range(station, frequency)
                    ]
                    
                    # Sort by last seen time and limit number of stations
                    suitable_stations.sort(key=lambda s: s.last_seen or 0, reverse=True)
                    suitable_stations = suitable_stations[:max_stations]
                    
                    logger.info(f"Found {len(suitable_stations)} suitable KiwiSDR stations for {frequency/1e6} MHz")
                    
                    # Capture data from each station sequentially
                    for idx, station in enumerate(suitable_stations):
                        station_dir = os.path.join(output_dir, f"station_{station.station_id}")
                        os.makedirs(station_dir, exist_ok=True)
                        
                        logger.info(f"Capturing IQ data and screen from station {idx+1}/{len(suitable_stations)}: {station.name}")
                        
                        result = await kiwi.capture_with_screen_ocr(
                            station=station,
                            frequency=frequency,
                            sample_rate=sample_rate,
                            duration=duration,
                            output_dir=station_dir,
                            region=region
                        )
                        
                        if result:
                            results.append(result)
                        else:
                            logger.warning(f"Failed to capture data from {station.name}")
            
            except Exception as e:
                logger.error(f"Error capturing combined data from KiwiSDR network: {e}")
        
        return results