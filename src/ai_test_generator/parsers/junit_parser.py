"""Parse JUnit XML reports into FailedTest models."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

from ..models import FailedTest


def parse_junit_xml(source: str | Path) -> tuple[int, int, int, list[FailedTest]]:
    """Parse JUnit XML report into structured failure data.

    Works with standard JUnit XML format used by pytest, Java, JS frameworks, etc.

    Args:
        source: Path to JUnit XML file or XML string.

    Returns:
        Tuple of (passed, failed, skipped, list[FailedTest]).
    """
    path = Path(source)
    if path.exists():
        tree = ET.parse(path)
        root = tree.getroot()
    else:
        root = ET.fromstring(source)

    # Handle both <testsuites> wrapper and direct <testsuite>
    if root.tag == "testsuites":
        suites = root.findall("testsuite")
    else:
        suites = [root]

    passed = 0
    failed = 0
    skipped = 0
    failures: list[FailedTest] = []

    for suite in suites:
        for testcase in suite.findall("testcase"):
            failure_el = testcase.find("failure")
            error_el = testcase.find("error")
            skip_el = testcase.find("skipped")

            classname = testcase.get("classname", "")
            name = testcase.get("name", "unknown")
            full_name = f"{classname}::{name}" if classname else name
            duration = float(testcase.get("time", "0"))

            if failure_el is not None or error_el is not None:
                failed += 1
                el = failure_el if failure_el is not None else error_el
                stdout_el = testcase.find("system-out")
                failures.append(FailedTest(
                    name=full_name,
                    error_message=el.get("message", "No error message"),
                    traceback=el.text or "",
                    duration=duration,
                    stdout=stdout_el.text if stdout_el is not None else "",
                ))
            elif skip_el is not None:
                skipped += 1
            else:
                passed += 1

    return passed, failed, skipped, failures
