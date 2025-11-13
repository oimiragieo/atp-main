/**
 * Frame Builder for ATP Protocol
 */

import { Frame, Payload, CompletionRequest } from './types';

export class FrameBuilder {
  private msgSeqCounters: Map<string, number> = new Map();

  constructor(
    private sessionId: string,
    private tenantId: string
  ) {}

  /**
   * Build a completion request frame
   */
  buildCompletionFrame(streamId: string, request: CompletionRequest, msgSeq?: number): Frame {
    if (msgSeq === undefined) {
      msgSeq = this.getNextMsgSeq(`${this.sessionId}:${streamId}`);
    }

    // Map quality to QoS
    const qosMap = {
      high: 'gold' as const,
      balanced: 'silver' as const,
      low: 'bronze' as const,
    };
    const qos = qosMap[request.quality || 'balanced'];

    // Build payload
    const payload: Payload = {
      type: 'completion',
      content: {
        prompt: request.prompt,
        maxTokens: request.maxTokens || 512,
        quality: request.quality || 'balanced',
        latencySloMs: request.latencySloMs || 5000,
        temperature: request.temperature || 0.7,
        stream: request.stream !== false,
        conversationId: request.conversationId,
        consistencyLevel: request.consistencyLevel || 'EVENTUAL',
      },
    };

    const frame: Frame = {
      v: 1,
      sessionId: this.sessionId,
      streamId,
      msgSeq,
      fragSeq: 0,
      flags: [],
      qos,
      ttl: 8,
      window: {
        maxParallel: 4,
        maxTokens: 50000,
        maxUsdMicros: 1000000,
      },
      meta: {
        taskType: 'completion',
        environmentId: this.tenantId,
      },
      payload,
    };

    return frame;
  }

  /**
   * Build a heartbeat frame
   */
  buildHeartbeatFrame(streamId: string): Frame {
    const msgSeq = this.getNextMsgSeq(`${this.sessionId}:${streamId}`);

    const payload: Payload = {
      type: 'heartbeat',
      content: {},
    };

    const frame: Frame = {
      v: 1,
      sessionId: this.sessionId,
      streamId,
      msgSeq,
      fragSeq: 0,
      flags: [],
      qos: 'bronze',
      ttl: 8,
      window: {
        maxParallel: 4,
        maxTokens: 50000,
        maxUsdMicros: 1000000,
      },
      meta: {
        taskType: 'heartbeat',
        environmentId: this.tenantId,
      },
      payload,
    };

    return frame;
  }

  /**
   * Get next message sequence number for a stream
   */
  private getNextMsgSeq(streamKey: string): number {
    const current = this.msgSeqCounters.get(streamKey) || 0;
    const next = current + 1;
    this.msgSeqCounters.set(streamKey, next);
    return next;
  }

  /**
   * Get current message sequence number for a stream
   */
  getCurrentMsgSeq(streamId: string): number {
    const streamKey = `${this.sessionId}:${streamId}`;
    return this.msgSeqCounters.get(streamKey) || 0;
  }

  /**
   * Reset message sequence counter for a stream
   */
  resetMsgSeq(streamId: string): void {
    const streamKey = `${this.sessionId}:${streamId}`;
    this.msgSeqCounters.delete(streamKey);
  }
}
