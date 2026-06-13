# ADR - MCP Task Prompts

## Status

Accepted

Date: 2026-06-13

## Coding Guidelines

These apply to all code written as part of this plan:

1. **Keep the codebase minimal** — write only what is needed. No speculative abstractions or future-proofing.
2. **Avoid excessive helper functions** — extract a helper when the logic is non-trivial or reused across two or more tasks. Keep extracted functions as plain module-level functions; do not use leading underscores.
3. **Linear, easy-to-follow logic** — code should read top-to-bottom with no surprising jumps. Prefer flat `if/elif/else` chains over layered function calls.
4. **No difficult constructs** — avoid metaclasses, decorators-on-decorators, `functools` tricks, nested closures, generator pipelines, or anything that makes stepping through a debugger awkward.
5. **Simple is better than clever** — if two approaches produce the same result, always choose the one a junior engineer can understand without context.
6. **No unnecessary classes** — do not wrap logic in a class just for the sake of grouping. Module-level functions are fine.
7. Use descriptive human readable names for variables, avoid using short name like s, or plo, exception could be list or dict comprehensions though.
8. If unsure about the shape of the data - ask, do not code overly safe data evaluation, talk with use to find out how to handle data.

## Context

NorFab worker tasks are registered by the `Task` decorator. The decorator
exports a serializable task schema containing the task name, description,
Pydantic input and output schemas, FastAPI metadata, MCP tool metadata, and
agent metadata. The `list_tasks` task makes this schema available to other
NorFab services.

The FastMCP worker currently:

1. Discovers active NorFab services through the broker.
2. Calls each service's `list_tasks` task.
3. Converts eligible task schemas into MCP `Tool` objects.
4. Publishes those tools through `tools/list`.
5. Routes `tools/call` back to the corresponding NorFab service and task.

MCP prompts are a separate protocol capability from tools. A prompt is a
user-selected, parameterized message template that helps a model use tools or
complete a workflow. Retrieving a prompt must return messages only; it must not
run the related NorFab task.

The initial prompts will explain different ways to use the Nornir `cli` task.
The design must also establish a reusable pattern for prompts on other NorFab
tasks.

References:

- MCP prompts specification:
  https://modelcontextprotocol.io/specification/2025-06-18/server/prompts
- MCP Python SDK `v1.27.2` FastMCP prompt implementation:
  https://github.com/modelcontextprotocol/python-sdk/blob/v1.27.2/src/mcp/server/fastmcp/server.py
- Existing MCP tool annotation plan:
  `docs/development/adr_mcp_tool_annotations_plan.md`
- Task Pydantic model guide:
  `docs/development/adr_tasks_pydantic_models_guide.md`

## Decision

NorFab will define MCP prompts as explicit, serializable metadata under the
existing `Task(..., mcp={...})` decorator argument.

The FastMCP worker will discover task tools and task prompts in the same
`list_tasks` request, but it will maintain separate MCP registries and protocol
handlers for them.

The initial implementation will support zero or more prompts per task. Tasks do
not receive automatically generated prompts. A prompt is published only when
its decorator explicitly includes it in `mcp["prompts"]`.

The Nornir `cli` task will initially demonstrate prompts that guide a model
through selecting devices, choosing operational commands, using the generated
MCP CLI tool, troubleshooting, and summarizing results. Retrieving any prompt
will not execute the CLI task.

## Goals

- Keep prompt ownership next to the task implementation inside its existing
  MCP metadata.
- Reuse the existing worker discovery path instead of building a second
  registration protocol.
- Keep the core `Task` decorator independent of the optional MCP package.
- Publish standards-compliant `Prompt`, `PromptArgument`, `PromptMessage`, and
  `GetPromptResult` data.
- Give prompt authors a small, predictable metadata contract.
- Prevent prompts for rejected or hidden tasks from leaking through MCP.
- Start with useful Nornir `cli` prompts and make the pattern reusable.

## Non-Goals

- Automatically converting every task docstring or Pydantic field into a
  prompt.
- Running a NorFab task during `prompts/get`.
- Letting prompt metadata bypass FastMCP task policy.
- Supporting prompt-defined Python callbacks in remote workers.
- Supporting images, audio, or embedded resources in the first version.
- Adding prompt authoring through inventory files.
- Adding prompt list-change notifications in the first version.
- Changing the behavior or input schema of the Nornir `cli` task.

## Task Decorator Contract

### Extend The Existing `mcp` Argument

Do not add a new `prompts` argument to `Task`. Reserve the `prompts` key inside
the existing `mcp` dictionary:

```python
@Task(
    input=SomeInput,
    output=SomeResult,
    mcp={
        # Existing keys continue to describe the MCP Tool.
        "annotations": {...},

        # NorFab extension consumed by FastMCP prompt publication.
        "prompts": [
            {...},
        ],
    },
)
```

This keeps all MCP-specific exposure decisions in one decorator argument and
associates prompts directly with the task and tool they explain.

The `mcp` values have these meanings:

| Value | Tool behavior | Prompt behavior |
| --- | --- | --- |
| omitted, `None`, or `{}` | Publish the task as a tool with default metadata. | Publish no prompts. |
| `False` | Publish no tool. | Publish no prompts. |
| dictionary without `prompts` | Publish a tool using the existing dictionary fields. | Publish no prompts. |
| dictionary with `prompts: []` | Publish a tool using all non-`prompts` fields. | Publish no prompts. |
| dictionary with a non-empty `prompts` list | Publish a tool using all non-`prompts` fields. | Publish each valid list entry. |

`mcp["prompts"]` is a NorFab metadata extension. It is not a field accepted by
the MCP SDK `Tool` model. The FastMCP worker must split the dictionary before
constructing protocol objects:

```python
mcp_metadata = dict(task["mcp"])
prompts_metadata = mcp_metadata.pop("prompts", [])

tool = types.Tool(
    name=derived_tool_name,
    description=task["description"],
    inputSchema=task["inputSchema"],
    outputSchema=task["outputSchema"],
    **mcp_metadata,
)
```

The split must operate on a copy. It must not mutate the task schema retained
for inspection, prompt rendering, or later discovery cycles.

The existing task schema shape remains unchanged. `make_task_schema()` and
`list_tasks` already expose the complete `mcp` dictionary, so prompt metadata
travels through the existing discovery contract as `schema["mcp"]["prompts"]`.
The `Task` implementation validates and normalizes the nested prompt list with
Pydantic before registering the task. It does not need another stored
attribute or a new top-level schema key.

No MCP classes are imported into `norfab.core.worker`. The decorator validates
plain Python data with core Pydantic and Jinja2 dependencies, then exposes
serializable dictionaries so workers without the optional MCP dependency
continue to operate normally.

### Reserved MCP Metadata Keys

Initially, `prompts` is the only NorFab-reserved key inside `mcp`.

All other top-level keys retain their existing meaning as keyword arguments for
the MCP SDK `Tool` model, such as `annotations`, `title`, and `icons`. The
FastMCP worker should keep an explicit set of reserved NorFab keys and remove
only those keys before `types.Tool(...)` construction. This avoids accidentally
dropping future MCP SDK tool fields.

Using a nested `tool` dictionary, for example
`mcp={"tool": {...}, "prompts": [...]}`, is not selected because it would require
migrating every existing task decorator and third-party worker plugin.

### Prompt Metadata

`mcp["prompts"]` is a list of prompt dictionaries. A list is a good fit because
it is simple to serialize, preserves author-defined server order, and allows
more workflows to be added without changing the decorator signature.

Each prompt requires its own stable task-local `name`. Without that field,
multiple prompts could not be uniquely addressed through MCP `prompts/get`.

The initial prompt entry contract is:

| Key | Type | Required | Purpose |
| --- | --- | --- | --- |
| `name` | string | yes | Stable task-local identifier used to derive the published MCP prompt name. |
| `title` | string | yes | Human-readable prompt title. |
| `description` | string | yes | Short description shown during discovery. |
| `arguments` | list | no | User-supplied string arguments. Defaults to an empty list. |
| `messages` | list | yes | Ordered prompt message templates. |

Each argument contains:

| Key | Type | Required | Purpose |
| --- | --- | --- | --- |
| `name` | string | yes | Argument identifier used by the message templates. |
| `description` | string | yes | Help text presented by the MCP client. |
| `required` | boolean | no | Whether the client must supply the argument. Defaults to false. |

Each message contains:

| Key | Type | Required | Purpose |
| --- | --- | --- | --- |
| `role` | `user` or `assistant` | yes | MCP prompt message role. |
| `content.type` | `text` | yes | Initial content type. |
| `content.text` | string | yes | Jinja2 message template. |

Prompt names must:

- Be unique within one task's `prompts` list.
- Use lowercase ASCII letters, digits, and underscores.
- Start with a letter.
- Remain stable after release because clients may save the published name.
- Describe the workflow, not repeat the task name, for example
  `collect_operational_data` or `troubleshoot`.

Only text content is supported initially. `Task` validates the complete prompt
list when the decorator is constructed. Unsupported roles, content types,
duplicate prompt or argument names, missing required keys, and references to
undeclared arguments raise a Pydantic validation error at the source.

### Is A Prompts List A Good Design?

Yes, provided the list is treated as a collection of distinct named workflows,
not as alternate wording for the same prompt.

It is a good design because:

- A task can support several meaningful user intents while retaining one
  authoritative tool schema.
- Each prompt can have different arguments and messages.
- The decorator remains serializable and plugin-friendly.
- FastMCP can index validated entries by their derived published names.
- Adding another prompt is additive and does not change existing prompt names.

The design has costs:

- Every prompt needs a stable local `name`.
- Duplicate names must be detected explicitly.
- Large lists can clutter MCP client prompt selection.
- Prompt-specific policy is more complex than task-level policy.
- Similar prompts can drift or contradict one another.

No hard prompt-count limit is proposed. As an authoring guideline, keep the
list small and add another prompt only when it represents a materially
different goal, required input, reasoning process, or output expectation.
Ordering is for deterministic server publication and inspection only; clients
may sort or present prompts differently and must address them by name.

If `prompts` is present, it must be a list. Do not accept a single dictionary,
`None`, or `False` as shorthand. Authors omit the key or use `prompts: []` when
the task has no prompts. A strict shape is easier to document, validate, and
extend.

### Illustrative Decorator Shape

The intended Nornir `cli` metadata shape is:

```python
@Task(
    input=CliInput,
    output=CliResult,
    fastapi={"methods": ["POST"]},
    mcp={
        "annotations": {
            "title": "Run CLI Commands",
            "readOnlyHint": False,
            "destructiveHint": True,
            "idempotentHint": False,
            "openWorldHint": True,
        },
        "prompts": [
            {
                "name": "collect_operational_data",
                "title": "Collect Operational Data",
                "description": "Plan and run operational CLI commands on selected devices.",
                "arguments": [
                    {
                        "name": "request",
                        "description": "Operational question or data collection objective.",
                        "required": True,
                    },
                    {
                        "name": "targets",
                        "description": "Optional device names, groups, platforms, or filter intent.",
                        "required": False,
                    },
                    {
                        "name": "commands",
                        "description": "Optional commands already selected by the user.",
                        "required": False,
                    },
                ],
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": "... data collection prompt template ...",
                        },
                    },
                ],
            },
            {
                "name": "troubleshoot",
                "title": "Troubleshoot Network Devices",
                "description": "Investigate a symptom using targeted operational CLI commands.",
                "arguments": [
                    {
                        "name": "symptom",
                        "description": "Observed fault or behavior to investigate.",
                        "required": True,
                    },
                    {
                        "name": "targets",
                        "description": "Optional devices or targeting constraints.",
                        "required": False,
                    },
                    {
                        "name": "context",
                        "description": "Optional topology, recent changes, or prior observations.",
                        "required": False,
                    },
                ],
                "messages": [
                    {
                        "role": "user",
                        "content": {
                            "type": "text",
                            "text": "... troubleshooting prompt template ...",
                        },
                    },
                ],
            },
        ],
    },
)
```

This is the reference contract implemented by the FastMCP worker.

## Prompt Naming

Each prompt entry supplies a task-local name. The FastMCP worker combines it
with the discovered service and task names because the service name is not
available when the task decorator runs.

Use this collision-resistant published name:

```text
service_<service_name>__task_<task_name>__prompt_<prompt_name>
```

The suffix is necessary because one task may publish multiple prompts. It also
makes the relationship to the callable tool visible to clients and operators.

For the illustrative Nornir CLI prompts:

```text
service_nornir__task_cli__prompt_collect_operational_data
service_nornir__task_cli__prompt_troubleshoot
```

The related tool remains:

```text
service_nornir__task_cli
```

Prompt names must be unique across the complete FastMCP server. The derived
service, task, and local prompt components provide that uniqueness without
requiring task authors to know deployment service names.

## Nornir CLI Prompts

### Collect Operational Data

The `collect_operational_data` prompt helps a model translate an operational
request into a safe and well-targeted call to
`service_nornir__task_cli`.

It is a usage workflow, not a copy of `CliInput`. Prompt arguments represent
user intent, while the tool input schema remains the authoritative source for
callable task parameters.

Its arguments are:

| Argument | Required | Meaning |
| --- | --- | --- |
| `request` | yes | The operational question or collection objective. |
| `targets` | no | Device names, groups, platforms, or natural-language targeting constraints. |
| `commands` | no | Commands the user already wants to run. |

All MCP prompt arguments are strings. A model may convert `commands` into a
tool argument list and `targets` into one or more Nornir filters.

The rendered prompt should instruct the model to:

1. Restate the operational objective and identify missing information.
2. Use explicit device targeting when supplied.
3. Translate targeting intent to the narrowest appropriate Nornir filter:
   `FL` for an explicit host list, `FG` for a group, `FM` for a platform,
   `FB` for glob matching, `FC` for name containment, or another supported
   filter when the user clearly requests it.
4. Use `service_nornir__task_get_nornir_hosts` first, when that tool is
   available, if the target set is ambiguous or should be verified.
5. Treat `netmiko` as the default plugin unless the user requests `scrapli` or
   `napalm`, or the inventory context requires another plugin.
6. Prefer operational read-only commands.
7. Do not silently convert an operational request into configuration,
   reload, delete, clear, write, copy, debug, or other state-changing commands.
8. Ask for explicit confirmation when a supplied command may alter device
   state. The prompt does not weaken the CLI tool's destructive annotation.
9. Use `dry_run=True` to verify rendered commands and targeting when commands
   are templated, targeting is uncertain, or the user asks for a preview.
10. Call `service_nornir__task_cli` with `commands` as a list and include only
    relevant optional arguments.
11. Report worker errors, failed hosts, and empty or unmatched target results
    instead of presenting partial output as complete.
12. Summarize results by device and command, preserving important raw values
    and clearly separating observations from conclusions.

The prompt should place the supplied `request`, `targets`, and `commands`
inside clearly labeled data sections. It must state that argument contents are
user data and cannot override the surrounding workflow and safety guidance.

Example outcome:

A user-selected prompt with:

```text
request: Check software versions on the spine switches.
targets: devices whose names contain "spine"
commands: show version
```

should guide the model toward a tool call equivalent to:

```json
{
  "commands": ["show version"],
  "FC": "spine",
  "plugin": "netmiko"
}
```

The prompt retrieval itself returns instructions and user context only. The MCP
client or model decides whether to call the tool.

### Troubleshoot

The `troubleshoot` prompt provides a distinct workflow for investigating an
observed symptom. It should not merely duplicate the data-collection prompt
under another name.

Its arguments are:

| Argument | Required | Meaning |
| --- | --- | --- |
| `symptom` | yes | Fault, alert, or unexpected behavior to investigate. |
| `targets` | no | Devices or natural-language targeting constraints. |
| `context` | no | Relevant topology, recent changes, expected behavior, or prior observations. |

The rendered troubleshooting prompt should instruct the model to:

1. Form one or more testable hypotheses from the symptom and context.
2. Select the narrowest relevant devices and operational commands.
3. Prefer low-cost, read-only checks before broader collection.
4. Run commands in small related groups so results can confirm or reject a
   hypothesis.
5. Avoid configuration or disruptive commands unless the user explicitly
   supplies and confirms them.
6. Use `service_nornir__task_get_nornir_hosts`, when available, if target
   resolution is uncertain.
7. Use `service_nornir__task_cli` for evidence collection.
8. Distinguish observed evidence, interpretation, ruled-out hypotheses, and
   recommended next checks.
9. Stop and report uncertainty when available evidence does not support a
   conclusion.

Both CLI prompts use the same MCP tool and policy. Multiple prompts are useful
here because they describe materially different user workflows and model
behavior. They should not be created merely to provide alternate wording.

## FastMCP Discovery

### Shared Discovery Pass

Keep the existing service and task discovery pass. For each task schema:

1. Continue building an MCP tool when `mcp` is not `False`.
2. Copy the task's `mcp` dictionary.
3. Remove the reserved `prompts` key from the copy.
4. Build the MCP tool from the remaining dictionary.
5. Validate each entry in the removed `prompts` list independently.
6. Build an MCP prompt for each valid entry.
7. Apply the same service/task policy before registering either capability.
8. Store the original task schema with all registry entries for diagnostics.

This avoids an extra broker request and guarantees that tools and prompts use
the same discovered service/task identity.

### Metadata Split

Split the metadata inline in the discovery loop:

```python
tool_metadata = dict(task["mcp"])
prompts_metadata = tool_metadata.pop("prompts", [])
```

The helper treats an absent `mcp["prompts"]` key as an empty list and returns a
fresh tool dictionary so discovery never changes worker-provided data. Prompt
shape validation has already happened in `Task`; FastMCP trusts the normalized
metadata and only translates it to MCP SDK models.

Tool construction must use only `tool_metadata`. Prompt registration must use
only `prompts_metadata`. This is the compatibility bridge between NorFab's
extended decorator contract and the MCP SDK's strict `types.Tool` model.

Applied to the current discovery loop, the existing direct expansion:

```python
task_tool = {
    "name": task["name"],
    "description": task["description"],
    "inputSchema": task["inputSchema"],
    "outputSchema": task["outputSchema"],
    **task["mcp"],
}
```

becomes conceptually:

```python
tool_metadata = dict(task["mcp"])
prompts_metadata = tool_metadata.pop("prompts", [])

task_tool = {
    "name": task["name"],
    "description": task["description"],
    "inputSchema": task["inputSchema"],
    "outputSchema": task["outputSchema"],
    **tool_metadata,
}

for prompt_metadata in prompts_metadata:
    register_task_prompt(task, prompt_metadata)
```

### Separate Registries

Keep separate runtime registries:

```text
norfab_services_tasks
norfab_services_prompts
```

The task registry continues to support tool listing and calls. The prompt
registry stores:

- The protocol `Prompt` definition used by `prompts/list`.
- A generated Pydantic model for MCP client arguments.
- The serializable message metadata used by `prompts/get`.
- The source service and task names.

An internal prompt entry can follow the existing tool registry pattern:

```python
worker.norfab_services_prompts[service][published_prompt_name] = {
    "prompt": types.Prompt(...),
    "metadata": prompt_metadata,
    "arguments_model": PromptArgumentsModel,
    "task": task,
}
```

The MCP protocol object and argument model are prepared once during discovery.
The original serializable metadata is retained for message rendering.

Separating registries prevents prompt data from changing the existing tool call
path and makes tool and prompt filtering explicit.

### Publication Handlers

Register low-level MCP handlers alongside the current tool handlers:

- `list_prompts` returns the discovered `Prompt` definitions.
- `get_prompt` resolves a published prompt name, validates arguments, renders
  message templates, and returns `GetPromptResult`.

The current `FastMCP` application already installs prompt protocol support.
NorFab will use low-level handlers because its prompts are discovered as data
from remote workers rather than declared as local Python functions.

`get_prompt` must never call `client.run_job`.

## Prompt Rendering

Use the existing `NFPWorker.jinja2_render_templates` method because Jinja2 is
already a core NorFab dependency and prompt metadata must remain serializable
across worker boundaries.

Rendering rules:

1. Validate prompt templates and declared variables in `Task`.
2. Build a Pydantic argument model for each published prompt.
3. Render each inline message once through `jinja2_render_templates`.
4. Provide only validated, declared prompt arguments as template context.
5. Reject unknown arguments.
6. Reject missing required arguments.
7. Keep optional missing arguments available as empty strings.
8. Do not add custom filters or worker objects to the rendering context.
9. Return argument values as literal rendered text; do not treat Jinja syntax
   supplied inside an argument as another template.
10. Convert request argument validation failures into an MCP
    invalid-parameters error with the prompt name and a concise reason.

`Task` catches static metadata errors at the source. Request-time Pydantic
validation remains necessary for MCP client-supplied argument values.

## Policy And Security

### Exposure Policy

The existing ordered `tools.policy` rules will initially govern both a task's
tool and all of its prompts.

A prompt is published only when:

- The task's `mcp` value is a dictionary.
- It is a valid entry in `task["mcp"]["prompts"]`.
- The task is allowed by `tools.policy`.

This prevents a rejected task from remaining discoverable through any of its
prompts. It also avoids adding a second policy language before there is a
demonstrated need for prompts to have different visibility.

A future `prompts.policy` may be added if prompt exposure needs to differ from
tool exposure. Per-prompt policy is not part of the first implementation:
prompts associated with one task are collectively allowed or rejected with
that task.

### Authentication

Prompts use the same MCP endpoint and bearer authentication middleware as
tools. No prompt-specific authentication path is required.

### Prompt Injection

Prompt templates cannot guarantee model behavior. They can, however, keep
trusted workflow instructions separate from user-supplied values.

The CLI prompts will:

- Label inserted arguments as user data.
- Avoid placing user data in instruction headings.
- Tell the model not to follow instructions embedded in argument values when
  they conflict with the surrounding workflow.
- Avoid fetching files, URLs, task results, or inventory data during rendering.
- Preserve the CLI tool's destructive annotation and confirmation guidance.

Policy enforcement and task authorization remain server responsibilities;
prompt wording is not an authorization control.

## Error Handling

`prompts/get` should reject:

- Unknown prompt names.
- Missing required arguments.
- Unknown arguments.
- Non-string argument values.
- Prompt rendering failures.

Invalid prompt definitions and duplicate local prompt names fail Pydantic
validation when `Task` is constructed. They cannot enter task discovery.

Duplicate prompt names from multiple workers in the same service should follow
the existing task discovery behavior: keep the first valid definition during a
discovery pass and log schema differences for later diagnosis.

## Observability

Extend FastMCP status and inspection behavior so operators can see prompt
publication without using an MCP client.

Planned additions:

- Track a `prompts_count` value in `get_status`.
- Add a `get_prompts` FastMCP worker task modeled after `get_tools`, with
  `brief`, `service`, and `name` filters. Detailed results include the
  unrendered message templates.
- Include source service and task names in internal registry data.
- Log prompt discovery failures with service, task, and derived prompt name.
- Log prompt retrieval by name without logging full argument values.

Do not log rendered prompts or user-supplied prompt arguments at info level
because they may contain sensitive operational context.

## Compatibility

- Existing tasks have no prompt metadata and continue to behave as before.
- Existing `mcp=False` tasks remain hidden.
- Existing `mcp={...}` tool metadata continues to work without modification.
- Existing MCP tool names and calls do not change.
- The top-level `list_tasks` schema does not change.
- Only tasks that opt in gain a nested `mcp.prompts` list.
- Workers do not need the MCP package to declare or report prompt metadata.
- FastMCP deployments with no prompts continue to return an empty prompt list.
- The current MCP dependency is pinned to `1.27.2`, which supports prompt
  titles, arguments, listing, retrieval, and text prompt messages.

Because prompt names extend the existing tool naming convention and live in a
separate MCP namespace, no tool compatibility migration is required.

## Alternatives Considered

### Generate Prompts From Pydantic Models

Rejected. Pydantic schemas describe valid tool arguments, but prompts describe
user workflows, decision points, safety guidance, and result interpretation.
Generating prompts would produce verbose parameter listings rather than useful
task guidance.

### Add A New `Task.prompts` Argument

Rejected. It would split MCP-specific exposure across two decorator arguments
and add a new top-level task schema key even though `mcp` already carries all
MCP publication metadata.

The selected nested design requires FastMCP to remove the reserved `prompts`
key before constructing `Tool`, but keeps the task-facing API cohesive.

### Replace Existing MCP Fields With `mcp.tool`

Rejected. A shape such as `mcp={"tool": {...}, "prompts": [...]}` has clearer
namespacing, but it would break all existing decorators and third-party worker
plugins that currently pass tool fields directly under `mcp`.

Keeping tool fields at the current level and reserving `mcp.prompts` provides a
backwards-compatible migration path.

### Use A Dictionary Keyed By Prompt Name

Considered:

```python
"prompts": {
    "collect_operational_data": {...},
    "troubleshoot": {...},
}
```

A dictionary naturally enforces unique keys and offers direct lookup. The list
form is selected because each prompt is a complete protocol-facing record,
including its name, and lists are easier to validate uniformly, preserve
author-defined server order, and extend with per-entry metadata.

The cost is that duplicate names require explicit validation and lookup is
linear during discovery. Prompt lists are expected to be small, and FastMCP
indexes validated prompts by published name, so runtime retrieval remains a
dictionary lookup.

### Register Prompt Functions In FastMCP

Rejected for discovered service prompts. FastMCP's local prompt decorator is a
good fit for prompts implemented in the same process, but NorFab discovers
task metadata from separate worker processes. Python callables cannot be
serialized through `list_tasks`.

### Store Prompts In FastMCP Inventory

Rejected as the primary model. It would separate task guidance from the task
that owns it, duplicate service/task names, and make plugin-provided prompts
harder to distribute.

### Allow Only One Prompt Per Task

Rejected. Tasks such as `cli` support materially different workflows, including
general data collection and hypothesis-driven troubleshooting. Restricting a
task to one prompt would either produce an overly broad prompt or force later
schema migration from an object to a list.

### Publish Prompts For Policy-Rejected Tasks

Rejected. It leaks task capability and gives clients instructions for a tool
they cannot call.

## Implementation Plan

### Phase 1 - Core Task Metadata

1. Document `prompts` as a reserved optional list inside `Task.mcp`.
2. Keep `make_task_schema()` unchanged because it already serializes the full
   `mcp` dictionary.
3. Add core Pydantic prompt models and validate prompt metadata in `Task`
   without importing MCP SDK classes.
4. Update `Task` documentation to distinguish direct MCP tool fields from the
   nested NorFab prompts extension.
5. Update `list_tasks` tests to verify that the prompts list is preserved
   unchanged.

### Phase 2 - Nornir CLI Prompts

1. Add the prompts list to `CliTask.cli` under
   `mcp={"annotations": {...}, "prompts": [...]}`.
2. Add `collect_operational_data` with `request`, `targets`, and `commands`
   arguments.
3. Add `troubleshoot` with `symptom`, `targets`, and `context` arguments.
4. Add the workflow, targeting, safety, dry-run, troubleshooting, execution,
   and result-summary guidance defined in this ADR.
5. Keep `CliInput`, `CliResult`, task behavior, and MCP tool annotations
   unchanged.

### Phase 3 - FastMCP Discovery And Publication

1. Add the separate prompt registry to `FastMCPWorker`.
2. Copy task MCP metadata and remove `mcp.prompts` inline during discovery.
3. Ensure `mcp.prompts` is removed before `types.Tool(...)` construction.
4. Extend the existing task discovery pass to translate validated prompt
   entries into MCP SDK models.
5. Derive each published prompt name from service, task, and local prompt name.
6. Apply `mcp=False` and `tools.policy` checks before prompt registration.
7. Add `list_prompts` and `get_prompt` MCP handlers.
8. Render through `NFPWorker.jinja2_render_templates`.
9. Ensure `get_prompt` never dispatches a NorFab job.
10. Add prompt counts and the `get_prompts` inspection task.

### Phase 4 - Documentation

1. Update the FastMCP service overview to describe tools and prompts.
2. Document the prompt naming convention.
3. Document prompt discovery and retrieval with an MCP client.
4. Add `get_prompts` to FastMCP service and CLI documentation.
5. Add examples showing the Nornir CLI prompts in VS Code or another
   MCP-capable client.
6. Explain that prompts are user-selected guidance and do not run tasks by
   themselves.

## Test Plan

### Task Decorator Tests

- A task with `mcp={}` reports the same empty MCP dictionary.
- A task with existing tool annotations reports them unchanged.
- A valid `mcp.prompts` list survives `make_task_schema()` and `list_tasks`
  unchanged.
- `mcp=False` remains `False` and cannot publish prompts.
- `mcp={"prompts": []}` publishes the tool without prompts.
- Two prompt entries remain in their authored order.
- Existing `fastapi`, `mcp`, and `agent` metadata remain unchanged.
- Invalid containers, roles, content, names, duplicate names, and undeclared
  template variables fail when `Task` is constructed.

### FastMCP Discovery Tests

- The Nornir `cli` prompts are discovered as
  `service_nornir__task_cli__prompt_collect_operational_data` and
  `service_nornir__task_cli__prompt_troubleshoot`.
- A task without `mcp.prompts` does not publish prompts.
- An `mcp=False` task does not publish prompts.
- `mcp.prompts` is not forwarded to `types.Tool`.
- Existing tool annotations are still forwarded to `types.Tool`.
- Discovery does not mutate the original task `mcp` dictionary.
- A policy-rejected task publishes neither its tool nor its prompts.
- Repeated discovery does not duplicate prompts.

### MCP Protocol Tests

Using `ClientSession`:

- `list_prompts()` returns both CLI prompt names, titles, descriptions, and
  arguments.
- `get_prompt()` renders each CLI prompt with its own argument contract.
- Optional arguments may be omitted.
- Missing `request` fails for `collect_operational_data`.
- Missing `symptom` fails for `troubleshoot`.
- Unknown prompt names fail.
- Unknown or non-string arguments fail.
- Jinja syntax inside an argument remains literal and is not evaluated again.
- Retrieving a prompt does not create a Nornir CLI job.
- Prompt access works through bearer authentication when enabled.

### Regression Tests

- Existing FastMCP tool listing and tool calls continue to pass.
- The CLI MCP tool still accepts `CliInput` arguments.
- `get_status` reports correct tool and prompt counts.
- `get_prompts` filtering behaves like `get_tools` filtering.
- Workers that do not install the MCP extra can still import and use `Task`.

## Rollout

1. Implement and test the decorator contract.
2. Add the CLI prompts and verify their serialized task schema.
3. Add FastMCP prompt discovery, rendering, and protocol tests.
4. Add operator inspection and documentation.
5. Use the CLI prompts as the reference pattern before adding prompts to other
   tasks.

Good next candidates are task-oriented workflows where model guidance adds
more value than schema repetition, such as Nornir tests, NetBox sync checks,
and Containerlab inspection.

## Consequences

### Positive

- Task authors can ship multiple focused MCP workflows with their task.
- Third-party NorFab worker plugins can expose prompts without modifying the
  FastMCP worker.
- Prompt and tool discovery remain synchronized.
- MCP clients receive a curated workflow instead of a generated schema dump.
- One task can expose focused workflows without broadening its tool API.
- The first CLI prompts encourage narrow targeting, previews, troubleshooting
  discipline, and transparent failure reporting.

### Negative

- Prompt metadata becomes another task contract that requires review and
  testing.
- Prompt definitions are validated when task modules load, so malformed
  metadata prevents that task from registering.
- A list contract requires stable local names and duplicate-name validation.
- Too many overlapping prompts can make client discovery noisy and confuse
  users about which workflow to select.
- Dynamic discovery without list-change notifications may require clients to
  re-list prompts after startup discovery.

### Deferred Follow-Up

- A dedicated `prompts.policy`.
- Prompt list-change notifications.
- Prompt argument completion.
- Non-text prompt content.
- Shared prompt fragments or centrally managed prompt libraries.
- Versioning prompt contracts independently from task schemas.
