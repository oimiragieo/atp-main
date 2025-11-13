/**
 * Frame Builder for ATP Protocol
 */
import { Frame, CompletionRequest } from './types';
export declare class FrameBuilder {
    private sessionId;
    private tenantId;
    private msgSeqCounters;
    constructor(sessionId: string, tenantId: string);
    /**
     * Build a completion request frame
     */
    buildCompletionFrame(streamId: string, request: CompletionRequest, msgSeq?: number): Frame;
    /**
     * Build a heartbeat frame
     */
    buildHeartbeatFrame(streamId: string): Frame;
    /**
     * Get next message sequence number for a stream
     */
    private getNextMsgSeq;
    /**
     * Get current message sequence number for a stream
     */
    getCurrentMsgSeq(streamId: string): number;
    /**
     * Reset message sequence counter for a stream
     */
    resetMsgSeq(streamId: string): void;
}
//# sourceMappingURL=frame-builder.d.ts.map