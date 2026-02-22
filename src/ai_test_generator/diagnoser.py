"""Layer 2 — Failure Diagnosis Agent.

Performs differential diagnosis on test failures using Claude.
Evaluates three hypotheses (test_issue, infra_issue, product_bug)
against evidence before classifying. Never guesses — classifies
as 'unknown' when evidence is inconclusive.
"""

from __future__ import annotations

import json
import os

from anthropic import Anthropic

from .models import (
    Classification,
    Confidence,
    Diagnosis,
    DiagnosisReport,
    FailedTest,
    Severity,
)
from .memory import FailureMemory


DIAGNOSIS_SYSTEM = """You are an expert test failure diagnostician. Your job is to perform
DIFFERENTIAL DIAGNOSIS on test failures — not guess, not assume, but evaluate evidence.

For each failure, you MUST evaluate THREE hypotheses:

1. test_issue — The test code itself is broken (bad locator, wrong assertion, flaky wait,
   missing setup, outdated test data). The application works fine.

2. infra_issue — Infrastructure problem (network timeout, service unavailable, DNS failure,
   container crash, resource exhaustion, CI runner issue). Neither test nor product is at fault.

3. product_bug — Actual defect in the application under test. The test is correct and
   infrastructure is healthy, but the application behaves incorrectly.

CRITICAL RULES:
- Every symptom has MULTIPLE possible causes. A timeout could be any of the three.
- List evidence FOR and AGAINST each hypothesis.
- Only classify with high confidence when one hypothesis clearly dominates.
- Classify as "unknown" when evidence is split — this is BETTER than guessing wrong.
- Say "probable cause" not "root cause" — you're analyzing logs, not debugging live.
- Never default to any classification. Each failure is evaluated independently."""


DIAGNOSIS_PROMPT = """Analyze these test failures and provide a differential diagnosis for each.

Test Execution Summary:
- Passed: {passed}
- Failed: {failed}
- Skipped: {skipped}

Failed Tests:
{failures_json}

For EACH failed test, return a diagnosis. Respond with a JSON object:
{{
  "failures": [
    {{
      "test_name": "full test name",
      "classification": "test_issue|infra_issue|product_bug|unknown",
      "confidence": "high|medium|low",
      "severity": "P0|P1|P2|P3",
      "probable_cause": "1-2 sentence explanation of the most likely cause",
      "hypotheses": [
        {{
          "classification": "test_issue",
          "evidence_for": ["list of evidence supporting this"],
          "evidence_against": ["list of evidence contradicting this"]
        }},
        {{
          "classification": "infra_issue",
          "evidence_for": ["..."],
          "evidence_against": ["..."]
        }},
        {{
          "classification": "product_bug",
          "evidence_for": ["..."],
          "evidence_against": ["..."]
        }}
      ],
      "recommended_action": "specific next step",
      "evidence_summary": "key evidence that led to this conclusion"
    }}
  ],
  "summary": "overall assessment of this test run"
}}

Severity guidelines:
- P0: product_bug + high confidence + core functionality affected
- P1: product_bug + new failure OR confirmed infra_issue blocking tests
- P2: recurring issue OR medium-confidence product_bug
- P3: test_issue OR unknown classification

Return ONLY valid JSON, no markdown fences."""


class FailureDiagnoser:
    """Diagnoses test failures using differential diagnosis via Claude."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str = "claude-sonnet-4-20250514",
        memory: FailureMemory | None = None,
    ):
        self.client = Anthropic(api_key=api_key or os.environ.get("ANTHROPIC_API_KEY"))
        self.model = model
        self.memory = memory

    def diagnose(
        self,
        passed: int,
        failed: int,
        skipped: int,
        failures: list[FailedTest],
    ) -> DiagnosisReport:
        """Run differential diagnosis on test failures.

        Args:
            passed: Number of passed tests.
            failed: Number of failed tests.
            skipped: Number of skipped tests.
            failures: Parsed failure details.

        Returns:
            DiagnosisReport with classification and evidence for each failure.
        """
        if not failures:
            return DiagnosisReport(
                total_tests=passed + failed + skipped,
                passed=passed,
                failed=0,
                skipped=skipped,
                failures=[],
                summary="All tests passed. No failures to diagnose.",
            )

        # Truncate very long tracebacks to stay within token limits
        truncated = []
        for f in failures:
            tb = f.traceback
            if len(tb) > 2000:
                tb = tb[:1000] + "\n... [truncated] ...\n" + tb[-1000:]
            truncated.append(FailedTest(
                name=f.name,
                error_message=f.error_message,
                traceback=tb,
                duration=f.duration,
                stdout=f.stdout[:500] if f.stdout else "",
            ))

        failures_json = json.dumps(
            [t.model_dump() for t in truncated],
            indent=2,
        )

        prompt = DIAGNOSIS_PROMPT.format(
            passed=passed,
            failed=failed,
            skipped=skipped,
            failures_json=failures_json,
        )

        # Inject failure memory context if available
        if self.memory:
            memory_context = self.memory.get_context_for_diagnosis(failures_json)
            if memory_context:
                prompt += memory_context

        response = self.client.messages.create(
            model=self.model,
            max_tokens=4096,
            system=DIAGNOSIS_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        data = json.loads(raw)

        diagnoses = [Diagnosis.model_validate(d) for d in data["failures"]]

        return DiagnosisReport(
            total_tests=passed + failed + skipped,
            passed=passed,
            failed=failed,
            skipped=skipped,
            failures=diagnoses,
            summary=data.get("summary", ""),
        )
