---
tags:
  - fastmcp
  - mcp
---

# FastMCP Guardrails

## Overview

FastMCP guardrails check tool calls before a job runs and filter results before
returning them to the MCP client. They can reject a call, ask for approval,
redact sensitive text, or limit response size.

There are three layers of built-in and user-configurable guardrails:

| Layer | What It Does | Setup |
|---|---|---|
| Built-in task guardrails | Apply restrictions and output redaction specific to a task, such as Nornir `cli`. Not every task has them. | Enabled by default. |
| User-configured inventory guardrails | Add rejection or approval rules under `tools.guardrails` and output rules under `tools.result_guardrails`. | Configure in your FastMCP worker inventory. |
| Built-in server result guardrails | Redact common secrets and limit the combined response to 100000 characters for every task. | Enabled by default. |

Add the examples below to the [FastMCP worker inventory](services_fastmcp_service_inventory.md),
merging them into its existing `tools` section. Restart the FastMCP worker after
changing inventory. User rules add to built-in rules. They do not override a
rejection. A matching inventory `characters_limit` rule replaces the server
default size limit while keeping built-in redaction.

These guardrails apply only to calls through FastMCP. Direct NorFab calls to
other services are unaffected.

## Where Guardrails Run

```mermaid
flowchart TD
    A[MCP tool call] --> B{Tool allowed by policy?}
    B -->|No| X[Reject call - no job submitted]
    B -->|Yes| C{"Input guardrails: built-in task rules, then user inventory rules"}
    C -->|Matching reject rule| X
    C -->|Approval required| D[Request confirmation from MCP client]
    D -->|Declined, invalid, unsupported or timed out| E[Return approval error - no job submitted]
    D -->|All approvals granted| F[Submit NorFab job]
    C -->|No matching rules| F
    F --> G[NorFab completes the job]
    G --> I[Built-in task result guardrails]
    I --> J[User inventory result guardrails]
    J --> K[Built-in server redaction and character limit]
    K --> L[Return guarded response to MCP client]
```

Any matching rejection stops the call before approval is requested. Rejections
return an entry keyed by the FastMCP worker name, with `service: fastmcp`,
`result: {}`, `failed: false`, and the reason in `errors`. Result
rules run in the order shown. An exceeded size limit stops result processing.
Built-in rules are skipped when disabled.

`tools.policy` controls which tasks are exposed and callable. Guardrails inspect
calls to those allowed tasks. See [tool policy configuration](services_fastmcp_service_inventory.md#tools-and-prompts-policy).

## Configure Input Guardrails

Add rules under `tools.guardrails` to reject calls or ask for approval. Each rule
selects a service, task, argument, and value to match.

=== "Reject Commands"

    Block retrieval of the running configuration through Nornir CLI. `reject` is the default
    action when `action` is omitted.

    ```yaml
    tools:
      guardrails:
        - service: nornir
          task: cli
          field: commands
          type: contains
          match: show running-config
          action: reject
          message: Retrieving the running configuration is not allowed through MCP.
    ```

=== "Request Approval"

    Ask before a Nornir configuration containing `commit` is submitted. The
    `cfg` task receives configuration through `config`.

    ```yaml
    tools:
      guardrails:
        - service: nornir
          task: cfg
          field: config
          type: contains
          match: commit
          action: request_approval
          message: Approve committing this configuration?
    ```

=== "Match Several Patterns"

    Reject a call when any command matches either expression.

    ```yaml
    tools:
      guardrails:
        - service: nornir
          task: cli
          field: commands
          type: regex
          match:
            - '(?i)^\s*show\s+running-config\b'
            - '(?i)^\s*show\s+tech-support\b'
          message: Configuration and support dumps are not allowed through MCP.
    ```

| Key | Meaning |
|---|---|
| `service`, `task` | Exact service and task names. Input rules do not support wildcard selectors. |
| `description` | Optional explanation for operators. |
| `field` | Required top-level argument to inspect. A missing argument does not match. |
| `type` | `contains`, `equals`, or `regex`. |
| `match` | Required string or list of strings. Any matching value triggers the action. |
| `action` | `reject` or `request_approval`. Defaults to `reject`. |
| `message` | Optional rejection or approval message shown to the client. |

Lists of argument values are inspected individually. `contains` and `equals`
are case-insensitive. Regex matching uses the flags in the expression, such as
`(?i)` for case-insensitive matching.

!!! warning
    Input guardrails inspect inline arguments only. They do not download or
    inspect the contents of `nf://` files, templates, or other references
    resolved later by a worker.

### Approve A Call

Use an MCP client that supports approval forms (MCP form elicitation).
Configure the client to ask a human rather than answer automatically. The
prompt contains the service, task, and your `message`, without task arguments.
Write a message that clearly describes what needs approval.

Each matching approval rule asks separately. All requests must be accepted with
`approve: true`, each within 120 seconds. Declining, cancelling, answering false,
an invalid reply, or a client that cannot handle approval stops the call.
No job is submitted. The response is keyed by the FastMCP worker name, with
`result: {}` and one `errors` entry.
Approval cannot override a rejection from another rule.

### Built-In Task Guardrails: Nornir CLI

Nornir `cli` includes protections without any inventory configuration:

- Before submission, reject restart commands, configuration-mode commands,
  `commit`, destructive operations, shell access, software changes, and outbound
  `ssh` or `telnet` sessions.
- Before returning output, redact device passwords, SNMP communities,
  RADIUS/TACACS keys, authentication keys, HTTP credentials, Linux password
  hashes, and private-key contents.

For example, `reload` is rejected before a job is submitted. Returned text such
as `username admin secret 5 example-secret` becomes
`username admin secret 5 REDACTED`.

Nornir `cfg` has different rules, including rejection of operational command
escapes and selected destructive commands. Check a task's rules before adding
approval: an inventory rule requesting approval for `cli` command `reload`
cannot override its built-in rejection.

## Configure Result Guardrails

Result guardrails change the response delivered through MCP after execution.
They do not undo the task or modify the original result stored in the job
database.

### Built-In Server Result Guardrails

After task and inventory result rules, FastMCP applies these built-in server
protections:

- Replace common labelled passwords, secrets, tokens, and credential keys with
  `REDACTED`. Coverage includes authentication headers and cookies, connection
  URL credentials, common network secrets, private-key blocks, password hashes,
  and recognizable service tokens.
- Limit the combined response across all workers to **100000 characters**.
  An oversized response is omitted, rather than truncated. It returns
  an entry for each responding worker with `result: {}`, `failed: false`,
  and one `errors`
  entry naming the FastMCP worker and explaining the limit
  and how to configure it. The task itself has already run.

For example, `password hunter42` becomes `password REDACTED`, and
`https://user:hunter42@example.com` becomes
`https://user:REDACTED@example.com`.

Replacement and regex rules inspect string values within each worker's
`result` and `diff`, including nested values. They do not inspect dictionary
keys or metadata such as `errors`, `messages`, and `resources`. A dictionary
key named `password` alone does not cause its value to be redacted. Encoded
content is not decoded. Public keys, ordinary identifiers, and unlabelled
hashes are generally preserved. Redaction does not guarantee detection of
every secret.

### Add User Inventory Result Rules

Result selectors support glob patterns such as `*` and `get_*`.

=== "Limit Characters"

    Add a lower character limit while keeping the built-in protections.
    The count includes the full combined result structure, not just output text.

    ```yaml
    tools:
      result_guardrails:
        - service: '*'
          task: '*'
          type: characters_limit
          limit: 16384
          message: Result omitted because it exceeds the 16384-character MCP limit.
    ```

=== "Redact A Custom Pattern"

    Extend redaction for an application-specific credential pattern.
    Single-quoted YAML preserves regex backslashes and replacement references.

    ```yaml
    tools:
      result_guardrails:
        - service: '*'
          task: '*'
          type: replace
          match: '(?i)(deployment_code\s*[=:]\s*)\S+'
          replace: '\1REDACTED'
    ```

=== "Withhold Matching Output"

    Replace a worker's affected `result` or `diff` field when a known phrase
    appears. Phrase matching alone is not comprehensive prompt-injection protection.

    ```yaml
    tools:
      result_guardrails:
        - service: '*'
          task: '*'
          type: regex
          match: '(?i)ignore (all |the )?previous instructions'
          message: Output withheld because it matched a configured content rule.
    ```

=== "Limit Bytes"

    Add a byte limit alongside the default character limit. Both apply.
    This rule measures the compact JSON response size in bytes. This differs from a character
    count, especially for non-ASCII output. When exceeded, this rule returns its
    message in `result` with `failed: false` and the available job UUID.

    ```yaml
    tools:
      result_guardrails:
        - service: '*'
          task: '*'
          type: limit
          limit: 262144
          message: Result exceeds the 256 KiB MCP limit.
    ```

| Type | Required Fields | Effect |
|---|---|---|
| `characters_limit` | `limit` | Omit results exceeding a positive character count. |
| `limit` | `limit` | Replace results exceeding a positive byte count with a message. |
| `replace` | `match`, `replace` | Replace matching text. `match` accepts a regex or list of regexes. |
| `regex` | `match` | Withhold an affected worker field. `match` accepts a regex or list of regexes. |

Every inventory result rule requires `service`, `task`, and `type`, plus the
fields listed above. `description` is optional. `message` customizes limit and
regex responses. Inventory rules run in listed order. Put replacement rules
before a size limit to measure the response after those replacements.

## Change Or Disable Defaults

`tools.disable_builtin_guardrails: true` disables both task-specific input and
result defaults and the server's default redaction and character limit.
Inventory rules still apply. This setting does not disable tool policy.

To lower or raise the limit, add an inventory `characters_limit` rule. It
replaces the server default for matching tasks while keeping built-in redaction
and input restrictions. A byte `limit` rule does not replace the character limit.

To remove built-in protections entirely, set `disable_builtin_guardrails: true`.
The example below disables all built-in rules and supplies custom replacements.

```yaml
tools:
  disable_builtin_guardrails: true
  result_guardrails:
    - service: '*'
      task: '*'
      type: replace
      match: '(?i)(password\s*[=:]\s*)\S+'
      replace: '\1REDACTED'
    - service: '*'
      task: '*'
      type: characters_limit
      limit: 65536
      message: Result omitted because it exceeds the 65536-character MCP limit.
```

This example replaces the broad built-in protection with a narrow password rule
and a larger limit. It does not reproduce all built-in redaction patterns.

## Inspect Guardrails

Use [Get Tools](services_fastmcp_service_task_get_tools.md) to inspect configured
rules for a published task.

=== "CLI"

    Show input and result guardrails:

    ```bash
    show fastmcp guardrails
    show fastmcp guardrails service nornir name *cfg*
    ```

    To view the full tool definition:

    ```bash
    show fastmcp tools service nornir name *cfg*
    ```

=== "Python"

    With a connected NorFab client:

    ```python
    client.run_job(
        service="fastmcp",
        task="get_tools",
        workers=["fastmcp-worker-1"],
        kwargs={"service": "nornir", "name": "*cfg*", "brief": False},
    )
    ```

Detailed tool information includes task-specific and matching inventory rules.
The server-wide default redaction and character limit are applied to calls but
are not listed there.

!!! warning
    Stored results can contain secrets and large output. A job UUID identifies
    a record; it is not an access credential. Restrict access to original job
    results separately from MCP response guardrails.
