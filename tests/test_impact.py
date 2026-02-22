"""Tests for PR Impact Analysis."""

import json
import pytest
from unittest.mock import MagicMock, patch

from ai_test_generator.impact import ImpactAnalyzer
from ai_test_generator.models import FileChange, ImpactReport, RiskLevel


MOCK_IMPACT_RESPONSE = json.dumps({
    "high_risk": [
        {
            "test_file": "tests/test_payment.py",
            "test_name": "test_checkout_flow",
            "risk_level": "high",
            "reason": "payment.py:handle_payment() was modified — removed null check on line 47. test_checkout_flow directly asserts on payment success.",
            "changed_file": "src/payment.py",
        },
    ],
    "medium_risk": [
        {
            "test_file": "tests/test_cart.py",
            "test_name": "test_apply_discount",
            "risk_level": "medium",
            "reason": "pricing.py:apply_discount() logic changed — discount calculation may differ.",
            "changed_file": "src/pricing.py",
        },
    ],
    "low_risk": [
        {
            "test_file": "tests/test_search.py",
            "test_name": "",
            "risk_level": "low",
            "reason": "Only logging changes in search.py — unlikely to affect test behavior.",
            "changed_file": "src/search.py",
        },
    ],
    "summary": "3 tests at risk. 1 high-risk: payment null check removal likely breaks checkout test.",
    "recommendation": "Run test_payment.py first. Then test_cart.py. test_search.py can wait.",
})


@pytest.fixture
def analyzer():
    with patch("ai_test_generator.impact.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        a = ImpactAnalyzer(api_key="test-key")
        a._mock_client = mock_client
        yield a


def _set_mock(analyzer, text):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    analyzer._mock_client.messages.create.return_value = mock_msg


class TestImpactAnalysis:
    def test_returns_impact_report(self, analyzer):
        _set_mock(analyzer, MOCK_IMPACT_RESPONSE)

        changes = [
            FileChange(path="src/payment.py", change_type="modified", diff_summary="- if x is None:\n+ # removed"),
            FileChange(path="src/pricing.py", change_type="modified", diff_summary="discount logic"),
            FileChange(path="src/search.py", change_type="modified", diff_summary="added logging"),
        ]
        test_files = {
            "tests/test_payment.py": {"path": "tests/test_payment.py", "content_preview": "def test_checkout_flow():"},
            "tests/test_cart.py": {"path": "tests/test_cart.py", "content_preview": "def test_apply_discount():"},
            "tests/test_search.py": {"path": "tests/test_search.py", "content_preview": "def test_search():"},
        }

        report = analyzer._predict_impact(changes, test_files)

        assert isinstance(report, ImpactReport)
        assert report.total_files_changed == 3
        assert report.total_tests_at_risk == 3

    def test_high_risk_identified(self, analyzer):
        _set_mock(analyzer, MOCK_IMPACT_RESPONSE)

        changes = [FileChange(path="src/payment.py", change_type="modified", diff_summary="diff")]
        report = analyzer._predict_impact(changes, {})

        assert len(report.high_risk) == 1
        assert report.high_risk[0].test_file == "tests/test_payment.py"
        assert report.high_risk[0].risk_level == RiskLevel.HIGH
        assert "null check" in report.high_risk[0].reason.lower()

    def test_medium_risk_identified(self, analyzer):
        _set_mock(analyzer, MOCK_IMPACT_RESPONSE)

        changes = [FileChange(path="src/pricing.py", change_type="modified", diff_summary="diff")]
        report = analyzer._predict_impact(changes, {})

        assert len(report.medium_risk) == 1
        assert "discount" in report.medium_risk[0].reason.lower()

    def test_low_risk_identified(self, analyzer):
        _set_mock(analyzer, MOCK_IMPACT_RESPONSE)

        changes = [FileChange(path="src/search.py", change_type="modified", diff_summary="diff")]
        report = analyzer._predict_impact(changes, {})

        assert len(report.low_risk) == 1
        assert "logging" in report.low_risk[0].reason.lower()

    def test_includes_recommendation(self, analyzer):
        _set_mock(analyzer, MOCK_IMPACT_RESPONSE)

        changes = [FileChange(path="x.py", change_type="modified", diff_summary="diff")]
        report = analyzer._predict_impact(changes, {})

        assert "payment" in report.recommendation.lower()

    def test_empty_changes_returns_clean_report(self, analyzer):
        report = analyzer.analyze_from_text("", {})
        assert report.total_files_changed == 0
        assert report.total_tests_at_risk == 0


class TestDiffParsing:
    def test_parses_raw_diff_text(self, analyzer):
        diff = """diff --git a/src/auth.py b/src/auth.py
index abc..def 100644
--- a/src/auth.py
+++ b/src/auth.py
@@ -10,3 +10,3 @@
- old_line
+ new_line
diff --git a/src/utils.py b/src/utils.py
--- a/src/utils.py
+++ b/src/utils.py
@@ -5,1 +5,1 @@
- old
+ new"""
        changes = analyzer._parse_diff_text(diff)
        assert len(changes) == 2
        assert changes[0].path == "src/auth.py"
        assert changes[1].path == "src/utils.py"

    def test_empty_diff_returns_empty(self, analyzer):
        changes = analyzer._parse_diff_text("")
        assert changes == []
