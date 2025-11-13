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
import { ProviderMetrics } from '../types/provider';
import { apiClient } from '../services/apiClient';

export const useProviderMetrics = (timeRange: string, providerId?: string) => {
  const [metrics, setMetrics] = useState<ProviderMetrics | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshMetrics = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const params = new URLSearchParams({
        timeRange,
        ...(providerId && providerId !== 'all' ? { providerId } : {})
      });
      
      const response = await apiClient.get(`/admin/metrics/providers?${params}`);
      setMetrics(response.data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch provider metrics');
    } finally {
      setLoading(false);
    }
  }, [timeRange, providerId]);

  return {
    metrics,
    loading,
    error,
    refreshMetrics
  };
};