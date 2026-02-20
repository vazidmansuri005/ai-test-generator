# AI Test Generator — Agentic QA

An autonomous, 3-layer QA system powered by Claude. Goes beyond "AI writes tests" — it generates, executes, diagnoses, and reports. Each layer works standalone or chains into a full pipeline.

```
┌─────────────────────────────────────────────────────────┐
│                   AGENTIC QA PIPELINE                   │
│                                                         │
│  ┌─────────────┐   ┌──────────────┐   ┌─────────────┐  │
│  │   Layer 1   │──▶│   Layer 2    │──▶│   Layer 3   │  │
│  │  Generate   │   │  Diagnose    │   │ Orchestrate │  │
│  │             │   │              │   │             │  │
│  │ User Story  │   │ Differential │   │ Full Pipeline│  │
│  │ → Test Cases│   │ Diagnosis    │   │ + Reporting │  │
│  │ → Code      │   │ 3 Hypotheses │   │ + GitHub    │  │
│  └─────────────┘   └──────────────┘   └─────────────┘  │
└─────────────────────────────────────────────────────────┘
```

## What Makes This Different

Most "AI testing" tools stop at test generation. This system:

- **Generates** structured test cases with priority, type, and coverage analysis
- **Produces** executable pytest or Playwright code (not pseudocode)
- **Diagnoses** failures using differential diagnosis — evaluates 3 hypotheses (test issue vs infra issue vs product bug) against evidence
- **Reports** with confidence scores, severity rankings (P0-P3), and actionable recommendations
- **Files GitHub issues** automatically for confirmed product bugs

## Quick Start

```bash
# Clone and install
git clone https://github.com/vazidmansuri005/ai-test-generator.git
cd ai-test-generator
pip install -e ".[dev]"

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-xxxxx
```

## Layer 1 — Test Generation

Generate test cases from any feature description or user story.

```bash
# From a one-liner
ai-test-gen generate "User login with email and password"

# From a requirements file
ai-test-gen generate requirements.md --output test_suite.json

# Generate pytest code from the test suite
ai-test-gen code test_suite.json --framework pytest --output test_login.py

# Or both in one shot
ai-test-gen one-shot "Shopping cart checkout" --framework playwright -d ./tests
```

**What you get:**
- 8-12 test cases covering happy path, edge cases, negative, boundary, security, accessibility
- Prioritized by severity (critical → low)
- Tagged for filtering
- Executable code with proper fixtures, assertions, and markers

## Layer 2 — Failure Diagnosis

Point it at any test results file and get a differential diagnosis.

```bash
# Diagnose pytest JSON report
ai-test-gen diagnose report.json

# Diagnose JUnit XML (works with any framework)
ai-test-gen diagnose results.xml --format junit-xml --output triage.md
```

**How diagnosis works:**

For each failure, the agent evaluates three hypotheses:

| Hypothesis | Meaning |
|------------|---------|
| `test_issue` | Test code is broken (bad locator, flaky wait, wrong assertion) |
| `infra_issue` | Infrastructure problem (timeout, DNS, container crash) |
| `product_bug` | Actual defect in the application under test |

Each hypothesis gets evidence **for** and **against**. Classification only happens when one hypothesis clearly dominates. When evidence is split → `unknown` (better than guessing wrong).

Output includes:
- Confidence: high / medium / low
- Severity: P0 (critical) → P3 (low)
- Probable cause (not "root cause" — we're analyzing logs, not debugging live)
- Recommended next action

## Layer 3 — Full Pipeline

Run the entire agentic QA pipeline autonomously.

```bash
# Full pipeline: generate → execute → diagnose → report
ai-test-gen pipeline "User login with email and password"

# With auto GitHub issue filing for product bugs
ai-test-gen pipeline "Checkout flow" --auto-issue --github-repo myuser/myapp

# Specify output directory
ai-test-gen pipeline requirements.md -d ./agentic_output
```

**What happens:**
1. Generates test cases from your feature description
2. Produces executable pytest code
3. Runs the tests
4. Diagnoses every failure with differential diagnosis
5. Generates a markdown triage report
6. Optionally files GitHub issues for confirmed product bugs

## All CLI Commands

```
ai-test-gen generate   — Layer 1: Generate test cases from feature description
ai-test-gen code       — Layer 1: Generate test code from test suite JSON
ai-test-gen one-shot   — Layer 1: Generate cases + code in one command
ai-test-gen diagnose   — Layer 2: Diagnose failures from test results file
ai-test-gen pipeline   — Layer 3: Run the full agentic pipeline
```

## Supported Formats

| Input | Formats |
|-------|---------|
| Feature descriptions | Inline text, `.md`, `.txt` files |
| Test results (diagnosis) | pytest-json-report (`.json`), JUnit XML (`.xml`) |
| Generated code | pytest, Playwright |

## Example Triage Report

```
# Agentic QA Triage Report

## Summary
| Metric      | Count |
|-------------|-------|
| Total Tests | 10    |
| Passed      | 8     |
| Failed      | 2     |

## Failure Details

### 1. test_login::test_account_lockout
| Classification   | Confidence | Severity |
|------------------|------------|----------|
| 🐛 product_bug   | 🟢 high    | **P1**   |

**Probable Cause**: Lockout counter not incrementing after failed attempts
**Recommended Action**: Check auth service lockout logic

### 2. test_login::test_session_timeout
| Classification   | Confidence | Severity |
|------------------|------------|----------|
| ❓ unknown        | 🔴 low     | **P3**   |

**Probable Cause**: Evidence split — could be stale selector, slow CI, or UI change
**Recommended Action**: Re-run locally, verify selector still valid
```

## Running Tests

```bash
pytest tests/ -v
```

27 tests covering all three layers — generators, parsers, diagnoser, and reporters.

## Architecture

```
src/ai_test_generator/
├── generator.py          # Layer 1: Claude-powered test generation
├── diagnoser.py          # Layer 2: Differential diagnosis engine
├── orchestrator.py       # Layer 3: Full pipeline orchestration
├── models.py             # Pydantic models for all layers
├── cli.py                # CLI interface (click + rich)
├── parsers/
│   ├── pytest_parser.py  # Parse pytest-json-report output
│   └── junit_parser.py   # Parse JUnit XML (universal)
└── reporters/
    ├── markdown_reporter.py  # Generate triage reports
    └── github_reporter.py    # File GitHub issues via gh CLI
```

## License

MIT
