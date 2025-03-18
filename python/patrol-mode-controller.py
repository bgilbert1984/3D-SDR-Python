import asyncio
import numpy as np
import websockets
import json
import time
import os
import logging
import math
import random
from collections import deque
from scipy.optimize import minimize
from haversine import haversine
from dronekit import connect, VehicleMode, LocationGlobalRelative, LocationGlobal
import tensorflow as tf

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('drone_patrol_controller')

# Patrol modes
PATROL_MODES = {
    'GRID': 'Grid pattern patrol',
    'SPIRAL': 'Spiral pattern patrol',
    'HOTSPOT': 'AI-optimized hotspot patrol',
    'PERIMETER': 'Perimeter patrol',
    'CUSTOM': 'Custom waypoint patrol'
}

# Operation modes
OPERATION_MODES = {
    'PATROL': 'Patrolling for signals',
    'PURSUIT': 'Pursuing detected violation',
    'TRIANGULATION': 'Supporting triangulation',
    'RETURNING': 'Returning to base',
    'STANDBY': 'Standing by for assignment'
}

class PatrolZone:
    """Defines a geographical zone for patrolling"""
    
    def __init__(self, name, boundaries, altitude_range=(50, 120), priority=1):
        """
        Initialize a patrol zone
        
        Args:
            name: Zone identifier
            boundaries: [lat_min, lon_min, lat_max, lon_max]
            altitude_range: (min_alt, max_alt) in meters
            priority: Priority level (higher = more important)
        """
        self.name = name
        self.boundaries = boundaries
        self.altitude_range = altitude_range
        self.priority = priority
        self.hotspots = []  # List of (lat, lon, weight) tuples for historical violation hotspots
    
    def contains_point(self, lat, lon):
        """Check if a point is within this zone"""
        lat_min, lon_min, lat_max, lon_max = self.boundaries
        return lat_min <= lat <= lat_max and lon_min <= lon <= lon_max
    
    def get_random_point(self):
        """Get a random point within the zone"""
        lat_min, lon_min, lat_max, lon_max = self.boundaries
        lat = lat_min + random.random() * (lat_max - lat_min)
        lon = lon_min + random.random() * (lon_max - lon_min)
        return lat, lon
    
    def get_altitude(self):
        """Get a random altitude within the allowed range"""
        min_alt, max_alt = self.altitude_range
        return min_alt + random.random() * (max_alt - min_alt)
    
    def add_hotspot(self, lat, lon, weight=1.0):
        """Add a historical violation hotspot"""
        self.hotspots.append((lat, lon, weight))

class DronePatrolController:
    """Controller for drone patrol operations with SDR scanning"""
    
    def __init__(self, config_file='drone_patrol_config.json'):
        """Initialize drone patrol controller"""
        self.config = self._load_config(config_file)
        self.vehicle = None
        self.websocket = None
        self.sdr_data = {}
        
        # Patrol state
        self.current_mode = 'STANDBY'
        self.patrol_mode = self.config['patrol']['default_mode']
        self.patrol_waypoints = []
        self.current_waypoint_index = 0
        self.patrol_zones = []
        self.current_zone = None
        self.scan_results = []
        self.hotspots = []
        
        # Pursuit state
        self.pursuit_target = None
        self.pursuit_frequency = None
        
        # Drone swarm info
        self.drone_id = self.config['drone_id']
        self.other_drones = {}
        self.known_signals = {}
        self.known_violations = {}
        
        # Load patrol zones
        self._load_patrol_zones()
        
        logger.info(f"Drone {self.drone_id} patrol controller initialized")
    
    def _load_config(self, config_file):
        """Load configuration from JSON file"""
        if not os.path.exists(config_file):
            # Default configuration
            config = {
                'drone_id': 'patrol1',
                'connection_string': 'udp:127.0.0.1:14550',
                'websocket_url': 'ws://localhost:8766',
                'home_location': [37.7749, -122.4194, 0],
                'patrol': {
                    'default_mode': 'GRID',
                    'grid_size': 10,
                    'patrol_speed': 5,  # m/s
                    'scan_interval': 2,  # seconds
                    'waypoint_radius': 10,  # meters to consider waypoint reached
                    'altitude_range': [50, 120],  # meters
                    'default_altitude': 80,
                    'patrol_zones': [
                        {
                            'name': 'Downtown',
                            'boundaries': [37.7699, -122.4294, 37.7799, -122.4094],
                            'priority': 2
                        },
                        {
                            'name': 'Marina',
                            'boundaries': [37.8020, -122.4400, 37.8080, -122.4300],
                            'priority': 1
                        }
                    ]
                },
                'spectrum': {
                    'frequency_bands': [
                        [88e6, 108e6],  # FM broadcast
                        [450e6, 470e6],  # UHF band
                    ],
                    'center_freq': 100e6,
                    'sample_rate': 2.048e6,
                    'gain': 20
                }
            }
            # Save default config
            with open(config_file, 'w') as f:
                json.dump(config, f, indent=4)
            logger.warning(f"Created default configuration file: {config_file}")
        else:
            # Load existing config
            with open(config_file, 'r') as f:
                config = json.load(f)
            logger.info(f"Loaded configuration from: {config_file}")
        
        return config
    
    def _load_patrol_zones(self):
        """Load patrol zones from configuration"""
        for zone_config in self.config['patrol'].get('patrol_zones', []):
            zone = PatrolZone(
                name=zone_config['name'],
                boundaries=zone_config['boundaries'],
                altitude_range=zone_config.get('altitude_range', self.config['patrol']['altitude_range']),
                priority=zone_config.get('priority', 1)
            )
            self.patrol_zones.append(zone)
        
        # Sort zones by priority
        self.patrol_zones.sort(key=lambda z: z.priority, reverse=True)
        
        if self.patrol_zones:
            self.current_zone = self.patrol_zones[0]
            logger.info(f"Loaded {len(self.patrol_zones)} patrol zones. Primary zone: {self.current_zone.name}")
        else:
            logger.warning("No patrol zones defined. Using default area.")
    
    async def connect_drone(self):
        """Connect to the drone using DroneKit"""
        try:
            logger.info(f"Connecting to drone at: {self.config['connection_string']}")
            self.vehicle = connect(self.config['connection_string'], wait_ready=True)
            logger.info(f"Connected to drone: {self.vehicle.version}")
            
            # Wait for drone to be armable
            while not self.vehicle.is_armable:
                logger.info("Waiting for drone to initialize...")
                await asyncio.sleep(1)
            
            # Set mode to GUIDED
            self.vehicle.mode = VehicleMode("GUIDED")
            logger.info("Drone ready for patrol mission")
            return True
        except Exception as e:
            logger.error(f"Error connecting to drone: {e}")
            return False
    
    async def connect_websocket(self):
        """Connect to the WebSocket server for swarm coordination"""
        try:
            logger.info(f"Connecting to WebSocket at: {self.config['websocket_url']}")
            self.websocket = await websockets.connect(self.config['websocket_url'])
            
            # Register with the server
            registration = {
                "type": "drone_registration",
                "drone_id": self.drone_id,
                "capabilities": {
                    "patrol_enabled": True,
                    "sdr_enabled": True,
                    "operation_mode": self.current_mode,
                    "patrol_mode": self.patrol_mode
                }
            }
            
            await self.websocket.send(json.dumps(registration))
            logger.info(f"Registered drone {self.drone_id} with server")
            
            return True
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            return False
    
    async def takeoff(self, target_altitude=None):
        """Arm and takeoff to target altitude"""
        if target_altitude is None:
            target_altitude = self.config['patrol']['default_altitude']
        
        if not self.vehicle:
            logger.error("No drone connection")
            return False
        
        try:
            logger.info("Arming motors")
            self.vehicle.armed = True
            while not self.vehicle.armed:
                logger.info("Waiting for arming...")
                await asyncio.sleep(1)
            
            logger.info(f"Taking off to {target_altitude} meters")
            self.vehicle.simple_takeoff(target_altitude)
            
            # Wait to reach the target altitude
            while True:
                current_altitude = self.vehicle.location.global_relative_frame.alt
                logger.info(f"Altitude: {current_altitude}")
                if current_altitude >= target_altitude * 0.95:
                    logger.info("Reached target altitude")
                    break
                await asyncio.sleep(1)
            
            return True
        except Exception as e:
            logger.error(f"Takeoff error: {e}")
            return False
    
    async def start_patrol(self):
        """Start patrol operations"""
        if not self.vehicle:
            logger.error("No drone connection")
            return False
        
        try:
            logger.info(f"Starting patrol in {self.patrol_mode} mode")
            self.current_mode = 'PATROL'
            
            # Generate patrol waypoints
            await self.generate_patrol_route()
            
            # Start patrol loop
            patrol_task = asyncio.create_task(self.patrol_loop())
            
            # Start SDR scanning
            scan_task = asyncio.create_task(self.sdr_scan_loop())
            
            # Notify other drones
            status_update = {
                "type": "drone_status",
                "drone_id": self.drone_id,
                "operation_mode": self.current_mode,
                "patrol_mode": self.patrol_mode,
                "current_zone": self.current_zone.name if self.current_zone else None,
                "timestamp": time.time()
            }
            
            if self.websocket:
                await self.websocket.send(json.dumps(status_update))
            
            return True
        except Exception as e:
            logger.error(f"Error starting patrol: {e}")
            return False
    
    async def generate_patrol_route(self):
        """Generate patrol route based on current mode and zone"""
        if not self.current_zone:
            logger.warning("No patrol zone selected. Using default area.")
            
            # Create a default zone around current position
            if self.vehicle:
                lat = self.vehicle.location.global_frame.lat
                lon = self.vehicle.location.global_frame.lon
                default_size = 0.01  # ~1km
                self.current_zone = PatrolZone(
                    "Default",
                    [lat - default_size, lon - default_size, lat + default_size, lon + default_size]
                )
            else:
                home = self.config['home_location']
                default_size = 0.01  # ~1km
                self.current_zone = PatrolZone(
                    "Default",
                    [home[0] - default_size, home[1] - default_size, home[0] + default_size, home[1] + default_size]
                )
        
        # Clear existing waypoints
        self.patrol_waypoints = []
        self.current_waypoint_index = 0
        
        # Generate waypoints based on patrol mode
        if self.patrol_mode == 'GRID':
            await self.generate_grid_patrol()
        elif self.patrol_mode == 'SPIRAL':
            await self.generate_spiral_patrol()
        elif self.patrol_mode == 'PERIMETER':
            await self.generate_perimeter_patrol()
        elif self.patrol_mode == 'HOTSPOT':
            await self.generate_hotspot_patrol()
        elif self.patrol_mode == 'CUSTOM':
            # Custom waypoints should be loaded from config or database
            logger.info("Using custom waypoints")
        else:
            logger.warning(f"Unknown patrol mode: {self.patrol_mode}. Falling back to grid.")
            await self.generate_grid_patrol()
        
        logger.info(f"Generated {len(self.patrol_waypoints)} waypoints for {self.patrol_mode} patrol")
        
        # Send patrol route to visualization
        if self.websocket:
            route_msg = {
                "type": "patrol_route",
                "drone_id": self.drone_id,
                "patrol_mode": self.patrol_mode,
                "waypoints": self.patrol_waypoints,
                "timestamp": time.time()
            }
            await self.websocket.send(json.dumps(route_msg))
    
    async def generate_grid_patrol(self):
        """Generate a grid pattern patrol route"""
        bounds = self.current_zone.boundaries
        lat_min, lon_min, lat_max, lon_max = bounds
        
        grid_size = self.config['patrol'].get('grid_size', 10)
        
        # Calculate steps based on grid size
        lat_step = (lat_max - lat_min) / grid_size
        lon_step = (lon_max - lon_min) / grid_size
        
        # Create a snake pattern grid
        for i in range(grid_size):
            row_points = []
            for j in range(grid_size):
                lat = lat_min + i * lat_step
                
                # If odd row, go right to left, else left to right
                if i % 2 == 0:
                    lon = lon_min + j * lon_step
                else:
                    lon = lon_max - j * lon_step
                
                row_points.append((lat, lon))
            
            self.patrol_waypoints.extend(row_points)
    
    async def generate_spiral_patrol(self):
        """Generate a spiral pattern patrol route"""
        bounds = self.current_zone.boundaries
        lat_min, lon_min, lat_max, lon_max = bounds
        
        # Calculate center of zone
        center_lat = (lat_min + lat_max) / 2
        center_lon = (lon_min + lon_max) / 2
        
        # Calculate max distance from center to corner
        max_distance = max(
            haversine((center_lat, center_lon), (lat_min, lon_min), unit='m'),
            haversine((center_lat, center_lon), (lat_min, lon_max), unit='m'),
            haversine((center_lat, center_lon), (lat_max, lon_min), unit='m'),
            haversine((center_lat, center_lon), (lat_max, lon_max), unit='m')
        )
        
        # Generate spiral points
        num_points = 50  # Number of points in spiral
        spiral_loops = 3  # Number of loops in spiral
        
        for i in range(num_points):
            # Parametric spiral formula
            t = i / num_points * spiral_loops * 2 * math.pi
            radius = max_distance * i / num_points
            
            # Calculate lat/lon offset
            lat_offset = radius * math.cos(t) / 111000  # 1 deg lat = ~111km
            lon_offset = radius * math.sin(t) / (111000 * math.cos(math.radians(center_lat)))  # Adjust for latitude
            
            # Add waypoint
            lat = center_lat + lat_offset
            lon = center_lon + lon_offset
            
            # Ensure point is within bounds
            if lat_min <= lat <= lat_max and lon_min <= lon <= lon_max:
                self.patrol_waypoints.append((lat, lon))
    
    async def generate_perimeter_patrol(self):
        """Generate a perimeter patrol route"""
        bounds = self.current_zone.boundaries
        lat_min, lon_min, lat_max, lon_max = bounds
        
        # Create perimeter points
        num_points = 20  # Points per side
        
        # Bottom edge (left to right)
        for i in range(num_points):
            lon = lon_min + (lon_max - lon_min) * i / (num_points - 1)
            self.patrol_waypoints.append((lat_min, lon))
        
        # Right edge (bottom to top)
        for i in range(num_points):
            lat = lat_min + (lat_max - lat_min) * i / (num_points - 1)
            self.patrol_waypoints.append((lat, lon_max))
        
        # Top edge (right to left)
        for i in range(num_points):
            lon = lon_max - (lon_max - lon_min) * i / (num_points - 1)
            self.patrol_waypoints.append((lat_max, lon))
        
        # Left edge (top to bottom)
        for i in range(num_points):
            lat = lat_max - (lat_max - lat_min) * i / (num_points - 1)
            self.patrol_waypoints.append((lat, lon_min))
    
    async def generate_hotspot_patrol(self):
        """Generate a patrol route focused on historical violation hotspots"""
        if not self.current_zone.hotspots and not self.hotspots:
            logger.warning("No hotspots available. Falling back to grid patrol.")
            await self.generate_grid_patrol()
            return
        
        # Combine zone hotspots and global hotspots
        all_hotspots = list(self.current_zone.hotspots)
        
        # Filter global hotspots to current zone
        for hotspot in self.hotspots:
            lat, lon, weight = hotspot
            if self.current_zone.contains_point(lat, lon):
                all_hotspots.append(hotspot)
        
        if not all_hotspots:
            logger.warning("No hotspots in current zone. Falling back to grid patrol.")
            await self.generate_grid_patrol()
            return
        
        # Sort hotspots by weight (importance)
        all_hotspots.sort(key=lambda h: h[2], reverse=True)
        
        # Take top N hotspots and create a route
        top_hotspots = all_hotspots[:20]  # Limit to 20 hotspots
        
        # Add center point and initial grid points to ensure coverage
        bounds = self.current_zone.boundaries
        center_lat = (bounds[0] + bounds[2]) / 2
        center_lon = (bounds[1] + bounds[3]) / 2
        
        # Start from center
        self.patrol_waypoints.append((center_lat, center_lon))
        
        # Add top hotspots
        for hotspot in top_hotspots:
            self.patrol_waypoints.append((hotspot[0], hotspot[1]))
        
        # Optimize route using a simple nearest-neighbor algorithm
        optimized_route = [self.patrol_waypoints[0]]
        remaining = self.patrol_waypoints[1:]
        
        while remaining:
            last = optimized_route[-1]
            
            # Find closest remaining point
            closest_idx = 0
            closest_dist = float('inf')
            
            for i, point in enumerate(remaining):
                dist = haversine((last[0], last[1]), (point[0], point[1]), unit='m')
                if dist < closest_dist:
                    closest_dist = dist
                    closest_idx = i
            
            # Add closest point to route
            optimized_route.append(remaining.pop(closest_idx))
        
        self.patrol_waypoints = optimized_route
    
    async def patrol_loop(self):
        """Main patrol loop - navigate through waypoints"""
        if not self.vehicle or not self.patrol_waypoints:
            logger.error("Cannot start patrol: no drone connection or waypoints")
            return
        
        try:
            logger.info("Starting patrol loop")
            
            while self.current_mode == 'PATROL':
                # Get next waypoint
                if self.current_waypoint_index >= len(self.patrol_waypoints):
                    self.current_waypoint_index = 0
                
                waypoint = self.patrol_waypoints[self.current_waypoint_index]
                altitude = self.current_zone.get_altitude()
                
                # Move to waypoint
                logger.info(f"Moving to waypoint {self.current_waypoint_index}: {waypoint}")
                
                target = LocationGlobalRelative(
                    waypoint[0],
                    waypoint[1],
                    altitude
                )
                
                # Set speed
                self.vehicle.airspeed = self.config['patrol'].get('patrol_speed', 5)
                
                # Navigate to waypoint
                self.vehicle.simple_goto(target)
                
                # Wait until we reach the waypoint
                reached = False
                start_time = time.time()
                timeout = 60  # seconds
                
                while not reached and time.time() - start_time < timeout:
                    # Check if we've switched modes
                    if self.current_mode != 'PATROL':
                        logger.info("Patrol mode changed, exiting patrol loop")
                        return
                    
                    # Check if we're at the waypoint
                    current_loc = (
                        self.vehicle.location.global_frame.lat,
                        self.vehicle.location.global_frame.lon
                    )
                    
                    distance = haversine(current_loc, waypoint, unit='m')
                    
                    if distance < self.config['patrol'].get('waypoint_radius', 10):
                        reached = True
                        logger.info(f"Reached waypoint {self.current_waypoint_index}")
                        
                        # Log visit to visualization
                        if self.websocket:
                            visit_msg = {
                                "type": "waypoint_visit",
                                "drone_id": self.drone_id,
                                "waypoint_index": self.current_waypoint_index,
                                "location": {
                                    "latitude": waypoint[0],
                                    "longitude": waypoint[1],
                                    "altitude": altitude
                                },
                                "timestamp": time.time()
                            }
                            await self.websocket.send(json.dumps(visit_msg))
                        
                        break
                    
                    # Check for collision risks
                    await self.check_collision_risks()
                    
                    # Short sleep
                    await asyncio.sleep(1)
                
                # Move to next waypoint
                self.current_waypoint_index += 1
                
                # Optionally hover at waypoint for scanning
                if reached:
                    hover_time = 3  # seconds
                    logger.info(f"Hovering at waypoint for {hover_time} seconds")
                    await asyncio.sleep(hover_time)
                
        except Exception as e:
            logger.error(f"Error in patrol loop: {e}")
            self.current_mode = 'STANDBY'
    
    async def sdr_scan_loop(self):
        """Continuously scan for signals while patrolling"""
        logger.info("Starting SDR scan loop")
        
        try:
            while self.current_mode in ['PATROL', 'PURSUIT']:
                # Scan frequency bands
                for band in self.config['spectrum'].get('frequency_bands', []):
                    start_freq, end_freq = band
                    
                    # Simulate SDR scan (in a real implementation, this would use actual SDR hardware)
                    scan_results = await self.simulate_sdr_scan(start_freq, end_freq)
                    
                    # Process scan results
                    for result in scan_results:
                        await self.process_signal(result)
                
                # Wait for next scan interval
                await asyncio.sleep(self.config['patrol'].get('scan_interval', 2))
        except Exception as e:
            logger.error(f"Error in SDR scan loop: {e}")
    
    async def simulate_sdr_scan(self, start_freq, end_freq):
        """Simulate SDR scan for testing (replace with actual SDR code)"""
        results = []
        
        # In real implementation, this would use pyrtlsdr or similar library
        # For now, we'll simulate finding signals occasionally
        
        # 10% chance of finding a signal
        if random.random() < 0.1:
            # Generate a random frequency in the band
            freq = start_freq + random.random() * (end_freq - start_freq)
            
            # Determine if this is a violation (30% chance)
            is_violation = random.random() < 0.3
            
            # Generate signal strength (RSSI)
            rssi = -random.randint(30, 90)  # -30 to -90 dBm
            
            # Current location
            lat = self.vehicle.location.global_frame.lat
            lon = self.vehicle.location.global_frame.lon
            
            # Add some randomness to location
            lat += random.uniform(-0.001, 0.001)
            lon += random.uniform(-0.001, 0.001)
            
            signal = {
                'frequency': freq,
                'rssi': rssi,
                'is_violation': is_violation,
                'modulation': random.choice(['AM', 'FM', 'SSB', 'CW', 'PSK', 'FSK', 'UNKNOWN']),
                'bandwidth': random.randint(5, 200) * 1000,  # 5-200 kHz
                'location': {
                    'latitude': lat,
                    'longitude': lon
                },
                'timestamp': time.time()
            }
            
            results.append(signal)
        
        return results
    
    async def process_signal(self, signal):
        """Process a detected signal"""
        # Check if it's a new signal or update to existing signal
        freq_key = f"{signal['frequency'] / 1e6:.3f}"
        
        is_new = freq_key not in self.known_signals
        
        if is_new:
            # New signal
            self.known_signals[freq_key] = signal
            logger.info(f"Detected new signal at {freq_key} MHz")
            
            # Send to visualization
            if self.websocket:
                signal_msg = {
                    "type": "signal_detected",
                    "drone_id": self.drone_id,
                    "signal": signal,
                    "timestamp": time.time()
                }
                await self.websocket.send(json.dumps(signal_msg))
        else:
            # Update existing signal
            self.known_signals[freq_key].update(signal)
        
        # Check if it's a violation
        if signal['is_violation']:
            await self.handle_violation(signal)
    
    async def handle_violation(self, violation):
        """Handle a detected violation"""
        freq_key = f"{violation['frequency'] / 1e6:.3f}"
        
        # Check if this is a new violation
        is_new = freq_key not in self.known_violations
        
        if is_new:
            # Record violation
            self.known_violations[freq_key] = violation
            
            # Add to hotspots
            lat = violation['location']['latitude']
            lon = violation['location']['longitude']
            self.hotspots.append((lat, lon, 1.0))  # New hotspot with weight 1.0
            
            # Log violation
            logger.warning(f"Detected new violation at {freq_key} MHz")
            
            # Send to visualization
            if self.websocket:
                violation_msg = {
                    "type": "violation_detected",
                    "drone_id": self.drone_id,
                    "violation": violation,
                    "timestamp": time.time()
                }
                await self.websocket.send(json.dumps(violation_msg))
            
            # Check if we should switch to pursuit mode
            if self.current_mode == 'PATROL':
                await self.switch_to_pursuit(violation)
        else:
            # Update existing violation
            self.known_violations[freq_key].update(violation)
            
            # Update hotspot weight
            for i, hotspot in enumerate(self.hotspots):
                lat, lon, weight = hotspot
                v_lat = violation['location']['latitude']
                v_lon = violation['location']['longitude']
                
                # If close to existing hotspot, increase weight
                if haversine((lat, lon), (v_lat, v_lon), unit='m') < 500:
                    # Increase weight (capped at 5.0)
                    new_weight = min(5.0, weight + 0.2)
                    self.hotspots[i] = (lat, lon, new_weight)
                    break
    
    async def switch_to_pursuit(self, violation):
        """Switch from patrol to pursuit mode"""
        logger.info(f"Switching to pursuit mode for violation at {violation['frequency'] / 1e6:.3f} MHz")
        
        # Set target info
        self.pursuit_target = (
            violation['location']['latitude'],
            violation['location']['longitude']
        )
        self.pursuit_frequency = violation['frequency']
        
        # Change mode
        self.current_mode = 'PURSUIT'
        
        # Notify other drones
        if self.websocket:
            pursuit_msg = {
                "type": "pursuit_started",
                "drone_id": self.drone_id,
                "violation": violation,
                "timestamp": time.time()
            }
            await self.websocket.send(json.dumps(pursuit_msg))
        
        # Start pursuit task
        asyncio.create_task(self.pursue_violation())
    
    async def pursue_violation(self):
        """Actively pursue a violation"""
        if not self.pursuit_target:
            logger.error("No pursuit target set")
            self.current_mode = 'PATROL'
            return
        
        try:
            logger.info(f"Pursuing violation at {self.pursuit_target}")
            
            # Set higher speed for pursuit
            self.vehicle.airspeed = 1.5 * self.config['patrol'].get('patrol_speed', 5)
            
            # Move to violation location
            target = LocationGlobalRelative(
                self.pursuit_target[0],
                self.pursuit_target[1],
                self.vehicle.location.global_relative_frame.alt
            )
            
            self.vehicle.simple_goto(target)
            
            # Track progress
            start_time = time.time()
            timeout = 300  # 5 minutes max
            arrived = False
            
            while not arrived and time.time() - start_time < timeout:
                # Check if mode changed
                if self.current_mode != 'PURSUIT':
                    logger.info("No longer in pursuit mode")
                    return
                
                # Check distance to target
                current_loc = (
                    self.vehicle.location.global_frame.lat,
                    self.vehicle.location.global_frame.lon
                )
                
                distance = haversine(current_loc, self.pursuit_target, unit='m')
                logger.info(f"Distance to target: {distance} meters")
                
                if distance < 50:  # Within 50m
                    arrived = True
                    logger.info("Arrived at violation location")
                    
                    # Notify visualization
                    if self.websocket:
                        arrived_msg = {
                            "type": "pursuit_arrived",
                            "drone_id": self.drone_id,
                            "location": {
                                "latitude": self.pursuit_target[0],
                                "longitude": self.pursuit_target[1]
                            },
                            "timestamp": time.time()
                        }
                        await self.websocket.send(json.dumps(arrived_msg))
                    
                    break
                
                # Check for updated target location from SDR readings
                freq_key = f"{self.pursuit_frequency / 1e6:.3f}"
                if freq_key in self.known_violations:
                    violation = self.known_violations[freq_key]
                    
                    # Check if violation location has been updated recently
                    if time.time() - violation.get('timestamp', 0) < 30:  # Within last 30 seconds
                        updated_target = (
                            violation['location']['latitude'],
                            violation['location']['longitude']
                        )
                        
                        # If significantly different, update target
                        if haversine(self.pursuit_target, updated_target, unit='m') > 50:
                            logger.info(f"Updating pursuit target to {updated_target}")
                            self.pursuit_target = updated_target
                            
                            # Move to updated location
                            new_target = LocationGlobalRelative(
                                updated_target[0],
                                updated_target[1],
                                self.vehicle.location.global_relative_frame.alt
                            )
                            
                            self.vehicle.simple_goto(new_target)
                
                # Check for collision risks
                await self.check_collision_risks()
                
                await asyncio.sleep(2)
            
            # If we arrived, hover and monitor for a while
            if arrived:
                logger.info("Hovering at violation location and monitoring signal")
                
                # Hover for 2 minutes while scanning
                hover_end = time.time() + 120
                
                while time.time() < hover_end and self.current_mode == 'PURSUIT':
                    # Check for collision risks while hovering
                    await self.check_collision_risks()
                    
                    # Continue scanning
                    await asyncio.sleep(5)
                
                logger.info("Finished monitoring violation")
            
            # Return to patrol mode
            self.current_mode = 'PATROL'
            self.pursuit_target = None
            self.pursuit_frequency = None
            
            logger.info("Returning to patrol mode")
            
            # Notify other drones
            if self.websocket:
                patrol_msg = {
                    "type": "patrol_resumed",
                    "drone_id": self.drone_id,
                    "timestamp": time.time()
                }
                await self.websocket.send(json.dumps(patrol_msg))
            
            # Resume patrol
            await self.start_patrol()
            
        except Exception as e:
            logger.error(f"Error in pursuit: {e}")
            self.current_mode = 'PATROL'
    
    async def check_collision_risks(self):
        """Check for potential collisions with other drones"""
        if not self.vehicle:
            return
        
        # Get our position
        our_pos = (
            self.vehicle.location.global_frame.lat,
            self.vehicle.location.global_frame.lon,
            self.vehicle.location.global_frame.alt
        )
        
        # Check distance to each other drone
        for drone_id, data in self.other_drones.items():
            if 'location' not in data:
                continue
            
            drone_pos = (
                data['location']['latitude'],
                data['location']['longitude'],
                data['location']['altitude']
            )
            
            # Calculate horizontal and vertical distance
            horizontal_dist = haversine(
                (our_pos[0], our_pos[1]),
                (drone_pos[0], drone_pos[1]),
                unit='m'
            )
            vertical_dist = abs(our_pos[2] - drone_pos[2])
            
            # Check if too close
            min_horizontal = 20  # meters
            min_vertical = 10    # meters
            
            if horizontal_dist < min_horizontal and vertical_dist < min_vertical:
                logger.warning(f"Collision risk with drone {drone_id}. Adjusting altitude.")
                
                # Adjust altitude to avoid collision
                current_alt = self.vehicle.location.global_relative_frame.alt
                
                # If we're higher, go higher, if lower, go lower
                if our_pos[2] >= drone_pos[2]:
                    new_alt = current_alt + 10
                else:
                    new_alt = max(10, current_alt - 10)  # Don't go below 10m
                
                # Move to new altitude
                target = LocationGlobalRelative(
                    our_pos[0],
                    our_pos[1],
                    new_alt
                )
                
                self.vehicle.simple_goto(target)
                
                # Notify about evasive maneuver
                if self.websocket:
                    collision_msg = {
                        "type": "collision_avoidance",
                        "drone_id": self.drone_id,
                        "other_drone": drone_id,
                        "new_altitude": new_alt,
                        "timestamp": time.time()
                    }
                    await self.websocket.send(json.dumps(collision_msg))
                
                # Wait for altitude change
                await asyncio.sleep(5)
    
    async def send_status_update(self):
        """Send periodic status updates to server"""
        if not self.websocket or not self.vehicle:
            return
        
        try:
            location = self.vehicle.location.global_frame
            status = {
                "type": "drone_status",
                "drone_id": self.drone_id,
                "timestamp": time.time(),
                "location": {
                    "latitude": location.lat,
                    "longitude": location.lon,
                    "altitude": location.alt
                },
                "battery": self.vehicle.battery.level if hasattr(self.vehicle, 'battery') else 100,
                "operation_mode": self.current_mode,
                "patrol_mode": self.patrol_mode,
                "current_zone": self.current_zone.name if self.current_zone else None,
                "waypoint_index": self.current_waypoint_index if self.patrol_waypoints else 0,
                "total_waypoints": len(self.patrol_waypoints),
                "pursuit_target": self.pursuit_target,
                "signals_detected": len(self.known_signals),
                "violations_detected": len(self.known_violations)
            }
            
            await self.websocket.send(json.dumps(status))
        except Exception as e:
            logger.error(f"Error sending status update: {e}")
    
    async def receive_messages(self):
        """Process incoming messages from server"""
        if not self.websocket:
            logger.error("No WebSocket connection")
            return
        
        try:
            while True:
                message = await self.websocket.recv()
                data = json.loads(message)
                
                # Process message based on type
                msg_type = data.get('type', '')
                
                if msg_type == 'command':
                    await self.handle_command(data)
                
                elif msg_type == 'drone_status':
                    # Update info about other drones
                    drone_id = data.get('drone_id')
                    if drone_id and drone_id != self.drone_id:
                        if drone_id not in self.other_drones:
                            self.other_drones[drone_id] = {}
                        
                        # Update drone info
                        self.other_drones[drone_id].update(data)
                
                elif msg_type == 'violation_detected':
                    # Another drone detected a violation
                    violation = data.get('violation')
                    if violation:
                        await self.handle_violation(violation)
                
                elif msg_type == 'pursuit_started':
                    # Another drone started pursuit
                    pursuing_drone = data.get('drone_id')
                    
                    # If we're also pursuing the same frequency, check if we should continue
                    if self.current_mode == 'PURSUIT' and self.pursuit_frequency:
                        other_freq = data.get('violation', {}).get('frequency')
                        
                        if other_freq and abs(other_freq - self.pursuit_frequency) < 10000:  # Within 10 kHz
                            # Check distance to target
                            our_pos = (
                                self.vehicle.location.global_frame.lat,
                                self.vehicle.location.global_frame.lon
                            )
                            
                            our_distance = haversine(our_pos, self.pursuit_target, unit='m')
                            
                            # Get other drone position
                            if pursuing_drone in self.other_drones and 'location' in self.other_drones[pursuing_drone]:
                                other_pos = (
                                    self.other_drones[pursuing_drone]['location']['latitude'],
                                    self.other_drones[pursuing_drone]['location']['longitude']
                                )
                                
                                other_target = (
                                    data.get('violation', {}).get('location', {}).get('latitude'),
                                    data.get('violation', {}).get('location', {}).get('longitude')
                                )
                                
                                if all(other_target):
                                    other_distance = haversine(other_pos, other_target, unit='m')
                                    
                                    # If other drone is closer, let them pursue and we go back to patrol
                                    if other_distance < our_distance:
                                        logger.info(f"Drone {pursuing_drone} is closer to target. Resuming patrol.")
                                        self.current_mode = 'PATROL'
                                        self.pursuit_target = None
                                        self.pursuit_frequency = None
                                        
                                        # Resume patrol
                                        await self.start_patrol()
                
                elif msg_type == 'patrol_zone_update':
                    # Update to patrol zones
                    zones = data.get('zones', [])
                    if zones:
                        # Clear existing zones
                        self.patrol_zones = []
                        
                        # Add new zones
                        for zone_data in zones:
                            zone = PatrolZone(
                                name=zone_data['name'],
                                boundaries=zone_data['boundaries'],
                                altitude_range=zone_data.get('altitude_range', self.config['patrol']['altitude_range']),
                                priority=zone_data.get('priority', 1)
                            )
                            
                            # Add hotspots if provided
                            for hotspot in zone_data.get('hotspots', []):
                                zone.add_hotspot(hotspot[0], hotspot[1], hotspot[2])
                            
                            self.patrol_zones.append(zone)
                        
                        # Sort zones by priority
                        self.patrol_zones.sort(key=lambda z: z.priority, reverse=True)
                        
                        if self.patrol_zones:
                            self.current_zone = self.patrol_zones[0]
                            logger.info(f"Updated patrol zones. Primary zone: {self.current_zone.name}")
                            
                            # Regenerate patrol route if in patrol mode
                            if self.current_mode == 'PATROL':
                                await self.generate_patrol_route()
        
        except websockets.exceptions.ConnectionClosed:
            logger.error("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Error receiving messages: {e}")
    
    async def handle_command(self, command):
        """Handle commands from control station"""
        cmd_type = command.get('command')
        
        if cmd_type == 'takeoff':
            altitude = command.get('altitude', self.config['patrol']['default_altitude'])
            await self.takeoff(altitude)
        
        elif cmd_type == 'start_patrol':
            # Set patrol mode if provided
            if 'patrol_mode' in command:
                mode = command['patrol_mode']
                if mode in PATROL_MODES:
                    self.patrol_mode = mode
            
            # Set patrol zone if provided
            if 'zone_name' in command:
                zone_name = command['zone_name']
                for zone in self.patrol_zones:
                    if zone.name == zone_name:
                        self.current_zone = zone
                        break
            
            await self.start_patrol()
        
        elif cmd_type == 'stop_patrol':
            self.current_mode = 'STANDBY'
            logger.info("Patrol stopped by command")
        
        elif cmd_type == 'change_zone':
            zone_name = command.get('zone_name')
            if zone_name:
                for zone in self.patrol_zones:
                    if zone.name == zone_name:
                        self.current_zone = zone
                        logger.info(f"Changed patrol zone to {zone_name}")
                        
                        # Regenerate patrol route if in patrol mode
                        if self.current_mode == 'PATROL':
                            await self.generate_patrol_route()
                        
                        break
        
        elif cmd_type == 'change_patrol_mode':
            mode = command.get('mode')
            if mode in PATROL_MODES:
                self.patrol_mode = mode
                logger.info(f"Changed patrol mode to {mode}")
                
                # Regenerate patrol route if in patrol mode
                if self.current_mode == 'PATROL':
                    await self.generate_patrol_route()
        
        elif cmd_type == 'goto':
            lat = command.get('latitude')
            lon = command.get('longitude')
            alt = command.get('altitude', self.vehicle.location.global_relative_frame.alt)
            
            if lat and lon:
                logger.info(f"Moving to specified location: {lat}, {lon}, {alt}")
                target = LocationGlobalRelative(lat, lon, alt)
                self.vehicle.simple_goto(target)
        
        elif cmd_type == 'return_home':
            await self.return_to_home()
        
        elif cmd_type == 'land':
            logger.info("Landing by command")
            self.vehicle.mode = VehicleMode("LAND")
    
    async def return_to_home(self):
        """Return drone to home location"""
        logger.info("Returning to home location")
        
        self.current_mode = 'RETURNING'
        
        try:
            # Get home location
            home = self.config['home_location']
            
            # Set to moderate speed
            self.vehicle.airspeed = self.config['patrol'].get('patrol_speed', 5)
            
            # Move to home location
            target = LocationGlobalRelative(home[0], home[1], home[2])
            self.vehicle.simple_goto(target)
            
            # Notify visualization
            if self.websocket:
                return_msg = {
                    "type": "returning_home",
                    "drone_id": self.drone_id,
                    "home_location": {
                        "latitude": home[0],
                        "longitude": home[1],
                        "altitude": home[2]
                    },
                    "timestamp": time.time()
                }
                await self.websocket.send(json.dumps(return_msg))
            
            # Track progress
            start_time = time.time()
            timeout = 300  # 5 minutes max
            arrived = False
            
            while not arrived and time.time() - start_time < timeout:
                # Check distance to home
                current_loc = (
                    self.vehicle.location.global_frame.lat,
                    self.vehicle.location.global_frame.lon
                )
                
                distance = haversine(current_loc, (home[0], home[1]), unit='m')
                
                if distance < 10:  # Within 10m
                    arrived = True
                    logger.info("Arrived at home location")
                    break
                
                # Check for collision risks
                await self.check_collision_risks()
                
                await asyncio.sleep(2)
            
            # Land
            logger.info("Landing at home location")
            self.vehicle.mode = VehicleMode("LAND")
            
            # Wait for landing
            while self.vehicle.location.global_relative_frame.alt > 0.5:
                await asyncio.sleep(1)
            
            logger.info("Landed successfully")
            self.current_mode = 'STANDBY'
            
        except Exception as e:
            logger.error(f"Error returning to home: {e}")
            self.current_mode = 'STANDBY'
    
    async def run(self):
        """Main execution loop"""
        # Connect to drone
        connected = await self.connect_drone()
        if not connected:
            logger.error("Failed to connect to drone. Exiting.")
            return
        
        # Connect to websocket server
        ws_connected = await self.connect_websocket()
        if not ws_connected:
            logger.warning("Failed to connect to WebSocket. Continuing without server communication.")
        
        # Start message receiver if websocket is connected
        if ws_connected:
            receiver_task = asyncio.create_task(self.receive_messages())
        
        # Main status loop
        try:
            while True:
                # Send status updates
                if ws_connected:
                    await self.send_status_update()
                
                # If in standby, wait for commands
                if self.current_mode == 'STANDBY':
                    logger.info("Drone in standby mode. Waiting for commands.")
                    await asyncio.sleep(5)
                
                await asyncio.sleep(1)
        
        except asyncio.CancelledError:
            logger.info("Drone patrol controller task cancelled")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            # Clean up
            if self.vehicle:
                self.vehicle.close()
            if self.websocket:
                await self.websocket.close()

async def main():
    """Entry point for drone patrol controller"""
    controller = DronePatrolController()
    await controller.run()

if __name__ == "__main__":
    asyncio.run(main())
