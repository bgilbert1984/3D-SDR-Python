# Signal Classifier

## Overview
The SDR Drone Pursuit System includes a sophisticated signal classification system that can identify different modulation types in real-time. The classifier uses machine learning techniques to analyze spectral features and determine the most likely modulation scheme being used by a detected signal.

## Supported Modulation Types

The signal classifier can identify the following modulation types:

| Modulation | Description |
|------------|-------------|
| AM | Amplitude Modulation |
| FM | Frequency Modulation |
| SSB | Single Sideband |
| CW | Continuous Wave (Morse code) |
| PSK | Phase Shift Keying |
| FSK | Frequency Shift Keying |
| NOISE | Noise/Interference |
| UNKNOWN | Unclassifiable signals |

## Machine Learning Approach

The classifier uses a RandomForest machine learning algorithm trained on spectral features extracted from signal samples. This provides significantly better classification accuracy than basic threshold-based approaches.

### Model Implementation

- **Algorithm**: RandomForestClassifier from scikit-learn
- **Training set**: 10,000 synthetic samples across modulation types
- **Features**: 10 spectral characteristics (bandwidth, center frequency, power metrics, etc.)
- **Confidence scoring**: Probability-based confidence scores for each prediction

## GPU Acceleration

The classifier supports GPU acceleration through CuPy when available:

```python
def setup_gpu_processing():
    """Set up GPU-accelerated signal processing if available"""
    try:
        import cupy as cp
        print("Using GPU acceleration for signal processing")
        return {'enabled': True, 'xp': cp}
    except ImportError:
        print("GPU acceleration not available, using CPU")
        return {'enabled': False, 'xp': np}
```

- **Automatic detection**: The system automatically detects GPU availability at runtime
- **Transparent API**: The same code works on both CPU and GPU through a common API
- **Fallback**: When GPU is unavailable, the system gracefully falls back to CPU

## Feature Extraction Process

The signal classification relies on extracting key features from the spectral representation of signals:

1. **Preprocessing**: Signal data is normalized and peaks are detected
2. **Feature calculation**: 10 key features are computed from the signal spectrum

### Key Features Used:

1. **Bandwidth** - Estimated signal bandwidth using 3dB method
2. **Center Frequency** - Dominant frequency of the signal
3. **Peak Power** - Maximum power of the signal
4. **Mean Power** - Average power across the signal
5. **Variance** - Statistical variance of the power distribution
6. **Skewness** - Asymmetry of the power distribution
7. **Kurtosis** - Peakedness/flatness of the power distribution
8. **Crest Factor** - Peak-to-average power ratio
9. **Spectral Flatness** - Ratio of geometric mean to arithmetic mean of spectrum
10. **Spectral Rolloff** - Frequency below which 85% of the signal energy is contained

### Feature Extraction Code:

```python
def extract_features(self, freqs, amplitudes, threshold=0.2):
    """Extract features from a signal for classification."""
    # Ensure we have arrays on the correct device (GPU or CPU)
    freqs = self.xp.array(freqs)
    amplitudes = self.xp.array(amplitudes)
    
    # Find peaks above threshold
    if self.gpu['enabled']:
        # CuPy doesn't have signal.find_peaks, use simplified peak finding
        peak_indices = self.xp.where((amplitudes > threshold) & 
                                  (amplitudes > self.xp.roll(amplitudes, 1)) & 
                                  (amplitudes > self.xp.roll(amplitudes, -1)))[0]
    else:
        peak_indices = sg.find_peaks(amplitudes, height=threshold)[0]
    
    # If no significant peaks found, return noise features
    if len(peak_indices) == 0:
        return {
            'bandwidth': 0,
            'center_freq': 0,
            'peak_power': 0,
            'mean_power': float(self.xp.mean(amplitudes)),
            'variance': float(self.xp.var(amplitudes)),
            'skewness': 0,
            'kurtosis': 0,
            'crest_factor': 0,
            'spectral_flatness': 0,
            'spectral_rolloff': 0
        }
    
    # Calculate remaining features...
    # [Further feature calculation code]
```

## Training Process

The classifier uses synthetic data generation to create training samples for each modulation type:

1. **Generate synthetic data**: Creates spectral patterns that mimic different modulations
2. **Extract features**: Computes feature vectors for each sample
3. **Train model**: Trains RandomForest classifier on the feature vectors
4. **Evaluate accuracy**: Tests performance on a validation set
5. **Save model**: Stores the trained model for later use

## Model Evaluation

The model accuracy is evaluated using standard classification metrics:

- **Accuracy**: Overall correct classification rate
- **Confusion matrix**: Distribution of predictions across actual modulation types
- **Precision/recall**: Balance between false positives and false negatives
- **F1 score**: Harmonic mean of precision and recall

## Usage

### Basic Usage:

```python
from signal_classifier import SignalClassifier

# Initialize classifier with pre-trained model
classifier = SignalClassifier('signal_classifier_model.pkl')

# Predict modulation from signal data
result = classifier.predict(frequencies, amplitudes)
print(f"Predicted modulation: {result['modulation']}")
print(f"Confidence: {result['confidence']:.2f}")
```

### Integration with SDR System:

The classifier is integrated into the `integrated-detector.py` script, which:

1. Captures raw IQ data from SDR
2. Performs FFT to get spectrum
3. Detects signal peaks
4. Extracts spectral segments around peaks
5. Classifies each segment using the model
6. Reports classifications via WebSocket interface

## Modulation Type Characteristics

### AM (Amplitude Modulation)
- Strong center carrier with symmetric sidebands
- Distinctive three-peak spectral pattern
- Moderate bandwidth (typically 10-30 kHz)

### FM (Frequency Modulation)
- Wider, more uniform spectral distribution
- Higher bandwidth than AM (typically 75-250 kHz for broadcast FM)
- More gradual rolloff at edges

### SSB (Single Sideband)
- Asymmetric spectrum with only one sideband
- No visible carrier
- Narrower bandwidth than full AM

### CW (Continuous Wave)
- Very narrow bandwidth (<500 Hz)
- Single sharp peak
- High peak-to-average power ratio

### PSK (Phase Shift Keying)
- Characteristic sinc-like frequency pattern
- Symmetric spectrum
- Distinctive nulls at regular intervals

### FSK (Frequency Shift Keying)
- Multiple discrete peaks or lobes
- Spacing between peaks related to shift frequency
- Often has two main lobes

## Future Improvements

1. **Real-world training data**: Replace synthetic data with captured real-world signals
2. **Dynamic adaptation**: Allow model to adapt to changing RF environments
3. **Deep learning**: Investigate CNN or RNN approaches for direct waveform classification
4. **Higher order modulations**: Add support for QAM, OFDM, and other digital modes
5. **Interference resilience**: Improve classification under low SNR conditions