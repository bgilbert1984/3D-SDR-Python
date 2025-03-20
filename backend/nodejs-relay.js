const WebSocket = require("ws");
const express = require("express");
const cors = require("cors");
const http = require("http");
const { KiwiSDRManager } = require("./backend-integration");

// Create Express app and WebSocket server
const app = express();
app.use(cors());
app.use(express.json());

const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Initialize KiwiSDR manager
const kiwiManager = new KiwiSDRManager();

// KiwiSDR API endpoints
app.post('/api/connect-kiwisdr', (req, res) => {
    const { server_address, port, frequency } = req.body;
    
    try {
        const success = kiwiManager.connect({
            server: server_address,
            port: port,
            frequency: frequency
        });
        
        if (success) {
            res.json({
                success: true,
                message: `Connected to KiwiSDR at ${server_address}:${port}`
            });
        } else {
            res.json({
                success: false,
                error: "Connection failed"
            });
        }
    } catch (error) {
        res.json({
            success: false,
            error: `Failed to connect: ${error.message}`
        });
    }
});

app.post('/api/disconnect-kiwisdr', (req, res) => {
    try {
        kiwiManager.disconnect();
        res.json({
            success: true,
            message: "Disconnected from KiwiSDR"
        });
    } catch (error) {
        res.json({
            success: false,
            error: `Failed to disconnect: ${error.message}`
        });
    }
});

app.post('/api/kiwisdr-command', (req, res) => {
    const { command, value } = req.body;
    
    try {
        const success = kiwiManager.sendCommand({ type: command, value: value });
        if (success) {
            res.json({
                success: true,
                message: `Sent command: ${command}`
            });
        } else {
            res.json({
                success: false,
                error: "Failed to send command"
            });
        }
    } catch (error) {
        res.json({
            success: false,
            error: `Failed to send command: ${error.message}`
        });
    }
});

// Forward KiwiSDR data to WebSocket clients
kiwiManager.on('data', (data) => {
    wss.clients.forEach((client) => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(JSON.stringify({
                source: 'kiwisdr',
                data: data
            }));
        }
    });
});

// Start server
const PORT = process.env.PORT || 8080;
server.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});