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

"""Configuration management commands for atpctl"""

import json
from pathlib import Path

import typer
import yaml
from rich import print as rprint
from rich.console import Console
from rich.panel import Panel
from rich.syntax import Syntax
from rich.table import Table

from ..utils.api_client import ATPAPIClient
from ..utils.formatters import format_output

app = typer.Typer()
console = Console()


@app.command("show")
def show_config(ctx: typer.Context, section: str | None = typer.Argument(None, help="Configuration section")):
    """Show current configuration"""
    try:
        client = ATPAPIClient.from_context(ctx)

        if section:
            response = client.get(f"/api/v1/config/{section}")
        else:
            response = client.get("/api/v1/config")

        if ctx.obj["output_format"] in ["json", "yaml"]:
            format_output(response, ctx.obj["output_format"])
        else:
            # Pretty print configuration
            config_json = json.dumps(response, indent=2)
            syntax = Syntax(config_json, "json", theme="monokai", line_numbers=True)
            console.print(Panel(syntax, title="ATP Configuration", border_style="blue"))

    except Exception as e:
        rprint(f"[red]Error showing configuration: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("get")
def get_config_value(ctx: typer.Context, key: str = typer.Argument(..., help="Configuration key")):
    """Get a specific configuration value"""
    try:
        client = ATPAPIClient.from_context(ctx)
        response = client.get(f"/api/v1/config/get/{key}")

        value = response.get("value")

        if ctx.obj["output_format"] in ["json", "yaml"]:
            format_output({"key": key, "value": value}, ctx.obj["output_format"])
        else:
            rprint(f"[cyan]{key}[/cyan] = [green]{value}[/green]")

    except Exception as e:
        rprint(f"[red]Error getting configuration value: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("set")
def set_config_value(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Configuration key"),
    value: str = typer.Argument(..., help="Configuration value"),
):
    """Set a configuration value"""
    try:
        client = ATPAPIClient.from_context(ctx)

        data = {"key": key, "value": value}
        client.post("/api/v1/config/set", json=data)

        rprint(f"[green]Configuration updated:[/green] [cyan]{key}[/cyan] = [yellow]{value}[/yellow]")

    except Exception as e:
        rprint(f"[red]Error setting configuration value: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("delete")
def delete_config_value(
    ctx: typer.Context,
    key: str = typer.Argument(..., help="Configuration key"),
    force: bool = typer.Option(False, "--force", help="Force deletion without confirmation"),
):
    """Delete a configuration value"""
    try:
        if not force and not typer.confirm(f"Are you sure you want to delete '{key}'?"):
            rprint("[yellow]Operation cancelled[/yellow]")
            return

        client = ATPAPIClient.from_context(ctx)
        client.delete(f"/api/v1/config/{key}")

        rprint(f"[green]Configuration key deleted:[/green] [cyan]{key}[/cyan]")

    except Exception as e:
        rprint(f"[red]Error deleting configuration value: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("import")
def import_config(
    ctx: typer.Context,
    config_file: str = typer.Argument(..., help="Configuration file to import"),
    merge: bool = typer.Option(False, "--merge", help="Merge with existing configuration"),
):
    """Import configuration from file"""
    try:
        config_path = Path(config_file)
        if not config_path.exists():
            rprint(f"[red]Configuration file not found: {config_file}[/red]")
            raise typer.Exit(1)

        # Load configuration file
        with open(config_path) as f:
            if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                config_data = yaml.safe_load(f)
            else:
                config_data = json.load(f)

        client = ATPAPIClient.from_context(ctx)

        data = {"config": config_data, "merge": merge}
        response = client.post("/api/v1/config/import", json=data)

        rprint(f"[green]Configuration imported successfully[/green]")
        rprint(f"[blue]Keys updated: {response.get('keys_updated', 0)}[/blue]")

    except Exception as e:
        rprint(f"[red]Error importing configuration: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("export")
def export_config(
    ctx: typer.Context,
    output_file: str = typer.Argument(..., help="Output file path"),
    section: str | None = typer.Option(None, "--section", help="Export specific section only"),
):
    """Export configuration to file"""
    try:
        client = ATPAPIClient.from_context(ctx)

        if section:
            config_data = client.get(f"/api/v1/config/{section}")
        else:
            config_data = client.get("/api/v1/config")

        output_path = Path(output_file)

        # Write configuration file
        with open(output_path, "w") as f:
            if output_file.endswith(".yaml") or output_file.endswith(".yml"):
                yaml.dump(config_data, f, default_flow_style=False)
            else:
                json.dump(config_data, f, indent=2)

        rprint(f"[green]Configuration exported to:[/green] [cyan]{output_file}[/cyan]")

    except Exception as e:
        rprint(f"[red]Error exporting configuration: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("validate")
def validate_config(
    ctx: typer.Context, config_file: str | None = typer.Argument(None, help="Configuration file to validate")
):
    """Validate configuration"""
    try:
        if config_file:
            # Validate file
            config_path = Path(config_file)
            if not config_path.exists():
                rprint(f"[red]Configuration file not found: {config_file}[/red]")
                raise typer.Exit(1)

            with open(config_path) as f:
                if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                    config_data = yaml.safe_load(f)
                else:
                    config_data = json.load(f)

            client = ATPAPIClient.from_context(ctx)
            response = client.post("/api/v1/config/validate", json={"config": config_data})
        else:
            # Validate current configuration
            client = ATPAPIClient.from_context(ctx)
            response = client.get("/api/v1/config/validate")

        valid = response.get("valid", False)
        errors = response.get("errors", [])
        warnings = response.get("warnings", [])

        if valid:
            rprint("[green]✓ Configuration is valid[/green]")
        else:
            rprint("[red]✗ Configuration validation failed[/red]")

        if errors:
            rprint("\n[bold red]Errors:[/bold red]")
            for error in errors:
                rprint(f"  - [red]{error}[/red]")

        if warnings:
            rprint("\n[bold yellow]Warnings:[/bold yellow]")
            for warning in warnings:
                rprint(f"  - [yellow]{warning}[/yellow]")

        if not valid:
            raise typer.Exit(1)

    except Exception as e:
        rprint(f"[red]Error validating configuration: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("list")
def list_configs(ctx: typer.Context, section: str | None = typer.Option(None, "--section", help="Filter by section")):
    """List all configuration keys"""
    try:
        client = ATPAPIClient.from_context(ctx)

        params = {}
        if section:
            params["section"] = section

        response = client.get("/api/v1/config/keys", params=params)
        keys = response.get("keys", [])

        if ctx.obj["output_format"] in ["json", "yaml"]:
            format_output(keys, ctx.obj["output_format"])
        else:
            table = Table(title="Configuration Keys")
            table.add_column("Key", style="cyan")
            table.add_column("Section", style="blue")
            table.add_column("Type", style="green")
            table.add_column("Value", style="yellow")

            for key_info in keys:
                table.add_row(
                    key_info.get("key", "N/A"),
                    key_info.get("section", "N/A"),
                    key_info.get("type", "string"),
                    str(key_info.get("value", ""))[:50],  # Truncate long values
                )

            console.print(table)

    except Exception as e:
        rprint(f"[red]Error listing configuration keys: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("reset")
def reset_config(
    ctx: typer.Context,
    section: str | None = typer.Option(None, "--section", help="Reset specific section only"),
    force: bool = typer.Option(False, "--force", help="Force reset without confirmation"),
):
    """Reset configuration to defaults"""
    try:
        if not force:
            msg = f"Reset {section} configuration" if section else "Reset all configuration"
            if not typer.confirm(f"{msg} to defaults?"):
                rprint("[yellow]Operation cancelled[/yellow]")
                return

        client = ATPAPIClient.from_context(ctx)

        if section:
            client.post(f"/api/v1/config/reset/{section}")
        else:
            client.post("/api/v1/config/reset")

        rprint("[green]Configuration reset to defaults[/green]")

    except Exception as e:
        rprint(f"[red]Error resetting configuration: {e}[/red]")
        raise typer.Exit(1) from e
