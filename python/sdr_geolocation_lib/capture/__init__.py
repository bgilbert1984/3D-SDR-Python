"""
Capture module for SDR Geolocation Library.

This module provides functionality for screen capture, image processing, and OCR
to complement signal data acquisition.
"""

from .capture import DataCapture, calculate_ssim

__all__ = ['DataCapture', 'calculate_ssim']