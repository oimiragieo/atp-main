/**
 * Main ATP Client
 */

import { ATPWebSocketClient } from './websocket-client';
import { CompletionRequest, CompletionResponse, SDKConfig, ConnectionError } from './types';

export class ATPClient {
  private wsClient: ATPWebSocketClient | null = null;
  private config: Required<SDKConfig>;

  constructor(config: SDKConfig = {}) {
    this.config = {
      baseUrl: config.baseUrl || 'http://localhost:8000',
      wsUrl: config.wsUrl || 'ws://localhost:8000',
      apiKey: config.apiKey || '',
      tenantId: config.tenantId || 'default',
      sessionId:
        config.sessionId || `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`,
      defaultTimeout: config.defaultTimeout || 30000,
      maxRetries: config.maxRetries || 3,
      retryDelay: config.retryDelay || 1000,
      heartbeatInterval: config.heartbeatInterval || 30000,
    };
  }

  /**
   * Initialize the client
   */
  async connect(): Promise<void> {
    if (this.wsClient) {
      return this.wsClient.connect();
    }

    this.wsClient = new ATPWebSocketClient(
      this.config,
      this.config.sessionId,
      this.config.tenantId
    );

    return this.wsClient.connect();
  }

  /**
   * Disconnect the client
   */
  async disconnect(): Promise<void> {
    if (this.wsClient) {
      await this.wsClient.disconnect();
      this.wsClient = null;
    }
  }

  /**
   * Complete text using WebSocket
   */
  async complete(request: CompletionRequest, _useWebsocket = true): Promise<CompletionResponse> {
    if (!this.wsClient) {
      throw new ConnectionError('Client not connected. Call connect() first.');
    }

    if (!this.wsClient.isConnected()) {
      await this.connect();
    }

    return this.wsClient.complete(request);
  }

  /**
   * Health check
   */
  async healthCheck(): Promise<boolean> {
    try {
      if (!this.wsClient) {
        await this.connect();
      }
      return this.wsClient?.isConnected() || false;
    } catch (error) {
      return false;
    }
  }

  /**
   * Get client configuration
   */
  getConfig(): Readonly<SDKConfig> {
    return { ...this.config };
  }

  /**
   * Check if client is connected
   */
  isConnected(): boolean {
    return this.wsClient?.isConnected() || false;
  }
}

/**
 * Convenience function to create and use ATP client
 */
export async function complete(prompt: string, config?: SDKConfig): Promise<CompletionResponse> {
  const client = new ATPClient(config);
  await client.connect();

  try {
    const request: CompletionRequest = { prompt };
    return await client.complete(request);
  } finally {
    await client.disconnect();
  }
}

/**
 * Convenience function to create ATP client
 */
export function createClient(config?: SDKConfig): ATPClient {
  return new ATPClient(config);
}
