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
import { Provider, ProviderHealth } from '../types/provider';
import { apiClient } from '../services/apiClient';

export const useProviders = () => {
  const [providers, setProviders] = useState<Provider[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshProviders = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const response = await apiClient.get('/admin/providers');
      setProviders(response.data);
    } catch (err: any) {
      setError(err.message || 'Failed to fetch providers');
    } finally {
      setLoading(false);
    }
  }, []);

  const addProvider = useCallback(async (providerData: Omit<Provider, 'id'>) => {
    setError(null);
    try {
      const response = await apiClient.post('/admin/providers', providerData);
      setProviders(prev => [...prev, response.data]);
      return response.data;
    } catch (err: any) {
      setError(err.message || 'Failed to add provider');
      throw err;
    }
  }, []);

  const updateProvider = useCallback(async (id: string, updates: Partial<Provider>) => {
    setError(null);
    try {
      const response = await apiClient.put(`/admin/providers/${id}`, updates);
      setProviders(prev => 
        prev.map(provider => 
          provider.id === id ? { ...provider, ...response.data } : provider
        )
      );
      return response.data;
    } catch (err: any) {
      setError(err.message || 'Failed to update provider');
      throw err;
    }
  }, []);

  const deleteProvider = useCallback(async (id: string) => {
    setError(null);
    try {
      await apiClient.delete(`/admin/providers/${id}`);
      setProviders(prev => prev.filter(provider => provider.id !== id));
    } catch (err: any) {
      setError(err.message || 'Failed to delete provider');
      throw err;
    }
  }, []);

  const testProvider = useCallback(async (id: string, testData: any) => {
    setError(null);
    try {
      const response = await apiClient.post(`/admin/providers/${id}/test`, testData);
      return response.data;
    } catch (err: any) {
      setError(err.message || 'Failed to test provider');
      throw err;
    }
  }, []);

  const getProviderHealth = useCallback(async (id: string): Promise<ProviderHealth> => {
    try {
      const response = await apiClient.get(`/admin/providers/${id}/health`);
      return response.data;
    } catch (err: any) {
      console.error(`Failed to get health for provider ${id}:`, err);
      return {
        healthy: false,
        healthScore: 0,
        lastCheck: new Date(),
        avgResponseTime: 0,
        successRate: 0,
        errorRate: 1,
        uptime: 0,
        issues: ['Health check failed']
      };
    }
  }, []);

  return {
    providers,
    loading,
    error,
    refreshProviders,
    addProvider,
    updateProvider,
    deleteProvider,
    testProvider,
    getProviderHealth
  };
};