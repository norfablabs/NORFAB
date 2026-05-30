# Task Pydantic Models Guide

This guide defines the model style for NORFAB worker tasks. It is written for agentic AI contributors: follow the checklist, keep changes scoped, and ask when a type or validation rule is ambiguous.

## Goal

Every `@Task(...)` worker function should have explicit Pydantic models for:

- **Input**: all task kwargs accepted by the public task API.
- **Output**: the returned `Result` shape, including a typed `result` payload when practical.

These models are used by worker runtime validation, FastAPI/OpenAPI schema generation, MCP/agent tool schemas, docs generation, and later PICLE shell models. PICLE builds interactive command trees from Pydantic models, so field names, aliases, descriptions, defaults, and validators must be CLI-friendly.

## Placement

Keep task models in the same module as the task unless the same model is shared across modules.

Preferred module layout:

```python
# helpers

# --------------------------------------------------------------------------
# <FEATURE> TASKS MODELS
# --------------------------------------------------------------------------

class GetThingsInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    ...

class ThingPayload(BaseModel):
    ...

class GetThingsResult(Result):
    result: dict[StrictStr, ThingPayload] = Field(
        {},
        description="Thing data keyed by device name",
    )


class NetboxThingTasks:
    @Task(
        input=GetThingsInput,
        output=GetThingsResult,
        fastapi={"methods": ["GET"], "schema": NetboxFastApiArgs.model_json_schema()},
    )
    def get_things(...):
        ...
```

Use existing examples in `bgp_peerings_tasks.py`, `ip_tasks.py`, `interfaces_tasks.py`, and `topology_tasks.py` for local naming and validator style.

## Input Models

Model names should be `<TaskNamePascalCase>Input`, for example `CreatePrefixInput` for `create_prefix`.

Rules:

- Include every public task kwarg except `self`, `job`, `progress`, internal-only kwargs, `*args`, and `**kwargs`.
- Inherit common worker arguments where appropriate, for example `NetboxCommonArgs`.
- Define task input models with `use_enum_values=True` and `populate_by_name=True`.
- Do not use `Optional`. For nullable fields use `Union[None, T]`.
- Prefer strict scalar types: `StrictStr`, `StrictInt`, `StrictBool`, `StrictFloat`.
- Prefer concrete collections: `list[StrictStr]`, `dict[StrictStr, Any]`, `list[dict[StrictStr, Any]]`.
- Use `Field(...)` for required values and `Field(default, ...)` for optional values.
- Put useful one-line `description` text on every field. This becomes API, MCP, agent, and PICLE help text.
- Mention units in field descriptions when known, for example `Timeout in seconds`.
- Put additional usage samples in the `Field(..., examples=[...])` attribute instead of expanding the description.
- Use aliases for CLI/API names that should contain hyphens, and enable `populate_by_name=True`.
- For boolean CLI presence flags, add `json_schema_extra={"presence": True}` when the shell should treat the field as a flag.
- If unsure about a type or acceptable values, stop and ask. Do not guess for NetBox object payloads, polymorphic input, or state-changing tasks.

Example:

```python
class SyncDeviceIpInput(NetboxCommonArgs, use_enum_values=True, populate_by_name=True):
    devices: Union[None, list[StrictStr]] = Field(
        None,
        description="List of NetBox device names to sync IP addresses for",
    )
    create_prefixes: StrictBool = Field(
        True,
        description="Create missing NetBox prefixes for discovered IP addresses",
        alias="create-prefixes",
        json_schema_extra={"presence": True},
    )
    filter_by_name: Union[None, StrictStr] = Field(
        None,
        description="Glob pattern to restrict interfaces by name",
        alias="filter-by-name",
        examples=["Loopback*", "Ethernet*", "Port-Channel*"],
    )
```

## Output Models

Model names should be `<TaskNamePascalCase>Result`.

Rules:

- Inherit from `norfab.models.Result`.
- Override `result` with a typed payload whenever the task result shape is stable.
- Create small payload models for repeated objects or nested structures.
- Keep dynamic NetBox API dictionaries as `dict[StrictStr, Any]` when the schema is intentionally pass-through.
- Keep output models simple unless the result shape is fully known; prefer `dict[StrictStr, Any]` over complex unions that guess every possible branch.
- Do not use `default_factory`; use the local model style with direct defaults such as `{}` or `[]`.
- If the task returns different dry-run and commit payload shapes, either model both explicitly with `Union[...]` or use a named payload with broad fields and document the variant.
- If an exact output shape depends on NetBox plugins, OpenAPI schemas, or arbitrary GraphQL fields, use `dict[StrictStr, Any]` and explain why in the field description.

Example:

```python
class SyncActionsPayload(BaseModel):
    created: list[StrictStr] = Field([])
    updated: list[StrictStr] = Field([])
    in_sync: list[StrictStr] = Field([])


class SyncDeviceIpResult(Result):
    result: dict[StrictStr, SyncActionsPayload] = Field(
        {},
        description="IP sync actions keyed by device name",
    )
```

## Validators

Use validators when fields depend on each other or when a field accepts more than one ergonomic input form.

Good uses:

- Require at least one selector, for example `devices`, `filters`, or `query`.
- Reject invalid combinations, for example host prefix plus peer IP creation.
- Normalize CLI-friendly strings into lists where the task already supports that behavior.
- Validate mutually exclusive fields, such as `object_id` versus `filters`.

Keep validation close to the model and prefer `model_validator(mode="after")` for cross-field checks.

```python
@model_validator(mode="after")
def validate_selectors(self) -> "GetInterfacesInput":
    if not self.devices and not self.filters:
        raise ValueError("Provide devices or filters")
    return self
```

## PICLE Readiness

PICLE uses Pydantic models to build interactive shell commands, completions, validation, and inline help. Design task models so they can be reused or mirrored in `norfab/clients/nfcli_shell/`.

Checklist:

- Reuse task input models in PICLE shell models whenever possible by inheriting from the task input model.
- Do not redeclare fields already provided by the task input model unless the shell needs a different CLI shape, enum, source method, or output behavior.
- Put CLI-only overrides in the shell model and keep them minimal.
- Field names should be readable as command words.
- Use aliases for user-facing hyphenated command arguments, for example `interface-regex`.
- Descriptions should be one-line, short, and actionable.
- Prefer enums for small fixed value sets.
- Add source methods only when completion data can be fetched cheaply and safely.
- Avoid deeply nested required objects for common CLI workflows; provide bulk/list fields only where the task naturally needs them.
- Keep model defaults aligned with task function defaults.

## Agent Checklist

When adding or auditing task models:

1. Read `CLAUDE.md`.
2. List all task functions with `@Task(...)`.
3. For each task, compare the function signature with the `input=` model.
4. Add or update the input model only after confirming each field type, default, alias, and validation rule.
5. Add or update the output model; use typed payloads for stable results and documented dictionaries for dynamic results.
6. Update the decorator with `input=<InputModel>` and `output=<ResultModel>`.
7. Run focused validation: import the module, generate schemas, and execute available tests for the touched service.
8. Do not refactor unrelated code while adding models.

Useful audit command:

```bash
rg -n "@Task\\(" norfab/workers
```

## Common Pitfalls

- Do not rely on the dynamic model generated by `Task.make_input_model` for production tasks.
- Do not use `Optional`; use `Union[None, T]`.
- Do not leave untyped `list` or `dict` unless the payload is intentionally arbitrary.
- Do not invent NetBox payload schemas when task behavior passes data through to NetBox; ask or model as `dict[StrictStr, Any]` with a clear description.
- Do not make PICLE-only choices that break Python API compatibility.
- Do not change task behavior while adding validation unless the change is explicitly approved.
