from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import subprocess
import asyncio
import os
from pathlib import Path

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

# Check if the directory exists
if not FRONTEND_DIR.exists():
    raise RuntimeError(f"Frontend directory not found: {FRONTEND_DIR}")

# Serve static files from the frontend directory
app.mount("/", StaticFiles(directory=str(FRONTEND_DIR), html=True), name="static")

# --- API Models ---
class StartSDRSimRequest(BaseModel):
    type: str

# --- API Endpoints ---
@app.post("/api/start-sdr-sim")
async def start_sdr_sim(request: StartSDRSimRequest):
    # Placeholder: We'll add the actual simulation start logic later
    print(f"Received request to start SDR sim of type: {request.type}") #Debug
    return JSONResponse({"success": True, "message": f"SDR Sim started (placeholder) - type: {request.type}"})

@app.get("/api/service-status")
async def get_service_status():
    # Placeholder: We'll add actual status checking later
    return JSONResponse({
        "pythonSdr": False,
        "nodeRelay": False,
        "websdrBridge": False
    })

@app.post("/api/start-relay")
async def start_relay():
    return JSONResponse({
        "success": True,
        "message": "Relay started (placeholder)."
    })

@app.post("/api/start-websdr-bridge")
async def start_websdr_bridge():
    return JSONResponse({
        "success": True,
        "message": "WebSDR bridge started (placeholder)."
    })