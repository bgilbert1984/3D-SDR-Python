const WebSocket = require("ws");
const express = require("express");
const cors = require("cors");
const http = require("http");
const { addWebSDRSupport } = require("./backend-integration");

// Create Express app and WebSocket server
const app = express();
app.use(cors());
const server = http.createServer(app);
const wss = new WebSocket.Server({ server });

// Add WebSDR support
const webSDRManager = addWebSDRSupport(app, wss);

// Start server
const PORT = process.env.PORT || 8080;
server.listen(PORT, () => {
    console.log(`Server is running on port ${PORT}`);
});