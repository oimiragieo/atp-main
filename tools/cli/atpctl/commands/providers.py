# Copyright 2025 ATP Project Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Provider management commands for atpctl
"""

import json
from pathlib import Path

import typer
import yaml
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..utils.api_client import ATPAPIClient
from ..utils.formatters import format_output
from ..utils.validators import validate_provider_config

app = typer.Typer()
console = Console()


@app.command("list")
def list_providers(
    ctx: typer.Context,
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by status"),
    provider_type: str | None = typer.Option(None, "--type", "-t", help="Filter by provider type"),
):
    """List configured providers"""
    try:
        client = ATPAPIClient.from_context(ctx)

        params = {}
        if status:
            params["status"] = status
        if provider_type:
            params["type"] = provider_type

        response = client.get("/api/v1/providers", params=params)
        providers = response.get("providers", [])

        if ctx.obj["output_format"] == "json":
            rprint(json.dumps(providers, indent=2))
        elif ctx.obj["output_format"] == "yaml":
            rprint(yaml.dump(providers, default_flow_style=False))
        else:
            # Table format
            table = Table(title="ATP Providers")
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="blue")
            table.add_column("Status", style="green")
            table.add_column("Models", justify="right")
            table.add_column("Requests/min", justify="right")
            table.add_column("Health", style="yellow")
            table.add_column("Priority", justify="right")

            for provider in providers:
                status_style = "green" if provider.get("status") == "active" else "red"
                health_style = "green" if provider.get("health_score", 0) > 0.8 else "yellow"

                table.add_row(
                    provider.get("name", "N/A"),
                    provider.get("type", "unknown"),
                    f"[{status_style}]{provider.get('status', 'unknown')}[/{status_style}]",
                    str(len(provider.get("models", []))),
                    f"{provider.get('requests_per_minute', 0):,}",
                    f"[{health_style}]{provider.get('health_score', 0):.2f}[/{health_style}]",
                    str(provider.get("priority", 100)),
                )

            console.print(table)

    except Exception as e:
        rprint(f"[red]Error listing providers: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("describe")
def describe_provider(
    ctx: typer.Context, provider_name: str = typer.Argument(..., help="Name of the provider to describe")
):
    """Describe a specific provider"""
    try:
        client = ATPAPIClient.from_context(ctx)
        response = client.get(f"/api/v1/providers/{provider_name}")

        if ctx.obj["output_format"] in ["json", "yaml"]:
            format_output(response, ctx.obj["output_format"])
        else:
            provider = response

            # Basic info
            info_text = f"""
[bold]Name:[/bold] {provider.get("name", "N/A")}
[bold]Type:[/bold] {provider.get("type", "unknown")}
[bold]Status:[/bold] {provider.get("status", "unknown")}
[bold]Endpoint:[/bold] {provider.get("endpoint", "N/A")}
[bold]Priority:[/bold] {provider.get("priority", 100)}
[bold]Created:[/bold] {provider.get("created_at", "N/A")}
[bold]Updated:[/bold] {provider.get("updated_at", "N/A")}
            """
            console.print(Panel(info_text, title="Provider Information", border_style="blue"))

            # Health and metrics
            health_text = f"""
[bold]Health Score:[/bold] {provider.get("health_score", 0):.2f}
[bold]Response Time:[/bold] {provider.get("avg_response_time", 0):.2f}ms
[bold]Success Rate:[/bold] {provider.get("success_rate", 0):.2f}%
[bold]Requests/min:[/bold] {provider.get("requests_per_minute", 0):,}
[bold]Rate Limit:[/bold] {provider.get("rate_limit", "N/A")}
[bold]Last Check:[/bold] {provider.get("last_health_check", "N/A")}
            """
            console.print(Panel(health_text, title="Health & Metrics", border_style="green"))

            # Models
            models = provider.get("models", [])
            if models:
                models_table = Table(title="Available Models")
                models_table.add_column("Model", style="cyan")
                models_table.add_column("Type", style="blue")
                models_table.add_column("Context", justify="right")
                models_table.add_column("Cost/1K", justify="right")

                for model in models:
                    models_table.add_row(
                        model.get("name", "N/A"),
                        model.get("type", "text"),
                        f"{model.get('context_length', 0):,}",
                        f"${model.get('cost_per_1k_tokens', 0):.4f}",
                    )

                console.print(models_table)

            # Configuration
            config = provider.get("config", {})
            if config:
                config_text = json.dumps(config, indent=2)
                console.print(Panel(config_text, title="Configuration", border_style="yellow"))

    except Exception as e:
        rprint(f"[red]Error describing provider: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("add")
def add_provider(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Provider name"),
    provider_type: str = typer.Argument(..., help="Provider type (openai, anthropic, google, etc.)"),
    config_file: str | None = typer.Option(None, "--config", "-c", help="Configuration file path"),
    endpoint: str | None = typer.Option(None, "--endpoint", help="Provider endpoint URL"),
    api_key: str | None = typer.Option(None, "--api-key", help="API key"),
    priority: int = typer.Option(100, "--priority", help="Provider priority (lower = higher priority)"),
    enabled: bool = typer.Option(True, "--enabled/--disabled", help="Enable provider"),
):
    """Add a new provider"""
    try:
        client = ATPAPIClient.from_context(ctx)

        # Load configuration from file if provided
        config = {}
        if config_file:
            config_path = Path(config_file)
            if not config_path.exists():
                rprint(f"[red]Configuration file not found: {config_file}[/red]")
                raise typer.Exit(1)

            with open(config_path) as f:
                if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                    config = yaml.safe_load(f)
                else:
                    config = json.load(f)

        # Override with command line options
        if endpoint:
            config["endpoint"] = endpoint
        if api_key:
            config["api_key"] = api_key

        provider_data = {
            "name": name,
            "type": provider_type,
            "config": config,
            "priority": priority,
            "enabled": enabled,
        }

        # Validate configuration
        validation_errors = validate_provider_config(provider_data)
        if validation_errors:
            rprint("[red]Configuration validation failed:[/red]")
            for error in validation_errors:
                rprint(f"  - {error}")
            raise typer.Exit(1)

        response = client.post("/api/v1/providers", json=provider_data)

        rprint(f"[green]Provider '{name}' added successfully[/green]")
        rprint(f"[blue]Provider ID: {response.get('id')}[/blue]")

    except Exception as e:
        rprint(f"[red]Error adding provider: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("update")
def update_provider(
    ctx: typer.Context,
    provider_name: str = typer.Argument(..., help="Provider name"),
    config_file: str | None = typer.Option(None, "--config", "-c", help="Configuration file path"),
    endpoint: str | None = typer.Option(None, "--endpoint", help="Provider endpoint URL"),
    api_key: str | None = typer.Option(None, "--api-key", help="API key"),
    priority: int | None = typer.Option(None, "--priority", help="Provider priority"),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled", help="Enable/disable provider"),
):
    """Update an existing provider"""
    try:
        client = ATPAPIClient.from_context(ctx)

        # Get current provider configuration
        current_provider = client.get(f"/api/v1/providers/{provider_name}")

        # Load new configuration from file if provided
        if config_file:
            config_path = Path(config_file)
            if not config_path.exists():
                rprint(f"[red]Configuration file not found: {config_file}[/red]")
                raise typer.Exit(1)

            with open(config_path) as f:
                if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                    new_config = yaml.safe_load(f)
                else:
                    new_config = json.load(f)

            current_provider["config"].update(new_config)

        # Override with command line options
        if endpoint:
            current_provider["config"]["endpoint"] = endpoint
        if api_key:
            current_provider["config"]["api_key"] = api_key
        if priority is not None:
            current_provider["priority"] = priority
        if enabled is not None:
            current_provider["enabled"] = enabled

        # Validate configuration
        validation_errors = validate_provider_config(current_provider)
        if validation_errors:
            rprint("[red]Configuration validation failed:[/red]")
            for error in validation_errors:
                rprint(f"  - {error}")
            raise typer.Exit(1)

        client.put(f"/api/v1/providers/{provider_name}", json=current_provider)

        rprint(f"[green]Provider '{provider_name}' updated successfully[/green]")

    except Exception as e:
        rprint(f"[red]Error updating provider: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("remove")
def remove_provider(
    ctx: typer.Context,
    provider_name: str = typer.Argument(..., help="Provider name"),
    force: bool = typer.Option(False, "--force", help="Force removal without confirmation"),
):
    """Remove a provider"""
    try:
        if not force and not typer.confirm(f"Are you sure you want to remove provider '{provider_name}'?"):
            rprint("[yellow]Operation cancelled[/yellow]")
            return

        client = ATPAPIClient.from_context(ctx)
        client.delete(f"/api/v1/providers/{provider_name}")

        rprint(f"[green]Provider '{provider_name}' removed successfully[/green]")

    except Exception as e:
        rprint(f"[red]Error removing provider: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("enable")
def enable_provider(ctx: typer.Context, provider_name: str = typer.Argument(..., help="Provider name")):
    """Enable a provider"""
    try:
        client = ATPAPIClient.from_context(ctx)
        client.post(f"/api/v1/providers/{provider_name}/enable")

        rprint(f"[green]Provider '{provider_name}' enabled[/green]")

    except Exception as e:
        rprint(f"[red]Error enabling provider: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("disable")
def disable_provider(ctx: typer.Context, provider_name: str = typer.Argument(..., help="Provider name")):
    """Disable a provider"""
    try:
        client = ATPAPIClient.from_context(ctx)
        client.post(f"/api/v1/providers/{provider_name}/disable")

        rprint(f"[yellow]Provider '{provider_name}' disabled[/yellow]")

    except Exception as e:
        rprint(f"[red]Error disabling provider: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("test")
def test_provider(
    ctx: typer.Context,
    provider_name: str = typer.Argument(..., help="Provider name"),
    model: str | None = typer.Option(None, "--model", help="Specific model to test"),
    prompt: str = typer.Option("Hello, world!", "--prompt", help="Test prompt"),
):
    """Test a provider connection and functionality"""
    try:
        client = ATPAPIClient.from_context(ctx)

        test_data = {"prompt": prompt}
        if model:
            test_data["model"] = model

        rprint(f"[blue]Testing provider '{provider_name}'...[/blue]")

        response = client.post(f"/api/v1/providers/{provider_name}/test", json=test_data)

        if response.get("success"):
            rprint("[green]✓ Provider test successful[/green]")
            rprint(f"[blue]Response time: {response.get('response_time', 0):.2f}ms[/blue]")
            rprint(f"[blue]Model used: {response.get('model_used', 'N/A')}[/blue]")

            if ctx.obj["verbose"]:
                rprint(f"[dim]Response: {response.get('response', 'N/A')}[/dim]")
        else:
            rprint("[red]✗ Provider test failed[/red]")
            rprint(f"[red]Error: {response.get('error', 'Unknown error')}[/red]")
            raise typer.Exit(1)

    except Exception as e:
        rprint(f"[red]Error testing provider: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("health")
def check_health(
    ctx: typer.Context,
    provider_name: str | None = typer.Argument(None, help="Provider name (check all if not specified)"),
):
    """Check provider health status"""
    try:
        client = ATPAPIClient.from_context(ctx)

        if provider_name:
            # Check specific provider
            response = client.get(f"/api/v1/providers/{provider_name}/health")
            providers = [response]
        else:
            # Check all providers
            response = client.get("/api/v1/providers/health")
            providers = response.get("providers", [])

        if ctx.obj["output_format"] in ["json", "yaml"]:
            format_output(providers, ctx.obj["output_format"])
        else:
            table = Table(title="Provider Health Status")
            table.add_column("Provider", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Health Score", justify="right")
            table.add_column("Response Time", justify="right")
            table.add_column("Success Rate", justify="right")
            table.add_column("Last Check", style="dim")

            for provider in providers:
                status = provider.get("status", "unknown")
                status_style = "green" if status == "healthy" else "red"
                health_score = provider.get("health_score", 0)
                health_style = "green" if health_score > 0.8 else "yellow" if health_score > 0.5 else "red"

                table.add_row(
                    provider.get("name", "N/A"),
                    f"[{status_style}]{status}[/{status_style}]",
                    f"[{health_style}]{health_score:.2f}[/{health_style}]",
                    f"{provider.get('avg_response_time', 0):.2f}ms",
                    f"{provider.get('success_rate', 0):.1f}%",
                    provider.get("last_check", "N/A"),
                )

            console.print(table)

    except Exception as e:
        rprint(f"[red]Error checking provider health: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("models")
def list_models(
    ctx: typer.Context,
    provider_name: str | None = typer.Argument(None, help="Provider name (list all if not specified)"),
    model_type: str | None = typer.Option(None, "--type", help="Filter by model type"),
):
    """List available models"""
    try:
        client = ATPAPIClient.from_context(ctx)

        params = {}
        if model_type:
            params["type"] = model_type

        if provider_name:
            response = client.get(f"/api/v1/providers/{provider_name}/models", params=params)
            models = response.get("models", [])
        else:
            response = client.get("/api/v1/models", params=params)
            models = response.get("models", [])

        if ctx.obj["output_format"] in ["json", "yaml"]:
            format_output(models, ctx.obj["output_format"])
        else:
            table = Table(title="Available Models")
            table.add_column("Model", style="cyan")
            table.add_column("Provider", style="blue")
            table.add_column("Type", style="green")
            table.add_column("Context Length", justify="right")
            table.add_column("Cost/1K Tokens", justify="right")
            table.add_column("Status", style="yellow")

            for model in models:
                status = model.get("status", "unknown")
                status_style = "green" if status == "available" else "red"

                table.add_row(
                    model.get("name", "N/A"),
                    model.get("provider", "N/A"),
                    model.get("type", "text"),
                    f"{model.get('context_length', 0):,}",
                    f"${model.get('cost_per_1k_tokens', 0):.4f}",
                    f"[{status_style}]{status}[/{status_style}]",
                )

            console.print(table)

    except Exception as e:
        rprint(f"[red]Error listing models: {e}[/red]")
        raise typer.Exit(1) from e
