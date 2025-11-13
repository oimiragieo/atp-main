#!/usr/bin/env python3
"""
AGP Route Snapshot Tool (agpsnapshot)

Takes snapshots of AGP route tables for backup and rollback purposes.
Supports diffing snapshots and restoring from backups.
"""

import argparse
import sys
from pathlib import Path
from typing import Any

import yaml


class AGPRouteSnapshot:
    """AGP route table snapshot manager."""

    def __init__(self, route_table_path: str):
        self.route_table_path = Path(route_table_path)
        self.snapshots_dir = self.route_table_path.parent / "snapshots"
        self.snapshots_dir.mkdir(exist_ok=True)

    def take_snapshot(self, name: str) -> str:
        """Take a snapshot of the current route table."""
        # For now, just copy the route table file as a snapshot
        # In production, this would connect to the actual route table
        snapshot_path = self.snapshots_dir / f"{name}.yaml"

        if self.route_table_path.exists():
            import shutil

            shutil.copy2(self.route_table_path, snapshot_path)
            return str(snapshot_path)
        else:
            raise FileNotFoundError(f"Route table not found: {self.route_table_path}")

    def list_snapshots(self) -> list[dict[str, Any]]:
        """List all available snapshots."""
        snapshots = []
        for snapshot_file in self.snapshots_dir.glob("*.yaml"):
            snapshots.append(
                {
                    "name": snapshot_file.stem,
                    "path": str(snapshot_file),
                    "size": snapshot_file.stat().st_size,
                    "modified": snapshot_file.stat().st_mtime,
                }
            )
        return sorted(snapshots, key=lambda x: x["modified"], reverse=True)

    def diff_snapshots(self, snapshot1: str, snapshot2: str) -> dict[str, Any]:
        """Diff two snapshots."""
        path1 = self.snapshots_dir / f"{snapshot1}.yaml"
        path2 = self.snapshots_dir / f"{snapshot2}.yaml"

        if not path1.exists():
            raise FileNotFoundError(f"Snapshot not found: {snapshot1}")
        if not path2.exists():
            raise FileNotFoundError(f"Snapshot not found: {snapshot2}")

        with open(path1, encoding="utf-8") as f:
            data1 = yaml.safe_load(f)
        with open(path2, encoding="utf-8") as f:
            data2 = yaml.safe_load(f)

        # Simple diff for route table YAML
        diff = {"added_routers": [], "removed_routers": [], "modified_routers": []}

        routers1 = set(data1.keys())
        routers2 = set(data2.keys())

        diff["added_routers"] = list(routers2 - routers1)
        diff["removed_routers"] = list(routers1 - routers2)

        for router in routers1 & routers2:
            if data1[router] != data2[router]:
                diff["modified_routers"].append(router)

        return diff

    def restore_snapshot(self, name: str, target_path: str | None = None) -> str:
        """Restore a snapshot to the route table."""
        snapshot_path = self.snapshots_dir / f"{name}.yaml"
        if not snapshot_path.exists():
            raise FileNotFoundError(f"Snapshot not found: {name}")

        target = Path(target_path) if target_path else self.route_table_path
        import shutil

        shutil.copy2(snapshot_path, target)
        return str(target)


def main():
    parser = argparse.ArgumentParser(description="AGP Route Snapshot Tool")
    parser.add_argument("route_table", help="Path to route table YAML file")

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # Take snapshot
    take_parser = subparsers.add_parser("take", help="Take a snapshot")
    take_parser.add_argument("name", help="Snapshot name")

    # List snapshots
    subparsers.add_parser("list", help="List snapshots")

    # Diff snapshots
    diff_parser = subparsers.add_parser("diff", help="Diff two snapshots")
    diff_parser.add_argument("snapshot1", help="First snapshot name")
    diff_parser.add_argument("snapshot2", help="Second snapshot name")

    # Restore snapshot
    restore_parser = subparsers.add_parser("restore", help="Restore a snapshot")
    restore_parser.add_argument("name", help="Snapshot name")
    restore_parser.add_argument("--target", help="Target path for restoration")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        snapshot_mgr = AGPRouteSnapshot(args.route_table)

        if args.command == "take":
            path = snapshot_mgr.take_snapshot(args.name)
            print(f"✅ Snapshot taken: {path}")

        elif args.command == "list":
            snapshots = snapshot_mgr.list_snapshots()
            if snapshots:
                print("📋 Available snapshots:")
                for snap in snapshots:
                    print(f"  {snap['name']} ({snap['path']})")
            else:
                print("📋 No snapshots found")

        elif args.command == "diff":
            diff = snapshot_mgr.diff_snapshots(args.snapshot1, args.snapshot2)
            print(f"🔍 Diff between {args.snapshot1} and {args.snapshot2}:")
            print(f"  Added routers: {diff['added_routers']}")
            print(f"  Removed routers: {diff['removed_routers']}")
            print(f"  Modified routers: {diff['modified_routers']}")

        elif args.command == "restore":
            path = snapshot_mgr.restore_snapshot(args.name, args.target)
            print(f"✅ Snapshot restored to: {path}")

    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
