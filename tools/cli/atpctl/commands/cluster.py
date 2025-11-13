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
Cluster management commands for atpctl
"""

import json

import typer
import yaml
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from ..utils.api_client import ATPAPIClient
from ..utils.formatters import format_output

app = typer.Typer()
console = Console()


@app.command("list")
def list_nodes(
    ctx: typer.Context,
    namespace: str | None = typer.Option(None, "--namespace", "-n", help="Filter by namespace"),
    status: str | None = typer.Option(None, "--status", "-s", help="Filter by status"),
    labels: str | None = typer.Option(None, "--labels", "-l", help="Filter by labels (key=value)"),
):
    """List cluster nodes"""
    try:
        client = ATPAPIClient.from_context(ctx)

        # Build query parameters
        params = {}
        if namespace:
            params["namespace"] = namespace
        if status:
            params["status"] = status
        if labels:
            params["labels"] = labels

        response = client.get("/api/v1/cluster/nodes", params=params)
        nodes = response.get("nodes", [])

        if ctx.obj["output_format"] == "json":
            rprint(json.dumps(nodes, indent=2))
        elif ctx.obj["output_format"] == "yaml":
            rprint(yaml.dump(nodes, default_flow_style=False))
        else:
            # Table format
            table = Table(title="Cluster Nodes")
            table.add_column("Name", style="cyan")
            table.add_column("Status", style="green")
            table.add_column("Role", style="blue")
            table.add_column("Version", style="yellow")
            table.add_column("CPU", justify="right")
            table.add_column("Memory", justify="right")
            table.add_column("Uptime", style="magenta")

            for node in nodes:
                status_style = "green" if node.get("status") == "ready" else "red"
                table.add_row(
                    node.get("name", "N/A"),
                    f"[{status_style}]{node.get('status', 'unknown')}[/{status_style}]",
                    node.get("role", "worker"),
                    node.get("version", "N/A"),
                    f"{node.get('cpu_usage', 0):.1f}%",
                    f"{node.get('memory_usage', 0):.1f}%",
                    node.get("uptime", "N/A"),
                )

            console.print(table)

    except Exception as e:
        rprint(f"[red]Error listing nodes: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("describe")
def describe_node(ctx: typer.Context, node_name: str = typer.Argument(..., help="Name of the node to describe")):
    """Describe a specific cluster node"""
    try:
        client = ATPAPIClient.from_context(ctx)
        response = client.get(f"/api/v1/cluster/nodes/{node_name}")

        if ctx.obj["output_format"] in ["json", "yaml"]:
            format_output(response, ctx.obj["output_format"])
        else:
            # Rich formatted output
            node = response

            # Basic info panel
            info_text = f"""
[bold]Name:[/bold] {node.get("name", "N/A")}
[bold]Status:[/bold] {node.get("status", "unknown")}
[bold]Role:[/bold] {node.get("role", "worker")}
[bold]Version:[/bold] {node.get("version", "N/A")}
[bold]Created:[/bold] {node.get("created_at", "N/A")}
[bold]Last Seen:[/bold] {node.get("last_seen", "N/A")}
            """
            console.print(Panel(info_text, title="Node Information", border_style="blue"))

            # Resource usage
            resources = node.get("resources", {})
            resource_text = f"""
[bold]CPU Usage:[/bold] {resources.get("cpu_usage", 0):.1f}%
[bold]Memory Usage:[/bold] {resources.get("memory_usage", 0):.1f}%
[bold]Disk Usage:[/bold] {resources.get("disk_usage", 0):.1f}%
[bold]Network In:[/bold] {resources.get("network_in", "N/A")}
[bold]Network Out:[/bold] {resources.get("network_out", "N/A")}
            """
            console.print(Panel(resource_text, title="Resource Usage", border_style="green"))

            # Labels and annotations
            if node.get("labels"):
                labels_text = "\n".join([f"[bold]{k}:[/bold] {v}" for k, v in node["labels"].items()])
                console.print(Panel(labels_text, title="Labels", border_style="yellow"))

    except Exception as e:
        rprint(f"[red]Error describing node: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("scale")
def scale_cluster(
    ctx: typer.Context,
    replicas: int = typer.Argument(..., help="Target number of replicas"),
    component: str | None = typer.Option("router", "--component", "-c", help="Component to scale"),
    namespace: str | None = typer.Option("default", "--namespace", "-n", help="Namespace"),
):
    """Scale cluster components"""
    try:
        client = ATPAPIClient.from_context(ctx)

        data = {"component": component, "replicas": replicas, "namespace": namespace}

        response = client.post("/api/v1/cluster/scale", json=data)

        rprint(f"[green]Scaling {component} to {replicas} replicas...[/green]")
        rprint(f"[blue]Operation ID: {response.get('operation_id')}[/blue]")

        # Wait for operation to complete if requested
        if typer.confirm("Wait for scaling operation to complete?"):
            wait_for_operation(ctx, response.get("operation_id"))

    except Exception as e:
        rprint(f"[red]Error scaling cluster: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("drain")
def drain_node(
    ctx: typer.Context,
    node_name: str = typer.Argument(..., help="Name of the node to drain"),
    force: bool = typer.Option(False, "--force", help="Force drain without confirmation"),
    timeout: int = typer.Option(300, "--timeout", help="Timeout in seconds"),
):
    """Drain a cluster node"""
    try:
        if not force and not typer.confirm(f"Are you sure you want to drain node {node_name}?"):
            rprint("[yellow]Operation cancelled[/yellow]")
            return

        client = ATPAPIClient.from_context(ctx)

        data = {"timeout": timeout, "force": force}

        response = client.post(f"/api/v1/cluster/nodes/{node_name}/drain", json=data)

        rprint(f"[yellow]Draining node {node_name}...[/yellow]")
        rprint(f"[blue]Operation ID: {response.get('operation_id')}[/blue]")

        # Wait for operation to complete
        wait_for_operation(ctx, response.get("operation_id"))

    except Exception as e:
        rprint(f"[red]Error draining node: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("cordon")
def cordon_node(ctx: typer.Context, node_name: str = typer.Argument(..., help="Name of the node to cordon")):
    """Cordon a cluster node (mark as unschedulable)"""
    try:
        client = ATPAPIClient.from_context(ctx)
        client.post(f"/api/v1/cluster/nodes/{node_name}/cordon")

        rprint(f"[yellow]Node {node_name} has been cordoned[/yellow]")

    except Exception as e:
        rprint(f"[red]Error cordoning node: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("uncordon")
def uncordon_node(ctx: typer.Context, node_name: str = typer.Argument(..., help="Name of the node to uncordon")):
    """Uncordon a cluster node (mark as schedulable)"""
    try:
        client = ATPAPIClient.from_context(ctx)
        client.post(f"/api/v1/cluster/nodes/{node_name}/uncordon")

        rprint(f"[green]Node {node_name} has been uncordoned[/green]")

    except Exception as e:
        rprint(f"[red]Error uncordoning node: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("logs")
def get_logs(
    ctx: typer.Context,
    component: str = typer.Argument(..., help="Component name"),
    namespace: str | None = typer.Option("default", "--namespace", "-n", help="Namespace"),
    follow: bool = typer.Option(False, "--follow", "-f", help="Follow log output"),
    tail: int | None = typer.Option(100, "--tail", help="Number of lines to show"),
    since: str | None = typer.Option(None, "--since", help="Show logs since timestamp"),
):
    """Get logs from cluster components"""
    try:
        client = ATPAPIClient.from_context(ctx)

        params = {"namespace": namespace, "tail": tail}
        if since:
            params["since"] = since
        if follow:
            params["follow"] = "true"

        if follow:
            # Stream logs
            for log_line in client.stream_get(f"/api/v1/cluster/components/{component}/logs", params=params):
                rprint(log_line.strip())
        else:
            # Get logs once
            response = client.get(f"/api/v1/cluster/components/{component}/logs", params=params)
            logs = response.get("logs", [])

            for log_entry in logs:
                timestamp = log_entry.get("timestamp", "")
                level = log_entry.get("level", "INFO")
                message = log_entry.get("message", "")

                level_color = {
                    "ERROR": "red",
                    "WARN": "yellow",
                    "WARNING": "yellow",
                    "INFO": "blue",
                    "DEBUG": "dim",
                }.get(level, "white")

                rprint(f"[dim]{timestamp}[/dim] [{level_color}]{level}[/{level_color}] {message}")

    except Exception as e:
        rprint(f"[red]Error getting logs: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("backup")
def backup_cluster(
    ctx: typer.Context,
    output_file: str | None = typer.Option(None, "--output", "-o", help="Output file path"),
    include_data: bool = typer.Option(True, "--include-data", help="Include application data"),
    compress: bool = typer.Option(True, "--compress", help="Compress backup"),
):
    """Create cluster backup"""
    try:
        client = ATPAPIClient.from_context(ctx)

        data = {"include_data": include_data, "compress": compress}

        response = client.post("/api/v1/cluster/backup", json=data)

        backup_id = response.get("backup_id")
        rprint(f"[green]Backup created with ID: {backup_id}[/green]")

        if output_file:
            # Download backup
            backup_data = client.get(f"/api/v1/cluster/backups/{backup_id}/download")
            with open(output_file, "wb") as f:
                f.write(backup_data)
            rprint(f"[blue]Backup saved to: {output_file}[/blue]")

    except Exception as e:
        rprint(f"[red]Error creating backup: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("restore")
def restore_cluster(
    ctx: typer.Context,
    backup_file: str = typer.Argument(..., help="Path to backup file"),
    force: bool = typer.Option(False, "--force", help="Force restore without confirmation"),
):
    """Restore cluster from backup"""
    try:
        if not force and not typer.confirm("This will restore the cluster from backup. Continue?"):
            rprint("[yellow]Operation cancelled[/yellow]")
            return

        client = ATPAPIClient.from_context(ctx)

        # Upload backup file
        with open(backup_file, "rb") as f:
            files = {"backup": f}
            response = client.post("/api/v1/cluster/restore", files=files)

        operation_id = response.get("operation_id")
        rprint("[yellow]Restoring cluster from backup...[/yellow]")
        rprint(f"[blue]Operation ID: {operation_id}[/blue]")

        # Wait for operation to complete
        wait_for_operation(ctx, operation_id)

    except Exception as e:
        rprint(f"[red]Error restoring cluster: {e}[/red]")
        raise typer.Exit(1) from e


def wait_for_operation(ctx: typer.Context, operation_id: str):
    """Wait for a long-running operation to complete"""
    import time

    client = ATPAPIClient.from_context(ctx)

    with console.status("[bold green]Waiting for operation to complete...") as status:
        while True:
            try:
                response = client.get(f"/api/v1/operations/{operation_id}")
                operation_status = response.get("status")

                if operation_status == "completed":
                    rprint("[green]Operation completed successfully[/green]")
                    break
                elif operation_status == "failed":
                    error = response.get("error", "Unknown error")
                    rprint(f"[red]Operation failed: {error}[/red]")
                    raise typer.Exit(1)
                elif operation_status == "cancelled":
                    rprint("[yellow]Operation was cancelled[/yellow]")
                    break

                # Update status message
                progress = response.get("progress", {})
                if progress:
                    percent = progress.get("percent", 0)
                    message = progress.get("message", "Processing...")
                    status.update(f"[bold green]{message} ({percent}%)")

                time.sleep(2)

            except KeyboardInterrupt:
                rprint("\n[yellow]Interrupted by user[/yellow]")
                if typer.confirm("Cancel the operation?"):
                    client.post(f"/api/v1/operations/{operation_id}/cancel")
                    rprint("[yellow]Operation cancelled[/yellow]")
                break
            except Exception as e:
                rprint(f"\n[red]Error checking operation status: {e}[/red]")
                break
