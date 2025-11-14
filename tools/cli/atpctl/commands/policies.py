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

"""Policy management commands for atpctl"""

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
from ..utils.validators import validate_policy_config

app = typer.Typer()
console = Console()


@app.command("list")
def list_policies(
    ctx: typer.Context,
    policy_type: str | None = typer.Option(None, "--type", "-t", help="Filter by policy type"),
    enabled: bool | None = typer.Option(None, "--enabled", help="Filter by enabled status"),
):
    """List all policies"""
    try:
        client = ATPAPIClient.from_context(ctx)

        params = {}
        if policy_type:
            params["type"] = policy_type
        if enabled is not None:
            params["enabled"] = str(enabled).lower()

        response = client.get("/api/v1/policies", params=params)
        policies = response.get("policies", [])

        if ctx.obj["output_format"] == "json":
            rprint(json.dumps(policies, indent=2))
        elif ctx.obj["output_format"] == "yaml":
            rprint(yaml.dump(policies, default_flow_style=False))
        else:
            table = Table(title="ATP Policies")
            table.add_column("Name", style="cyan")
            table.add_column("Type", style="blue")
            table.add_column("Enabled", style="green")
            table.add_column("Priority", justify="right")
            table.add_column("Rules", justify="right")
            table.add_column("Created", style="dim")

            for policy in policies:
                enabled_status = policy.get("enabled", False)
                enabled_style = "green" if enabled_status else "red"
                enabled_text = "✓" if enabled_status else "✗"

                table.add_row(
                    policy.get("name", "N/A"),
                    policy.get("type", "unknown"),
                    f"[{enabled_style}]{enabled_text}[/{enabled_style}]",
                    str(policy.get("priority", 100)),
                    str(len(policy.get("rules", []))),
                    policy.get("created_at", "N/A"),
                )

            console.print(table)

    except Exception as e:
        rprint(f"[red]Error listing policies: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("describe")
def describe_policy(ctx: typer.Context, policy_name: str = typer.Argument(..., help="Name of the policy")):
    """Describe a specific policy"""
    try:
        client = ATPAPIClient.from_context(ctx)
        response = client.get(f"/api/v1/policies/{policy_name}")

        if ctx.obj["output_format"] in ["json", "yaml"]:
            format_output(response, ctx.obj["output_format"])
        else:
            policy = response

            # Basic info
            info_text = f"""
[bold]Name:[/bold] {policy.get("name", "N/A")}
[bold]Type:[/bold] {policy.get("type", "unknown")}
[bold]Enabled:[/bold] {"Yes" if policy.get("enabled") else "No"}
[bold]Priority:[/bold] {policy.get("priority", 100)}
[bold]Created:[/bold] {policy.get("created_at", "N/A")}
[bold]Updated:[/bold] {policy.get("updated_at", "N/A")}
[bold]Description:[/bold] {policy.get("description", "No description")}
            """
            console.print(Panel(info_text, title="Policy Information", border_style="blue"))

            # Rules
            rules = policy.get("rules", [])
            if rules:
                rules_json = json.dumps(rules, indent=2)
                syntax = Syntax(rules_json, "json", theme="monokai", line_numbers=True)
                console.print(Panel(syntax, title="Policy Rules", border_style="green"))

            # Statistics
            stats = policy.get("statistics", {})
            if stats:
                stats_text = f"""
[bold]Applied:[/bold] {stats.get("times_applied", 0):,}
[bold]Blocked:[/bold] {stats.get("times_blocked", 0):,}
[bold]Allowed:[/bold] {stats.get("times_allowed", 0):,}
[bold]Last Applied:[/bold] {stats.get("last_applied", "Never")}
                """
                console.print(Panel(stats_text, title="Statistics", border_style="yellow"))

    except Exception as e:
        rprint(f"[red]Error describing policy: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("add")
def add_policy(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Policy name"),
    policy_type: str = typer.Argument(..., help="Policy type"),
    config_file: str | None = typer.Option(None, "--config", "-c", help="Policy configuration file"),
    enabled: bool = typer.Option(True, "--enabled/--disabled", help="Enable policy"),
    priority: int = typer.Option(100, "--priority", help="Policy priority"),
):
    """Add a new policy"""
    try:
        # Load configuration from file if provided
        rules = []
        description = ""

        if config_file:
            config_path = Path(config_file)
            if not config_path.exists():
                rprint(f"[red]Configuration file not found: {config_file}[/red]")
                raise typer.Exit(1)

            with open(config_path) as f:
                if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                    config_data = yaml.safe_load(f)
                else:
                    config_data = json.load(f)

            rules = config_data.get("rules", [])
            description = config_data.get("description", "")

        policy_data = {
            "name": name,
            "type": policy_type,
            "enabled": enabled,
            "priority": priority,
            "rules": rules,
            "description": description,
        }

        # Validate policy
        validation_errors = validate_policy_config(policy_data)
        if validation_errors:
            rprint("[red]Policy validation failed:[/red]")
            for error in validation_errors:
                rprint(f"  - {error}")
            raise typer.Exit(1)

        client = ATPAPIClient.from_context(ctx)
        response = client.post("/api/v1/policies", json=policy_data)

        rprint(f"[green]Policy '{name}' added successfully[/green]")
        rprint(f"[blue]Policy ID: {response.get('id')}[/blue]")

    except Exception as e:
        rprint(f"[red]Error adding policy: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("update")
def update_policy(
    ctx: typer.Context,
    policy_name: str = typer.Argument(..., help="Policy name"),
    config_file: str | None = typer.Option(None, "--config", "-c", help="Policy configuration file"),
    enabled: bool | None = typer.Option(None, "--enabled/--disabled", help="Enable/disable policy"),
    priority: int | None = typer.Option(None, "--priority", help="Policy priority"),
):
    """Update an existing policy"""
    try:
        client = ATPAPIClient.from_context(ctx)

        # Get current policy
        current_policy = client.get(f"/api/v1/policies/{policy_name}")

        # Update from file if provided
        if config_file:
            config_path = Path(config_file)
            if not config_path.exists():
                rprint(f"[red]Configuration file not found: {config_file}[/red]")
                raise typer.Exit(1)

            with open(config_path) as f:
                if config_file.endswith(".yaml") or config_file.endswith(".yml"):
                    config_data = yaml.safe_load(f)
                else:
                    config_data = json.load(f)

            if "rules" in config_data:
                current_policy["rules"] = config_data["rules"]
            if "description" in config_data:
                current_policy["description"] = config_data["description"]

        # Override with command line options
        if enabled is not None:
            current_policy["enabled"] = enabled
        if priority is not None:
            current_policy["priority"] = priority

        # Validate policy
        validation_errors = validate_policy_config(current_policy)
        if validation_errors:
            rprint("[red]Policy validation failed:[/red]")
            for error in validation_errors:
                rprint(f"  - {error}")
            raise typer.Exit(1)

        client.put(f"/api/v1/policies/{policy_name}", json=current_policy)

        rprint(f"[green]Policy '{policy_name}' updated successfully[/green]")

    except Exception as e:
        rprint(f"[red]Error updating policy: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("remove")
def remove_policy(
    ctx: typer.Context,
    policy_name: str = typer.Argument(..., help="Policy name"),
    force: bool = typer.Option(False, "--force", help="Force removal without confirmation"),
):
    """Remove a policy"""
    try:
        if not force and not typer.confirm(f"Are you sure you want to remove policy '{policy_name}'?"):
            rprint("[yellow]Operation cancelled[/yellow]")
            return

        client = ATPAPIClient.from_context(ctx)
        client.delete(f"/api/v1/policies/{policy_name}")

        rprint(f"[green]Policy '{policy_name}' removed successfully[/green]")

    except Exception as e:
        rprint(f"[red]Error removing policy: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("enable")
def enable_policy(ctx: typer.Context, policy_name: str = typer.Argument(..., help="Policy name")):
    """Enable a policy"""
    try:
        client = ATPAPIClient.from_context(ctx)
        client.post(f"/api/v1/policies/{policy_name}/enable")

        rprint(f"[green]Policy '{policy_name}' enabled[/green]")

    except Exception as e:
        rprint(f"[red]Error enabling policy: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("disable")
def disable_policy(ctx: typer.Context, policy_name: str = typer.Argument(..., help="Policy name")):
    """Disable a policy"""
    try:
        client = ATPAPIClient.from_context(ctx)
        client.post(f"/api/v1/policies/{policy_name}/disable")

        rprint(f"[yellow]Policy '{policy_name}' disabled[/yellow]")

    except Exception as e:
        rprint(f"[red]Error disabling policy: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("test")
def test_policy(
    ctx: typer.Context,
    policy_name: str = typer.Argument(..., help="Policy name"),
    test_file: str | None = typer.Option(None, "--test-file", help="Test request file"),
):
    """Test a policy with sample data"""
    try:
        client = ATPAPIClient.from_context(ctx)

        test_data = {}
        if test_file:
            test_path = Path(test_file)
            if not test_path.exists():
                rprint(f"[red]Test file not found: {test_file}[/red]")
                raise typer.Exit(1)

            with open(test_path) as f:
                if test_file.endswith(".yaml") or test_file.endswith(".yml"):
                    test_data = yaml.safe_load(f)
                else:
                    test_data = json.load(f)

        rprint(f"[blue]Testing policy '{policy_name}'...[/blue]")

        response = client.post(f"/api/v1/policies/{policy_name}/test", json=test_data)

        if response.get("allowed"):
            rprint("[green]✓ Request allowed by policy[/green]")
        else:
            rprint("[red]✗ Request blocked by policy[/red]")

        if "reason" in response:
            rprint(f"[yellow]Reason: {response['reason']}[/yellow]")

        if ctx.obj["verbose"] and "details" in response:
            details_json = json.dumps(response["details"], indent=2)
            syntax = Syntax(details_json, "json", theme="monokai")
            console.print(Panel(syntax, title="Test Details", border_style="dim"))

    except Exception as e:
        rprint(f"[red]Error testing policy: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("validate")
def validate_policy(ctx: typer.Context, policy_file: str = typer.Argument(..., help="Policy file to validate")):
    """Validate a policy configuration file"""
    try:
        policy_path = Path(policy_file)
        if not policy_path.exists():
            rprint(f"[red]Policy file not found: {policy_file}[/red]")
            raise typer.Exit(1)

        with open(policy_path) as f:
            if policy_file.endswith(".yaml") or policy_file.endswith(".yml"):
                policy_data = yaml.safe_load(f)
            else:
                policy_data = json.load(f)

        # Validate locally
        validation_errors = validate_policy_config(policy_data)

        if validation_errors:
            rprint("[red]✗ Policy validation failed[/red]")
            for error in validation_errors:
                rprint(f"  - [red]{error}[/red]")
            raise typer.Exit(1)

        # Validate with server
        client = ATPAPIClient.from_context(ctx)
        response = client.post("/api/v1/policies/validate", json=policy_data)

        if response.get("valid"):
            rprint("[green]✓ Policy is valid[/green]")
        else:
            rprint("[red]✗ Server validation failed[/red]")
            errors = response.get("errors", [])
            for error in errors:
                rprint(f"  - [red]{error}[/red]")
            raise typer.Exit(1)

    except Exception as e:
        rprint(f"[red]Error validating policy: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("stats")
def policy_stats(
    ctx: typer.Context,
    policy_name: str | None = typer.Argument(None, help="Policy name (show all if not specified)"),
    interval: int = typer.Option(3600, "--interval", help="Time interval in seconds"),
):
    """Show policy statistics"""
    try:
        client = ATPAPIClient.from_context(ctx)

        params = {"interval": interval}

        if policy_name:
            response = client.get(f"/api/v1/policies/{policy_name}/stats", params=params)
            policies = [response]
        else:
            response = client.get("/api/v1/policies/stats", params=params)
            policies = response.get("policies", [])

        if ctx.obj["output_format"] in ["json", "yaml"]:
            format_output(policies, ctx.obj["output_format"])
        else:
            table = Table(title=f"Policy Statistics (Last {interval}s)")
            table.add_column("Policy", style="cyan")
            table.add_column("Applied", justify="right", style="blue")
            table.add_column("Allowed", justify="right", style="green")
            table.add_column("Blocked", justify="right", style="red")
            table.add_column("Success Rate", justify="right", style="yellow")

            for policy in policies:
                stats = policy.get("statistics", {})
                applied = stats.get("times_applied", 0)
                allowed = stats.get("times_allowed", 0)
                blocked = stats.get("times_blocked", 0)
                success_rate = (allowed / applied * 100) if applied > 0 else 0

                table.add_row(
                    policy.get("name", "N/A"),
                    f"{applied:,}",
                    f"{allowed:,}",
                    f"{blocked:,}",
                    f"{success_rate:.1f}%",
                )

            console.print(table)

    except Exception as e:
        rprint(f"[red]Error getting policy statistics: {e}[/red]")
        raise typer.Exit(1) from e
