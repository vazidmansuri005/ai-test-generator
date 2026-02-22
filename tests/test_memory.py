"""Tests for Failure Memory — persistent learning system."""

import json
import pytest
from pathlib import Path

from ai_test_generator.memory import FailureMemory
from ai_test_generator.models import Classification, Confidence, Diagnosis, Hypothesis, Severity


@pytest.fixture
def memory(tmp_path):
    """Create a FailureMemory with a temp directory."""
    return FailureMemory(memory_dir=tmp_path / "memory")


class TestRecordCorrection:
    def test_stores_correction(self, memory):
        correction = memory.record_correction(
            test_name="test_checkout::test_payment",
            original=Classification.INFRA_ISSUE,
            corrected=Classification.TEST_ISSUE,
            reason="Stale CSS selector",
            error_pattern="TimeoutError: wait_for_selector",
        )

        assert correction.test_name == "test_checkout::test_payment"
        assert correction.original_classification == Classification.INFRA_ISSUE
        assert correction.corrected_classification == Classification.TEST_ISSUE
        assert memory.correction_count == 1

    def test_persists_to_disk(self, memory):
        memory.record_correction(
            test_name="test_a",
            original=Classification.UNKNOWN,
            corrected=Classification.PRODUCT_BUG,
            reason="Real bug",
            error_pattern="AssertionError",
        )

        # Create a new memory instance from the same directory
        memory2 = FailureMemory(memory_dir=memory.memory_dir)
        assert memory2.correction_count == 1
        assert memory2.corrections[0].test_name == "test_a"

    def test_multiple_corrections(self, memory):
        for i in range(5):
            memory.record_correction(
                test_name=f"test_{i}",
                original=Classification.UNKNOWN,
                corrected=Classification.TEST_ISSUE,
                reason=f"Reason {i}",
                error_pattern=f"Error pattern {i}",
            )
        assert memory.correction_count == 5

    def test_records_from_diagnosis(self, memory):
        diag = Diagnosis(
            test_name="test_login::test_lockout",
            classification=Classification.INFRA_ISSUE,
            confidence=Confidence.MEDIUM,
            severity=Severity.P2,
            probable_cause="Connection timeout to auth service",
            hypotheses=[
                Hypothesis(
                    classification=Classification.INFRA_ISSUE,
                    evidence_for=["timeout"],
                    evidence_against=[],
                ),
            ],
            recommended_action="Check auth service",
            evidence_summary="Timeout on auth call",
        )

        correction = memory.record_from_diagnosis(
            diag,
            corrected=Classification.PRODUCT_BUG,
            reason="Auth service regression, not infra",
        )

        assert correction.original_classification == Classification.INFRA_ISSUE
        assert correction.corrected_classification == Classification.PRODUCT_BUG


class TestFindMatches:
    def test_finds_matching_pattern(self, memory):
        memory.record_correction(
            test_name="test_checkout",
            original=Classification.INFRA_ISSUE,
            corrected=Classification.TEST_ISSUE,
            reason="Stale selector",
            error_pattern="TimeoutError: wait_for_selector('#pay-btn')",
        )

        matches = memory.find_matches("TimeoutError: wait_for_selector('#submit-btn')")
        assert len(matches) >= 1
        assert matches[0].correction.corrected_classification == Classification.TEST_ISSUE

    def test_exact_substring_gets_high_score(self, memory):
        memory.record_correction(
            test_name="test_a",
            original=Classification.UNKNOWN,
            corrected=Classification.TEST_ISSUE,
            reason="Known flaky",
            error_pattern="ElementNotFound: #login-btn",
        )

        matches = memory.find_matches("ElementNotFound: #login-btn timed out after 30s")
        assert len(matches) >= 1

    def test_no_match_returns_empty(self, memory):
        memory.record_correction(
            test_name="test_a",
            original=Classification.UNKNOWN,
            corrected=Classification.TEST_ISSUE,
            reason="Reason",
            error_pattern="SpecificUniqueError: xyz123",
        )

        matches = memory.find_matches("CompletleyDifferentError: abc")
        # Should not match — completely different tokens
        assert len(matches) == 0

    def test_empty_memory_returns_empty(self, memory):
        matches = memory.find_matches("any error text")
        assert matches == []

    def test_respects_limit(self, memory):
        for i in range(10):
            memory.record_correction(
                test_name=f"test_{i}",
                original=Classification.UNKNOWN,
                corrected=Classification.TEST_ISSUE,
                reason=f"Reason {i}",
                error_pattern=f"TimeoutError: selector_{i}",
            )

        matches = memory.find_matches("TimeoutError: selector_5", limit=3)
        assert len(matches) <= 3


class TestDiagnosisContext:
    def test_generates_context_with_corrections(self, memory):
        memory.record_correction(
            test_name="test_payment",
            original=Classification.INFRA_ISSUE,
            corrected=Classification.TEST_ISSUE,
            reason="CSS selector broke",
            error_pattern="TimeoutError: wait_for_selector",
        )

        context = memory.get_context_for_diagnosis(
            "TimeoutError: wait_for_selector timed out"
        )
        assert "Past corrections" in context
        assert "test_issue" in context
        assert "CSS selector broke" in context

    def test_empty_memory_returns_empty_context(self, memory):
        context = memory.get_context_for_diagnosis("any error")
        assert context == ""


class TestStats:
    def test_tracks_correction_counts(self, memory):
        memory.record_correction(
            test_name="test_a",
            original=Classification.INFRA_ISSUE,
            corrected=Classification.TEST_ISSUE,
            reason="A",
            error_pattern="err",
        )
        memory.record_correction(
            test_name="test_b",
            original=Classification.INFRA_ISSUE,
            corrected=Classification.TEST_ISSUE,
            reason="B",
            error_pattern="err",
        )

        stats = memory.get_stats()
        assert stats["total_corrections"] == 2
        assert stats["pattern_counts"]["infra_issue->test_issue"] == 2
