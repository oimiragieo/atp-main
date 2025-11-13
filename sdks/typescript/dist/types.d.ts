/**
 * ATP Router Protocol Types and Interfaces
 */
export interface Window {
    maxParallel: number;
    maxTokens: number;
    maxUsdMicros: number;
}
export interface CostEst {
    inTokens: number;
    outTokens: number;
    usdMicros: number;
}
export interface Meta {
    taskType?: string;
    languages?: string[];
    risk?: string;
    dataScope?: string[];
    trace?: unknown;
    toolPermissions?: string[];
    environmentId?: string;
    securityGroups?: string[];
}
export interface Payload {
    type: string;
    content: unknown;
    confidence?: number;
    costEst?: CostEst;
    checksum?: string;
    expiryMs?: number;
    sessionId?: string;
    personaId?: string;
    cloneId?: number;
    seq?: number;
}
export interface Frame {
    v: number;
    sessionId: string;
    streamId: string;
    msgSeq: number;
    fragSeq: number;
    flags: string[];
    qos: 'gold' | 'silver' | 'bronze';
    ttl: number;
    window: Window;
    meta: Meta;
    payload: Payload;
    sig?: string;
}
export interface CompletionRequest {
    prompt: string;
    maxTokens?: number;
    quality?: 'high' | 'balanced' | 'low';
    latencySloMs?: number;
    temperature?: number;
    stream?: boolean;
    tenant?: string;
    conversationId?: string;
    consistencyLevel?: 'EVENTUAL' | 'RYW' | 'STRONG';
}
export interface CompletionResponse {
    text: string;
    modelUsed: string;
    tokensIn: number;
    tokensOut: number;
    costUsd: number;
    qualityScore: number;
    finished: boolean;
    error?: string;
}
export interface SDKConfig {
    baseUrl?: string;
    wsUrl?: string;
    apiKey?: string;
    tenantId?: string;
    sessionId?: string;
    defaultTimeout?: number;
    maxRetries?: number;
    retryDelay?: number;
    heartbeatInterval?: number;
}
export declare class ATPClientError extends Error {
    code?: string | undefined;
    constructor(message: string, code?: string | undefined);
}
export declare class ConnectionError extends ATPClientError {
    constructor(message: string);
}
export declare class AuthenticationError extends ATPClientError {
    constructor(message: string);
}
export declare class ValidationError extends ATPClientError {
    constructor(message: string);
}
//# sourceMappingURL=types.d.ts.map