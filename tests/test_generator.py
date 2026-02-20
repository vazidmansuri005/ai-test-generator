"""Tests for the AI Test Generator — runs without API calls using mocked responses."""

import json
import pytest
from unittest.mock import MagicMock, patch
from ai_test_generator.generator import TestGenerator
from ai_test_generator.models import TestSuite, CodeOutput


MOCK_SUITE_RESPONSE = json.dumps({
    "feature": "User Login",
    "summary": "Comprehensive login feature test coverage",
    "test_cases": [
        {
            "id": "TC-001",
            "title": "Successful login with valid credentials",
            "type": "functional",
            "priority": "critical",
            "preconditions": ["User account exists", "User is on login page"],
            "steps": [
                {
                    "action": "Enter valid email in email field",
                    "expected": "Email is displayed in the field",
                    "test_data": "user@example.com",
                },
                {
                    "action": "Enter valid password in password field",
                    "expected": "Password is masked",
                    "test_data": "ValidPass123!",
                },
                {
                    "action": "Click Login button",
                    "expected": "User is redirected to dashboard",
                    "test_data": None,
                },
            ],
            "tags": ["login", "happy-path", "smoke"],
        },
        {
            "id": "TC-002",
            "title": "Login fails with incorrect password",
            "type": "negative",
            "priority": "high",
            "preconditions": ["User account exists"],
            "steps": [
                {
                    "action": "Enter valid email",
                    "expected": "Email is accepted",
                    "test_data": "user@example.com",
                },
                {
                    "action": "Enter incorrect password",
                    "expected": "Error message displayed",
                    "test_data": "WrongPass!",
                },
            ],
            "tags": ["login", "negative"],
        },
    ],
    "coverage_notes": "Covers happy path and basic negative case. Missing: boundary, security, accessibility.",
})


MOCK_CODE_RESPONSE = json.dumps({
    "framework": "pytest",
    "filename": "test_login.py",
    "code": "import pytest\n\ndef test_login_success():\n    assert True\n",
    "dependencies": ["pytest"],
})


@pytest.fixture
def generator():
    """Create a TestGenerator with a mocked Anthropic client."""
    with patch("ai_test_generator.generator.Anthropic") as mock_cls:
        mock_client = MagicMock()
        mock_cls.return_value = mock_client
        gen = TestGenerator(api_key="test-key")
        gen._mock_client = mock_client
        yield gen


def _set_mock_response(generator: TestGenerator, text: str):
    mock_msg = MagicMock()
    mock_msg.content = [MagicMock(text=text)]
    generator._mock_client.messages.create.return_value = mock_msg


class TestTestCaseGeneration:
    def test_generates_valid_test_suite(self, generator):
        _set_mock_response(generator, MOCK_SUITE_RESPONSE)
        suite = generator.generate_test_cases("User login feature")

        assert isinstance(suite, TestSuite)
        assert suite.feature == "User Login"
        assert len(suite.test_cases) == 2

    def test_first_test_case_structure(self, generator):
        _set_mock_response(generator, MOCK_SUITE_RESPONSE)
        suite = generator.generate_test_cases("User login feature")
        tc = suite.test_cases[0]

        assert tc.id == "TC-001"
        assert tc.priority.value == "critical"
        assert tc.type.value == "functional"
        assert len(tc.steps) == 3
        assert "login" in tc.tags

    def test_passes_context_to_prompt(self, generator):
        _set_mock_response(generator, MOCK_SUITE_RESPONSE)
        generator.generate_test_cases("Login", context="REST API, JWT auth")

        call_args = generator._mock_client.messages.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "REST API, JWT auth" in prompt

    def test_works_without_context(self, generator):
        _set_mock_response(generator, MOCK_SUITE_RESPONSE)
        generator.generate_test_cases("Login")

        call_args = generator._mock_client.messages.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "Additional Context:" not in prompt


class TestCodeGeneration:
    def test_generates_code_output(self, generator):
        _set_mock_response(generator, MOCK_SUITE_RESPONSE)
        suite = generator.generate_test_cases("Login")

        _set_mock_response(generator, MOCK_CODE_RESPONSE)
        code = generator.generate_code(suite, framework="pytest")

        assert isinstance(code, CodeOutput)
        assert code.framework == "pytest"
        assert code.filename == "test_login.py"
        assert "def test_login_success" in code.code

    def test_requests_correct_framework(self, generator):
        _set_mock_response(generator, MOCK_SUITE_RESPONSE)
        suite = generator.generate_test_cases("Login")

        _set_mock_response(generator, MOCK_CODE_RESPONSE)
        generator.generate_code(suite, framework="playwright")

        call_args = generator._mock_client.messages.create.call_args
        prompt = call_args.kwargs["messages"][0]["content"]
        assert "playwright" in prompt.lower()
