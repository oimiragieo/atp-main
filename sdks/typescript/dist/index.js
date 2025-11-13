"use strict";
/**
 * Main ATP Client
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.createClient = exports.complete = exports.ATPClient = void 0;
const websocket_client_1 = require("./websocket-client");
const types_1 = require("./types");
class ATPClient {
    constructor(config = {}) {
        this.wsClient = null;
        this.config = {
            baseUrl: config.baseUrl || 'http://localhost:8000',
            wsUrl: config.wsUrl || 'ws://localhost:8000',
            apiKey: config.apiKey || '',
            tenantId: config.tenantId || 'default',
            sessionId: config.sessionId || `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
            defaultTimeout: config.defaultTimeout || 30000,
            maxRetries: config.maxRetries || 3,
            retryDelay: config.retryDelay || 1000,
            heartbeatInterval: config.heartbeatInterval || 30000,
        };
    }
    /**
     * Initialize the client
     */
    async connect() {
        if (this.wsClient) {
            return this.wsClient.connect();
        }
        this.wsClient = new websocket_client_1.ATPWebSocketClient(this.config, this.config.sessionId, this.config.tenantId);
        return this.wsClient.connect();
    }
    /**
     * Disconnect the client
     */
    async disconnect() {
        if (this.wsClient) {
            await this.wsClient.disconnect();
            this.wsClient = null;
        }
    }
    /**
     * Complete text using WebSocket
     */
    async complete(request, _useWebsocket = true) {
        if (!this.wsClient) {
            throw new types_1.ConnectionError('Client not connected. Call connect() first.');
        }
        if (!this.wsClient.isConnected()) {
            await this.connect();
        }
        return this.wsClient.complete(request);
    }
    /**
     * Health check
     */
    async healthCheck() {
        try {
            if (!this.wsClient) {
                await this.connect();
            }
            return this.wsClient?.isConnected() || false;
        }
        catch (error) {
            return false;
        }
    }
    /**
     * Get client configuration
     */
    getConfig() {
        return { ...this.config };
    }
    /**
     * Check if client is connected
     */
    isConnected() {
        return this.wsClient?.isConnected() || false;
    }
}
exports.ATPClient = ATPClient;
/**
 * Convenience function to create and use ATP client
 */
async function complete(prompt, config) {
    const client = new ATPClient(config);
    await client.connect();
    try {
        const request = { prompt };
        return await client.complete(request);
    }
    finally {
        await client.disconnect();
    }
}
exports.complete = complete;
/**
 * Convenience function to create ATP client
 */
function createClient(config) {
    return new ATPClient(config);
}
exports.createClient = createClient;
//# sourceMappingURL=index.js.map