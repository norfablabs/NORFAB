# ADR - FastMCP Task Call Guardrails

## Status

Accepted

Date: 2026-07-05

## Overview

FastMCP exposes NorFab service tasks as MCP tools. Existing FastMCP policy
controls whether a service task is published and callable:

```yaml
tools:
  policy:
    - service: nornir
      tasks: ["cli"]
      action: allow
    - service: "*"
      tasks: ["*"]
      action: reject
```

Policy answers the coarse question: "May this MCP server expose and call this
task?"

Guardrails answer the next question: "Is this particular task call acceptable
with these arguments?"

For example, the Nornir `cli` task is intentionally exposed as a flexible MCP
tool, but an MCP client should not be able to submit disruptive commands such
as `reboot` or `configure terminal` by accident. The task can provide a
default guardrail set that rejects any value in the `commands` argument
matching unsafe regex checks. A FastMCP operator can also define additional
guardrails in the FastMCP worker inventory for the same task.

## Decision

NorFab will add FastMCP task call guardrails as serializable metadata attached
to task definitions and as inventory-defined overlays in the FastMCP worker.

Task-owned defaults live under the existing `Task(..., mcp={...})` metadata:

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
        "guardrails": [
            {
                "description": "Reject CLI commands that reboot, reload, or restart devices.",
                "field": "commands",
                "type": "regex",
                "match": [
                    "(?im)^\\s*(reboot|reload|restart)\\b.*",
                    "(?im)^\\s*request\\s+system\\s+(reboot|power-off)\\b.*",
                    "(?im)^\\s*admin\\s+reboot\\b.*",
                ],
                "message": "MCP guardrail rejected a reboot, reload, or restart command.",
            },
            {
                "description": "Reject CLI commands that enter configuration mode.",
                "field": "commands",
                "type": "regex",
                "match": [
                    "(?im)^\\s*configure\\s+(terminal|private|exclusive)\\b.*",
                    "(?im)^\\s*configuration\\b.*",
                    "(?im)^\\s*conf\\s+t\\b.*",
                    "(?im)^\\s*edit\\b.*",
                    "(?im)^\\s*system-view\\b.*",
                ],
                "message": "MCP guardrail rejected a configuration mode command.",
            },
            {
                "description": "Reject CLI commands that commit, delete, debug, or clear state.",
                "field": "commands",
                "type": "regex",
                "match": [
                    "(?im)^\\s*commit\\b.*",
                    "(?im)^\\s*(delete|erase|format|factory-reset|clear|debug|undebug|monitor|test|reset)\\b.*",
                    "(?im)^\\s*request\\s+system\\s+zeroize\\b.*",
                ],
                "message": "MCP guardrail rejected a destructive or state-changing command.",
            },
            {
                "description": "Reject CLI commands that enter device shell modes.",
                "field": "commands",
                "type": "regex",
                "match": [
                    "(?im)^\\s*(bash|shell|sh)\\b.*",
                    "(?im)^\\s*start\\s+shell\\b.*",
                    "(?im)^\\s*request\\s+system\\s+shell\\b.*",
                    "(?im)^\\s*run\\s+(bash|shell|sh)\\b.*",
                    "(?im)^\\s*(guestshell|run\\s+guestshell)\\b.*",
                ],
                "message": "MCP guardrail rejected a shell mode command.",
            },
            {
                "description": "Reject CLI commands that change device software or boot images.",
                "field": "commands",
                "type": "regex",
                "match": [
                    "(?im)^\\s*install\\b.*",
                    "(?im)^\\s*request\\s+system\\s+software\\b.*",
                    "(?im)^\\s*software\\s+(install|add|activate|commit|rollback|clean|remove)\\b.*",
                    "(?im)^\\s*boot\\s+system\\b.*",
                    "(?im)^\\s*package\\s+(install|add|delete|remove|activate)\\b.*",
                ],
                "message": "MCP guardrail rejected an OS/image/package operation command.",
            },
            {
                "description": "Reject CLI commands that open outbound device sessions.",
                "field": "commands",
                "type": "regex",
                "match": [
                    "(?im)^\\s*(ssh|telnet)\\b.*",
                ],
                "message": "MCP guardrail rejected an outbound session command.",
            },
        ],
        "prompts": [
            ...
        ],
    },
)
def cli(...):
    ...
```

FastMCP inventory can add deployment-specific guardrails. Built-in task
guardrails are enabled by default:

```yaml
service: fastmcp
host: "127.0.0.1"
port: 8001

tools:
  guardrails:
    - service: nornir
      task: cli
      description: Reject reload commands from MCP clients.
      field: commands
      type: regex
      match: "(?i)^\\s*reload\\b.*"
      message: "MCP guardrail rejected a reload command."
```

Operators can disable task-defined guardrails while keeping inventory-defined
guardrails active:

```yaml
tools:
  disable_builtin_guardrails: true
  guardrails:
    - service: nornir
      task: cli
      field: commands
      type: regex
      match: "(?i)^\\s*reload\\b.*"
      message: "MCP guardrail rejected a reload command."
```

The FastMCP worker evaluates all matching guardrails before calling
`self.client.run_job(...)`. If any guardrail matches, the MCP tool call is
rejected and no NorFab job is dispatched.

## Goals

- Let task authors publish safe defaults next to task description, input
  schema, output schema, annotations, and prompts.
- Let FastMCP operators add local guardrails per service/task from inventory.
- Keep guardrails serializable in `list_tasks` output.
- Keep the core `Task` decorator independent of the MCP SDK.
- Evaluate guardrails at the FastMCP boundary before job dispatch.
- Return a clear MCP error when a call is rejected.
- Keep the first implementation small, readable, and deterministic.

## Non-Goals

- Replacing `tools.policy`; policy remains the task exposure and coarse
  authorization layer.
- Replacing service-side validation, authorization, dry-run behavior, or
  task-specific safety checks.
- Adding an external policy engine.
- Evaluating guardrails against task output.
- Supporting arbitrary Python callbacks in guardrail definitions.
- Automatically generating guardrails from task descriptions or JSON Schema.
- Publishing guardrails as MCP `Tool` fields; guardrails are a NorFab extension
  consumed by the FastMCP worker.

## Relationship To Existing Controls

| Control | Scope | Enforcement point | Effect |
| --- | --- | --- | --- |
| `mcp=False` | Task definition | Discovery | Task is not exposed through MCP. |
| `tools.policy` | Service/task name | Discovery and call time | Task is hidden or rejected. |
| Guardrails | Service/task arguments | Call time | Specific call is rejected before dispatch. |
| Task input model | Task arguments | Worker execution | Invalid arguments fail Pydantic validation. |
| Task logic | Full task behavior | Worker execution | Service-specific safety remains authoritative. |

Guardrails are evaluated only after the tool name has resolved to a registered
NorFab service/task and after `tools.policy` has allowed the call.

## Task Decorator Contract

### Extend The Existing `mcp` Argument

Do not add a new `guardrails` argument to `Task`. Reserve the `guardrails` key
inside the existing `mcp` dictionary:

```python
@Task(
    input=SomeInput,
    output=SomeOutput,
    mcp={
        "annotations": {...},
        "guardrails": [
            {...},
        ],
        "prompts": [
            {...},
        ],
    },
)
```

The `mcp` values have these meanings:

| Value | Tool behavior | Guardrail behavior |
| --- | --- | --- |
| omitted, `None`, or `{}` | Publish the task as a tool with default metadata. | No task-defined guardrails. |
| `False` | Publish no tool. | No guardrails are evaluated through MCP because the task is hidden. |
| dictionary without `guardrails` | Publish the task as a tool. | No task-defined guardrails. |
| dictionary with `guardrails: []` | Publish the task as a tool. | No task-defined guardrails. |
| dictionary with guardrail entries | Publish the task as a tool. | Evaluate guardrails on each MCP tool call. |

`mcp["guardrails"]` is a NorFab metadata extension. It is not accepted by the
MCP SDK `Tool` model. The FastMCP worker must remove it from the copied MCP
metadata before constructing `types.Tool(...)`, the same way it removes
`prompts`:

```python
tool_metadata = dict(task["mcp"])
prompts_metadata = tool_metadata.pop("prompts", [])
guardrails_metadata = tool_metadata.pop("guardrails", [])

tool = types.Tool(
    name=derived_tool_name,
    description=task["description"],
    inputSchema=task["inputSchema"],
    outputSchema=task["outputSchema"],
    **tool_metadata,
)
```

The split must operate on a copy. It must not mutate the task schema retained
for diagnostics, prompt rendering, or later discovery cycles.

### Reserved MCP Metadata Keys

The NorFab-reserved keys inside `mcp` become:

- `prompts`
- `guardrails`

All other top-level keys retain their existing meaning as keyword arguments for
the MCP SDK `Tool` model.

### Guardrail Metadata

`mcp["guardrails"]` is a list of guardrail dictionaries. A list preserves
author-defined order and allows a task to define more than one independent
check.

Each guardrail has this contract:

| Key | Type | Required | Purpose |
| --- | --- | --- | --- |
| `description` | string | no | Human-readable explanation for operators. |
| `field` | string | yes | Top-level argument field to inspect. |
| `type` | `contains`, `equals`, or `regex` | yes | Match strategy. |
| `match` | string or list of strings | yes | Text checks to compare, or Python regular expressions used with `re.search` when `type` is `regex`. |
| `message` | string | no | Client-facing rejection message. |

The `field` selector is intentionally small:

- `commands` selects the top-level `commands` argument.
- When the selected value is a list, each list item is inspected.
- String, dictionary, and other non-list values are converted to strings and
  inspected as one value.
- Missing fields do not match. Required argument validation remains the task
  input model's responsibility.

All selected scalar values are compared as strings. When `match` is a list,
entries are evaluated with OR semantics. A guardrail matches when any selected
scalar value matches any configured check. `contains` and `equals` are always
case-insensitive; regex checks use the flags declared in the regex value.

Guardrails inspect only inline MCP call arguments. They do not resolve NorFab
URLs, download Filesharing content, or inspect templates rendered later by the
target service worker. For example, `commands: "nf://cli/commands.txt"` is
checked as that literal path string, not as the file's eventual contents.

Invalid guardrail metadata must fail early:

- Task-defined guardrails are validated by the FastMCP worker during discovery
  before they are attached to a tool.
- Inventory-defined guardrails are validated during discovery before they are
  attached to a tool.
- Invalid regex checks are rejected during validation, not during a tool
  call. When `match` is a list, every regex in the list is validated.

## Inventory Contract

FastMCP inventory guardrails live under `tools.guardrails` as a list of
guardrail entries. Built-in task guardrails are enabled by default. Set
`tools.disable_builtin_guardrails: true` to skip task-defined guardrails while
still applying inventory-defined guardrails.

Each inventory guardrail entry declares the service and task it applies to:

```yaml
tools:
  guardrails:
    - service: nornir
      task: cli
      description: Reject commit confirmed commands through MCP.
      field: commands
      type: contains
      match: commit confirmed
      message: "MCP guardrail rejected a commit confirmed command."
```

Inventory options:

| Key | Type | Required | Purpose |
| --- | --- | --- | --- |
| `disable_builtin_guardrails` | boolean | no | Optional flag under `tools`; defaults to `false`. |

Inventory guardrail entry fields:

| Key | Type | Required | Purpose |
| --- | --- | --- | --- |
| `service` | string | yes | Exact NorFab service name, for example `nornir`. |
| `task` | string | yes | Exact NorFab task name, for example `cli`. |
| `description` | string | no | Human-readable explanation for operators. |
| `field` | string | yes | Top-level argument field to inspect. |
| `type` | `contains`, `equals`, or `regex` | yes | Match strategy. |
| `match` | string or list of strings | yes | Match check or checks. |
| `message` | string | no | Client-facing rejection message. |

Inventory guardrails are appended after task-defined guardrails unless
`tools.disable_builtin_guardrails` is `true`.

## Enforcement Flow

FastMCP tool discovery will store guardrails with the registered tool data:

```python
result[task["service"]][task_tool["name"]] = {
    "tool": types.Tool(**task_tool),
    "task": task,
    "guardrails": effective_guardrails,
}
```

MCP `tools/call` will follow this sequence:

1. Log the requested tool name.
2. Resolve the MCP tool name to a registered NorFab service/task.
3. Enforce `tools.policy` again at call time.
4. Load the registered tool's effective guardrails.
5. Evaluate guardrails against the raw MCP `arguments` dictionary.
6. Reject the call on the first matching guardrail.
7. Dispatch the NorFab job only when no guardrail matches.

The enforcement point must sit immediately before:

```python
self.client.run_job(
    service=service,
    task=task_name,
    kwargs=arguments,
    workers="all",
)
```

This prevents a rejected call from creating a NorFab job, reaching a service
worker, or producing partial side effects.

## Rejection Behavior

When a guardrail matches, FastMCP will:

- Return an MCP error to the caller.
- Include the guardrail `message` when provided.
- Log a warning with service, task, tool name, field, and match type.
- Avoid logging the full argument payload in the rejection warning.
- Not call `self.client.run_job(...)`.

Example client-facing message:

```text
MCP tool call 'service_nornir__task_cli' rejected by guardrail
MCP guardrail rejected a configuration mode command.
```

## Nornir CLI Default Guardrails

The Nornir `cli` task should ship with six default MCP guardrails:

```python
MCP_GUARDRAILS = [
    {
        "description": "Reject CLI commands that reboot, reload, or restart devices.",
        "field": "commands",
        "type": "regex",
        "match": [
            "(?im)^\\s*(reboot|reload|restart)\\b.*",
            "(?im)^\\s*request\\s+system\\s+(reboot|power-off)\\b.*",
            "(?im)^\\s*admin\\s+reboot\\b.*",
        ],
        "message": "MCP guardrail rejected a reboot, reload, or restart command.",
    },
    {
        "description": "Reject CLI commands that enter configuration mode.",
        "field": "commands",
        "type": "regex",
        "match": [
            "(?im)^\\s*configure\\s+(terminal|private|exclusive)\\b.*",
            "(?im)^\\s*configuration\\b.*",
            "(?im)^\\s*conf\\s+t\\b.*",
            "(?im)^\\s*edit\\b.*",
            "(?im)^\\s*system-view\\b.*",
        ],
        "message": "MCP guardrail rejected a configuration mode command.",
    },
    {
        "description": "Reject CLI commands that commit, delete, debug, or clear state.",
        "field": "commands",
        "type": "regex",
        "match": [
            "(?im)^\\s*commit\\b.*",
            "(?im)^\\s*(delete|erase|format|factory-reset|clear|debug|undebug|monitor|test|reset)\\b.*",
            "(?im)^\\s*request\\s+system\\s+zeroize\\b.*",
        ],
        "message": "MCP guardrail rejected a destructive or state-changing command.",
    },
    {
        "description": "Reject CLI commands that enter device shell modes.",
        "field": "commands",
        "type": "regex",
        "match": [
            "(?im)^\\s*(bash|shell|sh)\\b.*",
            "(?im)^\\s*start\\s+shell\\b.*",
            "(?im)^\\s*request\\s+system\\s+shell\\b.*",
            "(?im)^\\s*run\\s+(bash|shell|sh)\\b.*",
            "(?im)^\\s*(guestshell|run\\s+guestshell)\\b.*",
        ],
        "message": "MCP guardrail rejected a shell mode command.",
    },
    {
        "description": "Reject CLI commands that change device software or boot images.",
        "field": "commands",
        "type": "regex",
        "match": [
            "(?im)^\\s*install\\b.*",
            "(?im)^\\s*request\\s+system\\s+software\\b.*",
            "(?im)^\\s*software\\s+(install|add|activate|commit|rollback|clean|remove)\\b.*",
            "(?im)^\\s*boot\\s+system\\b.*",
            "(?im)^\\s*package\\s+(install|add|delete|remove|activate)\\b.*",
        ],
        "message": "MCP guardrail rejected an OS/image/package operation command.",
    },
    {
        "description": "Reject CLI commands that open outbound device sessions.",
        "field": "commands",
        "type": "regex",
        "match": [
            "(?im)^\\s*(ssh|telnet)\\b.*",
        ],
        "message": "MCP guardrail rejected an outbound session command.",
    },
]
```

These guardrails apply whether `commands` is a string or a list of strings:

```json
{"commands": "show version"}
```

passes, while:

```json
{"commands": ["show version", "conf t"]}
```

is rejected before FastMCP dispatches the NorFab job.

The guardrails apply even when `dry_run=true`. `dry_run` is a service task
feature, while FastMCP guardrails protect the MCP boundary before task
execution.

## Inspection

FastMCP does not publish guardrails through MCP `tools/list` because MCP
`Tool` has no guardrail field.

NorFab-side inspection is available through `fastmcp.get_tools` when
`brief=False`. Tool definitions returned by this task include the effective
guardrails after inventory overlays, not only task-defined defaults.

## Implementation Notes

Core worker changes:

1. Keep `mcp["guardrails"]` as plain serializable task metadata in the task
   schema. Do not add FastMCP guardrail validation models to core worker code.

FastMCP worker changes:

1. Add FastMCP-local Pydantic models for guardrail metadata.
2. During discovery, validate task-defined guardrails unless
   `tools.disable_builtin_guardrails` is `true`, validate inventory-defined
   guardrails, and append matching inventory entries.
3. During discovery, remove `guardrails` from the copied tool metadata before
   constructing `types.Tool(...)`.
4. Store effective guardrails with each registered tool.
5. During `call_tool`, evaluate guardrails before `client.run_job(...)`.
6. Keep logic flat and explicit. Do not introduce a generic policy engine.

Nornir worker changes:

1. Add the default reboot/reload/restart, configuration-mode, and destructive
   command guardrails to the `cli` task MCP metadata.

## Testing

Unit tests should cover:

- FastMCP accepts valid guardrail metadata.
- FastMCP rejects invalid match types.
- FastMCP rejects invalid regex checks.
- FastMCP strips `guardrails` before constructing `types.Tool`.
- Inventory guardrails append to task-defined guardrails.
- `tools.disable_builtin_guardrails` skips task-defined guardrails while
  keeping inventory-defined guardrails active.
- `contains`, `equals`, and `regex` matching work for string values,
  list-valued `match`, and list-valued task arguments.
- Missing fields do not match.
- A rejected call does not call `client.run_job(...)`.

Service tests should cover:

- `service_nornir__task_cli` accepts safe commands such as `show version`.
- `service_nornir__task_cli` rejects `commands=["reboot"]`,
  `commands=["configure terminal"]`, and `commands=["conf t"]`.
- Inventory-defined guardrails reject an additional rule without changing
  the Nornir task source.
- `tools.policy` rejection still hides tools and prompts before guardrails are
  considered.

## Consequences

- FastMCP gains a payload-aware safety layer without changing the broker,
  client API, or service task execution model.
- Task authors can document and enforce MCP-specific safety expectations in
  the same metadata block already used for annotations and prompts.
- Operators can make local MCP deployments stricter without forking service
  task code.
- Guardrails are intentionally conservative. They reject matching calls; they
  do not rewrite arguments, request confirmation, or dispatch dry-run previews.
- Complex authorization remains outside this feature and belongs to the wider
  NorFab AAA and policy architecture.
