import asyncio
import numpy as np
import websockets
import json
import time
import logging
import sounddevice as sd
import scipy.signal as signal
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('websdr_bridge')

# Configuration
CONFIG = {
    'websdr': {
        'url': 'http://sdr.kf5jmd.com:8901/',
        'initial_frequency': 14200,  # 20m band
        'initial_mode': 'usb',
        'band': '20m',
        'waterfall_refresh': 0.1,
    },
    'bridge': {
        'sample_rate': 48000,
        'fft_size': 2048,
        'spectrum_refresh': 0.1,
        'timeout': 30,
        'headless': True,
    },
    'websocket': {
        'server_url': 'ws://localhost:8080',
    }
}

class WebSDRBridge:
    def __init__(self, config):
        self.config = config
        self.driver = None
        self.websocket = None
        self.running = False
        self.current_freq = config['websdr']['initial_frequency']
        self.current_mode = config['websdr']['initial_mode']
        self.current_band = config['websdr']['initial_band']
        
        # Audio processing setup
        self.sample_rate = config['bridge']['sample_rate']
        self.fft_size = config['bridge']['fft_size']
        self.audio_buffer = np.zeros(self.fft_size)

    async def connect_websdr(self):
        try:
            logger.info(f"Connecting to WebSDR at {self.config['websdr']['url']}")
            
            chrome_options = Options()
            if self.config['bridge']['headless']:
                chrome_options.add_argument("--headless=new")
                chrome_options.add_argument("--mute-audio")
            
            chrome_options.add_argument("--use-fake-ui-for-media-stream")
            chrome_options.add_argument("--allow-file-access-from-files")
            chrome_options.add_argument("--enable-features=AudioServiceOutOfProcess")
            
            self.driver = webdriver.Chrome(options=chrome_options)
            self.driver.set_page_load_timeout(self.config['bridge']['timeout'])
            
            self.driver.get(self.config['websdr']['url'])
            
            # Wait for WebSDR interface to load
            wait = WebDriverWait(self.driver, 15)
            wait.until(EC.presence_of_element_located((By.ID, "waterfallcanvas")))
            
            # Set initial parameters
            self.set_frequency(self.current_freq)
            self.set_mode(self.current_mode)
            self.select_band(self.current_band)
            
            logger.info("Successfully connected to WebSDR")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to WebSDR: {e}")
            if self.driver:
                self.driver.quit()
                self.driver = None
            return False

    async def connect_websocket(self):
        try:
            logger.info(f"Connecting to WebSocket server at {self.config['websocket']['server_url']}")
            self.websocket = await websockets.connect(self.config['websocket']['server_url'])
            logger.info("Successfully connected to WebSocket server")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to WebSocket server: {e}")
            return False

    def set_frequency(self, freq_khz):
        if not self.driver:
            return False
        try:
            self.driver.execute_script(f"setfreq({freq_khz})")
            self.current_freq = freq_khz
            logger.info(f"Set frequency to {freq_khz} kHz")
            return True
        except Exception as e:
            logger.error(f"Failed to set frequency: {e}")
            return False

    def set_mode(self, mode):
        if not self.driver:
            return False
        try:
            self.driver.execute_script(f"setmode('{mode}')")
            self.current_mode = mode
            logger.info(f"Set mode to {mode}")
            return True
        except Exception as e:
            logger.error(f"Failed to set mode: {e}")
            return False

    def select_band(self, band):
        if not self.driver:
            return False
        try:
            self.driver.execute_script(f"setband('{band}')")
            self.current_band = band
            logger.info(f"Selected band {band}")
            return True
        except Exception as e:
            logger.error(f"Failed to select band: {e}")
            return False

    def extract_waterfall_data(self):
        if not self.driver:
            return None
        
        try:
            waterfall_canvas = self.driver.find_element(By.ID, "waterfallcanvas")
            canvas_data = self.driver.execute_script("""
                var canvas = arguments[0];
                var ctx = canvas.getContext('2d');
                var imgData = ctx.getImageData(0, 0, canvas.width, 1);
                return {
                    width: imgData.width,
                    data: Array.from(imgData.data)
                };
            """, waterfall_canvas)
            
            if canvas_data:
                width = canvas_data['width']
                row_data = canvas_data['data'][0:width*4]
                intensities = []
                for i in range(0, len(row_data), 4):
                    r, g, b = row_data[i], row_data[i+1], row_data[i+2]
                    intensities.append((r + g + b) / 3)
                return intensities
            
            return None
            
        except Exception as e:
            logger.warning(f"Failed to extract waterfall data: {e}")
            return None

    async def capture_audio(self):
        logger.info("Starting audio capture from WebSDR")
        
        try:
            def audio_callback(indata, frames, time, status):
                if status:
                    logger.warning(f"Audio callback status: {status}")
                self.audio_buffer = np.roll(self.audio_buffer, -len(indata))
                self.audio_buffer[-len(indata):] = indata[:, 0]

            with sd.InputStream(callback=audio_callback, channels=1,
                              samplerate=self.sample_rate, blocksize=1024):
                logger.info("Audio stream started")
                
                while self.running:
                    await self.process_audio_spectrum()
                    await asyncio.sleep(self.config['bridge']['spectrum_refresh'])
        
        except Exception as e:
            logger.error(f"Audio capture error: {e}")

    async def process_audio_spectrum(self):
        if not self.websocket:
            return
        
        windowed_data = self.audio_buffer * signal.windows.hann(len(self.audio_buffer))
        fft_data = np.abs(np.fft.fft(windowed_data, n=self.fft_size))
        fft_data = fft_data[:self.fft_size//2]
        
        fft_data = 20 * np.log10(fft_data + 1e-10)
        fft_data = (fft_data - np.min(fft_data)) / (np.max(fft_data) - np.min(fft_data) + 1e-10)
        
        freqs = np.fft.fftfreq(self.fft_size, 1/self.sample_rate)[:self.fft_size//2]
        center_freq = self.current_freq * 1000
        bandwidth = self.sample_rate / 2
        freqs = freqs + (center_freq - bandwidth/2)
        
        waterfall_data = self.extract_waterfall_data()
        
        data = {
            "freqs": freqs.tolist(),
            "amplitudes": fft_data.tolist(),
            "timestamp": time.time(),
            "source": "websdr",
            "websdr_info": {
                "url": self.config['websdr']['url'],
                "frequency": self.current_freq,
                "mode": self.current_mode,
                "band": self.current_band
            }
        }
        
        if waterfall_data:
            data["waterfall"] = waterfall_data
        
        try:
            await self.websocket.send(json.dumps(data))
        except Exception as e:
            logger.error(f"Failed to send data to WebSocket: {e}")

    async def run(self):
        websdr_connected = await self.connect_websdr()
        if not websdr_connected:
            logger.error("Failed to connect to WebSDR. Exiting.")
            return
        
        websocket_connected = await self.connect_websocket()
        if not websocket_connected:
            logger.error("Failed to connect to WebSocket server. Exiting.")
            self.driver.quit()
            return
        
        self.running = True
        logger.info("WebSDR bridge is running")
        
        try:
            audio_task = asyncio.create_task(self.capture_audio())
            while self.running:
                await asyncio.sleep(1)
        
        except asyncio.CancelledError:
            logger.info("Bridge task cancelled")
        except Exception as e:
            logger.error(f"Error in bridge: {e}")
        finally:
            self.running = False
            if self.driver:
                self.driver.quit()
                self.driver = None
            if self.websocket:
                await self.websocket.close()
                self.websocket = None
            logger.info("WebSDR bridge shutdown complete")

    async def stop(self):
        self.running = False

async def main():
    bridge = WebSDRBridge(CONFIG)
    await bridge.run()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("WebSDR bridge stopped by user")
        sys.exit(0)
