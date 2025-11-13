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

export interface ProviderConfig {
  endpoint?: string;
  apiKey: string;
  timeout: number;
  retries: number;
  rateLimit: number;
  headers?: Record<string, string>;
  models?: string[];
  // Azure-specific
  resourceName?: string;
  deploymentName?: string;
  apiVersion?: string;
}

export interface ProviderModel {
  name: string;
  type: 'chat' | 'completion' | 'embedding';
  maxTokens?: number;
  costPer1kTokens?: number;
  capabilities?: string[];
}

export interface Provider {
  id: string;
  name: string;
  type: string;
  status: 'active' | 'inactive' | 'error';
  priority: number;
  config: ProviderConfig;
  models?: ProviderModel[];
  createdAt?: Date;
  updatedAt?: Date;
}

export interface ProviderHealth {
  healthy: boolean;
  healthScore: number;
  lastCheck: Date;
  avgResponseTime: number;
  successRate: number;
  errorRate: number;
  uptime: number;
  issues?: string[];
}

export interface ProviderMetrics {
  summary: {
    totalRequests: number;
    requestsPerSecond: number;
    successRate: number;
    avgResponseTime: number;
    errorRate: number;
  };
  timeSeries: {
    requests: Array<{ timestamp: number; count: number }>;
    responseTime: Array<{ timestamp: number; avg: number; p95: number }>;
  };
  providerDistribution: Array<{ name: string; requests: number }>;
  errorTypes: Array<{ type: string; count: number }>;
  modelStats: Array<{
    provider: string;
    model: string;
    requests: number;
    successRate: number;
    avgResponseTime: number;
    totalTokens: number;
    totalCost?: number;
  }>;
}

export interface TestRequest {
  model: string;
  prompt: string;
  temperature?: number;
  maxTokens?: number;
}

export interface TestResult {
  success: boolean;
  responseTime: number;
  tokensUsed?: number;
  response?: string;
  error?: string;
}

export interface BenchmarkRequest {
  model: string;
  prompts: string[];
  iterations: number;
}

export interface BenchmarkResult {
  successRate: number;
  avgResponseTime: number;
  totalTests: number;
  details: TestResult[];
}