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


**host**

IP address to bind the MCP HTTP server to. Default is `0.0.0.0`.
For local development and VS Code MCP integration, prefer `127.0.0.1`.

**port**

TCP port to serve MCP HTTP endpoint on. Default is `8001`.
