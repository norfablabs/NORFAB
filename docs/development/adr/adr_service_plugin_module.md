# ADR - Packaged Python Service Plugins

## Status

Draft. This record replaces the unfinished Python module plugin tutorial. The
entry-point discovery described below already exists; a verified package example
and user-facing walkthrough remain documentation work.

## Context

Custom services need a reusable distribution mechanism when their worker code is
shared between NORFAB environments. Keeping a worker beside `inventory.yaml` is
useful for local development, but an installable Python package can declare its
own dependencies and distribute the worker independently of that environment.

## Decision

Use the existing `norfab.workers` Python entry-point group for packaged service
workers. Each entry-point name identifies a service, and its target identifies
the worker class. The class extends `NFPWorker` and exposes tasks through the
normal task registration mechanism.

`NorFab.register_plugins()` discovers installed entry points with
`importlib.metadata.entry_points()` and registers them by service name. A worker's
inventory selects that service through its `service` setting. Installing the
package must make its worker module and dependencies importable in the Python
environment running NORFAB.

Keep the inventory-based plugin mechanism available for local worker development;
this record introduces no new plugin loader or public client interface.

## Consequences

- Plugin authors can version and distribute workers as Python packages.
- Environments running those workers must install the package and its dependencies.
- Packaging does not change how clients submit tasks or retrieve results.
- The previous tutorial's instruction to create a plugin directory inside the
  NORFAB repository is not a requirement for a separately packaged worker.

## Documentation Follow-Up

Before publishing a complete packaged-plugin tutorial:

1. Provide a minimal worker with a small public task and accurate task docstring.
2. Show a package layout and a `pyproject.toml` entry in `norfab.workers`.
3. Verify package installation and discovery in the worker environment.
4. Show inventory selecting the registered service and starting its worker.
5. Verify a public-client job submission and its returned result.

Keep runnable instructions in Customization once these examples have been
verified. Do not present placeholder code blocks as working examples.

## References

- [Custom service plugins](../../customization/service_plugin_overview.md)
- [Local service plugin guide](../../customization/service_plugin_local.md)
- Discovery implementation: `norfab/core/nfapi.py`, `NorFab.register_plugins()`.
