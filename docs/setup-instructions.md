# Setup Instructions

## System Requirements

### Hardware Requirements
- RTL-SDR device (or compatible SDR hardware)
- NVIDIA GPU with CUDA support (optional, for GPU acceleration)
- Sufficient RAM (minimum 8GB recommended)
- x86_64 or ARM64 processor

### Software Prerequisites
- Python 3.7 or higher
- Node.js 14.x or higher
- CUDA Toolkit 11.x (optional, for GPU acceleration)
- MongoDB (optional, for data logging)
- GNU Radio 3.8+ (optional, for advanced signal processing)

## Installation Steps

### 1. Clone the Repository
```bash
git clone https://github.com/yourusername/sdr-threejs.git
cd sdr-threejs
```

### 2. Python Environment Setup

#### Create and Activate Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate  # On Linux/MacOS
# or
.\venv\Scripts\activate  # On Windows
```

#### Install Python Dependencies
```bash
pip install -r requirements.txt
```

Key Python dependencies include:
- RTL-SDR libraries for SDR hardware interaction
- NumPy and SciPy for signal processing
- TensorFlow and scikit-learn for signal classification
- CuPy for GPU acceleration (if CUDA is available)
- WebSockets for real-time data streaming
- MongoDB drivers for data logging

### 3. Node.js Backend Setup

Navigate to the backend directory and install dependencies:
```bash
cd backend
npm install
```

This will install:
- Express.js for the web server
- WebSocket libraries for real-time communication
- CORS middleware for security

### 4. Hardware Configuration

#### RTL-SDR Setup
1. Connect your RTL-SDR device
2. Install RTL-SDR drivers:
   ```bash
   # Ubuntu/Debian
   sudo apt-get install rtl-sdr
   
   # Fedora
   sudo dnf install rtl-sdr
   
   # Arch Linux
   sudo pacman -S rtl-sdr
   ```
3. Add udev rules (Linux only):
   ```bash
   sudo cp rtl-sdr.rules /etc/udev/rules.d/
   sudo udevadm control --reload-rules
   sudo udevadm trigger
   ```

#### GPU Setup (Optional)
If using GPU acceleration:
1. Install NVIDIA drivers
2. Install CUDA Toolkit 11.x
3. Verify CUDA installation:
   ```bash
   nvidia-smi
   ```

### 5. Database Setup (Optional)

If using MongoDB for data logging:
1. Install MongoDB
2. Start MongoDB service:
   ```bash
   sudo systemctl start mongodb
   ```
3. Create database and user:
   ```bash
   mongo
   > use fcc_monitor
   > db.createUser({
       user: "sdruser",
       pwd: "your_password",
       roles: ["readWrite"]
     })
   ```

### 6. Starting the System

1. Start the WebSocket server:
```bash
cd backend
node server.js
```

2. Start the SDR controller:
```bash
cd python
python integrated-detector.py
```

3. Start the web interface:
```bash
cd frontend
python -m http.server 8000
```

4. Access the interface:
Open your browser and navigate to:
`http://localhost:8000/Drone-SDR-Pursuit-Interface.html`

## Configuration

### Signal Classifier Setup
The system includes a pre-trained signal classification model. To use it:
1. Ensure scikit-learn and related dependencies are installed
2. The model will be automatically loaded from `signal_classifier_model.pkl`
3. To retrain the model:
   ```bash
   python signal_classifier.py --train
   ```

### SDR Configuration
Edit `python/integrated-detector.py` to modify:
- Sample rate
- Center frequency
- Gain settings
- FFT size

### Visualization Settings
Adjust in `frontend/frontend-signal-visualization.js`:
- Update rate
- Color schemes
- Display resolution

## Troubleshooting

### Common Issues

1. **RTL-SDR Not Detected**
   - Check USB connection
   - Verify drivers are installed
   - Run `rtl_test` to verify device functionality

2. **WebSocket Connection Failed**
   - Verify server is running
   - Check port availability (default: 8766)
   - Check firewall settings

3. **GPU Acceleration Not Working**
   - Verify CUDA installation
   - Check CuPy installation matches CUDA version
   - Monitor GPU usage with `nvidia-smi`

4. **MongoDB Connection Issues**
   - Verify MongoDB service is running
   - Check connection string in configuration
   - Verify database user permissions

### Getting Help

For additional assistance:
1. Check the project documentation in `/docs`
2. Review error logs in the terminal output
3. Check system requirements match specifications
4. Verify all dependencies are correctly installed

## Optional Components

### GNU Radio Integration
If using GNU Radio features:
1. Install GNU Radio 3.8 or higher
2. Install gr-osmosdr
3. Install gr-fosphor for GPU-accelerated visualization

### Remote SDR Integration
For KiwiSDR and WebSDR support:
1. Ensure aiohttp is installed
2. Configure API endpoints in configuration files
3. Test connection with remote SDR services

## Security Considerations

1. **Network Security**
   - Use firewall rules to restrict port access
   - Configure CORS settings appropriately
   - Use secure WebSocket connections when possible

2. **Database Security**
   - Use strong MongoDB passwords
   - Enable authentication
   - Restrict database network access

3. **Hardware Access**
   - Set appropriate USB device permissions
   - Restrict SDR frequency ranges as needed
   - Monitor system resource usage

## Updating

To update the system:
1. Pull latest changes from repository
2. Update Python dependencies
3. Update Node.js dependencies
4. Rebuild any modified components
5. Restart all services