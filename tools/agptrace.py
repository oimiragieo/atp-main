#!/usr/bin/env python3
"""
AGP Trace Utility (agptrace)

Traceroute-like utility for AGP federation that shows the next-hop chain
with RLH TTL decrements for a given prefix.
"""

import argparse
import sys
from typing import Any

import yaml


class AGPTracer:
    """AGP route tracer that simulates packet forwarding through the network."""

    def __init__(self, route_table_path: str):
        self.route_table = self._load_route_table(route_table_path)

    def _load_route_table(self, path: str) -> dict[str, Any]:
        """Load route table from YAML file."""
        with open(path, encoding="utf-8") as f:
            return yaml.safe_load(f)

    def trace_route(self, prefix: str, start_router: str, max_hops: int = 30, initial_ttl: int = 64) -> dict[str, Any]:
        """Trace the route for a prefix through the AGP network."""
        hops = []
        current_router = start_router
        ttl = initial_ttl
        visited = set()

        for hop_num in range(1, max_hops + 1):
            if current_router in visited:
                hops.append(
                    {
                        "hop": hop_num,
                        "router": current_router,
                        "ttl": ttl,
                        "status": "LOOP_DETECTED",
                        "reason": f"Loop detected at {current_router}",
                    }
                )
                break

            visited.add(current_router)

            # Look up route for prefix at current router
            route_info = self._lookup_route(current_router, prefix)

            if not route_info:
                hops.append(
                    {
                        "hop": hop_num,
                        "router": current_router,
                        "ttl": ttl,
                        "status": "NO_ROUTE",
                        "reason": f"No route to {prefix} at {current_router}",
                    }
                )
                break

            # Decrement TTL (simulate RLH processing)
            ttl -= 1

            hops.append(
                {
                    "hop": hop_num,
                    "router": current_router,
                    "ttl": ttl,
                    "status": "FORWARD",
                    "next_hop": route_info["next_hop"],
                    "path": route_info.get("path", []),
                    "local_pref": route_info.get("local_pref"),
                    "reason": f"Forwarding to {route_info['next_hop']}",
                }
            )

            # Check TTL expiry
            if ttl <= 0:
                hops.append(
                    {
                        "hop": hop_num + 1,
                        "router": route_info["next_hop"],
                        "ttl": 0,
                        "status": "TTL_EXPIRED",
                        "reason": "TTL expired",
                    }
                )
                break

            current_router = route_info["next_hop"]

            # Check if we've reached the destination
            if self._is_destination(current_router, prefix):
                hops.append(
                    {
                        "hop": hop_num + 1,
                        "router": current_router,
                        "ttl": ttl - 1,
                        "status": "DESTINATION_REACHED",
                        "reason": f"Reached destination for {prefix}",
                    }
                )
                break

        return {
            "prefix": prefix,
            "initial_ttl": initial_ttl,
            "hops": hops,
            "total_hops": len(hops),
            "trace_complete": len(hops) < max_hops,
        }

    def _lookup_route(self, router: str, prefix: str) -> dict[str, Any] | None:
        """Look up route for prefix at given router."""
        router_routes = self.route_table.get(router, {})
        return router_routes.get(prefix)

    def _is_destination(self, router: str, prefix: str) -> bool:
        """Check if router is the destination for the prefix."""
        # Simple check: if router has a direct route to prefix
        route = self._lookup_route(router, prefix)
        return route is not None and route.get("next_hop") == router


def main():
    parser = argparse.ArgumentParser(description="AGP Trace Utility")
    parser.add_argument("route_table", help="Path to route table YAML file")
    parser.add_argument("prefix", help="Prefix to trace")
    parser.add_argument("--start-router", default="router1", help="Starting router ID")
    parser.add_argument("--max-hops", type=int, default=30, help="Maximum number of hops")
    parser.add_argument("--ttl", type=int, default=64, help="Initial TTL value")

    args = parser.parse_args()

    try:
        tracer = AGPTracer(args.route_table)
        result = tracer.trace_route(args.prefix, args.start_router, args.max_hops, args.ttl)

        print(f"🔍 AGP Trace for {result['prefix']}")
        print(f"📊 Initial TTL: {result['initial_ttl']}")
        print()

        for hop in result["hops"]:
            status_emoji = {
                "FORWARD": "➡️",
                "NO_ROUTE": "❌",
                "TTL_EXPIRED": "⏰",
                "LOOP_DETECTED": "🔄",
                "DESTINATION_REACHED": "🎯",
            }.get(hop["status"], "❓")

            print(f"{status_emoji} Hop {hop['hop']}: {hop['router']} (TTL: {hop['ttl']})")
            if "next_hop" in hop:
                print(f"   Next hop: {hop['next_hop']}")
            if "path" in hop and hop["path"]:
                print(f"   Path: {' -> '.join(map(str, hop['path']))}")
            if "local_pref" in hop and hop["local_pref"] is not None:
                print(f"   Local pref: {hop['local_pref']}")
            print(f"   {hop['reason']}")
            print()

        if result["trace_complete"]:
            print("✅ Trace completed successfully")
        else:
            print("⚠️  Trace may be incomplete (max hops reached)")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
