"""File GitHub issues for diagnosed product bugs."""

from __future__ import annotations

import subprocess
from ..models import Diagnosis, Classification, Confidence


def file_github_issue(
    diagnosis: Diagnosis,
    repo: str | None = None,
) -> str | None:
    """File a GitHub issue for a diagnosed product bug.

    Only files issues for product_bug classifications with medium+ confidence.
    Uses the `gh` CLI — requires GitHub CLI to be installed and authenticated.

    Args:
        diagnosis: The diagnosis to create an issue for.
        repo: Optional repo in "owner/repo" format. Defaults to current repo.

    Returns:
        URL of the created issue, or None if skipped/failed.
    """
    # Gate: only file for product bugs with sufficient confidence
    if diagnosis.classification != Classification.PRODUCT_BUG:
        return None
    if diagnosis.confidence == Confidence.LOW:
        return None

    title = f"[{diagnosis.severity.value}] {diagnosis.test_name}: {diagnosis.probable_cause[:80]}"

    body_lines = [
        "## AI-Diagnosed Product Bug",
        "",
        f"**Test**: `{diagnosis.test_name}`",
        f"**Severity**: {diagnosis.severity.value}",
        f"**Confidence**: {diagnosis.confidence.value}",
        "",
        "## Probable Cause",
        diagnosis.probable_cause,
        "",
        "## Evidence",
        diagnosis.evidence_summary,
        "",
        "## Differential Diagnosis",
    ]

    for h in diagnosis.hypotheses:
        body_lines.append(f"### {h.classification.value}")
        if h.evidence_for:
            body_lines.append("**FOR**: " + "; ".join(h.evidence_for))
        if h.evidence_against:
            body_lines.append("**AGAINST**: " + "; ".join(h.evidence_against))
        body_lines.append("")

    body_lines.extend([
        "## Recommended Action",
        diagnosis.recommended_action,
        "",
        "---",
        "*Filed automatically by [AI Test Generator](https://github.com/vazidmansuri005/ai-test-generator). "
        "AI-assessed — verify before acting.*",
    ])

    body = "\n".join(body_lines)

    severity_labels = {
        "P0": "priority:critical",
        "P1": "priority:high",
        "P2": "priority:medium",
        "P3": "priority:low",
    }
    label = severity_labels.get(diagnosis.severity.value, "bug")

    cmd = ["gh", "issue", "create", "--title", title, "--body", body, "--label", f"bug,{label}"]
    if repo:
        cmd.extend(["--repo", repo])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            return result.stdout.strip()
        return None
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return None
