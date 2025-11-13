import yaml


def render_canary(name: str, image_stable: str, image_canary: str, canary_weight: int = 10) -> str:
    # Two Deployments with label track=stable/canary and a Service selecting both
    svc = {
        "apiVersion": "v1",
        "kind": "Service",
        "metadata": {"name": name},
        "spec": {"selector": {"app": name}, "ports": [{"port": 7443, "targetPort": 7443}]},
    }
    dep_stable = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": f"{name}-stable"},
        "spec": {
            "replicas": 9,
            "selector": {"matchLabels": {"app": name, "track": "stable"}},
            "template": {
                "metadata": {"labels": {"app": name, "track": "stable"}},
                "spec": {"containers": [{"name": name, "image": image_stable, "ports": [{"containerPort": 7443}]}]},
            },
        },
    }
    dep_canary = {
        "apiVersion": "apps/v1",
        "kind": "Deployment",
        "metadata": {"name": f"{name}-canary"},
        "spec": {
            "replicas": max(1, canary_weight // 10),
            "selector": {"matchLabels": {"app": name, "track": "canary"}},
            "template": {
                "metadata": {"labels": {"app": name, "track": "canary"}},
                "spec": {"containers": [{"name": name, "image": image_canary, "ports": [{"containerPort": 7443}]}]},
            },
        },
    }
    docs = [svc, dep_stable, dep_canary]
    return "---\n".join(yaml.safe_dump(d, sort_keys=False) for d in docs)
