"""Parse pytest-json-report output into FailedTest models."""

from __future__ import annotations

import json
from pathlib import Path

from ..models import FailedTest


def parse_pytest_json(source: str | Path | dict) -> tuple[int, int, int, list[FailedTest]]:
    """Parse pytest JSON report into structured failure data.

    Supports pytest-json-report format (pip install pytest-json-report).

    Args:
        source: File path, JSON string, or already-parsed dict.

    Returns:
        Tuple of (passed, failed, skipped, list[FailedTest]).
    """
    if isinstance(source, dict):
        data = source
    else:
        path = Path(source)
        try:
            if path.exists() and path.is_file():
                data = json.loads(path.read_text())
            else:
                data = json.loads(source)
        except OSError:
            # Path too long to be a filename — treat as JSON string
            data = json.loads(source)

    summary = data.get("summary", {})
    passed = summary.get("passed", 0)
    failed = summary.get("failed", 0)
    skipped = summary.get("skipped", 0)

    failures: list[FailedTest] = []
    for test in data.get("tests", []):
        if test.get("outcome") != "failed":
            continue

        call_info = test.get("call", {})
        failures.append(FailedTest(
            name=test.get("nodeid", "unknown"),
            error_message=call_info.get("longrepr", call_info.get("crash", {}).get("message", "No error message")),
            traceback=call_info.get("longrepr", ""),
            duration=call_info.get("duration", 0.0),
            stdout=test.get("setup", {}).get("stdout", "") + test.get("call", {}).get("stdout", ""),
        ))

    return passed, failed, skipped, failures
