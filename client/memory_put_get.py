"""ATP Memory Gateway Client Example.

Demonstrates basic memory gateway operations including PUT, GET, and SEARCH.
Shows how to interact with the ATP memory fabric for storing and retrieving data.
"""

import os

import requests

ns, key = "tenant/acme", "session/s1"
obj = {"type": "task.plan.v1", "steps": ["analyze", "generate", "test"]}
timeout = float(os.getenv("ATP_CLIENT_TIMEOUT", "5"))
r = requests.put(f"http://localhost:8080/v1/memory/{ns}/{key}", json={"object": obj}, timeout=timeout)
print("PUT:", r.status_code, r.json())
g = requests.get(f"http://localhost:8080/v1/memory/{ns}/{key}", timeout=timeout)
print("GET:", g.status_code, g.json())
s = requests.post("http://localhost:8080/v1/memory/search", json={"q": "generate"}, timeout=timeout)
print("SEARCH:", s.status_code, s.json())
