# Regression Fixtures

All real files in this directory are already publicly available government
regulatory records from Regulations.gov and the public Mirrulations dataset.
Including exact copies here does not disclose private or previously unavailable
information. They are committed solely for reproducible parser, alignment, and
Markdown-conversion tests.

Each case is stored under `regression_cases/<case-id>/` and contains:

- `case.yaml`: provenance, SHA-256 hashes, and expected structural assertions;
- `source/`: exact public source objects; and
- optionally `expected/`: human-reviewed golden outputs.

Tests discover cases from `case.yaml`; adding a case does not require a bespoke
Python test. Use the fixture helper to copy only explicitly selected public
objects and generate hashes. The helper never treats current generated output as
approved expected output.

## Adding a regression

```shell
.venv/bin/python scripts/add_regression_fixture.py --help
```

After adding a case, edit its assertions and review conversion output before
adding or updating any golden files.