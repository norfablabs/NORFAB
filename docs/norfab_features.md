---
tags:
  - features
  - services
---

# NORFAB Features

*Last updated: 5 September 2026*

NORFAB is a distributed automation fabric for operating network devices, network
sources of truth, virtual labs, workflows, and AI-assisted tools through a common
job model. This page is a concise capability reference for technical evaluation
and RFP response; follow the links for configuration details and task schemas.
Capabilities are designed to compose—for example, build a lab from NetBox,
load it into Nornir, deploy configuration, run assurance tests, compare the
result with a baseline, and expose the whole operation through REST or MCP.

## Contents

[TOC]

## Interface coverage

NORFAB service tasks use the same brokered job model across these interfaces:

| Interface | Support | Best suited to |
|-----------|---------|----------------|
| **NFCLI** | Interactive commands for supported service tasks, inventory, workers, jobs, and results | Operators, troubleshooting, and ad-hoc changes |
| **NFWeb** | Generic browser client with runtime monitoring and live/historical 3D topology using native NORFAB access | Visual operations, observability, troubleshooting, reporting, and future web-based tools |
| **Python API** | Direct task submission, synchronous results, futures, events, and worker input | Applications, scripts, and custom integrations |
| **REST API** | FastAPI-generated endpoints for tasks that declare REST exposure | OSS/BSS integration, portals, and language-neutral automation |
| **MCP** | FastMCP-generated tools and task-authored prompts for tasks that declare MCP exposure | AI assistants and agentic automation |
| **Robot Framework** | Keyword library for targeting hosts and running Nornir CLI, configuration, and test operations | Acceptance testing, CI, and keyword-driven automation |

Public service tasks generally support **NFCLI, Python API, REST, and MCP**;
exceptions are called out below. REST requires a
[FastAPI worker](#fastapi-rest-service), MCP requires a
[FastMCP worker](#fastmcp-service), and the corresponding service worker must
be deployed. The Python API is the complete native task interface. Task
exposure metadata can exclude a REST endpoint or MCP tool, while FastMCP tool
policy can further allow or reject published MCP tools.

### NFWeb local web client

Runs a browser-based NORFAB client on the operator's computer and connects it to an
existing broker through the native Python API. NFWeb provides the local web host,
packaged frontend, browser boundary, and application-specific services without
requiring a FastAPI worker or a central web deployment. It is intended to grow into
a collection of focused web applications for visual operations, observability,
troubleshooting, reporting, and guided workflows.

The **runtime monitoring dashboard** polls existing broker management and worker
watchdog interfaces to show broker, local NFWeb client, and worker health; CPU and
resident memory; worker resource comparisons; stacked fabric-wide broker and
worker CPU and memory consumption; selected-worker trends; and
local-client job totals and interval status activity from the existing client job
database. Selecting a worker also shows a full-width status card summarizing its
recent jobs, statuses, and tasks through the existing worker `job_list` task.
ECharts supplies resource trends, stacked job-status activity bars,
data zoom, and
worker comparisons. Worker comparisons rank combined CPU and relative-memory
demand on each refresh, show ten workers at once with synchronized scrolling, and
offer 5, 10, 30, or 60-second reads of the latest shared sample. Samples are pushed to
browsers over WebSocket and retained
only in process memory for up to three hours; restart clears them and no monitoring
database or telemetry journal is created. **Monitoring use cases:** live fabric
health, worker availability, resource trend inspection, and keepalive diagnosis.

The first built-in application is the **3D topology observatory**. Its persistent
Vasturiano scene combines intended NetBox cabling with observed LLDP, BGP, and
interface state, makes partial collection failures visible, and stores compressed
snapshots in a rolling three-hour local SQLite history. Same-layer connections
between a node pair render as one link while their interface-level records remain
available in the inspector; NetBox, LLDP, and BGP links remain separate. Its shared
shell provides
an inventory-configured footer message and quick links to FastAPI, documentation,
and the NORFAB repository. Common controls use the maintained Mantine React
component system with Tabler icons, color-matched L1 and BGP link selectors,
an L2 traffic overlay that renders telemetry-backed physical-link directions as
shallow, independently colored and animated lanes without obscuring BGP peerings,
fully opaque health-colored nodes with matching States-dropdown keys, toggleable
3D bloom, and Enter-submitted topology
search that highlights matches without removing non-matching elements. It also
provides nested application navigation and searchable, sortable inspector tables.
The local runtime supports graceful Ctrl+C
shutdown with a second-interrupt forced-exit fallback. **Topology use cases:**
weather-map dashboards, topology exploration, current-state windows, incident
timelines, and intended-versus-observed context. **Current limitations:** NFWeb has
no authentication, origin filtering, or TLS, and both applications are polling-based.
Restrict remote access to trusted administrative networks. Unknown telemetry is
not inferred and monitoring does not capture message payloads.
[NFWeb client details](clients_nfweb_overview.md) ·
[Monitoring dashboard details](clients_nfweb_monitoring.md) ·
[Topology application details](clients_nfweb_topology.md)

## Core platform

NORFAB's [broker, clients, and workers](reference_architecture_norfab.md) provide
the shared execution layer beneath every service.

### Distributed service architecture

Routes client jobs through a broker to independently deployable service workers
on a laptop, server, VM, container, or distributed hosts. **Use cases:** central
automation, remote execution, hybrid deployments, and workload isolation.
**Limitations:** the broker endpoint must be reachable by every component and
production resilience depends on the topology and infrastructure deployed.

### Horizontal worker scaling

Allows multiple workers to provide the same service and supports targeting one,
any, or all eligible workers. **Use cases:** capacity growth, geographic
placement, and separating environments or tenants. **Limitations:** task
semantics determine whether multi-worker execution is safe; shared external
resources may still require coordination.

### Unified job lifecycle

Provides blocking execution, asynchronous submission, user-supplied UUIDs,
deadlines, worker selectors, deferred results, and recoverable futures.
**Use cases:** simple scripts, fire-and-track operations, long-running changes,
and application-controlled job correlation. **Limitations:** callers must set
timeouts appropriate to the work and retain UUIDs for asynchronous jobs.
[Python client details](clients_python_api_overview.md#running-jobs)

### Live events and interactive approvals

Streams structured progress events with service, worker, task, resource,
severity, status, timestamp, and extensible metadata. Workers can pause for
typed client input, present a dry-run preview, enforce an approval timeout, and
continue or cancel from the response. **Use cases:** live progress displays,
change approvals, human-in-the-loop workflows, and audit timelines.
**Limitations:** interactive callers must consume events and answer before the
request timeout.
[Event and input details](clients_python_api_overview.md#future-based-jobs)

### Persistent client job history

Stores job state, arguments, worker replies, results, errors, and events in a
client-side SQLite database; active futures are reconstructed after client
startup and expired work is marked stale. **Use cases:** operational history,
result recovery, event review, failure investigation, and job statistics.
**Limitations:** history belongs to the named client and its local data
directory; retention and backup are deployment responsibilities.

### Worker-side job observability

Lists pending and completed worker jobs by task, client, UUID, or recency and
retrieves result/event details for a job. **Use cases:** finding queue pressure,
tracing a request end to end, and diagnosing a slow or failed worker.
**Limitations:** worker and client databases are local operational stores, not a
central enterprise audit archive.

### Model-driven task contracts

Uses typed task input/output models to validate calls and generate REST and MCP
schemas. **Use cases:** predictable integrations, discoverability, and early
rejection of malformed requests. **Limitations:** validation quality depends on
the annotations and models supplied by each built-in or custom task.

### Runtime task discovery

Every worker can list task names or return the complete schema for one or all
tasks. FastAPI, FastMCP, agents, and NFCLI use this metadata to build interfaces
without duplicating task definitions. **Use cases:** dynamic clients, capability
negotiation, integration testing, and feature inventory. **Limitations:** only
tasks registered by running workers are discoverable.

### Inventory composition

Uses a broker-hosted Simple Inventory Datastore to match worker names with one
or more YAML definitions and recursively merge common and worker-specific
configuration. **Use cases:** environment overlays, repeatable deployment, and
centralized worker configuration. **Limitations:** merge order and glob overlap
must be managed deliberately; sensitive values require appropriate secret and
file controls.
[Inventory details](reference_norfab_inventory.md)

### Templated inventory

Renders inventory files with Jinja2 before loading them. **Use cases:** computed
endpoints, environment-dependent values, reusable worker definitions, and
reducing duplicated YAML. **Limitations:** templates execute at inventory load
time and should remain deterministic and reviewable.
[Jinja2 inventory details](reference_norfab_inventory.md#jinja2-support)

### Local environment bootstrap

Detects and loads a project `.env` file before inventory rendering using the
`python-dotenv` library. Local values override existing process variables by
default, with an NFAPI option to preserve existing values instead, and NFAPI can
list its visible environment variables for inspection. **Use cases:** local
NFCLI configuration, environment-specific endpoints, and development credentials
kept outside inventory YAML. **Limitations:** the `.env` file is local process
configuration rather than a secret store; files containing secrets must be
excluded from source control and protected appropriately.
[NFAPI environment details](api_reference_core_norfab_nfapi.md#environment-file-loading)

### Topology dependencies and lifecycle hooks

Starts an ordered selection of broker/workers, lets workers declare
`depends_on` relationships, and runs configured startup, exit, Nornir-startup,
and Nornir-exit Python hooks. **Use cases:** waiting for a source-of-truth
service, preloading data, registering integrations, and cleanup. **Limitations:**
hooks are trusted code; dependency ordering does not replace external service
health orchestration.
[Hook details](customization/norfab_hooks.md)

### Worker capacity and resource controls

Configures per-worker concurrent-job limits, compressed job storage, watchdog
intervals, and memory thresholds that log or shut down the worker. **Use cases:**
protecting fragile downstream systems, bounding resource use, and operating
small edge nodes. **Limitations:** values require workload-specific tuning;
shutdown policy needs an external restart strategy.

### Worker health and statistics

Exposes inventory, package versions, watchdog configuration, RAM/CPU and job
statistics, service-specific status, and broker-known worker presence.
**Use cases:** health dashboards, compatibility checks, deployment verification,
and support bundles. **Limitations:** built-in status is component health, not a
substitute for end-to-end service-level monitoring.

### Worker reachability and remote diagnostics

Pings selected workers through an echo task and can execute a timeout-bounded
host shell command with captured stdout, stderr, return code, and failure state.
**Interfaces:** NFCLI, Python API, and REST; shell execution is deliberately
excluded from MCP and automatic agent discovery. **Use cases:** verify worker
routing, inspect local dependencies, gather diagnostics, and perform tightly
controlled maintenance. **Limitations:** shell execution is arbitrary code on
the worker host and requires strict administrative access and auditing.

### Configurable logging

Supports the Python `dictConfig` model: named formatters, filters, loggers,
stream/file/rotating/timed/syslog/SMTP/buffer/queue-style handler parameters,
per-logger levels and propagation, plus optional conversion of job events into
logs. Broker and worker processes configure their own logging and default to
per-process JSONL files under `__norfab__/logs`; NFCLI can retrieve broker and
worker logs through normal client calls. **Use cases:** local troubleshooting,
centralized logging, SIEM ingestion, rotation, and environment-specific
verbosity. **Limitations:** the selected handlers and destinations must be
provisioned and secured by the deployment.
[Logging inventory details](reference_norfab_inventory.md#logging-inventory-section)

### Encrypted component communication

Supports ZeroMQ authentication and CurveZMQ encryption between the broker,
clients, and workers; authentication is enabled by default. **Use cases:**
protecting distributed fabric traffic. **Limitations:** distributed components
must share the correct broker key, and northbound REST/MCP TLS is a separate
deployment concern.
[Broker inventory details](reference_norfab_inventory.md#broker-inventory-section)

### Custom service plugins

Loads custom worker services from local Python modules or package entry points,
allowing new resources and tasks to participate in the same job and gateway
model. **Use cases:** proprietary systems, new protocols, and
organization-specific automation. **Limitations:** plugins are trusted code and require
packaging, dependency, schema, security, and lifecycle ownership.
[Plugin details](customization/service_plugin_overview.md)

## NFCLI interactive shell

The [NFCLI client](clients_nfcli_overview.md) provides a model-driven operations
shell over the same task contracts used by the Python, REST, and MCP interfaces.

### Hierarchical operating modes

Organizes platform and service commands into familiar nested modes such as
`nornir cli`, `netbox`, `containerlab`, and `show`. **Use cases:** guided
operations, ad-hoc troubleshooting, demonstrations, and runbook execution.
**Limitations:** commands execute when entered; production access should be
governed like any other change interface.

### Context help, completion, and command manuals

Derives validation, inline help, required/default markers, value completion, and
multiline input from Pydantic models. `man tree <path>` prints any command
subtree, `man json-schema <path>` exposes its schema, and `man tasks` discovers
worker task documentation. **Use cases:** self-service exploration, learning
task parameters, and confirming capabilities without leaving the shell.
**Limitations:** help quality follows model descriptions and the versions
installed on the connected workers.

### Live job console

Prints a job header, colour-coded progress/warning/error events, worker and
resource context, elapsed time, and a completion summary before results.
Interactive input requests can display a formatted dry-run preview and collect
timed yes/no or choice responses. **Use cases:** following large fleet changes,
spotting partial failures early, and operator approval. **Limitations:** terminal
display is ephemeral unless events/results are also retained or exported.

### Asynchronous submission

The common `nowait` option returns the job UUID immediately instead of holding
the terminal. **Use cases:** launching slow lab deployments, large discovery
runs, or parallel work from an operator session. **Limitations:** the operator
must use job inspection to retrieve the eventual outcome.

### Result shaping and tables

Displays nested, YAML, JSON, key/value, Markdown, pretty-print, Rich table, or
tabulated output. Service commands can select/exclude columns, sort, reverse,
flatten nested rows with `table extend`, and switch between brief/terse/custom
table formats. **Use cases:** human review, compact incident output, copy/paste
into tickets, and rapid comparison across devices. **Limitations:** a table
requires list-like records; irregular results remain nested.

### Output filtering and file export

Pipe-enabled commands can include or exclude matching lines, return the last
N lines, convert the result format, or save rendered output to a local file.
**Use cases:** isolate errors from large command output, preserve evidence, feed
another tool, and create lightweight reports. **Limitations:** shell pipes
post-process the returned display; they do not reduce work performed on workers.

### Job and platform inspection

Shows broker, client, worker, inventory, security, package-version, job,
database-statistics, and service-specific status data. Jobs can be filtered by
UUID, service, task, worker, status, and recency. **Use cases:** operational
triage, upgrade verification, capacity review, and support diagnostics.

### Transactional inventory editing

Provides a configuration mode backed by typed inventory models. Changes are
staged, reviewable, committable, discardable, negatable with `no`, and
rollbackable from rotating backups. **Use cases:** safe local inventory edits
and repeatable environment setup. **Limitations:** committing changes updates
the YAML inventory; affected running processes may still require refresh or
restart.

## Nornir service

The [Nornir service](workers/nornir/services_nornir_service.md) runs concurrent,
inventory-driven operations against network devices.

### Command execution

Runs show and operational commands over SSH or Telnet using Netmiko, Scrapli, or
NAPALM, including enable/privilege handling, prompt/echo stripping, custom
terminators, read timeouts, command intervals, multiline splitting, and
promptless Netmiko execution. **Use cases:** diagnostics, bulk state collection,
interactive-prompt commands, slow commands, and multi-vendor operational
checks. **Limitations:** command syntax and transport support depend on the
device platform and selected plugin.
[Task details](workers/nornir/services_nornir_service_tasks_cli.md)

### Repeated command sampling and stop conditions

Netmiko and Scrapli can repeat command sets, wait between samples, stop early
when output matches a glob pattern, and return only the latest N samples.
**Use cases:** wait for BGP establishment, watch convergence, verify counters
stabilize, monitor an upgrade, or capture a short time series without an
external polling loop. **Limitations:** polling occupies device sessions and a
worker task for its duration.
[CLI examples](workers/nornir/services_nornir_service_tasks_cli.md#running-show-commands-multiple-times)

### Output-based failure detection

Scrapli can mark a command failed when its response contains configured strings;
configuration plugins can detect error patterns and optionally stop after a
failed command. **Use cases:** catch vendor error banners that still return a
successful transport status, fail pipelines on rejected syntax, and prevent
later commands after an error. **Limitations:** patterns are platform-specific
and require testing to avoid false positives.

### Per-host command templating and previews

Renders inline commands or `nf://` files with Jinja2 separately for every host,
using host data, inline/file job data, NetBox helpers, and custom filters.
Dry-run returns rendered commands without connecting to devices. **Use cases:**
parameterized diagnostics, per-device VRF/interface commands, and reviewing
target-specific intent before execution. **Limitations:** template inputs and
host data are trusted automation content.

### NetBox-backed Jinja2 object filtering

Exposes `netbox.filter` to Nornir Jinja2 templates for retrieving filtered
NetBox core or plugin objects with optional field selection. Results are returned
as a list for direct iteration when rendering commands, configuration, or test
suites. **Use cases:** source-of-truth-driven interface configuration, dynamic
per-object tests, and plugin-backed routing templates. **Limitations:** requires
an available NetBox service and knowledge of the target object and filter
fields; per-host rendering queries can add NetBox API load and latency.
[Jinja2 filter examples](workers/nornir/services_nornir_service_jinja2_filters.md#netboxfilter)

### Resilient execution with RetryRunner

Separately tunes task-worker and connection-worker pools, TCP connection
pre-checks/timeouts, connection and task retry counts, reconnect-on-task-failure,
and alternate credentials/connection parameters. **Use cases:** unreliable WAN
links, staged credential rotation, transient device load, and large mixed-speed
fleets. **Limitations:** retries extend runtime and must be bounded to avoid
amplifying persistent failures.

### Shared result processors

Built-in and custom Nornir tasks can apply a client-selected processing chain:
arbitrary Nornir-Salt DataProcessor functions, line matching with context,
XPath, JMESPath, XML flattening, IP/DNS lookup, NTC TextFSM, TTP, and inline test
assertions. **Use cases:** normalize raw data at the worker, extract only
decision-relevant values, enrich IPs with names, and turn collection into a
pass/fail gate. **Limitations:** processors expect compatible input shapes and
templates.

### Inline CLI parsing

Netmiko command collection can return TextFSM, TTP, or PyATS/Genie structured
results in the same call; a general TTP processor can combine multiple command
outputs into one chosen result structure. **Use cases:** replace screen scraping
with records, feed dashboards, correlate commands, and make assertions against
typed values. **Limitations:** parser packages/templates must support the target
platform and command syntax.

### Detailed or compact result serialization

Returns results as a host-keyed dictionary or flat task-record list and can add
failure state, exception, changed/diff, connection retry, and task retry details
where available. **Use cases:** compact operator output, rich troubleshooting,
table generation, machine processing, and partial-failure accounting.
**Limitations:** available detail fields depend on the underlying plugin.

### Result snapshots and historical diff

Saves per-host task output into named, versioned worker file groups, optionally
skipping failures, and compares current results with a selected earlier
version. **Use cases:** pre/post-change evidence, configuration drift, routing
delta review, incident timelines, and audit records. **Limitations:** snapshots
are local to each worker and retain up to the configured processor limit.
[CLI examples](workers/nornir/services_nornir_service_tasks_cli.md#saving-task-results-to-files)

### Configuration deployment

Pushes raw, file-sourced, or per-host Jinja2-rendered configuration through
Netmiko, Scrapli, or NAPALM. Supports merge/replace, batching, privilege
selection, command verification, dry-run, diffs, and plugin-specific error
detection. **Use cases:** standards rollout, remediation, service provisioning,
bulk changes, and generated configuration. **Limitations:** no universal
cross-device transaction; behavior is platform/plugin dependent.
[Task details](workers/nornir/services_nornir_service_tasks_cfg.md)

### Commit-confirmed and automatic revert

Exposes Netmiko commit-confirm/final-commit timing and NAPALM timed revert where
supported. **Use cases:** protect remote changes, validate reachability before
final commit, and reduce lockout risk. **Limitations:** only platforms and
drivers with the relevant transaction semantics can provide these safeguards.
[Commit-confirmed examples](workers/nornir/services_nornir_service_tasks_cfg.md#using-commit-confirmed)

### Network testing and compliance

Evaluates validated inline or `nf://` YAML suites, rendered per host with Jinja2
and job data. Tests can call CLI, network, configuration, or arbitrary task
plugins and use patterns, schemas, or custom Python functions. **Use cases:**
pre/post checks, compliance, acceptance testing, migration sign-off, regression
testing, and fault isolation. **Limitations:** test quality depends on reliable
collection and well-designed assertions.
[Task details](workers/nornir/services_nornir_service_tasks_test.md)

### Targeted test reporting

Supports test-name glob subsets, test groups, failed-only output, dry-run of the
rendered per-host suite, Markdown results, and an extensive mode that includes
raw task details and the generated suite. **Use cases:** focused remediation,
CI-friendly reports, audit evidence, and debugging why an assertion was built.
**Limitations:** extensive output can be large across many hosts.

### Structured data parsing

Turns live network state into structured data through dozens of NAPALM getters,
NTC or custom TextFSM templates, and TTP templates from inline text, `nf://`,
HTTP, or the `ttp_templates` collection. TTP input definitions can choose the
commands automatically. **Use cases:** inventory, interface/counter reports,
routing and neighbour analysis, validation, normalization, and workflow input.
**Limitations:** parser/getter coverage varies by platform.
[Task details](workers/nornir/services_nornir_service_tasks_parse.md)

### Custom Nornir tasks

Provides complete access to the Nornir task-plugin ecosystem: import any
installed task callable by dotted path, or fetch and execute an arbitrary Python
`task` function from `nf://`. All keyword arguments, host filters, RetryRunner
controls, result serialization, progress, tests, parsing, file snapshots, and
diff processors remain available. **Use cases:** call vendor SDKs, REST/NETCONF/
gNMI clients, databases, custom discovery, proprietary checks, or an existing
community plugin without changing NORFAB core. **Limitations:** there is no code
sandbox; plugins are trusted Python code and dependencies must exist on each
worker. [Task details](workers/nornir/services_nornir_service_tasks_task.md)

### NETCONF operations and transactions

Runs arbitrary ncclient manager or Scrapli NETCONF methods, retrieves/filter
configuration, capabilities and schemas, sends RPCs, and supports an ordered
transaction flow with lock, discard, edit, validate, confirmed/final commit,
failure cleanup, and unlock where the server supports them. **Use cases:**
model-driven configuration, YANG data retrieval, safe candidate changes, and
custom RPC automation. **Limitations:** plugin keyword names differ and device
NETCONF capabilities determine transaction steps.

### Network utility checks

Provides worker-side ICMP ping with count, timeout, size/payload, sweep, DF,
source, and payload matching, plus A/AAAA resolution through selected DNS
servers. **Use cases:** MTU/path testing, source-specific reachability,
name-resolution audit, dual-stack validation, and workflow gates.
**Limitations:** results reflect the selected worker's network vantage point.
[Task details](workers/nornir/services_nornir_service_tasks_network.md)

### Topology diagram generation

Builds Layer 2, Layer 3, OSPF, or IS-IS diagrams in DrawIO or yEd-compatible
formats, plus 3D viewer data, using N2G. Options cover link grouping, LAGs,
connected subnets, interface labels, and attaching source data. **Use cases:**
automated as-built documentation, topology review, protocol visualization,
design comparison, and incident analysis. **Interfaces:** currently implemented
as an NFCLI client workflow that calls Nornir CLI collection.
**Limitations:** accuracy is bounded by supported discovery commands, parsers,
and device data quality.
[Task details](workers/nornir/services_nornir_service_tasks_diagram.md)

### Device file transfer

Transfers files in either direction with dry-run, overwrite control, destination
file-system selection, socket timeout, MD5 verification, and Cisco IOS inline
transfer; sources can come from `nf://`. **Use cases:** image staging,
certificates, licenses, configuration backup/restore, and integrity-checked
artifact distribution. **Limitations:** the current implementation uses Netmiko
and requires compatible SCP or inline-transfer support.
[Task details](workers/nornir/services_nornir_service_tasks_file_copy.md)

### Runtime inventory management

Creates, reads, updates, deletes, or loads Nornir hosts without restarting a
worker; reads nested host data, manages group membership/defaults, and lists
hosts/platforms. Runtime hosts can also be created or replaced directly from
explicit NetBox device names. **Use cases:** ephemeral targets, dynamic
discovery, per-job metadata, lab inventory injection, source-of-truth handoff,
and debugging inventory resolution. **Limitations:** changes are worker-local
runtime state, not durable source-of-truth updates.
[Task details](workers/nornir/services_nornir_service_tasks_runtime_inventory.md) ·
[Create from NetBox](workers/nornir/services_nornir_service_tasks_create_host_from_netbox.md)

### NetBox and Containerlab inventory loading

Can merge Nornir inventory from a configured NetBox instance at startup/runtime,
or pull hosts from selected Containerlab workers with optional groups, default
credentials, dry-run, and Nornir reinitialization. **Use cases:** production
source-of-truth automation, lab-to-automation handoff, and using identical tasks
against physical and virtual networks. **Limitations:** imported platform and
connection data must map to installed Nornir plugins.

### Rich static and source-of-truth inventory

Accepts native Nornir hosts, groups, defaults, connection options, runner,
logging, and `user_defined` data. NetBox enrichment can add interfaces, IPs,
inventory items, connections, circuits, BGP peerings, config context, tags,
site/role data, and choose IPv4 or IPv6 primary management addressing.
**Use cases:** keep credentials/options in groups, drive templates from business
metadata, and give tasks a complete device context. **Limitations:** inventory
quality and secret handling remain deployment responsibilities.
[Inventory details](workers/nornir/services_nornir_service_inventory.md)

### SNMP operations

Supports GET, GETNEXT, walks, bulk operations, tables, SET, and multi-variable
operations over SNMPv2c or SNMPv3 inventory credentials; common filters and
result processors also apply. **Use cases:** telemetry collection, discovery,
bulk table retrieval, interface/environment audit, and controlled updates where
CLI access is unsuitable. **Limitations:** credentials, views, accessible OIDs,
and device agent support determine coverage; SET alters state.
[Task details](workers/nornir/services_nornir_service_tasks_snmp.md)

### Device targeting and concurrency

Filters hosts by name, group, platform, IP prefix, regular expression, and other
Nornir-Salt filter objects, supports exclusion and negation, then processes
devices concurrently. **Use cases:** exact maintenance lists, site/role groups,
platform-specific commands, canary scopes, exception lists, and horizontal
fleet scale. **Limitations:** throughput is constrained by worker sizing, device
session limits, latency, and task timeouts.
[Inventory details](workers/nornir/services_nornir_service_inventory.md)

### Connection pooling and watchdog

Reuses connections across jobs and tracks them by host/plugin; idle connections
can be retained indefinitely, closed immediately, or expired after a configured
timeout, with client-visible connection state and statistics. Failed hosts remain
errdisabled until the recovery timeout expires, can be included explicitly with
`on_failed` (`on-failed` in NFCLI), and can be inspected or recovered on demand
through NFCLI. Optional pre-task reset mode preserves the earlier always-recover
behavior and disables persistent errdisabled-host handling; it is mutually
exclusive with watchdog timeout recovery. Task results identify executed hosts
in `resources` and current failures in
`resources_failed`. **Use cases:**
low-latency repeated polling, limiting login churn, releasing scarce sessions,
diagnosing connection leaks, and suppressing repeated work against unreachable
devices. **Limitations:** long-lived sessions must align with device timeout and
credential-rotation policy; failed-host reasons are available only when captured
from the originating task result.
[Errdisabled-host task details](workers/nornir/services_nornir_service_tasks_errdisabled_hosts.md)

## NetBox service

The [NetBox service](workers/netbox/services_netbox_service.md) reads, provisions,
and reconciles NetBox data, including live-state collection through Nornir.

### Multiple NetBox instances

Names and connects to multiple NetBox instances from one worker, with a default
instance and per-call selection. **Use cases:** production/lab separation,
regional sources of truth, migrations, and shared automation across business
units. **Limitations:** schemas, plugins, credentials, and version compatibility
can differ between instances and must be managed explicitly.

### Resilient and tunable NetBox access

Configures connect/read timeouts, request retry count and backoff, TLS
certificate verification, GraphQL parallelism, cache mode/TTL, and branch
creation timeout. **Use cases:** slow or distant instances, transient API
failures, high-volume inventory reads, self-signed labs, and predictable
failure bounds. **Limitations:** aggressive retries or parallelism can increase
load on NetBox; disabling TLS verification is for controlled environments.
[Inventory details](workers/netbox/services_netbox_service_inventory.md)

### Status and compatibility checks

Reports reachability/status, installed NetBox and plugin versions, and
compatibility state for configured instances. **Use cases:** deployment
validation, upgrade readiness, support diagnostics, and workflow pre-flight
checks. **Limitations:** compatibility reporting covers NORFAB's known
requirements, not every custom NetBox plugin interaction.

### Response caching and cache control

Caches selected NetBox query results and exposes cache keys, values, creation
age, expiry, glob filtering, and targeted/bulk invalidation. Inventory
generation can use, refresh, or force cache behavior. **Use cases:** reduce API
load, accelerate repeated inventory builds, inspect stale data, and force fresh
reads after changes. **Limitations:** cached data can lag NetBox until expiry or
explicit refresh.

### REST passthrough

Sends direct HTTP requests to the configured NetBox REST API when no dedicated
task exists. **Use cases:** new NetBox endpoints and uncommon object types.
**Limitations:** callers must understand NetBox paths and payloads; this
low-level interface provides fewer task-specific guardrails.
[Task details](workers/netbox/services_netbox_service_tasks_rest.md)

### GraphQL queries

Builds and runs single, aliased, or raw GraphQL queries. **Use cases:** selective
reads, reporting, and reducing response payloads. **Limitations:** queries depend
on the target NetBox GraphQL schema; the public `graphql` task is deprecated in
code in favour of the lower-level helper for new internal development.
[Task details](workers/netbox/services_netbox_service_tasks_graphql.md)

### Generic object CRUD

Lists, searches, reads, creates, updates, and deletes arbitrary NetBox objects
and retrieves change logs, with field selection, pagination, ordering, bulk
payloads, PATCH updates, and dry-run for create/update/delete. **Use cases:**
broad object lifecycle automation, data migration, reporting, audit history,
and AI tool use. **Limitations:** generic operations require knowledge of the
NetBox data model and do not provide every safeguard of a dedicated task.
[Task details](workers/netbox/services_netbox_service_tasks_crud.md)

### Branch-aware changes

Supported get, sync, CRUD, raw REST, and paginated GraphQL tasks can target a named NetBox branch, and the service can delete a
branch through the NetBox Branching plugin. **Use cases:** stage designs,
review source-of-truth changes, test automation against proposed state, and
clean up completed branches. **Interfaces:** branch arguments are available on
supporting Python/REST/MCP tasks; branch deletion is not currently modelled in
NFCLI. **Limitations:** requires a compatible branching plugin and not every
NetBox operation is inherently branch-aware. Branch reads bypass the main-context
cache, including circuit retrieval and circuit termination path tracing.

### Device and interface retrieval

Returns devices and detailed interfaces, with optional IP, inventory item,
child-interface, and LAG relationships. **Use cases:** inventory exports,
capacity checks, and automation inputs. **Limitations:** completeness depends on
data maintained in NetBox.
[Device task](workers/netbox/services_netbox_service_tasks_get_devices.md) ·
[Interface task](workers/netbox/services_netbox_service_tasks_get_interfaces.md)

### Connection and circuit retrieval

Resolves physical, virtual, LAG, console, provider, and circuit relationships for
selected devices. **Use cases:** impact analysis, cabling audit, and circuit
reporting. **Limitations:** only relationships represented correctly in NetBox
can be returned.
[Connections](workers/netbox/services_netbox_service_tasks_get_connections.md) ·
[Circuits](workers/netbox/services_netbox_service_tasks_get_circuits.md)

### BGP peering retrieval

Returns BGP sessions associated with selected devices. **Use cases:** routing
inventory, peer audit, and configuration generation. **Limitations:** requires
the NetBox BGP plugin and compatible data.
[Task details](workers/netbox/services_netbox_service_tasks_get_bgp_peerings.md)

### Topology data

Produces normalized nodes and physical links from NetBox device and cable data.
**Use cases:** visualization, graph analysis, and topology validation.
**Limitations:** this represents documented NetBox state rather than live
discovery, and is bounded by cable and termination records.
[Task details](workers/netbox/services_netbox_service_tasks_get_topology.md)

### Nornir inventory generation

Builds Nornir hosts, groups, connection options, and optional interface,
connection, circuit, and BGP data from NetBox. **Interfaces:** Python API, REST,
and MCP; NFCLI does not currently expose this task directly under `netbox get`.
**Use cases:** source-of-truth-driven device automation. **Limitations:** platform
mapping, credentials, and required device fields must be modelled correctly.
[Task details](workers/netbox/services_netbox_service_tasks_get_nornir_inventory.md)

### Containerlab inventory generation

Converts NetBox devices and links into a Containerlab topology inventory.
**Use cases:** digital-twin labs and topology reproduction. **Limitations:**
selected NetBox devices must map to usable container kinds/images and modelled
links.
[Task details](workers/netbox/services_netbox_service_tasks_get_containerlab_inventory.md)

### IP address and prefix allocation

Allocates next-available addresses or child prefixes, assigns interface and
primary IP data, carries tenant/VRF/site/role/tags metadata, supports connected
peer addressing and point-to-point peer derivation, and performs bulk interface
allocation. **Use cases:** provisioning links, loopbacks, management addresses,
new devices, and template-driven zero-touch workflows.
**Limitations:** parent prefixes and assignment context must be valid; concurrent
external allocators require operational coordination.
[Create IP](workers/netbox/services_netbox_service_tasks_create_ip.md) ·
[Bulk IP](workers/netbox/services_netbox_service_tasks_create_ip_bulk.md) ·
[Create prefix](workers/netbox/services_netbox_service_tasks_create_prefix.md)

### Interface provisioning

Creates missing interfaces in bulk and expands alphanumeric interface ranges.
**Use cases:** device onboarding and templated chassis creation. **Limitations:**
creates interfaces but does not discover live state; device and interface type
inputs must match the NetBox model.
[Task details](workers/netbox/services_netbox_service_tasks_create_device_interfaces.md)

Live-state synchronization tasks report per-device Nornir collection failures
in their NetBox task errors while retaining usable results from other devices.

### Live interface reconciliation

Collects live interface configuration and operational data through Nornir.
Operational state fills MTU, duplex, and speed when absent from configuration
parsing. Missing or zero live MTU and speed values preserve existing NetBox
values. Existing descriptions can be preserved always, preserved only when
live text is empty, or overwritten by live text. The task computes a
desired/current diff, optionally maps live
interface names through ordered device- and model-aware
rename rules, and applies ordered create, update, and optional delete actions.
An empty NetBox interface set is valid, allowing a device to be initialized
entirely from discovered live interfaces.
Interface-name and VLAN-group mapping rules can be supplied inline or loaded
from YAML through `nf://` URLs. Live interface VLAN values can be numeric VIDs
or names; names are resolved against existing scoped NetBox VLANs before the
desired/current diff is calculated.
New interfaces accept any parsed type; existing interfaces use safe logical
type transitions that protect specific physical types and never downgrade to
the `other` fallback. **Use cases:**
source-of-truth maintenance and drift remediation. **Limitations:** parser
coverage determines live-state quality; deletion is opt-in and should be
reviewed with dry-run first.
[Task details](workers/netbox/services_netbox_service_tasks_sync_device_interfaces.md)

### Live VLAN reconciliation

Reconciles live VLAN names and descriptions with site- or VLAN-group-scoped
NetBox objects using ordered device, VLAN-name, and VLAN-ID mapping rules plus
an optional scalar VLAN-group fallback. Mapping rules can be supplied inline or
loaded from YAML through `nf://` URLs, using `match_device_names`,
`match_interface_names`, `match_vlan_ids`, and `set_vlan_group` for matching
and group selection. Existing descriptions support always, live-empty-only, or
never preservation. VLANs are identified by VID per scope;
the first device supplies values when later devices report a conflict.
**Use cases:** correct placeholder VLANs, maintain shared VLAN naming, and audit
layer-two source-of-truth drift. **Limitations:** parser coverage determines
live-state quality; the task does not delete VLANs because live data cannot
reliably identify stale NetBox objects.
[Task details](workers/netbox/services_netbox_service_tasks_sync_vlans.md)

### Live VRF reconciliation

Reconciles global VRFs and descriptions from live devices, and adds all observed
import/export route targets to the existing NetBox associations. Missing route
targets are created, and an optional multi-object custom field records the
devices on which each VRF was observed. Existing descriptions support the same
always, live-empty-only, or never preservation policy as interface and BGP
peering synchronization. If multiple NetBox VRFs share a matched name, the
lowest numeric ID is selected and a warning is logged. **Use cases:** VRF inventory,
route-target aggregation, and device-to-VRF inventory. **Limitations:** route
distinguishers and route policies are not stored; VRF objects, route-target
objects, route-target associations, and device associations are not removed
automatically.
[Task details](workers/netbox/services_netbox_service_tasks_sync_vrfs.md)

### Live IP and MAC reconciliation

Reconciles device IP assignments, derived prefixes, and interface MAC addresses
with NetBox, including interface-first IP matching, filters, inline or `nf://`
anycast ranges, VRF/site association, and controlled deletion behavior. **Use
cases:** IPAM accuracy and address/MAC drift correction.
**Limitations:** requires supported live parsers and accurate interface identity;
write runs should follow scoped dry-run review.
[IP sync](workers/netbox/services_netbox_service_tasks_sync_device_ip.md) ·
[Prefix sync](workers/netbox/services_netbox_service_tasks_sync_device_prefixes.md) ·
[MAC sync](workers/netbox/services_netbox_service_tasks_sync_mac_addresses.md)

### Hardware inventory reconciliation

Reconciles live chassis, module, and inventory records with NetBox and supports
custom TTP parsing templates, name mapping, and trusted Python transformers.
**Use cases:** asset audit, serial number capture, and module lifecycle.
**Limitations:** platform parser coverage and NetBox module modelling are
prerequisites; templates and transformer files execute as trusted code.
[Task details](workers/netbox/services_netbox_service_tasks_sync_device_inventory.md)

### BGP peering lifecycle

Creates or updates individual and bulk BGP sessions, and reconciles live BGP
neighbors with NetBox using dry-run, filters, optional stale-session deletion,
and tri-state existing-description preservation. **Use cases:** routing
source-of-truth onboarding and drift control.
**Limitations:** requires the NetBox BGP plugin, supported live parsing, and
consistent IP/ASN/VRF modelling.
[Create](workers/netbox/services_netbox_service_tasks_create_bgp_peering.md) ·
[Update](workers/netbox/services_netbox_service_tasks_update_bgp_peering.md) ·
[Synchronize](workers/netbox/services_netbox_service_tasks_sync_bgp_peerings.md)

### Live BGP community reconciliation

Collects named BGP communities from supported live devices, stores route
targets in NetBox IPAM and other types in the NetBox BGP plugin, appends
missing live names for the same value, and associates observed devices through
optional custom fields. **Use cases:** community inventory, naming audits,
device-to-community inventory, and source-of-truth onboarding.
**Limitations:** parser and NetBox plugin value support determine coverage;
objects are never deleted.
[Task details](workers/netbox/services_netbox_service_tasks_sync_bgp_community.md)

### Live BGP ASN reconciliation

Reconciles globally unique ASNs from supported live devices with NetBox IPAM,
preserves existing descriptions by default, and optionally associates each ASN
with the devices for which it is a local ASN. Missing ASNs are created only
when an existing RIR is supplied.
**Use cases:** ASN inventory, description audits, and device-to-ASN inventory.
**Limitations:** ASNs and device associations are never deleted automatically.
[Task details](workers/netbox/services_netbox_service_tasks_sync_bgp_asn.md)

### Interface description updates

Writes static or Jinja2-rendered descriptions using interface and connection
context. **Use cases:** circuit labels, neighbour descriptions, and
documentation standards. **Limitations:** supported port types are interfaces,
console ports, console server ports, and power outlet ports; templates should be
validated in dry-run mode.
[Task details](workers/netbox/services_netbox_service_tasks_update_interfaces_description.md)

### Drift assessment and coordinated synchronization

Runs selected synchronizers in read-only dry-run mode for drift reporting,
including inventory, interface, MAC, IP, and BGP peering state, or executes the
supported synchronizers in a fixed inventory, VLAN, prefix, VRF, interface,
MAC, IP, and BGP sequence. `sync_all` accepts per-task keyword arguments inline
or from an `nf://` YAML file and can skip individual stages. **Use cases:** audit
evidence, change planning, and scheduled source-of-truth maintenance.
**Limitations:** assessment is limited to implemented sync domains; `sync_all`
can make broad changes and requires careful deletion/filter policy.
[Check sync](workers/netbox/services_netbox_service_tasks_check_device_sync.md) ·
[Sync all](workers/netbox/services_netbox_service_tasks_sync_all.md)

## Containerlab service

The [Containerlab service](workers/containerlab/services_containerlab_service.md)
manages containerized network labs.

### Topology deployment

Downloads or accepts a topology definition, organizes lab files, and invokes
Containerlab deployment. Existing labs can be reconfigured and a node filter
can deploy only selected topology nodes. **Use cases:** integration testing,
training, reproducible labs, partial topology testing, and focused node
rebuilds. **Limitations:** requires a Containerlab-capable host, container
runtime, images, and sufficient compute/network privileges.
[Task details](workers/containerlab/services_containerlab_service_tasks_deploy.md)

### NetBox-driven deployment

Selects NetBox devices by tenant, explicit names, or filters; converts devices
and connections into a topology; allocates a non-conflicting management subnet
and host port range; and can preview, partially deploy, or reconfigure it.
**Use cases:** digital twins, topology reproduction, production-incident
rehearsal, and automated ephemeral test environments. **Limitations:** NetBox
roles/platforms must map to valid Containerlab node definitions and available
images.
[Task details](workers/containerlab/services_containerlab_service_tasks_deploy_netbox.md)

### Topology preview

Returns the generated NetBox-derived topology without deploying containers.
**Use cases:** design review, CI validation, image/kind mapping checks, and
change approval before consuming lab resources. **Limitations:** a valid
preview does not guarantee image availability or runtime host capacity.

### Lab inspection

Lists running labs and returns topology, container, labels, addressing, and
status information at summary or detailed level. **Use cases:** health checks,
resource discovery, troubleshooting, cleanup selection, and automation gates.
**Limitations:** reports the local Containerlab host's view and does not replace
in-device validation.
[Task details](workers/containerlab/services_containerlab_service_tasks_inspect.md)

### Lab lifecycle controls

Restarts labs from their topology or destroys associated containers, networks,
and artifacts. **Use cases:** clean test cycles and resource reclamation.
**Limitations:** disruptive by design; restart depends on the retained topology
and destroy removes runtime lab state.
[Restart](workers/containerlab/services_containerlab_service_tasks_restart.md) ·
[Destroy](workers/containerlab/services_containerlab_service_tasks_destroy.md)

### Configuration save

Invokes Containerlab save behavior for supported lab nodes. **Use cases:** lab
checkpointing and configuration preservation. **Limitations:** save behavior and
file persistence depend on the network OS kind and topology bindings.
[Task details](workers/containerlab/services_containerlab_service_tasks_save.md)

### Nornir inventory generation

Converts an inspected lab into Nornir-compatible hosts for immediate automation.
**Use cases:** running the same tests against lab and production targets.
**Limitations:** platform and management connection mapping must be compatible
with Nornir plugins.
[Task details](workers/containerlab/services_containerlab_service_tasks_nornir_inventory.md)

## FakeNOS service

The [FakeNOS service](workers/fakenos/services_fakenos_service.md) runs lightweight
simulated network CLI endpoints.

### Simulated network startup

Starts named FakeNOS networks in isolated child processes from file-based or
inline inventory, with multiple independent networks per worker. **Use cases:**
fast automation development, large endpoint mocks, demos, parser fixtures,
failure injection, and CI without device images. **Limitations:** simulation
implements configured command responses and is not a full network operating
system or forwarding-plane emulator.
[Task details](workers/fakenos/services_fakenos_service_tasks_start.md)

### Custom simulated network operating systems

Loads YAML NOS plugins at worker startup to define prompts, commands, and
responses, then references them from simulated hosts. **Use cases:** emulate
private command sets, reproduce a customer output sample, test a new parser, or
model an error response deterministically. **Limitations:** behavior must be
authored explicitly and does not emulate control-plane state.
[Inventory details](workers/fakenos/services_fakenos_service_inventory.md)

### Simulated network inspection

Returns network names, process metrics, and host inventory. **Use cases:** CI
health checks and test-environment discovery. **Limitations:** visibility is
limited to FakeNOS process and inventory state.
[Task details](workers/fakenos/services_fakenos_service_tasks_inspect_networks.md)

### Simulated network lifecycle

Stops one or all networks, or restarts a network using its current inventory.
**Use cases:** deterministic test reset and cleanup. **Limitations:** active
client sessions are interrupted and unsaved runtime state is discarded.
[Stop](workers/fakenos/services_fakenos_service_tasks_stop.md) ·
[Restart](workers/fakenos/services_fakenos_service_tasks_restart.md)

### Nornir inventory generation

Builds Nornir inventory for running simulated hosts. **Use cases:** testing
Nornir tasks and parsers without physical devices. **Limitations:** results
validate the simulated command surface, not vendor behavior.
[Task details](workers/fakenos/services_fakenos_service_tasks_get_nornir_inventory.md)

## Workflow service

The [Workflow service](workers/workflow/services_workflow_service.md) orchestrates
tasks across NORFAB services.

### YAML workflow orchestration

Runs ordered service-task steps from inline or `nf://` YAML, passing per-step
service, task, workers, positional/keyword arguments, and timeouts. **Use
cases:** multi-service runbooks, build-test-document pipelines, lab setup,
source-of-truth synchronization, and reusable operational procedures.
**Limitations:** steps execute in definition order; the DSL is not a general
distributed transaction engine, and compensation/rollback must be designed into
the workflow.
[Task details](workers/workflow/services_workflow_service_tasks_run.md)

### Result-driven branching and failure control

Runs a step only when any/all workers passed or failed selected earlier steps,
records skipped steps, can stop the workflow when a step fails, and can remove
benign no-match results. **Use cases:** remediate only failed compliance checks,
continue only after all pre-checks pass, run fallback collection, and abort a
change on partial failure. **Limitations:** conditions reference earlier steps
and evaluate NORFAB task success, not arbitrary expressions.

## Agent service

The [Agent service](workers/agent/services_agent_service.md) connects an LLM-backed
agent to NORFAB automation.

### LLM-assisted automation chat

Invokes an agent with natural-language instructions and returns the final
response or verbose LangChain invocation data. LLMs can use Ollama or Groq, and
agent tools invoke typed NORFAB service tasks. **Use cases:** guided operations,
multi-step investigation, natural-language data collection, and conversational
access to automation. **Limitations:** model/provider dependencies are optional;
outputs inherit model accuracy and changes require tool governance and review.
[Task details](workers/agent/services_agent_service_tasks_chat.md)

### Custom agent definitions

Loads an agent name, system prompt, LLM override, and typed NORFAB tool
definitions from an `nf://` YAML file; tool schemas are converted to Pydantic
models for the LLM. **Use cases:** role-specific NOC assistants, constrained
troubleshooting agents, change-review agents, and domain-specific tool sets.
**Limitations:** agent files and tool defaults are trusted configuration; a
mis-scoped tool can perform real changes.

## Client-side AI agent

The Python client and NFCLI also include an optional profile-driven agent that
runs beside the user rather than as a distributed Agent service worker.

### Multi-provider LLM profiles

Supports named and inheritable profiles for OpenAI, Anthropic, Ollama, Groq,
Mistral, OpenRouter, Google, and Amazon Bedrock models, with custom system
prompts and per-profile settings. **Interfaces:** Python API and NFCLI.
**Use cases:** switch models by environment, separate read-only and change
personas, and keep lab/production instructions distinct. **Limitations:**
provider packages, credentials, cost, privacy, and availability are external
deployment concerns.

### Automatic NORFAB tool discovery

Discovers running services and eligible task schemas, then creates typed
LangChain tools automatically; profiles can also define inline tools with fixed
service/task arguments. **Use cases:** an agent that immediately understands a
new service plugin, constrained workflow helpers, and natural-language access to
the full fabric. **Limitations:** broad discovery can expose powerful tasks;
profiles and service permissions must enforce least privilege.

### External MCP tool federation

Loads tools from multiple stdio, SSE, or streamable-HTTP MCP servers alongside
NORFAB tools. **Use cases:** combine network automation with ticketing, source
control, cloud, or documentation tools in one reasoning loop. **Limitations:**
each external server adds its own trust, authentication, availability, and
prompt-injection boundary.

### Local RAG knowledge base

Indexes configured files/directories into a persistent Qdrant collection using
FastEmbed and gives the agent a top-K retrieval tool. **Use cases:** ground
answers in standards, runbooks, designs, customer notes, or local NORFAB
documentation. **Limitations:** retrieval quality depends on sources,
embeddings, chunking, and document freshness.

### Conversation memory and streaming

Supports token streaming, reusable thread IDs, resettable conversations,
in-memory continuity, and optional persistent SQLite checkpoints.
**Use cases:** interactive troubleshooting that carries evidence across turns,
long investigations, and resumable operator sessions. **Limitations:** retained
conversation data may contain operationally sensitive content.

### Sandboxed local filesystem tools

Optionally lets the agent read, write, edit, and list files, with all paths
restricted to the current working directory. **Use cases:** produce reports,
update local runbooks, inspect generated artifacts, and prepare configuration
inputs. **Limitations:** write/edit tools still modify files inside the allowed
root and should be disabled for analysis-only profiles.

## File Sharing service

The [File Sharing service](workers/filesharing/services_filesharing_service.md)
distributes controlled inventory assets through `nf://` URLs and synchronizes
configured Git remotes on demand through `git://` URLs.

### File discovery

Lists one directory level or recursively walks files beneath the configured
base directory. **Use cases:** locating templates, playbooks, golden configs,
and software artifacts. **Limitations:** hidden/special content is skipped by
walk and paths cannot escape the worker base directory.
[List files](workers/filesharing/services_filesharing_service_tasks_list_files.md) ·
[Walk](workers/filesharing/services_filesharing_service_tasks_walk.md)

### File metadata and integrity

Reports existence, byte size, and MD5 hash. **Use cases:** pre-flight checks,
cache validation, and transfer verification. **Limitations:** MD5 is provided
for integrity comparison, not cryptographic trust or publisher authentication.
[Task details](workers/filesharing/services_filesharing_service_tasks_file_details.md)

### Streamed file retrieval

Streams files in configurable chunks with offset/credit pipelining. The Python
client helper caches downloads, skips transfer when the local MD5 matches,
verifies the completed stream, and can return a path or decoded text.
**Interfaces:** Python API is preferred; direct NFCLI, REST, or MCP calls expose
lower-level chunk-oriented results. **Use cases:** distributing templates and
software efficiently, resuming chunk flow, and avoiding duplicate downloads.
`git://<remote-name>/<path>` first synchronizes the named remote through the
File Sharing service, then streams the file from its configured `nf://` mount.
**Limitations:** only `nf://` paths under the configured base directory and
paths from configured `git://` remotes are accepted.
[Task details](workers/filesharing/services_filesharing_service_tasks_fetch_file.md)

### Read-only Git remotes

Uses GitPython to shallow-fetch configured Git repository branches into
independent managed folders and serves each snapshot through its configurable,
safe `nf://<mount>/...` path. Mounts default to the remote name. Configured
clients and workers can use `git://<remote-name>/<path>` to synchronize a
remote on demand and retrieve a file in one operation. Git access and
credentials remain isolated to the File Sharing worker, whose
`resolve_git_url` task returns the published `nf://` URL. Configured
local repositories are initialized on worker startup without fetching content;
operators can list remotes, inspect synchronization state, explicitly create or
delete runtime-registered remote definitions and local data, or enable
interval-based refresh. NFCLI exposes these operations under `filesharing git
create-remote`, `clone-remote`, and `delete-remote`.
Public HTTPS repositories require no credentials. Authenticated remotes support
username/password or username/token authentication, with credentials redacted
from inventory, task results, errors, and logs. Git authentication is fully
non-interactive; rejected credentials fail the task without opening terminal,
browser, credential-helper, or GUI prompts. **Interfaces:**
Python API, NFCLI, REST, and MCP tasks `get_remotes`, `create_remote_git`,
`delete_remote_git`, `git_clone`, and `resolve_git_url`. **Use cases:**
distributing version-controlled templates, playbooks, and automation assets
without changing consuming workers.
NFCLI renders `show filesharing remotes brief` as a table, `detail` with complete
remote data, and `summary` as nested counts with per-remote last synchronization
attempts. File metadata is exposed under `show filesharing files details`.
**Limitations:** remotes are read-only; the system Git executable is required,
SSH credential management is not provided, shared snapshots contain no Git
history, refresh is polling-based, and each remote tracks one branch.
[Design decision](development/adr_extensible_data_sources_and_git_sync.md)

## FastAPI REST service

The [FastAPI service](workers/fastapi/services_fastapi_service.md) is NORFAB's
HTTP/JSON gateway.

### Generated service APIs

Discovers eligible service tasks and generates REST endpoints from their
schemas, descriptions, paths, and declared GET/POST/PATCH/DELETE methods. Tasks
can be rediscovered at runtime. **Interfaces:** REST is the delivered interface;
NFCLI and Python API administer the service. **Use cases:** portals, OSS/BSS,
ITSM, webhooks, CI pipelines, and non-Python consumers. **Limitations:** only
tasks declaring REST exposure are published.

### OpenAPI documentation and validation

Publishes OpenAPI JSON plus Swagger UI and ReDoc, with Pydantic request
validation; its OpenAPI schema is also retrievable as a NORFAB task.
**Use cases:** integration discovery, client generation, contract testing,
manual API execution, and archiving an interface specification. **Limitations:**
generated schemas are bounded by task type annotations and metadata.

### Bearer authentication

Stores, checks, lists, expires, and revokes API bearer tokens. **Interfaces:**
token administration is deliberately excluded from REST and MCP and is
performed through NFCLI or the Python API. **Use cases:** API consumer access
control and token rotation. **Limitations:** the service does not provide native
HTTPS; use a reverse proxy or load balancer for TLS termination.
[Authentication details](workers/fastapi/services_fastapi_service_task_auth.md)

## FastMCP service

The [FastMCP service](workers/fastmcp/services_fastmcp_service.md) exposes NORFAB
to Model Context Protocol clients over streamable HTTP.

### Generated MCP tools

Discovers eligible service tasks and publishes typed MCP tools with stable
service/task names, JSON input schemas, descriptions, and MCP behavioral
annotations such as read-only, destructive, idempotent, and open-world hints.
**Interfaces:** MCP is the delivered interface; NFCLI and Python API administer
the service. **Use cases:** VS Code assistants, AI agents, capability-aware tool
selection, and safer approval UX. **Limitations:** annotations inform clients
but do not enforce authorization.

### Task-authored MCP prompts

Publishes parameterized prompts declared by service tasks; retrieving a prompt
returns messages without executing the task. Built-in Nornir prompts guide an
agent through safe operational-data collection and hypothesis-driven
troubleshooting with narrow host filters and read-only commands. **Use cases:**
guided tool use, repeatable investigation methods, and task-specific agent
instructions. **Limitations:** prompt availability is task-defined and a prompt
itself performs no automation.
[Prompt details](workers/fastmcp/services_fastmcp_service_task_get_prompts.md)

### Tool policy and discovery

Supports first-match ordered allow/reject rules with service and task globs;
rejecting a task also hides its prompts. Tools/prompts can be rediscovered and
inspected in full or filtered by service/name; NFCLI can show effective tool and
result guardrails in separate sections. **Use cases:** read-only agent profiles,
service allow-lists, hiding configuration tasks, and integration
troubleshooting. **Limitations:** unmatched tasks are allowed by default, so a
strict allow-list needs a final catch-all reject rule.
[Tool details](workers/fastmcp/services_fastmcp_service_task_get_tools.md)

### Argument guardrails

Evaluates `contains`, `equals`, or regex rules against top-level MCP call
arguments before dispatch. Built-in task guardrails and deployment-specific
rules can be combined; Nornir CLI defaults reject reloads, configuration mode,
destructive commands, device shells, software operations, and outbound
sessions. Nornir configuration defaults reject reload/restart, operational
`do`/`run`, delete/erase/format, zeroize, and outbound-session inputs.
**Use cases:** expose flexible operations while blocking unsafe values and
tailoring prohibited commands to local policy. **Limitations:**
guardrails inspect inline arguments only and do not inspect content later loaded
from `nf://` files; they complement rather than replace authorization.

### Result guardrails

Applies `limit`, `replace`, and blocking regex rules in their configured order
to each completed MCP task result. Limit rules measure
the compact JSON aggregate at the point where they appear. Content rules
recursively inspect string values below each worker's `result` and `diff`.
Oversized content is replaced by one bounded base result with job-UUID retrieval
guidance, while regex blocking replaces only an affected worker field with its
configured message. **Use cases:** model-context budgets, deterministic
credential redaction, and deployment-specific indirect-prompt-injection
deny-lists. Built-in Nornir CLI MCP guardrails redact common network-device,
Linux, HTTP header, URL credential, OAuth token, netrc, and PEM private-key
secrets before delivery while preserving the raw stored job result.
**Limitations:** rules are pattern-based, metadata fields are not
content-inspected, and trusted retrieval by UUID returns the unsanitized raw
database result.

### MCP bearer authentication

Optionally protects the MCP endpoint with expiring bearer tokens.
**Interfaces:** token administration is deliberately excluded from REST and MCP
and is performed through NFCLI or the Python API. Configurable issuer/resource
URLs and required scopes support MCP authorization metadata. **Use cases:**
authenticating MCP clients, scoped access, token expiry, audit, and rotation.
**Limitations:** authentication is disabled by default and transport/TLS
protection must be designed as part of deployment.
[Authentication details](workers/fastmcp/services_fastmcp_service_task_auth.md)
