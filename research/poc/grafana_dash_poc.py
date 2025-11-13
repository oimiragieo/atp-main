import json


def render_dashboard(title: str = "ATP Router Overview") -> str:
    dash = {
        "title": title,
        "panels": [
            {"title": "Windows Usage", "type": "graph", "targets": [{"expr": "router_window_tokens_used"}]},
            {"title": "Consensus Confidence", "type": "graph", "targets": [{"expr": "router_consensus_confidence"}]},
            {"title": "Adapter Predictability", "type": "graph", "targets": [{"expr": "adapter_predictability_score"}]},
        ],
    }
    return json.dumps(dash)
