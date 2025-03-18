import asyncio
import numpy as np
import websockets
import json
import time
import os
import logging
from scipy.optimize import minimize
from haversine import haversine
from dronekit import connect, VehicleMode, LocationGlobalRelative
import tensorflow as tf
from pymavlink import mavutil
from gnuradio import osmosdr

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('drone_sdr_controller')

# Constants
SPEED_OF_LIGHT = 299792458  # m/s

class DroneSDRController:
    """
    Main controller for SDR-equipped drones for signal pursuit and geolocation
    """
    
    def __init__(self, config_file='drone_config.json'):
        """Initialize the drone controller with configuration"""
        self.config = self._load_config(config_file)
        self.vehicle = None
        self.sdr_data = {}
        self.target_location = None
        self.pursuit_model = None
        self.signal_classifier = None
        self.is_pursuing = False
        self.other_drones = {}
        self.drone_id = self.config['drone_id']
        self.websocket = None
        logger.info(f"Drone {self.drone_id} controller initialized")
    
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
        """Connect to the WebSocket server for SDR data"""
        try:
            logger.info(f"Connecting to WebSocket at: {self.config['websocket_url']}")
            self.websocket = await websockets.connect(self.config['websocket_url'])
            logger.info("Connected to WebSocket server")
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
                'battery': self.vehicle.battery.level,
                'is_pursuing': self.is_pursuing,
                'target_location': self.target_location
            }
            
            await self.websocket.send(json.dumps(status))
        except Exception as e:
            logger.error(f"Error sending status update: {e}")

    async def process_sdr_data(self, data):
        """Process incoming SDR data"""
        try:
            freq = data.get('freq', 0)
            rssi = data.get('rssi', 0)
            tdoa = data.get('tdoa', 0)
            predicted_location = data.get('predicted_location', [0, 0, 0])
            
            # Store SDR data for this frequency
            self.sdr_data[freq] = {
                'rssi': rssi,
                'tdoa': tdoa,
                'predicted_location': predicted_location,
                'timestamp': time.time()
            }
            
            # If we're not already pursuing and this is a violation, start pursuit
            if not self.is_pursuing and data.get('is_violation', False):
                logger.info(f"Starting pursuit of signal at {freq} MHz")
                self.target_location = predicted_location
                self.is_pursuing = True
                
                # Launch pursuit task
                asyncio.create_task(self.pursue_signal(freq))
        except Exception as e:
            logger.error(f"Error processing SDR data: {e}")

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
        Actively pursue a signal transmitter
        Uses AI to predict transmitter movement if model is available
        """
        logger.info(f"Beginning signal pursuit for {freq} MHz")
        
        try:
            while self.is_pursuing:
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
                        move = moves[move_index]
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
                
                # Share our status with the ground station
                await self.send_status_update()
                
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

    async def return_to_home(self):
        """Return the drone to its home location"""
        try:
            logger.info("Returning to home location")
            self.is_pursuing = False
            
            # Get home location from config
            home = self.config['flight_parameters']['home_location']
            
            # Navigate to home location
            target = LocationGlobalRelative(home[0], home[1], home[2])
            self.vehicle.simple_goto(target)
            
            # Wait until we're close to home
            while True:
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

    async def receive_sdr_data(self):
        """Continuously receive SDR data from the WebSocket"""
        if not self.websocket:
            logger.error("No WebSocket connection")
            return
        
        try:
            logger.info("Starting SDR data receiver...")
            while True:
                message = await self.websocket.recv()
                data = json.loads(message)
                
                if data.get('type') == 'command':
                    # Handle command from ground station
                    await self.handle_command(data)
                else:
                    # Process SDR data
                    await self.process_sdr_data(data)
                
        except websockets.exceptions.ConnectionClosed:
            logger.error("WebSocket connection closed")
        except Exception as e:
            logger.error(f"Error receiving SDR data: {e}")

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
                self.is_pursuing = True
                asyncio.create_task(self.pursue_signal(freq))
                logger.info(f"Starting pursuit of {freq} MHz")
                
        elif cmd_type == 'stop_pursuit':
            self.is_pursuing = False
            logger.info("Stopping pursuit")
            
        else:
            logger.warning(f"Unknown command: {cmd_type}")

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
        
        # Start receiving SDR data
        asyncio.create_task(self.receive_sdr_data())
        
        # Status update loop
        while True:
            await self.send_status_update()
            await asyncio.sleep(1)

    def detect_all_sdr_devices(self):
        """Discover all available SDR devices across multiple APIs"""
        devices = []
        
        # Detect RTL-SDR devices via osmosdr
        for i in range(10):
            try:
                src = osmosdr.source(args=f"rtl={i}")
                devices.append({
                    "type": "rtl-sdr", 
                    "index": i,
                    "name": f"RTL-SDR #{i}",
                    "sample_rate_range": [0.25e6, 3.2e6]
                })
                del src
            except Exception as e:
                if "Failed to open" in str(e):
                    break
        
        # Add other SDR APIs detection here
        
        return devices

async def main():
    """Entry point for the drone controller"""
    controller = DroneSDRController()
    await controller.run()

if __name__ == "__main__":
    asyncio.run(main())
