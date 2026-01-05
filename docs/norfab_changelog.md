## 0.15.0

### CHANGES

1. 

---

## 0.14.0

### CHANGES

1. Netbox sync_device_interfaces - refactored to use bulk update and bulk create operations
2. Netbox service - deprecated support for Netbox below 4.4.0 version
3. Netbox service - `get_interfaces` added `label` and `mark_connected` fields
4. Netbox service - `get_connections` added `remote_device_status` field
5. Nornir service - test task added nornir hosts inventory to results if extensive set to true
6. Nornir tests markdown - added hosts expandable inventory section
7. Nornir tests markdown - added total tests number for detailed section for each host
8. Nornir tests markdown - updated headings and paragraphs content
9. Enhanced message construction for NFP protocol buy adding message builder
10. Enhanced client, worker and broker socket handling by adding thread locks

### FEATURES

1. Netbox service - added `create_device_interfaces` task
2. Netbox service - added `branch_create_timeout` inventory argument to control timer waiting for new branch to be created
3. Netbox service - added integration with Netbox BGP Plugin in a form of `get_bgp_peerings` task to fetch BGP sessions data for devices, added nfcli shell command to call `get_bgp_peerings` task.
4. Netbox service - `get_nornir_inventory` task added support for `bgp_sessions` argument. if True, fetched devices' BGP peerings from netbox and stores them under `bgp_sessions` key in host's data.

### BUGS

1. Nornir tests markdown - fixed detailed output handling to not collect suite into summary table
2. Nfcli - fixed show client command function calling

----

## 0.13.0

### BUG FIXES

1. Fixing event severity handling in worker.

### CHANGES

1. Changed worker to use sqllite database for job persistent storage instead of json files
2. Netbox sync device facts - enhanced sync logic to use bulk device updates

### FEATURES

1. Nornir test task - added `extensive` argument to return detailed results
2. Client - added `markdown` argument to `run_job` method to support rendering results into markdown output
3. Client - added Nornir test task markdown render function to return tests results in a form of markdown report.
3. Client - added generic markdown render function to return results in a form of markdown report.

---

## 0.12.7

### FEATURES

1. NFAPI logging - added support for `logging->log_events` parameter to emit events as syslog messages
2. Added context manager support fo NFAPI to simplify invocation from python scripts

### CHANGES

1. NFAPI changed start method arguments from `start_broker` to `run_broker` and `workers` to `run_workers`
2. Nornir task - enhanced task import logic
3. Nornir worker - added filter hosts method to reduce duplicate code
4. NorFab client - added ensure_bytes method to reduce duplicate code

---

## 0.12.6

### BUGS

1. Netbox service - fixed get_circuits handling bug, was not returning circuits data due to recent code refactoring, updated test to catch this kind of an issue.

---

## 0.12.5

### BUGS

1. Containerlab - fixing error handling when result is None
2. Workflow - fixed emitting event progress for cli shell
3. Netbox - bulk ip create updated to sort interfaces names to make ip allocation order deterministic

### CHANGES

1. Updated dependencies:
  - TTP 0.9.5 -> 0.10.0
  - nornir-salt 0.22 -> 0.23

2. Renamed Netbox service tasks:
  - update_device_facts -> sync_device_facts
  - update_device_interfaces -> sync_device_interfaces
  - update_device_ip -> sync_device_ip
  
### FEATURES

1. Netbox service - get_connections enhanced to retrieve power outlet connections.

---

## 0.12.4

### BUGS

1. Netbox worker - fixing handling of Netbox instance for child subnet creation


## FEATURES

1. Netbox worker - update interface descriptions task now can supply dictionary of interface descriptions

---

## 0.12.3

### BUGS

1. Fixing handling of entry points for sourcing norfab workers plugins for Py3.10+

### CHANGES

1. Docker images updated to use Py3.11

---

## 0.12.2

### CHANGES

1. Updated Python version dependencies
2. Adding FastMCP worker
3. Updating agent worker - work in progress
4. Adding Streamlit worker to host WEB UI - work in progress

---

## 0.12.1

### BUGS

1. Netbox service - restored Netbox v4.2.0 support
2. Fixing Picle shell netbox get interfaces to have `interface_regex` argument
3. Fixing Picle chek netbox get connection arguments

---

## 0.12.0

### BUGS

1. FastAPI Service - fixing json references for OpenAPI schema, which previously broken lead to error in swagger and redoc UIs rendering.

### FEATURES

1. Netbox service - `get_interfaces` task added `interfaces_regex` filter
2. Netbox service - `get_connections` task added `interfaces_regex` filter
3. Netbox service - `get_connections` added support to retrieve virtual interfaces connections for physical and lag interfaces
4. Netbox service - `create_ip` added support to automatically assign IPs to link peers or use peers IP addresses prefixes to allocate next available IP address
5. Netbox service - `create_ip` added support to create child subnet within parent prefix and assign IP out of it
6. Netbox service - added new task `create_ip_bulk` to create IP addresses for devices using interfaces regex match
7. FastMCP service - created NorFab MCP service

---

## 0.11.2

### CHANGES

1. Moving to Python 3.10 as primary supported version instead of 3.9 due to addition of FastMCP service which only supports Py3.10 and up.
2. Updated build dockerfiles to use `python:3.10-slim-trixie` as a base image

### BUGS

1. Fixing FastAPI worker argument handling by setting it to `all` by default

----

## 0.11.1

### BUGS

1. Fixed containerlab show lab outputting
2. Enhanced nfcli logic to b able to start broker nad workers only without a client
3. Updated aio docker file to start broker and workers only

---

## 0.11.0

### FEATURES

1. FastAPI Services -  enhanced to generate api endpoints for all services tasks automatically using `@Task` decorator data
2. NFCLI -  Picle show containerlab containers now emits output with nested tables
3. Netbox Service - `create_ip` task enhanced to source prefixes to allocate next IP from using prefix description string
4. Netbox Service -  Added `create_prefix` task to allocate next available prefix
5. Nornir Service - Adding `nb_create_prefix` Jinja2 filter allocate next available prefix during templates rendering
6. Worker - Added `fastapi` argument to `@Task` decorator to control FastAPI REST API endpoints auto-generation
7. Containerlab Service - added support for Containerlab 0.69+
8. Netbox Service - added support for branching plugin, made creat and update tasks be branch aware, updated nfcli shells to support `branch` argument
9. Netbox Service - added `delete_branch` task

### BUGS

1. Fixing nornir test picle shell test task handling for verbouse-result and dry-run
2. Fixing nornir test handling for when suite renders to empty tests for a host
3. Fixed Netbox service `instance` variable options sourcing for CLI shells

### CHANGES

1. Upgrading NAPALM library dependency from 5.0.0 to 5.1.0
2. Upgrading PICLE library dependency from 0.9.0 to 0.9.1
3. Upgrading Pynetbox library dependency from 7.4.0 to 7.5.0
4. Refactoring Netbox service pydantic models
5. BREAKING CHANGE: Starting NorFab 0.11.0 containerlab service only supports Containerlab 0.69+
6. Dependencies updates.


## 0.10.0

### FEATURES

1. Adding support for Netbox >= 4.3.0
2. Enhanced Netbox service inventory device filters to support GraphQL query string for `device_list` queries.
3. Added Netbox service `create_ip` task to allocate new or source existing IP from prefix
4. Added `nb_create_ip` Jinja2 filter to Nornir service to source IP allocations during templates rendering
5. Added nfcli shell `netbox create ip` command to run IP allocations from interactive command line
 
---

## 0.9.1

### BUGS

1. Fixing list and dict annotations to also allow None values for workers tasks.

---

## 0.9.0

### FEATURES

1. Adding concurrency to worker jobs execution, adding new worker inventory parameter `max_concurrent_jobs`
2. Adding `@Task()` decorator to expose worker methods as tasks, this decorator perfoms automatic typechecking using type annotation, alternatively it support input / output pydanti models to verify input arguments and return results.
3. Passing on `job` argument to all NorFab tasks, `job` is an object that contains relevant metadata - client address, juuid, args, kwargs etc. Job object can be used to emit events.
4. Adding workers `echo` task to perform tests, added respective nfcli commands tree `workers.ping`.
5. Adding workers `list_tasks` method to return information about tasks in MCP compatible format.
6. Added picle shell `man.tasks` command to retrieve information about NorFab services tasks

### CHANGES

1. Improved Netbox device update nfcli to include Fx hosts filtering for nornir datasource
2. Result object added `task_started` and `task_completed` timestamp and `service` parameters

### BREAKING CHANGES

1. Instead of `self.event` worker now need to use `job.event`
2. To add pydantic input / output models for tasks need to use `@Task()` decorator instead of `@Task` decorator
3. Nornir Jinja2 templates context `nornir.cli` removed, need to use `norfab.run_job` instead

---

## 0.8.2

### BUGS

1. Fixed nornir inventory load from containerlab handling

---

## 0.8.1

### BUGS

1. Fixed `show containerlab inventory` command
2. Fixed Nornir Worker inventory load handling
3. Netbox interface update improving mac address handling

### FEATURES

1. Netbox service added `get_containerlab_inventory` task 
2. Containerlab service added `deploy_netbox` task

### CHANGES

1. Improved client post job retry logic
2. `FN` filter argument for Nornir add presence handling for nfcli

---

## 0.8.0

### CHANGES

1. Restructuring pydantic models structures for better following DRY principles:
    1. Moved FatAPI models under norfab.models.fastapi
    2. Added norfab.models.nornir pydantic models
    3. Events and results models moved under norfab.models
2. Added broker `zmq_auth` inventory parameter to turn zero mq authentication and encryption off
3. Added `verbose-result` command line argument to relevant tasks to emit result details
4. Updated to CLI shells to support PICLE 0.9.0
5. Enhanced Netbox service to support working with instances of Netbox of different major and minor releases

### BUGS

1. Fixed broker to allow workers reconnect on restart.

### FEATURES

1. Improved worker jinja2 templates rendering logic to allow render url first and next download its content
2. Added `nornir refresh` CLI command to refresh Nornir workers instances and reload inventory
3. Added support for Netbox 4.2
4. Added support for Nornir service to pull hosts inventory from Containerlab service

---

## 0.7.0

### FEATURES

1. Added new `workflow` service to run simple workflows constructed using YAML DSL

### CHANGES

1. NFCLI shells - updated to use nested outputter where appropriate
2. Nornir worker - updated to set failed flag for its tasks according to test results
3. Worker - Added `status` filed to worker result object to reflect job execution status
4. Nornir Service - replaced `cfg_dry_run` and `cli_dry_run` arguments with `dry_run` argument
5. NFCLI shell - added aliases to use dash instead of underscore
6. NFCLI shell - Moved Nornir service show commands under `show nornir xyz` path  

---

## 0.6.0

### FEATURES

1. Added support for worker plugins
2. Added support for nfcli custom shells

### CHANGES

1. All workers loaded into NorFab using entrypoints implementing lazy loading - workers classes only imported when they being used, in some cases allowing to save on startup time.

---

## 0.5.0

### FEATURES

1. FastAPI service added bearer authentication support
2. Added hooks attachpoints `nornir-startup` and `nornir-exit` to influence Nornir service workers startup and exit

---

## 0.4.0

### CHANGES

1. Improved netbox get_circuits logic.
2. Standartised worker `get_version` and `get_inventory` methods

### Features

1. Added `runtime_inventory` task to Nornir service, #6
2. Added support to configure `startup` and `exit` hook functions in inventory to be executed by nfapi on start and on exit.

---

## 0.3.1

### CHANGES

1. Improved logging handling for NFAPI if it failing to start a worker
2. Update client `get` method to return result as a dictionary for broker MMI, file and inventory services
3. Enhanced Netbox `update_device_facts` and `update_device_interface` to support `batch_size` argument - a number of devices to process at a time
4. Improved nfcli shell for Netbox service to provide more arguments for `netbox update device facts` command

### FEATURES

1. Added Netbox Service `update_device_ip` task to retrieve device interface IP addresses and create them in Netbox
2. Added support to NorFab simple inventory and nfapi to load inventory from dictionary data as well as to explicitly provide `base_dir` information where to anchor NorFab environment
3. Added support for NorFab inventory workers section items to be dictionaries in addition to OS path to YAML files allowing to construct workers inventory out of dictionaries and/or YAML files.

---

## 0.3.0

### FEATURES

1. Added "show version" support for nfcli client to display versions of locally installed libraries, fixes. #4
2. Added "show broker version" support for nfcli client to  retrieve broker report of the version of libraries broker is running on, fixes. #4
3. Added support "show broker inventory" command to display broker inventory
4. Simple inventory added support to produce a serialized dictionary output
5. Broker added "show_broker_inventory" and "show_broker_version" MMI endpoints
6. Added support for simple inventory service to render inventory using Jinja2, renderer passed on `env` variable that contains operating system environment variables, allowing to source any env data into NorFab inventory for both broker and workers. #5
7. Created `fastapi` service to host REST API for NorFab

---

## 0.2.4

### BUGS

1. Fixed nfcli `--workers-list` handling
2. Fixed `job_data` url handling for nornir cli/cfg/test tasks
3. Fixed nfapi handling of empty worker name

### FEATURES

1. Added a set of confirmed commit shell commands to nornir cfg netmiko plugin

---

## 0.2.3

### FEATURES

1. Added nfcli `--workers-list` option to specify a list of workers to start

### CHANGES

1. Fixed handling of jinja2 import for the worker to make it optional 

---

## 0.2.1

### CHANGES

1. Improved libs imports handling to account for distributed deployment
2. Improved logging handling
3. Fixed nfcli issue with starting components onf NorFab #2
4. Changed CTRL+C handling to trigger graceful NorFab exit

### FEATURES

1. Added `broker -> shared_secret` parameter in `inventory.yaml` to configure clients and workers broker shared secret key
2. Added and tested docker files

---

## 0.2.0

### CHANGES

1. refactored `get_circuits` to use `threadpoolexecutor` to fetch circuits path from netbox
2. adding `job_data` json load to nornir cli, cfg and test tasks

### BUGS

1. Fixing netbox `get_devices` dry run test
2. Fixed netbox `get_circuits` devices site retrieval handling

## FEATURES

1. Added cache to Netbox `get_circuits` and `get_devices` tasks
2. Added new `agent` worker to stsart working on use cases to interface with LLMs

---

## 0.1.1

### BUGS

1. FIxed Netbox CLI Shell handling of NFCLIENT

### CHANGES

1. Updated and tested dependencies for Netmiko 4.5.0
2. Updated and tested dependencies for Nornir 3.5.0
3. Updated and tested dependencies for Nornir-Salt 0.22.1

---

## 0.1.0

### Changes

1. Changes to Nornir service module files structure
2. PICLE dependency updated: 0.7.* -> 0.8.*
3. Made Nornir Service `progress` argument set to `True` by default to emit and display events for all Nornir Jobs
4. Nornir tests changed `table` argument to be set to `True` by default
5. Improved `nfapi` broker start logic to wait until broker fully initialized before proceeding to start workers

### Features

1. Added support for Nornir parse task to source TTP template from file with autocompletion
2. Added Nornir File Copy task to copy files to devices using SCP
3. Added support for logs to  be collected into single file from all NorFab local processes
4. Added to NorFab worker `job_list` and `job_details` methods
5. Added `show jobs summary` and `show jobs details` commands to NorFab shell and to Nornir shell
6. Added `--create-env` argument to nfcli utility to create NorFab folders and files to make it easier to get started using norfab

### BUGS

1. Fixed Nornir Service Watchdog to clean up dead connections from hosts data

---

## 0.0.0

Initial Release

### Notable Features

1. NorFAB Broker, Client and Worker base classes
2. Nornir Service
3. Network Service
4. Simple Inventory Datastore Service
5. File service
6. ZeroMQ encryption