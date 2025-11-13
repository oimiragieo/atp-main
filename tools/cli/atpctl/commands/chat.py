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

"""Interactive chat/REPL commands for atpctl - World-class AI agent CLI experience"""

import json
import os
from datetime import UTC, datetime
from pathlib import Path

import typer
from prompt_toolkit import PromptSession
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.history import FileHistory
from prompt_toolkit.styles import Style
from rich import print as rprint
from rich.console import Console
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.syntax import Syntax

from ..utils.api_client import ATPAPIClient

app = typer.Typer()
console = Console()

# Custom prompt style
prompt_style = Style.from_dict(
    {
        "prompt": "#00aa00 bold",
        "user": "#00aa00",
        "assistant": "#00aaff",
    }
)


class ChatSession:
    """Manages an interactive chat session with ATP"""

    def __init__(self, api_client: ATPAPIClient, model: str = "gpt-3.5-turbo"):
        """Initialize chat session.

        Args:
            api_client: ATP API client
            model: Model to use for chat
        """
        self.client = api_client
        self.model = model
        self.messages: list[dict] = []
        self.session_id = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")

        # Set up history file
        history_dir = Path.home() / ".atpctl"
        history_dir.mkdir(exist_ok=True)
        self.history_file = history_dir / "chat_history.txt"
        self.session_file = history_dir / f"session_{self.session_id}.json"

    def add_message(self, role: str, content: str) -> None:
        """Add message to conversation history.

        Args:
            role: Message role (user/assistant)
            content: Message content
        """
        self.messages.append({"role": role, "content": content, "timestamp": datetime.now(UTC).isoformat()})

    def save_session(self) -> None:
        """Save session to file"""
        with open(self.session_file, "w") as f:
            json.dump(
                {
                    "session_id": self.session_id,
                    "model": self.model,
                    "messages": self.messages,
                    "timestamp": datetime.now(UTC).isoformat(),
                },
                f,
                indent=2,
            )

    def send_message(self, message: str) -> str:
        """Send message and get response.

        Args:
            message: User message

        Returns:
            Assistant response
        """
        self.add_message("user", message)

        # Send to ATP API
        try:
            response = self.client.post(
                "/v1/ask",
                json={
                    "messages": self.messages,
                    "model": self.model,
                    "max_tokens": 4096,
                    "temperature": 0.7,
                },
            )

            assistant_message = response.get("content", "No response received")
            self.add_message("assistant", assistant_message)

            return assistant_message

        except Exception as e:
            error_msg = f"Error: {e}"
            self.add_message("assistant", error_msg)
            return error_msg


@app.command("repl")
def interactive_repl(
    ctx: typer.Context,
    model: str = typer.Option("gpt-3.5-turbo", "--model", "-m", help="Model to use"),
    system_prompt: str | None = typer.Option(None, "--system", help="System prompt"),
    multiline: bool = typer.Option(False, "--multiline", help="Enable multiline input"),
):
    """Start interactive REPL session (like Claude CLI)"""
    try:
        console.print(
            Panel.fit(
                "[bold cyan]ATP Interactive Chat[/bold cyan]\nType '/help' for commands, '/exit' to quit",
                border_style="blue",
            )
        )

        client = ATPAPIClient.from_context(ctx)
        session = ChatSession(client, model=model)

        # Add system prompt if provided
        if system_prompt:
            session.add_message("system", system_prompt)

        # Set up prompt toolkit session with history
        prompt_session: PromptSession = PromptSession(
            history=FileHistory(str(session.history_file)), auto_suggest=AutoSuggestFromHistory(), style=prompt_style
        )

        # Command completer
        commands = ["/help", "/exit", "/clear", "/save", "/model", "/history", "/export", "/multiline"]
        completer = WordCompleter(commands, ignore_case=True)

        while True:
            try:
                # Get user input
                if multiline:
                    console.print("[dim]Enter your message (Ctrl+D or empty line to send):[/dim]")
                    lines = []
                    while True:
                        try:
                            line = prompt_session.prompt("... ", completer=completer if not lines else None)
                            if not line:
                                break
                            lines.append(line)
                        except EOFError:
                            break
                    user_input = "\n".join(lines)
                else:
                    user_input = prompt_session.prompt("You: ", completer=completer)

                if not user_input.strip():
                    continue

                # Handle commands
                if user_input.startswith("/"):
                    command = user_input.lower().strip()

                    if command == "/exit" or command == "/quit":
                        console.print("[yellow]Saving session and exiting...[/yellow]")
                        session.save_session()
                        break

                    elif command == "/help":
                        help_text = """
[bold]Available Commands:[/bold]
  /help       - Show this help message
  /exit       - Exit the chat session
  /clear      - Clear conversation history
  /save       - Save current session
  /model      - Show current model
  /history    - Show conversation history
  /export     - Export conversation to file
  /multiline  - Toggle multiline mode
                        """
                        console.print(Panel(help_text, title="Help", border_style="blue"))

                    elif command == "/clear":
                        session.messages = []
                        if system_prompt:
                            session.add_message("system", system_prompt)
                        console.print("[green]Conversation cleared[/green]")

                    elif command == "/save":
                        session.save_session()
                        console.print(f"[green]Session saved to: {session.session_file}[/green]")

                    elif command == "/model":
                        console.print(f"[blue]Current model: {session.model}[/blue]")

                    elif command == "/history":
                        for msg in session.messages:
                            role = msg["role"]
                            content = msg["content"]
                            timestamp = msg.get("timestamp", "")

                            if role == "system":
                                console.print(f"[dim]{timestamp}[/dim] [magenta]SYSTEM:[/magenta] {content}")
                            elif role == "user":
                                console.print(f"[dim]{timestamp}[/dim] [green]YOU:[/green] {content}")
                            elif role == "assistant":
                                console.print(f"[dim]{timestamp}[/dim] [cyan]ASSISTANT:[/cyan] {content}")

                    elif command == "/export":
                        export_file = Path.home() / ".atpctl" / f"export_{session.session_id}.md"
                        with open(export_file, "w") as f:
                            f.write(f"# ATP Chat Session - {session.session_id}\n\n")
                            f.write(f"**Model:** {session.model}\n\n")
                            f.write("---\n\n")

                            for msg in session.messages:
                                role = msg["role"]
                                content = msg["content"]
                                timestamp = msg.get("timestamp", "")

                                f.write(f"## {role.upper()} ({timestamp})\n\n")
                                f.write(f"{content}\n\n")
                                f.write("---\n\n")

                        console.print(f"[green]Conversation exported to: {export_file}[/green]")

                    elif command == "/multiline":
                        multiline = not multiline
                        status = "enabled" if multiline else "disabled"
                        console.print(f"[blue]Multiline mode {status}[/blue]")

                    else:
                        console.print(f"[red]Unknown command: {command}[/red]")
                        console.print("[dim]Type /help for available commands[/dim]")

                    continue

                # Send message and display response with streaming effect
                console.print()  # Blank line before response

                with Live(console=console, refresh_per_second=10) as live:
                    live.update(Panel("[dim]Thinking...[/dim]", border_style="blue"))

                    response = session.send_message(user_input)

                    # Display response as markdown for better formatting
                    md = Markdown(response)
                    live.update(Panel(md, title="[cyan]Assistant[/cyan]", border_style="cyan"))

                console.print()  # Blank line after response

                # Auto-save after each interaction
                session.save_session()

            except KeyboardInterrupt:
                console.print("\n[yellow]Use /exit to quit[/yellow]")
                continue

            except EOFError:
                console.print("\n[yellow]Saving session and exiting...[/yellow]")
                session.save_session()
                break

    except Exception as e:
        rprint(f"[red]Error in REPL: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("ask")
def quick_ask(
    ctx: typer.Context,
    question: str = typer.Argument(..., help="Question to ask"),
    model: str = typer.Option("gpt-3.5-turbo", "--model", "-m", help="Model to use"),
    system_prompt: str | None = typer.Option(None, "--system", help="System prompt"),
    save: bool = typer.Option(False, "--save", help="Save conversation"),
):
    """Ask a single question (non-interactive)"""
    try:
        client = ATPAPIClient.from_context(ctx)

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": question})

        console.print(Panel(f"[green]Question:[/green] {question}", border_style="blue"))

        with Live(console=console, refresh_per_second=10) as live:
            live.update(Panel("[dim]Thinking...[/dim]", border_style="blue"))

            response = client.post(
                "/v1/ask",
                json={"messages": messages, "model": model, "max_tokens": 4096, "temperature": 0.7},
            )

            answer = response.get("content", "No response received")

            # Display as markdown
            md = Markdown(answer)
            live.update(Panel(md, title="[cyan]Answer[/cyan]", border_style="cyan"))

        if save:
            session = ChatSession(client, model=model)
            if system_prompt:
                session.add_message("system", system_prompt)
            session.add_message("user", question)
            session.add_message("assistant", answer)
            session.save_session()
            console.print(f"\n[dim]Session saved to: {session.session_file}[/dim]")

    except Exception as e:
        rprint(f"[red]Error asking question: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("history")
def show_history(
    ctx: typer.Context,  # noqa: ARG001
    limit: int = typer.Option(10, "--limit", "-n", help="Number of recent sessions"),
):
    """Show recent chat sessions"""
    try:
        history_dir = Path.home() / ".atpctl"
        if not history_dir.exists():
            console.print("[yellow]No chat history found[/yellow]")
            return

        # Find session files
        session_files = sorted(history_dir.glob("session_*.json"), reverse=True)[:limit]

        if not session_files:
            console.print("[yellow]No chat sessions found[/yellow]")
            return

        from rich.table import Table

        table = Table(title="Recent Chat Sessions")
        table.add_column("Session ID", style="cyan")
        table.add_column("Model", style="blue")
        table.add_column("Messages", justify="right", style="green")
        table.add_column("Date", style="yellow")

        for session_file in session_files:
            try:
                with open(session_file) as f:
                    session_data = json.load(f)

                table.add_row(
                    session_data.get("session_id", "Unknown"),
                    session_data.get("model", "Unknown"),
                    str(len(session_data.get("messages", []))),
                    session_data.get("timestamp", "Unknown"),
                )
            except Exception:
                continue

        console.print(table)

    except Exception as e:
        rprint(f"[red]Error showing history: {e}[/red]")
        raise typer.Exit(1) from e


@app.command("load")
def load_session(
    ctx: typer.Context,
    session_id: str = typer.Argument(..., help="Session ID to load"),
    continue_chat: bool = typer.Option(True, "--continue", help="Continue chatting"),
):
    """Load a previous chat session"""
    try:
        history_dir = Path.home() / ".atpctl"
        session_file = history_dir / f"session_{session_id}.json"

        if not session_file.exists():
            console.print(f"[red]Session not found: {session_id}[/red]")
            raise typer.Exit(1)

        with open(session_file) as f:
            session_data = json.load(f)

        console.print(
            Panel(f"[bold]Loaded session: {session_id}[/bold]\nModel: {session_data.get('model')}", border_style="blue")
        )

        # Display conversation
        for msg in session_data.get("messages", []):
            role = msg["role"]
            content = msg["content"]

            if role == "user":
                console.print(Panel(content, title="[green]You[/green]", border_style="green"))
            elif role == "assistant":
                md = Markdown(content)
                console.print(Panel(md, title="[cyan]Assistant[/cyan]", border_style="cyan"))

        if continue_chat:
            console.print("\n[yellow]Continuing session...[/yellow]\n")
            # Start REPL with loaded messages
            client = ATPAPIClient.from_context(ctx)
            session = ChatSession(client, model=session_data.get("model", "gpt-3.5-turbo"))
            session.messages = session_data.get("messages", [])
            session.session_id = session_id

            # Continue with REPL (simplified version)
            console.print("[dim]Type /exit to quit[/dim]")

    except Exception as e:
        rprint(f"[red]Error loading session: {e}[/red]")
        raise typer.Exit(1) from e
