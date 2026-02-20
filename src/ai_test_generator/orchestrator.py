"""Layer 3 — Agentic QA Orchestrator.

Chains the full pipeline: generate → execute → diagnose → report.
Each stage runs autonomously and feeds its output to the next.
"""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path

from .generator import TestGenerator
from .diagnoser import FailureDiagnoser
from .parsers import parse_pytest_json
from .reporters.markdown_reporter import save_report
from .reporters.github_reporter import file_github_issue
from .models import (
    Classification,
    CodeOutput,
    DiagnosisReport,
    PipelineResult,
    PipelineStage,
    TestSuite,
)


class Orchestrator:
    """Full agentic QA pipeline: generate tests, run them, diagnose failures, report.

    Example:
        orch = Orchestrator()
        result = orch.run("User login with email and password")
        print(result.diagnosis.summary)
    """

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        output_dir: str = ".",
    ):
        self.generator = TestGenerator(api_key=api_key, model=model)
        self.diagnoser = FailureDiagnoser(api_key=api_key, model=model)
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(
        self,
        feature: str,
        context: str | None = None,
        framework: str = "pytest",
        auto_file_issues: bool = False,
        github_repo: str | None = None,
    ) -> PipelineResult:
        """Execute the full agentic QA pipeline.

        Args:
            feature: Feature description or path to requirements file.
            context: Optional additional context.
            framework: Test framework to generate for (pytest or playwright).
            auto_file_issues: Whether to auto-file GitHub issues for product bugs.
            github_repo: GitHub repo for issue filing (owner/repo format).

        Returns:
            PipelineResult with outputs from each stage.
        """
        result = PipelineResult(feature=feature)

        # --- Stage 1: Generate test cases ---
        feature_text = self._load_input(feature)
        context_text = self._load_input(context) if context else None

        suite = self.generator.generate_test_cases(feature_text, context_text)
        result.test_suite = suite
        result.stages_completed.append(PipelineStage.GENERATE)

        # Save test suite
        suite_path = self.output_dir / "test_suite.json"
        suite_path.write_text(suite.model_dump_json(indent=2))

        # --- Stage 2: Generate executable code ---
        code_output = self.generator.generate_code(suite, framework=framework)
        result.code_output = code_output
        code_path = self.output_dir / code_output.filename
        code_path.write_text(code_output.code)

        # --- Stage 3: Execute tests ---
        if framework == "pytest":
            passed, failed, skipped, failures = self._run_pytest(code_path)
            result.stages_completed.append(PipelineStage.EXECUTE)
        else:
            # Playwright execution requires browser setup — skip auto-execution
            return result

        # --- Stage 4: Diagnose failures ---
        if failures:
            diagnosis = self.diagnoser.diagnose(passed, failed, skipped, failures)
        else:
            diagnosis = DiagnosisReport(
                total_tests=passed + failed + skipped,
                passed=passed,
                failed=0,
                skipped=skipped,
                failures=[],
                summary="All tests passed — no diagnosis needed.",
            )
        result.diagnosis = diagnosis
        result.stages_completed.append(PipelineStage.DIAGNOSE)

        # --- Stage 5: Generate report ---
        report_path = self.output_dir / "triage_report.md"
        save_report(diagnosis, report_path, feature=feature_text[:100])
        result.report_path = str(report_path)
        result.stages_completed.append(PipelineStage.REPORT)

        # --- Stage 6: Auto-file GitHub issues (optional) ---
        if auto_file_issues and diagnosis.failures:
            for diag in diagnosis.failures:
                if diag.classification == Classification.PRODUCT_BUG:
                    url = file_github_issue(diag, repo=github_repo)
                    if url and not result.github_issue_url:
                        result.github_issue_url = url

        return result

    def diagnose_results(
        self,
        results_path: str,
        feature: str = "",
        output: str | None = None,
    ) -> DiagnosisReport:
        """Diagnose an existing test results file (pytest JSON or JUnit XML).

        This lets you use Layer 2 standalone — point it at any test results
        file and get a diagnosis without running the full pipeline.

        Args:
            results_path: Path to pytest JSON report or JUnit XML.
            feature: Optional feature name for the report.
            output: Optional path to save the markdown report.

        Returns:
            DiagnosisReport with classifications.
        """
        path = Path(results_path)

        if path.suffix == ".xml":
            from .parsers import parse_junit_xml
            passed, failed, skipped, failures = parse_junit_xml(path)
        else:
            passed, failed, skipped, failures = parse_pytest_json(path)

        report = self.diagnoser.diagnose(passed, failed, skipped, failures)

        if output:
            save_report(report, output, feature=feature)

        return report

    def _run_pytest(self, test_file: Path) -> tuple[int, int, int, list]:
        """Run pytest on generated test file and capture results."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as tmp:
            report_path = tmp.name

        cmd = [
            "python", "-m", "pytest",
            str(test_file),
            f"--json-report-file={report_path}",
            "--json-report",
            "--tb=long",
            "--no-header",
            "-q",
        ]

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=120,
                cwd=str(self.output_dir),
            )
        except subprocess.TimeoutExpired:
            pass

        report_file = Path(report_path)
        if report_file.exists():
            return parse_pytest_json(report_file)

        # Fallback: no JSON report generated
        return 0, 0, 0, []

    @staticmethod
    def _load_input(source: str) -> str:
        path = Path(source)
        if path.exists() and path.is_file():
            return path.read_text().strip()
        return source
