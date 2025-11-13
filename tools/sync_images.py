#!/usr/bin/env python3
"""
Image Registry Sync Script for Air-Gapped Deployments

This script synchronizes container images from external registries to an internal
registry for air-gapped ATP deployments.

Usage:
    python sync_images.py --source-registry docker.io --target-registry registry.internal.company.com --dry-run
    python sync_images.py --config sync-config.yaml
"""

import argparse
import asyncio
import logging
import subprocess
import sys
from dataclasses import dataclass

import yaml


@dataclass
class ImageSyncConfig:
    """Configuration for image synchronization."""

    source_registry: str
    target_registry: str
    images: list[str]
    dry_run: bool = False
    concurrency: int = 3
    timeout: int = 300


class ImageRegistrySync:
    """Handles synchronization of container images to internal registry."""

    def __init__(self, config: ImageSyncConfig):
        self.config = config
        self.logger = logging.getLogger(__name__)

        # Setup logging
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    async def sync_image(self, image: str) -> bool:
        """Sync a single image from source to target registry."""
        try:
            # Pull from source
            pull_cmd = ["docker", "pull", f"{self.config.source_registry}/{image}"]
            if not self.config.dry_run:
                self.logger.info(f"Pulling {image} from {self.config.source_registry}")
                result = await self._run_command(pull_cmd)
                if result.returncode != 0:
                    self.logger.error(f"Failed to pull {image}: {result.stderr}")
                    return False
            else:
                self.logger.info(f"[DRY RUN] Would pull {image} from {self.config.source_registry}")

            # Tag for target registry
            source_tag = f"{self.config.source_registry}/{image}"
            target_tag = f"{self.config.target_registry}/{image}"

            tag_cmd = ["docker", "tag", source_tag, target_tag]
            if not self.config.dry_run:
                self.logger.info(f"Tagging {image} for {self.config.target_registry}")
                result = await self._run_command(tag_cmd)
                if result.returncode != 0:
                    self.logger.error(f"Failed to tag {image}: {result.stderr}")
                    return False
            else:
                self.logger.info(f"[DRY RUN] Would tag {image} as {target_tag}")

            # Push to target registry
            push_cmd = ["docker", "push", target_tag]
            if not self.config.dry_run:
                self.logger.info(f"Pushing {image} to {self.config.target_registry}")
                result = await self._run_command(push_cmd)
                if result.returncode != 0:
                    self.logger.error(f"Failed to push {image}: {result.stderr}")
                    return False
            else:
                self.logger.info(f"[DRY RUN] Would push {image} to {self.config.target_registry}")

            self.logger.info(f"Successfully synced {image}")
            return True

        except Exception as e:
            self.logger.error(f"Error syncing {image}: {e}")
            return False

    async def _run_command(self, cmd: list[str]) -> subprocess.CompletedProcess:
        """Run a command asynchronously."""
        return await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, timeout=self.config.timeout
        )

    async def sync_all_images(self) -> dict[str, bool]:
        """Sync all configured images."""
        self.logger.info(f"Starting image sync with concurrency={self.config.concurrency}")

        # Create semaphore for concurrency control
        semaphore = asyncio.Semaphore(self.config.concurrency)

        async def sync_with_semaphore(image: str) -> tuple[str, bool]:
            async with semaphore:
                success = await self.sync_image(image)
                return image, success

        # Run all syncs concurrently
        tasks = [sync_with_semaphore(image) for image in self.config.images]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Process results
        sync_results = {}
        successful = 0
        failed = 0

        for result in results:
            if isinstance(result, Exception):
                self.logger.error(f"Task failed with exception: {result}")
                failed += 1
                continue

            image, success = result
            sync_results[image] = success
            if success:
                successful += 1
            else:
                failed += 1

        self.logger.info(f"Sync completed: {successful} successful, {failed} failed")
        return sync_results

    def validate_prerequisites(self) -> bool:
        """Validate that required tools are available."""
        try:
            result = subprocess.run(["docker", "--version"], capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                self.logger.error("Docker is not available or not running")
                return False

            self.logger.info(f"Docker version: {result.stdout.strip()}")
            return True

        except (subprocess.TimeoutExpired, FileNotFoundError) as e:
            self.logger.error(f"Docker validation failed: {e}")
            return False


def load_config_from_file(config_path: str) -> ImageSyncConfig:
    """Load configuration from YAML file."""
    with open(config_path) as f:
        data = yaml.safe_load(f)

    return ImageSyncConfig(
        source_registry=data.get("source_registry", "docker.io"),
        target_registry=data["target_registry"],
        images=data["images"],
        dry_run=data.get("dry_run", False),
        concurrency=data.get("concurrency", 3),
        timeout=data.get("timeout", 300),
    )


def create_default_config() -> ImageSyncConfig:
    """Create default configuration for ATP images."""
    return ImageSyncConfig(
        source_registry="docker.io",
        target_registry="registry.internal.company.com",
        images=[
            "atp/router:latest",
            "postgres:15-alpine",
            "redis:7-alpine",
            "prom/prometheus:latest",
            "grafana/grafana:latest",
            "nginx:1.25-alpine",
        ],
        dry_run=True,
        concurrency=3,
        timeout=300,
    )


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="ATP Image Registry Sync Tool")
    parser.add_argument("--source-registry", default="docker.io", help="Source registry to pull images from")
    parser.add_argument("--target-registry", required=True, help="Target registry to push images to")
    parser.add_argument("--images", nargs="+", help="List of images to sync")
    parser.add_argument("--config", help="Path to YAML configuration file")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without actually syncing")
    parser.add_argument("--concurrency", type=int, default=3, help="Number of concurrent sync operations")
    parser.add_argument("--timeout", type=int, default=300, help="Timeout for individual operations in seconds")

    args = parser.parse_args()

    # Load configuration
    if args.config:
        config = load_config_from_file(args.config)
    else:
        config = create_default_config()

    # Override with command line args
    if args.source_registry:
        config.source_registry = args.source_registry
    if args.target_registry:
        config.target_registry = args.target_registry
    if args.images:
        config.images = args.images
    if args.dry_run:
        config.dry_run = args.dry_run
    if args.concurrency:
        config.concurrency = args.concurrency
    if args.timeout:
        config.timeout = args.timeout

    # Create sync handler
    sync = ImageRegistrySync(config)

    # Validate prerequisites
    if not sync.validate_prerequisites():
        sys.exit(1)

    # Perform sync
    results = await sync.sync_all_images()

    # Report results
    successful = sum(1 for success in results.values() if success)
    failed = len(results) - successful

    print("\nSync Summary:")
    print(f"  Total images: {len(results)}")
    print(f"  Successful: {successful}")
    print(f"  Failed: {failed}")

    if failed > 0:
        print("\nFailed images:")
        for image, success in results.items():
            if not success:
                print(f"  - {image}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
