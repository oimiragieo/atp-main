# Task Clustering Pipeline Guide

## Overview

GAP-342 implements an incremental task clustering pipeline that combines TF-IDF text features with embedding-based features to create stable task clusters for SLM (Small Language Model) specialist selection.

## Architecture

The task clustering pipeline consists of:

1. **Feature Extraction**: Combines TF-IDF (Term Frequency-Inverse Document Frequency) with text embeddings
2. **Clustering Algorithm**: Uses AgglomerativeClustering (hierarchical clustering) for stable cluster assignments
3. **Incremental Updates**: Supports adding new data without full retraining
4. **Metrics & Monitoring**: Tracks cluster activity and churn rates

## Feature Extraction

### TF-IDF Features
- **Max Features**: 1000 most important terms
- **Stop Words**: English stop words removed
- **N-grams**: Unigrams and bigrams (1-2 word combinations)
- **Normalization**: L2 normalization applied

### Embedding Features
- **Service**: Configurable embedding service (default: MockEmbeddingService)
- **Dimensions**: 128-dimensional embeddings (configurable)
- **Fallback**: Hash-based mock embeddings when service unavailable

### Combined Features
- **Concatenation**: TF-IDF + embedding features combined
- **Scaling**: StandardScaler applied to normalize feature distributions
- **Dimensionality**: Variable based on TF-IDF vocabulary + embedding dimensions

## Clustering Algorithm

### AgglomerativeClustering
- **Linkage**: Ward's method (minimizes variance)
- **Distance**: Euclidean distance
- **Clusters**: Configurable number (default: 10)
- **Stability**: Hierarchical structure ensures consistent assignments

### Incremental Updates
- **Retraining**: Full pipeline retraining on new data
- **Cluster Tracking**: Maintains assignment history for churn analysis
- **Performance**: Scales with training data size

## Metrics

### Cluster Activity
- `atp_task_clusters_active`: Number of active clusters
- `atp_clustering_requests_total`: Total clustering training requests
- `atp_cluster_assignments_total`: Total classification requests

### Churn Analysis
- `atp_cluster_churn_rate`: Rate of cluster assignment changes (0.0-1.0)
- **Calculation**: `(changed_assignments / total_assignments)` over time window

## Usage

### Training
```python
from router_service.task_clustering_pipeline import TASK_CLUSTERING_PIPELINE

# Train on task prompts
prompts = [
    "Write a Python function",
    "Debug JavaScript code",
    "Summarize article",
    "Translate document"
]

TASK_CLUSTERING_PIPELINE.train_clusters(prompts)
```

### Classification
```python
# Classify new tasks
cluster = TASK_CLUSTERING_PIPELINE.classify_task("Create a machine learning model")
# Returns: "task_cluster_0", "task_cluster_1", etc.
```

### Incremental Updates
```python
# Add new training data
new_prompts = ["Analyze dataset", "Generate report"]
TASK_CLUSTERING_PIPELINE.incremental_update(new_prompts)
```

## Configuration

### Parameters
- `n_clusters`: Number of target clusters (default: 10)
- `tfidf_max_features`: Max TF-IDF features (default: 1000)
- `embedding_service`: Custom embedding service implementation
- `random_state`: Random seed for reproducibility

### Environment Variables
- `CLUSTER_HASH_BUCKETS`: Fallback bucket count for heuristic clustering

## Integration Points

### SLM Training Data
- **Task Classification**: Routes tasks to appropriate SLM specialists
- **Observation Enrichment**: Adds cluster metadata to training observations
- **Quality Tracking**: Monitors cluster-specific performance metrics

### Router Service
- **Task Classification**: Integrated with `task_classify.py` for cluster hints
- **Metrics Registry**: Publishes clustering metrics to Prometheus
- **Fallback Support**: Graceful degradation when clustering unavailable

## Monitoring & Debugging

### Health Checks
- `is_trained`: Whether clustering model is available
- `training_samples`: Number of training examples
- `cluster_sizes`: Distribution of samples across clusters

### Performance Metrics
- **Training Time**: Time to train clustering model
- **Classification Latency**: Time to classify new tasks
- **Memory Usage**: Feature matrices and cluster centers

### Troubleshooting
- **Empty Clusters**: Check training data diversity
- **High Churn**: Review feature stability and training frequency
- **Classification Failures**: Verify TF-IDF/transformer state

## Future Enhancements

### Planned Improvements
- **HDBSCAN Integration**: Replace AgglomerativeClustering with HDBSCAN
- **Online Learning**: True incremental learning without full retraining
- **Cluster Validation**: Automatic determination of optimal cluster count
- **Feature Engineering**: Domain-specific feature extractors

### Research Areas
- **Temporal Clustering**: Time-aware cluster evolution
- **Multi-modal Features**: Image/text/audio clustering support
- **Federated Clustering**: Distributed cluster training across nodes
