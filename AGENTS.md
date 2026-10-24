# AGENTS.md - NorFab Repository Guide

## Working Rules

- Read the relevant guides below before changing code, tests, or documentation; follow existing patterns.
- Keep implementations simple and direct. Avoid unnecessary abstractions, compatibility paths, and helpers used only once or twice.
- Preserve public task arguments and client interfaces unless a change is explicitly requested.
- Validate data at the appropriate boundary; avoid repeating checks deeper in the implementation.
- Keep task Google-style docstrings accurate. Document every argument, the result, important behavior, limitations, and relevant errors.
- Start logging and `job.event` messages with lowercase letters. Use `severity` for event severity.
- Fix spelling mistakes in docstrings, comments, and variable names you change.

## Repository Map

NorFab is a cross-platform network automation framework. Clients submit jobs through a ZeroMQ broker to service workers using the NorFab Protocol (NFP).

| Area | Location |
| --- | --- |
| Lifecycle, broker, client, inventory, protocol, and worker base | `norfab/core/` |
| Service workers and task implementations | `norfab/workers/` |
| CLI, Robot Framework, Textual, and NFWeb clients | `norfab/clients/` |
| Shared Pydantic models | `norfab/models/` |
| CLI entry point | `norfab/utils/nfcli.py` |
| Service integration tests | `tests/services/` |
| Client and CLI tests | `tests/clients/`, `tests/nfcli/` |
| Fixtures and test inventory | `tests/conftest.py`, `tests/nf_tests_inventory/` |
| Documentation and Docker environments | `docs/`, `docker/` |

Workers extend `NFPWorker`; `@task` exposes methods to clients. Worker plugins are registered under `project.entry-points."norfab.workers"` in `pyproject.toml`. Consult that file for current dependencies, Python support, extras, entry points, and lint settings rather than duplicating them here.

## Testing

Follow [NORFAB Testing Framework](docs/development/testing/norfab_testing_framework.md) when writing or running tests:

- Always use integration tests through the public client interface when possible, integeation tests are preferred
- Keep tests small and focused. Extend related tests; add a dedicated test when existing tests are unrelated.
- Run commands from the repository root; use the guide for suite selection, build options, and reports.

### Netbox Test Data

Read and maintain [tests/netbox_data_manifest.json](tests/netbox_data_manifest.json) when adding or changing tests that use Netbox data.

- Record only Netbox database records and address space that tests read, create, update, or delete, including ownership and cleanup.
- Tests that mutate Netbox must use their own records and address space. Never reuse data owned by other tests; clean up only records the test owns.
- Do not record local files, file-fetch behavior, temporary scripts, caches, or other resources outside Netbox. Tests that use no Netbox data need no entry, even when exercising a Netbox worker task.

## Documentation

Follow the [documentation style guide](docs/development/documentation_style_guide.md).

- Do not add an Inputs section to service task pages. The Python API reference renders arguments from the task's Google-style docstring.
- Record user-facing changes in [the changelog](docs/norfab_changelog.md) and relevant task or developer documentation.
- Update [the feature catalogue](docs/norfab_features.md) only for notable capabilities relevant to technical evaluation or RFPs, or to correct materially inaccurate entries after a change, deprecation, or removal. Minor enhancements, fixes, refactors, and internal performance improvements do not need catalogue entries.
- Keep catalogue entries concise; verify capabilities, interfaces, use cases, limitations, and links. Update its **Last updated** date only when the catalogue changes.

## Development Commands

Use Poetry and Invoke from the repository root. List available tasks with `poetry run inv --list`.

```bash
poetry run inv checks             # Non-mutating Black, Ruff, and Vulture checks
poetry run inv format             # Format with Black
poetry run inv lint               # Run Ruff
poetry run inv dead-code          # Report dead code without suppression or auto-fixes
poetry run inv docs-build
poetry run inv docs-serve
poetry run inv docker-tests-build
poetry run inv docker-tests-core
poetry run inv docker-tests-all
```

## Task-Specific Guides

- [Task Pydantic models](docs/development/tasks_pydantic_models_guide.md)
- [NFWeb development](docs/development/nfweb_developer_guide.md)
- [Invoke automation decisions](docs/development/adr/adr_invoke_developer_automation.md)
- [Docker test commands](docker/norfab-docker-tests/README.md)
