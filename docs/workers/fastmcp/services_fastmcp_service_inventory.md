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
