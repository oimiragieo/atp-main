/**
 * ATP WebSocket Client
 */
/// <reference types="node" />
import { EventEmitter } from 'events';
import { Frame, CompletionRequest, CompletionResponse, SDKConfig } from './types';
export declare class ATPWebSocketClient extends EventEmitter {
    private config;
    private ws;
    private connected;
    private reconnecting;
    private frameBuilder;
    private responseHandlers;
    private heartbeatInterval;
    private reconnectTimeout;
    constructor(config: SDKConfig, sessionId: string, tenantId: string);
    /**
     * Connect to ATP Router
     */
    connect(): Promise<void>;
    /**
     * Disconnect from ATP Router
     */
    disconnect(): Promise<void>;
    /**
     * Send a frame and wait for response
     */
    sendFrame(frame: Frame): Promise<unknown>;
    /**
     * Send completion request
     */
    complete(request: CompletionRequest, streamId?: string): Promise<CompletionResponse>;
    /**
     * Handle incoming WebSocket messages
     */
    private handleMessage;
    /**
     * Start heartbeat
     */
    private startHeartbeat;
    /**
     * Stop heartbeat
     */
    private stopHeartbeat;
    /**
     * Check if client is connected
     */
    isConnected(): boolean;
}
//# sourceMappingURL=websocket-client.d.ts.map