// Copyright 2025 ATP Project Contributors
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * K6 Load Testing Scripts for ATP Platform
 * Comprehensive performance testing under enterprise load conditions.
 */

import http from 'k6/http';
import ws from 'k6/ws';
import { check, group, sleep } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';
import { randomString, randomIntBetween } from 'https://jslib.k6.io/k6-utils/1.2.0/index.js';

// Custom metrics
const chatCompletionDuration = new Trend('chat_completion_duration');
const chatCompletionFailureRate = new Rate('chat_completion_failures');
const streamingDuration = new Trend('streaming_duration');
const streamingFailureRate = new Rate('streaming_failures');
const apiGatewayDuration = new Trend('api_gateway_duration');
const rateLimitHits = new Counter('rate_limit_hits');

// Configuration
const BASE_URL = __ENV.BASE_URL || 'http://localhost:8000';
const API_KEY = __ENV.API_KEY || 'test-api-key';
const WS_URL = __ENV.WS_URL || 'ws://localhost:8000';

// Test scenarios
export const options = {
  scenarios: {
    // Baseline load test
    baseline_load: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '2m', target: 10 },   // Ramp up to 10 users
        { duration: '5m', target: 10 },   // Stay at 10 users
        { duration: '2m', target: 0 },    // Ramp down
      ],
      gracefulRampDown: '30s',
      tags: { test_type: 'baseline' },
    },
    
    // Stress test
    stress_test: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '2m', target: 50 },   // Ramp up to 50 users
        { duration: '5m', target: 50 },   // Stay at 50 users
        { duration: '2m', target: 100 },  // Ramp up to 100 users
        { duration: '5m', target: 100 },  // Stay at 100 users
        { duration: '2m', target: 0 },    // Ramp down
      ],
      gracefulRampDown: '30s',
      tags: { test_type: 'stress' },
    },
    
    // Spike test
    spike_test: {
      executor: 'ramping-vus',
      startVUs: 1,
      stages: [
        { duration: '1m', target: 10 },   // Normal load
        { duration: '30s', target: 200 }, // Spike to 200 users
        { duration: '1m', target: 10 },   // Back to normal
      ],
      gracefulRampDown: '30s',
      tags: { test_type: 'spike' },
    },
    
    // Streaming test
    streaming_test: {
      executor: 'constant-vus',
      vus: 20,
      duration: '5m',
      tags: { test_type: 'streaming' },
    },
    
    // API Gateway test
    api_gateway_test: {
      executor: 'constant-arrival-rate',
      rate: 100, // 100 requests per second
      timeUnit: '1s',
      duration: '5m',
      preAllocatedVUs: 50,
      maxVUs: 100,
      tags: { test_type: 'api_gateway' },
    },
  },
  
  thresholds: {
    // Overall performance thresholds
    http_req_duration: ['p(95)<2000'], // 95% of requests under 2s
    http_req_failed: ['rate<0.05'],    // Error rate under 5%
    
    // Chat completion thresholds
    chat_completion_duration: ['p(95)<5000'], // 95% under 5s
    chat_completion_failures: ['rate<0.02'],  // Error rate under 2%
    
    // Streaming thresholds
    streaming_duration: ['p(95)<10000'], // 95% under 10s
    streaming_failures: ['rate<0.03'],   // Error rate under 3%
    
    // API Gateway thresholds
    api_gateway_duration: ['p(95)<500'], // 95% under 500ms
    rate_limit_hits: ['count<100'],      // Less than 100 rate limit hits
  },
};

// Test data
const testPrompts = [
  "Hello, how are you today?",
  "Explain quantum computing in simple terms.",
  "Write a short story about a robot.",
  "What are the benefits of renewable energy?",
  "How does machine learning work?",
  "Describe the process of photosynthesis.",
  "What is the capital of France?",
  "Explain the theory of relativity.",
  "Write a poem about the ocean.",
  "How do you make chocolate chip cookies?",
];

const testModels = [
  "gpt-4",
  "gpt-3.5-turbo",
  "claude-3",
  "gemini-pro",
];

// Helper functions
function getRandomPrompt() {
  return testPrompts[randomIntBetween(0, testPrompts.length - 1)];
}

function getRandomModel() {
  return testModels[randomIntBetween(0, testModels.length - 1)];
}

function getHeaders() {
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${API_KEY}`,
    'User-Agent': 'K6-LoadTest/1.0',
  };
}

// Main test function
export default function () {
  const testType = __ENV.K6_SCENARIO || 'baseline_load';
  
  switch (testType) {
    case 'streaming_test':
      testStreamingEndpoint();
      break;
    case 'api_gateway_test':
      testAPIGateway();
      break;
    default:
      testChatCompletion();
      break;
  }
  
  sleep(randomIntBetween(1, 3)); // Random think time
}

// Test chat completion endpoint
function testChatCompletion() {
  group('Chat Completion', () => {
    const payload = {
      model: getRandomModel(),
      messages: [
        {
          role: "user",
          content: getRandomPrompt()
        }
      ],
      temperature: 0.7,
      max_tokens: randomIntBetween(50, 200),
    };
    
    const startTime = Date.now();
    const response = http.post(
      `${BASE_URL}/api/v1/chat/completions`,
      JSON.stringify(payload),
      { headers: getHeaders() }
    );
    const duration = Date.now() - startTime;
    
    // Record metrics
    chatCompletionDuration.add(duration);
    
    // Validate response
    const success = check(response, {
      'status is 200': (r) => r.status === 200,
      'has response body': (r) => r.body && r.body.length > 0,
      'response time < 10s': (r) => r.timings.duration < 10000,
      'has choices': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.choices && body.choices.length > 0;
        } catch (e) {
          return false;
        }
      },
      'has usage info': (r) => {
        try {
          const body = JSON.parse(r.body);
          return body.usage && body.usage.total_tokens > 0;
        } catch (e) {
          return false;
        }
      },
    });
    
    if (!success) {
      chatCompletionFailureRate.add(1);
      console.error(`Chat completion failed: ${response.status} - ${response.body}`);
    } else {
      chatCompletionFailureRate.add(0);
    }
    
    // Check for rate limiting
    if (response.status === 429) {
      rateLimitHits.add(1);
    }
  });
}

// Test streaming endpoint
function testStreamingEndpoint() {
  group('Streaming Chat', () => {
    const payload = {
      model: getRandomModel(),
      messages: [
        {
          role: "user",
          content: "Write a detailed explanation of artificial intelligence."
        }
      ],
      temperature: 0.8,
      max_tokens: 500,
      stream: true,
    };
    
    const startTime = Date.now();
    const response = http.post(
      `${BASE_URL}/api/v1/chat/completions`,
      JSON.stringify(payload),
      { 
        headers: getHeaders(),
        timeout: '30s',
      }
    );
    const duration = Date.now() - startTime;
    
    // Record metrics
    streamingDuration.add(duration);
    
    // Validate streaming response
    const success = check(response, {
      'status is 200': (r) => r.status === 200,
      'is streaming response': (r) => r.headers['Content-Type'] && r.headers['Content-Type'].includes('text/plain'),
      'has streaming data': (r) => r.body && r.body.includes('data:'),
      'response time < 30s': (r) => r.timings.duration < 30000,
    });
    
    if (!success) {
      streamingFailureRate.add(1);
      console.error(`Streaming failed: ${response.status} - ${response.body.substring(0, 200)}`);
    } else {
      streamingFailureRate.add(0);
      
      // Count streaming chunks
      const chunks = response.body.split('\n').filter(line => line.startsWith('data:'));
      console.log(`Received ${chunks.length} streaming chunks`);
    }
  });
}

// Test API Gateway functionality
function testAPIGateway() {
  group('API Gateway', () => {
    // Test different endpoints
    const endpoints = [
      '/api/v1/models',
      '/api/v1/health',
      '/api/v1/metrics',
    ];
    
    endpoints.forEach(endpoint => {
      const startTime = Date.now();
      const response = http.get(`${BASE_URL}${endpoint}`, { headers: getHeaders() });
      const duration = Date.now() - startTime;
      
      apiGatewayDuration.add(duration);
      
      check(response, {
        [`${endpoint} status is 200`]: (r) => r.status === 200,
        [`${endpoint} response time < 1s`]: (r) => r.timings.duration < 1000,
        [`${endpoint} has content`]: (r) => r.body && r.body.length > 0,
      });
      
      if (response.status === 429) {
        rateLimitHits.add(1);
      }
    });
  });
}

// Test WebSocket connections
export function testWebSocket() {
  group('WebSocket Connection', () => {
    const url = `${WS_URL}/ws`;
    const params = { headers: { 'Authorization': `Bearer ${API_KEY}` } };
    
    const response = ws.connect(url, params, function (socket) {
      socket.on('open', () => {
        console.log('WebSocket connection opened');
        
        // Send test message
        socket.send(JSON.stringify({
          type: 'chat',
          message: getRandomPrompt(),
          model: getRandomModel(),
        }));
      });
      
      socket.on('message', (data) => {
        console.log('Received WebSocket message:', data.substring(0, 100));
        
        try {
          const message = JSON.parse(data);
          check(message, {
            'has type': (m) => m.type !== undefined,
            'has content': (m) => m.content !== undefined,
          });
        } catch (e) {
          console.error('Failed to parse WebSocket message:', e);
        }
      });
      
      socket.on('error', (e) => {
        console.error('WebSocket error:', e);
      });
      
      // Keep connection open for a bit
      sleep(5);
      
      socket.close();
    });
    
    check(response, {
      'WebSocket connection successful': (r) => r && r.status === 101,
    });
  });
}

// Chaos testing function
export function chaosTest() {
  group('Chaos Testing', () => {
    // Simulate various failure scenarios
    const scenarios = [
      () => testWithInvalidAuth(),
      () => testWithMalformedRequest(),
      () => testWithLargePayload(),
      () => testWithConcurrentRequests(),
    ];
    
    const scenario = scenarios[randomIntBetween(0, scenarios.length - 1)];
    scenario();
  });
}

function testWithInvalidAuth() {
  const payload = {
    model: "gpt-4",
    messages: [{ role: "user", content: "Test" }],
  };
  
  const response = http.post(
    `${BASE_URL}/api/v1/chat/completions`,
    JSON.stringify(payload),
    { headers: { 'Content-Type': 'application/json', 'Authorization': 'Bearer invalid-key' } }
  );
  
  check(response, {
    'invalid auth returns 401': (r) => r.status === 401,
  });
}

function testWithMalformedRequest() {
  const response = http.post(
    `${BASE_URL}/api/v1/chat/completions`,
    '{"invalid": json}',
    { headers: getHeaders() }
  );
  
  check(response, {
    'malformed request returns 400': (r) => r.status === 400,
  });
}

function testWithLargePayload() {
  const largeContent = randomString(10000); // 10KB string
  const payload = {
    model: "gpt-4",
    messages: [{ role: "user", content: largeContent }],
  };
  
  const response = http.post(
    `${BASE_URL}/api/v1/chat/completions`,
    JSON.stringify(payload),
    { headers: getHeaders() }
  );
  
  check(response, {
    'large payload handled': (r) => r.status === 200 || r.status === 413,
  });
}

function testWithConcurrentRequests() {
  // Make multiple concurrent requests
  const requests = [];
  for (let i = 0; i < 5; i++) {
    const payload = {
      model: getRandomModel(),
      messages: [{ role: "user", content: `Concurrent request ${i}` }],
    };
    
    requests.push([
      'POST',
      `${BASE_URL}/api/v1/chat/completions`,
      JSON.stringify(payload),
      { headers: getHeaders() }
    ]);
  }
  
  const responses = http.batch(requests);
  
  responses.forEach((response, index) => {
    check(response, {
      [`concurrent request ${index} successful`]: (r) => r.status === 200,
    });
  });
}

// Setup function
export function setup() {
  console.log('Starting ATP Load Tests');
  console.log(`Base URL: ${BASE_URL}`);
  console.log(`Test scenarios: ${Object.keys(options.scenarios).join(', ')}`);
  
  // Verify API is accessible
  const healthCheck = http.get(`${BASE_URL}/health`);
  if (healthCheck.status !== 200) {
    throw new Error(`API health check failed: ${healthCheck.status}`);
  }
  
  return { startTime: Date.now() };
}

// Teardown function
export function teardown(data) {
  const duration = (Date.now() - data.startTime) / 1000;
  console.log(`Load test completed in ${duration} seconds`);
}

// Handle summary
export function handleSummary(data) {
  return {
    'stdout': textSummary(data, { indent: ' ', enableColors: true }),
    'summary.json': JSON.stringify(data),
    'summary.html': htmlReport(data),
  };
}

function textSummary(data, options = {}) {
  const indent = options.indent || '';
  const enableColors = options.enableColors || false;
  
  let summary = `${indent}ATP Load Test Summary\n`;
  summary += `${indent}========================\n\n`;
  
  // Test execution info
  summary += `${indent}Test Duration: ${data.state.testRunDurationMs / 1000}s\n`;
  summary += `${indent}Total VUs: ${data.metrics.vus_max.values.max}\n`;
  summary += `${indent}Total Requests: ${data.metrics.http_reqs.values.count}\n\n`;
  
  // Performance metrics
  summary += `${indent}Performance Metrics:\n`;
  summary += `${indent}  Response Time (avg): ${data.metrics.http_req_duration.values.avg.toFixed(2)}ms\n`;
  summary += `${indent}  Response Time (p95): ${data.metrics.http_req_duration.values['p(95)'].toFixed(2)}ms\n`;
  summary += `${indent}  Request Rate: ${data.metrics.http_req_rate.values.rate.toFixed(2)} req/s\n`;
  summary += `${indent}  Error Rate: ${(data.metrics.http_req_failed.values.rate * 100).toFixed(2)}%\n\n`;
  
  // Custom metrics
  if (data.metrics.chat_completion_duration) {
    summary += `${indent}Chat Completion Metrics:\n`;
    summary += `${indent}  Duration (avg): ${data.metrics.chat_completion_duration.values.avg.toFixed(2)}ms\n`;
    summary += `${indent}  Duration (p95): ${data.metrics.chat_completion_duration.values['p(95)'].toFixed(2)}ms\n`;
    summary += `${indent}  Failure Rate: ${(data.metrics.chat_completion_failures.values.rate * 100).toFixed(2)}%\n\n`;
  }
  
  // Thresholds
  summary += `${indent}Threshold Results:\n`;
  Object.entries(data.thresholds).forEach(([name, threshold]) => {
    const status = threshold.ok ? '✓' : '✗';
    summary += `${indent}  ${status} ${name}\n`;
  });
  
  return summary;
}

function htmlReport(data) {
  return `
<!DOCTYPE html>
<html>
<head>
    <title>ATP Load Test Report</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        .metric { margin: 10px 0; }
        .pass { color: green; }
        .fail { color: red; }
        table { border-collapse: collapse; width: 100%; }
        th, td { border: 1px solid #ddd; padding: 8px; text-align: left; }
        th { background-color: #f2f2f2; }
    </style>
</head>
<body>
    <h1>ATP Load Test Report</h1>
    <h2>Summary</h2>
    <div class="metric">Test Duration: ${data.state.testRunDurationMs / 1000}s</div>
    <div class="metric">Total Requests: ${data.metrics.http_reqs.values.count}</div>
    <div class="metric">Error Rate: ${(data.metrics.http_req_failed.values.rate * 100).toFixed(2)}%</div>
    
    <h2>Performance Metrics</h2>
    <table>
        <tr><th>Metric</th><th>Average</th><th>P95</th><th>Max</th></tr>
        <tr>
            <td>Response Time</td>
            <td>${data.metrics.http_req_duration.values.avg.toFixed(2)}ms</td>
            <td>${data.metrics.http_req_duration.values['p(95)'].toFixed(2)}ms</td>
            <td>${data.metrics.http_req_duration.values.max.toFixed(2)}ms</td>
        </tr>
    </table>
    
    <h2>Threshold Results</h2>
    <ul>
        ${Object.entries(data.thresholds).map(([name, threshold]) => 
            `<li class="${threshold.ok ? 'pass' : 'fail'}">${threshold.ok ? '✓' : '✗'} ${name}</li>`
        ).join('')}
    </ul>
</body>
</html>
  `;
}
/
/ Additional performance test scenarios

// Memory leak detection test
export function memoryLeakTest() {
  group('Memory Leak Detection', () => {
    const startTime = Date.now();
    const testDuration = 60000; // 1 minute
    let requestCount = 0;
    
    while (Date.now() - startTime < testDuration) {
      const payload = {
        model: getRandomModel(),
        messages: [
          {
            role: "user",
            content: `Memory test request ${requestCount++}: ${randomString(100)}`
          }
        ],
        temperature: 0.7,
        max_tokens: 50,
      };
      
      const response = http.post(
        `${BASE_URL}/api/v1/chat/completions`,
        JSON.stringify(payload),
        { headers: getHeaders() }
      );
      
      check(response, {
        'memory test request successful': (r) => r.status === 200,
        'response time stable': (r) => r.timings.duration < 5000,
      });
      
      sleep(0.1); // Small delay between requests
    }
    
    console.log(`Memory leak test completed: ${requestCount} requests in ${testDuration/1000}s`);
  });
}

// Database connection pool test
export function connectionPoolTest() {
  group('Database Connection Pool', () => {
    const concurrentRequests = 50;
    const requests = [];
    
    // Create concurrent requests that will stress the connection pool
    for (let i = 0; i < concurrentRequests; i++) {
      const payload = {
        model: "gpt-4",
        messages: [
          {
            role: "user", 
            content: `Connection pool test ${i}`
          }
        ],
        max_tokens: 10,
      };
      
      requests.push([
        'POST',
        `${BASE_URL}/api/v1/chat/completions`,
        JSON.stringify(payload),
        { headers: getHeaders() }
      ]);
    }
    
    const responses = http.batch(requests);
    
    let successCount = 0;
    let connectionErrors = 0;
    
    responses.forEach((response, index) => {
      const success = check(response, {
        [`connection pool request ${index} successful`]: (r) => r.status === 200,
        [`connection pool request ${index} no timeout`]: (r) => r.timings.duration < 10000,
      });
      
      if (success) {
        successCount++;
      } else if (response.status === 503 || response.body.includes('connection')) {
        connectionErrors++;
      }
    });
    
    console.log(`Connection pool test: ${successCount}/${concurrentRequests} successful, ${connectionErrors} connection errors`);
    
    // Should handle concurrent connections gracefully
    check(null, {
      'connection pool handles concurrent requests': () => successCount >= concurrentRequests * 0.9,
      'connection errors within acceptable range': () => connectionErrors <= concurrentRequests * 0.1,
    });
  });
}

// Cache performance test
export function cachePerformanceTest() {
  group('Cache Performance', () => {
    const testPrompt = "What is the capital of France?";
    const model = "gpt-4";
    
    // First request (cache miss)
    const payload = {
      model: model,
      messages: [{ role: "user", content: testPrompt }],
      temperature: 0.0, // Deterministic for caching
      max_tokens: 50,
    };
    
    const firstResponse = http.post(
      `${BASE_URL}/api/v1/chat/completions`,
      JSON.stringify(payload),
      { headers: getHeaders() }
    );
    
    const firstResponseTime = firstResponse.timings.duration;
    
    check(firstResponse, {
      'first request successful': (r) => r.status === 200,
    });
    
    sleep(1); // Brief pause
    
    // Second identical request (potential cache hit)
    const secondResponse = http.post(
      `${BASE_URL}/api/v1/chat/completions`,
      JSON.stringify(payload),
      { headers: getHeaders() }
    );
    
    const secondResponseTime = secondResponse.timings.duration;
    
    check(secondResponse, {
      'second request successful': (r) => r.status === 200,
      'cache improves performance': () => secondResponseTime <= firstResponseTime,
    });
    
    console.log(`Cache test: First request ${firstResponseTime}ms, Second request ${secondResponseTime}ms`);
    
    // Test cache invalidation
    const invalidationPayload = {
      model: model,
      messages: [{ role: "user", content: testPrompt }],
      temperature: 0.1, // Different temperature should bypass cache
      max_tokens: 50,
    };
    
    const invalidationResponse = http.post(
      `${BASE_URL}/api/v1/chat/completions`,
      JSON.stringify(invalidationPayload),
      { headers: getHeaders() }
    );
    
    check(invalidationResponse, {
      'cache invalidation request successful': (r) => r.status === 200,
    });
  });
}

// Provider failover test
export function providerFailoverTest() {
  group('Provider Failover', () => {
    // Test with a model that might have multiple providers
    const payload = {
      model: "gpt-4",
      messages: [{ role: "user", content: "Test provider failover" }],
      max_tokens: 20,
    };
    
    const responses = [];
    const maxAttempts = 10;
    
    for (let i = 0; i < maxAttempts; i++) {
      const response = http.post(
        `${BASE_URL}/api/v1/chat/completions`,
        JSON.stringify(payload),
        { headers: getHeaders() }
      );
      
      responses.push({
        status: response.status,
        duration: response.timings.duration,
        provider: response.headers['X-Provider'] || 'unknown',
        attempt: i + 1
      });
      
      check(response, {
        [`failover test attempt ${i + 1} handled`]: (r) => r.status === 200 || r.status === 503,
      });
      
      sleep(0.5);
    }
    
    // Analyze failover behavior
    const successfulResponses = responses.filter(r => r.status === 200);
    const failedResponses = responses.filter(r => r.status !== 200);
    
    console.log(`Failover test: ${successfulResponses.length}/${maxAttempts} successful`);
    console.log(`Providers used: ${[...new Set(successfulResponses.map(r => r.provider))].join(', ')}`);
    
    check(null, {
      'failover maintains availability': () => successfulResponses.length >= maxAttempts * 0.8,
      'failover response time acceptable': () => {
        const avgResponseTime = successfulResponses.reduce((sum, r) => sum + r.duration, 0) / successfulResponses.length;
        return avgResponseTime < 10000;
      },
    });
  });
}

// Rate limiting accuracy test
export function rateLimitAccuracyTest() {
  group('Rate Limiting Accuracy', () => {
    const rateLimit = 10; // Assume 10 requests per minute
    const testDuration = 60000; // 1 minute
    const requestInterval = testDuration / (rateLimit + 5); // Slightly exceed rate limit
    
    const startTime = Date.now();
    let requestCount = 0;
    let rateLimitedCount = 0;
    let successCount = 0;
    
    while (Date.now() - startTime < testDuration) {
      const payload = {
        model: "gpt-4",
        messages: [{ role: "user", content: `Rate limit test ${requestCount}` }],
        max_tokens: 10,
      };
      
      const response = http.post(
        `${BASE_URL}/api/v1/chat/completions`,
        JSON.stringify(payload),
        { headers: getHeaders() }
      );
      
      requestCount++;
      
      if (response.status === 429) {
        rateLimitedCount++;
      } else if (response.status === 200) {
        successCount++;
      }
      
      sleep(requestInterval / 1000);
    }
    
    console.log(`Rate limit test: ${requestCount} requests, ${successCount} successful, ${rateLimitedCount} rate limited`);
    
    check(null, {
      'rate limiting is enforced': () => rateLimitedCount > 0,
      'rate limiting is accurate': () => successCount <= rateLimit * 1.1, // Allow 10% tolerance
      'rate limiting provides proper response': () => rateLimitedCount > 0,
    });
  });
}

// Concurrent user simulation
export function concurrentUserSimulation() {
  group('Concurrent User Simulation', () => {
    const userSessions = 20;
    const requestsPerSession = 5;
    
    // Simulate multiple user sessions
    const allRequests = [];
    
    for (let userId = 0; userId < userSessions; userId++) {
      for (let reqId = 0; reqId < requestsPerSession; reqId++) {
        const payload = {
          model: getRandomModel(),
          messages: [
            {
              role: "user",
              content: `User ${userId} request ${reqId}: ${getRandomPrompt()}`
            }
          ],
          temperature: Math.random(),
          max_tokens: randomIntBetween(20, 100),
        };
        
        allRequests.push([
          'POST',
          `${BASE_URL}/api/v1/chat/completions`,
          JSON.stringify(payload),
          { 
            headers: {
              ...getHeaders(),
              'X-User-ID': `user-${userId}`,
              'X-Session-ID': `session-${userId}-${Date.now()}`
            }
          }
        ]);
      }
    }
    
    // Execute all requests concurrently
    const startTime = Date.now();
    const responses = http.batch(allRequests);
    const totalDuration = Date.now() - startTime;
    
    // Analyze results
    let successCount = 0;
    let errorCount = 0;
    const responseTimes = [];
    const userResponseTimes = {};
    
    responses.forEach((response, index) => {
      const userId = Math.floor(index / requestsPerSession);
      
      if (!userResponseTimes[userId]) {
        userResponseTimes[userId] = [];
      }
      
      if (response.status === 200) {
        successCount++;
        responseTimes.push(response.timings.duration);
        userResponseTimes[userId].push(response.timings.duration);
      } else {
        errorCount++;
      }
    });
    
    const avgResponseTime = responseTimes.reduce((sum, time) => sum + time, 0) / responseTimes.length;
    const maxResponseTime = Math.max(...responseTimes);
    const minResponseTime = Math.min(...responseTimes);
    
    console.log(`Concurrent user simulation: ${successCount}/${allRequests.length} successful`);
    console.log(`Response times: avg=${avgResponseTime.toFixed(2)}ms, min=${minResponseTime}ms, max=${maxResponseTime}ms`);
    console.log(`Total test duration: ${totalDuration}ms`);
    
    check(null, {
      'concurrent users handled successfully': () => successCount >= allRequests.length * 0.95,
      'response times reasonable under load': () => avgResponseTime < 5000,
      'no user session completely failed': () => {
        return Object.values(userResponseTimes).every(times => times.length > 0);
      },
    });
  });
}

// Resource utilization test
export function resourceUtilizationTest() {
  group('Resource Utilization', () => {
    // Test different payload sizes
    const payloadSizes = [
      { name: 'small', tokens: 50 },
      { name: 'medium', tokens: 500 },
      { name: 'large', tokens: 2000 }
    ];
    
    payloadSizes.forEach(size => {
      const largeContent = randomString(size.tokens * 4); // Approximate token to character ratio
      
      const payload = {
        model: "gpt-4",
        messages: [{ role: "user", content: largeContent }],
        max_tokens: Math.min(size.tokens, 4000),
      };
      
      const response = http.post(
        `${BASE_URL}/api/v1/chat/completions`,
        JSON.stringify(payload),
        { 
          headers: getHeaders(),
          timeout: '60s' // Longer timeout for large requests
        }
      );
      
      check(response, {
        [`${size.name} payload processed`]: (r) => r.status === 200 || r.status === 413,
        [`${size.name} payload response time acceptable`]: (r) => {
          // Larger payloads should have proportionally longer response times
          const maxTime = size.tokens * 10; // 10ms per token as rough estimate
          return r.timings.duration < maxTime;
        },
      });
      
      console.log(`${size.name} payload (${size.tokens} tokens): ${response.status}, ${response.timings.duration}ms`);
    });
  });
}

// Export additional test functions for specific scenarios
export { 
  memoryLeakTest,
  connectionPoolTest, 
  cachePerformanceTest,
  providerFailoverTest,
  rateLimitAccuracyTest,
  concurrentUserSimulation,
  resourceUtilizationTest
};