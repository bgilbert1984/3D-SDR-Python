// This file extends the existing Node.js relay server to support WebSDR commands
// Add this code to backend/nodejs-relay.js or create a new module

const WebSocket = require("ws");
const express = require("express");
const cors = require("cors");
const http = require("http");

// Configuration for WebSDR integration
const WEBSDR_CONFIG = {
    // WebSDR bridge WebSocket (connects to the Python WebSDR bridge)
    bridgeUrl: "ws://localhost:8765",
    
    // Time to wait before attempting to reconnect to the bridge
    reconnectInterval: 5000,
    
    // Maximum number of reconnection attempts
    maxReconnectAttempts: 10
};

class WebSDRManager {
    constructor(wss) {
        this.wss = wss;                      // WebSocket server for clients
        this.bridgeSocket = null;            // WebSocket connection to WebSDR bridge
        this.reconnectAttempts = 0;
        this.isConnected = false;
        this.pendingCommands = [];           // Queue for commands while reconnecting
        
        // Initialize connection to WebSDR bridge
        this.connectToBridge();
    }
    
    connectToBridge() {
        console.log(`Connecting to WebSDR bridge at ${WEBSDR_CONFIG.bridgeUrl}...`);
        
        try {
            this.bridgeSocket = new WebSocket(WEBSDR_CONFIG.bridgeUrl);
            
            this.bridgeSocket.on("open", () => {
                console.log("Connected to WebSDR bridge");
                this.isConnected = true;
                this.reconnectAttempts = 0;
                
                // Process any pending commands
                if (this.pendingCommands.length > 0) {
                    console.log(`Processing ${this.pendingCommands.length} pending WebSDR commands`);
                    this.pendingCommands.forEach(cmd => this.sendCommand(cmd));
                    this.pendingCommands = [];
                }
                
                // Notify clients that WebSDR is connected
                this.broadcastStatus("connected");
            });
            
            this.bridgeSocket.on("message", (data) => {
                try {
                    // Forward WebSDR data to all clients
                    this.broadcastToClients(data);
                } catch (error) {
                    console.error("Error processing WebSDR bridge data:", error.message);
                }
            });
            
            this.bridgeSocket.on("close", () => {
                console.log("WebSDR bridge connection closed");
                this.isConnected = false;
                this.broadcastStatus("disconnected");
                this.scheduleReconnect();
            });
            
            this.bridgeSocket.on("error", (error) => {
                console.error("WebSDR bridge error:", error.message);
                this.isConnected = false;
                this.broadcastStatus("error");
            });
            
        } catch (error) {
            console.error("Failed to connect to WebSDR bridge:", error.message);
            this.scheduleReconnect();
        }
    }
    
    scheduleReconnect() {
        // Don't try to reconnect if we've exceeded the maximum attempts
        if (this.reconnectAttempts >= WEBSDR_CONFIG.maxReconnectAttempts) {
            console.log("Maximum reconnection attempts reached. Giving up.");
            return;
        }
        
        this.reconnectAttempts++;
        console.log(`Scheduling WebSDR bridge reconnection attempt ${this.reconnectAttempts} in ${WEBSDR_CONFIG.reconnectInterval / 1000} seconds...`);
        
        setTimeout(() => {
            console.log("Attempting to reconnect to WebSDR bridge...");
            this.connectToBridge();
        }, WEBSDR_CONFIG.reconnectInterval);
    }
    
    sendCommand(command) {
        if (!this.isConnected || !this.bridgeSocket) {
            console.log("WebSDR bridge not connected. Queuing command for later.");
            this.pendingCommands.push(command);
            return false;
        }
        
        try {
            this.bridgeSocket.send(JSON.stringify(command));
            console.log(`Sent command to WebSDR bridge: ${command.type} - ${JSON.stringify(command.value)}`);
            return true;
        } catch (error) {
            console.error("Error sending command to WebSDR bridge:", error.message);
            return false;
        }
    }
    
    handleClientCommand(command, client) {
        // Validate command format
        if (!command.command || typeof command.command !== 'string') {
            console.error("Invalid WebSDR command:", command);
            return false;
        }
        
        // Create bridge command object
        const bridgeCommand = {
            type: 'command',
            command: command.command,
            value: command.value
        };
        
        // Send to bridge
        const result = this.sendCommand(bridgeCommand);
        
        // Send response to the client
        try {
            client.send(JSON.stringify({
                type: 'websdr_command_response',
                command: command.command,
                success: result,
                timestamp: Date.now()
            }));
        } catch (error) {
            console.error("Error sending response to client:", error.message);
        }
        
        return result;
    }
    
    broadcastToClients(data) {
        this.wss.clients.forEach(client => {
            if (client.readyState === WebSocket.OPEN) {
                try {
                    client.send(data);
                } catch (error) {
                    console.error("Error broadcasting to client:", error.message);
                }
            }
        });
    }
    
    broadcastStatus(status) {
        const statusMessage = JSON.stringify({
            type: 'status',
            status: status,
            timestamp: Date.now()
        });
        
        this.broadcastToClients(statusMessage);
    }
}

// Function to extend the existing relay server with WebSDR support
function addWebSDRSupport(app, wss) {
    // Create WebSDR manager
    const webSDRManager = new WebSDRManager(wss);
    
    // Add WebSDR status endpoint
    app.get("/websdr-status", (req, res) => {
        res.json({
            connected: webSDRManager.isConnected,
            pendingCommands: webSDRManager.pendingCommands.length,
            reconnectAttempts: webSDRManager.reconnectAttempts
        });
    });
    
    // Handle WebSDR commands from clients
    wss.on("connection", (client) => {
        client.on("message", (message) => {
            try {
                const msg = JSON.parse(message);
                
                // Handle WebSDR specific commands
                if (msg.type === "websdr_command") {
                    webSDRManager.handleClientCommand(msg, client);
                }
            } catch (e) {
                console.error("Error processing client message:", e.message);
            }
        });
    });
    
    console.log("WebSDR support added to relay server");
    return webSDRManager;
}

// --- Example of how to integrate with existing server code ---

// If this is included as a module:
module.exports = {
    addWebSDRSupport
};

/* 
// If directly modifying the existing server file, add this code:

// After creating your WebSocket server (wss) and Express app:
const webSDRManager = addWebSDRSupport(app, wss);

// Example of how to handle process termination with WebSDR:
process.on("SIGINT", () => {
    console.log("Shutting down...");
    
    if (webSDRManager.bridgeSocket) {
        webSDRManager.bridgeSocket.close();
    }
    
    // Other cleanup...
    
    wss.close(() => {
        console.log("WebSocket server closed");
        process.exit(0);
    });
});
*/
