import yaml


def render_hpa(
    name: str, namespace: str, min_replicas: int, max_replicas: int, target_p95_ms: int, target_queue_depth: int
) -> str:
    hpa = {
        "apiVersion": "autoscaling/v2",
        "kind": "HorizontalPodAutoscaler",
        "metadata": {"name": f"{name}-hpa", "namespace": namespace},
        "spec": {
            "scaleTargetRef": {"apiVersion": "apps/v1", "kind": "Deployment", "name": name},
            "minReplicas": min_replicas,
            "maxReplicas": max_replicas,
            "metrics": [
                {  # p95 latency SLI via custom metric
                    "type": "Pods",
                    "pods": {
                        "metric": {"name": "router_latency_p95_ms"},
                        "target": {"type": "AverageValue", "averageValue": f"{target_p95_ms}"},
                    },
                },
                {  # queue depth
                    "type": "Pods",
                    "pods": {
                        "metric": {"name": "router_queue_depth"},
                        "target": {"type": "AverageValue", "averageValue": f"{target_queue_depth}"},
                    },
                },
            ],
        },
    }
    return yaml.safe_dump(hpa, sort_keys=False)
