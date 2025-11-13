# 15 — Deployment Guide (Docker & Kubernetes)

- Local: `docker compose up -d` (router, adapters, OPA, memory, Prom, Tempo, Grafana, OTel).
- K8s: Distroless images, Pod anti-affinity, PDBs, HPA, ServiceMonitor.
- Secrets: external secret stores; no plaintext keys in env.
- Upgrades: rolling with maxUnavailable=0 for low-latency tiers.

## Pod Anti-Affinity & Topology Spread Constraints

The ATP Router deployment includes sophisticated pod distribution controls to ensure high availability and optimal resource utilization across the cluster.

### Anti-Affinity Rules

Pods are configured with preferred anti-affinity rules to distribute across:

- **Zones**: `topology.kubernetes.io/zone` - Ensures pods are spread across availability zones
- **Nodes**: `kubernetes.io/hostname` - Ensures pods are spread across different physical/virtual nodes

```yaml
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
    - weight: 100
      podAffinityTerm:
        labelSelector:
          matchExpressions:
          - key: app
            operator: In
            values:
            - atp-router
        topologyKey: topology.kubernetes.io/zone
    - weight: 50
      podAffinityTerm:
        labelSelector:
          matchExpressions:
          - key: app
            operator: In
            values:
            - atp-router
        topologyKey: kubernetes.io/hostname
```

### Topology Spread Constraints

Topology spread constraints ensure even distribution with hard limits:

```yaml
topologySpreadConstraints:
- maxSkew: 1
  topologyKey: topology.kubernetes.io/zone
  whenUnsatisfiable: DoNotSchedule
  labelSelector:
    matchLabels:
      app: atp-router
- maxSkew: 1
  topologyKey: kubernetes.io/hostname
  whenUnsatisfiable: ScheduleAnyway
  labelSelector:
    matchLabels:
      app: atp-router
```

### Pod Distribution Testing

Use the pod distribution testing tool to verify proper spread:

```bash
# Test current pod distribution
python tools/pod_distribution_tester.py

# Test in specific namespace
python tools/pod_distribution_tester.py --namespace production --deployment atp-router

# Run tests only (no detailed report)
python tools/pod_distribution_tester.py --test-only
```

The tool validates:
- Multiple zones are used
- Multiple nodes are used
- Reasonable spread scores (< 2.0)
- No single points of failure

### Monitoring Pod Distribution

Pod distribution metrics are exposed via the `/metrics` endpoint:

- `pods_total`: Total number of router pods
- `nodes_used`: Number of nodes with router pods
- `zones_used`: Number of zones with router pods
- `zone_spread_score`: Zone distribution quality (lower is better)
- `node_spread_score`: Node distribution quality (lower is better)

### Pod Disruption Budget

The deployment includes a Pod Disruption Budget (PDB) to prevent excessive pod evictions:

```yaml
apiVersion: policy/v1
kind: PodDisruptionBudget
metadata:
  name: atp-router-pdb
spec:
  minAvailable: 2
  selector:
    matchLabels:
      app: atp-router
```

This ensures at least 2 pods remain available during cluster maintenance operations.

### Troubleshooting Pod Distribution

**Pods not spreading across zones:**
1. Verify node labels: `kubectl get nodes --show-labels`
2. Check cluster topology: `kubectl get nodes -o jsonpath='{.items[*].metadata.labels.topology\.kubernetes\.io/zone}'`
3. Ensure sufficient nodes in different zones

**Pods concentrated on few nodes:**
1. Check node capacity: `kubectl describe nodes`
2. Verify resource requests/limits in deployment
3. Check for node taints/tolerations

**Topology spread constraint violations:**
1. Check events: `kubectl get events --sort-by=.metadata.creationTimestamp`
2. Verify constraint configuration
3. Ensure sufficient cluster capacity
