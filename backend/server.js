const WebSocket = require("ws");
const express = require("express");

const app = express();
const PORT = 4000;
const WSS_PORT = 8080;

// Start Web Server
app.use(require("cors")());
app.get("/", (req, res) => res.send("SDR WebSocket Relay Active"));
app.listen(PORT, () => console.log(`HTTP Server running on port ${PORT}`));

// WebSocket Server for Frontend
const wss = new WebSocket.Server({ port: WSS_PORT });
console.log(`WebSocket Server running on port ${WSS_PORT}`);

// Connect to Python SDR WebSocket
let sdrSocket = null;
let kiwiSocket = null;

function connectToSDR() {
    try {
        sdrSocket = new WebSocket("ws://localhost:8765");
        
        sdrSocket.on("open", () => {
            console.log("Successfully connected to Python SDR WebSocket");
        });

        sdrSocket.on("message", (data) => {
            console.log("Received SDR Data:", data.length, "bytes");
            // Broadcast to all connected clients
            wss.clients.forEach((client) => {
                if (client.readyState === WebSocket.OPEN) {
                    client.send(data);
                }
            });
        });

        // Handle connection errors
        sdrSocket.on("error", (error) => {
            console.error("WebSocket Error:", error.message);
            setTimeout(reconnectToSDR, 5000);
        });

        sdrSocket.on("close", () => {
            console.log("SDR WebSocket connection closed");
            setTimeout(reconnectToSDR, 5000);
        });
    } catch (error) {
        console.error("Error creating WebSocket connection:", error);
        setTimeout(reconnectToSDR, 5000);
    }
}

function connectToKiwiSDR(config) {
    try {
        kiwiSocket = new WebSocket(`ws://${config.server}:${config.port}/kiwi`);
        
        kiwiSocket.on("open", () => {
            console.log("Successfully connected to KiwiSDR WebSocket");
            // Initial setup commands
            kiwiSocket.send(JSON.stringify({
                type: 'mode',
                value: 'AM'
            }));
            kiwiSocket.send(JSON.stringify({
                type: 'frequency',
                value: config.frequency
            }));
        });

        kiwiSocket.on("message", (data) => {
            // Process KiwiSDR data and forward to clients
            wss.clients.forEach((client) => {
                if (client.readyState === WebSocket.OPEN) {
                    const message = {
                        source: 'kiwisdr',
                        data: data
                    };
                    client.send(JSON.stringify(message));
                }
            });
        });

        kiwiSocket.on("error", (error) => {
            console.error("KiwiSDR WebSocket Error:", error.message);
        });

        kiwiSocket.on("close", () => {
            console.log("KiwiSDR WebSocket connection closed");
            kiwiSocket = null;
        });
    } catch (error) {
        console.error("Error creating KiwiSDR connection:", error);
        kiwiSocket = null;
    }
}

function reconnectToSDR() {
    console.log("Attempting to reconnect to Python WebSocket...");
    if (sdrSocket) {
        sdrSocket.removeAllListeners();
        try {
            sdrSocket.terminate();
        } catch (error) {
            console.error("Error closing existing connection:", error);
        }
    }
    connectToSDR();
}

// Handle WebSocket client connections
wss.on("connection", (ws) => {
    console.log("New client connected");

    ws.on("message", (message) => {
        try {
            const data = JSON.parse(message);
            if (data.type === 'kiwisdr_command') {
                if (kiwiSocket && kiwiSocket.readyState === WebSocket.OPEN) {
                    kiwiSocket.send(JSON.stringify(data));
                }
            }
        } catch (error) {
            console.error("Error processing message:", error);
        }
    });

    ws.on("close", () => {
        console.log("Client disconnected");
    });
});

// Initial connection
connectToSDR();
console.log("SDR WebSocket Relay initialized. Waiting for connections...");