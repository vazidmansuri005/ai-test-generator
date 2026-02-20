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
