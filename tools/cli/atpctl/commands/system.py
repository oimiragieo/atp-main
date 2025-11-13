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

"""System management commands for atpctl"""

import json
from datetime import UTC, datetime

import typer
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..utils.api_client import ATPAPIClient
from ..utils.formatters import format_output

app = typer.Typer()
console = Console()

# Version information
ATP_VERSION = "2.0.0"
ATP_BUILD_DATE = "2025-01-13"


@app.command("status")
def status(ctx: typer.Context):
    """Get ATP system status"""
    get_system_status(ctx)


@app.command("version")
def version_cmd(ctx: typer.Context):  # noqa: ARG001
    """Show ATP version information"""
    show_version()


@app.command("info")
def system_info(ctx: typer.Context):
    """Get detailed system information"""
    try:
        client = ATPAPIClient.from_context(ctx)
        response = client.get("/api/v1/system/info")

        if ctx.obj["output_format"] in ["json", "yaml"]:
            format_output(response, ctx.obj["output_format"])
        else:
            # Display system info in panels
            info_text = f"""
[bold]Version:[/bold] {response.get("version", "N/A")}
[bold]Build:[/bold] {response.get("build", "N/A")}
[bold]Uptime:[/bold] {response.get("uptime", "N/A")}
[bold]Platform:[/bold] {response.get("platform", "N/A")}
[bold]Python:[/bold] {response.get("python_version", "N/A")}
            """
            console.print(Panel(info_text, title="System Information", border_style="blue"))

            # Resource usage
            resources = response.get("resources", {})
            if resources:
                resource_text = f"""
[bold]CPU Usage:[/bold] {resources.get("cpu_percent", 0):.1f}%
[bold]Memory:[/bold] {resources.get("memory_percent", 0):.1f}%
[bold]Disk:[/bold] {resources.get("disk_percent", 0):.1f}%
[bold]Active Connections:[/bold] {resources.get("active_connections", 0):,}
[bold]Total Requests:[/bold] {resources.get("total_requests", 0):,}
                """
                console.print(Panel(resource_text, title="Resource Usage", border_style="green"))

    except Exception as e:
        rprint(f"[red]Error getting system info: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("health")
def health_check(ctx: typer.Context):
    """Check overall system health"""
    try:
        client = ATPAPIClient.from_context(ctx)
        response = client.get("/health")

        if ctx.obj["output_format"] in ["json", "yaml"]:
            format_output(response, ctx.obj["output_format"])
        else:
            status = response.get("status", "unknown")
            status_color = "green" if status == "healthy" else "red"

            rprint(f"[{status_color}]System Status: {status.upper()}[/{status_color}]")

            # Show component health
            components = response.get("components", {})
            if components:
                table = Table(title="Component Health")
                table.add_column("Component", style="cyan")
                table.add_column("Status", style="green")
                table.add_column("Details", style="dim")

                for component, details in components.items():
                    comp_status = details.get("status", "unknown")
                    comp_color = "green" if comp_status == "healthy" else "red"

                    table.add_row(
                        component,
                        f"[{comp_color}]{comp_status}[/{comp_color}]",
                        details.get("message", ""),
                    )

                console.print(table)

    except Exception as e:
        rprint(f"[red]Error checking health: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("metrics")
def system_metrics(
    ctx: typer.Context,
    interval: int = typer.Option(60, "--interval", help="Time interval in seconds"),
    metric_type: str | None = typer.Option(None, "--type", help="Metric type filter"),
):
    """Get system metrics"""
    try:
        client = ATPAPIClient.from_context(ctx)

        params = {"interval": interval}
        if metric_type:
            params["type"] = metric_type

        response = client.get("/api/v1/system/metrics", params=params)

        if ctx.obj["output_format"] in ["json", "yaml"]:
            format_output(response, ctx.obj["output_format"])
        else:
            metrics = response.get("metrics", [])

            table = Table(title=f"System Metrics (Last {interval}s)")
            table.add_column("Metric", style="cyan")
            table.add_column("Value", justify="right", style="green")
            table.add_column("Unit", style="dim")
            table.add_column("Change", justify="right", style="yellow")

            for metric in metrics:
                change = metric.get("change", 0)
                change_str = f"+{change:.1f}%" if change > 0 else f"{change:.1f}%"
                change_color = "red" if change < 0 else "green"

                table.add_row(
                    metric.get("name", "N/A"),
                    str(metric.get("value", 0)),
                    metric.get("unit", ""),
                    f"[{change_color}]{change_str}[/{change_color}]",
                )

            console.print(table)

    except Exception as e:
        rprint(f"[red]Error getting metrics: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("logs")
def system_logs(
    ctx: typer.Context,
    level: str = typer.Option("INFO", "--level", help="Log level filter"),
    tail: int = typer.Option(100, "--tail", help="Number of lines"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
):
    """View system logs"""
    try:
        client = ATPAPIClient.from_context(ctx)

        params = {"level": level, "tail": tail}
        if follow:
            params["follow"] = "true"

        if follow:
            # Stream logs
            for log_line in client.stream_get("/api/v1/system/logs", params=params):
                try:
                    log_entry = json.loads(log_line)
                    timestamp = log_entry.get("timestamp", "")
                    log_level = log_entry.get("level", "INFO")
                    message = log_entry.get("message", "")

                    level_color = {
                        "ERROR": "red",
                        "WARN": "yellow",
                        "WARNING": "yellow",
                        "INFO": "blue",
                        "DEBUG": "dim",
                    }.get(log_level, "white")

                    rprint(f"[dim]{timestamp}[/dim] [{level_color}]{log_level}[/{level_color}] {message}")
                except json.JSONDecodeError:
                    rprint(log_line)
        else:
            response = client.get("/api/v1/system/logs", params=params)
            logs = response.get("logs", [])

            for log_entry in logs:
                timestamp = log_entry.get("timestamp", "")
                log_level = log_entry.get("level", "INFO")
                message = log_entry.get("message", "")

                level_color = {
                    "ERROR": "red",
                    "WARN": "yellow",
                    "WARNING": "yellow",
                    "INFO": "blue",
                    "DEBUG": "dim",
                }.get(log_level, "white")

                rprint(f"[dim]{timestamp}[/dim] [{level_color}]{log_level}[/{level_color}] {message}")

    except Exception as e:
        rprint(f"[red]Error getting logs: {e}[/red]")
        raise typer.Exit(1) from e


def get_system_status(ctx: typer.Context | None = None) -> None:
    """Get ATP platform status (called from main.py).

    Args:
        ctx: Typer context (optional)
    """
    try:
        if ctx:
            client = ATPAPIClient.from_context(ctx)
        else:
            # Default client when called without context
            client = ATPAPIClient(base_url="http://localhost:8000")

        response = client.get("/health")

        status = response.get("status", "unknown")
        status_color = "green" if status == "healthy" else "red"

        rprint(f"\n[bold]ATP Platform Status[/bold]")
        rprint(f"Status: [{status_color}]{status.upper()}[/{status_color}]")

        if "version" in response:
            rprint(f"Version: [blue]{response['version']}[/blue]")

        if "uptime" in response:
            rprint(f"Uptime: [yellow]{response['uptime']}[/yellow]")

        rprint()

    except Exception as e:
        rprint(f"[red]Error: Unable to connect to ATP service[/red]")
        rprint(f"[dim]{e}[/dim]")
        if ctx:
            raise typer.Exit(1) from e


def show_version() -> None:
    """Show ATP platform version information (called from main.py)."""
    rprint(f"\n[bold cyan]ATP Control CLI (atpctl)[/bold cyan]")
    rprint(f"Version: [green]{ATP_VERSION}[/green]")
    rprint(f"Build Date: [yellow]{ATP_BUILD_DATE}[/yellow]")
    rprint(f"Current Time: [dim]{datetime.now(UTC).strftime('%Y-%m-%d %H:%M:%S UTC')}[/dim]")
    rprint()
