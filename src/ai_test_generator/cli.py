"""CLI interface for AI Test Generator — all three layers."""

from __future__ import annotations

import json
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.syntax import Syntax

from .generator import TestGenerator
from .diagnoser import FailureDiagnoser
from .orchestrator import Orchestrator
from .memory import FailureMemory
from .impact import ImpactAnalyzer
from .models import TestSuite, DiagnosisReport, Classification, Confidence, RiskLevel
from .parsers import parse_pytest_json, parse_junit_xml
from .reporters.markdown_reporter import generate_markdown_report, save_report

console = Console()

_CLASS_ICON = {
    Classification.PRODUCT_BUG: "🐛",
    Classification.INFRA_ISSUE: "🔧",
    Classification.TEST_ISSUE: "🧪",
    Classification.UNKNOWN: "❓",
}

_CONF_ICON = {
    Confidence.HIGH: "🟢",
    Confidence.MEDIUM: "🟡",
    Confidence.LOW: "🔴",
}


def _load_input(source: str) -> str:
    """Load feature description from file path or treat as inline text."""
    path = Path(source)
    if path.exists() and path.is_file():
        return path.read_text().strip()
    return source


@click.group()
@click.version_option()
def main():
    """AI Test Generator — Agentic QA in three layers.

    Layer 1: Generate test cases and code from user stories.
    Layer 2: Diagnose test failures with differential diagnosis.
    Layer 3: Orchestrate the full pipeline autonomously.
    """
    pass


# ---------------------------------------------------------------------------
# Layer 1 commands
# ---------------------------------------------------------------------------


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
    """
    feature_text = _load_input(feature)
    context_text = _load_input(context) if context else None

    console.print(Panel(f"[bold]Feature:[/bold] {feature_text[:100]}...", title="🧪 Layer 1: Test Generation"))

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
    "--framework", "-f",
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
        title="🧪 Layer 1: Code Generation",
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
    "--framework", "-f",
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


# ---------------------------------------------------------------------------
# Layer 2 commands
# ---------------------------------------------------------------------------


@main.command()
@click.argument("results_file", type=click.Path(exists=True))
@click.option("--format", "-f", "fmt", type=click.Choice(["pytest-json", "junit-xml"]),
              default="pytest-json", help="Results file format")
@click.option("--output", "-o", help="Save markdown report to file")
@click.option("--no-memory", is_flag=True, help="Disable failure memory for this run")
@click.option("--model", "-m", default="claude-sonnet-4-20250514", help="Claude model to use")
def diagnose(results_file: str, fmt: str, output: str | None, no_memory: bool, model: str):
    """Diagnose test failures from a results file.

    Performs differential diagnosis — evaluates whether each failure is a
    test issue, infrastructure issue, or actual product bug.

    Uses failure memory by default: past corrections improve future diagnoses.

    Examples:

        ai-test-gen diagnose report.json

        ai-test-gen diagnose results.xml --format junit-xml --output triage.md
    """
    memory = None if no_memory else FailureMemory()

    console.print(Panel(
        f"[bold]Results:[/bold] {results_file}\n[bold]Format:[/bold] {fmt}\n"
        f"[bold]Memory:[/bold] {'disabled' if no_memory else f'{memory.correction_count} corrections loaded'}",
        title="🔍 Layer 2: Failure Diagnosis",
    ))

    # Parse results
    if fmt == "junit-xml":
        passed, failed, skipped, failures = parse_junit_xml(results_file)
    else:
        passed, failed, skipped, failures = parse_pytest_json(results_file)

    console.print(f"Parsed: {passed} passed, {failed} failed, {skipped} skipped")

    if not failures:
        console.print("[bold green]No failures found — nothing to diagnose.[/bold green]")
        return

    with console.status(f"[bold green]Diagnosing {len(failures)} failures with Claude..."):
        diagnoser = FailureDiagnoser(model=model, memory=memory)
        report = diagnoser.diagnose(passed, failed, skipped, failures)

    _display_diagnosis(report)

    if output:
        save_report(report, output)
        console.print(f"\n[green]Report saved to {output}[/green]")


# ---------------------------------------------------------------------------
# Layer 3 commands
# ---------------------------------------------------------------------------


@main.command()
@click.argument("feature")
@click.option("--context", "-c", help="Additional context")
@click.option("--framework", "-f", type=click.Choice(["pytest", "playwright"]),
              default="pytest")
@click.option("--output-dir", "-d", default="./agentic_output", help="Output directory")
@click.option("--auto-issue/--no-auto-issue", default=False,
              help="Auto-file GitHub issues for product bugs")
@click.option("--github-repo", help="GitHub repo for issues (owner/repo)")
@click.option("--model", "-m", default="claude-sonnet-4-20250514", help="Claude model to use")
def pipeline(
    feature: str, context: str | None, framework: str,
    output_dir: str, auto_issue: bool, github_repo: str | None, model: str,
):
    """Run the full agentic QA pipeline.

    Generates tests, executes them, diagnoses failures, and produces
    a triage report — all autonomously.

    Examples:

        ai-test-gen pipeline "User login with email and password"

        ai-test-gen pipeline requirements.md --auto-issue --github-repo myuser/myrepo
    """
    console.print(Panel(
        "[bold]Agentic QA Pipeline[/bold]\n\n"
        "Layer 1: Generate → Layer 2: Execute & Diagnose → Layer 3: Report",
        title="🤖 Full Pipeline",
    ))

    orch = Orchestrator(model=model, output_dir=output_dir)

    with console.status("[bold green]Running agentic QA pipeline..."):
        result = orch.run(
            feature=feature,
            context=context,
            framework=framework,
            auto_file_issues=auto_issue,
            github_repo=github_repo,
        )

    # Display results for each completed stage
    console.print(f"\n[bold]Stages completed:[/bold] {' → '.join(s.value for s in result.stages_completed)}")

    if result.test_suite:
        _display_suite(result.test_suite)

    if result.code_output:
        console.print(f"\n[bold]Generated:[/bold] {result.code_output.filename}")

    if result.diagnosis:
        _display_diagnosis(result.diagnosis)

    if result.report_path:
        console.print(f"\n[green]Triage report: {result.report_path}[/green]")

    if result.github_issue_url:
        console.print(f"[green]GitHub issue: {result.github_issue_url}[/green]")


# ---------------------------------------------------------------------------
# Display helpers
# ---------------------------------------------------------------------------


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


def _display_diagnosis(report: DiagnosisReport):
    """Pretty-print a diagnosis report to the console."""
    console.print(f"\n[bold]Diagnosis: {report.failed} failures analyzed[/bold]")
    console.print(f"[dim]{report.summary}[/dim]\n")

    if not report.failures:
        return

    table = Table(title="Failure Triage", show_lines=True)
    table.add_column("Test", style="white", min_width=30, max_width=50)
    table.add_column("Classification", width=16)
    table.add_column("Confidence", width=12)
    table.add_column("Severity", width=10)
    table.add_column("Probable Cause", min_width=30)

    severity_colors = {"P0": "bold red", "P1": "red", "P2": "yellow", "P3": "green"}

    for d in report.failures:
        cls_icon = _CLASS_ICON.get(d.classification, "")
        conf_icon = _CONF_ICON.get(d.confidence, "")
        sev_color = severity_colors.get(d.severity.value, "white")
        table.add_row(
            d.test_name[:50],
            f"{cls_icon} {d.classification.value}",
            f"{conf_icon} {d.confidence.value}",
            f"[{sev_color}]{d.severity.value}[/{sev_color}]",
            d.probable_cause[:60] + "..." if len(d.probable_cause) > 60 else d.probable_cause,
        )

    console.print(table)


def _display_impact(report):
    """Pretty-print an impact report to the console."""
    console.print(f"\n[bold]{report.total_tests_at_risk} tests at risk[/bold] from {report.total_files_changed} changed files")
    console.print(f"[dim]{report.summary}[/dim]\n")

    if not (report.high_risk or report.medium_risk or report.low_risk):
        console.print("[bold green]No test impact detected.[/bold green]")
        return

    table = Table(title="Test Impact Prediction", show_lines=True)
    table.add_column("Risk", width=8)
    table.add_column("Test", style="white", min_width=25, max_width=45)
    table.add_column("Changed File", style="cyan", min_width=20, max_width=35)
    table.add_column("Reason", min_width=30)

    risk_styles = {
        RiskLevel.HIGH: ("🔴", "bold red"),
        RiskLevel.MEDIUM: ("🟡", "yellow"),
        RiskLevel.LOW: ("🟢", "green"),
    }

    for impacts, level in [
        (report.high_risk, RiskLevel.HIGH),
        (report.medium_risk, RiskLevel.MEDIUM),
        (report.low_risk, RiskLevel.LOW),
    ]:
        icon, color = risk_styles[level]
        for t in impacts:
            name = t.test_name if t.test_name else t.test_file
            table.add_row(
                f"[{color}]{icon} {level.value}[/{color}]",
                name[:45],
                t.changed_file[:35],
                t.reason[:80] + "..." if len(t.reason) > 80 else t.reason,
            )

    console.print(table)
    console.print(f"\n[bold]Recommendation:[/bold] {report.recommendation}")


# ---------------------------------------------------------------------------
# Failure Memory commands
# ---------------------------------------------------------------------------


@main.command()
@click.argument("test_name")
@click.option("--correct-to", "-t", required=True,
              type=click.Choice(["test_issue", "infra_issue", "product_bug"]),
              help="What the failure actually was")
@click.option("--reason", "-r", required=True, help="Why this correction is right")
@click.option("--error-pattern", "-e", default="",
              help="Key error text to match in future (auto-extracted if omitted)")
def feedback(test_name: str, correct_to: str, reason: str, error_pattern: str):
    """Correct a diagnosis — the agent learns from your feedback.

    When the AI gets a diagnosis wrong, tell it. The correction is stored
    and used to improve future diagnoses on similar failures.

    Examples:

        ai-test-gen feedback "test_checkout::test_payment" \\
            --correct-to test_issue \\
            --reason "Stale CSS selector, not a network issue" \\
            --error-pattern "TimeoutError: wait_for_selector"

        ai-test-gen feedback "test_login::test_lockout" \\
            --correct-to product_bug \\
            --reason "Auth service regression, lockout counter broken"
    """
    memory = FailureMemory()
    corrected = Classification(correct_to)

    # If no error pattern provided, use test name as pattern
    if not error_pattern:
        error_pattern = test_name

    correction = memory.record_correction(
        test_name=test_name,
        original=Classification.UNKNOWN,  # We don't know the original from CLI
        corrected=corrected,
        reason=reason,
        error_pattern=error_pattern,
    )

    console.print(Panel(
        f"[bold]Test:[/bold] {test_name}\n"
        f"[bold]Corrected to:[/bold] {correct_to}\n"
        f"[bold]Reason:[/bold] {reason}\n"
        f"[bold]Pattern:[/bold] {error_pattern[:80]}",
        title="🧠 Correction Recorded",
    ))
    console.print(f"[green]Memory now has {memory.correction_count} corrections.[/green]")
    console.print("[dim]Future diagnoses with similar error patterns will use this feedback.[/dim]")


@main.command(name="memory")
def memory_status():
    """Show failure memory status and stored corrections.

    Examples:

        ai-test-gen memory
    """
    memory = FailureMemory()
    stats = memory.get_stats()

    console.print(Panel(
        f"[bold]Corrections stored:[/bold] {memory.correction_count}\n"
        f"[bold]Memory location:[/bold] {memory.memory_dir}",
        title="🧠 Failure Memory",
    ))

    if not memory.corrections:
        console.print("[dim]No corrections recorded yet. Use 'ai-test-gen feedback' to teach the agent.[/dim]")
        return

    # Show pattern counts
    pattern_counts = stats.get("pattern_counts", {})
    if pattern_counts:
        console.print("\n[bold]Correction patterns:[/bold]")
        for pattern, count in sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True):
            console.print(f"  {pattern}: {count}x")

    # Show recent corrections
    table = Table(title="Stored Corrections", show_lines=True)
    table.add_column("Test", style="cyan", max_width=35)
    table.add_column("Was", width=14)
    table.add_column("Actually", width=14)
    table.add_column("Reason", min_width=25)
    table.add_column("When", width=12)

    for c in memory.corrections[-10:]:  # Last 10
        table.add_row(
            c.test_name[:35],
            c.original_classification.value,
            c.corrected_classification.value,
            c.reason[:40] + "..." if len(c.reason) > 40 else c.reason,
            c.timestamp[:10],
        )

    console.print(table)


# ---------------------------------------------------------------------------
# PR Impact Analysis commands
# ---------------------------------------------------------------------------


@main.command()
@click.option("--diff", "-d", "diff_target", default="HEAD~1",
              help="Git diff target (commit, branch, or SHA)")
@click.option("--repo", "-r", "repo_path", default=".",
              help="Path to the git repository")
@click.option("--test-dir", "-t", default="tests",
              help="Directory containing test files")
@click.option("--model", "-m", default="claude-sonnet-4-20250514", help="Claude model to use")
def impact(diff_target: str, repo_path: str, test_dir: str, model: str):
    """Predict which tests will break from code changes.

    Analyzes a git diff semantically — not just file matching, but
    understanding what changed and which test behaviors are affected.

    Examples:

        ai-test-gen impact

        ai-test-gen impact --diff main

        ai-test-gen impact --diff abc123 --repo /path/to/project --test-dir spec
    """
    console.print(Panel(
        f"[bold]Diff target:[/bold] {diff_target}\n"
        f"[bold]Repo:[/bold] {repo_path}\n"
        f"[bold]Test dir:[/bold] {test_dir}",
        title="🎯 PR Impact Analysis",
    ))

    analyzer = ImpactAnalyzer(model=model)

    with console.status("[bold green]Analyzing code changes and predicting test impact..."):
        report = analyzer.analyze_diff(
            repo_path=repo_path,
            diff_target=diff_target,
            test_dir=test_dir,
        )

    _display_impact(report)
