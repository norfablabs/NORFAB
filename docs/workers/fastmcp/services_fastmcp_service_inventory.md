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

## Tools Section

The optional `tools` section controls which NorFab service tasks are
exposed as MCP tools.

**tools.policy**

An ordered list of rule dictionaries. Each rule has three keys:

| Key | Type | Description |
|---|---|---|
| `service` | glob string | Matched against the NorFab service name (e.g. `nornir`, `net*`) |
| `tasks` | list of globs | Matched against the task name (e.g. `cli`, `cfg_*`, `*`) |
| `action` | `allow` / `reject` | What to do when the rule matches |

Rules are evaluated **in order**; the **first matching rule wins**. A task must
match both `service` and at least one pattern in `tasks` for a rule to apply.
If no rule matches, the tool is **allowed** (default-allow policy).

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
| `service: "*", tasks: ["*"], action: allow` | Allow every tool (same as no rules) |
| `service: "nornir", tasks: ["*"], action: allow` + catch-all reject | Expose only Nornir tools |
| `service: "nornir", tasks: ["cfg_*"], action: reject` | Block all Nornir `cfg_*` tasks, allow the rest |

!!! tip
    Task names can be inspected at runtime with the `show fastmcp tools` CLI
    command or the `get_tools` API call.
