# KiwiSDR Integration

## Overview
The SDR Drone Pursuit System integrates with the KiwiSDR network to enhance signal detection and geolocation capabilities. KiwiSDR is a network of software-defined radios (SDRs) that provide remote access to RF spectrum data from various locations worldwide. This integration allows the system to:

- Fetch real-time signal data from multiple remote SDRs
- Perform geolocation using signal strength and SNR measurements
- Expand frequency coverage beyond local SDR hardware

## KiwiSDR Client

The `KiwiSDRClient` class in `kiwisdr_client.py` handles communication with the KiwiSDR network. It provides methods to:

1. Fetch and update the list of available KiwiSDR stations
2. Query specific stations for signal data at a given frequency
3. Aggregate measurements from multiple stations for enhanced analysis

### Key Features

- **Station List Management**: Automatically updates the list of active KiwiSDR stations every hour.
- **Frequency Matching**: Ensures that queried stations can receive the requested frequency.
- **Parallel Data Retrieval**: Uses asynchronous tasks to fetch data from multiple stations simultaneously.
- **Error Handling**: Logs errors and skips stations that fail to respond.

## Station List Management

The `update_station_list` method fetches the latest list of active KiwiSDR stations from the KiwiSDR API. It filters stations based on their online status and parses their frequency coverage.

```python
async def update_station_list(self, force: bool = False) -> None:
    """Update the list of available KiwiSDR stations"""
    now = datetime.now().timestamp()
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
```

## Querying Station Data

The `get_station_data` method retrieves signal data from a specific KiwiSDR station for a given frequency. It ensures that the frequency is within the station's coverage and returns details such as signal strength and SNR.

```python
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
                    "timestamp": datetime.now().timestamp()
                }
            else:
                logger.warning(f"Failed to get data from {station.name}: HTTP {response.status}")
                return None
                
    except Exception as e:
        logger.error(f"Error getting data from {station.name}: {e}")
        return None
```

## Aggregating Measurements

The `get_measurements` method collects signal data from multiple KiwiSDR stations for a given frequency. It prioritizes stations based on their last seen time and limits the number of queried stations to optimize performance.

```python
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
```

## Frequency Coverage

The `_parse_band_coverage` and `_frequency_in_range` methods ensure that only stations capable of receiving the requested frequency are queried. This improves efficiency and accuracy.

```python
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
```

## Integration with SDR System

The KiwiSDR client is integrated into the SDR Drone Pursuit System to:

1. Enhance geolocation accuracy by aggregating data from multiple remote stations.
2. Expand frequency coverage beyond the capabilities of local SDR hardware.
3. Provide redundancy in case of local hardware failure.

### Example Usage

```python
async def main():
    async with KiwiSDRClient() as client:
        frequency = 14.2e6  # 14.2 MHz
        measurements = await client.get_measurements(frequency)
        for measurement in measurements:
            print(measurement)

if __name__ == "__main__":
    asyncio.run(main())
```

## Future Enhancements

1. **Improved Error Handling**: Add retries for failed requests.
2. **Station Filtering**: Allow filtering by geographic region or signal quality.
3. **Data Caching**: Cache station data to reduce API calls.
4. **Advanced Geolocation**: Use TDOA or multilateration for precise signal source tracking.