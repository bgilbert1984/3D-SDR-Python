const WebSocket = require("ws");
const express = require("express");
const cors = require("cors");

const app = express();
const PORT = 4000;
const WSS_PORT = 8080;
const SDR_WEBSOCKET_URL = "ws://localhost:8765";

// Start Web Server
app.use(cors());
app.get("/", (req, res) => res.send("SDR FCC Monitor WebSocket Relay Active"));
app.get("/status", (req, res) => {
    res.json({
        status: "active",
        connections: wss.clients.size,
        sdrConnected: sdrSocket.readyState === WebSocket.OPEN
    });
});

app.listen(PORT, () => console.log(`HTTP Server running on port ${PORT}`));

// WebSocket Server for Frontend Clients
const wss = new WebSocket.Server({ port: WSS_PORT });
console.log(`WebSocket Server running on port ${WSS_PORT}`);

// Connect to Python SDR WebSocket
let sdrSocket;
let reconnectTimeout;
let lastViolations = [];

function connectToSDR() {
    if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
    }
    
    console.log(`Connecting to SDR WebSocket at ${SDR_WEBSOCKET_URL}...`);
    
    sdrSocket = new WebSocket(SDR_WEBSOCKET_URL);
    
    sdrSocket.on("open", () => {
        console.log("Connected to Python SDR WebSocket server");
        broadcastStatus("connected");
    });
    
    sdrSocket.on("message", (data) => {
        try {
            // Parse data to extract violation information for logging
            const jsonData = JSON.parse(data.toString());
            const violations = jsonData.violations || [];
            
            // Log violations for monitoring
            if (violations.length > 0) {
                lastViolations = violations;
                console.log(`ALERT: Detected ${violations.length} potential FCC violations:`);
                violations.forEach(v => {
                    console.log(`  - ${v.frequency_mhz.toFixed(3)} MHz (Power: ${(v.power * 100).toFixed(1)}%)`);
                });
            }
            
            // Broadcast to all connected clients
            broadcastToClients(data);
            
        } catch (error) {
            console.error("Error processing SDR data:", error.message);
            // Forward the raw data anyway
            broadcastToClients(data);
        }
    });
    
    sdrSocket.on("close", () => {
        console.log("SDR WebSocket connection closed");
        broadcastStatus("disconnected");
        scheduleReconnect();
    });
    
    sdrSocket.on("error", (error) => {
        console.error("SDR WebSocket Error:", error.message);
        broadcastStatus("error");
        scheduleReconnect();
    });
}

function scheduleReconnect() {
    console.log("Scheduling reconnection to SDR WebSocket in 5 seconds...");
    
    if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
    }
    
    reconnectTimeout = setTimeout(() => {
        console.log("Attempting to reconnect to SDR WebSocket...");
        connectToSDR();
    }, 5000);
}

function broadcastToClients(data) {
    const clientCount = wss.clients.size;
    
    if (clientCount > 0) {
        wss.clients.forEach((client) => {
            if (client.readyState === WebSocket.OPEN) {
                client.send(data);
            }
        });
    }
}

function broadcastStatus(status) {
    const statusMsg = JSON.stringify({
        type: "status",
        status: status,
        timestamp: Date.now()
    });
    
    wss.clients.forEach((client) => {
        if (client.readyState === WebSocket.OPEN) {
            client.send(statusMsg);
        }
    });
}

// Frontend WebSocket Server Events
wss.on("connection", (client, req) => {
    const clientIp = req.socket.remoteAddress;
    console.log(`New client connected from ${clientIp}`);
    
    // Send current status to the new client
    client.send(JSON.stringify({
        type: "status",
        status: sdrSocket && sdrSocket.readyState === WebSocket.OPEN ? "connected" : "disconnected",
        timestamp: Date.now(),
        lastViolations: lastViolations
    }));
    
    client.on("message", (message) => {
        try {
            const msg = JSON.parse(message);
            
            // Handle client requests
            if (msg.type === "getStatus") {
                client.send(JSON.stringify({
                    type: "status",
                    status: sdrSocket && sdrSocket.readyState === WebSocket.OPEN ? "connected" : "disconnected",
                    timestamp: Date.now(),
                    lastViolations: lastViolations
                }));
            }
        } catch (e) {
            console.error("Error processing client message:", e.message);
        }
    });
    
    client.on("close", () => {
        console.log(`Client disconnected from ${clientIp}`);
    });
});

// Start connection to SDR WebSocket
connectToSDR();

// Handle process termination
process.on("SIGINT", () => {
    console.log("Shutting down...");
    
    if (reconnectTimeout) {
        clearTimeout(reconnectTimeout);
    }
    
    if (sdrSocket) {
        sdrSocket.close();
    }
    
    wss.close(() => {
        console.log("WebSocket server closed");
        process.exit(0);
    });
});

console.log("SDR FCC Monitor WebSocket Relay initialized. Waiting for connections...");