import numpy as np
import json
import time
import pickle
import os
from scipy import signal as sg
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
from sklearn.model_selection import train_test_split
from sklearn.metrics import accuracy_score, classification_report

# Define modulation types we want to classify
MODULATION_TYPES = {
    'AM': 'Amplitude Modulation',
    'FM': 'Frequency Modulation',
    'SSB': 'Single Sideband',
    'CW': 'Continuous Wave (Morse)',
    'PSK': 'Phase Shift Keying',
    'FSK': 'Frequency Shift Keying',
    'NOISE': 'Noise/Interference',
    'UNKNOWN': 'Unknown'
}

class SignalClassifier:
    def __init__(self, model_path=None):
        """Initialize the signal classifier, optionally loading a pre-trained model."""
        self.model = None
        self.scaler = StandardScaler()
        self.feature_names = [
            'bandwidth', 'center_freq', 'peak_power', 'mean_power', 
            'variance', 'skewness', 'kurtosis', 'crest_factor',
            'spectral_flatness', 'spectral_rolloff'
        ]
        
        if model_path and os.path.exists(model_path):
            self.load_model(model_path)
        else:
            # Initialize a new model
            self.model = RandomForestClassifier(
                n_estimators=100, 
                max_depth=10,
                random_state=42
            )
            print("Created new signal classifier model (not trained yet)")
    
    def load_model(self, model_path):
        """Load a pre-trained model from file."""
        try:
            with open(model_path, 'rb') as f:
                model_data = pickle.load(f)
                self.model = model_data['model']
                self.scaler = model_data.get('scaler', StandardScaler())
                print(f"Loaded signal classifier model from {model_path}")
                
                # If the model has feature importances, print them
                if hasattr(self.model, 'feature_importances_'):
                    importances = self.model.feature_importances_
                    indices = np.argsort(importances)[::-1]
                    print("Feature ranking:")
                    for i, idx in enumerate(indices):
                        if i < len(self.feature_names):
                            print(f"{i+1}. {self.feature_names[idx]} ({importances[idx]:.4f})")
                
                return True
        except Exception as e:
            print(f"Error loading model: {e}")
            return False
    
    def save_model(self, model_path):
        """Save the trained model to file."""
        if self.model is None:
            print("No model to save")
            return False
        
        try:
            with open(model_path, 'wb') as f:
                pickle.dump({'model': self.model, 'scaler': self.scaler}, f)
            print(f"Saved signal classifier model to {model_path}")
            return True
        except Exception as e:
            print(f"Error saving model: {e}")
            return False
    
    def extract_features(self, freqs, amplitudes, threshold=0.2):
        """
        Extract features from a signal for classification.
        
        Parameters:
        freqs: Array of frequency values
        amplitudes: Array of amplitude values (normalized)
        threshold: Power threshold to consider for feature extraction
        
        Returns:
        Dictionary of features
        """
        # Ensure we have numpy arrays
        freqs = np.array(freqs)
        amplitudes = np.array(amplitudes)
        
        # Find peaks above threshold
        peak_indices = sg.find_peaks(amplitudes, height=threshold)[0]
        
        # If no significant peaks found, return noise features
        if len(peak_indices) == 0:
            return {
                'bandwidth': 0,
                'center_freq': 0,
                'peak_power': 0,
                'mean_power': np.mean(amplitudes),
                'variance': np.var(amplitudes),
                'skewness': 0,
                'kurtosis': 0,
                'crest_factor': 0,
                'spectral_flatness': 0,
                'spectral_rolloff': 0
            }
        
        # Find the strongest peak
        strongest_peak_idx = peak_indices[np.argmax(amplitudes[peak_indices])]
        
        # Calculate bandwidth (use 3dB below peak for estimation)
        peak_power_db = 10 * np.log10(amplitudes[strongest_peak_idx])
        threshold_db = peak_power_db - 3
        threshold_linear = 10 ** (threshold_db / 10)
        
        # Find indices where power is above threshold
        above_threshold = amplitudes > threshold_linear
        if np.any(above_threshold):
            bandwidth = np.max(freqs[above_threshold]) - np.min(freqs[above_threshold])
        else:
            bandwidth = 0
        
        # Calculate statistical features
        mean_power = np.mean(amplitudes)
        variance = np.var(amplitudes)
        
        # Higher-order statistics
        amplitudes_normalized = (amplitudes - mean_power) / np.sqrt(variance) if variance > 0 else amplitudes
        skewness = np.mean(amplitudes_normalized ** 3) if variance > 0 else 0
        kurtosis = np.mean(amplitudes_normalized ** 4) if variance > 0 else 0
        
        # Crest factor (peak-to-average power ratio)
        crest_factor = np.max(amplitudes) / mean_power if mean_power > 0 else 0
        
        # Spectral features
        spectral_flatness = np.exp(np.mean(np.log(amplitudes + 1e-10))) / mean_power if mean_power > 0 else 0
        
        # Spectral rolloff (frequency below which 85% of energy is contained)
        cumsum = np.cumsum(amplitudes)
        spectral_rolloff = 0
        if cumsum[-1] > 0:
            rolloff_point = 0.85 * cumsum[-1]
            rolloff_idx = np.where(cumsum >= rolloff_point)[0][0]
            spectral_rolloff = freqs[rolloff_idx]
        
        # Return features as a dictionary
        return {
            'bandwidth': bandwidth,
            'center_freq': freqs[strongest_peak_idx],
            'peak_power': amplitudes[strongest_peak_idx],
            'mean_power': mean_power,
            'variance': variance,
            'skewness': skewness,
            'kurtosis': kurtosis,
            'crest_factor': crest_factor,
            'spectral_flatness': spectral_flatness,
            'spectral_rolloff': spectral_rolloff
        }
    
    def features_to_vector(self, features):
        """Convert feature dictionary to vector for model input."""
        return np.array([features[name] for name in self.feature_names]).reshape(1, -1)
    
    def train(self, X_train, y_train):
        """Train the model with feature vectors and modulation labels."""
        if X_train.shape[0] == 0 or y_train.shape[0] == 0:
            print("No training data provided")
            return False
        
        print(f"Training signal classifier on {X_train.shape[0]} samples")
        
        # Scale features
        X_train_scaled = self.scaler.fit_transform(X_train)
        
        # Train the model
        self.model.fit(X_train_scaled, y_train)
        
        print("Training completed")
        return True
    
    def evaluate(self, X_test, y_test):
        """Evaluate the model on test data."""
        if self.model is None:
            print("Model not trained yet")
            return None
        
        if X_test.shape[0] == 0 or y_test.shape[0] == 0:
            print("No test data provided")
            return None
        
        # Scale test data
        X_test_scaled = self.scaler.transform(X_test)
        
        # Make predictions
        y_pred = self.model.predict(X_test_scaled)
        
        # Calculate accuracy
        accuracy = accuracy_score(y_test, y_pred)
        report = classification_report(y_test, y_pred)
        
        print(f"Model accuracy: {accuracy:.4f}")
        print("Classification report:")
        print(report)
        
        return {
            'accuracy': accuracy,
            'report': report,
            'predictions': y_pred
        }
    
    def predict(self, freqs, amplitudes, threshold=0.2):
        """
        Predict the modulation type of a signal.
        
        Parameters:
        freqs: Array of frequency values
        amplitudes: Array of amplitude values (normalized)
        threshold: Power threshold to consider for feature extraction
        
        Returns:
        Dictionary with prediction results
        """
        if self.model is None:
            return {'modulation': 'UNKNOWN', 'confidence': 0.0, 'features': {}}
        
        # Extract features from the signal
        features = self.extract_features(freqs, amplitudes, threshold)
        
        # Convert to feature vector
        X = self.features_to_vector(features)
        
        # Scale features
        X_scaled = self.scaler.transform(X)
        
        # Make prediction
        modulation = self.model.predict(X_scaled)[0]
        
        # Get prediction probabilities
        proba = self.model.predict_proba(X_scaled)[0]
        confidence = np.max(proba)
        
        return {
            'modulation': modulation,
            'confidence': float(confidence),
            'features': features
        }
    
    def generate_training_data(self, num_samples=1000):
        """
        Generate synthetic training data for different modulation types.
        This is a simplified version - in a real implementation, you'd use 
        actual SDR recordings of different modulation types.
        """
        print(f"Generating {num_samples} synthetic samples for training")
        
        # Lists to store features and labels
        X = []
        y = []
        
        # Generate samples for each modulation type
        modulations = list(MODULATION_TYPES.keys())
        modulations.remove('UNKNOWN')  # Don't generate samples for UNKNOWN
        
        samples_per_mod = num_samples // len(modulations)
        
        for modulation in modulations:
            print(f"Generating {samples_per_mod} samples for {modulation}")
            
            for _ in range(samples_per_mod):
                # Generate a synthetic spectrum based on modulation characteristics
                freqs = np.linspace(-1e6, 1e6, 1024)
                amplitudes = np.zeros_like(freqs)
                
                # Different modulation types have different spectral characteristics
                if modulation == 'AM':
                    # AM has carrier + symmetric sidebands
                    carrier_idx = len(freqs) // 2
                    carrier_width = np.random.randint(5, 15)
                    sideband_width = np.random.randint(30, 100)
                    
                    # Add carrier
                    amplitudes[carrier_idx-carrier_width:carrier_idx+carrier_width] = np.random.uniform(0.7, 1.0)
                    
                    # Add sidebands
                    amplitudes[carrier_idx-sideband_width:carrier_idx-carrier_width] = np.random.uniform(0.2, 0.5)
                    amplitudes[carrier_idx+carrier_width:carrier_idx+sideband_width] = np.random.uniform(0.2, 0.5)
                
                elif modulation == 'FM':
                    # FM has wider bandwidth
                    center_idx = len(freqs) // 2
                    bandwidth = np.random.randint(100, 200)
                    
                    # Create a wider, more uniform spectrum
                    amplitudes[center_idx-bandwidth:center_idx+bandwidth] = np.random.uniform(0.5, 1.0, size=2*bandwidth)
                    
                    # Add some random peaks
                    for _ in range(5):
                        peak_idx = np.random.randint(center_idx-bandwidth, center_idx+bandwidth)
                        peak_width = np.random.randint(3, 10)
                        amplitudes[peak_idx-peak_width:peak_idx+peak_width] += np.random.uniform(0.1, 0.3)
                
                elif modulation == 'SSB':
                    # SSB has one sideband only
                    center_idx = len(freqs) // 2
                    sideband_width = np.random.randint(50, 150)
                    
                    # Add single sideband (50% chance for upper vs lower)
                    if np.random.random() > 0.5:
                        # Upper sideband
                        amplitudes[center_idx:center_idx+sideband_width] = np.random.uniform(0.4, 0.9, size=sideband_width)
                    else:
                        # Lower sideband
                        amplitudes[center_idx-sideband_width:center_idx] = np.random.uniform(0.4, 0.9, size=sideband_width)
                
                elif modulation == 'CW':
                    # CW is a narrow signal
                    center_idx = len(freqs) // 2
                    width = np.random.randint(2, 10)
                    
                    # Add narrow peak
                    amplitudes[center_idx-width:center_idx+width] = np.random.uniform(0.7, 1.0)
                
                elif modulation == 'PSK':
                    # PSK has a sinc-like spectrum
                    center_idx = len(freqs) // 2
                    bandwidth = np.random.randint(30, 80)
                    
                    # Create a sinc-like shape
                    for i in range(-bandwidth, bandwidth+1):
                        if i == 0:
                            continue
                        idx = center_idx + i
                        if 0 <= idx < len(amplitudes):
                            amplitudes[idx] = 0.6 * np.abs(np.sin(i * np.pi/20) / (i * np.pi/20))
                    
                    # Add center peak
                    amplitudes[center_idx-5:center_idx+5] = np.random.uniform(0.7, 0.9)
                
                elif modulation == 'FSK':
                    # FSK has multiple peaks
                    center_idx = len(freqs) // 2
                    shift = np.random.randint(30, 100)
                    width = np.random.randint(5, 15)
                    
                    # Add two main peaks
                    amplitudes[center_idx-shift-width:center_idx-shift+width] = np.random.uniform(0.7, 1.0)
                    amplitudes[center_idx+shift-width:center_idx+shift+width] = np.random.uniform(0.7, 1.0)
                
                elif modulation == 'NOISE':
                    # Just noise with maybe a few weak signals
                    amplitudes = np.random.uniform(0.1, 0.3, size=len(freqs))
                    
                    # Maybe add a few weak peaks
                    if np.random.random() > 0.5:
                        for _ in range(np.random.randint(1, 5)):
                            peak_idx = np.random.randint(0, len(freqs))
                            width = np.random.randint(3, 10)
                            start_idx = max(0, peak_idx - width)
                            end_idx = min(len(freqs), peak_idx + width)
                            amplitudes[start_idx:end_idx] += np.random.uniform(0.1, 0.2)
                
                # Add noise to all
                amplitudes += np.random.normal(0, 0.05, size=len(freqs))
                
                # Ensure non-negative
                amplitudes = np.maximum(amplitudes, 0)
                
                # Normalize
                if np.max(amplitudes) > 0:
                    amplitudes /= np.max(amplitudes)
                
                # Extract features
                features = self.extract_features(freqs, amplitudes)
                feature_vector = [features[name] for name in self.feature_names]
                
                # Add to dataset
                X.append(feature_vector)
                y.append(modulation)
        
        return np.array(X), np.array(y)

# Function to train and save a new model
def train_new_model(model_path='signal_classifier_model.pkl'):
    """Train and save a new signal classifier model."""
    classifier = SignalClassifier()
    
    # Generate synthetic training data
    X, y = classifier.generate_training_data(num_samples=10000)
    
    # Split into training and test sets
    X_train, X_test, y_train, y_test = train_test_split(X, y, test_size=0.2, random_state=42)
    
    # Train the model
    classifier.train(X_train, y_train)
    
    # Evaluate the model
    classifier.evaluate(X_test, y_test)
    
    # Save the model
    classifier.save_model(model_path)
    
    return classifier

# Main code for testing the classifier
if __name__ == "__main__":
    model_path = 'signal_classifier_model.pkl'
    
    # Check if model exists
    if os.path.exists(model_path):
        print(f"Loading existing model from {model_path}")
        classifier = SignalClassifier(model_path)
    else:
        print(f"Training new model and saving to {model_path}")
        classifier = train_new_model(model_path)
    
    # Test on some synthetic data
    print("\nTesting on synthetic signals:")
    
    # Simulate AM signal
    freqs = np.linspace(-1e6, 1e6, 1024)
    center_idx = len(freqs) // 2
    amplitudes = np.zeros_like(freqs)
    amplitudes[center_idx-10:center_idx+10] = 1.0  # Carrier
    amplitudes[center_idx-100:center_idx-10] = 0.3  # Lower sideband
    amplitudes[center_idx+10:center_idx+100] = 0.3  # Upper sideband
    amplitudes += np.random.normal(0, 0.05, size=len(freqs))
    amplitudes = np.maximum(amplitudes, 0)
    amplitudes /= np.max(amplitudes)
    
    result = classifier.predict(freqs, amplitudes)
    print(f"AM signal test - Predicted: {result['modulation']} with {result['confidence']:.4f} confidence")
    
    # Simulate FM signal
    amplitudes = np.zeros_like(freqs)
    amplitudes[center_idx-150:center_idx+150] = 0.7  # Wide bandwidth
    amplitudes += np.random.normal(0, 0.05, size=len(freqs))
    amplitudes = np.maximum(amplitudes, 0)
    amplitudes /= np.max(amplitudes)
    
    result = classifier.predict(freqs, amplitudes)
    print(f"FM signal test - Predicted: {result['modulation']} with {result['confidence']:.4f} confidence")
    
    # Simulate CW signal
    amplitudes = np.zeros_like(freqs)
    amplitudes[center_idx-5:center_idx+5] = 1.0  # Very narrow
    amplitudes += np.random.normal(0, 0.05, size=len(freqs))
    amplitudes = np.maximum(amplitudes, 0)
    amplitudes /= np.max(amplitudes)
    
    result = classifier.predict(freqs, amplitudes)
    print(f"CW signal test - Predicted: {result['modulation']} with {result['confidence']:.4f} confidence")
