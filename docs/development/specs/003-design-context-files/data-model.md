# Design Context Data Model

**Status**: Implemented.

## File Source Mapping

Add `context` to the existing `DesignDocument` metadata model.

| Field | Type | Default | Meaning |
| --- | --- | --- | --- |
| context | Dictionary of strict string keys and URL strings | {} | YAML sources keyed by effective context name |

Keys must be non-empty. Names remain dictionary keys, with bracket access available
when dot access is unsuitable. Values identify nf:// or git:// YAML files.
Supported source suffixes are .yaml and .yml.
Initial Pydantic model validation checks mapping shape, every source scheme and YAML suffix. Preparation loads every source and reports fetch/parse errors before writes. Existing YAML duplicate-key behavior
is preserved. Duplicate Markdown metadata/context definitions keep existing rejection.

## Loaded Value

Each complete YAML document becomes one value at its declared key.
Supported roots include dictionary, list, string, number, boolean and null.
Empty YAML produces null. Existing safe YAML loading rules govern nested values
and tags. No executable constructors or recursive URL expansion are added.
No loaded string is evaluated as Jinja.

## Effective Context

Precedence is task input above Markdown context above file defaults.
Presence, rather than truthiness, determines whether a key overrides a default.
Replacement applies to a whole top-level value. Unrelated keys remain.
Schema validation occurs after assembly and retains existing transformation rules.

Sequence: parse task context, process Markdown blocks with task input only,
load all declared file values, merge design-file/Markdown/task dictionaries, validate through optional input
schema, render the design, then use existing deployment processing.
Dictionary designs skip template rendering as before.

## Netbox Context Data

`config_context` and `local_context_data` remain deployment collections.
The source mapping is metadata and is never dispatched to a Netbox object handler.
No database schema, result schema, lifecycle or persistent entity changes.
