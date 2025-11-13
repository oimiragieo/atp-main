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

import { useState, useCallback } from 'react';
import { TestRequest, TestResult, BenchmarkRequest, BenchmarkResult } from '../types/provider';
import { apiClient } from '../services/apiClient';

export const useProviderTest = () => {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runTest = useCallback(async (providerId: string, testRequest: TestRequest): Promise<TestResult> => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.post(`/admin/providers/${providerId}/test`, testRequest);
      return response.data;
    } catch (err: any) {
      setError(err.message || 'Test failed');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  const runBenchmark = useCallback(async (providerId: string, benchmarkRequest: BenchmarkRequest): Promise<BenchmarkResult> => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.post(`/admin/providers/${providerId}/benchmark`, benchmarkRequest);
      return response.data;
    } catch (err: any) {
      setError(err.message || 'Benchmark failed');
      throw err;
    } finally {
      setLoading(false);
    }
  }, []);

  return {
    loading,
    error,
    runTest,
    runBenchmark
  };
};