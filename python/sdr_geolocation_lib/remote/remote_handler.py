"""
Remote SDR interfaces and handlers.

This module contains classes for connecting to remote SDR providers
like KiwiSDR network and WebSDR.
"""

import time
import aiohttp
import asyncio
import logging
from typing import Dict, List, Optional
from dataclasses import dataclass

# Import from local modules
from sdr_geolocation_lib.models import SDRReceiver, SignalMeasurement

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
        
    async def __aenter__(self):
        """Context manager entry"""
        self.session = aiohttp.ClientSession()
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit"""
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