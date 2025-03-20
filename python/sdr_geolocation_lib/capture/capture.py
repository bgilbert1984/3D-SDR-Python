"""
Screen capture and OCR module.

This module provides functionality for capturing screenshots, performing change detection,
and running OCR on the captured images. It's designed to work in conjunction with IQ
data acquisition for building datasets suitable for ML model training.
"""

import mss
import mss.tools
import cv2
import numpy as np
from PIL import Image
import easyocr
import time
import os
from datetime import datetime
import logging
import json

# Configure logging
logger = logging.getLogger('capture')

def calculate_ssim(img1, img2):
    """Calculates the Structural Similarity Index (SSIM) between two images."""
    img1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    img2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)
    return cv2.matchTemplate(img1, img2, cv2.TM_CCOEFF_NORMED)[0][0]

class DataCapture:
    """
    A class for capturing and processing screen data from SDR interfaces.
    
    This class handles screen captures, change detection between frames,
    and OCR processing. It's designed to work in conjunction with IQ data
    acquisition to associate visual information with signal data.
    """
    
    def __init__(self, ssim_threshold=0.95, capture_interval=1, monitor_number=1, 
                 region=None, languages=['en']):
        """
        Initialize the DataCapture object.
        
        Args:
            ssim_threshold: Threshold for detecting changes between frames (0-1)
            capture_interval: Time interval between captures in seconds
            monitor_number: Which monitor to capture (1-based index)
            region: Optional tuple of (left, top, width, height) to capture specific region
            languages: List of languages for OCR
        """
        self.ssim_threshold = ssim_threshold
        self.capture_interval = capture_interval
        self.monitor_number = monitor_number
        self.region = region
        self.reader = easyocr.Reader(languages)
        self.previous_frame = None
        self.frame_count = 0
        
        # Create monitor dict for specific region if provided
        self.monitor = None
        if region:
            self.monitor = {
                "left": region[0],
                "top": region[1],
                "width": region[2],
                "height": region[3]
            }
    
    def capture_frame(self):
        """
        Captures a single frame from the specified monitor or region using mss.
        
        Returns:
            Numpy array of the captured frame or None on error
        """
        try:
            with mss.mss() as sct:
                # If specific region is defined, use it, otherwise use the full monitor
                if self.monitor:
                    target = self.monitor
                else:
                    target = sct.monitors[self.monitor_number]
                
                sct_img = sct.grab(target)
                return np.array(sct_img)
        except mss.exception.ScreenShotError as e:
            logger.error(f"Screenshot error: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error during screen capture: {e}")
            return None
    
    def preprocess_image(self, image):
        """
        Apply preprocessing to improve OCR results.
        
        Args:
            image: Numpy array of the image
            
        Returns:
            Preprocessed image as numpy array
        """
        # Convert to grayscale if not already
        if len(image.shape) > 2 and image.shape[2] > 1:
            gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        else:
            gray = image
            
        # Apply adaptive thresholding
        thresh = cv2.adaptiveThreshold(
            gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )
        
        # Apply noise reduction
        denoised = cv2.fastNlMeansDenoising(thresh, None, 10, 7, 21)
        
        return denoised
    
    def process_frame(self, frame, output_dir, frequency=None, include_preprocessing=True):
        """
        Processes a single frame: change detection, OCR, and saving.
        
        Args:
            frame: Numpy array of the captured frame
            output_dir: Directory to save captured images and OCR results
            frequency: Optional frequency information for metadata
            include_preprocessing: Whether to use preprocessing for OCR
            
        Returns:
            Tuple of (timestamp, image_filename, ocr_text) or None if no significant change
        """
        self.frame_count += 1
        
        # Ensure output directory exists
        os.makedirs(output_dir, exist_ok=True)
        
        if self.previous_frame is not None:
            try:
                ssim = calculate_ssim(self.previous_frame, frame)
                logger.debug(f"Frame {self.frame_count}: SSIM = {ssim:.4f}")
                
                # Check if current frame is significantly different from previous
                if ssim < self.ssim_threshold:
                    timestamp = int(time.time())
                    freq_str = f"{frequency/1e6:.3f}MHz_" if frequency else ""
                    image_filename = f"frame_{timestamp}_{freq_str}{self.frame_count:04d}.png"
                    image_path = os.path.join(output_dir, image_filename)
                    
                    # Save the image using PIL
                    # MSS returns images in BGRA format, convert to RGB for saving
                    pil_img = Image.frombytes("RGB", (frame.shape[1], frame.shape[0]), 
                                            frame, "raw", "BGRX")
                    pil_img.save(image_path)
                    
                    try:
                        # Apply preprocessing if requested
                        if include_preprocessing:
                            processed = self.preprocess_image(frame)
                            proc_path = os.path.join(output_dir, f"proc_{image_filename}")
                            cv2.imwrite(proc_path, processed)
                            ocr_image = proc_path
                        else:
                            ocr_image = image_path
                            
                        # Perform OCR
                        results = self.reader.readtext(ocr_image)
                        ocr_text = " ".join([result[1] for result in results])
                        
                        # Save OCR results
                        ocr_filename = os.path.join(output_dir, f"{os.path.splitext(image_filename)[0]}_ocr.txt")
                        with open(ocr_filename, 'w') as f:
                            f.write(ocr_text)
                            
                        # Save detailed OCR results with bounding boxes
                        ocr_details_filename = os.path.join(output_dir, f"{os.path.splitext(image_filename)[0]}_ocr_details.json")
                        with open(ocr_details_filename, 'w') as f:
                            # Convert results to serializable format
                            serializable_results = []
                            for bbox, text, confidence in results:
                                serializable_results.append({
                                    "bbox": [[float(coord) for coord in point] for point in bbox],
                                    "text": text,
                                    "confidence": float(confidence)
                                })
                            json.dump(serializable_results, f, indent=2)
                            
                        logger.info(f"Saved frame with OCR text: {ocr_text[:60]}...")
                        return timestamp, image_filename, ocr_text
                    
                    except Exception as e:
                        logger.error(f"OCR Error on frame {self.frame_count}: {e}")
                        return timestamp, image_filename, ""  # Return empty string for OCR text
                else:
                    logger.debug(f"No significant change (SSIM: {ssim:.4f})")
            except Exception as e:
                logger.error(f"Error during frame processing: {e}")
        else:
            timestamp = int(time.time())
            freq_str = f"{frequency/1e6:.3f}MHz_" if frequency else ""
            image_filename = f"frame_{timestamp}_{freq_str}{self.frame_count:04d}.png"
            image_path = os.path.join(output_dir, image_filename)
            
            # First frame - save it but don't do OCR
            pil_img = Image.frombytes("RGB", (frame.shape[1], frame.shape[0]), 
                                    frame, "raw", "BGRX")
            pil_img.save(image_path)
            logger.info(f"Saved initial frame {image_filename}")
            
        # Update previous frame
        self.previous_frame = frame.copy()
        return None  # No significant change or first frame

    def capture_and_process(self, output_dir, duration=10, frequency=None, 
                          include_preprocessing=True):
        """
        Continuously captures and processes frames for specified duration.
        
        Args:
            output_dir: Directory to save captured images and OCR results
            duration: Duration of capture in seconds
            frequency: Optional frequency information for metadata
            include_preprocessing: Whether to use preprocessing for OCR
            
        Returns:
            List of tuples (timestamp, image_filename, ocr_text)
        """
        results = []
        end_time = time.time() + duration
        
        while time.time() < end_time:
            start_capture = time.time()
            
            frame = self.capture_frame()
            if frame is not None:
                result = self.process_frame(
                    frame, output_dir, frequency, include_preprocessing
                )
                if result:
                    results.append(result)
            
            # Sleep to maintain capture interval
            elapsed = time.time() - start_capture
            if elapsed < self.capture_interval:
                time.sleep(self.capture_interval - elapsed)
        
        return results