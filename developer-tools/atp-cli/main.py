#!/usr/bin/env python3
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
ATP Developer CLI Tool

A comprehensive command-line interface for ATP developers and system administrators.
Provides debugging, profiling, testing, and management capabilities.
"""

import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any

import click
import yaml
from atp_sdk import AsyncATPClient, ATPClient, ChatMessage
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

console = Console()

# Global configuration
CONFIG_FILE = Path.home() / ".atp" / "config.yaml"
DEFAULT_CONFIG = {
    "api_key": None,
    "base_url": "https://api.atp.company.com",
    "tenant_id": None,
    "project_id": None,
    "timeout": 30.0,
    "max_retries": 3,
    "log_level": "INFO",
}


class ATPCLIError(Exception):
    """Base exception for ATP CLI errors."""

    pass


def load_config() -> dict[str, Any]:
    """Load configuration from file or environment."""
    config = DEFAULT_CONFIG.copy()

    if CONFIG_FILE.exists():
        with open(CONFIG_FILE) as f:
            file_config = yaml.safe_load(f) or {}
            config.update(file_config)

    # Override with environment variables
    import os

    env_mapping = {
        "ATP_API_KEY": "api_key",
        "ATP_BASE_URL": "base_url",
        "ATP_TENANT_ID": "tenant_id",
        "ATP_PROJECT_ID": "project_id",
        "ATP_TIMEOUT": "timeout",
        "ATP_MAX_RETRIES": "max_retries",
        "ATP_LOG_LEVEL": "log_level",
    }

    for env_var, config_key in env_mapping.items():
        if env_var in os.environ:
            value = os.environ[env_var]
            if config_key in ["timeout", "max_retries"]:
                try:
                    value = float(value) if config_key == "timeout" else int(value)
                except ValueError:
                    pass
            config[config_key] = value

    return config


def save_config(config: dict[str, Any]):
    """Save configuration to file."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(CONFIG_FILE, "w") as f:
        yaml.dump(config, f, default_flow_style=False)


def get_client(config: dict[str, Any]) -> ATPClient:
    """Create ATP client from configuration."""
    if not config.get("api_key"):
        raise ATPCLIError("API key not configured. Run 'atp config set api_key <key>' first.")

    return ATPClient(
        api_key=config["api_key"],
        base_url=config["base_url"],
        tenant_id=config.get("tenant_id"),
        project_id=config.get("project_id"),
        timeout=config["timeout"],
        max_retries=config["max_retries"],
    )


@click.group()
@click.version_option(version="1.0.0")
def cli():
    """ATP Developer CLI - Tools for ATP developers and administrators."""
    pass


@cli.group()
def config():
    """Configuration management commands."""
    pass


@config.command()
@click.argument("key")
@click.argument("value")
def set(key: str, value: str):
    """Set a configuration value."""
    config_data = load_config()

    # Type conversion for numeric values
    if key in ["timeout"]:
        try:
            value = float(value)
        except ValueError:
            console.print(f"[red]Error: {key} must be a number[/red]")
            sys.exit(1)
    elif key in ["max_retries"]:
        try:
            value = int(value)
        except ValueError:
            console.print(f"[red]Error: {key} must be an integer[/red]")
            sys.exit(1)

    config_data[key] = value
    save_config(config_data)
    console.print(f"[green]Set {key} = {value}[/green]")


@config.command()
@click.argument("key", required=False)
def get(key: str | None):
    """Get configuration value(s)."""
    config_data = load_config()

    if key:
        if key in config_data:
            console.print(f"{key}: {config_data[key]}")
        else:
            console.print(f"[red]Configuration key '{key}' not found[/red]")
            sys.exit(1)
    else:
        table = Table(title="ATP CLI Configuration")
        table.add_column("Key", style="cyan")
        table.add_column("Value", style="green")

        for k, v in config_data.items():
            # Mask API key for security
            display_value = "***" if k == "api_key" and v else str(v)
            table.add_row(k, display_value)

        console.print(table)


@config.command()
def init():
    """Initialize ATP CLI configuration interactively."""
    console.print("[bold blue]ATP CLI Configuration Setup[/bold blue]")
    console.print("Please provide the following information:")

    config_data = load_config()

    # API Key
    api_key = click.prompt("API Key", default=config_data.get("api_key", ""), hide_input=True)
    if api_key:
        config_data["api_key"] = api_key

    # Base URL
    base_url = click.prompt("Base URL", default=config_data.get("base_url", DEFAULT_CONFIG["base_url"]))
    config_data["base_url"] = base_url

    # Tenant ID (optional)
    tenant_id = click.prompt("Tenant ID (optional)", default=config_data.get("tenant_id", ""), show_default=False)
    if tenant_id:
        config_data["tenant_id"] = tenant_id

    # Project ID (optional)
    project_id = click.prompt("Project ID (optional)", default=config_data.get("project_id", ""), show_default=False)
    if project_id:
        config_data["project_id"] = project_id

    save_config(config_data)
    console.print("[green]Configuration saved successfully![/green]")


@cli.group()
def chat():
    """Interactive chat commands."""
    pass


@chat.command()
@click.option("--model", "-m", help="Specific model to use")
@click.option("--temperature", "-t", type=float, help="Sampling temperature (0.0-2.0)")
@click.option("--max-tokens", type=int, help="Maximum tokens to generate")
@click.option("--stream", is_flag=True, help="Stream the response")
def interactive(model: str | None, temperature: float | None, max_tokens: int | None, stream: bool):
    """Start an interactive chat session."""
    config_data = load_config()

    try:
        client = get_client(config_data)
    except ATPCLIError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    console.print("[bold green]ATP Interactive Chat[/bold green]")
    console.print("Type 'exit' or 'quit' to end the session")
    console.print("Type '/help' for available commands")
    console.print()

    messages = []

    while True:
        try:
            user_input = click.prompt("You", prompt_suffix="> ")

            if user_input.lower() in ["exit", "quit"]:
                break

            if user_input == "/help":
                console.print("""
Available commands:
  /help     - Show this help message
  /clear    - Clear conversation history
  /history  - Show conversation history
  /model    - Show current model info
  /cost     - Show session cost info
  exit/quit - End the session
                """)
                continue

            if user_input == "/clear":
                messages.clear()
                console.print("[yellow]Conversation history cleared[/yellow]")
                continue

            if user_input == "/history":
                if not messages:
                    console.print("[yellow]No conversation history[/yellow]")
                else:
                    for _i, msg in enumerate(messages):
                        role_color = "blue" if msg.role == "user" else "green"
                        console.print(f"[{role_color}]{msg.role}:[/{role_color}] {msg.content}")
                continue

            if user_input == "/model":
                if model:
                    try:
                        model_info = client.get_model_info(model)
                        console.print(f"[cyan]Current model:[/cyan] {model_info.name}")
                        console.print(f"[cyan]Provider:[/cyan] {model_info.provider}")
                        console.print(f"[cyan]Context length:[/cyan] {model_info.context_length}")
                    except Exception as e:
                        console.print(f"[red]Error getting model info: {e}[/red]")
                else:
                    console.print("[yellow]No specific model set (ATP will choose optimal)[/yellow]")
                continue

            # Add user message
            messages.append(ChatMessage(role="user", content=user_input))

            # Make request
            kwargs = {}
            if model:
                kwargs["model"] = model
            if temperature is not None:
                kwargs["temperature"] = temperature
            if max_tokens:
                kwargs["max_tokens"] = max_tokens

            if stream:
                console.print("[green]Assistant:[/green] ", end="")
                response_content = ""

                for chunk in client.chat_completion(messages=messages, stream=True, **kwargs):
                    for choice in chunk.choices:
                        if choice.delta.content:
                            console.print(choice.delta.content, end="")
                            response_content += choice.delta.content

                console.print()  # New line after streaming

                if response_content:
                    messages.append(ChatMessage(role="assistant", content=response_content))
            else:
                with console.status("[bold green]Thinking..."):
                    response = client.chat_completion(messages=messages, **kwargs)

                assistant_message = response.choices[0].message.content
                console.print(f"[green]Assistant:[/green] {assistant_message}")

                # Add assistant message to history
                messages.append(ChatMessage(role="assistant", content=assistant_message))

                # Show cost info if available
                if hasattr(response, "cost") and response.cost:
                    console.print(f"[dim]Cost: ${response.cost:.4f}[/dim]")

        except KeyboardInterrupt:
            console.print("\n[yellow]Session interrupted[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Error: {e}[/red]")


@chat.command()
@click.argument("message")
@click.option("--model", "-m", help="Specific model to use")
@click.option("--temperature", "-t", type=float, help="Sampling temperature (0.0-2.0)")
@click.option("--max-tokens", type=int, help="Maximum tokens to generate")
@click.option("--stream", is_flag=True, help="Stream the response")
def send(message: str, model: str | None, temperature: float | None, max_tokens: int | None, stream: bool):
    """Send a single message and get response."""
    config_data = load_config()

    try:
        client = get_client(config_data)
    except ATPCLIError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    messages = [ChatMessage(role="user", content=message)]

    kwargs = {}
    if model:
        kwargs["model"] = model
    if temperature is not None:
        kwargs["temperature"] = temperature
    if max_tokens:
        kwargs["max_tokens"] = max_tokens

    try:
        if stream:
            for chunk in client.chat_completion(messages=messages, stream=True, **kwargs):
                for choice in chunk.choices:
                    if choice.delta.content:
                        console.print(choice.delta.content, end="")
            console.print()  # New line after streaming
        else:
            response = client.chat_completion(messages=messages, **kwargs)
            console.print(response.choices[0].message.content)

            # Show additional info
            if hasattr(response, "cost") and response.cost:
                console.print(f"[dim]Cost: ${response.cost:.4f}[/dim]")
            if hasattr(response, "provider") and response.provider:
                console.print(f"[dim]Provider: {response.provider}[/dim]")

    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.group()
def models():
    """Model management commands."""
    pass


@models.command()
def list():
    """List available models."""
    config_data = load_config()

    try:
        client = get_client(config_data)
        model_list = client.list_models()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    table = Table(title="Available Models")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Provider", style="blue")
    table.add_column("Context Length", justify="right")
    table.add_column("Input Cost", justify="right")
    table.add_column("Output Cost", justify="right")
    table.add_column("Status", style="yellow")

    for model in model_list:
        table.add_row(
            model.id,
            model.name,
            model.provider,
            str(model.context_length),
            f"${model.pricing.input_cost_per_token:.6f}",
            f"${model.pricing.output_cost_per_token:.6f}",
            model.status,
        )

    console.print(table)


@models.command()
@click.argument("model_id")
def info(model_id: str):
    """Get detailed information about a model."""
    config_data = load_config()

    try:
        client = get_client(config_data)
        model = client.get_model_info(model_id)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    # Create a detailed info panel
    info_text = f"""
[bold cyan]Model ID:[/bold cyan] {model.id}
[bold cyan]Name:[/bold cyan] {model.name}
[bold cyan]Provider:[/bold cyan] {model.provider}
[bold cyan]Description:[/bold cyan] {model.description or "N/A"}

[bold yellow]Capabilities:[/bold yellow]
• Chat: {"✓" if model.capabilities.chat else "✗"}
• Completion: {"✓" if model.capabilities.completion else "✗"}
• Embedding: {"✓" if model.capabilities.embedding else "✗"}
• Function Calling: {"✓" if model.capabilities.function_calling else "✗"}
• Streaming: {"✓" if model.capabilities.streaming else "✗"}

[bold green]Specifications:[/bold green]
• Context Length: {model.context_length:,} tokens
• Max Output: {model.max_output_tokens:,} tokens
• Status: {model.status}

[bold red]Pricing:[/bold red]
• Input: ${model.pricing.input_cost_per_token:.6f} per token
• Output: ${model.pricing.output_cost_per_token:.6f} per token
• Currency: {model.pricing.currency}

[bold blue]Metadata:[/bold blue]
• Created: {model.created}
• Updated: {model.updated}
• Tags: {", ".join(model.tags) if model.tags else "None"}
    """.strip()

    console.print(Panel(info_text, title=f"Model Information: {model.name}", border_style="blue"))


@cli.group()
def providers():
    """Provider management commands."""
    pass


@providers.command()
def list():
    """List available providers."""
    config_data = load_config()

    try:
        client = get_client(config_data)
        provider_list = client.list_providers()
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    table = Table(title="Available Providers")
    table.add_column("ID", style="cyan")
    table.add_column("Name", style="green")
    table.add_column("Status", style="yellow")
    table.add_column("Models", justify="right")
    table.add_column("Regions", justify="right")
    table.add_column("Latency", justify="right")
    table.add_column("Error Rate", justify="right")

    for provider in provider_list:
        status_color = "green" if provider.status.available else "red"
        status_text = f"[{status_color}]{'Available' if provider.status.available else 'Unavailable'}[/{status_color}]"

        latency = f"{provider.status.latency:.3f}s" if provider.status.latency else "N/A"
        error_rate = f"{provider.status.error_rate:.2%}" if provider.status.error_rate else "N/A"

        table.add_row(
            provider.id,
            provider.name,
            status_text,
            str(len(provider.models)),
            str(len(provider.regions)),
            latency,
            error_rate,
        )

    console.print(table)


@cli.group()
def cost():
    """Cost tracking and analysis commands."""
    pass


@cost.command()
@click.option("--start-date", help="Start date (YYYY-MM-DD)")
@click.option("--end-date", help="End date (YYYY-MM-DD)")
@click.option("--format", "output_format", type=click.Choice(["table", "json"]), default="table")
def info(start_date: str | None, end_date: str | None, output_format: str):
    """Get cost information and breakdown."""
    config_data = load_config()

    try:
        client = get_client(config_data)
        cost_info = client.get_cost_info(start_date, end_date)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    if output_format == "json":
        console.print(json.dumps(cost_info.__dict__, indent=2, default=str))
        return

    # Display cost information in table format
    console.print("[bold blue]Cost Information[/bold blue]")
    console.print(f"Period: {cost_info.period_start} to {cost_info.period_end}")
    console.print(f"Total Cost: [bold green]${cost_info.total_cost:.2f} {cost_info.currency}[/bold green]")
    console.print()

    # Cost breakdown
    breakdown_table = Table(title="Cost Breakdown")
    breakdown_table.add_column("Category", style="cyan")
    breakdown_table.add_column("Cost", justify="right", style="green")
    breakdown_table.add_column("Percentage", justify="right")

    total = cost_info.total_cost
    for category, amount in cost_info.breakdown.__dict__.items():
        percentage = (amount / total * 100) if total > 0 else 0
        breakdown_table.add_row(category.replace("_", " ").title(), f"${amount:.2f}", f"{percentage:.1f}%")

    console.print(breakdown_table)

    # Top models by cost
    if cost_info.top_models:
        console.print()
        models_table = Table(title="Top Models by Cost")
        models_table.add_column("Model", style="cyan")
        models_table.add_column("Cost", justify="right", style="green")
        models_table.add_column("Requests", justify="right")

        for model_data in cost_info.top_models[:5]:  # Top 5
            models_table.add_row(
                model_data.get("model", "Unknown"),
                f"${model_data.get('cost', 0):.2f}",
                str(model_data.get("requests", 0)),
            )

        console.print(models_table)


@cli.group()
def debug():
    """Debugging and diagnostic commands."""
    pass


@debug.command()
def health():
    """Check ATP service health."""
    config_data = load_config()

    try:
        client = get_client(config_data)

        with console.status("[bold green]Checking service health..."):
            health_data = client.health_check()

        # Display health information
        if health_data.get("status") == "healthy":
            console.print("[bold green]✓ ATP Service is healthy[/bold green]")
        else:
            console.print("[bold red]✗ ATP Service is unhealthy[/bold red]")

        # Show detailed health info
        table = Table(title="Health Check Details")
        table.add_column("Component", style="cyan")
        table.add_column("Status", style="green")
        table.add_column("Details")

        for component, info in health_data.items():
            if isinstance(info, dict):
                status = info.get("status", "unknown")
                details = info.get("details", "")
            else:
                status = str(info)
                details = ""

            status_color = "green" if status in ["healthy", "ok", "up"] else "red"
            table.add_row(component, f"[{status_color}]{status}[/{status_color}]", details)

        console.print(table)

    except Exception as e:
        console.print(f"[red]Error checking health: {e}[/red]")
        sys.exit(1)


@debug.command()
@click.option("--duration", "-d", type=int, default=60, help="Test duration in seconds")
@click.option("--requests", "-r", type=int, default=10, help="Number of concurrent requests")
def load_test(duration: int, requests: int):
    """Run a load test against the ATP service."""
    config_data = load_config()

    try:
        get_client(config_data)
    except ATPCLIError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    console.print("[bold blue]Starting load test...[/bold blue]")
    console.print(f"Duration: {duration} seconds")
    console.print(f"Concurrent requests: {requests}")
    console.print()

    # Test message
    test_message = [ChatMessage(role="user", content="Hello, this is a load test message.")]

    # Statistics
    stats = {
        "total_requests": 0,
        "successful_requests": 0,
        "failed_requests": 0,
        "total_latency": 0,
        "min_latency": float("inf"),
        "max_latency": 0,
        "errors": [],
    }

    async def make_request():
        """Make a single test request."""
        start_time = time.time()
        try:
            async with AsyncATPClient(
                api_key=config_data["api_key"],
                base_url=config_data["base_url"],
                tenant_id=config_data.get("tenant_id"),
                project_id=config_data.get("project_id"),
            ) as async_client:
                await async_client.chat_completion(messages=test_message)

            latency = time.time() - start_time
            stats["successful_requests"] += 1
            stats["total_latency"] += latency
            stats["min_latency"] = min(stats["min_latency"], latency)
            stats["max_latency"] = max(stats["max_latency"], latency)

        except Exception as e:
            stats["failed_requests"] += 1
            stats["errors"].append(str(e))

        stats["total_requests"] += 1

    async def run_load_test():
        """Run the load test."""
        end_time = time.time() + duration

        with Progress(
            SpinnerColumn(), TextColumn("[progress.description]{task.description}"), console=console
        ) as progress:
            task = progress.add_task("Running load test...", total=None)

            while time.time() < end_time:
                # Create batch of concurrent requests
                tasks = [make_request() for _ in range(requests)]
                await asyncio.gather(*tasks, return_exceptions=True)

                # Update progress
                progress.update(
                    task,
                    description=f"Requests: {stats['total_requests']}, Success: {stats['successful_requests']}, Failed: {stats['failed_requests']}",
                )

                # Small delay between batches
                await asyncio.sleep(0.1)

    # Run the load test
    try:
        asyncio.run(run_load_test())
    except KeyboardInterrupt:
        console.print("\n[yellow]Load test interrupted[/yellow]")

    # Display results
    console.print("\n[bold blue]Load Test Results[/bold blue]")

    results_table = Table()
    results_table.add_column("Metric", style="cyan")
    results_table.add_column("Value", style="green")

    avg_latency = stats["total_latency"] / stats["successful_requests"] if stats["successful_requests"] > 0 else 0
    success_rate = (stats["successful_requests"] / stats["total_requests"] * 100) if stats["total_requests"] > 0 else 0

    results_table.add_row("Total Requests", str(stats["total_requests"]))
    results_table.add_row("Successful Requests", str(stats["successful_requests"]))
    results_table.add_row("Failed Requests", str(stats["failed_requests"]))
    results_table.add_row("Success Rate", f"{success_rate:.1f}%")
    results_table.add_row("Average Latency", f"{avg_latency:.3f}s")
    results_table.add_row(
        "Min Latency", f"{stats['min_latency']:.3f}s" if stats["min_latency"] != float("inf") else "N/A"
    )
    results_table.add_row("Max Latency", f"{stats['max_latency']:.3f}s")

    console.print(results_table)

    # Show errors if any
    if stats["errors"]:
        console.print("\n[bold red]Errors encountered:[/bold red]")
        error_counts = {}
        for error in stats["errors"]:
            error_counts[error] = error_counts.get(error, 0) + 1

        for error, count in error_counts.items():
            console.print(f"• {error} ({count} times)")


@cli.group()
def tools():
    """Development tools and utilities."""
    pass


@tools.command()
@click.argument("input_file", type=click.Path(exists=True))
@click.option("--output", "-o", help="Output file (default: stdout)")
@click.option("--format", "output_format", type=click.Choice(["json", "yaml", "table"]), default="json")
def validate_config(input_file: str, output: str | None, output_format: str):
    """Validate ATP configuration file."""
    try:
        with open(input_file) as f:
            if input_file.endswith(".yaml") or input_file.endswith(".yml"):
                config_data = yaml.safe_load(f)
            else:
                config_data = json.load(f)

        # Validation logic here
        validation_results = {"valid": True, "errors": [], "warnings": [], "config": config_data}

        # Basic validation
        required_fields = ["api_key", "base_url"]
        for field in required_fields:
            if field not in config_data or not config_data[field]:
                validation_results["errors"].append(f"Missing required field: {field}")
                validation_results["valid"] = False

        # Output results
        if output_format == "json":
            result = json.dumps(validation_results, indent=2)
        elif output_format == "yaml":
            result = yaml.dump(validation_results, default_flow_style=False)
        else:  # table
            if validation_results["valid"]:
                console.print("[green]✓ Configuration is valid[/green]")
            else:
                console.print("[red]✗ Configuration is invalid[/red]")
                for error in validation_results["errors"]:
                    console.print(f"  [red]Error: {error}[/red]")

            for warning in validation_results["warnings"]:
                console.print(f"  [yellow]Warning: {warning}[/yellow]")
            return

        if output:
            with open(output, "w") as f:
                f.write(result)
            console.print(f"[green]Validation results written to {output}[/green]")
        else:
            console.print(result)

    except Exception as e:
        console.print(f"[red]Error validating config: {e}[/red]")
        sys.exit(1)


@tools.command()
@click.option("--name", prompt="Plugin name", help="Name of the plugin")
@click.option("--type", "plugin_type", type=click.Choice(["adapter", "middleware", "tool"]), prompt="Plugin type")
@click.option("--language", type=click.Choice(["python", "javascript", "go", "java"]), prompt="Programming language")
def create_plugin(name: str, plugin_type: str, language: str):
    """Create a new ATP plugin from template."""
    plugin_dir = Path(f"atp-{plugin_type}-{name}")

    if plugin_dir.exists():
        console.print(f"[red]Directory {plugin_dir} already exists[/red]")
        sys.exit(1)

    console.print(f"[blue]Creating {plugin_type} plugin '{name}' in {language}...[/blue]")

    # Create plugin directory structure
    plugin_dir.mkdir()

    # Create basic files based on language and type
    if language == "python":
        create_python_plugin(plugin_dir, name, plugin_type)
    elif language == "javascript":
        create_javascript_plugin(plugin_dir, name, plugin_type)
    elif language == "go":
        create_go_plugin(plugin_dir, name, plugin_type)
    elif language == "java":
        create_java_plugin(plugin_dir, name, plugin_type)

    console.print(f"[green]✓ Plugin created successfully in {plugin_dir}[/green]")
    console.print("[blue]Next steps:[/blue]")
    console.print(f"  1. cd {plugin_dir}")
    console.print("  2. Edit the generated files to implement your plugin")
    console.print("  3. Test your plugin with the provided test files")
    console.print("  4. Submit to the ATP marketplace when ready")


def create_python_plugin(plugin_dir: Path, name: str, plugin_type: str):
    """Create Python plugin template."""
    # Create directory structure
    (plugin_dir / "src").mkdir()
    (plugin_dir / "tests").mkdir()
    (plugin_dir / "docs").mkdir()

    # Create main plugin file
    main_file = plugin_dir / "src" / f"{name}_{plugin_type}.py"
    main_file.write_text(f'''"""
ATP {plugin_type.title()} Plugin: {name}

This is a template for an ATP {plugin_type} plugin.
"""

class {name.title()}{plugin_type.title()}:
    """Main {plugin_type} class."""
    
    def __init__(self, config=None):
        self.config = config or {{}}
    
    def process(self, data):
        """Process data through the {plugin_type}."""
        # Implement your {plugin_type} logic here
        return data
''')

    # Create setup.py
    setup_file = plugin_dir / "setup.py"
    setup_file.write_text(f"""from setuptools import setup, find_packages

setup(
    name="atp-{plugin_type}-{name}",
    version="0.1.0",
    description="ATP {plugin_type.title()} Plugin: {name}",
    packages=find_packages(where="src"),
    package_dir={{"": "src"}},
    install_requires=[
        "atp-sdk>=1.0.0",
    ],
    python_requires=">=3.8",
)
""")

    # Create README
    readme_file = plugin_dir / "README.md"
    readme_file.write_text(f"""# ATP {plugin_type.title()} Plugin: {name}

## Description

This is an ATP {plugin_type} plugin that...

## Installation

```bash
pip install -e .
```

## Usage

```python
from {name}_{plugin_type} import {name.title()}{plugin_type.title()}

{plugin_type} = {name.title()}{plugin_type.title()}()
result = {plugin_type}.process(data)
```

## Configuration

...

## License

Apache License 2.0
""")


def create_javascript_plugin(plugin_dir: Path, name: str, plugin_type: str):
    """Create JavaScript plugin template."""
    # Create package.json
    package_file = plugin_dir / "package.json"
    package_file.write_text(f"""{{
  "name": "atp-{plugin_type}-{name}",
  "version": "0.1.0",
  "description": "ATP {plugin_type.title()} Plugin: {name}",
  "main": "index.js",
  "dependencies": {{
    "atp-sdk": "^1.0.0"
  }},
  "devDependencies": {{
    "jest": "^29.0.0"
  }},
  "scripts": {{
    "test": "jest"
  }}
}}
""")

    # Create main file
    main_file = plugin_dir / "index.js"
    main_file.write_text(f"""/**
 * ATP {plugin_type.title()} Plugin: {name}
 */

class {name.title()}{plugin_type.title()} {{
    constructor(config = {{}}) {{
        this.config = config;
    }}
    
    process(data) {{
        // Implement your {plugin_type} logic here
        return data;
    }}
}}

module.exports = {name.title()}{plugin_type.title()};
""")


def create_go_plugin(plugin_dir: Path, name: str, plugin_type: str):
    """Create Go plugin template."""
    # Create go.mod
    mod_file = plugin_dir / "go.mod"
    mod_file.write_text(f"""module atp-{plugin_type}-{name}

go 1.21

require (
    github.com/atp-project/go-sdk v1.0.0
)
""")

    # Create main file
    main_file = plugin_dir / "main.go"
    main_file.write_text(f"""package main

import (
    "fmt"
)

// {name.title()}{plugin_type.title()} represents the main {plugin_type} struct
type {name.title()}{plugin_type.title()} struct {{
    config map[string]interface{{}}
}}

// New{name.title()}{plugin_type.title()} creates a new {plugin_type} instance
func New{name.title()}{plugin_type.title()}(config map[string]interface{{}}) *{name.title()}{plugin_type.title()} {{
    return &{name.title()}{plugin_type.title()}{{
        config: config,
    }}
}}

// Process processes data through the {plugin_type}
func (a *{name.title()}{plugin_type.title()}) Process(data interface{{}}) (interface{{}}, error) {{
    // Implement your {plugin_type} logic here
    return data, nil
}}

func main() {{
    fmt.Println("ATP {plugin_type.title()} Plugin: {name}")
}}
""")


def create_java_plugin(plugin_dir: Path, name: str, plugin_type: str):
    """Create Java plugin template."""
    # Create pom.xml
    pom_file = plugin_dir / "pom.xml"
    pom_file.write_text(f"""<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 
         http://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    
    <groupId>com.atp.plugins</groupId>
    <artifactId>atp-{plugin_type}-{name}</artifactId>
    <version>0.1.0</version>
    
    <properties>
        <maven.compiler.source>11</maven.compiler.source>
        <maven.compiler.target>11</maven.compiler.target>
    </properties>
    
    <dependencies>
        <dependency>
            <groupId>com.atp</groupId>
            <artifactId>atp-java-sdk</artifactId>
            <version>1.0.0</version>
        </dependency>
    </dependencies>
</project>
""")

    # Create Java source directory
    java_dir = plugin_dir / "src" / "main" / "java" / "com" / "atp" / "plugins"
    java_dir.mkdir(parents=True)

    # Create main Java file
    java_file = java_dir / f"{name.title()}{plugin_type.title()}.java"
    java_file.write_text(f"""package com.atp.plugins;

import java.util.Map;

/**
 * ATP {plugin_type.title()} Plugin: {name}
 */
public class {name.title()}{plugin_type.title()} {{
    
    private final Map<String, Object> config;
    
    public {name.title()}{plugin_type.title()}(Map<String, Object> config) {{
        this.config = config;
    }}
    
    public Object process(Object data) {{
        // Implement your {plugin_type} logic here
        return data;
    }}
}}
""")


if __name__ == "__main__":
    cli()
