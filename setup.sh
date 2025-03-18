#!/bin/bash

echo "Installing GNU Radio and dependencies..."
sudo apt-get update
sudo apt-get install -y gnuradio gnuradio-dev gr-osmosdr gr-fosphor python3-pip

echo "Installing Python dependencies..."
python3 -m pip install -r python/requirements.txt

echo "Setup complete!"
echo "To start the SDR visualization:"
echo "1. Start the GNU Radio flowgraph: python3 python/geolocation-integrated.py"
echo "2. Open frontend/Drone-SDR-Pursuit-Interface.html in your browser"