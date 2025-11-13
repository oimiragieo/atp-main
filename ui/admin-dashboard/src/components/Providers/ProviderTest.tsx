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
import React, { useState } from 'react';
import {
  Box,
  Button,
  Card,
  CardContent,
  FormControl,
  Grid,
  InputLabel,
  MenuItem,
  Select,
  TextField,
  Typography,
  Alert,
  CircularProgress,
  Accordion,
  AccordionSummary,
  AccordionDetails,
  Chip,
  LinearProgress
} from '@mui/material';
import {
  ExpandMore as ExpandMoreIcon,
  PlayArrow as PlayIcon,
  CheckCircle as CheckCircleIcon,
  Error as ErrorIcon,
  Timer as TimerIcon
} from '@mui/icons-material';
import { Provider } from '../../types/provider';
import { useProviderTest } from '../../hooks/useProviderTest';

interface ProviderTestProps {
  provider: Provider;
  onClose: () => void;
}

const TEST_PROMPTS = [
  {
    name: 'Simple Greeting',
    prompt: 'Hello! How are you today?',
    description: 'Basic connectivity test'
  },
  {
    name: 'Code Generation',
    prompt: 'Write a Python function to calculate the factorial of a number.',
    description: 'Test code generation capabilities'
  },
  {
    name: 'Creative Writing',
    prompt: 'Write a short story about a robot learning to paint.',
    description: 'Test creative capabilities'
  },
  {
    name: 'Question Answering',
    prompt: 'What are the main benefits of renewable energy?',
    description: 'Test knowledge and reasoning'
  },
  {
    name: 'Long Context',
    prompt: 'Summarize the following text: ' + 'Lorem ipsum '.repeat(100),
    description: 'Test handling of longer inputs'
  }
];

export const ProviderTest: React.FC<ProviderTestProps> = ({ provider, onClose }) => {
  const [selectedModel, setSelectedModel] = useState(provider.models?.[0]?.name || '');
  const [selectedPrompt, setSelectedPrompt] = useState(TEST_PROMPTS[0].name);
  const [customPrompt, setCustomPrompt] = useState('');
  const [useCustomPrompt, setUseCustomPrompt] = useState(false);
  const [testResults, setTestResults] = useState<any[]>([]);

  const {
    runTest,
    runBenchmark,
    loading,
    error
  } = useProviderTest();

  const getCurrentPrompt = () => {
    if (useCustomPrompt) {
      return customPrompt;
    }
    const selected = TEST_PROMPTS.find(p => p.name === selectedPrompt);
    return selected?.prompt || '';
  };

  const handleSingleTest = async () => {
    const prompt = getCurrentPrompt();
    if (!prompt.trim()) {
      return;
    }

    try {
      const result = await runTest(provider.id, {
        model: selectedModel,
        prompt: prompt,
        temperature: 0.7,
        maxTokens: 500
      });

      setTestResults(prev => [{
        id: Date.now(),
        type: 'single',
        prompt: prompt,
        model: selectedModel,
        timestamp: new Date(),
        ...result
      }, ...prev]);
    } catch (error) {
      console.error('Test failed:', error);
    }
  };

  const handleBenchmarkTest = async () => {
    try {
      const results = await runBenchmark(provider.id, {
        model: selectedModel,
        prompts: TEST_PROMPTS.map(p => p.prompt),
        iterations: 3
      });

      setTestResults(prev => [{
        id: Date.now(),
        type: 'benchmark',
        model: selectedModel,
        timestamp: new Date(),
        ...results
      }, ...prev]);
    } catch (error) {
      console.error('Benchmark failed:', error);
    }
  };

  const formatDuration = (ms: number): string => {
    if (ms < 1000) return `${ms.toFixed(0)}ms`;
    return `${(ms / 1000).toFixed(2)}s`;
  };

  const getStatusIcon = (success: boolean) => {
    return success ? 
      <CheckCircleIcon color="success" /> : 
      <ErrorIcon color="error" />;
  };

  return (
    <Box sx={{ mt: 2 }}>
      <Grid container spacing={3}>
        {/* Test Configuration */}
        <Grid item xs={12}>
          <Card>
            <CardContent>
              <Typography variant="h6" gutterBottom>
                Test Configuration
              </Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} md={6}>
                  <FormControl fullWidth>
                    <InputLabel>Model</InputLabel>
                    <Select
                      value={selectedModel}
                      onChange={(e) => setSelectedModel(e.target.value)}
                      label="Model"
                    >
                      {provider.models?.map((model) => (
                        <MenuItem key={model.name} value={model.name}>
                          {model.name}
                        </MenuItem>
                      )) || []}
                    </Select>
                  </FormControl>
                </Grid>
                <Grid item xs={12} md={6}>
                  <FormControl fullWidth>
                    <InputLabel>Test Prompt</InputLabel>
                    <Select
                      value={useCustomPrompt ? 'custom' : selectedPrompt}
                      onChange={(e) => {
                        if (e.target.value === 'custom') {
                          setUseCustomPrompt(true);
                        } else {
                          setUseCustomPrompt(false);
                          setSelectedPrompt(e.target.value);
                        }
                      }}
                      label="Test Prompt"
                    >
                      {TEST_PROMPTS.map((prompt) => (
                        <MenuItem key={prompt.name} value={prompt.name}>
                          {prompt.name}
                        </MenuItem>
                      ))}
                      <MenuItem value="custom">Custom Prompt</MenuItem>
                    </Select>
                  </FormControl>
                </Grid>
                {useCustomPrompt && (
                  <Grid item xs={12}>
                    <TextField
                      fullWidth
                      multiline
                      rows={3}
                      label="Custom Prompt"
                      value={customPrompt}
                      onChange={(e) => setCustomPrompt(e.target.value)}
                      placeholder="Enter your custom test prompt..."
                    />
                  </Grid>
                )}
                {!useCustomPrompt && (
                  <Grid item xs={12}>
                    <Alert severity="info">
                      {TEST_PROMPTS.find(p => p.name === selectedPrompt)?.description}
                    </Alert>
                  </Grid>
                )}
              </Grid>
              <Box sx={{ display: 'flex', gap: 2, mt: 3 }}>
                <Button
                  variant="contained"
                  startIcon={<PlayIcon />}
                  onClick={handleSingleTest}
                  disabled={loading || !getCurrentPrompt().trim()}
                >
                  Run Single Test
                </Button>
                <Button
                  variant="outlined"
                  startIcon={<TimerIcon />}
                  onClick={handleBenchmarkTest}
                  disabled={loading}
                >
                  Run Benchmark
                </Button>
              </Box>
            </CardContent>
          </Card>
        </Grid>

        {/* Loading Indicator */}
        {loading && (
          <Grid item xs={12}>
            <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
              <CircularProgress size={24} />
              <Typography>Running test...</Typography>
            </Box>
          </Grid>
        )}

        {/* Error Display */}
        {error && (
          <Grid item xs={12}>
            <Alert severity="error">
              {error}
            </Alert>
          </Grid>
        )}

        {/* Test Results */}
        {testResults.length > 0 && (
          <Grid item xs={12}>
            <Typography variant="h6" gutterBottom>
              Test Results
            </Typography>
            {testResults.map((result) => (
              <Accordion key={result.id} sx={{ mb: 2 }}>
                <AccordionSummary expandIcon={<ExpandMoreIcon />}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, width: '100%' }}>
                    {getStatusIcon(result.success)}
                    <Typography variant="subtitle1">
                      {result.type === 'benchmark' ? 'Benchmark Test' : 'Single Test'}
                    </Typography>
                    <Chip 
                      label={result.model} 
                      size="small" 
                      variant="outlined" 
                    />
                    <Typography variant="body2" color="text.secondary" sx={{ ml: 'auto' }}>
                      {result.timestamp.toLocaleString()}
                    </Typography>
                  </Box>
                </AccordionSummary>
                <AccordionDetails>
                  {result.type === 'single' ? (
                    <Grid container spacing={2}>
                      <Grid item xs={12}>
                        <Typography variant="subtitle2" gutterBottom>
                          Prompt:
                        </Typography>
                        <Typography variant="body2" sx={{ mb: 2, p: 1, bgcolor: 'grey.100', borderRadius: 1 }}>
                          {result.prompt}
                        </Typography>
                      </Grid>
                      <Grid item xs={12} md={6}>
                        <Typography variant="subtitle2" gutterBottom>
                          Response Time:
                        </Typography>
                        <Typography variant="body1">
                          {formatDuration(result.responseTime)}
                        </Typography>
                      </Grid>
                      <Grid item xs={12} md={6}>
                        <Typography variant="subtitle2" gutterBottom>
                          Tokens Used:
                        </Typography>
                        <Typography variant="body1">
                          {result.tokensUsed || 'N/A'}
                        </Typography>
                      </Grid>
                      {result.success && result.response && (
                        <Grid item xs={12}>
                          <Typography variant="subtitle2" gutterBottom>
                            Response:
                          </Typography>
                          <Typography variant="body2" sx={{ p: 2, bgcolor: 'grey.50', borderRadius: 1 }}>
                            {result.response}
                          </Typography>
                        </Grid>
                      )}
                      {!result.success && result.error && (
                        <Grid item xs={12}>
                          <Alert severity="error">
                            {result.error}
                          </Alert>
                        </Grid>
                      )}
                    </Grid>
                  ) : (
                    // Benchmark results
                    <Grid container spacing={2}>
                      <Grid item xs={12} md={4}>
                        <Typography variant="subtitle2" gutterBottom>
                          Success Rate:
                        </Typography>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                          <LinearProgress
                            variant="determinate"
                            value={result.successRate * 100}
                            sx={{ flexGrow: 1 }}
                          />
                          <Typography variant="body2">
                            {(result.successRate * 100).toFixed(1)}%
                          </Typography>
                        </Box>
                      </Grid>
                      <Grid item xs={12} md={4}>
                        <Typography variant="subtitle2" gutterBottom>
                          Avg Response Time:
                        </Typography>
                        <Typography variant="body1">
                          {formatDuration(result.avgResponseTime)}
                        </Typography>
                      </Grid>
                      <Grid item xs={12} md={4}>
                        <Typography variant="subtitle2" gutterBottom>
                          Total Tests:
                        </Typography>
                        <Typography variant="body1">
                          {result.totalTests}
                        </Typography>
                      </Grid>
                      {result.details && (
                        <Grid item xs={12}>
                          <Typography variant="subtitle2" gutterBottom>
                            Detailed Results:
                          </Typography>
                          <Box sx={{ maxHeight: 300, overflow: 'auto' }}>
                            {result.details.map((detail: any, index: number) => (
                              <Box key={index} sx={{ mb: 1, p: 1, bgcolor: 'grey.50', borderRadius: 1 }}>
                                <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                                  <Typography variant="body2">
                                    Test {index + 1}
                                  </Typography>
                                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                    {getStatusIcon(detail.success)}
                                    <Typography variant="body2">
                                      {formatDuration(detail.responseTime)}
                                    </Typography>
                                  </Box>
                                </Box>
                                {!detail.success && detail.error && (
                                  <Typography variant="body2" color="error" sx={{ mt: 1 }}>
                                    {detail.error}
                                  </Typography>
                                )}
                              </Box>
                            ))}
                          </Box>
                        </Grid>
                      )}
                    </Grid>
                  )}
                </AccordionDetails>
              </Accordion>
            ))}
          </Grid>
        )}
      </Grid>
    </Box>
  );
};