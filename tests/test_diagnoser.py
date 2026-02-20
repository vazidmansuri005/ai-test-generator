"""Tests for Layer 2 — Failure Diagnoser."""

import json
import pytest
from unittest.mock import MagicMock, patch

from ai_test_generator.diagnoser import FailureDiagnoser
from ai_test_generator.models import (
    Classification,
    Confidence,
    Diagnosis,
    DiagnosisReport,
    FailedTest,
    Severity,
)


MOCK_DIAGNOSIS_RESPONSE = json.dumps({
    "failures": [
        {
            "test_name": "test_login::test_account_lockout",
            "classification": "product_bug",
            "confidence": "high",
            "severity": "P1",
            "probable_cause": "Lockout counter not incrementing after failed login attempts — likely a regression in the auth service.",
            "hypotheses": [
                {
                    "classification": "test_issue",
                    "evidence_for": [],
                    "evidence_against": ["Test correctly attempts 5 logins and checks lockout"],
                },
                {
                    "classification": "infra_issue",
                    "evidence_for": [],
                    "evidence_against": ["No timeout or network errors observed"],
                },
                {
                    "classification": "product_bug",
                    "evidence_for": [
                        "Assertion fails on lockout check after 5 attempts",
                        "Login prompt still shown instead of lockout message",
                    ],
                    "evidence_against": [],
                },
            ],
            "recommended_action": "Check auth service lockout counter logic — verify failed_attempts field increments on each POST /auth/login failure.",
            "evidence_summary": "Test correctly performs 5 failed logins. Expected lockout message but got login prompt. No infra errors. Points to auth service regression.",
        },
        {
            "test_name": "test_login::test_session_timeout",
            "classification": "unknown",
            "confidence": "low",
            "severity": "P3",
            "probable_cause": "30s timeout on wait_for_selector — could be slow page load, broken locator, or actual UI regression.",
            "hypotheses": [
                {
                    "classification": "test_issue",
                    "evidence_for": ["Timeout could indicate a stale CSS selector"],
                    "evidence_against": ["No prior failures on this test"],
                },
                {
                    "classification": "infra_issue",
                    "evidence_for": ["30s timeout could indicate slow CI runner"],
                    "evidence_against": ["Other tests passed with normal duration"],
                },
                {
                    "classification": "product_bug",
                    "evidence_for": ["UI element may have been removed or renamed"],
                    "evidence_against": ["No evidence of UI change"],
                },
            ],
            "recommended_action": "Re-run test locally. Check if the CSS selector still matches the target element. Compare with last successful run.",
            "evidence_summary": "Timeout on page selector. Evidence is split across all three hypotheses — classified as unknown.",
        },
    ],
    "summary": "2 failures analyzed. 1 probable product bug (P1, high confidence). 1 unknown (P3, needs investigation).",
})


@pytest.fixture
def diagnoser():
    with patch("ai_test_generator.diagnoser.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        d = FailureDiagnoser(api_key="test-key")
        d._mock_client = mock_client
        yield d


def _set_mock(diagnoser, text):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    diagnoser._mock_client.messages.create.return_value = mock_msg


class TestDiagnosis:
    def test_returns_diagnosis_report(self, diagnoser):
        _set_mock(diagnoser, MOCK_DIAGNOSIS_RESPONSE)
        failures = [
            FailedTest(name="test_login::test_account_lockout", error_message="AssertionError"),
            FailedTest(name="test_login::test_session_timeout", error_message="TimeoutError"),
        ]
        report = diagnoser.diagnose(3, 2, 1, failures)

        assert isinstance(report, DiagnosisReport)
        assert report.total_tests == 6
        assert report.failed == 2
        assert len(report.failures) == 2

    def test_classifies_product_bug(self, diagnoser):
        _set_mock(diagnoser, MOCK_DIAGNOSIS_RESPONSE)
        failures = [FailedTest(name="test_lockout", error_message="err")]
        report = diagnoser.diagnose(3, 2, 1, [failures[0], failures[0]])

        bug = report.failures[0]
        assert bug.classification == Classification.PRODUCT_BUG
        assert bug.confidence == Confidence.HIGH
        assert bug.severity == Severity.P1

    def test_classifies_unknown_when_split(self, diagnoser):
        _set_mock(diagnoser, MOCK_DIAGNOSIS_RESPONSE)
        failures = [FailedTest(name="test", error_message="err")]
        report = diagnoser.diagnose(3, 2, 1, [failures[0], failures[0]])

        unknown = report.failures[1]
        assert unknown.classification == Classification.UNKNOWN
        assert unknown.confidence == Confidence.LOW

    def test_evaluates_all_three_hypotheses(self, diagnoser):
        _set_mock(diagnoser, MOCK_DIAGNOSIS_RESPONSE)
        failures = [FailedTest(name="test", error_message="err")]
        report = diagnoser.diagnose(3, 2, 1, [failures[0], failures[0]])

        for diag in report.failures:
            classifications = {h.classification for h in diag.hypotheses}
            assert Classification.TEST_ISSUE in classifications
            assert Classification.INFRA_ISSUE in classifications
            assert Classification.PRODUCT_BUG in classifications

    def test_empty_failures_returns_clean_report(self, diagnoser):
        report = diagnoser.diagnose(10, 0, 0, [])

        assert report.total_tests == 10
        assert report.failed == 0
        assert len(report.failures) == 0
        assert "passed" in report.summary.lower()

    def test_truncates_long_tracebacks(self, diagnoser):
        _set_mock(diagnoser, MOCK_DIAGNOSIS_RESPONSE)
        long_tb = "x" * 5000
        failures = [FailedTest(name="test", error_message="err", traceback=long_tb)]
        diagnoser.diagnose(0, 1, 0, failures)

        call_args = diagnoser._mock_client.messages.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "[truncated]" in prompt
