"""Core test generation engine using Claude API."""

from __future__ import annotations

import json
import os
from anthropic import Anthropic
from .models import TestSuite, CodeOutput


SYSTEM_PROMPT = """You are an expert SDET (Software Development Engineer in Test) who generates
comprehensive test cases from feature descriptions or user stories.

Your test cases must be:
- Thorough: cover happy path, edge cases, negative scenarios, and boundary conditions
- Actionable: each step is clear enough for any QA engineer to execute
- Prioritized: critical paths first, edge cases after
- Tagged: include relevant labels for filtering

When generating test code, follow these principles:
- Clean, readable code with descriptive names
- Proper assertions with meaningful error messages
- Independent tests that don't depend on execution order
- Appropriate use of fixtures and setup/teardown"""


TEST_CASE_PROMPT = """Analyze this feature and generate a comprehensive test suite.

Feature Description:
{feature_description}

{context_section}

Return a JSON object with this exact structure:
{{
  "feature": "feature name",
  "summary": "brief coverage summary",
  "test_cases": [
    {{
      "id": "TC-001",
      "title": "descriptive title",
      "type": "functional|edge_case|negative|boundary|security|accessibility",
      "priority": "critical|high|medium|low",
      "preconditions": ["list of setup requirements"],
      "steps": [
        {{
          "action": "what the user does",
          "expected": "what should happen",
          "test_data": "specific data if needed or null"
        }}
      ],
      "tags": ["relevant", "labels"]
    }}
  ],
  "coverage_notes": "what is and isn't covered"
}}

Generate at least 8-12 test cases covering:
- 2-3 happy path / functional tests
- 2-3 edge case tests
- 2-3 negative tests
- 1-2 boundary value tests
- 1 security test (if applicable)
- 1 accessibility test (if applicable)

Return ONLY valid JSON, no markdown fences or extra text."""


CODE_GEN_PROMPT = """Convert these test cases into executable {framework} test code.

Test Suite:
{test_suite_json}

Requirements:
- Use {framework} best practices and conventions
- Include proper imports and fixtures
- Add docstrings to each test function
- Use descriptive assertion messages
- Group related tests in classes where appropriate
- Add markers/tags for filtering (e.g., @pytest.mark.critical)

{framework_specific}

Return a JSON object:
{{
  "framework": "{framework}",
  "filename": "suggested_filename.py",
  "code": "the full test code as a string",
  "dependencies": ["list", "of", "pip", "packages"]
}}

Return ONLY valid JSON, no markdown fences or extra text."""

PYTEST_SPECIFICS = """Pytest-specific:
- Use pytest fixtures for setup
- Use @pytest.mark.parametrize for data-driven tests
- Use conftest.py patterns where appropriate
- Include the code for conftest.py if needed as a separate note"""

PLAYWRIGHT_SPECIFICS = """Playwright-specific:
- Use sync Playwright API (playwright.sync_api)
- Use Page Object Model pattern
- Include proper page.wait_for_selector calls
- Use expect() for assertions
- Handle navigation waits"""


class TestGenerator:
    """Generates test cases and test code from feature descriptions using Claude."""

    def __init__(self, api_key: str | None = None, model: str = "claude-sonnet-4-20250514"):
        self.client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model

    def generate_test_cases(
        self,
        feature_description: str,
        context: str | None = None,
    ) -> TestSuite:
        """Generate structured test cases from a feature description.

        Args:
            feature_description: The feature, user story, or requirement to test.
            context: Optional additional context (API docs, UI description, etc).

        Returns:
            TestSuite with generated test cases.
        """
        context_section = f"Additional Context:\n{context}" if context else ""
        prompt = TEST_CASE_PROMPT.format(
            feature_description=feature_description,
            context_section=context_section,
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        data = json.loads(raw)
        return TestSuite.model_validate(data)

    def generate_code(
        self,
        test_suite: TestSuite,
        framework: str = "pytest",
    ) -> CodeOutput:
        """Generate executable test code from a test suite.

        Args:
            test_suite: Previously generated test suite.
            framework: Target framework — "pytest" or "playwright".

        Returns:
            CodeOutput with the generated code and metadata.
        """
        framework_specific = (
            PYTEST_SPECIFICS if framework == "pytest" else PLAYWRIGHT_SPECIFICS
        )
        prompt = CODE_GEN_PROMPT.format(
            framework=framework,
            test_suite_json=test_suite.model_dump_json(indent=2),
            framework_specific=framework_specific,
        )

        response = self.client.messages.create(
            model=self.model,
            max_tokens=8192,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        data = json.loads(raw)
        return CodeOutput.model_validate(data)
