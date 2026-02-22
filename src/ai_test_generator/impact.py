"""PR Impact Analysis — predict which tests break from code changes.

Given a git diff, this agent:
1. Parses the changed files and understands what was modified
2. Scans the test directory for related test files
3. Uses Claude to perform semantic impact analysis — not just
   "file X changed so re-run tests importing X" but actually
   understanding "this change affects the error path, so only
   error-scenario tests are at risk"

This is the feature Microsoft and Google have internally but
nobody has open-sourced.
"""

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

from anthropic import Anthropic

from .models import FileChange, ImpactReport, RiskLevel, TestImpact


IMPACT_SYSTEM = """You are an expert test impact analyst. Given code changes (git diff) and
existing test files, you predict which tests are likely to break and WHY.

Your analysis must be SEMANTIC, not just syntactic:
- Don't just match file names. Understand what the code DOES.
- If a change only affects an error path, only flag tests that test error scenarios.
- If a change is purely cosmetic (logging, comments), flag it as low risk.
- If a change modifies core business logic, flag all tests exercising that logic.

For each impacted test, explain the causal chain:
"File X changed function Y which handles Z, and test T asserts on Z behavior."

Risk levels:
- HIGH: Direct behavior change in code that a test asserts on. Very likely to break.
- MEDIUM: Indirect dependency or edge case that might be affected. Worth running.
- LOW: Tangential change. Unlikely to break but good to verify.

If no tests are at risk, say so clearly. Don't fabricate impact."""


IMPACT_PROMPT = """Analyze the impact of these code changes on the test suite.

## Changed Files
{changes_json}

## Existing Test Files
{tests_json}

Predict which tests are at risk of breaking. Return a JSON object:
{{
  "high_risk": [
    {{
      "test_file": "path/to/test.py",
      "test_name": "specific test function if identifiable, or empty string",
      "risk_level": "high",
      "reason": "WHY this test will likely break — the causal chain",
      "changed_file": "which changed file causes the risk"
    }}
  ],
  "medium_risk": [...],
  "low_risk": [...],
  "summary": "overall impact assessment in 1-2 sentences",
  "recommendation": "what to run and in what order — prioritized test plan"
}}

Return ONLY valid JSON, no markdown fences."""


class ImpactAnalyzer:
    """Predicts test impact from code changes using semantic analysis."""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-20250514"):
        self.client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model

    def analyze_diff(
        self,
        repo_path: str | Path = ".",
        diff_target: str = "HEAD~1",
        test_dir: str = "tests",
    ) -> ImpactReport:
        """Analyze a git diff and predict test impact.

        Args:
            repo_path: Path to the git repository.
            diff_target: Git diff target (e.g., "HEAD~1", "main", a commit SHA).
            test_dir: Directory containing test files.

        Returns:
            ImpactReport with risk-ranked test predictions.
        """
        repo = Path(repo_path).resolve()

        # Get the diff
        changes = self._get_diff(repo, diff_target)
        if not changes:
            return ImpactReport(
                total_files_changed=0,
                total_tests_at_risk=0,
                summary="No changes detected.",
                recommendation="Nothing to test.",
            )

        # Find existing test files and read their content
        test_files = self._scan_test_files(repo, test_dir)

        return self._predict_impact(changes, test_files)

    def analyze_from_text(
        self,
        diff_text: str,
        test_files: dict[str, str],
    ) -> ImpactReport:
        """Analyze impact from raw diff text and test file contents.

        Useful when you don't have a git repo — e.g., analyzing a PR diff
        fetched from GitHub API.

        Args:
            diff_text: Raw git diff output.
            test_files: Dict of {filename: file_content} for test files.

        Returns:
            ImpactReport with risk-ranked predictions.
        """
        changes = self._parse_diff_text(diff_text)
        if not changes:
            return ImpactReport(
                total_files_changed=0,
                total_tests_at_risk=0,
                summary="No changes detected in diff.",
                recommendation="Nothing to test.",
            )

        tests_info = {
            name: {"path": name, "content_preview": content[:2000]}
            for name, content in test_files.items()
        }
        return self._predict_impact(changes, tests_info)

    def _predict_impact(
        self,
        changes: list[FileChange],
        test_files: dict[str, dict],
    ) -> ImpactReport:
        """Use Claude to predict test impact."""
        changes_json = json.dumps([c.model_dump() for c in changes], indent=2)
        tests_json = json.dumps(test_files, indent=2)

        # Truncate if too large
        if len(tests_json) > 15000:
            tests_json = tests_json[:15000] + "\n... [truncated]"
        if len(changes_json) > 10000:
            changes_json = changes_json[:10000] + "\n... [truncated]"

        prompt = IMPACT_PROMPT.format(
            changes_json=changes_json,
            tests_json=tests_json,
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=IMPACT_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        data = json.loads(raw)

        high = [TestImpact.model_validate(t) for t in data.get("high_risk", [])]
        medium = [TestImpact.model_validate(t) for t in data.get("medium_risk", [])]
        low = [TestImpact.model_validate(t) for t in data.get("low_risk", [])]

        return ImpactReport(
            total_files_changed=len(changes),
            total_tests_at_risk=len(high) + len(medium) + len(low),
            high_risk=high,
            medium_risk=medium,
            low_risk=low,
            summary=data.get("summary", ""),
            recommendation=data.get("recommendation", ""),
        )

    def _get_diff(self, repo: Path, diff_target: str) -> list[FileChange]:
        """Get structured diff from git."""
        # Get list of changed files with their status
        cmd_stat = ["git", "diff", "--name-status", diff_target]
        result = subprocess.run(
            cmd_stat, capture_output=True, text=True, cwd=str(repo), timeout=30,
        )
        if result.returncode != 0:
            return []

        changes = []
        for line in result.stdout.strip().splitlines():
            if not line.strip():
                continue
            parts = line.split("\t")
            if len(parts) < 2:
                continue

            status_code = parts[0][0]
            filepath = parts[-1]  # Handle renames (R100\told\tnew)
            change_type = {
                "A": "added", "M": "modified", "D": "deleted", "R": "renamed",
            }.get(status_code, "modified")

            # Get the actual diff for this file
            diff_summary = self._get_file_diff_summary(repo, diff_target, filepath)

            changes.append(FileChange(
                path=filepath,
                change_type=change_type,
                diff_summary=diff_summary,
            ))

        return changes

    def _get_file_diff_summary(self, repo: Path, diff_target: str, filepath: str) -> str:
        """Get a concise diff summary for a single file."""
        cmd = ["git", "diff", diff_target, "--", filepath]
        result = subprocess.run(
            cmd, capture_output=True, text=True, cwd=str(repo), timeout=15,
        )
        diff = result.stdout
        # Truncate very long diffs
        if len(diff) > 3000:
            diff = diff[:1500] + "\n...[truncated]...\n" + diff[-1500:]
        return diff

    def _scan_test_files(self, repo: Path, test_dir: str) -> dict[str, dict]:
        """Find test files and read their content preview."""
        test_path = repo / test_dir
        if not test_path.exists():
            return {}

        test_files = {}
        patterns = ["test_*.py", "*_test.py", "Test*.java", "*.test.ts", "*.test.js", "*.spec.ts"]

        for pattern in patterns:
            for f in test_path.rglob(pattern):
                if f.is_file():
                    try:
                        content = f.read_text()
                        # First 2000 chars gives us imports + function signatures
                        test_files[str(f.relative_to(repo))] = {
                            "path": str(f.relative_to(repo)),
                            "content_preview": content[:2000],
                        }
                    except (OSError, UnicodeDecodeError):
                        continue

        return test_files

    def _parse_diff_text(self, diff_text: str) -> list[FileChange]:
        """Parse raw diff text into FileChange objects."""
        changes = []
        current_file = None
        current_diff_lines: list[str] = []

        for line in diff_text.splitlines():
            if line.startswith("diff --git"):
                # Save previous file
                if current_file:
                    changes.append(FileChange(
                        path=current_file,
                        change_type="modified",
                        diff_summary="\n".join(current_diff_lines[-50:]),
                    ))
                # Extract new file path
                parts = line.split(" b/")
                current_file = parts[-1] if len(parts) > 1 else "unknown"
                current_diff_lines = []
            elif current_file:
                current_diff_lines.append(line)

        # Don't forget the last file
        if current_file:
            changes.append(FileChange(
                path=current_file,
                change_type="modified",
                diff_summary="\n".join(current_diff_lines[-50:]),
            ))

        return changes
