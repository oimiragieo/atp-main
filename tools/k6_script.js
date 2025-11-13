import http from 'k6/http';
import { check, sleep } from 'k6';

// Test configuration
export let options = {
  stages: [
    { duration: '30s', target: 10 },  // Ramp up to 10 users over 30s
    { duration: '1m', target: 10 },   // Stay at 10 users for 1 minute
    { duration: '30s', target: 0 },   // Ramp down to 0 users
  ],
  thresholds: {
    http_req_duration: ['p(95)<500'], // 95% of requests should be below 500ms
    http_req_failed: ['rate<0.1'],    // Error rate should be below 10%
  },
};

const BASE_URL = __ENV.BASE_URL || 'http://host.docker.internal:8080';

export default function () {
  // Test memory gateway health
  let response = http.get(`${BASE_URL}/healthz`);
  check(response, {
    'memory gateway health status is 200': (r) => r.status === 200,
  });

  // Test memory put operation
  let putResponse = http.put(
    `${BASE_URL}/v1/memory/test/key1`,
    JSON.stringify({ object: { message: 'load test data' } }),
    {
      headers: {
        'Content-Type': 'application/json',
        'x-tenant-id': 'test-tenant',
      },
    }
  );
  check(putResponse, {
    'memory put status is 200': (r) => r.status === 200,
  });

  // Test memory get operation
  let getResponse = http.get(
    `${BASE_URL}/v1/memory/test/key1`,
    {
      headers: {
        'x-tenant-id': 'test-tenant',
      },
    }
  );
  check(getResponse, {
    'memory get status is 200': (r) => r.status === 200,
  });

  sleep(1); // Wait 1 second between iterations
}
