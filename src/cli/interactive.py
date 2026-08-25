from __future__ import annotations
import sys
import uuid
from rich.console import Console
from rich.panel import Panel

from src.agent.orchestrator import OrbitMeshOrchestrator
from src.core.models import ActionEnum


def main():
    console = Console()
    orchestrator = OrbitMeshOrchestrator()
    session_id = f"cli-{uuid.uuid4().hex[:6]}"

    console.print(Panel.fit(
        "[bold cyan]OrbitMesh Support Assistant[/bold cyan]\n"
        "[dim]Intelligent, safety-grounded diagnostic CLI for OrbitMesh Wi-Fi systems.[/dim]\n"
        f"[dim]Session ID: {session_id} | Type 'exit' or 'quit' to end session.[/dim]",
        border_style="cyan"
    ))

    while True:
        try:
            user_input = console.input("[bold green]Customer > [/bold green]").strip()
            if not user_input:
                continue
            if user_input.lower() in ["exit", "quit", "bye"]:
                console.print("[dim]Ending session. Thank you for using OrbitMesh Assistant.[/dim]")
                break

            envelope = orchestrator.process_turn(session_id, user_input)

            action_color = {
                ActionEnum.ASK: "yellow",
                ActionEnum.INSTRUCT: "cyan",
                ActionEnum.RESOLVED: "green",
                ActionEnum.ESCALATE: "red",
            }.get(envelope.action, "white")

            citations_text = ""
            if envelope.citations:
                cite_items = [f"• [bold]{c.source_id}[/bold] — [italic]{c.locator}[/italic]" for c in envelope.citations]
                citations_text = "\n\n[dim]Sources:\n" + "\n".join(cite_items) + "[/dim]"

            panel_content = f"{envelope.response}{citations_text}\n\n[bold {action_color}]Action: {envelope.action.value.upper()}[/bold {action_color}]"
            console.print(Panel(panel_content, border_style=action_color, title="[bold]OrbitMesh Assistant[/bold]"))

            if envelope.action in [ActionEnum.RESOLVED, ActionEnum.ESCALATE]:
                console.print(f"[dim]Conversation state: {envelope.action.value}.[/dim]")

        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Session closed.[/dim]")
            break


if __name__ == "__main__":
    main()
