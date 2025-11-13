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

import React from 'react';
import {
  Grid,
  Card,
  CardContent,
  Typography,
  Box,
  LinearProgress,
  Chip,
  Alert,
} from '@mui/material';
import {
  TrendingUp,
  Speed,
  CloudQueue,
  Computer,
  Warning,
  CheckCircle,
} from '@mui/icons-material';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
  BarChart,
  Bar,
  PieChart,
  Pie,
  Cell,
} from 'recharts';
import { useQuery } from 'react-query';
import { apiClient } from '../../services/api';

interface MetricCardProps {
  title: string;
  value: string | number;
  change?: string;
  icon: React.ReactNode;
  color?: 'primary' | 'secondary' | 'success' | 'warning' | 'error';
}

const MetricCard: React.FC<MetricCardProps> = ({ title, value, change, icon, color = 'primary' }) => (
  <Card>
    <CardContent>
      <Box display="flex" alignItems="center" justifyContent="space-between">
        <Box>
          <Typography color="textSecondary" gutterBottom variant="body2">
            {title}
          </Typography>
          <Typography variant="h4" component="div">
            {value}
          </Typography>
          {change && (
            <Typography variant="body2" color={color === 'success' ? 'success.main' : 'error.main'}>
              {change}
            </Typography>
          )}
        </Box>
        <Box color={`${color}.main`}>
          {icon}
        </Box>
      </Box>
    </CardContent>
  </Card>
);

const Dashboard: React.FC = () => {
  const { data: systemHealth } = useQuery('systemHealth', () => apiClient.get('/api/v1/system/health'));
  const { data: metrics } = useQuery('dashboardMetrics', () => apiClient.get('/api/v1/metrics/dashboard'));
  const { data: providers } = useQuery('providers', () => apiClient.get('/api/v1/providers'));
  const { data: requestStats } = useQuery('requestStats', () => apiClient.get('/api/v1/metrics/requests'));

  // Mock data for charts
  const requestData = [
    { time: '00:00', requests: 120, errors: 2 },
    { time: '04:00', requests: 80, errors: 1 },
    { time: '08:00', requests: 200, errors: 5 },
    { time: '12:00', requests: 350, errors: 8 },
    { time: '16:00', requests: 280, errors: 3 },
    { time: '20:00', requests: 150, errors: 2 },
  ];

  const providerData = [
    { name: 'OpenAI', requests: 45, color: '#8884d8' },
    { name: 'Anthropic', requests: 30, color: '#82ca9d' },
    { name: 'Google', requests: 20, color: '#ffc658' },
    { name: 'Local', requests: 5, color: '#ff7300' },
  ];

  const costData = [
    { date: '2025-01-01', cost: 120 },
    { date: '2025-01-02', cost: 135 },
    { date: '2025-01-03', cost: 98 },
    { date: '2025-01-04', cost: 156 },
    { date: '2025-01-05', cost: 142 },
    { date: '2025-01-06', cost: 178 },
    { date: '2025-01-07', cost: 165 },
  ];

  return (
    <Box>
      <Typography variant="h4" gutterBottom>
        Dashboard
      </Typography>

      {/* System Status Alert */}
      {systemHealth?.status !== 'healthy' && (
        <Alert severity="warning" sx={{ mb: 3 }}>
          System health check detected issues. Check the monitoring page for details.
        </Alert>
      )}

      {/* Key Metrics */}
      <Grid container spacing={3} sx={{ mb: 3 }}>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Total Requests"
            value="12,543"
            change="+12.5%"
            icon={<TrendingUp />}
            color="success"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Avg Response Time"
            value="245ms"
            change="-5.2%"
            icon={<Speed />}
            color="success"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Active Providers"
            value={providers?.data?.filter((p: any) => p.status === 'active').length || 0}
            icon={<CloudQueue />}
            color="primary"
          />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <MetricCard
            title="Cluster Nodes"
            value="8"
            change="All healthy"
            icon={<Computer />}
            color="success"
          />
        </Grid>
      </Grid>

      <Grid container spacing={3}>
        {/* Request Volume Chart */}
        <Grid item xs={12} md={8}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Request Volume (24h)
              </Typography>
              <ResponsiveContainer width="100%" height={300}>
                <LineChart data={requestData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="time" />
                  <YAxis />
                  <Tooltip />
                  <Line type="monotone" dataKey="requests" stroke="#8884d8" strokeWidth={2} />
                  <Line type="monotone" dataKey="errors" stroke="#ff7300" strokeWidth={2} />
                </LineChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Provider Distribution */}
        <Grid item xs={12} md={4}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Provider Usage
              </Typography>
              <ResponsiveContainer width="100%" height={300}>
                <PieChart>
                  <Pie
                    data={providerData}
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    fill="#8884d8"
                    dataKey="requests"
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  >
                    {providerData.map((entry, index) => (
                      <Cell key={`cell-${index}`} fill={entry.color} />
                    ))}
                  </Pie>
                  <Tooltip />
                </PieChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* Cost Tracking */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Daily Costs (USD)
              </Typography>
              <ResponsiveContainer width="100%" height={250}>
                <BarChart data={costData}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="date" />
                  <YAxis />
                  <Tooltip />
                  <Bar dataKey="cost" fill="#82ca9d" />
                </BarChart>
              </ResponsiveContainer>
            </CardContent>
          </Card>
        </Grid>

        {/* System Health */}
        <Grid item xs={12} md={6}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                System Health
              </Typography>
              <Box sx={{ mb: 2 }}>
                <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                  <Typography variant="body2">CPU Usage</Typography>
                  <Typography variant="body2">65%</Typography>
                </Box>
                <LinearProgress variant="determinate" value={65} sx={{ mb: 2 }} />
                
                <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                  <Typography variant="body2">Memory Usage</Typography>
                  <Typography variant="body2">78%</Typography>
                </Box>
                <LinearProgress variant="determinate" value={78} sx={{ mb: 2 }} />
                
                <Box display="flex" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
                  <Typography variant="body2">Disk Usage</Typography>
                  <Typography variant="body2">45%</Typography>
                </Box>
                <LinearProgress variant="determinate" value={45} sx={{ mb: 2 }} />
              </Box>
              
              <Box display="flex" gap={1} flexWrap="wrap">
                <Chip
                  icon={<CheckCircle />}
                  label="Router Service"
                  color="success"
                  size="small"
                />
                <Chip
                  icon={<CheckCircle />}
                  label="Memory Gateway"
                  color="success"
                  size="small"
                />
                <Chip
                  icon={<Warning />}
                  label="Analytics Service"
                  color="warning"
                  size="small"
                />
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Recent Activity */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Recent Activity
              </Typography>
              <Box>
                {[
                  { time: '2 minutes ago', event: 'Provider OpenAI-GPT4 health check passed', type: 'success' },
                  { time: '5 minutes ago', event: 'New policy "Rate Limiting v2" deployed', type: 'info' },
                  { time: '12 minutes ago', event: 'Cluster node worker-3 joined', type: 'success' },
                  { time: '18 minutes ago', event: 'High error rate detected on Anthropic provider', type: 'warning' },
                  { time: '25 minutes ago', event: 'Backup completed successfully', type: 'success' },
                ].map((activity, index) => (
                  <Box key={index} display="flex" alignItems="center" sx={{ mb: 1 }}>
                    <Box
                      sx={{
                        width: 8,
                        height: 8,
                        borderRadius: '50%',
                        backgroundColor: 
                          activity.type === 'success' ? 'success.main' :
                          activity.type === 'warning' ? 'warning.main' : 'info.main',
                        mr: 2,
                      }}
                    />
                    <Box flexGrow={1}>
                      <Typography variant="body2">{activity.event}</Typography>
                      <Typography variant="caption" color="text.secondary">
                        {activity.time}
                      </Typography>
                    </Box>
                  </Box>
                ))}
              </Box>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
};

export default Dashboard;