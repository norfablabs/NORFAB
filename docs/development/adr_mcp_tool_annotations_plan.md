# ADR - MCP Tool Annotations Plan

## Overview

Add MCP tool annotations to NorFab worker tasks exposed through the FastMCP
worker. NorFab's `Task` decorator already accepts an `mcp` dictionary and the
FastMCP worker expands that dictionary into `mcp.types.Tool(...)`, so task
decorators can supply MCP SDK fields directly.

Use the SDK field name `annotations`:

```python
@Task(
    input=GetVersionInput,
    output=GetVersionResult,
    fastapi={"methods": ["GET"]},
    mcp={
        "annotations": {
            "title": "Get Version",
            "readOnlyHint": True,
            "destructiveHint": False,
            "idempotentHint": True,
            "openWorldHint": False,
        }
    },
)
```

The supported annotation fields come from MCP `ToolAnnotations`:
`title`, `readOnlyHint`, `destructiveHint`, `idempotentHint`, and
`openWorldHint`.

Reference:
https://github.com/modelcontextprotocol/python-sdk/blob/616476f6927a5c64213ea97bbd36a7466f410775/src/mcp/types/_types.py#L1090

---

## Decision

Every task exposed to MCP should define a human-readable `annotations.title`
and the four behavior hints. Tasks that explicitly set `mcp=False` stay hidden
from MCP and are documented here as not applicable.

---

## Classification Rules

- Read-only inspection tasks use `readOnlyHint=True`, `destructiveHint=False`,
  `idempotentHint=True`.
- Tasks that create, update, delete, restart, push configuration, execute
  arbitrary plugins, or run arbitrary remote commands use `readOnlyHint=False`.
- Destructive means the tool can delete data, overwrite configuration, interrupt
  services, or run arbitrary actions that may do so.
- Idempotent means repeating the same call should not create additional state or
  progressively change the target beyond the first successful call.
- `openWorldHint=True` is used when a task reaches external systems or dynamic
  environments such as NetBox, live network devices, Docker/containerlab, or
  arbitrary agents/workflows.
- `openWorldHint=False` is used for local NorFab metadata, configured local file
  roots, local cache operations, and FastAPI/FastMCP service registration.

---

## Task Annotation Matrix

### Agent Worker

| File | Task | Title | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `agent_worker/agent_worker.py` | `get_version` | Get Version | true | false | true | false | Local package metadata. |
| `agent_worker/agent_worker.py` | `get_inventory` | Get Inventory | true | false | true | false | Local agent inventory. |
| `agent_worker/agent_worker.py` | `get_status` | Get Status | true | false | true | false | Local health status. |
| `agent_worker/agent_worker.py` | `invoke` | Invoke Agent | false | true | false | true | Agent execution may call tools, external APIs, or state-changing actions. |

### Containerlab Worker

| File | Task | Title | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `containerlab_worker/containerlab_worker.py` | `get_version` | Get Version | true | false | true | false | Local package metadata. |
| `containerlab_worker/containerlab_worker.py` | `get_inventory` | Get Inventory | true | false | true | false | Local worker inventory. |
| `containerlab_worker/containerlab_worker.py` | `get_containerlab_status` | Get Containerlab Status | true | false | true | true | Inspects local containerlab/Docker runtime. |
| `containerlab_worker/containerlab_worker.py` | `get_running_labs` | Get Running Labs | true | false | true | true | Reads dynamic lab runtime state. |
| `containerlab_worker/containerlab_worker.py` | `run_containerlab_command` | Run Containerlab Command | false | true | false | true | Arbitrary containerlab command can mutate or delete labs. |
| `containerlab_worker/containerlab_worker.py` | `deploy` | Deploy Lab | false | false | false | true | Creates or changes lab runtime resources. |
| `containerlab_worker/containerlab_worker.py` | `destroy_lab` | Destroy Lab | false | true | true | true | Deletes lab resources; repeated destroy should converge. |
| `containerlab_worker/containerlab_worker.py` | `inspect` | Inspect Lab | true | false | true | true | Reads lab runtime state. |
| `containerlab_worker/containerlab_worker.py` | `save` | Save Lab | false | true | true | true | Writes persisted device configuration. |
| `containerlab_worker/containerlab_worker.py` | `restart_lab` | Restart Lab | false | true | false | true | Interrupts lab services. |
| `containerlab_worker/containerlab_worker.py` | `get_nornir_inventory` | Get Nornir Inventory | true | false | true | true | Reads generated inventory from lab state. |
| `containerlab_worker/containerlab_worker.py` | `deploy_netbox` | Deploy NetBox Lab | false | false | false | true | Creates lab resources from NetBox-derived topology. |

### FakeNOS Worker

| File | Task | Title | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `fakenos_worker/fakenos_worker.py` | `get_version` | Get Version | true | false | true | false | Local package metadata. |
| `fakenos_worker/fakenos_worker.py` | `get_inventory` | Get Inventory | true | false | true | false | Local worker inventory. |
| `fakenos_worker/fakenos_worker.py` | `stop` | Stop FakeNOS Network | false | true | true | false | Stops emulated network instances. |
| `fakenos_worker/fakenos_worker.py` | `start` | Start FakeNOS Network | false | false | true | false | Starts emulated network instances. |
| `fakenos_worker/fakenos_worker.py` | `restart` | Restart FakeNOS Network | false | true | false | false | Interrupts emulated network instances. |
| `fakenos_worker/fakenos_worker.py` | `inspect_networks` | Inspect FakeNOS Networks | true | false | true | false | Reads local emulator state. |
| `fakenos_worker/nornir_inventory_tasks.py` | `get_nornir_inventory` | Get Nornir Inventory | true | false | true | false | Reads generated inventory from local emulator state. |

### FastAPI Worker

| File | Task | Title | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `fastapi_worker/fastapi_worker.py` | `get_version` | Get Version | true | false | true | false | Local package metadata. |
| `fastapi_worker/fastapi_worker.py` | `get_inventory` | Get Inventory | true | false | true | false | Local worker inventory. |
| `fastapi_worker/fastapi_worker.py` | `get_openapi_schema` | Get OpenAPI Schema | true | false | true | false | Local API schema. |
| `fastapi_worker/fastapi_worker.py` | `bearer_token_store` | Store Bearer Token | n/a | n/a | n/a | n/a | Existing `mcp=False`; keep hidden from MCP. |
| `fastapi_worker/fastapi_worker.py` | `bearer_token_delete` | Delete Bearer Token | n/a | n/a | n/a | n/a | Existing `mcp=False`; keep hidden from MCP. |
| `fastapi_worker/fastapi_worker.py` | `bearer_token_list` | List Bearer Tokens | n/a | n/a | n/a | n/a | Existing `mcp=False`; keep hidden from MCP. |
| `fastapi_worker/fastapi_worker.py` | `bearer_token_check` | Check Bearer Token | n/a | n/a | n/a | n/a | Existing `mcp=False`; keep hidden from MCP. |
| `fastapi_worker/fastapi_worker.py` | `discover` | Discover FastAPI Tasks | false | false | true | false | Registers or refreshes local FastAPI routes. |

### FastMCP Worker

| File | Task | Title | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `fastmcp_worker/fastmcp_worker.py` | `get_version` | Get Version | true | false | true | false | Local package metadata. |
| `fastmcp_worker/fastmcp_worker.py` | `get_inventory` | Get Inventory | true | false | true | false | Local worker inventory. |
| `fastmcp_worker/fastmcp_worker.py` | `get_tools` | Get MCP Tools | true | false | true | false | Reads registered MCP tool metadata. |
| `fastmcp_worker/fastmcp_worker.py` | `discover` | Discover MCP Tools | false | false | true | false | Registers or refreshes local MCP tools from NorFab services. |
| `fastmcp_worker/fastmcp_worker.py` | `get_status` | Get MCP Status | true | false | true | false | Local MCP server status. |

### File Sharing Worker

| File | Task | Title | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `filesharing_worker/filesharing_worker.py` | `get_version` | Get Version | true | false | true | false | Local package metadata. |
| `filesharing_worker/filesharing_worker.py` | `get_inventory` | Get Inventory | true | false | true | false | Local worker inventory. |
| `filesharing_worker/filesharing_worker.py` | `get_status` | Get Status | true | false | true | false | Local health status. |
| `filesharing_worker/filesharing_worker.py` | `list_files` | List Files | true | false | true | false | Reads configured file roots. |
| `filesharing_worker/filesharing_worker.py` | `file_details` | Get File Details | true | false | true | false | Reads metadata for configured file roots. |
| `filesharing_worker/filesharing_worker.py` | `walk` | Walk Files | true | false | true | false | Reads configured file roots recursively. |
| `filesharing_worker/filesharing_worker.py` | `fetch_file` | Fetch File | true | false | true | false | Reads file content from configured file roots. |

### NetBox Worker

| File | Task | Title | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `netbox_worker/netbox_worker.py` | `get_inventory` | Get Inventory | true | false | true | false | Local worker inventory. |
| `netbox_worker/netbox_worker.py` | `get_version` | Get Version | true | false | true | false | Local package metadata. |
| `netbox_worker/netbox_worker.py` | `get_netbox_status` | Get NetBox Status | true | false | true | true | Reads external NetBox API status. |
| `netbox_worker/netbox_worker.py` | `get_compatibility` | Get NetBox Compatibility | true | false | true | true | Reads external NetBox API capabilities. |
| `netbox_worker/netbox_worker.py` | `cache_list` | List NetBox Cache | true | false | true | false | Reads local worker cache keys. |
| `netbox_worker/netbox_worker.py` | `cache_clear` | Clear NetBox Cache | false | true | true | false | Deletes local worker cache entries. |
| `netbox_worker/netbox_worker.py` | `cache_get` | Get NetBox Cache | true | false | true | false | Reads local worker cache entries. |
| `netbox_worker/netbox_worker.py` | `rest` | Call NetBox REST API | false | true | false | true | Arbitrary NetBox REST operation can mutate or delete data. |
| `netbox_worker/bgp_peerings_tasks.py` | `get_bgp_peerings` | Get BGP Peerings | true | false | true | true | Reads NetBox and related network data. |
| `netbox_worker/bgp_peerings_tasks.py` | `create_bgp_peering` | Create BGP Peering | false | false | false | true | Creates NetBox BGP peering data. |
| `netbox_worker/bgp_peerings_tasks.py` | `update_bgp_peering` | Update BGP Peering | false | true | true | true | Updates existing NetBox BGP peering data. |
| `netbox_worker/bgp_peerings_tasks.py` | `sync_bgp_peerings` | Sync BGP Peerings | false | true | true | true | Updates NetBox from live or computed state. |
| `netbox_worker/branch_tasks.py` | `delete_branch` | Delete Branch | false | true | true | true | Deletes NetBox branch data. |
| `netbox_worker/circuits_tasks.py` | `get_circuits` | Get Circuits | true | false | true | true | Reads NetBox circuit data. |
| `netbox_worker/connections_tasks.py` | `get_connections` | Get Connections | true | false | true | true | Reads NetBox connection data. |
| `netbox_worker/containerlab_inventory_tasks.py` | `get_containerlab_inventory` | Get Containerlab Inventory | true | false | true | true | Reads NetBox data to generate inventory. |
| `netbox_worker/design_tasks.py` | `create_design` | Create Design | false | false | false | true | Creates NetBox design data. |
| `netbox_worker/devices_tasks.py` | `get_devices` | Get Devices | true | false | true | true | Reads NetBox device data. |
| `netbox_worker/devices_tasks.py` | `check_device_sync` | Check Device Sync | true | false | true | true | Runs sync checks in dry-run mode. |
| `netbox_worker/devices_tasks.py` | `sync_all` | Sync All Device Data | false | true | true | true | Updates multiple NetBox object classes. |
| `netbox_worker/graphql_tasks.py` | `netbox_graphql` | Query NetBox GraphQL | true | false | true | true | Reads external NetBox GraphQL API. |
| `netbox_worker/graphql_tasks.py` | `graphql` | Query GraphQL | true | false | true | true | Executes GraphQL query against NetBox. |
| `netbox_worker/interfaces_tasks.py` | `get_interfaces` | Get Interfaces | true | false | true | true | Reads NetBox interface data. |
| `netbox_worker/interfaces_tasks.py` | `create_device_interfaces` | Create Device Interfaces | false | false | false | true | Creates NetBox interface data. |
| `netbox_worker/interfaces_tasks.py` | `update_interfaces_description` | Update Interface Descriptions | false | true | true | true | Updates NetBox interface descriptions. |
| `netbox_worker/interfaces_tasks.py` | `sync_device_interfaces` | Sync Device Interfaces | false | true | true | true | Updates NetBox interfaces from live device data. |
| `netbox_worker/interfaces_tasks.py` | `sync_mac_addresses` | Sync MAC Addresses | false | true | true | true | Updates NetBox MAC address data. |
| `netbox_worker/ip_tasks.py` | `create_ip` | Create IP Address | false | false | false | true | Creates NetBox IP address data. |
| `netbox_worker/ip_tasks.py` | `create_ip_bulk` | Create IP Addresses Bulk | false | false | false | true | Creates NetBox IP address data in bulk. |
| `netbox_worker/ip_tasks.py` | `sync_device_ip` | Sync Device IP Addresses | false | true | true | true | Updates NetBox IP assignments from live device data. |
| `netbox_worker/netbox_crud.py` | `crud_list_objects` | List NetBox Object Types | true | false | true | true | Reads available NetBox object metadata. |
| `netbox_worker/netbox_crud.py` | `crud_search` | Search NetBox Objects | true | false | true | true | Reads NetBox object data. |
| `netbox_worker/netbox_crud.py` | `crud_read` | Read NetBox Object | true | false | true | true | Reads a NetBox object. |
| `netbox_worker/netbox_crud.py` | `crud_create` | Create NetBox Object | false | false | false | true | Creates arbitrary NetBox object data. |
| `netbox_worker/netbox_crud.py` | `crud_update` | Update NetBox Object | false | true | true | true | Updates arbitrary NetBox object data. |
| `netbox_worker/netbox_crud.py` | `crud_delete` | Delete NetBox Object | false | true | true | true | Deletes arbitrary NetBox object data. |
| `netbox_worker/netbox_crud.py` | `crud_get_changelogs` | Get NetBox Changelogs | true | false | true | true | Reads NetBox changelog data. |
| `netbox_worker/nornir_inventory_tasks.py` | `get_nornir_inventory` | Get Nornir Inventory | true | false | true | true | Reads NetBox data to generate Nornir inventory. |
| `netbox_worker/prefix_tasks.py` | `create_prefix` | Create Prefix | false | false | false | true | Creates NetBox prefix data. |
| `netbox_worker/topology_tasks.py` | `get_topology` | Get Topology | true | false | true | true | Reads NetBox topology data. |

### Nornir Worker

| File | Task | Title | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `nornir_worker/nornir_worker.py` | `get_version` | Get Version | true | false | true | false | Local package metadata. |
| `nornir_worker/nornir_worker.py` | `get_watchdog_connections` | Get Watchdog Connections | true | false | true | true | Reads live connection state. |
| `nornir_worker/nornir_worker.py` | `refresh_nornir` | Refresh Nornir Inventory | false | false | true | true | Refreshes local Nornir inventory from configured sources. |
| `nornir_worker/inventory_tasks.py` | `nornir_inventory_load_netbox` | Load Nornir Inventory from NetBox | false | false | true | true | Replaces or refreshes local runtime inventory from NetBox. |
| `nornir_worker/inventory_tasks.py` | `nornir_inventory_load_containerlab` | Load Nornir Inventory from Containerlab | false | false | true | true | Replaces or refreshes local runtime inventory from containerlab. |
| `nornir_worker/inventory_tasks.py` | `get_inventory` | Get Inventory | true | false | true | false | Reads local worker inventory. |
| `nornir_worker/inventory_tasks.py` | `get_nornir_hosts` | Get Nornir Hosts | true | false | true | false | Reads local Nornir inventory. |
| `nornir_worker/inventory_tasks.py` | `runtime_inventory` | Update Runtime Inventory | false | true | false | false | Mutates local runtime inventory. |
| `nornir_worker/cli_task.py` | `cli` | Run CLI Commands | false | true | false | true | Arbitrary CLI commands may change device state. |
| `nornir_worker/cfg_task.py` | `cfg` | Configure Devices | false | true | false | true | Pushes configuration to devices. |
| `nornir_worker/file_copy_task.py` | `file_copy` | Copy File to Devices | false | true | false | true | Copies or overwrites files on devices. |
| `nornir_worker/netconf_task.py` | `netconf` | Run NETCONF Operation | false | true | false | true | Arbitrary NETCONF operation may mutate devices. |
| `nornir_worker/network_task.py` | `network` | Run Network Operation | false | true | false | true | Arbitrary network operation may mutate devices. |
| `nornir_worker/parse_task.py` | `parse_napalm` | Parse NAPALM Output | true | false | true | true | Reads devices and parses output. |
| `nornir_worker/parse_task.py` | `parse_textfsm` | Parse TextFSM Output | true | false | true | true | Reads devices and parses output. |
| `nornir_worker/parse_task.py` | `parse_ttp` | Parse TTP Output | true | false | true | true | Reads devices and parses output. |
| `nornir_worker/task_task.py` | `task` | Run Nornir Task Plugin | false | true | false | true | Arbitrary plugin may mutate devices or external systems. |
| `nornir_worker/test_task.py` | `test` | Run Nornir Tests | true | false | true | true | Executes validation checks against devices. |

### Workflow Worker

| File | Task | Title | readOnlyHint | destructiveHint | idempotentHint | openWorldHint | Notes |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `workflow_worker/workflow_worker.py` | `get_version` | Get Version | true | false | true | false | Local package metadata. |
| `workflow_worker/workflow_worker.py` | `get_inventory` | Get Inventory | true | false | true | false | Local worker inventory. |
| `workflow_worker/workflow_worker.py` | `run` | Run Workflow | false | true | false | true | Workflow can call arbitrary state-changing tasks. |

---

## Implementation Steps

1. Add a small helper constant or local dictionary pattern where useful, but keep
   decorators explicit enough that generated task schemas show the intended MCP
   metadata without extra runtime work.
2. Update every MCP-exposed `@Task(...)` in `norfab/workers/` with
   `mcp={"annotations": {...}}`.
3. Leave existing `mcp=False` bearer-token helper tasks hidden from MCP.
4. Verify that `fastmcp_worker.service_tasks_discovery()` still creates
   `types.Tool(**task_tool)` successfully.
5. Add or update tests around `list_tasks` or FastMCP discovery to assert that a
   representative read-only tool, destructive tool, idempotent mutating tool,
   and `mcp=False` task behave as expected.
