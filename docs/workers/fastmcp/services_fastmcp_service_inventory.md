# FastMCP Worker Inventory

Content of `inventory.yaml` need to be updated to include FastMCP worker details:

``` yaml title="inventory.yaml"
broker:
  endpoint: "tcp://127.0.0.1:5555"
  shared_key: "CHANGE_ME"

workers:
  fastmcp-worker-1:
    - fastmcp/fastmcp-worker-1.yaml

topology:
  workers:
    - fastmcp-worker-1
```

To obtain broker `shared_key` run this command on broker:

```
cd <path/to/broker/inventory.yaml>
nfcli --show-broker-shared-key
```

Sample FastMCP worker inventory definition

!!! example

    === "Minimal"

        ``` yaml title="fastmcp/fastmcp-worker-1.yaml"
        service: fastmcp
        
        # MCP server bind settings
        host: "127.0.0.1"
        port: 8001

        # Optional bearer authentication for MCP streamable HTTP
        authentication_enabled: false
        auth_bearer:
          token_ttl: null
        
        # Optional sections reserved for future/extended configuration
        fastmcp: {}
        uvicorn: {}
        ```

    === "Allow specific services"

        ``` yaml title="fastmcp/fastmcp-worker-1.yaml"
        service: fastmcp
        
        host: "127.0.0.1"
        port: 8001
        
        tools:
          policy:
            - service: "nornir"
              tasks: ["*"]
              action: allow
            - service: "netbox"
              tasks: ["*"]
              action: allow
            - service: "*"
              tasks: ["*"]
              action: reject   # block everything else
        
        uvicorn: {}
        ```

    === "Allow specific tasks only"

        ``` yaml title="fastmcp/fastmcp-worker-1.yaml"
        service: fastmcp
        
        host: "127.0.0.1"
        port: 8001
        
        tools:
          policy:
            - service: "nornir"
              tasks: ["cli", "cfg_deploy"]
              action: allow
            - service: "netbox"
              tasks: ["get_*"]
              action: allow
            - service: "*"
              tasks: ["*"]
              action: reject   # block everything else
        
        uvicorn: {}
        ```

    === "Reject sensitive tasks"

        ``` yaml title="fastmcp/fastmcp-worker-1.yaml"
        service: fastmcp
        
        host: "127.0.0.1"
        port: 8001
        
        tools:
          policy:
            - service: "nornir"
              tasks: ["cfg_deploy", "cfg_rollback"]
              action: reject   # block destructive tasks
            # no further rules — everything else is allowed by default
        
        uvicorn: {}
        ```

    === "Allow all (default)"

        ``` yaml title="fastmcp/fastmcp-worker-1.yaml"
        service: fastmcp
        
        host: "127.0.0.1"
        port: 8001
        
        tools: {}   # omit policy to expose every discovered tool
        
        uvicorn: {}
        ```


**host**

IP address to bind the MCP HTTP server to. Default is `0.0.0.0`.
For local development and VS Code MCP integration, prefer `127.0.0.1`.

**port**

TCP port to serve MCP HTTP endpoint on. Default is `8001`.

---

## Authentication

FastMCP bearer authentication is disabled by default. Enable it with
`authentication_enabled: true` to require MCP clients to send
`Authorization: Bearer <token>` on the MCP streamable HTTP endpoint.

```yaml
service: fastmcp
host: "127.0.0.1"
port: 8001

authentication_enabled: true
auth_bearer:
  token_ttl: 86400
  issuer_url: "http://127.0.0.1:8001"
  resource_server_url: "http://127.0.0.1:8001"
  required_scopes: []
```

Tokens are stored in the FastMCP worker diskcache using the same
`bearer_token::<token>` key format as the FastAPI worker:

```python
nfclient.run_job(
    "fastmcp",
    "bearer_token_store",
    kwargs={"username": "automation", "token": "secret-token", "expire": 86400},
)
```

Use `bearer_token_list`, `bearer_token_check`, and `bearer_token_delete` to
inspect or remove tokens. Token management tasks are available through NorFab
client jobs and are not exposed as MCP tools.

---

## Tools And Prompts Policy

The optional `tools` section controls which NorFab service tasks are
exposed as MCP tools. The same policy also controls prompts associated with
those tasks. Rejecting a task hides both its tool and every prompt declared by
that task.

**tools.policy**

An ordered list of rule dictionaries. Each rule has three keys:

| Key | Type | Description |
|---|---|---|
| `service` | glob string | Matched against the NorFab service name (e.g. `nornir`, `net*`) |
| `tasks` | list of globs | Matched against the task name (e.g. `cli`, `cfg_*`, `*`) |
| `action` | `allow` / `reject` | What to do when the rule matches |

Rules are evaluated **in order**; the **first matching rule wins**. A task must
match both `service` and at least one pattern in `tasks` for a rule to apply.
If no rule matches, the task's MCP tool and prompts are **allowed**
(default-allow policy).

```yaml
tools:
  policy:
    - service: "nornir"
      tasks: ["cli", "cfg_*"]
      action: allow
    - service: "netbox"
      tasks: ["get_*"]
      action: allow
    - service: "*"
      tasks: ["*"]
      action: reject   # catch-all — block everything else
```

| Example rule | Effect |
|---|---|
| `service: "*", tasks: ["*"], action: allow` | Allow every task tool and its prompts (same as no rules) |
| `service: "nornir", tasks: ["*"], action: allow` + catch-all reject | Expose only Nornir task tools and prompts |
| `service: "nornir", tasks: ["cfg_*"], action: reject` | Block matching Nornir tools and their prompts, allow the rest |

!!! tip
    Task names can be inspected at runtime with the `show fastmcp tools` CLI
    command or the `get_tools` API call. Published prompts can be inspected
    with `show fastmcp prompts` or `get_prompts`.

---

## Tool Call Guardrails

FastMCP guardrails reject specific MCP tool calls by inspecting the call
arguments before the NorFab job is dispatched. They are useful for allowing a
flexible task such as `nornir.cli` while blocking unsafe command values.

Guardrails do not replace `tools.policy`. Policy decides whether a task is
published and callable. Guardrails decide whether one specific call to an
allowed task is acceptable.

Task authors can define default guardrails in task MCP metadata. FastMCP
inventory can add deployment-specific guardrails under `tools.guardrails`.
Built-in task guardrails are enabled by default.

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

`tools.guardrails` is a list of guardrail entries.

Set `tools.disable_builtin_guardrails: true` to ignore guardrails declared by
tasks. Inventory-defined guardrails still apply:

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

Inventory options:

| Key | Type | Description |
|---|---|---|
| `disable_builtin_guardrails` | boolean | Optional flag under `tools`; defaults to `false` |

Guardrail entry keys:

| Key | Type | Description |
|---|---|---|
| `service` | string | Exact NorFab service name, for example `nornir` |
| `task` | string | Exact NorFab task name, for example `cli` |
| `description` | string | Optional human-readable explanation for operators |
| `field` | string | Top-level tool argument field to inspect |
| `type` | `contains` / `equals` / `regex` | Match strategy |
| `match` | string or list of strings | Text value or regex value to match |
| `message` | string | Optional client-facing rejection message |

When `match` is a list, FastMCP rejects the call if any selected argument
value matches any configured match value. `contains` and `equals` checks are
always case-insensitive; regex checks use the flags declared in the regex
value.

!!! warning
    Guardrails inspect only the inline MCP call arguments. They do not
    download NorFab URLs or inspect content resolved later by service workers,
    such as `nf://cli/commands.txt` files rendered by the Nornir worker at
    runtime.

Use NFCLI to inspect effective guardrails for a published task:

```bash
show fastmcp tools service nornir name *cli*
```

Example with several regex values:

```yaml
tools:
  guardrails:
    - service: nornir
      task: cli
      description: Reject CLI commands that enter configuration mode.
      field: commands
      type: regex
      match:
        - "(?i)^\\s*configure\\s+terminal\\b.*"
        - "(?i)^\\s*configuration\\b.*"
        - "(?i)^\\s*conf\\s+t\\b.*"
      message: "MCP guardrail rejected a configuration mode command."
```

The Nornir `cli` task includes default MCP guardrails that reject `reboot` and
related reload or restart commands, configuration-mode commands such as
`configure terminal`, `configuration`, and `conf t`, and destructive or
state-changing commands such as `commit`, `delete`, `clear`, and `debug`.
It also rejects shell-mode commands such as `bash`, `shell`, `start shell`,
`request system shell`, and `guestshell`, OS/image/package operations, and
outbound session commands such as `ssh` and `telnet`.
Its built-in result guardrails also redact common network-platform and Linux
passwords, secrets, authentication keys, shadow hashes, and PEM private keys
from MCP-delivered CLI output.
The Nornir `cfg` task includes default MCP guardrails that reject operational
command escapes in configuration input, such as `do ...` and `run ...`, plus
reboot, reload, restart, delete, erase, zeroize, `ssh`, and `telnet` commands.

---

## Task Result Guardrails

FastMCP result guardrails inspect the aggregate result after the NorFab job has
completed but before the result is returned to the MCP client. The raw result
stored in the FastMCP client's job database is not changed. Configure
deployment rules under `tools.result_guardrails`:

```yaml
tools:
  result_guardrails:
    - service: "*"
      task: "*"
      description: Keep MCP task results below 256 KiB.
      type: limit
      limit: 262144
      message: The task result is too large to return through MCP.

    - service: nornir
      task: cli
      description: Redact labelled passwords.
      type: replace
      match: "(?i)(password\\s*[=:]\\s*)\\S+"
      replace: "\\1[REDACTED:PASSWORD]"

    - service: "*"
      task: "*"
      description: Withhold known instruction-injection content.
      type: regex
      match: "(?i)ignore (all |the )?previous instructions"
      message: Task result content was withheld for safety.
```

Result guardrail selectors use glob (`fnmatch`) matching. Task-owned rules from
`mcp.result_guardrails` run first in their declared order, followed by matching
inventory rules in inventory order. `tools.disable_builtin_guardrails: true`
disables both task-owned call and result guardrails while leaving inventory
rules enabled.

| Type | Required keys | Behavior |
|---|---|---|
| `limit` | `limit` (positive byte count) | Measures the compact JSON aggregate. If exceeded, returns one bounded base result containing `message` and the existing job UUID. |
| `replace` | `match`, `replace` | Recursively replaces matching string values below each worker's `result` and `diff`. |
| `regex` | `match` | Recursively detects matching string values below `result` and `diff` and replaces only the affected worker field with `message`. |

Guardrails run once in authored order. A limit rule measures the delivery copy
at the point where the rule appears. Dictionary keys and result metadata such as
`errors`, `messages`, and `resources` are not regex-inspected, although the
complete aggregate counts toward a `limit`.

!!! warning
    A job UUID locates the original database record; it is not an authorization
    credential. Raw stored results have not been sanitized and may be large or
    sensitive. Do not expose unrestricted raw-result retrieval to a model.

Effective result guardrails are included by `get_tools`, `show fastmcp tools`
when detailed tool data is requested, and `show fastmcp guardrails` under the
`result_guardrails` section for each matching tool.
