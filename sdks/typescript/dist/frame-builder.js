"use strict";
/**
 * Frame Builder for ATP Protocol
 */
Object.defineProperty(exports, "__esModule", { value: true });
exports.FrameBuilder = void 0;
class FrameBuilder {
    constructor(sessionId, tenantId) {
        this.sessionId = sessionId;
        this.tenantId = tenantId;
        this.msgSeqCounters = new Map();
    }
    /**
     * Build a completion request frame
     */
    buildCompletionFrame(streamId, request, msgSeq) {
        if (msgSeq === undefined) {
            msgSeq = this.getNextMsgSeq(`${this.sessionId}:${streamId}`);
        }
        // Map quality to QoS
        const qosMap = {
            high: 'gold',
            balanced: 'silver',
            low: 'bronze',
        };
        const qos = qosMap[request.quality || 'balanced'];
        // Build payload
        const payload = {
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
        const frame = {
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
    buildHeartbeatFrame(streamId) {
        const msgSeq = this.getNextMsgSeq(`${this.sessionId}:${streamId}`);
        const payload = {
            type: 'heartbeat',
            content: {},
        };
        const frame = {
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
    getNextMsgSeq(streamKey) {
        const current = this.msgSeqCounters.get(streamKey) || 0;
        const next = current + 1;
        this.msgSeqCounters.set(streamKey, next);
        return next;
    }
    /**
     * Get current message sequence number for a stream
     */
    getCurrentMsgSeq(streamId) {
        const streamKey = `${this.sessionId}:${streamId}`;
        return this.msgSeqCounters.get(streamKey) || 0;
    }
    /**
     * Reset message sequence counter for a stream
     */
    resetMsgSeq(streamId) {
        const streamKey = `${this.sessionId}:${streamId}`;
        this.msgSeqCounters.delete(streamKey);
    }
}
exports.FrameBuilder = FrameBuilder;
//# sourceMappingURL=frame-builder.js.map