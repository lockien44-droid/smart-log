// src/socket.js

import { io } from "socket.io-client";

const SOCKET_URL =
    import.meta.env.VITE_SOCKET_URL ||
    "http://127.0.0.1:8000";

const socket = io(SOCKET_URL, {
    transports: ["websocket"],
    autoConnect: true,

    reconnection: true,
    reconnectionAttempts: Infinity,
    reconnectionDelay: 1000,
    reconnectionDelayMax: 5000,

    timeout: 10000
});

// =========================
// CONNECTION EVENTS
// =========================

socket.on("connect", () => {
    console.log(
        "[SOCKET] Connected:",
        socket.id
    );
});

socket.on("disconnect", (reason) => {
    console.log(
        "[SOCKET] Disconnected:",
        reason
    );
});

socket.on("connect_error", (error) => {
    console.error(
        "[SOCKET] Connection Error:",
        error.message
    );
});

socket.on("reconnect", (attempt) => {
    console.log(
        "[SOCKET] Reconnected:",
        attempt
    );
});

// =========================
// DASHBOARD EVENT
// =========================

socket.on("dashboard_update", (data) => {
    console.log(
        "[DASHBOARD UPDATE]",
        data
    );
});

export default socket;