# Contributing

Thanks for your interest in improving Commerce System Demo.

## Development setup

1. Clone the repository.
2. Create and activate a Python 3.11 virtual environment.
3. Install dependencies:

```bash
python -m pip install --upgrade pip
pip install -e ".[dev]"
```

4. Start the local stack when needed:

```bash
docker compose up -d
```

5. Run the fast test suite before opening a pull request:

```bash
pytest
```

## Branching and workflow

- Use a feature branch for your work.
- Keep changes focused and reviewable.
- Prefer small, well-described pull requests.
- Update docs and tests alongside code changes when relevant.

## Coding standards

- Follow the existing Python style used in the project.
- Keep functions and modules small and explicit.
- Preserve async/database patterns and existing observability instrumentation.
- Add or update tests for bug fixes and new features.

## Running tests

Fast suite:

```bash
pytest
```

Performance benchmarks (opt-in):

```bash
pytest -m performance
```

## Submitting changes

- Open a pull request with a clear summary of what changed and why.
- Include the context for any bug fix, behavior change, or new feature.
- Mention manual verification steps when applicable.
- Link any related issue or discussion.

## Reporting issues

Before opening a new issue, please:

- Search for existing issues to avoid duplicates.
- Include the relevant environment details, steps to reproduce, and expected behavior.
- Share logs or screenshots when helpful.

## Code of conduct

Please keep discussions constructive and respectful. We aim to maintain a welcoming and professional environment for contributors.
