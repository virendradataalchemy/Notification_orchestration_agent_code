# Manual Scripts

This folder contains one-off and operator-driven scripts that are useful for:

- local smoke testing
- live provider verification
- database diagnostics
- tenant/demo environment checks

These files are not part of the automated `pytest` suite.

Suggested organization:

- `api/`: scripts that call HTTP endpoints
- `db/`: scripts that inspect database state
- `diagnostics/`: provider, config, and runtime checks
