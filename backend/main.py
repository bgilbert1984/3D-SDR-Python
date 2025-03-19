from fastapi import FastAPI, HTTPException, Request, BackgroundTasks, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import asyncio
import os
import signal
import sys
import json
from pathlib import Path
import psutil
import importlib.util
from typing import List, Optional
from datetime import datetime, timedelta

# Import KiwiSDR client
try:
    spec = importlib.util.spec_from_file_location(
        "kiwisdr_client", 
        str(Path(__file__).parent.parent / "python" / "kiwisdr_client.py")
    )
    kiwisdr_module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(kiwisdr_module)
    KiwiSDRClient = kiwisdr_module.KiwiSDRClient
except Exception as e:
    print(f"Error loading KiwiSDR client: {e}")
    KiwiSDRClient = None

app = FastAPI()

# Add CORS middleware for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Get the absolute path to the frontend directory
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
PYTHON_DIR = Path(__file__).parent.parent / "python"

# Check if directories exist
if not FRONTEND_DIR.exists():
    raise RuntimeError(f"Frontend directory not found: {FRONTEND_DIR}")
if not PYTHON_DIR.exists():
    raise RuntimeError(f"Python directory not found: {PYTHON_DIR}")

# Track running processes
processes = {
    "sdr_sim": None,
    "node_relay": None,
    "websdr_bridge": None,
    "kiwisdr": None
}

# Global KiwiSDR client
kiwisdr_client = None
kiwisdr_task = None

# In-memory storage for historical data
historical_signals = []
historical_violations = []

# --- Helper Functions ---
def is_process_running(process_obj):
    """Check if a process is running"""
    if process_obj is None:
        return False
    try:
        return process_obj.poll() is None  # None means still running
    except Exception:
        return False

def kill_process(process_obj):
    """Kill a process gracefully"""
    if process_obj is None:
        return True
    
    try:
        if is_process_running(process_obj):
            process_obj.terminate()  # Try SIGTERM first
            try:
                process_obj.wait(timeout=5)  # Wait up to 5 seconds
            except subprocess.TimeoutExpired:
                process_obj.kill()  # Force kill if not responding
        return True
    except Exception as e:
        print(f"Error killing process: {str(e)}")
        return False

# --- API Models ---
class StartSDRSimRequest(BaseModel):
    type: str = "sim"  # Default to 'sim' if not provided

class KiwiSDRConnectRequest(BaseModel):
    server_address: str
    port: int = 8073  # Default KiwiSDR port
    frequency: float  # In kHz

# --- API Endpoints ---
@app.post("/api/start-sdr-sim")
async def start_sdr_sim(request: StartSDRSimRequest):
    """Start the SDR simulation Python script"""
    global processes
    
    # First, kill any existing SDR sim process
    kill_process(processes["sdr_sim"])
    
    # Determine which script to run based on the sim type
    script_path = None
    if request.type == "sim":
        script_path = PYTHON_DIR / "sdr_sim_stream.py"
    # Add more script types as needed
    
    if script_path is None or not script_path.exists():
        return {"success": False, "error": f"Script for {request.type} not found"}
    
    try:
        # Launch the Python process
        python_executable = sys.executable  # Use the same Python that's running this
        cmd = [python_executable, str(script_path)]
        
        # Start the process with proper redirections
        processes["sdr_sim"] = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Give it a moment to start
        await asyncio.sleep(0.5)
        
        # Check if it's running
        if is_process_running(processes["sdr_sim"]):
            print(f"Started {script_path} successfully")
            return {"success": True, "message": f"SDR Sim ({request.type}) started successfully"}
        else:
            error_output = processes["sdr_sim"].stderr.read()
            return {"success": False, "error": f"Failed to start: {error_output}"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/stop-sdr-sim")
async def stop_sdr_sim():
    """Stop the SDR simulation"""
    global processes
    if kill_process(processes["sdr_sim"]):
        processes["sdr_sim"] = None
        return {"success": True, "message": "SDR Sim stopped"}
    return {"success": False, "error": "Failed to stop SDR Sim process"}

@app.get("/api/service-status")
async def get_service_status():
    """Get the status of all services"""
    global processes, kiwisdr_client
    
    # Check if each process is running
    sdr_sim_running = is_process_running(processes["sdr_sim"])
    node_relay_running = is_process_running(processes["node_relay"])
    websdr_bridge_running = is_process_running(processes["websdr_bridge"])
    kiwisdr_running = kiwisdr_client is not None
    
    return {
        "pythonSdr": sdr_sim_running,
        "nodeRelay": node_relay_running, 
        "websdrBridge": websdr_bridge_running,
        "kiwiSdr": kiwisdr_running
    }

@app.post("/api/start-relay")
async def start_relay():
    """Start the Node.js relay server"""
    global processes
    
    # First, kill any existing relay process
    kill_process(processes["node_relay"])
    
    relay_script = Path(__file__).parent / "server.js"
    
    if not relay_script.exists():
        return {"success": False, "error": "Relay script not found"}
    
    try:
        # Launch Node.js process
        cmd = ["node", str(relay_script)]
        
        processes["node_relay"] = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Give it a moment to start
        await asyncio.sleep(0.5)
        
        if is_process_running(processes["node_relay"]):
            return {"success": True, "message": "Node.js relay started successfully"}
        else:
            error_output = processes["node_relay"].stderr.read()
            return {"success": False, "error": f"Failed to start relay: {error_output}"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/start-websdr-bridge")
async def start_websdr_bridge():
    """Start the WebSDR bridge"""
    global processes
    
    # First, kill any existing WebSDR bridge process
    kill_process(processes["websdr_bridge"])
    
    bridge_script = PYTHON_DIR / "websdr-bridge.py"
    
    if not bridge_script.exists():
        return {"success": False, "error": "WebSDR bridge script not found"}
    
    try:
        # Launch the Python WebSDR bridge process
        python_executable = sys.executable
        cmd = [python_executable, str(bridge_script)]
        
        processes["websdr_bridge"] = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True
        )
        
        # Give it a moment to start
        await asyncio.sleep(0.5)
        
        if is_process_running(processes["websdr_bridge"]):
            return {"success": True, "message": "WebSDR bridge started successfully"}
        else:
            error_output = processes["websdr_bridge"].stderr.read()
            return {"success": False, "error": f"Failed to start WebSDR bridge: {error_output}"}
            
    except Exception as e:
        return {"success": False, "error": str(e)}

@app.post("/api/stop-all-services")
async def stop_all_services():
    """Stop all running services"""
    global processes, kiwisdr_client, kiwisdr_task
    
    success = True
    errors = []
    
    # Try to stop all processes
    for service, process in processes.items():
        if not kill_process(process):
            success = False
            errors.append(f"Failed to stop {service}")
    
    # Stop KiwiSDR client if running
    if kiwisdr_task:
        kiwisdr_task.cancel()
        kiwisdr_task = None
        kiwisdr_client = None
    
    # Clear all process references
    processes = {
        "sdr_sim": None,
        "node_relay": None,
        "websdr_bridge": None,
        "kiwisdr": None
    }
    
    if success:
        return {"success": True, "message": "All services stopped"}
    else:
        return {"success": False, "error": ", ".join(errors)}

async def kiwisdr_streaming_task(server, port, frequency, websocket_queue):
    """Background task for streaming KiwiSDR data"""
    global kiwisdr_client
    
    try:
        # Create KiwiSDR client
        if not KiwiSDRClient:
            raise RuntimeError("KiwiSDR client module not found")
            
        kiwisdr_client = KiwiSDRClient()
        await kiwisdr_client.__aenter__()  # Initialize the client
        
        # Generate direct URL to the KiwiSDR instance
        custom_station = {
            'station_id': f"custom_{server}_{port}",
            'name': f"Custom KiwiSDR at {server}:{port}",
            'url': f"http://{server}:{port}",
            'latitude': 0.0,
            'longitude': 0.0,
            'band_coverage': [{'start': 0, 'end': 30}]  # Assume full coverage
        }
        
        custom_station_obj = kiwisdr_module.KiwiStation(**custom_station)
        
        # Main streaming loop
        update_interval = 0.5  # Update every 500ms
        while True:
            try:
                # Get data from the KiwiSDR
                data = await kiwisdr_client.get_station_data(custom_station_obj, frequency * 1000)  # Convert kHz to Hz
                
                if data:
                    # Format data for visualization
                    vis_data = {
                        'timestamp': data['timestamp'],
                        'freqs': [data['frequency']],
                        'amplitudes': [data['signal_strength'] / 100.0],  # Scale to 0-1 range
                    }
                    
                    # Send data to websocket queue
                    await websocket_queue.put(json.dumps(vis_data))
                
                await asyncio.sleep(update_interval)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"Error in KiwiSDR streaming loop: {e}")
                await asyncio.sleep(1)  # Wait a bit before retrying
                
    except Exception as e:
        print(f"KiwiSDR streaming task error: {e}")
    finally:
        # Cleanup
        if kiwisdr_client:
            await kiwisdr_client.__aexit__(None, None, None)
            kiwisdr_client = None

@app.post("/api/connect-kiwisdr")
async def connect_kiwisdr(request: KiwiSDRConnectRequest, background_tasks: BackgroundTasks):
    """Connect to a KiwiSDR instance"""
    global kiwisdr_client, kiwisdr_task
    
    # Stop any existing KiwiSDR connection
    if kiwisdr_task:
        kiwisdr_task.cancel()
        await asyncio.sleep(0.5)  # Give it time to clean up
    
    try:
        # Create a queue for communicating with the websocket
        websocket_queue = asyncio.Queue()
        
        # Start the KiwiSDR streaming task
        kiwisdr_task = asyncio.create_task(
            kiwisdr_streaming_task(
                request.server_address, 
                request.port, 
                request.frequency,
                websocket_queue
            )
        )
        
        return {
            "success": True,
            "message": f"Connected to KiwiSDR at {request.server_address}:{request.port} on frequency {request.frequency} kHz"
        }
    except Exception as e:
        return {
            "success": False,
            "error": f"Failed to connect to KiwiSDR: {str(e)}"
        }

@app.post("/api/disconnect-kiwisdr")
async def disconnect_kiwisdr():
    """Disconnect from KiwiSDR"""
    global kiwisdr_client, kiwisdr_task
    
    if kiwisdr_task:
        kiwisdr_task.cancel()
        kiwisdr_task = None
        kiwisdr_client = None
        return {"success": True, "message": "Disconnected from KiwiSDR"}
    else:
        return {"success": True, "message": "No active KiwiSDR connection to disconnect"}

@app.post("/api/add-signal")
async def add_signal(signal: dict):
    """Add a signal to the historical data storage."""
    signal["timestamp"] = datetime.now().isoformat()
    historical_signals.append(signal)
    return {"success": True, "message": "Signal added."}

@app.post("/api/add-violation")
async def add_violation(violation: dict):
    """Add a violation to the historical data storage."""
    violation["timestamp"] = datetime.now().isoformat()
    historical_violations.append(violation)
    return {"success": True, "message": "Violation added."}

@app.get("/api/get-historical-data")
async def get_historical_data(
    start_time: Optional[str] = Query(None, description="Start time in ISO format"),
    end_time: Optional[str] = Query(None, description="End time in ISO format"),
    frequency_min: Optional[float] = Query(None, description="Minimum frequency in MHz"),
    frequency_max: Optional[float] = Query(None, description="Maximum frequency in MHz"),
    modulation: Optional[str] = Query(None, description="Filter by modulation type"),
    power_min: Optional[float] = Query(None, description="Minimum power (0-1)"),
    power_max: Optional[float] = Query(None, description="Maximum power (0-1)")
):
    """Retrieve historical signal and violation data based on filters."""
    start_time = datetime.fromisoformat(start_time) if start_time else datetime.min
    end_time = datetime.fromisoformat(end_time) if end_time else datetime.max

    # Filter signals
    filtered_signals = [
        signal for signal in historical_signals
        if start_time <= datetime.fromisoformat(signal["timestamp"]) <= end_time
        and (frequency_min is None or signal["frequency_mhz"] >= frequency_min)
        and (frequency_max is None or signal["frequency_mhz"] <= frequency_max)
        and (modulation is None or signal["modulation"] == modulation)
        and (power_min is None or signal["power"] >= power_min)
        and (power_max is None or signal["power"] <= power_max)
    ]

    # Filter violations
    filtered_violations = [
        violation for violation in historical_violations
        if start_time <= datetime.fromisoformat(violation["timestamp"]) <= end_time
        and (frequency_min is None or violation["frequency_mhz"] >= frequency_min)
        and (frequency_max is None or violation["frequency_mhz"] <= frequency_max)
        and (modulation is None or violation["modulation"] == modulation)
        and (power_min is None or violation["power"] >= power_min)
        and (power_max is None or violation["power"] <= power_max)
    ]

    return {
        "signals": filtered_signals,
        "violations": filtered_violations
    }

# Serve the index.html file at the root path
@app.get("/")
async def read_index():
    return FileResponse(str(FRONTEND_DIR / "index.html"))

# Serve static files only after API routes are defined
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR)), name="static")

# Clean up on shutdown
@app.on_event("shutdown")
def shutdown_event():
    """Stop all processes when the FastAPI app shuts down"""
    for process in processes.values():
        kill_process(process)