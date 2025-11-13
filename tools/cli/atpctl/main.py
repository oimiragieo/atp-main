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
ATP Control CLI (atpctl)
Enterprise command-line interface for managing ATP platform.
"""

import os
import sys

import typer

# Add the parent directory to the path to import other modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", ".."))

from .commands import cluster, config, policies, providers, system

app = typer.Typer(name="atpctl", help="ATP Control - Enterprise AI Text Processing Platform CLI", no_args_is_help=True)

# Add command groups
app.add_typer(cluster.app, name="cluster", help="Cluster management commands")
app.add_typer(providers.app, name="providers", help="Provider management commands")
app.add_typer(policies.app, name="policies", help="Policy management commands")
app.add_typer(system.app, name="system", help="System management commands")
app.add_typer(config.app, name="config", help="Configuration management commands")


@app.command()
def status():
    """Get ATP platform status"""
    from .commands.system import get_system_status

    get_system_status()


@app.command()
def version():
    """Show ATP platform version information"""
    from .commands.system import show_version

    show_version()


@app.callback()
def main(
    ctx: typer.Context,
    config_file: str | None = typer.Option(None, "--config", "-c", help="Path to configuration file"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose output"),
    output_format: str = typer.Option("table", "--output", "-o", help="Output format (table, json, yaml)"),
):
    """
    ATP Control CLI - Manage your ATP platform deployment.

    Examples:
        atpctl status                    # Get platform status
        atpctl cluster list              # List cluster nodes
        atpctl providers add openai      # Add OpenAI provider
        atpctl policies validate         # Validate policies
    """
    # Store global options in context
    ctx.ensure_object(dict)
    ctx.obj["config_file"] = config_file
    ctx.obj["verbose"] = verbose
    ctx.obj["output_format"] = output_format


if __name__ == "__main__":
    app()
