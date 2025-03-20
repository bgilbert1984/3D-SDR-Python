#!/usr/bin/env python3
"""
Gemma Training Data Collector

This script demonstrates how to use the combined IQ data and screen capture functionality
to create a unified dataset for training a Gemma model. It captures both IQ data from KiwiSDR
stations and screen captures with OCR text from the web interface.

Usage:
  python gemma_training_data_collector.py --freq 14.2 --duration 60 --region 100 100 800 600
"""

import asyncio
import argparse
import logging
import os
import json
import numpy as np
from datetime import datetime
from typing import Tuple, Dict, List, Optional

# Import the remote SDR handler
from sdr_geolocation_lib.remote.remote_handler import RemoteSDRHandler

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('gemma_data_collector')

async def collect_training_data(
    frequency: float,
    duration: float = 60.0,
    sample_rate: float = 12000.0,
    output_dir: str = None,
    region: Tuple[int, int, int, int] = None,
    max_stations: int = 1
) -> List[Dict]:
    """
    Collect unified training data for the Gemma model by capturing both
    IQ data and screen/OCR data from KiwiSDR stations.
    
    Args:
        frequency: Center frequency in MHz
        duration: Duration of capture in seconds
        sample_rate: Sample rate in Hz
        output_dir: Directory to save the data (default: auto-generate)
        region: Screen region to capture (left, top, width, height)
        max_stations: Maximum number of KiwiSDR stations to use
        
    Returns:
        List of dictionaries containing paths to the captured data
    """
    # Convert frequency from MHz to Hz
    freq_hz = frequency * 1e6
    
    # Create timestamped output directory if not specified
    if not output_dir:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_dir = os.path.join("gemma_training_data", f"{timestamp}_{frequency:.3f}MHz")
        os.makedirs(output_dir, exist_ok=True)
    
    logger.info(f"Starting data collection at {frequency} MHz for {duration} seconds")
    logger.info(f"Output directory: {output_dir}")
    
    results = []
    
    # Use the RemoteSDRHandler to capture both IQ data and screen captures
    async with RemoteSDRHandler() as handler:
        capture_results = await handler.capture_iq_with_screen(
            frequency=freq_hz,
            sample_rate=sample_rate,
            duration=duration,
            output_dir=output_dir,
            max_stations=max_stations,
            region=region
        )
        
        if capture_results:
            results.extend(capture_results)
            logger.info(f"Successfully captured data from {len(capture_results)} stations")
        else:
            logger.warning("No data was captured")
    
    # Create a summary file with metadata about the capture session
    summary = {
        "timestamp": datetime.now().isoformat(),
        "frequency_mhz": frequency,
        "duration_seconds": duration,
        "sample_rate_hz": sample_rate,
        "captures": len(results),
        "output_directory": output_dir,
        "results": results
    }
    
    summary_path = os.path.join(output_dir, "capture_summary.json")
    with open(summary_path, "w") as f:
        json.dump(summary, f, indent=2)
    
    logger.info(f"Created summary file: {summary_path}")
    logger.info("Data collection complete")
    
    return results

def process_results(results: List[Dict]) -> None:
    """
    Process and display information about the captured data.
    
    Args:
        results: List of dictionaries containing paths to captured data
    """
    if not results:
        logger.warning("No results to process")
        return
    
    total_iq_samples = 0
    total_images = 0
    total_ocr_text_length = 0
    
    for result in results:
        # Load IQ data to get sample count
        iq_path = result.get("iq_data_path")
        if iq_path and os.path.exists(iq_path):
            iq_data = np.load(iq_path)
            total_iq_samples += len(iq_data)
        
        # Count image files in the screen data directory
        screen_dir = result.get("screen_data_dir")
        if screen_dir and os.path.exists(screen_dir):
            image_files = [f for f in os.listdir(screen_dir) 
                          if f.endswith('.png') and not f.startswith('proc_')]
            total_images += len(image_files)
        
        # Get total length of OCR text
        ocr_results = result.get("ocr_results", [])
        for _, _, text in ocr_results:
            total_ocr_text_length += len(text)
    
    # Display summary
    print("\n=== CAPTURE RESULTS SUMMARY ===")
    print(f"Total stations: {len(results)}")
    print(f"Total IQ samples: {total_iq_samples}")
    print(f"Total screen captures: {total_images}")
    print(f"Total OCR text length: {total_ocr_text_length} characters")
    print(f"Average OCR text per image: {total_ocr_text_length / max(1, total_images):.2f} characters")
    print("==============================\n")

def main():
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Collect unified KiwiSDR IQ and screen capture data for Gemma training"
    )
    
    parser.add_argument(
        "--freq", type=float, required=True,
        help="Center frequency in MHz (e.g., 14.2 for 14.2 MHz)"
    )
    
    parser.add_argument(
        "--duration", type=float, default=60.0,
        help="Duration of capture in seconds (default: 60)"
    )
    
    parser.add_argument(
        "--sample-rate", type=float, default=12000.0,
        help="Sample rate in Hz (default: 12000)"
    )
    
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Directory to save data (default: auto-generate)"
    )
    
    parser.add_argument(
        "--region", type=int, nargs=4, default=None,
        help="Screen region to capture: left top width height"
    )
    
    parser.add_argument(
        "--max-stations", type=int, default=1,
        help="Maximum number of KiwiSDR stations to use (default: 1)"
    )
    
    args = parser.parse_args()
    
    # Run the data collector
    results = asyncio.run(collect_training_data(
        frequency=args.freq,
        duration=args.duration,
        sample_rate=args.sample_rate,
        output_dir=args.output_dir,
        region=args.region,
        max_stations=args.max_stations
    ))
    
    # Process and display results
    process_results(results)

if __name__ == "__main__":
    main()