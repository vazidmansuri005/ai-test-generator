# AI Test Generator

Generate comprehensive test cases and executable test code from user stories — powered by Claude.

Give it a feature description, get back structured test cases (happy path, edge cases, negative, boundary, security) and optionally generate `pytest` or `playwright` code.

## Quick Start

```bash
# Clone and install
git clone https://github.com/vazidmansuri005/ai-test-generator.git
cd ai-test-generator
pip install -e ".[dev]"

# Set your API key
export ANTHROPIC_API_KEY=sk-ant-xxxxx

# Generate test cases from a one-liner
ai-test-gen generate "User login with email and password"

# Generate from a detailed requirements file
ai-test-gen generate examples/login_feature.md --output test_suite.json

# Generate pytest code from the test suite
ai-test-gen code test_suite.json --framework pytest --output test_login.py

# Or do both in one shot
ai-test-gen one-shot "Shopping cart checkout" --framework playwright -d ./tests
```

## Commands

### `generate` — Create test cases

```bash
ai-test-gen generate "feature description or path/to/file.md" [OPTIONS]

Options:
  -c, --context   Additional context (API docs, constraints, etc.)
  -o, --output    Save test suite JSON to file
  -m, --model     Claude model (default: claude-sonnet-4-20250514)
```

### `code` — Generate executable tests

```bash
ai-test-gen code test_suite.json [OPTIONS]

Options:
  -f, --framework   pytest or playwright (default: pytest)
  -o, --output      Save code to file
  -m, --model       Claude model
```

### `one-shot` — Generate everything at once

```bash
ai-test-gen one-shot "feature description" [OPTIONS]

Options:
  -c, --context      Additional context
  -f, --framework    pytest or playwright
  -d, --output-dir   Directory for output files (default: .)
  -m, --model        Claude model
```

## Example Output

```
$ ai-test-gen generate "User login with email and password"

Generated 10 test cases

┌──────────────────────────────────────────────────────────────┐
│ ID      │ Title                              │ Type      │ P │
├──────────────────────────────────────────────────────────────┤
│ TC-001  │ Successful login with valid creds  │ functional│ C │
│ TC-002  │ Login fails with wrong password    │ negative  │ H │
│ TC-003  │ Account lockout after 5 failures   │ security  │ H │
│ TC-004  │ Empty email field validation       │ negative  │ M │
│ TC-005  │ SQL injection in email field       │ security  │ C │
│ ...     │ ...                                │ ...       │ . │
└──────────────────────────────────────────────────────────────┘
```

## How It Works

1. Your feature description is sent to Claude with an expert SDET system prompt
2. Claude generates structured test cases covering functional, edge, negative, boundary, security, and accessibility scenarios
3. Optionally, the test suite is fed back to Claude to generate framework-specific test code
4. Everything is validated through Pydantic models for type safety

## Running Tests

```bash
pytest tests/ -v
```

## License

MIT
