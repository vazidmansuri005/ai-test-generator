"""CLI interface for AI Test Generator."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

from .generator import TestGenerator
from .models import TestSuite

console = Console()


def _load_input(source: str) -> str:
    """Load feature description from file path or treat as inline text."""
    path = Path(source)
    if path.exists() and path.is_file():
        return path.read_text().strip()
    return source


@click.group()
@click.version_option()
def main():
    """AI Test Generator — from user stories to executable tests."""
    pass


@main.command()
@click.argument("feature")
@click.option("--context", "-c", help="Additional context (file path or inline text)")
@click.option("--output", "-o", help="Save JSON output to file")
@click.option("--model", "-m", default="claude-sonnet-4-20250514", help="Claude model to use")
def generate(feature: str, context: str | None, output: str | None, model: str):
    """Generate test cases from a feature description.

    FEATURE can be inline text or a path to a .md/.txt file.

    Examples:

        ai-test-gen generate "User login with email and password"

        ai-test-gen generate requirements.md --output tests.json

        ai-test-gen generate "Shopping cart checkout" --context "REST API, no guest checkout"
    """
    feature_text = _load_input(feature)
    context_text = _load_input(context) if context else None

    console.print(Panel(f"[bold]Feature:[/bold] {feature_text[:100]}...", title="AI Test Generator"))

    with console.status("[bold green]Generating test cases with Claude..."):
        gen = TestGenerator(model=model)
        suite = gen.generate_test_cases(feature_text, context_text)

    _display_suite(suite)

    if output:
        Path(output).write_text(suite.model_dump_json(indent=2))
        console.print(f"\n[green]Saved to {output}[/green]")


@main.command()
@click.argument("suite_file", type=click.Path(exists=True))
@click.option(
    "--framework",
    "-f",
    type=click.Choice(["pytest", "playwright"]),
    default="pytest",
    help="Target test framework",
)
@click.option("--output", "-o", help="Save generated code to file")
@click.option("--model", "-m", default="claude-sonnet-4-20250514", help="Claude model to use")
def code(suite_file: str, framework: str, output: str | None, model: str):
    """Generate executable test code from a test suite JSON file.

    Examples:

        ai-test-gen code tests.json --framework pytest

        ai-test-gen code tests.json --framework playwright --output test_login.py
    """
    suite_data = json.loads(Path(suite_file).read_text())
    suite = TestSuite.model_validate(suite_data)

    console.print(Panel(
        f"[bold]Suite:[/bold] {suite.feature} ({len(suite.test_cases)} tests)\n"
        f"[bold]Framework:[/bold] {framework}",
        title="Code Generator",
    ))

    with console.status(f"[bold green]Generating {framework} code with Claude..."):
        gen = TestGenerator(model=model)
        result = gen.generate_code(suite, framework)

    console.print(f"\n[bold]File:[/bold] {result.filename}")
    console.print(f"[bold]Dependencies:[/bold] {', '.join(result.dependencies)}\n")
    console.print(Syntax(result.code, "python", theme="monokai", line_numbers=True))

    if output:
        Path(output).write_text(result.code)
        console.print(f"\n[green]Saved to {output}[/green]")


@main.command(name="one-shot")
@click.argument("feature")
@click.option("--context", "-c", help="Additional context")
@click.option(
    "--framework",
    "-f",
    type=click.Choice(["pytest", "playwright"]),
    default="pytest",
)
@click.option("--output-dir", "-d", default=".", help="Directory for output files")
@click.option("--model", "-m", default="claude-sonnet-4-20250514", help="Claude model to use")
def one_shot(feature: str, context: str | None, framework: str, output_dir: str, model: str):
    """Generate test cases AND code in one command.

    Examples:

        ai-test-gen one-shot "User registration flow" --framework pytest

        ai-test-gen one-shot requirements.md -f playwright -d ./tests
    """
    feature_text = _load_input(feature)
    context_text = _load_input(context) if context else None
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    gen = TestGenerator(model=model)

    with console.status("[bold green]Step 1/2: Generating test cases..."):
        suite = gen.generate_test_cases(feature_text, context_text)

    _display_suite(suite)

    suite_path = out / "test_suite.json"
    suite_path.write_text(suite.model_dump_json(indent=2))
    console.print(f"[green]Test suite saved to {suite_path}[/green]\n")

    with console.status(f"[bold green]Step 2/2: Generating {framework} code..."):
        result = gen.generate_code(suite, framework)

    code_path = out / result.filename
    code_path.write_text(result.code)
    console.print(Syntax(result.code, "python", theme="monokai", line_numbers=True))
    console.print(f"\n[green]Test code saved to {code_path}[/green]")
    console.print(f"[bold]Install deps:[/bold] pip install {' '.join(result.dependencies)}")


def _display_suite(suite: TestSuite):
    """Pretty-print a test suite to the console."""
    console.print(f"\n[bold green]Generated {len(suite.test_cases)} test cases[/bold green]")
    console.print(f"[dim]{suite.summary}[/dim]\n")

    table = Table(title=suite.feature, show_lines=True)
    table.add_column("ID", style="cyan", width=8)
    table.add_column("Title", style="white", min_width=30)
    table.add_column("Type", style="yellow", width=12)
    table.add_column("Priority", width=10)
    table.add_column("Steps", justify="center", width=6)

    priority_colors = {
        "critical": "bold red",
        "high": "red",
        "medium": "yellow",
        "low": "green",
    }

    for tc in suite.test_cases:
        color = priority_colors.get(tc.priority.value, "white")
        table.add_row(
            tc.id,
            tc.title,
            tc.type.value,
            f"[{color}]{tc.priority.value}[/{color}]",
            str(len(tc.steps)),
        )

    console.print(table)
    console.print(f"\n[dim]Coverage: {suite.coverage_notes}[/dim]")
