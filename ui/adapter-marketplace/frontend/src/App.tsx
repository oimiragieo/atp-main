/*
 * Copyright 2025 ATP Project Contributors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import React, { useState, useEffect } from 'react';
import {
  AppBar,
  Toolbar,
  Typography,
  Container,
  Grid,
  Card,
  CardContent,
  CardActions,
  Button,
  TextField,
  Select,
  MenuItem,
  FormControl,
  InputLabel,
  Chip,
  Rating,
  Box,
  Tabs,
  Tab,
  Dialog,
  DialogTitle,
  DialogContent,
  DialogActions,
  IconButton,
  Badge,
  Avatar,
  List,
  ListItem,
  ListItemText,
  ListItemAvatar,
  Divider,
  Paper,
  LinearProgress,
  Snackbar,
  Alert
} from '@mui/material';
import {
  Search as SearchIcon,
  Download as DownloadIcon,
  Star as StarIcon,
  Verified as VerifiedIcon,
  Code as CodeIcon,
  Security as SecurityIcon,
  Speed as SpeedIcon,
  TrendingUp as TrendingUpIcon,
  FilterList as FilterListIcon,
  Close as CloseIcon
} from '@mui/icons-material';
import { ThemeProvider, createTheme } from '@mui/material/styles';
import CssBaseline from '@mui/material/CssBaseline';

// Types
interface Adapter {
  id: string;
  name: string;
  description: string;
  author_id: string;
  category: string;
  provider_type?: string;
  version: string;
  license: string;
  downloads: number;
  rating: number;
  rating_count: number;
  featured: boolean;
  verified: boolean;
  supported_models: string[];
  capabilities: Record<string, any>;
  requirements: Record<string, any>;
  certification_status: string;
  pricing_model: string;
  price: number;
  package_url?: string;
  documentation_url?: string;
  source_url?: string;
  created_at: string;
  updated_at: string;
  published_at?: string;
}

interface Review {
  id: string;
  adapter_id: string;
  user_id: string;
  rating: number;
  title?: string;
  content?: string;
  created_at: string;
  updated_at: string;
}

interface MarketplaceStats {
  total_adapters: number;
  total_downloads: number;
  total_reviews: number;
  verified_adapters: number;
  verification_rate: number;
}

// Theme
const theme = createTheme({
  palette: {
    primary: {
      main: '#1976d2',
    },
    secondary: {
      main: '#dc004e',
    },
  },
});

// API Base URL
const API_BASE_URL = process.env.REACT_APP_API_URL || 'http://localhost:8000';

// Main App Component
const App: React.FC = () => {
  const [adapters, setAdapters] = useState<Adapter[]>([]);
  const [filteredAdapters, setFilteredAdapters] = useState<Adapter[]>([]);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [selectedCategory, setSelectedCategory] = useState('');
  const [selectedProvider, setSelectedProvider] = useState('');
  const [selectedPricing, setSelectedPricing] = useState('');
  const [minRating, setMinRating] = useState(0);
  const [verifiedOnly, setVerifiedOnly] = useState(false);
  const [featuredOnly, setFeaturedOnly] = useState(false);
  const [sortBy, setSortBy] = useState('score');
  const [selectedAdapter, setSelectedAdapter] = useState<Adapter | null>(null);
  const [adapterReviews, setAdapterReviews] = useState<Review[]>([]);
  const [tabValue, setTabValue] = useState(0);
  const [stats, setStats] = useState<MarketplaceStats | null>(null);
  const [categories, setCategories] = useState<string[]>([]);
  const [providers, setProviders] = useState<string[]>([]);
  const [snackbar, setSnackbar] = useState({ open: false, message: '', severity: 'info' as 'info' | 'success' | 'warning' | 'error' });

  // Fetch data on component mount
  useEffect(() => {
    fetchAdapters();
    fetchStats();
    fetchCategories();
    fetchProviders();
  }, []);

  // Filter adapters when filters change
  useEffect(() => {
    filterAdapters();
  }, [adapters, searchTerm, selectedCategory, selectedProvider, selectedPricing, minRating, verifiedOnly, featuredOnly, sortBy]);

  const fetchAdapters = async () => {
    try {
      setLoading(true);
      const response = await fetch(`${API_BASE_URL}/adapters?limit=100&sort_by=${sortBy}`);
      const data = await response.json();
      setAdapters(data);
    } catch (error) {
      console.error('Error fetching adapters:', error);
      showSnackbar('Error fetching adapters', 'error');
    } finally {
      setLoading(false);
    }
  };

  const fetchStats = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/stats`);
      const data = await response.json();
      setStats(data);
    } catch (error) {
      console.error('Error fetching stats:', error);
    }
  };

  const fetchCategories = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/categories`);
      const data = await response.json();
      setCategories(data);
    } catch (error) {
      console.error('Error fetching categories:', error);
    }
  };

  const fetchProviders = async () => {
    try {
      const response = await fetch(`${API_BASE_URL}/providers`);
      const data = await response.json();
      setProviders(data);
    } catch (error) {
      console.error('Error fetching providers:', error);
    }
  };

  const fetchAdapterReviews = async (adapterId: string) => {
    try {
      const response = await fetch(`${API_BASE_URL}/adapters/${adapterId}/reviews`);
      const data = await response.json();
      setAdapterReviews(data);
    } catch (error) {
      console.error('Error fetching reviews:', error);
    }
  };

  const filterAdapters = () => {
    let filtered = [...adapters];

    // Search filter
    if (searchTerm) {
      filtered = filtered.filter(adapter =>
        adapter.name.toLowerCase().includes(searchTerm.toLowerCase()) ||
        adapter.description.toLowerCase().includes(searchTerm.toLowerCase())
      );
    }

    // Category filter
    if (selectedCategory) {
      filtered = filtered.filter(adapter => adapter.category === selectedCategory);
    }

    // Provider filter
    if (selectedProvider) {
      filtered = filtered.filter(adapter => adapter.provider_type === selectedProvider);
    }

    // Pricing filter
    if (selectedPricing) {
      filtered = filtered.filter(adapter => adapter.pricing_model === selectedPricing);
    }

    // Rating filter
    if (minRating > 0) {
      filtered = filtered.filter(adapter => adapter.rating >= minRating);
    }

    // Verified filter
    if (verifiedOnly) {
      filtered = filtered.filter(adapter => adapter.verified);
    }

    // Featured filter
    if (featuredOnly) {
      filtered = filtered.filter(adapter => adapter.featured);
    }

    // Sort
    filtered.sort((a, b) => {
      switch (sortBy) {
        case 'downloads':
          return b.downloads - a.downloads;
        case 'rating':
          return b.rating - a.rating;
        case 'created_at':
          return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
        case 'updated_at':
          return new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime();
        default: // score
          return calculateScore(b) - calculateScore(a);
      }
    });

    setFilteredAdapters(filtered);
  };

  const calculateScore = (adapter: Adapter): number => {
    const baseScore = adapter.rating * adapter.rating_count;
    const downloadScore = Math.min(adapter.downloads / 1000, 10);
    const verificationBonus = adapter.verified ? 5 : 0;
    const featuredBonus = adapter.featured ? 3 : 0;
    return baseScore + downloadScore + verificationBonus + featuredBonus;
  };

  const handleAdapterClick = (adapter: Adapter) => {
    setSelectedAdapter(adapter);
    fetchAdapterReviews(adapter.id);
  };

  const handleDownload = async (adapter: Adapter) => {
    try {
      const response = await fetch(`${API_BASE_URL}/adapters/${adapter.id}/download`, {
        method: 'POST',
        headers: {
          'Authorization': 'Bearer your-token-here', // In real app, get from auth context
        },
      });
      
      if (response.ok) {
        const data = await response.json();
        window.open(data.download_url, '_blank');
        showSnackbar('Download started', 'success');
        
        // Update download count locally
        setAdapters(prev => prev.map(a => 
          a.id === adapter.id ? { ...a, downloads: a.downloads + 1 } : a
        ));
      } else {
        throw new Error('Download failed');
      }
    } catch (error) {
      console.error('Error downloading adapter:', error);
      showSnackbar('Download failed', 'error');
    }
  };

  const showSnackbar = (message: string, severity: 'info' | 'success' | 'warning' | 'error') => {
    setSnackbar({ open: true, message, severity });
  };

  const closeSnackbar = () => {
    setSnackbar(prev => ({ ...prev, open: false }));
  };

  const AdapterCard: React.FC<{ adapter: Adapter }> = ({ adapter }) => (
    <Card sx={{ height: '100%', display: 'flex', flexDirection: 'column' }}>
      <CardContent sx={{ flexGrow: 1 }}>
        <Box display="flex" alignItems="center" mb={1}>
          <Typography variant="h6" component="h2" sx={{ flexGrow: 1 }}>
            {adapter.name}
          </Typography>
          {adapter.verified && (
            <VerifiedIcon color="primary" sx={{ ml: 1 }} />
          )}
          {adapter.featured && (
            <Chip label="Featured" color="secondary" size="small" sx={{ ml: 1 }} />
          )}
        </Box>
        
        <Typography variant="body2" color="text.secondary" paragraph>
          {adapter.description}
        </Typography>
        
        <Box display="flex" alignItems="center" mb={1}>
          <Rating value={adapter.rating} readOnly size="small" />
          <Typography variant="body2" sx={{ ml: 1 }}>
            ({adapter.rating_count})
          </Typography>
        </Box>
        
        <Box display="flex" gap={1} mb={1}>
          <Chip label={adapter.category} size="small" />
          {adapter.provider_type && (
            <Chip label={adapter.provider_type} size="small" variant="outlined" />
          )}
          <Chip 
            label={adapter.pricing_model} 
            size="small" 
            color={adapter.pricing_model === 'free' ? 'success' : 'default'}
          />
        </Box>
        
        <Typography variant="body2" color="text.secondary">
          Downloads: {adapter.downloads.toLocaleString()}
        </Typography>
        
        <Typography variant="body2" color="text.secondary">
          Version: {adapter.version}
        </Typography>
      </CardContent>
      
      <CardActions>
        <Button 
          size="small" 
          onClick={() => handleAdapterClick(adapter)}
        >
          View Details
        </Button>
        <Button 
          size="small" 
          startIcon={<DownloadIcon />}
          onClick={() => handleDownload(adapter)}
          disabled={!adapter.package_url}
        >
          Download
        </Button>
      </CardActions>
    </Card>
  );

  const AdapterDetailDialog: React.FC = () => (
    <Dialog 
      open={!!selectedAdapter} 
      onClose={() => setSelectedAdapter(null)}
      maxWidth="md"
      fullWidth
    >
      {selectedAdapter && (
        <>
          <DialogTitle>
            <Box display="flex" alignItems="center" justifyContent="space-between">
              <Box display="flex" alignItems="center">
                <Typography variant="h5">{selectedAdapter.name}</Typography>
                {selectedAdapter.verified && (
                  <VerifiedIcon color="primary" sx={{ ml: 1 }} />
                )}
              </Box>
              <IconButton onClick={() => setSelectedAdapter(null)}>
                <CloseIcon />
              </IconButton>
            </Box>
          </DialogTitle>
          
          <DialogContent>
            <Tabs value={tabValue} onChange={(_, newValue) => setTabValue(newValue)}>
              <Tab label="Overview" />
              <Tab label="Reviews" />
              <Tab label="Technical" />
            </Tabs>
            
            {tabValue === 0 && (
              <Box mt={2}>
                <Typography paragraph>{selectedAdapter.description}</Typography>
                
                <Grid container spacing={2} mb={2}>
                  <Grid item xs={6}>
                    <Typography variant="subtitle2">Category</Typography>
                    <Typography>{selectedAdapter.category}</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="subtitle2">Provider Type</Typography>
                    <Typography>{selectedAdapter.provider_type || 'N/A'}</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="subtitle2">Version</Typography>
                    <Typography>{selectedAdapter.version}</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="subtitle2">License</Typography>
                    <Typography>{selectedAdapter.license}</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="subtitle2">Downloads</Typography>
                    <Typography>{selectedAdapter.downloads.toLocaleString()}</Typography>
                  </Grid>
                  <Grid item xs={6}>
                    <Typography variant="subtitle2">Rating</Typography>
                    <Box display="flex" alignItems="center">
                      <Rating value={selectedAdapter.rating} readOnly size="small" />
                      <Typography sx={{ ml: 1 }}>
                        ({selectedAdapter.rating_count})
                      </Typography>
                    </Box>
                  </Grid>
                </Grid>
                
                {selectedAdapter.supported_models.length > 0 && (
                  <Box mb={2}>
                    <Typography variant="subtitle2" mb={1}>Supported Models</Typography>
                    <Box display="flex" gap={1} flexWrap="wrap">
                      {selectedAdapter.supported_models.map(model => (
                        <Chip key={model} label={model} size="small" />
                      ))}
                    </Box>
                  </Box>
                )}
                
                <Box display="flex" gap={2} mt={2}>
                  {selectedAdapter.source_url && (
                    <Button 
                      variant="outlined" 
                      startIcon={<CodeIcon />}
                      href={selectedAdapter.source_url}
                      target="_blank"
                    >
                      Source Code
                    </Button>
                  )}
                  {selectedAdapter.documentation_url && (
                    <Button 
                      variant="outlined"
                      href={selectedAdapter.documentation_url}
                      target="_blank"
                    >
                      Documentation
                    </Button>
                  )}
                </Box>
              </Box>
            )}
            
            {tabValue === 1 && (
              <Box mt={2}>
                <Typography variant="h6" mb={2}>Reviews</Typography>
                {adapterReviews.length === 0 ? (
                  <Typography color="text.secondary">No reviews yet</Typography>
                ) : (
                  <List>
                    {adapterReviews.map((review, index) => (
                      <React.Fragment key={review.id}>
                        <ListItem alignItems="flex-start">
                          <ListItemAvatar>
                            <Avatar>{review.user_id.charAt(0).toUpperCase()}</Avatar>
                          </ListItemAvatar>
                          <ListItemText
                            primary={
                              <Box display="flex" alignItems="center" gap={1}>
                                <Rating value={review.rating} readOnly size="small" />
                                {review.title && (
                                  <Typography variant="subtitle2">{review.title}</Typography>
                                )}
                              </Box>
                            }
                            secondary={
                              <>
                                {review.content && (
                                  <Typography variant="body2" paragraph>
                                    {review.content}
                                  </Typography>
                                )}
                                <Typography variant="caption" color="text.secondary">
                                  {new Date(review.created_at).toLocaleDateString()}
                                </Typography>
                              </>
                            }
                          />
                        </ListItem>
                        {index < adapterReviews.length - 1 && <Divider />}
                      </React.Fragment>
                    ))}
                  </List>
                )}
              </Box>
            )}
            
            {tabValue === 2 && (
              <Box mt={2}>
                <Typography variant="h6" mb={2}>Technical Details</Typography>
                
                <Paper sx={{ p: 2, mb: 2 }}>
                  <Typography variant="subtitle2" mb={1}>Capabilities</Typography>
                  <pre style={{ fontSize: '0.875rem', overflow: 'auto' }}>
                    {JSON.stringify(selectedAdapter.capabilities, null, 2)}
                  </pre>
                </Paper>
                
                <Paper sx={{ p: 2, mb: 2 }}>
                  <Typography variant="subtitle2" mb={1}>Requirements</Typography>
                  <pre style={{ fontSize: '0.875rem', overflow: 'auto' }}>
                    {JSON.stringify(selectedAdapter.requirements, null, 2)}
                  </pre>
                </Paper>
                
                <Box display="flex" alignItems="center" gap={2}>
                  <SecurityIcon color={selectedAdapter.verified ? 'success' : 'disabled'} />
                  <Typography>
                    Certification Status: {selectedAdapter.certification_status}
                  </Typography>
                </Box>
              </Box>
            )}
          </DialogContent>
          
          <DialogActions>
            <Button onClick={() => setSelectedAdapter(null)}>Close</Button>
            <Button 
              variant="contained" 
              startIcon={<DownloadIcon />}
              onClick={() => handleDownload(selectedAdapter)}
              disabled={!selectedAdapter.package_url}
            >
              Download
            </Button>
          </DialogActions>
        </>
      )}
    </Dialog>
  );

  return (
    <ThemeProvider theme={theme}>
      <CssBaseline />
      
      <AppBar position="static">
        <Toolbar>
          <Typography variant="h6" component="div" sx={{ flexGrow: 1 }}>
            ATP Adapter Marketplace
          </Typography>
          {stats && (
            <Box display="flex" gap={2}>
              <Typography variant="body2">
                {stats.total_adapters} Adapters
              </Typography>
              <Typography variant="body2">
                {stats.total_downloads.toLocaleString()} Downloads
              </Typography>
            </Box>
          )}
        </Toolbar>
      </AppBar>
      
      <Container maxWidth="xl" sx={{ mt: 4, mb: 4 }}>
        {/* Search and Filters */}
        <Paper sx={{ p: 3, mb: 3 }}>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} md={4}>
              <TextField
                fullWidth
                placeholder="Search adapters..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                InputProps={{
                  startAdornment: <SearchIcon sx={{ mr: 1, color: 'text.secondary' }} />
                }}
              />
            </Grid>
            
            <Grid item xs={6} md={2}>
              <FormControl fullWidth>
                <InputLabel>Category</InputLabel>
                <Select
                  value={selectedCategory}
                  onChange={(e) => setSelectedCategory(e.target.value)}
                  label="Category"
                >
                  <MenuItem value="">All</MenuItem>
                  {categories.map(category => (
                    <MenuItem key={category} value={category}>
                      {category}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            
            <Grid item xs={6} md={2}>
              <FormControl fullWidth>
                <InputLabel>Provider</InputLabel>
                <Select
                  value={selectedProvider}
                  onChange={(e) => setSelectedProvider(e.target.value)}
                  label="Provider"
                >
                  <MenuItem value="">All</MenuItem>
                  {providers.map(provider => (
                    <MenuItem key={provider} value={provider}>
                      {provider}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            </Grid>
            
            <Grid item xs={6} md={2}>
              <FormControl fullWidth>
                <InputLabel>Pricing</InputLabel>
                <Select
                  value={selectedPricing}
                  onChange={(e) => setSelectedPricing(e.target.value)}
                  label="Pricing"
                >
                  <MenuItem value="">All</MenuItem>
                  <MenuItem value="free">Free</MenuItem>
                  <MenuItem value="paid">Paid</MenuItem>
                  <MenuItem value="freemium">Freemium</MenuItem>
                </Select>
              </FormControl>
            </Grid>
            
            <Grid item xs={6} md={2}>
              <FormControl fullWidth>
                <InputLabel>Sort By</InputLabel>
                <Select
                  value={sortBy}
                  onChange={(e) => setSortBy(e.target.value)}
                  label="Sort By"
                >
                  <MenuItem value="score">Relevance</MenuItem>
                  <MenuItem value="downloads">Downloads</MenuItem>
                  <MenuItem value="rating">Rating</MenuItem>
                  <MenuItem value="created_at">Newest</MenuItem>
                  <MenuItem value="updated_at">Recently Updated</MenuItem>
                </Select>
              </FormControl>
            </Grid>
          </Grid>
        </Paper>
        
        {/* Results */}
        {loading ? (
          <LinearProgress />
        ) : (
          <>
            <Typography variant="h6" mb={2}>
              {filteredAdapters.length} adapters found
            </Typography>
            
            <Grid container spacing={3}>
              {filteredAdapters.map(adapter => (
                <Grid item xs={12} sm={6} md={4} lg={3} key={adapter.id}>
                  <AdapterCard adapter={adapter} />
                </Grid>
              ))}
            </Grid>
          </>
        )}
      </Container>
      
      <AdapterDetailDialog />
      
      <Snackbar
        open={snackbar.open}
        autoHideDuration={6000}
        onClose={closeSnackbar}
      >
        <Alert onClose={closeSnackbar} severity={snackbar.severity}>
          {snackbar.message}
        </Alert>
      </Snackbar>
    </ThemeProvider>
  );
};

export default App;