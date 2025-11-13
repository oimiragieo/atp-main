/**
 * ATP WebSocket Client
 */

import WebSocket from 'ws';
import { EventEmitter } from 'events';
import {
  Frame,
  CompletionRequest,
  CompletionResponse,
  SDKConfig,
  ConnectionError,
  ATPClientError,
} from './types';
import { FrameBuilder } from './frame-builder';

export class ATPWebSocketClient extends EventEmitter {
  private ws: WebSocket | null = null;
  private connected = false;
  private reconnecting = false;
  private frameBuilder: FrameBuilder;
  private responseHandlers: Map<
    string,
    { resolve: Function; reject: Function; timeout: NodeJS.Timeout }
  > = new Map();
  private heartbeatInterval: NodeJS.Timeout | null = null;
  private reconnectTimeout: NodeJS.Timeout | null = null;

  constructor(
    private config: SDKConfig,
    sessionId: string,
    tenantId: string
  ) {
    super();
    this.frameBuilder = new FrameBuilder(sessionId, tenantId);
  }

  /**
   * Connect to ATP Router
   */
  async connect(): Promise<void> {
    if (this.connected) {
      return;
    }

    return new Promise((resolve, reject) => {
      const wsUrl = this.config.wsUrl || 'ws://localhost:8000';
      const url = `${wsUrl}/ws?session_id=${this.config.sessionId}&tenant_id=${this.config.tenantId}`;

      this.ws = new WebSocket(url);

      this.ws.on('open', () => {
        this.connected = true;
        this.startHeartbeat();
        this.emit('connected');
        resolve();
      });

      this.ws.on('message', (data: Buffer) => {
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
          reject(new ConnectionError(`WebSocket connection failed: ${error.message}`));
        }
      });

      // Connection timeout
      setTimeout(() => {
        if (!this.connected) {
          this.ws?.close();
          reject(new ConnectionError('WebSocket connection timeout'));
        }
      }, this.config.defaultTimeout || 30000);
    });
  }

  /**
   * Disconnect from ATP Router
   */
  async disconnect(): Promise<void> {
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
      handler.reject(new ConnectionError('Connection closed'));
    }
    this.responseHandlers.clear();
  }

  /**
   * Send a frame and wait for response
   */
  async sendFrame(frame: Frame): Promise<unknown> {
    if (!this.connected || !this.ws) {
      throw new ConnectionError('Not connected to ATP Router');
    }

    return new Promise((resolve, reject) => {
      const requestId = `${frame.streamId}:${frame.msgSeq}`;

      // Set up timeout
      const timeout = setTimeout(() => {
        this.responseHandlers.delete(requestId);
        reject(new ATPClientError(`Request timeout after ${this.config.defaultTimeout}ms`));
      }, this.config.defaultTimeout || 30000);

      // Store response handler
      this.responseHandlers.set(requestId, { resolve, reject, timeout });

      // Send frame
      try {
        if (!this.ws) {
          throw new ATPClientError('WebSocket connection not established');
        }
        this.ws.send(JSON.stringify(frame));
      } catch (error) {
        clearTimeout(timeout);
        this.responseHandlers.delete(requestId);
        reject(new ATPClientError(`Failed to send frame: ${(error as Error).message}`));
      }
    });
  }

  /**
   * Send completion request
   */
  async complete(request: CompletionRequest, streamId?: string): Promise<CompletionResponse> {
    const stream =
      streamId || `completion_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
    const frame = this.frameBuilder.buildCompletionFrame(stream, request);

    const response = (await this.sendFrame(frame)) as {
      type: string;
      content?: {
        text?: string;
        modelUsed?: string;
        tokensIn?: number;
        tokensOut?: number;
        costUsd?: number;
        qualityScore?: number;
      };
      error?: { message?: string };
    };

    if (response.type === 'error') {
      throw new ATPClientError(`ATP Router error: ${response.error?.message || 'Unknown error'}`);
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
  private handleMessage(data: Buffer): void {
    try {
      const frame: Frame = JSON.parse(data.toString());

      // Handle response frames
      if (frame.payload.type === 'completion_response' || frame.payload.type === 'error') {
        const requestId = `${frame.streamId}:${frame.msgSeq}`;
        const handler = this.responseHandlers.get(requestId);

        if (handler) {
          clearTimeout(handler.timeout);
          this.responseHandlers.delete(requestId);

          if (frame.payload.type === 'error') {
            const errorContent = frame.payload.content as { message?: string };
            handler.reject(new ATPClientError(errorContent?.message || 'Unknown error'));
          } else {
            handler.resolve(frame.payload.content);
          }
        }
      }

      // Emit frame event for external handling
      this.emit('frame', frame);
    } catch (error) {
      this.emit(
        'error',
        new ATPClientError(`Failed to parse message: ${(error as Error).message}`)
      );
    }
  }

  /**
   * Start heartbeat
   */
  private startHeartbeat(): void {
    const interval = this.config.heartbeatInterval || 30000;

    this.heartbeatInterval = setInterval(async () => {
      if (this.connected) {
        try {
          const heartbeatFrame = this.frameBuilder.buildHeartbeatFrame('heartbeat');
          await this.sendFrame(heartbeatFrame);
        } catch (error) {
          this.emit('error', error);
        }
      }
    }, interval);
  }

  /**
   * Stop heartbeat
   */
  private stopHeartbeat(): void {
    if (this.heartbeatInterval) {
      clearInterval(this.heartbeatInterval);
      this.heartbeatInterval = null;
    }
  }

  /**
   * Check if client is connected
   */
  isConnected(): boolean {
    return this.connected;
  }
}
