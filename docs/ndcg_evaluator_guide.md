# GAP-306: Ranking & Relevance Quality Metrics

## Overview

This document describes the implementation of NDCG@k evaluator harness for ranking and relevance quality metrics in the ATP platform. The implementation provides comprehensive evaluation capabilities for vector search ranking quality using Normalized Discounted Cumulative Gain (NDCG) metrics.

## Architecture

### Core Components

#### NDCGEvaluator Class
- **Location**: `tools/ndcg_evaluator.py`
- **Purpose**: Main evaluator class implementing NDCG@k calculations
- **Key Methods**:
  - `dcg_at_k()`: Calculates Discounted Cumulative Gain at k
  - `idcg_at_k()`: Calculates Ideal DCG at k (best possible ranking)
  - `ndcg_at_k()`: Calculates Normalized DCG at k
  - `evaluate_ranking()`: Evaluates a single ranking
  - `compare_rankings()`: Compares baseline vs improved rankings

#### Metrics Integration
- **Metric**: `vector_ndcg_avg` (histogram)
- **Buckets**: [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]
- **Purpose**: Tracks NDCG scores across evaluations for monitoring ranking quality

#### Synthetic Data Generation
- **Function**: `create_synthetic_evaluation_data()`
- **Purpose**: Generates test data for evaluation and benchmarking
- **Features**:
  - Configurable number of items and embedding dimensions
  - Realistic relevance score distributions
  - Ground truth relevance judgments

## API Usage

### Basic Evaluation

```python
from tools.ndcg_evaluator import NDCGEvaluator

# Create evaluator with custom k values
evaluator = NDCGEvaluator(k_values=[1, 3, 5, 10])

# Prepare ranking results
ranked_items = [
    {'key': 'doc_1', 'score': 0.9},
    {'key': 'doc_2', 'score': 0.8},
    {'key': 'doc_3', 'score': 0.7}
]

# Ground truth relevance judgments
relevance_judgments = {
    'doc_1': 1.0,  # Highly relevant
    'doc_2': 0.5,  # Moderately relevant
    'doc_3': 0.0   # Not relevant
}

# Evaluate ranking
results = evaluator.evaluate_ranking(ranked_items, relevance_judgments)
print(results)
# Output: {'ndcg@1': 1.0, 'ndcg@3': 0.9203, 'ndcg@5': 0.9203, 'ndcg@10': 0.9203}
```

### Ranking Comparison

```python
# Compare baseline vs improved rankings
baseline_ranking = [
    {'key': 'doc_1'},  # Wrong order
    {'key': 'doc_2'},
    {'key': 'doc_3'}
]

improved_ranking = [
    {'key': 'doc_2'},  # Correct order by relevance
    {'key': 'doc_1'},
    {'key': 'doc_3'}
]

comparison = evaluator.compare_rankings(
    baseline_ranking, improved_ranking, relevance_judgments
)

print(comparison)
# Output includes baseline scores, improved scores, and improvement percentages
```

### Synthetic Data Generation

```python
from tools.ndcg_evaluator import create_synthetic_evaluation_data

# Generate test data
items, query_embedding, relevance_judgments = create_synthetic_evaluation_data(
    num_items=100,      # Total items to rank
    embedding_dim=384,  # Embedding dimensionality
    num_relevant=10     # Number of highly relevant items
)

# Use for evaluation
results = evaluator.evaluate_ranking(items, relevance_judgments)
```

## NDCG@k Calculation Details

### Discounted Cumulative Gain (DCG)
DCG@k measures the ranking quality by giving higher weight to relevant items at top positions:

```
DCG@k = sum_{i=1 to k} rel_i / log2(i + 1)
```

Where:
- `rel_i` is the relevance score of item at position i
- The denominator `log2(i + 1)` provides the discount factor

### Ideal DCG (IDCG)
IDCG@k represents the best possible DCG@k score:

```
IDCG@k = DCG@k with items sorted by relevance descending
```

### Normalized DCG (NDCG)
NDCG@k normalizes DCG@k by the ideal DCG:

```
NDCG@k = DCG@k / IDCG@k
```

NDCG@k values range from 0.0 (worst possible ranking) to 1.0 (perfect ranking).

## Configuration

### K Values
Configure which k values to evaluate:

```python
# Default k values
evaluator = NDCGEvaluator()  # [1, 3, 5, 10]

# Custom k values
evaluator = NDCGEvaluator(k_values=[1, 5, 10, 20])
```

### Metrics Configuration
The `vector_ndcg_avg` histogram is automatically configured with appropriate buckets for NDCG score distribution tracking.

## Integration with Vector Backend

The evaluator is designed to work seamlessly with the existing vector backend infrastructure:

```python
from tools.vector_backend import get_vector_backend
from tools.ndcg_evaluator import NDCGEvaluator

# Get vector backend
backend = get_vector_backend({
    'type': 'in_memory',
    'metrics_callback': None
})

# Perform search
query_embedding = [0.1, 0.2, 0.3]  # Your query embedding
search_results = backend.query('my_namespace', query_embedding, k=10)

# Convert to evaluator format
ranked_items = [
    {'key': result.key, 'score': result.score}
    for result in search_results
]

# Evaluate (would need relevance judgments)
# results = evaluator.evaluate_ranking(ranked_items, relevance_judgments)
```

## Testing

### Test Coverage
- **Location**: `tests/test_ndcg_evaluator.py`
- **Coverage**:
  - NDCG calculation accuracy
  - Ranking comparison functionality
  - Synthetic data generation
  - Edge cases (empty rankings, single items)

### Running Tests

```bash
# Run NDCG evaluator tests
python -m pytest tests/test_ndcg_evaluator.py -v

# Or run directly
python tests/test_ndcg_evaluator.py
```

## Performance Considerations

### Computational Complexity
- **DCG/IDCG Calculation**: O(k) where k is the number of items to evaluate
- **Sorting for IDCG**: O(n log n) for n relevance scores
- **Memory Usage**: O(n) for storing relevance scores

### Optimization Recommendations
1. **Pre-compute IDCG**: If evaluating multiple rankings with the same relevance judgments
2. **Batch Evaluation**: Process multiple rankings together for better cache locality
3. **Approximate NDCG**: For very large k values, consider truncated calculations

## Monitoring and Observability

### Metrics
- **vector_ndcg_avg**: Histogram of NDCG scores across all evaluations
- **Granularity**: Per evaluation call
- **Use Cases**:
  - Track ranking quality trends over time
  - Compare different ranking algorithms
  - Monitor performance degradation

### Logging
The evaluator integrates with the platform's logging infrastructure for debugging and monitoring.

## Future Enhancements

### Potential Extensions
1. **Additional Metrics**: Implement MAP, MRR, and other ranking metrics
2. **Statistical Significance**: Add confidence intervals for ranking comparisons
3. **A/B Testing**: Framework for comparing ranking algorithms in production
4. **Real-time Evaluation**: Streaming evaluation for online learning scenarios

### Integration Opportunities
1. **Router Service**: Integrate with ask endpoint for real-time ranking evaluation
2. **Continuous Learning**: Use NDCG feedback for model improvement
3. **Dashboard Integration**: Add ranking quality metrics to monitoring dashboards

## Troubleshooting

### Common Issues

1. **Zero NDCG Scores**
   - **Cause**: All relevance judgments are 0.0
   - **Solution**: Ensure relevance judgments include positive values

2. **Unexpected NDCG Values**
   - **Cause**: Incorrect ranking order or relevance judgment mapping
   - **Solution**: Verify item keys match between ranking and judgments

3. **Performance Issues**
   - **Cause**: Large k values with many items
   - **Solution**: Use smaller k values or implement truncated evaluation

### Debug Mode
Enable detailed logging for troubleshooting:

```python
import logging
logging.getLogger('tools.ndcg_evaluator').setLevel(logging.DEBUG)
```

## Dependencies

- **metrics.registry**: For histogram metrics recording
- **numpy**: For vector operations in synthetic data generation
- **math**: For logarithmic calculations in DCG
- **random**: For synthetic data generation
- **typing**: For type annotations

## Conclusion

The NDCG@k evaluator provides a robust foundation for ranking quality assessment in the ATP platform. It enables:

- Quantitative evaluation of ranking algorithms
- Baseline vs improved ranking comparisons
- Integration with existing vector search infrastructure
- Comprehensive monitoring and observability

The implementation follows platform conventions for metrics, testing, and documentation, ensuring maintainability and extensibility for future enhancements.
