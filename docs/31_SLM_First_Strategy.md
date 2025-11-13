# SLM-First Strategy Alignment (Paper: "Small Language Models are the Future of Agentic AI", arXiv:2506.02153)

## 1. Core Claims (Concise)
- Sufficiency: Modern <10B param SLMs meet many agentic subtask capability needs (reasoning, tool calling, code, instruction following) with augmentation.
- Suitability: Agent subtasks are narrow, repetitive, format-constrained; alignment + determinism favored over broad generality.
- Economics: 10–30× lower latency / energy / FLOPs vs monolithic LLM; simpler infra (less parallelism) → lower OpEx and greener footprint.
- Flexibility: Cheap PEFT / LoRA / QLoRA / distillation → overnight specialization & rapid iteration.
- Heterogeneity: Natural multi-model composition; invoke large models sparsely for complex planning or out-of-distribution escalations.
- Data Flywheel: Agent orchestration surfaces structured, evaluable interactions → organic fine-tuning corpus for SLM specialists.
- Barriers: Infra sunk cost (centralized LLM), benchmarking inertia (generalist metrics), awareness/marketing gap.

## 2. Implications for ATP Platform
| Dimension | Present POC State | SLM-First Enhancement |
|----------|-------------------|-----------------------|
| Routing | Static cost/quality heuristic | Multi-armed (bandit + constraint solver) picking among specialized SLM experts + fallback LLM |
| Cost Accounting | Basic per-call estimate | Granular per-model token, energy (optional), carbon proxy, savings vs baseline frontiers |
| Memory / Context Fabric | Generic | Task cluster aware context templates; per-cluster compression & retrieval profiles |
| Policy / Governance | POC ABAC / egress | Model-level safety score gating & differential privacy logging for new specialists |
| Observability | Traces + basic metrics | Model registry metrics: win-rate, regret, success@k, escalation rate, drift signatures |
| Continuous Learning | Not yet wired | S1–S6 conversion loop implemented as scheduled/triggered pipeline |
| Federation | Concept | Distribute distilled SLM packs; signed provenance & capability manifest |
| Marketplace / Adapters | General | Adapter declares task cluster tags enabling auto matching to SLM specialist set |

## 3. ATP-Specific SLM Conversion Loop (Operationalization of S1–S6)
1. Instrumentation (S1):
   - Add router streaming hook capturing: (task_type guess, prompt hash, normalized prompt template ID, tool schema signature, response, latency, cost, model, outcome label). Store anonymized event to `slm_observation` table / topic.
   - PII/PHI screening: apply existing `pii` redaction pass (memory-gateway) before persistence.
2. Data Curation (S2):
   - Offline job (Airflow / Dagster later): filter events passing safety + cost ceiling; dedupe by semantic hash (MinHash over normalized tokens) to reduce over-representation.
3. Task Clustering (S3):
   - Feature vector: TF-IDF(verbs+tool names) + structural tokens (JSON keys) + average embedding (existing vector store). Run incremental HDBSCAN or KMeansMiniBatch. Persist cluster_id.
4. SLM Candidate Selection (S4):
   - Registry entry schema: {model_name, params, context_len, license, max_tokens/sec, cost_per_1k, supported_clusters[], safety_grade, eval_scores{}}.
   - Populate initial open models (Phi-3-mini, Nemotron-4.8B, SmolLM2-1.7B, DeepSeek-R1-distill-7B) with coarse capabilities.
5. Fine-Tuning / Distill (S5):
   - For each cluster with >N examples & >X daily calls & baseline regret >Y%: generate supervised pairs (prompt_template + filled variables, target response). Use PEFT (LoRA rank 16) + 4-bit QLoRA for efficiency; store adapter weights + hash chain.
   - Optionally add distillation pairs: teacher frontier LLM vs ground truth tool success outputs.
6. Iteration & Routing Promotion (S6):
   - Shadow eval: New SLM serves in parallel (silent) for M calls; compute win-rate (tool success, formatting correctness, latency delta, cost delta). Promote when win-rate ≥ target and regression metrics < thresholds.

## 4. Model Routing Decision Function (Target Contract)
Inputs: task_features, cluster_id, latency_budget_ms, max_cost, safety_level, user_tier.
Outputs: (primary_model, escalation_chain[], justification, expected_cost_range, expected_latency_p95).
Constraints: cost <= max_cost; safety_grade >= policy; predicted quality >= SLA; carbon_intensity preference (optional future).
Ranking Objective: Minimize expected cost subject to SLA; incorporate exploration epsilon for under-evaluated specialists.

## 5. Key Metrics & Dashboards
- Cost: avg_cost_per_task_cluster, savings_pct_vs_frontier.
- Performance: success_rate@cluster, escalation_rate, regret_vs_best_available.
- Learning: cluster_coverage (% clusters with specialist), mean_promotion_cycle_days.
- Quality: formatting_error_rate, tool_call_parse_error_rate.
- Safety: redaction_incident_rate, blocked_model_invocations.
- Sustainability (optional): estimated_kwh_saved (via tokens * joules/token heuristic), carbon_co2e_saved.

## 6. Governance & Safety Enhancements
- Add model capability manifest signed (hash of weights, adapter, safety eval vector) -> stored in audit chain.
- Policy engine rule: deny routing if specialist safety_grade < required or last 1h formatting_error_rate > threshold.
- DP / Privacy: configurable token sampling & noise addition for analytics exports (reuse existing DP sampler POC) -> ensures aggregated cluster metrics privacy.

## 7. Data & Storage Additions
Tables (logical):
- model_registry
- model_metrics_timeseries
- slm_observation_raw (append-only)
- slm_observation_curated (post-redaction, clustered)
- cluster_model_assignment
- promotion_audit_log

## 8. Minimal Initial Code Changes (Phase 1 Target)
1. Extend `router_service/models.py` with TaskMetadata (task_type optional) & add to `AskRequest`.
2. Introduce `router_service/task_classify.py` (heuristic: regex + keyword map; placeholder for ML classifier) returning cluster_hint.
3. Modify `/v1/ask` to:
   - Derive cluster_hint.
   - Include model plan in first event frame: {type:"plan", candidates:[...]}.
   - Emit structured observation (async queue) to an in-memory ring; background task batches to disk (JSONL) as proto for future pipeline.
4. Add unit test asserting plan frame + final metrics fields + anonymization (prompt hash instead of raw if flag set).

## 9. Promotion Policy (Initial Thresholds)
- Shadow sample size: 300 calls.
- Success criteria: ≥98% formatting compliance; ≥95% tool success parity; ≤+10% latency; ≥30% cost reduction vs frontier LLM; escalation_rate < 5%.
- Automatic demotion if formatting_error_rate >5% rolling 50 calls or safety incident.

## 10. Risk & Mitigation Snapshot
| Risk | Mitigation |
|------|------------|
| Specialist overfitting | Shadow eval on fresh live traffic; add temperature & paraphrase augmentation |
| Data leakage via logs | Early redaction + PII masker + hashed prompt templates |
| Cluster drift | Weekly recluster + Jaccard drift alert > threshold |
| Model sprawl | Registry lifecycle states (candidate, shadow, active, deprecated) |
| Latency variance | Track p95 delta; route large context to larger SLM or escalate |

## 11. Roadmap Integration
Reference `30_Enterprise_TODO.md`:
- Phase 1: Implement instrumentation + registry skeleton + plan frame + basic clustering heuristic.
- Phase 2: Add shadow eval + promotion automation + cost & regret metrics.
- Phase 3: Introduce PEFT fine-tune pipeline & model provenance signing.
- Phase 4+: Multi-region SLM pack distribution & carbon-aware routing.

## 12. Immediate Actionable Tickets
1. Add plan frame + observation emission (router service).
2. Create model registry stub (YAML or JSON) consumed at startup.
3. Implement basic task classifier mapping (prompt prefix / keywords) -> cluster_hint.
4. Introduce hashing + redaction pipeline reuse for observations.
5. Dashboard JSON skeleton (Grafana) for cost & success metrics.

## 13. Success Definition (Initial)
Within 30 days: ≥3 high-volume task clusters routed to SLM specialists with ≥40% aggregate cost savings & no SLA regression (latency / success).

---

## PEFT Fine-Tune Workflow (GAP-347)

### Overview
The PEFT (Parameter-Efficient Fine-Tuning) pipeline enables rapid specialization of base models using LoRA (Low-Rank Adaptation) adapters. This allows creating task-specific specialists with minimal computational overhead and storage requirements.

### Workflow Steps

#### 1. Data Preparation
- **Input Format**: JSONL with `{"input": "...", "output": "..."}` pairs
- **Data Validation**: Check for required fields, minimum sample count (≥100)
- **Preprocessing**: Tokenization, length filtering, quality filtering

#### 2. Configuration Setup
```python
from router_service.peft_fine_tune_pipeline import PEFTFineTunePipeline

pipeline = PEFTFineTunePipeline()
config = pipeline.create_training_config(
    base_model="microsoft/DialoGPT-medium",
    training_data_path="/data/customer_support.jsonl",
    output_dir="/adapters/customer_support_v1",
    lora_rank=16,  # Default rank
    num_epochs=3,
    batch_size=4,
    learning_rate=2e-4
)
```

#### 3. Pre-Training Validation
```python
errors = pipeline.validate_training_config(config)
if errors:
    print("Configuration errors:", errors)
    # Fix configuration issues
```

#### 4. Dry Run (Optional)
```python
dry_result = pipeline.dry_run_training(config)
print(f"Dry run completed in {dry_result['training_time_seconds']:.2f}s")
print(f"Estimated total steps: {dry_result['total_estimated_steps']}")
```

#### 5. Provenance Generation
```python
provenance = pipeline.generate_provenance_record(config, "job_2025_0906_001")
pipeline.save_provenance_record(provenance, config.output_dir)
```

#### 6. Training Execution
```python
# Actual training (implementation depends on framework)
# This would integrate with transformers/peft libraries
trainer = Trainer(
    model=model,
    args=training_args,
    train_dataset=train_dataset,
    eval_dataset=eval_dataset,
    peft_config=peft_config,
)
trainer.train()
```

#### 7. Adapter Saving & Registration
```python
# Save LoRA adapters
trainer.save_model(config.output_dir)

# Register in model registry
new_model_entry = {
    "model": "customer_support_specialist_v1",
    "base_model": config.base_model,
    "adapter_path": config.output_dir,
    "capabilities": ["customer_support", "chat"],
    "safety_grade": "A",
    "status": "shadow",  # Start in shadow mode
    "peft_config": config.lora_config.to_dict(),
    "provenance_hash": provenance["content_hash"]
}
```

### LoRA Configuration

#### Default Settings
- **Rank**: 16 (balances quality vs. parameter efficiency)
- **Alpha**: 32 (scaling factor for LoRA updates)
- **Dropout**: 0.05 (prevents overfitting)
- **Target Modules**: `["q_proj", "k_proj", "v_proj", "o_proj"]`

#### Performance Tuning
- **Higher Rank** (32-64): Better quality, more parameters
- **Lower Rank** (8-16): Faster training, smaller adapters
- **Task-Specific Modules**: Target only relevant attention layers

### Training Parameters

#### Recommended Defaults
- **Epochs**: 3 (sufficient for most fine-tuning tasks)
- **Batch Size**: 4 (balance memory vs. training speed)
- **Learning Rate**: 2e-4 (stable convergence)
- **Warmup Steps**: 100 (gradual learning rate increase)
- **Max Sequence Length**: 512 (balance context vs. memory)

#### Hardware Considerations
- **GPU Memory**: Adjust batch size based on available VRAM
- **Training Time**: ~30 minutes for 10K samples on A100
- **Storage**: LoRA adapters ~1-5MB vs. full fine-tuning ~1-10GB

### Provenance & Reproducibility

#### Content Hashing
```python
config_str = json.dumps(config.to_dict(), sort_keys=True)
content_hash = hashlib.sha256(config_str.encode()).hexdigest()
```

#### Provenance Record
```json
{
  "job_id": "customer_support_finetune_2025_0906",
  "timestamp": 1757204705,
  "config": {...},
  "content_hash": "a1b2c3d4...",
  "pipeline_version": "1.0.0",
  "framework": "peft-lora"
}
```

### Metrics & Monitoring

#### Training Metrics
- `peft_jobs_completed_total`: Counter of completed training jobs
- `peft_jobs_failed_total`: Counter of failed training jobs
- `peft_training_time_seconds`: Histogram of training durations

#### Quality Metrics
- Validation loss tracking
- Perplexity monitoring
- Task-specific accuracy metrics

### Integration Points

#### Model Registry
- Automatic registration of trained adapters
- Lifecycle management (shadow → active → deprecated)
- Capability tagging for routing decisions

#### Router Service
- Dynamic loading of LoRA adapters
- A/B testing between base and fine-tuned models
- Performance monitoring and automatic rollback

### Best Practices

#### Data Quality
- Ensure diverse, high-quality training examples
- Balance positive/negative examples
- Validate data format and encoding

#### Model Selection
- Choose base models appropriate for target domain
- Consider model size vs. available compute
- Evaluate base model performance on target task

#### Deployment Strategy
- Start with shadow evaluation
- Gradual traffic ramp-up
- Monitor for performance regressions
- Maintain rollback capability

### Troubleshooting

#### Common Issues
- **Out of Memory**: Reduce batch size or sequence length
- **Poor Convergence**: Adjust learning rate or increase epochs
- **Overfitting**: Increase dropout or reduce model capacity
- **Slow Training**: Optimize data loading or reduce precision

#### Validation Checks
- Verify adapter file integrity
- Test model loading and inference
- Validate provenance records
- Check metric collection

### Future Enhancements
- **QLoRA Integration**: 4-bit quantization for memory efficiency
- **Multi-Task Training**: Joint training on multiple related tasks
- **Adapter Merging**: Combine multiple fine-tuned adapters
- **Automated Hyperparameter Tuning**: Bayesian optimization
- **Distributed Training**: Multi-GPU/TPU support

---
Generated: 2025-09-06
