# scripts/cli.py

import sys, os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from rich.console import Console
from rich.panel import Panel
from rich.prompt import Prompt
from rich.markdown import Markdown
from rich.progress import track

from src.synthesis.response_generator import ResponseGenerator

console = Console()

def main():
    console.print(Panel.fit(
        "[bold cyan]🩺 Personal Medical Assistant[/bold cyan]\n"
        "[dim]AI-powered • High accuracy • CLI Mode[/dim]",
        title="Welcome"
    ))

    assistant = ResponseGenerator()   # Only creates profile (lazy everything else)

    console.print("[green]✓ Ready! Type your symptoms or health question.[/green]")
    console.print("Type [bold]exit[/bold] or [bold]quit[/bold] to stop.\n")

    while True:
        try:
            user_input = Prompt.ask("[bold][yellow]You[/yellow][/bold]").strip()
            
            if user_input.lower() in ["exit", "quit", "bye"]:
                console.print("[cyan]👋 Goodbye! Stay healthy.[/cyan]")
                break

            if not user_input:
                continue

            response = assistant.generate(user_input)
            console.print(Panel(Markdown(response), title="🩺 Assistant", border_style="green", padding=(1, 2)))

        except KeyboardInterrupt:
            console.print("\n[yellow]Session ended.[/yellow]")
            break
        except Exception as e:
            console.print(f"[red]Critical error: {e}[/red]")

if __name__ == "__main__":
    main()