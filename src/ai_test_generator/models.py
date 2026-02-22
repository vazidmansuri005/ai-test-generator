"""Data models for test case generation."""

from __future__ import annotations

from enum import Enum
from pydantic import BaseModel, Field


class Priority(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class TestType(str, Enum):
    FUNCTIONAL = "functional"
    EDGE_CASE = "edge_case"
    NEGATIVE = "negative"
    BOUNDARY = "boundary"
    SECURITY = "security"
    ACCESSIBILITY = "accessibility"


class TestStep(BaseModel):
    action: str = Field(description="What the user does")
    expected: str = Field(description="What should happen")
    test_data: str | None = Field(default=None, description="Specific test data needed")


class TestCase(BaseModel):
    id: str = Field(description="Short identifier like TC-001")
    title: str = Field(description="Concise test case title")
    type: TestType = Field(description="Category of this test")
    priority: Priority = Field(description="Execution priority")
    preconditions: list[str] = Field(default_factory=list, description="Setup requirements")
    steps: list[TestStep] = Field(description="Ordered test steps")
    tags: list[str] = Field(default_factory=list, description="Labels for filtering")


class TestSuite(BaseModel):
    feature: str = Field(description="Feature being tested")
    summary: str = Field(description="Brief description of test coverage")
    test_cases: list[TestCase] = Field(description="Generated test cases")
    coverage_notes: str = Field(description="What's covered and what's not")


class CodeOutput(BaseModel):
    framework: str = Field(description="pytest or playwright")
    filename: str = Field(description="Suggested filename")
    code: str = Field(description="Generated test code")
    dependencies: list[str] = Field(default_factory=list, description="Required pip packages")


# ---------------------------------------------------------------------------
# Layer 2 — Diagnosis models
# ---------------------------------------------------------------------------


class Classification(str, Enum):
    TEST_ISSUE = "test_issue"
    INFRA_ISSUE = "infra_issue"
    PRODUCT_BUG = "product_bug"
    UNKNOWN = "unknown"


class Confidence(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class Severity(str, Enum):
    P0 = "P0"
    P1 = "P1"
    P2 = "P2"
    P3 = "P3"


class FailedTest(BaseModel):
    name: str = Field(description="Fully qualified test name")
    error_message: str = Field(description="Error or assertion message")
    traceback: str = Field(default="", description="Full stack trace")
    duration: float = Field(default=0.0, description="Execution time in seconds")
    stdout: str = Field(default="", description="Captured stdout")


class Hypothesis(BaseModel):
    classification: Classification
    evidence_for: list[str] = Field(description="Evidence supporting this hypothesis")
    evidence_against: list[str] = Field(description="Evidence contradicting this hypothesis")


class Diagnosis(BaseModel):
    test_name: str = Field(description="Which test was diagnosed")
    classification: Classification = Field(description="Final classification")
    confidence: Confidence = Field(description="How confident is this diagnosis")
    severity: Severity = Field(description="Priority for action")
    probable_cause: str = Field(description="Most likely root cause explanation")
    hypotheses: list[Hypothesis] = Field(description="All evaluated hypotheses")
    recommended_action: str = Field(description="What to do next")
    evidence_summary: str = Field(description="Key evidence that led to this conclusion")


class DiagnosisReport(BaseModel):
    total_tests: int
    passed: int
    failed: int
    skipped: int
    failures: list[Diagnosis] = Field(description="Diagnosis for each failed test")
    summary: str = Field(description="Overall assessment")


# ---------------------------------------------------------------------------
# Layer 3 — Orchestration models
# ---------------------------------------------------------------------------


class PipelineStage(str, Enum):
    GENERATE = "generate"
    EXECUTE = "execute"
    DIAGNOSE = "diagnose"
    REPORT = "report"


class PipelineResult(BaseModel):
    feature: str = Field(description="Feature that was tested")
    stages_completed: list[PipelineStage] = Field(default_factory=list)
    test_suite: TestSuite | None = None
    code_output: CodeOutput | None = None
    diagnosis: DiagnosisReport | None = None
    report_path: str | None = Field(default=None, description="Path to generated report")
    github_issue_url: str | None = Field(default=None, description="URL if issue was filed")


# ---------------------------------------------------------------------------
# Failure Memory models
# ---------------------------------------------------------------------------


class Correction(BaseModel):
    test_name: str = Field(description="Test that was corrected")
    original_classification: Classification
    corrected_classification: Classification
    reason: str = Field(description="Why the correction was made")
    error_pattern: str = Field(description="Key error pattern for future matching")
    timestamp: str = Field(description="ISO 8601 timestamp of correction")


class MemoryMatch(BaseModel):
    correction: Correction
    similarity: str = Field(description="How this past correction relates to current failure")


# ---------------------------------------------------------------------------
# PR Impact Analysis models
# ---------------------------------------------------------------------------


class RiskLevel(str, Enum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class FileChange(BaseModel):
    path: str = Field(description="File path that changed")
    change_type: str = Field(description="added, modified, deleted, renamed")
    diff_summary: str = Field(description="Summary of what changed in this file")


class TestImpact(BaseModel):
    test_file: str = Field(description="Test file at risk")
    test_name: str = Field(default="", description="Specific test function if identifiable")
    risk_level: RiskLevel = Field(description="How likely this test will break")
    reason: str = Field(description="Why this test is at risk")
    changed_file: str = Field(description="Which changed file affects this test")


class ImpactReport(BaseModel):
    total_files_changed: int
    total_tests_at_risk: int
    high_risk: list[TestImpact] = Field(default_factory=list)
    medium_risk: list[TestImpact] = Field(default_factory=list)
    low_risk: list[TestImpact] = Field(default_factory=list)
    summary: str = Field(description="Overall impact assessment")
    recommendation: str = Field(description="What to run and in what order")
