"use strict";
/**
 * ATP WebSocket Client
 */
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.ATPWebSocketClient = void 0;
const ws_1 = __importDefault(require("ws"));
const events_1 = require("events");
const types_1 = require("./types");
const frame_builder_1 = require("./frame-builder");
class ATPWebSocketClient extends events_1.EventEmitter {
    constructor(config, sessionId, tenantId) {
        super();
        this.config = config;
        this.ws = null;
        this.connected = false;
        this.reconnecting = false;
        this.responseHandlers = new Map();
        this.heartbeatInterval = null;
        this.reconnectTimeout = null;
        this.frameBuilder = new frame_builder_1.FrameBuilder(sessionId, tenantId);
    }
    /**
     * Connect to ATP Router
     */
    async connect() {
        if (this.connected) {
            return;
        }
        return new Promise((resolve, reject) => {
            const wsUrl = this.config.wsUrl || 'ws://localhost:8000';
            const url = `${wsUrl}/ws?session_id=${this.config.sessionId}&tenant_id=${this.config.tenantId}`;
            this.ws = new ws_1.default(url);
            this.ws.on('open', () => {
                this.connected = true;
                this.startHeartbeat();
                this.emit('connected');
                resolve();
            });
            this.ws.on('message', (data) => {
                this.handleMessage(data);
            });
            this.ws.on('close', () => {
                this.connected = false;
                this.stopHeartbeat();
                this.emit('disconnected');
            });
            this.ws.on('error', (error) => {
                this.emit('error', error);
                if (!this.connected) {
                    reject(new types_1.ConnectionError(`WebSocket connection failed: ${error.message}`));
                }
            });
            // Connection timeout
            setTimeout(() => {
                if (!this.connected) {
                    this.ws?.close();
                    reject(new types_1.ConnectionError('WebSocket connection timeout'));
                }
            }, this.config.defaultTimeout || 30000);
        });
    }
    /**
     * Disconnect from ATP Router
     */
    async disconnect() {
        if (this.reconnectTimeout) {
            clearTimeout(this.reconnectTimeout);
            this.reconnectTimeout = null;
        }
        this.stopHeartbeat();
        if (this.ws) {
            this.ws.close();
            this.ws = null;
        }
        this.connected = false;
        // Clean up pending response handlers
        for (const [_requestId, handler] of this.responseHandlers) {
            clearTimeout(handler.timeout);
            handler.reject(new types_1.ConnectionError('Connection closed'));
        }
        this.responseHandlers.clear();
    }
    /**
     * Send a frame and wait for response
     */
    async sendFrame(frame) {
        if (!this.connected || !this.ws) {
            throw new types_1.ConnectionError('Not connected to ATP Router');
        }
        return new Promise((resolve, reject) => {
            const requestId = `${frame.streamId}:${frame.msgSeq}`;
            // Set up timeout
            const timeout = setTimeout(() => {
                this.responseHandlers.delete(requestId);
                reject(new types_1.ATPClientError(`Request timeout after ${this.config.defaultTimeout}ms`));
            }, this.config.defaultTimeout || 30000);
            // Store response handler
            this.responseHandlers.set(requestId, { resolve, reject, timeout });
            // Send frame
            try {
                if (!this.ws) {
                    throw new types_1.ATPClientError('WebSocket connection not established');
                }
                this.ws.send(JSON.stringify(frame));
            }
            catch (error) {
                clearTimeout(timeout);
                this.responseHandlers.delete(requestId);
                reject(new types_1.ATPClientError(`Failed to send frame: ${error.message}`));
            }
        });
    }
    /**
     * Send completion request
     */
    async complete(request, streamId) {
        const stream = streamId || `completion_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
        const frame = this.frameBuilder.buildCompletionFrame(stream, request);
        const response = (await this.sendFrame(frame));
        if (response.type === 'error') {
            throw new types_1.ATPClientError(`ATP Router error: ${response.error?.message || 'Unknown error'}`);
        }
        return {
            text: response.content?.text || '',
            modelUsed: response.content?.modelUsed || 'unknown',
            tokensIn: response.content?.tokensIn || 0,
            tokensOut: response.content?.tokensOut || 0,
            costUsd: response.content?.costUsd || 0,
            qualityScore: response.content?.qualityScore || 0,
            finished: true,
        };
    }
    /**
     * Handle incoming WebSocket messages
     */
    handleMessage(data) {
        try {
            const frame = JSON.parse(data.toString());
            // Handle response frames
            if (frame.payload.type === 'completion_response' || frame.payload.type === 'error') {
                const requestId = `${frame.streamId}:${frame.msgSeq}`;
                const handler = this.responseHandlers.get(requestId);
                if (handler) {
                    clearTimeout(handler.timeout);
                    this.responseHandlers.delete(requestId);
                    if (frame.payload.type === 'error') {
                        const errorContent = frame.payload.content;
                        handler.reject(new types_1.ATPClientError(errorContent?.message || 'Unknown error'));
                    }
                    else {
                        handler.resolve(frame.payload.content);
                    }
                }
            }
            // Emit frame event for external handling
            this.emit('frame', frame);
        }
        catch (error) {
            this.emit('error', new types_1.ATPClientError(`Failed to parse message: ${error.message}`));
        }
    }
    /**
     * Start heartbeat
     */
    startHeartbeat() {
        const interval = this.config.heartbeatInterval || 30000;
        this.heartbeatInterval = setInterval(async () => {
            if (this.connected) {
                try {
                    const heartbeatFrame = this.frameBuilder.buildHeartbeatFrame('heartbeat');
                    await this.sendFrame(heartbeatFrame);
                }
                catch (error) {
                    this.emit('error', error);
                }
            }
        }, interval);
    }
    /**
     * Stop heartbeat
     */
    stopHeartbeat() {
        if (this.heartbeatInterval) {
            clearInterval(this.heartbeatInterval);
            this.heartbeatInterval = null;
        }
    }
    /**
     * Check if client is connected
     */
    isConnected() {
        return this.connected;
    }
}
exports.ATPWebSocketClient = ATPWebSocketClient;
//# sourceMappingURL=websocket-client.js.map