"""Tests for report generators."""

from ai_test_generator.reporters.markdown_reporter import generate_markdown_report
from ai_test_generator.models import (
    Classification,
    Confidence,
    Diagnosis,
    DiagnosisReport,
    Hypothesis,
    Severity,
)


def _make_report(failures=None):
    if failures is None:
        failures = [
            Diagnosis(
                test_name="test_login::test_lockout",
                classification=Classification.PRODUCT_BUG,
                confidence=Confidence.HIGH,
                severity=Severity.P1,
                probable_cause="Lockout counter not incrementing",
                hypotheses=[
                    Hypothesis(
                        classification=Classification.TEST_ISSUE,
                        evidence_for=[],
                        evidence_against=["Test is correct"],
                    ),
                    Hypothesis(
                        classification=Classification.INFRA_ISSUE,
                        evidence_for=[],
                        evidence_against=["No infra errors"],
                    ),
                    Hypothesis(
                        classification=Classification.PRODUCT_BUG,
                        evidence_for=["Lockout not triggered"],
                        evidence_against=[],
                    ),
                ],
                recommended_action="Check auth service",
                evidence_summary="Lockout counter bug",
            ),
        ]
    return DiagnosisReport(
        total_tests=10,
        passed=8,
        failed=len(failures),
        skipped=10 - 8 - len(failures),
        failures=failures,
        summary="Test run complete",
    )


class TestMarkdownReport:
    def test_contains_header(self):
        md = generate_markdown_report(_make_report(), feature="Login")
        assert "# Agentic QA Triage Report" in md
        assert "Login" in md

    def test_contains_summary_table(self):
        md = generate_markdown_report(_make_report())
        assert "| Total Tests | 10 |" in md
        assert "| Passed | 8 |" in md

    def test_contains_classification_breakdown(self):
        md = generate_markdown_report(_make_report())
        assert "product_bug" in md

    def test_contains_differential_diagnosis(self):
        md = generate_markdown_report(_make_report())
        assert "Differential Diagnosis" in md
        assert "test_issue" in md
        assert "infra_issue" in md

    def test_contains_ai_disclaimer(self):
        md = generate_markdown_report(_make_report())
        assert "AI-assessed" in md

    def test_empty_failures_report(self):
        md = generate_markdown_report(_make_report(failures=[]))
        assert "No failures to diagnose" in md
