# Contributing

Contributions are welcome. Here's how to get started.

## Setup

```bash
git clone https://github.com/michael-niemand/litellm-triage.git
cd litellm-triage
pip install -e ".[dev]"
```

## Running tests

```bash
pytest
```

Tests use mocked HTTP (via `respx`) — no running services required.

## Making changes

1. Fork the repo and create a branch (`git checkout -b feat/your-thing`)
2. Write tests for new behaviour
3. Run `pytest` and make sure everything passes
4. Open a PR against `main`

## Reporting bugs

Open an issue. Include:
- LiteLLM version (`pip show litellm`)
- Your guardrail config (redact any keys)
- The error or unexpected behaviour

## Known limitations

See the [Known Issues](README.md#known-issues) section in the README before opening an issue — the `default_on` workaround and provider model string requirement are intentional.
