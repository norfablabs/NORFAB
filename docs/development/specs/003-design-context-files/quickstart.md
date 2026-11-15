# Validate Design Context Files

**Status**: Implemented. Core scenarios exercised by public-client integration tests. See [plan.md](plan.md) for results.

## Prerequisites

Use the repository's configured Netbox and FileSharing test environment.
From the repository root, install dependencies with:

```powershell
uv sync --locked --python 3.12 --extra full --extra docs
```

For data shapes and precedence, see [interface reference](contracts/design-context.md)
and [data model](data-model.md).

## Preview A YAML Design

Make `nf://netbox/data/defaults.yaml` available with:

```yaml
site: BRISBANE
```

Make `nf://netbox/designs/context-preview.yaml` available with:

```yaml
context:
  defaults: nf://netbox/data/defaults.yaml
sites:
  - name: "{{ context.defaults.site }}"
```

Using an established client:

```python
result = client.run_job(
    "netbox", "design_deploy",
    workers="any",
    kwargs={
        "design": "nf://netbox/designs/context-preview.yaml",
        "dry_run_render": True,
    },
)
```

Expected: rendered sites contain BRISBANE, result dry_run is true, and no objects
are written. Metadata may remain in preview text as with existing design metadata.

## Verify Core Behaviors

- Repeat using the Markdown example in the interface reference. Expect the same name.
- Supply task context `{"defaults": {"site": "SYDNEY"}}`. Expect SYDNEY.
  Repeat with a URL pointing to a missing file and task input replacing its key. Preview fails because every declared file must load.
- Use an existing Markdown context block for the same key. Expect Markdown to win
  unless task input overrides it. Confirm existing task-only block scope is retained.
- Use a YAML file containing a list or null. Verify the complete value is assigned.
- Use quoted Jinja text in a YAML source. Confirm it stays literal.
- Register a local Git remote following existing FileSharing test patterns.
  Use `git://<remote>/defaults.yaml` and expect the same loaded data.
- Use malformed YAML and an unsupported source URL separately. Expect failed task
  results identifying the key or URL, with no writes.

## Run Checks

From the repository root, run local tests with the documented test-root working
directory through uv's directory option. Configured external services are required:

```powershell
uv run --directory tests pytest services/netbox/test_designs.py -m netbox_design_deploy
uv run inv checks
uv run inv docs-build
```

For Docker execution, use the existing Netbox suite and pytest selection documented
in [the testing guide](../../norfab_developing_and_testing_framework.md).
Inspect generated reports and JUnit results. Do not infer success from startup alone.
These previews use no Netbox records and need no manifest entry.
