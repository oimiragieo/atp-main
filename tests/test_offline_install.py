"""Tests for GAP-335C: On-prem operator packaging - Offline install simulation."""

import os
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import yaml

from tools.sync_images import ImageRegistrySync, ImageSyncConfig, load_config_from_file


class TestOfflineInstallSimulation:
    """Test offline installation simulation for air-gapped deployments."""

    def setup_method(self):
        """Set up test environment."""
        self.temp_dir = tempfile.mkdtemp()
        self.config = ImageSyncConfig(
            source_registry="docker.io",
            target_registry="registry.internal.company.com",
            images=["atp/router:latest", "postgres:15-alpine"],
            dry_run=True,
            concurrency=2,
            timeout=30
        )

    def teardown_method(self):
        """Clean up test environment."""
        # Clean up temp directory
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_image_sync_config_creation(self):
        """Test creation of image sync configuration."""
        assert self.config.source_registry == "docker.io"
        assert self.config.target_registry == "registry.internal.company.com"
        assert len(self.config.images) == 2
        assert self.config.dry_run is True
        assert self.config.concurrency == 2
        assert self.config.timeout == 30

    def test_load_config_from_file(self):
        """Test loading configuration from YAML file."""
        config_path = os.path.join(self.temp_dir, "test-config.yaml")
        config_data = {
            "source_registry": "docker.io",
            "target_registry": "registry.internal.company.com",
            "images": ["test/image:1.0", "test/image:2.0"],
            "dry_run": False,
            "concurrency": 5,
            "timeout": 600
        }

        with open(config_path, "w") as f:
            yaml.dump(config_data, f)

        loaded_config = load_config_from_file(config_path)

        assert loaded_config.source_registry == "docker.io"
        assert loaded_config.target_registry == "registry.internal.company.com"
        assert loaded_config.images == ["test/image:1.0", "test/image:2.0"]
        assert loaded_config.dry_run is False
        assert loaded_config.concurrency == 5
        assert loaded_config.timeout == 600

    @patch("subprocess.run")
    def test_validate_prerequisites_success(self, mock_subprocess):
        """Test successful prerequisite validation."""
        mock_subprocess.return_value.returncode = 0
        mock_subprocess.return_value.stdout = "Docker version 24.0.0"

        sync = ImageRegistrySync(self.config)
        result = sync.validate_prerequisites()

        assert result is True
        mock_subprocess.assert_called_once()

    @patch("subprocess.run")
    def test_validate_prerequisites_failure(self, mock_subprocess):
        """Test failed prerequisite validation."""
        mock_subprocess.return_value.returncode = 1

        sync = ImageRegistrySync(self.config)
        result = sync.validate_prerequisites()

        assert result is False

    @patch("subprocess.run")
    def test_validate_prerequisites_docker_not_found(self, mock_subprocess):
        """Test prerequisite validation when docker is not found."""
        mock_subprocess.side_effect = FileNotFoundError

        sync = ImageRegistrySync(self.config)
        result = sync.validate_prerequisites()

        assert result is False

    @patch("asyncio.create_subprocess_exec")
    async def test_sync_image_dry_run(self, mock_subprocess):
        """Test image sync in dry run mode."""
        # Mock the subprocess calls
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_subprocess.return_value = mock_process

        sync = ImageRegistrySync(self.config)
        result = await sync.sync_image("test/image:latest")

        assert result is True
        # In dry run mode, no actual subprocess calls should be made
        assert mock_subprocess.call_count == 0

    @patch("asyncio.create_subprocess_exec")
    async def test_sync_image_success(self, mock_subprocess):
        """Test successful image sync."""
        # Create non-dry-run config
        config = ImageSyncConfig(
            source_registry="docker.io",
            target_registry="registry.internal.company.com",
            images=["test/image:latest"],
            dry_run=False
        )

        # Mock successful subprocess calls
        mock_process = MagicMock()
        mock_process.returncode = 0
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_subprocess.return_value = mock_process

        sync = ImageRegistrySync(config)
        result = await sync.sync_image("test/image:latest")

        assert result is True
        # Should make 3 calls: pull, tag, push
        assert mock_subprocess.call_count == 3

    @patch("asyncio.create_subprocess_exec")
    async def test_sync_image_pull_failure(self, mock_subprocess):
        """Test image sync failure during pull."""
        config = ImageSyncConfig(
            source_registry="docker.io",
            target_registry="registry.internal.company.com",
            images=["test/image:latest"],
            dry_run=False
        )

        # Mock failed pull
        mock_process = MagicMock()
        mock_process.returncode = 1
        mock_process.stdout = MagicMock()
        mock_process.stderr = MagicMock()
        mock_subprocess.return_value = mock_process

        sync = ImageRegistrySync(config)
        result = await sync.sync_image("test/image:latest")

        assert result is False

    async def test_sync_all_images_concurrency(self):
        """Test syncing multiple images with concurrency control."""
        config = ImageSyncConfig(
            source_registry="docker.io",
            target_registry="registry.internal.company.com",
            images=["image1:latest", "image2:latest", "image3:latest"],
            dry_run=True,
            concurrency=2
        )

        sync = ImageRegistrySync(config)

        # Mock the sync_image method
        sync_results = []

        async def mock_sync_image(image):
            # Simulate some processing time
            import asyncio
            await asyncio.sleep(0.01)
            sync_results.append(image)
            return True

        sync.sync_image = mock_sync_image

        results = await sync.sync_all_images()

        assert len(results) == 3
        assert all(results.values())  # All should be successful
        assert len(sync_results) == 3

    def test_kustomize_base_structure(self):
        """Test that kustomize base structure exists and is valid."""
        base_dir = Path("deploy/kustomize/base")
        assert base_dir.exists()

        kustomization_file = base_dir / "kustomization.yaml"
        assert kustomization_file.exists()

        # Load and validate kustomization
        with open(kustomization_file) as f:
            kustomization = yaml.safe_load(f)

        assert "apiVersion" in kustomization
        assert "kind" in kustomization
        assert "resources" in kustomization
        assert len(kustomization["resources"]) > 0

    def test_air_gapped_overlay_structure(self):
        """Test that air-gapped overlay structure exists."""
        overlay_dir = Path("deploy/kustomize/overlays/air-gapped")
        assert overlay_dir.exists()

        kustomization_file = overlay_dir / "kustomization.yaml"
        assert kustomization_file.exists()

        # Load and validate overlay kustomization
        with open(kustomization_file) as f:
            kustomization = yaml.safe_load(f)

        assert "apiVersion" in kustomization
        assert "bases" in kustomization
        assert len(kustomization["bases"]) > 0

    def test_helm_chart_structure(self):
        """Test that helm chart has required structure."""
        chart_dir = Path("deploy/helm/atp")
        assert chart_dir.exists()

        required_files = ["Chart.yaml", "values.yaml", "templates"]
        for file in required_files:
            assert (chart_dir / file).exists()

        # Check that templates directory has content
        templates_dir = chart_dir / "templates"
        assert templates_dir.is_dir()
        assert len(list(templates_dir.glob("*.yaml"))) > 0

    def test_dockerfile_structure(self):
        """Test that docker setup is complete."""
        dockerfile = Path("deploy/docker/Dockerfile.router")
        assert dockerfile.exists()

        with open(dockerfile) as f:
            content = f.read()

        # Should be a multi-stage build
        assert "FROM rust:" in content
        assert "FROM gcr.io/distroless" in content
        assert "COPY --from=builder" in content

    def test_sync_config_structure(self):
        """Test that sync config is valid YAML."""
        config_file = Path("deploy/kustomize/sync-config.yaml")
        assert config_file.exists()

        with open(config_file) as f:
            config = yaml.safe_load(f)

        assert "source_registry" in config
        assert "target_registry" in config
        assert "images" in config
        assert isinstance(config["images"], list)
        assert len(config["images"]) > 0


class TestImageSyncConfig:
    """Test ImageSyncConfig dataclass."""

    def test_config_creation(self):
        """Test creating image sync config."""
        config = ImageSyncConfig(
            source_registry="docker.io",
            target_registry="internal.registry.com",
            images=["app:v1", "db:v2"],
            dry_run=True,
            concurrency=5,
            timeout=600
        )

        assert config.source_registry == "docker.io"
        assert config.target_registry == "internal.registry.com"
        assert config.images == ["app:v1", "db:v2"]
        assert config.dry_run is True
        assert config.concurrency == 5
        assert config.timeout == 600
