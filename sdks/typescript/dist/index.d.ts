/**
 * Main ATP Client
 */
import { CompletionRequest, CompletionResponse, SDKConfig } from './types';
export declare class ATPClient {
    private wsClient;
    private config;
    constructor(config?: SDKConfig);
    /**
     * Initialize the client
     */
    connect(): Promise<void>;
    /**
     * Disconnect the client
     */
    disconnect(): Promise<void>;
    /**
     * Complete text using WebSocket
     */
    complete(request: CompletionRequest, _useWebsocket?: boolean): Promise<CompletionResponse>;
    /**
     * Health check
     */
    healthCheck(): Promise<boolean>;
    /**
     * Get client configuration
     */
    getConfig(): Readonly<SDKConfig>;
    /**
     * Check if client is connected
     */
    isConnected(): boolean;
}
/**
 * Convenience function to create and use ATP client
 */
export declare function complete(prompt: string, config?: SDKConfig): Promise<CompletionResponse>;
/**
 * Convenience function to create ATP client
 */
export declare function createClient(config?: SDKConfig): ATPClient;
//# sourceMappingURL=index.d.ts.map