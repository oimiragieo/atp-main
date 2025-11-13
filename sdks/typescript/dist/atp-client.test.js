"use strict";
/**
 * Basic tests for ATP TypeScript SDK
 */
Object.defineProperty(exports, "__esModule", { value: true });
const index_1 = require("../src/index");
describe('ATPClient', () => {
    let client;
    beforeEach(() => {
        client = new index_1.ATPClient({
            baseUrl: 'http://localhost:8000',
            wsUrl: 'ws://localhost:8000',
            apiKey: 'test-key',
            tenantId: 'test-tenant',
            sessionId: 'test-session'
        });
    });
    test('should create client with config', () => {
        expect(client).toBeDefined();
    });
    test('should handle completion request structure', () => {
        const request = {
            prompt: 'Test prompt',
            maxTokens: 100,
            temperature: 0.7
        };
        expect(request.prompt).toBe('Test prompt');
        expect(request.maxTokens).toBe(100);
        expect(request.temperature).toBe(0.7);
    });
});
//# sourceMappingURL=atp-client.test.js.map