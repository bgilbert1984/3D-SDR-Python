import asyncio
import numpy as np
import websockets
import json
import time
import os
import logging
import math
from scipy.optimize import minimize
from haversine import haversine
from dronekit import connect, VehicleMode, LocationGlobalRelative, LocationGlobal
import tensorflow as tf
from pymavlink import mavutil

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('drone_swarm_controller')

# Constants
SPEED_OF_LIGHT = 299792458  # m/s
MIN_SEPARATION_DISTANCE = 15  # meters
SAFE_ALTITUDE_STEP = 10  # meters to adjust for collision avoidance
PURSUIT_ROLES = ['LEAD', 'TRIANGULATION', 'BACKUP', 'SCOUT']

# Standard SDR frequency bands for scanning
FREQUENCY_BANDS = [
    (88e6, 108e6),   # FM broadcast
    (144e6, 148e6),  # 2m amateur
    (430e6, 440e6),  # 70cm amateur
    (450e6, 470e6)   # UHF band
]

class SwarmSDRManager:
    """Manages SDR frequency coordination across the drone swarm"""
    
    def __init__(self, swarm_controller):
        self.swarm_controller = swarm_controller
        self.devices = {}
        self.active_frequencies = {}
        self.scan_results = {}
        logger.info("SwarmSDRManager initialized")

    async def assign_frequency_bands(self):
        """Assign different frequency bands to different drones based on their capabilities and positions"""
        active_drones = list(self.swarm_controller.other_drones.keys()) + [self.swarm_controller.drone_id]
        
        # Sort drones by ID to ensure consistent assignment across swarm
        active_drones.sort()
        
        for i, drone_id in enumerate(active_drones):
            band_index = i % len(FREQUENCY_BANDS)
            band = FREQUENCY_BANDS[band_index]
            self.active_frequencies[drone_id] = band
            
            if drone_id == self.swarm_controller.drone_id:
                # Update our SDR configuration
                self.swarm_controller.config['sdr_parameters'].update({
                    'center_freq': (band[0] + band[1]) / 2,  # Center of the band
                    'sample_rate': min(2.4e6, band[1] - band[0]),  # Bandwidth up to 2.4MHz
                })
        
        logger.info(f"Assigned frequency band {self.active_frequencies[self.swarm_controller.drone_id]} to drone {self.swarm_controller.drone_id}")
        
        # Notify other drones of the assignment
        if self.swarm_controller.websocket:
            assignment_msg = {
                'type': 'frequency_band_assignment',
                'assignments': self.active_frequencies,
                'timestamp': time.time()
            }
            await self.swarm_controller.websocket.send(json.dumps(assignment_msg))

    async def process_scan_results(self, results, frequency_band):
        """Process scan results from a specific frequency band"""
        drone_id = self.swarm_controller.drone_id
        self.scan_results[drone_id] = {
            'band': frequency_band,
            'results': results,
            'timestamp': time.time()
        }
        
        # Share results with swarm if significant signals found
        if any(r.get('is_violation', False) for r in results):
            await self.share_scan_results(results)

    async def share_scan_results(self, results):
        """Share significant scan results with the swarm"""
        if not self.swarm_controller.websocket:
            return
            
        scan_msg = {
            'type': 'sdr_scan_results',
            'drone_id': self.swarm_controller.drone_id,
            'frequency_band': self.active_frequencies[self.swarm_controller.drone_id],
            'results': results,
            'timestamp': time.time()
        }
        await self.swarm_controller.websocket.send(json.dumps(scan_msg))

class DroneSwarmController:
    """
    Main controller for SDR-equipped drone swarms with collision avoidance
    and collaborative signal pursuit capabilities
    """
    
    def __init__(self, config_file='drone_config.json'):
        """Initialize the drone swarm controller with configuration"""
        self.config = self._load_config(config_file)
        self.vehicle = None
        self.sdr_data = {}
        self.target_location = None
        self.pursuit_model = None
        self.signal_classifier = None
        self.is_pursuing = False
        self.other_drones = {}  # Data about other drones in the swarm
        self.drone_id = self.config['drone_id']
        self.websocket = None
        self.is_lead = False  # Whether this drone is the lead pursuer
        self.role = 'UNASSIGNED'  # Current role in the swarm
        self.swarm_positions = {}  # Last known positions of all drones
        self.collision_risks = {}  # Current collision risks with other drones
        self.evasive_maneuver = False  # Whether drone is currently avoiding collision
        self.target_frequency = None  # Frequency being pursued
        self.last_position_share = 0  # Timestamp of last position sharing
        self.formation_position = None  # Target position in formation
        self.swarm_leader_id = None  # ID of the current swarm leader
        self.sdr_manager = SwarmSDRManager(self)  # Initialize SDR manager
        logger.info(f"Drone {self.drone_id} swarm controller initialized")
    
    def _load_config(self, config_file):
        """Load configuration from JSON file"""
        if not os.path.exists(config_file):
            # Default configuration
            config = {
                'drone_id': 'drone1',
                'connection_string': 'udp:127.0.0.1:14550',
                'websocket_url': 'ws://localhost:8766',
                'pursuit_model_path': 'models/pursuit_model.h5',
                'signal_classifier_path': 'models/signal_classifier.pkl',
                'flight_parameters': {
                    'altitude': 100,
                    'speed': 10,
                    'max_distance': 2000,
                    'home_location': [37.7749, -122.4194, 0]
                },
                'sdr_parameters': {
                    'center_freq': 100e6,
                    'sample_rate': 2.048e6,
                    'gain': 20
                },
                'swarm_parameters': {
                    'min_separation': MIN_SEPARATION_DISTANCE,
                    'position_share_interval': 1.0,  # seconds
                    'default_role': 'BACKUP',
                    'formation_radius': 100  # meters
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
            
            # Arm and get ready for takeoff
            self.vehicle.mode = VehicleMode("GUIDED")
            logger.info("Drone ready for flight")
            return True
        except Exception as e:
            logger.error(f"Error connecting to drone: {e}")
            return False

    async def takeoff(self, target_altitude=None):
        """Arm and takeoff to target altitude"""
        if target_altitude is None:
            target_altitude = self.config['flight_parameters']['altitude']
        
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

    async def load_models(self):
        """Load AI models for signal classification and pursuit prediction"""
        try:
            # Load pursuit model (LSTM or other ML model)
            if os.path.exists(self.config['pursuit_model_path']):
                logger.info(f"Loading pursuit model from: {self.config['pursuit_model_path']}")
                self.pursuit_model = tf.keras.models.load_model(self.config['pursuit_model_path'])
            else:
                logger.warning(f"Pursuit model not found at: {self.config['pursuit_model_path']}")
            
            # Load signal classifier (could be sklearn or other model)
            if os.path.exists(self.config['signal_classifier_path']):
                logger.info(f"Loading signal classifier from: {self.config['signal_classifier_path']}")
                import joblib
                self.signal_classifier = joblib.load(self.config['signal_classifier_path'])
            else:
                logger.warning(f"Signal classifier not found at: {self.config['signal_classifier_path']}")
            
            return True
        except Exception as e:
            logger.error(f"Error loading models: {e}")
            return False

    async def connect_websocket(self):
        """Connect to the WebSocket server for swarm coordination and SDR data"""
        try:
            logger.info(f"Connecting to WebSocket at: {self.config['websocket_url']}")
            self.websocket = await websockets.connect(self.config['websocket_url'])
            logger.info("Connected to WebSocket server")
            
            # Register with the server
            registration = {
                "type": "drone_registration",
                "drone_id": self.drone_id,
                "capabilities": {
                    "sdr_enabled": True,
                    "max_altitude": self.config['flight_parameters']['altitude'],
                    "max_speed": self.config['flight_parameters']['speed'],
                    "battery_level": 100,  # Start with full battery
                    "tdoa_capable": True
                }
            }
            
            await self.websocket.send(json.dumps(registration))
            logger.info(f"Registered drone {self.drone_id} with server")
            
            return True
        except Exception as e:
            logger.error(f"WebSocket connection error: {e}")
            return False

    async def send_status_update(self):
        """Send drone status to the WebSocket server"""
        if not self.websocket:
            return
        
        try:
            location = self.vehicle.location.global_frame
            status = {
                'type': 'drone_status',
                'drone_id': self.drone_id,
                'timestamp': time.time(),
                'location': {
                    'latitude': location.lat,
                    'longitude': location.lon,
                    'altitude': location.alt
                },
                'battery': self.vehicle.battery.level if hasattr(self.vehicle, 'battery') else 100,
                'is_pursuing': self.is_pursuing,
                'target_location': self.target_location,
                'role': self.role,
                'is_lead': self.is_lead,
                'target_frequency': self.target_frequency,
                'evasive_maneuver': self.evasive_maneuver,
                'assigned_band': self.sdr_manager.active_frequencies.get(self.drone_id)  # Add frequency band info
            }
            
            await self.websocket.send(json.dumps(status))
        except Exception as e:
            logger.error(f"Error sending status update: {e}")

    async def share_position(self):
        """Broadcast this drone's position to other drones for collision avoidance"""
        now = time.time()
        
        # Check if we need to share position based on interval
        if now - self.last_position_share < self.config['swarm_parameters'].get('position_share_interval', 1.0):
            return
        
        if not self.websocket or not self.vehicle:
            return
        
        try:
            location = self.vehicle.location.global_frame
            velocity = self.vehicle.velocity if hasattr(self.vehicle, 'velocity') else [0, 0, 0]
            position_data = {
                'type': 'drone_position',
                'drone_id': self.drone_id,
                'timestamp': now,
                'location': {
                    'latitude': location.lat,
                    'longitude': location.lon,
                    'altitude': location.alt
                },
                'velocity': {
                    'x': velocity[0],
                    'y': velocity[1],
                    'z': velocity[2]
                },
                'heading': self.vehicle.heading if hasattr(self.vehicle, 'heading') else 0
            }
            
            await self.websocket.send(json.dumps(position_data))
            self.last_position_share = now
        except Exception as e:
            logger.error(f"Error sharing position: {e}")

    async def process_sdr_data(self, data):
        """Process incoming SDR data"""
        try:
            freq = data.get('freq', 0)
            rssi = data.get('rssi', 0)
            tdoa = data.get('tdoa', 0)
            predicted_location = data.get('predicted_location', [0, 0, 0])
            
            # Check if frequency is in our assigned band
            our_band = self.sdr_manager.active_frequencies.get(self.drone_id)
            if our_band and not (our_band[0] <= freq <= our_band[1]):
                logger.debug(f"Ignoring signal at {freq} Hz - outside our assigned band {our_band}")
                return
            
            # Store SDR data for this frequency
            self.sdr_data[freq] = {
                'rssi': rssi,
                'tdoa': tdoa,
                'predicted_location': predicted_location,
                'timestamp': time.time()
            }
            
            # Process scan results through SDR manager
            await self.sdr_manager.process_scan_results([{
                'frequency': freq,
                'rssi': rssi,
                'is_violation': data.get('is_violation', False),
                'predicted_location': predicted_location
            }], our_band)
            
            # If we're not already pursuing and this is a violation, start pursuit
            if not self.is_pursuing and data.get('is_violation', False):
                logger.info(f"Potential target at {freq} MHz. Checking with swarm...")
                
                # Notify swarm about potential violation
                violation_data = {
                    'type': 'violation_detected',
                    'drone_id': self.drone_id,
                    'frequency': freq,
                    'rssi': rssi,
                    'tdoa': tdoa,
                    'predicted_location': predicted_location,
                    'timestamp': time.time()
                }
                
                await self.websocket.send(json.dumps(violation_data))
                
                # Wait for leader election to complete before starting pursuit
                await self.elect_swarm_leader(freq)
        except Exception as e:
            logger.error(f"Error processing SDR data: {e}")

    async def elect_swarm_leader(self, frequency):
        """
        Participate in swarm leader election to determine which drone
        will lead the pursuit and assign roles to other drones
        """
        if not self.other_drones:
            # If we're alone, we're the leader
            self.is_lead = True
            self.role = 'LEAD'
            self.target_frequency = frequency
            logger.info(f"Drone {self.drone_id} is the only drone - automatically becoming lead pursuer")
            await self.start_pursuit(frequency)
            return
        
        # Collect information about all drones
        all_drones = list(self.other_drones.items()) + [(self.drone_id, {
            'location': {
                'latitude': self.vehicle.location.global_frame.lat,
                'longitude': self.vehicle.location.global_frame.lon,
                'altitude': self.vehicle.location.global_frame.alt
            },
            'rssi': self.sdr_data.get(frequency, {}).get('rssi', -100),
            'battery': self.vehicle.battery.level if hasattr(self.vehicle, 'battery') else 100
        })]
        
        # Sort by signal strength (RSSI), then by battery level
        all_drones.sort(key=lambda d: (-d[1].get('rssi', -100), -d[1].get('battery', 0)))
        
        # Select leader (drone with strongest signal and highest battery)
        leader_id = all_drones[0][0]
        self.swarm_leader_id = leader_id
        
        # Determine if this drone is the leader
        self.is_lead = (leader_id == self.drone_id)
        
        # Assign roles based on position in the sorted list
        if self.is_lead:
            self.role = 'LEAD'
            logger.info(f"Drone {self.drone_id} elected as lead pursuer for frequency {frequency} MHz")
            
            # Send role assignments to all drones
            assignments = []
            for i, (drone_id, _) in enumerate(all_drones):
                role = PURSUIT_ROLES[min(i, len(PURSUIT_ROLES) - 1)]
                if drone_id != self.drone_id:  # Skip self in assignments
                    assignments.append({
                        'drone_id': drone_id,
                        'role': role
                    })
            
            # Send role assignments to all drones
            role_message = {
                'type': 'swarm_roles',
                'leader_id': self.drone_id,
                'frequency': frequency,
                'assignments': assignments,
                'timestamp': time.time()
            }
            
            await self.websocket.send(json.dumps(role_message))
            await self.start_pursuit(frequency)
        else:
            # Wait for role assignment from leader
            logger.info(f"Drone {self.drone_id} waiting for role assignment from leader {leader_id}")

    async def set_role(self, role, frequency):
        """Set this drone's role in the swarm and begin appropriate behavior"""
        self.role = role
        self.target_frequency = frequency
        logger.info(f"Drone {self.drone_id} assigned role: {role} for frequency {frequency} MHz")
        
        # Start appropriate behavior based on role
        if role == 'LEAD':
            self.is_lead = True
            await self.start_pursuit(frequency)
        elif role == 'TRIANGULATION':
            self.is_lead = False
            await self.start_triangulation(frequency)
        elif role == 'BACKUP':
            self.is_lead = False
            await self.start_backup_role(frequency)
        elif role == 'SCOUT':
            self.is_lead = False
            await self.start_scout_role(frequency)

    async def start_pursuit(self, freq):
        """Start active pursuit as the lead drone"""
        # Begin the pursuit
        self.is_pursuing = True
        self.target_frequency = freq
        logger.info(f"Starting pursuit of signal at {freq} MHz as LEAD")
        
        # Launch pursuit task
        asyncio.create_task(self.pursue_signal(freq))
    
    async def start_triangulation(self, freq):
        """
        Start triangulation role - position drone to optimize
        geolocation accuracy by maintaining orthogonal angles
        """
        self.is_pursuing = True
        self.target_frequency = freq
        logger.info(f"Starting triangulation role for {freq} MHz")
        
        # Start triangulation task
        asyncio.create_task(self.triangulation_behavior(freq))
    
    async def start_backup_role(self, freq):
        """
        Start backup role - follow lead drone but maintain distance
        and be ready to take over if lead drone needs to return
        """
        self.is_pursuing = True
        self.target_frequency = freq
        logger.info(f"Starting backup role for {freq} MHz")
        
        # Start backup task
        asyncio.create_task(self.backup_behavior(freq))
    
    async def start_scout_role(self, freq):
        """
        Start scout role - conduct wider search patterns to look
        for better signal reception or detect transmitter movement
        """
        self.is_pursuing = True
        self.target_frequency = freq
        logger.info(f"Starting scout role for {freq} MHz")
        
        # Start scout task
        asyncio.create_task(self.scout_behavior(freq))

    async def triangulation_behavior(self, freq):
        """
        Triangulation drone behavior - position for optimal TDoA/RSSI
        measurement by forming an angle with the lead drone
        """
        try:
            logger.info(f"Triangulation behavior active for {freq} MHz")
            
            while self.is_pursuing and self.role == 'TRIANGULATION':
                # Find the lead drone
                lead_drone = None
                for drone_id, data in self.other_drones.items():
                    if data.get('is_lead', False):
                        lead_drone = data
                        lead_drone['id'] = drone_id
                        break
                
                if not lead_drone:
                    logger.warning("No lead drone found. Waiting...")
                    await asyncio.sleep(2)
                    continue
                
                # Get target and lead drone positions
                target_location = None
                if self.target_location:
                    target_location = self.target_location
                elif lead_drone.get('target_location'):
                    target_location = lead_drone.get('target_location')
                
                if not target_location:
                    logger.warning("No target location available. Waiting...")
                    await asyncio.sleep(2)
                    continue
                
                # Calculate optimal position for triangulation (90° angle from lead to target)
                lead_pos = (
                    lead_drone['location']['latitude'],
                    lead_drone['location']['longitude']
                )
                
                target_pos = (target_location[0], target_location[1])
                
                # Calculate formation position (perpendicular to lead-target line)
                formation_position = self.calculate_triangulation_position(
                    lead_pos, target_pos, self.config['swarm_parameters'].get('formation_radius', 100)
                )
                
                # Move to formation position
                logger.info(f"Moving to triangulation position: {formation_position}")
                target_alt = self.vehicle.location.global_relative_frame.alt
                target = LocationGlobalRelative(
                    formation_position[0],
                    formation_position[1],
                    target_alt
                )
                
                self.vehicle.simple_goto(target)
                
                # Check for collision risks while moving
                await self.detect_collision_risk()
                
                # Update formation position
                self.formation_position = formation_position
                
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error(f"Error in triangulation behavior: {e}")
        finally:
            logger.info("Triangulation behavior ended")

    async def backup_behavior(self, freq):
        """
        Backup drone behavior - follow behind lead drone at a safe distance
        ready to take over pursuit if needed
        """
        try:
            logger.info(f"Backup behavior active for {freq} MHz")
            
            while self.is_pursuing and self.role == 'BACKUP':
                # Find the lead drone
                lead_drone = None
                for drone_id, data in self.other_drones.items():
                    if data.get('is_lead', False):
                        lead_drone = data
                        lead_drone['id'] = drone_id
                        break
                
                if not lead_drone:
                    logger.warning("No lead drone found. Waiting...")
                    await asyncio.sleep(2)
                    continue
                
                # Calculate position behind lead drone
                lead_pos = (
                    lead_drone['location']['latitude'],
                    lead_drone['location']['longitude']
                )
                
                # If lead has a heading, use it to position behind
                heading = lead_drone.get('heading', 0)
                
                # Calculate position behind lead drone in its direction of travel
                formation_position = self.calculate_backup_position(
                    lead_pos, heading, self.config['swarm_parameters'].get('formation_radius', 100) * 0.75
                )
                
                # Move to formation position
                logger.info(f"Moving to backup position: {formation_position}")
                target_alt = self.vehicle.location.global_relative_frame.alt
                target = LocationGlobalRelative(
                    formation_position[0],
                    formation_position[1],
                    target_alt
                )
                
                self.vehicle.simple_goto(target)
                
                # Check for collision risks while moving
                await self.detect_collision_risk()
                
                # Update formation position
                self.formation_position = formation_position
                
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error(f"Error in backup behavior: {e}")
        finally:
            logger.info("Backup behavior ended")

    async def scout_behavior(self, freq):
        """
        Scout drone behavior - search in expanding circles around
        the suspected transmitter location to look for stronger signals
        """
        try:
            logger.info(f"Scout behavior active for {freq} MHz")
            
            # Scout parameters
            search_radius = 200  # meters
            altitude_offset = 20  # meters above lead drone
            circle_points = 8    # number of points on search circle
            
            while self.is_pursuing and self.role == 'SCOUT':
                # Find the lead drone and target
                lead_drone = None
                for drone_id, data in self.other_drones.items():
                    if data.get('is_lead', False):
                        lead_drone = data
                        lead_drone['id'] = drone_id
                        break
                
                # Get target position
                target_location = None
                if self.target_location:
                    target_location = self.target_location
                elif lead_drone and lead_drone.get('target_location'):
                    target_location = lead_drone.get('target_location')
                
                if not target_location:
                    logger.warning("No target location available. Waiting...")
                    await asyncio.sleep(2)
                    continue
                
                # Calculate search pattern positions
                target_pos = (target_location[0], target_location[1])
                
                # Use a time-based angle to create a circular search pattern
                angle = (time.time() % 360) * (2 * math.pi / 360)
                
                # Calculate position on search circle
                formation_position = self.calculate_scout_position(
                    target_pos, angle, search_radius
                )
                
                # Move to search position with altitude offset
                logger.info(f"Moving to scout position: {formation_position}")
                base_alt = self.vehicle.location.global_relative_frame.alt
                if lead_drone:
                    base_alt = lead_drone['location'].get('altitude', base_alt)
                
                target_alt = base_alt + altitude_offset
                target = LocationGlobalRelative(
                    formation_position[0],
                    formation_position[1],
                    target_alt
                )
                
                self.vehicle.simple_goto(target)
                
                # Check for collision risks while moving
                await self.detect_collision_risk()
                
                # Update formation position
                self.formation_position = formation_position
                
                # Share any strong signal measurements
                if freq in self.sdr_data and self.sdr_data[freq]['rssi'] > -60:
                    signal_data = {
                        'type': 'scout_signal',
                        'drone_id': self.drone_id,
                        'frequency': freq,
                        'rssi': self.sdr_data[freq]['rssi'],
                        'location': {
                            'latitude': self.vehicle.location.global_frame.lat,
                            'longitude': self.vehicle.location.global_frame.lon,
                            'altitude': self.vehicle.location.global_frame.alt
                        },
                        'timestamp': time.time()
                    }
                    
                    await self.websocket.send(json.dumps(signal_data))
                    logger.info(f"Shared strong signal measurement: RSSI = {self.sdr_data[freq]['rssi']}")
                
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error(f"Error in scout behavior: {e}")
        finally:
            logger.info("Scout behavior ended")

    def calculate_triangulation_position(self, lead_pos, target_pos, distance):
        """
        Calculate optimal position for triangulation - 90° from lead-target line
        
        Args:
            lead_pos: (lat, lon) of lead drone
            target_pos: (lat, lon) of target
            distance: desired distance from target in meters
        
        Returns:
            (lat, lon) position for triangulation
        """
        # Calculate bearing from target to lead
        lat1, lon1 = target_pos
        lat2, lon2 = lead_pos
        
        # Convert to radians
        lat1 = math.radians(lat1)
        lon1 = math.radians(lon1)
        lat2 = math.radians(lat2)
        lon2 = math.radians(lon2)
        
        # Calculate bearing
        y = math.sin(lon2 - lon1) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
        bearing = math.atan2(y, x)
        
        # Add 90° to get perpendicular bearing
        bearing_perp = bearing + (math.pi / 2)
        
        # Calculate position at that bearing and distance
        lat_perp, lon_perp = self.calculate_position_at_bearing(
            target_pos[0], target_pos[1], bearing_perp, distance
        )
        
        return (lat_perp, lon_perp)

    def calculate_backup_position(self, lead_pos, heading, distance):
        """
        Calculate position behind lead drone based on its heading
        
        Args:
            lead_pos: (lat, lon) of lead drone
            heading: heading of lead drone in degrees
            distance: desired distance behind lead drone in meters
        
        Returns:
            (lat, lon) position for backup drone
        """
        # Convert heading to opposite direction (behind lead)
        opposite_bearing = math.radians((heading + 180) % 360)
        
        # Calculate position at opposite bearing
        lat, lon = self.calculate_position_at_bearing(
            lead_pos[0], lead_pos[1], opposite_bearing, distance
        )
        
        return (lat, lon)

    def calculate_scout_position(self, target_pos, angle, radius):
        """
        Calculate position for scout drone on a circle around target
        
        Args:
            target_pos: (lat, lon) of target
            angle: angle in radians for position on circle
            radius: radius of search circle in meters
        
        Returns:
            (lat, lon) position for scout drone
        """
        # Calculate position at given angle on circle
        lat, lon = self.calculate_position_at_bearing(
            target_pos[0], target_pos[1], angle, radius
        )
        
        return (lat, lon)

    def calculate_position_at_bearing(self, lat, lon, bearing, distance):
        """
        Calculate new position given starting position, bearing and distance
        
        Args:
            lat, lon: Starting point in degrees
            bearing: Bearing in radians
            distance: Distance in meters
        
        Returns:
            (latitude, longitude) of new position in degrees
        """
        # Earth's radius in meters
        R = 6371000
        
        # Convert to radians
        lat_rad = math.radians(lat)
        lon_rad = math.radians(lon)
        
        # Calculate new lat/lon
        new_lat = math.asin(
            math.sin(lat_rad) * math.cos(distance / R) +
            math.cos(lat_rad) * math.sin(distance / R) * math.cos(bearing)
        )
        
        new_lon = lon_rad + math.atan2(
            math.sin(bearing) * math.sin(distance / R) * math.cos(lat_rad),
            math.cos(distance / R) - math.sin(lat_rad) * math.sin(new_lat)
        )
        
        # Convert back to degrees
        new_lat = math.degrees(new_lat)
        new_lon = math.degrees(new_lon)
        
        return (new_lat, new_lon)

    async def adjust_position_for_triangulation(self, freq):
        """
        Adjust drone position to improve triangulation accuracy
        This uses the signal strength to find better positions
        """
        if not self.sdr_data.get(freq):
            return
        
        try:
            current_rssi = self.sdr_data[freq]['rssi']
            
            # Simple algorithm: move in different directions and measure RSSI improvements
            directions = [
                (0.0001, 0, 0),  # North
                (-0.0001, 0, 0), # South
                (0, 0.0001, 0),  # East
                (0, -0.0001, 0),  # West
                (0, 0, 10),      # Up
                (0, 0, -10)      # Down
            ]
            
            best_direction = None
            best_improvement = 0
            
            current_location = self.vehicle.location.global_frame
            
            for direction in directions:
                # Try moving in this direction
                target = LocationGlobalRelative(
                    current_location.lat + direction[0],
                    current_location.lon + direction[1],
                    self.vehicle.location.global_relative_frame.alt + direction[2]
                )
                
                # Ensure altitude stays positive and within limits
                if target.alt < 10:
                    target.alt = 10
                elif target.alt > 120:
                    target.alt = 120
                
                # Move to the test position
                self.vehicle.simple_goto(target)
                await asyncio.sleep(3)  # Wait for movement and measurement
                
                # Get new RSSI
                new_rssi = self.sdr_data[freq]['rssi']
                improvement = abs(new_rssi) - abs(current_rssi)  # Lower absolute value is better
                
                if improvement > best_improvement:
                    best_improvement = improvement
                    best_direction = direction
            
            # If we found a better direction, move there permanently
            if best_direction:
                logger.info(f"Found better position for triangulation. Moving {best_direction}")
                target = LocationGlobalRelative(
                    current_location.lat + best_direction[0],
                    current_location.lon + best_direction[1],
                    self.vehicle.location.global_relative_frame.alt + best_direction[2]
                )
                self.vehicle.simple_goto(target)
                await asyncio.sleep(5)  # Allow time to reach the position
        except Exception as e:
            logger.error(f"Error adjusting position: {e}")

    async def pursue_signal(self, freq):
        """
        Actively pursue a signal transmitter as the lead drone
        Uses AI to predict transmitter movement if model is available
        """
        logger.info(f"Beginning signal pursuit for {freq} MHz as lead drone")
        
        try:
            while self.is_pursuing and self.role == 'LEAD':
                # Get latest location data
                if not self.sdr_data.get(freq):
                    logger.warning(f"No data for frequency {freq}")
                    await asyncio.sleep(1)
                    continue
                
                data = self.sdr_data[freq]
                predicted_location = data['predicted_location']
                
                # If we have the pursuit model, use it to predict movement
                if self.pursuit_model:
                    # Prepare features for the model
                    features = np.array([[
                        data['rssi'],
                        data['tdoa'],
                        predicted_location[0],
                        predicted_location[1],
                        predicted_location[2]
                    ]])
                    
                    # Reshape for LSTM if needed
                    if len(self.pursuit_model.input_shape) > 2:
                        features = features.reshape(1, 1, features.shape[1])
                    
                    # Predict next move
                    prediction = self.pursuit_model.predict(features)
                    
                    # If the model outputs movement directions
                    if isinstance(prediction, np.ndarray) and prediction.shape[1] > 1:
                        move_index = np.argmax(prediction[0])
                        moves = ["FORWARD", "LEFT", "RIGHT", "UP", "DOWN"]
                        move = moves[move_index] if move_index < len(moves) else "FORWARD"
                        logger.info(f"AI predicts target will move: {move}")
                        
                        # Adjust target location based on predicted movement
                        if move == "FORWARD":
                            predicted_location[0] += 0.0001
                        elif move == "LEFT":
                            predicted_location[1] -= 0.0001
                        elif move == "RIGHT":
                            predicted_location[1] += 0.0001
                        elif move == "UP":
                            predicted_location[2] += 10
                        elif move == "DOWN":
                            predicted_location[2] -= 10
                
                # Update target location
                self.target_location = predicted_location
                
                # Move toward the target
                target = LocationGlobalRelative(
                    predicted_location[0],
                    predicted_location[1],
                    max(10, min(120, predicted_location[2]))  # Clamp altitude
                )
                
                logger.info(f"Moving to target location: {target.lat}, {target.lon}, {target.alt}")
                self.vehicle.simple_goto(target)
                
                # Share our status with the swarm
                await self.send_status_update()
                
                # Check for collision risks before moving
                await self.detect_collision_risk()
                
                # Check if we've reached the target
                current_location = (
                    self.vehicle.location.global_frame.lat,
                    self.vehicle.location.global_frame.lon,
                    self.vehicle.location.global_frame.alt
                )
                target_location = (predicted_location[0], predicted_location[1], predicted_location[2])
                
                # Calculate distance
                horizontal_distance = haversine(
                    (current_location[0], current_location[1]),
                    (target_location[0], target_location[1]),
                    unit='m'
                )
                vertical_distance = abs(current_location[2] - target_location[2])
                
                logger.info(f"Distance to target: {horizontal_distance}m horizontal, {vertical_distance}m vertical")
                
                # If we're close enough, try to improve triangulation
                if horizontal_distance < 50 and vertical_distance < 20:
                    logger.info("Reached target location, optimizing position")
                    await self.adjust_position_for_triangulation(freq)
                
                await asyncio.sleep(2)
                
        except Exception as e:
            logger.error(f"Error in signal pursuit: {e}")
        finally:
            self.is_pursuing = False
            logger.info("Signal pursuit ended")

    async def detect_collision_risk(self):
        """Check for nearby drones and adjust course to avoid collisions"""
        if not self.vehicle:
            return
        
        min_separation = self.config['swarm_parameters'].get('min_separation', MIN_SEPARATION_DISTANCE)
        our_position = (
            self.vehicle.location.global_frame.lat,
            self.vehicle.location.global_frame.lon
        )
        
        collision_risks = {}
        
        # Check distance to each drone
        for drone_id, data in self.other_drones.items():
            if 'location' not in data:
                continue
                
            drone_position = (
                data['location']['latitude'],
                data['location']['longitude']
            )
            
            dist = haversine(our_position, drone_position, unit='m')
            
            # Check if this drone is too close
            if dist < min_separation:
                # Store collision risk
                collision_risks[drone_id] = {
                    'distance': dist,
                    'position': drone_position,
                    'altitude': data['location'].get('altitude', self.vehicle.location.global_frame.alt)
                }
                
                logger.warning(f"Collision risk detected with {drone_id}. Distance: {dist:.2f}m")
        
        # Store the current collision risks
        self.collision_risks = collision_risks
        
        # If we have collision risks, avoid them
        if collision_risks:
            await self.avoid_collisions(collision_risks)
    
    async def avoid_collisions(self, collision_risks):
        """
        Execute collision avoidance maneuvers based on detected risks
        Uses a priority-based approach to handle multiple collision risks
        """
        if not collision_risks or not self.vehicle:
            return
            
        # Skip if already in evasive maneuver
        if self.evasive_maneuver:
            return
            
        try:
            # Mark that we're starting evasive maneuvers
            self.evasive_maneuver = True
            
            # Get our current position and altitude
            current_location = self.vehicle.location.global_frame
            current_alt = self.vehicle.location.global_relative_frame.alt
            
            # Determine evasion strategy based on roles and positions
            # Find the closest drone
            closest_drone_id = min(collision_risks.items(), key=lambda x: x[1]['distance'])[0]
            closest_drone = collision_risks[closest_drone_id]
            
            # Get the role of the closest drone
            closest_role = self.other_drones.get(closest_drone_id, {}).get('role', 'UNKNOWN')
            
            # Adjust evasion strategy based on role priority
            role_priority = {
                'LEAD': 3,
                'TRIANGULATION': 2,
                'BACKUP': 1,
                'SCOUT': 0,
                'UNASSIGNED': -1,
                'UNKNOWN': -1
            }
            
            our_priority = role_priority.get(self.role, -1)
            closest_priority = role_priority.get(closest_role, -1)
            
            # Determine who should move
            we_should_adjust = our_priority <= closest_priority
            
            if we_should_adjust:
                logger.info(f"Executing collision avoidance with {closest_drone_id} (our priority: {our_priority}, their priority: {closest_priority})")
                
                # Choose avoidance maneuver: altitude or lateral
                # If altitude difference is significant, move laterally
                alt_diff = abs(current_alt - closest_drone['altitude'])
                
                if alt_diff > SAFE_ALTITUDE_STEP * 0.8:
                    # Move laterally (away from the other drone)
                    our_pos = (current_location.lat, current_location.lon)
                    their_pos = closest_drone['position']
                    
                    # Calculate bearing from their position to ours
                    bearing = self.calculate_bearing(their_pos, our_pos)
                    
                    # Continue in the same direction to move away
                    safe_position = self.calculate_position_at_bearing(
                        current_location.lat,
                        current_location.lon,
                        bearing,
                        MIN_SEPARATION_DISTANCE
                    )
                    
                    logger.info(f"Moving laterally to avoid collision: {safe_position}")
                    target = LocationGlobalRelative(
                        safe_position[0],
                        safe_position[1],
                        current_alt
                    )
                else:
                    # Adjust altitude
                    # If we're higher, move higher; if lower, move lower
                    if current_alt >= closest_drone['altitude']:
                        safe_alt = current_alt + SAFE_ALTITUDE_STEP
                    else:
                        safe_alt = current_alt - SAFE_ALTITUDE_STEP
                        
                    # Ensure altitude is within safe range
                    safe_alt = max(10, min(120, safe_alt))
                    
                    logger.info(f"Adjusting altitude to {safe_alt}m to avoid collision")
                    target = LocationGlobalRelative(
                        current_location.lat,
                        current_location.lon,
                        safe_alt
                    )
                
                # Execute the avoidance maneuver
                self.vehicle.simple_goto(target)
                
                # Wait for movement to execute
                await asyncio.sleep(5)
            else:
                logger.info(f"Not adjusting for collision with {closest_drone_id} due to higher priority role")
        
        except Exception as e:
            logger.error(f"Error in collision avoidance: {e}")
        finally:
            # Reset evasive maneuver flag
            self.evasive_maneuver = False

    def calculate_bearing(self, pos1, pos2):
        """
        Calculate bearing from pos1 to pos2
        
        Args:
            pos1: (lat, lon) of starting position
            pos2: (lat, lon) of destination position
        
        Returns:
            bearing in radians
        """
        lat1, lon1 = pos1
        lat2, lon2 = pos2
        
        # Convert to radians
        lat1 = math.radians(lat1)
        lon1 = math.radians(lon1)
        lat2 = math.radians(lat2)
        lon2 = math.radians(lon2)
        
        # Calculate bearing
        y = math.sin(lon2 - lon1) * math.cos(lat2)
        x = math.cos(lat1) * math.sin(lat2) - math.sin(lat1) * math.cos(lat2) * math.cos(lon2 - lon1)
        bearing = math.atan2(y, x)
        
        return bearing

    async def return_to_home(self):
        """Return the drone to its home location"""
        try:
            logger.info("Returning to home location")
            self.is_pursuing = False
            self.role = 'UNASSIGNED'
            
            # Get home location from config
            home = self.config['flight_parameters']['home_location']
            
            # Notify swarm we're returning home
            status_update = {
                'type': 'drone_returning',
                'drone_id': self.drone_id,
                'reason': 'manual_command',
                'timestamp': time.time()
            }
            
            await self.websocket.send(json.dumps(status_update))
            
            # Navigate to home location
            target = LocationGlobalRelative(home[0], home[1], home[2])
            self.vehicle.simple_goto(target)
            
            # Wait until we're close to home
            while True:
                # Check for collision risks during return
                await self.detect_collision_risk()
                
                current_location = self.vehicle.location.global_frame
                home_location = (home[0], home[1])
                current = (current_location.lat, current_location.lon)
                
                distance = haversine(current, home_location, unit='m')
                logger.info(f"Distance to home: {distance}m")
                
                if distance < 10:
                    logger.info("Reached home location")
                    break
                    
                await asyncio.sleep(2)
            
            # Land
            logger.info("Landing")
            self.vehicle.mode = VehicleMode("LAND")
            
            # Wait for landing
            while self.vehicle.location.global_relative_frame.alt > 0.1:
                logger.info(f"Altitude: {self.vehicle.location.global_relative_frame.alt}")
                await asyncio.sleep(1)
                
            logger.info("Landed successfully")
            
        except Exception as e:
            logger.error(f"Error returning to home: {e}")

    async def receive_messages(self):
        """Continuously receive messages from the WebSocket"""
        if not self.websocket:
            logger.error("No WebSocket connection")
            return
        
        try:
            logger.info("Starting message receiver...")
            while True:
                message = await self.websocket.recv()
                data = json.loads(message)
                
                # Process message based on type
                message_type = data.get('type', '')
                
                if message_type == 'drone_registration':
                    # New drone joined the swarm
                    drone_id = data.get('drone_id')
                    if drone_id and drone_id != self.drone_id:
                        logger.info(f"New drone {drone_id} joined the swarm")
                        # Reassign frequency bands to accommodate new drone
                        await self.sdr_manager.assign_frequency_bands()
                
                elif message_type == 'frequency_band_assignment':
                    # Handle frequency band assignment
                    assignments = data.get('assignments', {})
                    self.sdr_manager.active_frequencies.update(assignments)
                    logger.info(f"Updated frequency band assignments: {assignments}")
                
                elif message_type == 'sdr_scan_results':
                    # Handle SDR scan results from other drones
                    drone_id = data.get('drone_id')
                    if drone_id and drone_id != self.drone_id:
                        self.sdr_manager.scan_results[drone_id] = {
                            'band': data.get('frequency_band'),
                            'results': data.get('results'),
                            'timestamp': data.get('timestamp')
                        }
                
                elif message_type == 'command':
                    # Handle command from ground station
                    await self.handle_command(data)
                
                elif message_type == 'sdr_data':
                    # Process SDR data
                    await self.process_sdr_data(data)
                
                elif message_type == 'drone_position':
                    # Update position of another drone
                    drone_id = data.get('drone_id')
                    if drone_id and drone_id != self.drone_id:
                        if drone_id not in self.other_drones:
                            self.other_drones[drone_id] = {}
                        
                        self.other_drones[drone_id]['location'] = data.get('location')
                        self.other_drones[drone_id]['velocity'] = data.get('velocity')
                        self.other_drones[drone_id]['heading'] = data.get('heading')
                        self.other_drones[drone_id]['timestamp'] = data.get('timestamp')
                
                elif message_type == 'drone_status':
                    # Update status of another drone
                    drone_id = data.get('drone_id')
                    if drone_id and drone_id != self.drone_id:
                        if drone_id not in self.other_drones:
                            self.other_drones[drone_id] = {}
                        
                        self.other_drones[drone_id]['is_pursuing'] = data.get('is_pursuing')
                        self.other_drones[drone_id]['target_location'] = data.get('target_location')
                        self.other_drones[drone_id]['role'] = data.get('role')
                        self.other_drones[drone_id]['is_lead'] = data.get('is_lead')
                        
                        # Update location if included
                        if 'location' in data:
                            self.other_drones[drone_id]['location'] = data.get('location')
                
                elif message_type == 'swarm_roles':
                    # Handle role assignment from leader
                    leader_id = data.get('leader_id')
                    frequency = data.get('frequency')
                    
                    # Find our assignment
                    for assignment in data.get('assignments', []):
                        if assignment.get('drone_id') == self.drone_id:
                            await self.set_role(assignment.get('role'), frequency)
                            break
                
                elif message_type == 'violation_detected':
                    # Another drone detected a violation
                    if not self.is_pursuing:
                        # Participate in leader election
                        await self.elect_swarm_leader(data.get('frequency'))
                
                elif message_type == 'drone_returning':
                    # Another drone is returning to home
                    drone_id = data.get('drone_id')
                    if drone_id in self.other_drones:
                        logger.info(f"Drone {drone_id} is returning to home")
                        
                        # If this was the lead drone, we need to re-elect
                        if self.other_drones[drone_id].get('is_lead', False) and self.is_pursuing:
                            logger.info(f"Lead drone {drone_id} is returning home. Re-electing leader.")
                            await self.elect_swarm_leader(self.target_frequency)
                
                elif message_type == 'scout_signal':
                    # A scout drone found a strong signal
                    if self.is_lead and self.is_pursuing:
                        scout_id = data.get('drone_id')
                        freq = data.get('frequency')
                        rssi = data.get('rssi')
                        scout_location = data.get('location')
                        
                        # If this is our target frequency and signal is stronger than ours
                        if freq == self.target_frequency and self.sdr_data.get(freq) and rssi > self.sdr_data[freq]['rssi']:
                            logger.info(f"Scout {scout_id} found stronger signal. Updating target location.")
                            
                            # Update target location based on scout's position
                            self.target_location = [
                                scout_location['latitude'],
                                scout_location['longitude'],
                                scout_location['altitude']
                            ]
                
        except websockets.exceptions.ConnectionClosed:
            logger.error("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Error receiving messages: {e}")

    async def handle_command(self, command):
        """Handle commands from the ground station"""
        cmd_type = command.get('command')
        
        if cmd_type == 'takeoff':
            altitude = command.get('altitude', self.config['flight_parameters']['altitude'])
            await self.takeoff(altitude)
            
        elif cmd_type == 'land':
            self.vehicle.mode = VehicleMode("LAND")
            logger.info("Landing command received")
            
        elif cmd_type == 'return_home':
            await self.return_to_home()
            
        elif cmd_type == 'goto':
            lat = command.get('latitude')
            lon = command.get('longitude')
            alt = command.get('altitude', self.vehicle.location.global_relative_frame.alt)
            
            if lat and lon:
                target = LocationGlobalRelative(lat, lon, alt)
                self.vehicle.simple_goto(target)
                logger.info(f"Moving to: {lat}, {lon}, {alt}")
                
        elif cmd_type == 'pursue':
            freq = command.get('frequency')
            if freq and freq in self.sdr_data:
                # Initiate swarm leader election
                await self.elect_swarm_leader(freq)
                logger.info(f"Starting pursuit of {freq} MHz")
                
        elif cmd_type == 'stop_pursuit':
            self.is_pursuing = False
            self.role = 'UNASSIGNED'
            logger.info("Stopping pursuit")
            
        elif cmd_type == 'assign_role':
            role = command.get('role')
            freq = command.get('frequency')
            
            if role in PURSUIT_ROLES and freq:
                await self.set_role(role, freq)
                logger.info(f"Manually assigned role: {role}")
        
        else:
            logger.warning(f"Unknown command: {cmd_type}")

    async def cleanup_old_drones(self):
        """Remove drones that haven't sent updates in a while"""
        while True:
            # Find drones with old timestamps
            now = time.time()
            old_drones = []
            swarm_changed = False
            
            for drone_id, data in self.other_drones.items():
                last_timestamp = data.get('timestamp', 0)
                if now - last_timestamp > 10:  # 10 seconds timeout
                    old_drones.append(drone_id)
                    swarm_changed = True
            
            # Remove old drones
            for drone_id in old_drones:
                logger.info(f"Removing inactive drone: {drone_id}")
                del self.other_drones[drone_id]
                
                # If this was the lead drone, we need to re-elect
                if self.swarm_leader_id == drone_id and self.is_pursuing:
                    logger.info(f"Lead drone {drone_id} is no longer active. Re-electing leader.")
                    await self.elect_swarm_leader(self.target_frequency)
            
            # Reassign frequency bands if swarm composition changed
            if swarm_changed:
                logger.info("Swarm composition changed. Reassigning frequency bands...")
                await self.sdr_manager.assign_frequency_bands()
            
            await asyncio.sleep(5)

    async def run(self):
        """Main execution loop"""
        success = await self.connect_drone()
        if not success:
            logger.error("Failed to connect to drone. Exiting.")
            return
        
        await self.load_models()
        
        success = await self.connect_websocket()
        if not success:
            logger.error("Failed to connect to WebSocket. Exiting.")
            return
        
        # Start receivers and background tasks
        message_task = asyncio.create_task(self.receive_messages())
        cleanup_task = asyncio.create_task(self.cleanup_old_drones())
        
        # Assign frequency bands to drones
        await self.sdr_manager.assign_frequency_bands()
        
        # Status update and position sharing loop
        try:
            while True:
                await self.send_status_update()
                await self.share_position()
                
                # Check for collision risks periodically
                if self.role != 'UNASSIGNED':
                    await self.detect_collision_risk()
                
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Main loop cancelled")
        except Exception as e:
            logger.error(f"Error in main loop: {e}")
        finally:
            # Clean up tasks
            message_task.cancel()
            cleanup_task.cancel()
            
            # Close connections
            if self.websocket:
                await self.websocket.close()
            
            if self.vehicle:
                self.vehicle.close()
            
            logger.info("Drone controller shutdown complete")

async def main():
    """Entry point for the drone swarm controller"""
    controller = DroneSwarmController()
    await controller.run()

if __name__ == "__main__":
    asyncio.run(main())
