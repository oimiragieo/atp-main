/**
 * Basic tests for ATP TypeScript SDK
 */

import { ATPClient } from '../src/index';
import { CompletionRequest } from '../src/types';

describe('ATPClient', () => {
  let client: ATPClient;

  beforeEach(() => {
    client = new ATPClient({
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
    const request: CompletionRequest = {
      prompt: 'Test prompt',
      maxTokens: 100,
      temperature: 0.7
    };
    expect(request.prompt).toBe('Test prompt');
    expect(request.maxTokens).toBe(100);
    expect(request.temperature).toBe(0.7);
  });
});
