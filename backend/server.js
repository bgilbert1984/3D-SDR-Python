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
const sdrSocket = new WebSocket("ws://localhost:8765");

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
    // Try to reconnect after a delay
    setTimeout(() => {
        console.log("Attempting to reconnect to Python WebSocket...");
        sdrSocket.close();
        sdrSocket = new WebSocket("ws://localhost:8765");
    }, 5000);
});

console.log("SDR WebSocket Relay initialized. Waiting for connections...");