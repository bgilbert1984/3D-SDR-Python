#!/usr/bin/env python3
"""
Gemma Data Preprocessor

This script processes the collected SDR IQ data and OCR text from screen captures
to create training data for the Gemma model. It extracts features from the IQ data,
combines them with OCR text, and formats the data for model training.

Usage:
  python gemma_data_preprocessor.py --input-dir dataset/20250320_123456_14.200MHz
"""

import os
import argparse
import json
import numpy as np
import pandas as pd
import glob
from typing import Dict, List, Tuple, Optional
from datetime import datetime
import logging
import scipy.signal as signal

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger('gemma_data_processor')

class GemmaDataProcessor:
    """
    Process KiwiSDR IQ and screen OCR data for Gemma model training.
    
    This class handles:
    1. Loading IQ data and OCR text
    2. Feature extraction from IQ data
    3. Data alignment between IQ and OCR
    4. Formatting data for Gemma training
    """
    
    def __init__(self, input_dir: str, output_dir: str = None):
        """
        Initialize the data processor.
        
        Args:
            input_dir: Directory containing the captured data
            output_dir: Directory to save processed data (default: input_dir/processed)
        """
        self.input_dir = input_dir
        
        if not output_dir:
            output_dir = os.path.join(input_dir, "processed")
            
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)
        
        # Check if input directory exists
        if not os.path.isdir(input_dir):
            raise ValueError(f"Input directory does not exist: {input_dir}")
            
        # Check for capture summary file
        summary_path = os.path.join(input_dir, "capture_summary.json")
        if os.path.exists(summary_path):
            with open(summary_path, 'r') as f:
                self.summary = json.load(f)
            logger.info(f"Loaded capture summary from {summary_path}")
        else:
            # Try to find station directories
            station_dirs = glob.glob(os.path.join(input_dir, "station_*"))
            if not station_dirs:
                station_dirs = [input_dir]  # Use input dir if no station dirs
            self.summary = {
                "results": [{"output_dir": d} for d in station_dirs]
            }
            logger.info(f"No summary file found, using {len(station_dirs)} station directories")
    
    def extract_iq_features(self, iq_data: np.ndarray) -> Dict:
        """
        Extract features from IQ data.
        
        Args:
            iq_data: Complex IQ samples
            
        Returns:
            Dictionary of features extracted from the IQ data
        """
        # Ensure we have enough samples
        if len(iq_data) < 1024:
            logger.warning(f"IQ data too short: {len(iq_data)} samples")
            return {}
        
        # Calculate power spectral density
        f, psd = signal.welch(iq_data, fs=12000, nperseg=1024, noverlap=512, return_onesided=False)
        psd = np.fft.fftshift(psd)
        f = np.fft.fftshift(f)
        
        # Calculate signal statistics
        power = 10 * np.log10(np.mean(np.abs(iq_data)**2))
        peak_power = 10 * np.log10(np.max(np.abs(iq_data)**2))
        std_dev = np.std(np.abs(iq_data))
        
        # Phase statistics
        phase = np.angle(iq_data)
        phase_std = np.std(phase)
        
        # Find peaks in PSD
        peak_indices = signal.find_peaks(psd, height=np.max(psd)/10)[0]
        peak_freqs = f[peak_indices]
        peak_values = psd[peak_indices]
        
        # Sort peaks by power
        peak_order = np.argsort(-peak_values)
        peak_freqs = peak_freqs[peak_order]
        peak_values = peak_values[peak_order]
        
        # Take up to 5 strongest peaks
        num_peaks = min(5, len(peak_freqs))
        peaks = [
            {"freq_offset": float(peak_freqs[i]), "power": float(peak_values[i])}
            for i in range(num_peaks)
        ]
        
        # Calculate modulation features
        # AM detection
        am_demod = np.abs(iq_data)
        am_mod_index = (np.max(am_demod) - np.min(am_demod)) / np.mean(am_demod)
        
        # FM detection
        fm_demod = np.diff(np.unwrap(np.angle(iq_data)))
        fm_deviation = np.std(fm_demod)
        
        # Collect features into a dictionary
        features = {
            "power_db": float(power),
            "peak_power_db": float(peak_power),
            "std_dev": float(std_dev),
            "phase_std": float(phase_std),
            "am_mod_index": float(am_mod_index),
            "fm_deviation": float(fm_deviation),
            "peaks": peaks,
            "num_samples": len(iq_data)
        }
        
        return features
    
    def process_station_data(self, station_result: Dict) -> Optional[Dict]:
        """
        Process data from a single station.
        
        Args:
            station_result: Dictionary with paths to station data
            
        Returns:
            Dictionary with processed data or None if processing failed
        """
        output_dir = station_result.get("output_dir")
        if not output_dir or not os.path.isdir(output_dir):
            logger.error(f"Invalid station directory: {output_dir}")
            return None
            
        metadata_files = glob.glob(os.path.join(output_dir, "*_metadata.json"))
        if not metadata_files:
            # Check for IQ data subdirectory
            iq_data_dir = os.path.join(output_dir, "iq_data")
            if os.path.isdir(iq_data_dir):
                metadata_files = glob.glob(os.path.join(iq_data_dir, "..", "*_metadata.json"))
        
        if not metadata_files:
            logger.error(f"No metadata files found in {output_dir}")
            return None
            
        # Use the first metadata file found
        metadata_path = metadata_files[0]
        with open(metadata_path, 'r') as f:
            metadata = json.load(f)
        
        # Find corresponding IQ data file
        iq_path = station_result.get("iq_data_path")
        if not iq_path or not os.path.exists(iq_path):
            # Try to find it from metadata
            base_filename = os.path.basename(metadata_path).replace("_metadata.json", "")
            iq_data_dir = os.path.join(output_dir, "iq_data")
            candidate_paths = [
                os.path.join(output_dir, f"{base_filename}_iq.npy"),
                os.path.join(iq_data_dir, f"{base_filename}_iq.npy")
            ]
            
            for path in candidate_paths:
                if os.path.exists(path):
                    iq_path = path
                    break
        
        if not iq_path or not os.path.exists(iq_path):
            logger.error(f"Could not find IQ data file for {metadata_path}")
            return None
            
        # Load IQ data
        try:
            iq_data = np.load(iq_path)
            logger.info(f"Loaded IQ data from {iq_path}: {len(iq_data)} samples")
        except Exception as e:
            logger.error(f"Error loading IQ data from {iq_path}: {e}")
            return None
            
        # Extract features from IQ data
        iq_features = self.extract_iq_features(iq_data)
        
        # Process OCR results
        ocr_results = metadata.get("ocr_results", station_result.get("ocr_results", []))
        
        # Combine all OCR text
        ocr_text = ""
        for result in ocr_results:
            if len(result) >= 3:  # Should be (timestamp, filename, text)
                text = result[2]
                if text:
                    ocr_text += text + " "
        
        ocr_text = ocr_text.strip()
        
        # Create processed data
        processed_data = {
            "station_id": metadata.get("station_id", "unknown"),
            "station_name": metadata.get("station_name", "Unknown Station"),
            "frequency": metadata.get("frequency", 0.0),
            "sample_rate": metadata.get("sample_rate", 12000.0),
            "latitude": metadata.get("latitude", 0.0),
            "longitude": metadata.get("longitude", 0.0),
            "timestamp": metadata.get("timestamp", time.time()),
            "datetime": metadata.get("datetime", datetime.now().strftime("%Y%m%d_%H%M%S")),
            "iq_features": iq_features,
            "ocr_text": ocr_text,
            "ocr_count": len(ocr_results)
        }
        
        return processed_data
    
    def create_gemma_training_data(self, processed_data: List[Dict]) -> pd.DataFrame:
        """
        Create training data for the Gemma model.
        
        Args:
            processed_data: List of processed data dictionaries
            
        Returns:
            DataFrame with formatted training data
        """
        training_rows = []
        
        for data in processed_data:
            # Skip entries with no OCR text
            if not data.get("ocr_text"):
                continue
                
            iq_features = data.get("iq_features", {})
            
            # Format the feature information as text
            feature_text = (
                f"Signal at {data['frequency']/1e6:.3f} MHz with "
                f"power {iq_features.get('power_db', 0):.1f} dB. "
            )
            
            # Add peak information
            peaks = iq_features.get("peaks", [])
            if peaks:
                feature_text += "Signal contains peaks at: "
                for i, peak in enumerate(peaks[:3]):  # Top 3 peaks
                    offset = peak.get("freq_offset", 0)
                    power = peak.get("power", 0)
                    feature_text += f"{offset:.1f} Hz ({power:.1f} dB)"
                    if i < len(peaks[:3]) - 1:
                        feature_text += ", "
            
            # Add modulation information
            am_mod = iq_features.get("am_mod_index", 0)
            fm_dev = iq_features.get("fm_deviation", 0)
            if am_mod > 0.2:
                feature_text += f" AM modulation detected (index: {am_mod:.2f}). "
            if fm_dev > 0.1:
                feature_text += f" FM modulation detected (deviation: {fm_dev:.2f}). "
                
            # Create input and output pairs for training
            # Input: Signal features with prompt
            # Output: OCR text from the waterfall display
            
            # Input prompt
            input_text = f"Analyze the following radio signal: {feature_text}"
            
            # Output text (OCR content)
            output_text = data["ocr_text"]
            
            # Create training row
            training_rows.append({
                "input": input_text,
                "output": output_text,
                "frequency": data["frequency"],
                "station_id": data["station_id"],
                "timestamp": data["timestamp"]
            })
        
        # Create DataFrame
        if training_rows:
            df = pd.DataFrame(training_rows)
            return df
        else:
            return pd.DataFrame(columns=["input", "output", "frequency", "station_id", "timestamp"])
    
    def process_all_data(self) -> pd.DataFrame:
        """
        Process all data from all stations.
        
        Returns:
            DataFrame with training data for the Gemma model
        """
        all_processed_data = []
        
        # Process each station
        for result in self.summary.get("results", []):
            processed = self.process_station_data(result)
            if processed:
                all_processed_data.append(processed)
        
        # Save processed data as JSON
        processed_json_path = os.path.join(self.output_dir, "processed_data.json")
        with open(processed_json_path, 'w') as f:
            json.dump(all_processed_data, f, indent=2)
        logger.info(f"Saved processed data to {processed_json_path}")
        
        # Create training data
        training_df = self.create_gemma_training_data(all_processed_data)
        
        # Save training data as CSV
        csv_path = os.path.join(self.output_dir, "gemma_training_data.csv")
        training_df.to_csv(csv_path, index=False)
        logger.info(f"Saved {len(training_df)} training examples to {csv_path}")
        
        # Also save as JSON for easier parsing
        json_path = os.path.join(self.output_dir, "gemma_training_data.json")
        training_df.to_json(json_path, orient="records", indent=2)
        logger.info(f"Saved training data as JSON to {json_path}")
        
        return training_df

def main():
    parser = argparse.ArgumentParser(
        description="Process KiwiSDR data for Gemma model training"
    )
    
    parser.add_argument(
        "--input-dir", type=str, required=True,
        help="Directory containing the captured data"
    )
    
    parser.add_argument(
        "--output-dir", type=str, default=None,
        help="Directory to save processed data (default: input_dir/processed)"
    )
    
    args = parser.parse_args()
    
    # Initialize processor and process data
    try:
        processor = GemmaDataProcessor(args.input_dir, args.output_dir)
        training_df = processor.process_all_data()
        
        # Print summary
        print("\n=== PROCESSED DATA SUMMARY ===")
        print(f"Total training examples: {len(training_df)}")
        if len(training_df) > 0:
            print(f"Average input length: {training_df['input'].str.len().mean():.1f} characters")
            print(f"Average output length: {training_df['output'].str.len().mean():.1f} characters")
            print(f"Number of unique frequencies: {training_df['frequency'].nunique()}")
        print("===============================\n")
        
    except Exception as e:
        logger.error(f"Error processing data: {e}", exc_info=True)
        return 1
    
    return 0

if __name__ == "__main__":
    import time
    import sys
    sys.exit(main())