"""AsyncAPI/OpenAPI Aggregation POC
Loads existing spec artifacts and validates presence of key fields.
"""

import os

import yaml


def load_yaml(path: str):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def validate():
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    openapi = load_yaml(os.path.join(root, "tools", "openapi_poc.yaml"))
    asyncapi = load_yaml(os.path.join(root, "tools", "asyncapi_poc.yaml"))
    assert "openapi" in openapi or "swagger" in openapi
    assert "paths" in openapi
    assert "channels" in asyncapi
    assert "asyncapi" in asyncapi
    return True


if __name__ == "__main__":
    assert validate()
    print("OK: API specs aggregation POC passed")
