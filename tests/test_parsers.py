"""Tests for result parsers — pytest JSON and JUnit XML."""

import json
import tempfile
from pathlib import Path

import pytest
from ai_test_generator.parsers import parse_pytest_json, parse_junit_xml


SAMPLE_PYTEST_JSON = {
    "summary": {"passed": 3, "failed": 2, "skipped": 1},
    "tests": [
        {"nodeid": "test_login::test_valid_login", "outcome": "passed"},
        {"nodeid": "test_login::test_invalid_password", "outcome": "passed"},
        {"nodeid": "test_login::test_empty_email", "outcome": "passed"},
        {
            "nodeid": "test_login::test_account_lockout",
            "outcome": "failed",
            "call": {
                "longrepr": "AssertionError: Expected lockout after 5 attempts, got login prompt",
                "crash": {"message": "AssertionError"},
                "duration": 2.5,
                "stdout": "Attempt 1: fail\nAttempt 2: fail\n",
            },
        },
        {
            "nodeid": "test_login::test_session_timeout",
            "outcome": "failed",
            "call": {
                "longrepr": "TimeoutError: page.wait_for_selector exceeded 30s",
                "crash": {"message": "TimeoutError"},
                "duration": 30.1,
            },
        },
        {"nodeid": "test_login::test_remember_me", "outcome": "skipped"},
    ],
}


SAMPLE_JUNIT_XML = """<?xml version="1.0" encoding="utf-8"?>
<testsuites>
  <testsuite name="LoginTests" tests="4" failures="1" errors="1" skipped="1">
    <testcase classname="LoginTests" name="test_valid_login" time="1.2"/>
    <testcase classname="LoginTests" name="test_lockout" time="5.0">
      <failure message="Expected lockout">AssertionError: not locked</failure>
    </testcase>
    <testcase classname="LoginTests" name="test_timeout" time="30.0">
      <error message="Connection refused">ConnectionError: timeout</error>
    </testcase>
    <testcase classname="LoginTests" name="test_remember_me" time="0">
      <skipped message="Not implemented"/>
    </testcase>
  </testsuite>
</testsuites>"""


class TestPytestParser:
    def test_parses_counts(self):
        passed, failed, skipped, failures = parse_pytest_json(SAMPLE_PYTEST_JSON)
        assert passed == 3
        assert failed == 2
        assert skipped == 1

    def test_extracts_failures(self):
        _, _, _, failures = parse_pytest_json(SAMPLE_PYTEST_JSON)
        assert len(failures) == 2
        assert failures[0].name == "test_login::test_account_lockout"
        assert "lockout" in failures[0].error_message.lower()

    def test_captures_duration(self):
        _, _, _, failures = parse_pytest_json(SAMPLE_PYTEST_JSON)
        assert failures[1].duration == pytest.approx(30.1)

    def test_parses_from_json_string(self):
        raw = json.dumps(SAMPLE_PYTEST_JSON)
        passed, failed, _, _ = parse_pytest_json(raw)
        assert passed == 3
        assert failed == 2

    def test_parses_from_file(self, tmp_path):
        f = tmp_path / "report.json"
        f.write_text(json.dumps(SAMPLE_PYTEST_JSON))
        passed, failed, _, failures = parse_pytest_json(f)
        assert passed == 3
        assert len(failures) == 2


class TestJUnitParser:
    def test_parses_counts(self):
        passed, failed, skipped, _ = parse_junit_xml(SAMPLE_JUNIT_XML)
        assert passed == 1
        assert failed == 2  # 1 failure + 1 error
        assert skipped == 1

    def test_extracts_failures(self):
        _, _, _, failures = parse_junit_xml(SAMPLE_JUNIT_XML)
        assert len(failures) == 2
        assert failures[0].name == "LoginTests::test_lockout"
        assert "lockout" in failures[0].error_message.lower()

    def test_captures_error_type(self):
        _, _, _, failures = parse_junit_xml(SAMPLE_JUNIT_XML)
        assert "connection" in failures[1].error_message.lower() or "refused" in failures[1].error_message.lower()

    def test_parses_from_file(self, tmp_path):
        f = tmp_path / "results.xml"
        f.write_text(SAMPLE_JUNIT_XML)
        passed, failed, skipped, failures = parse_junit_xml(f)
        assert passed == 1
        assert failed == 2
        assert len(failures) == 2
