# ADR - Hermes Workers and Distributed Network Agents

**Status:** Proposed. **Updated:** 18 October 2026.
Interfaces below are planned, not implemented.

## The WHY

Build a fleet of agents that monitors networks, investigates faults, performs
configured remediation and verifies results. Engineers assign work through one
command or chat, with evidence and history available for review.

NorFab already provides distributed network tasks. Hermes supplies profiles,
reasoning, sessions, memory, skills, scheduling and delegation. A lightweight
wrapper combines them without rebuilding Hermes features inside NorFab.

### Key use cases

| Operator request | Agent work and useful output |
| --- | --- |
| "Customer A cannot reach their application. Find where it breaks." | Resolve the customer/site/VRF from inventory, inspect relevant interfaces, VLANs, routes and policies, and choose follow-up checks. Return the suspected failure point, evidence and remaining unknowns. |
| "These sites alarmed together. Is there one underlying fault?" | Check shared circuits, uplinks and routing dependencies across affected sites. Separate observed failures from likely consequences and identify the next check that would distinguish competing causes. |
| "Can we take this core router out tonight?" | Inspect redundancy, alternate paths, routing peers and current faults. Produce maintenance blockers, prechecks, expected impact and a verification plan; highlight dependencies that could not be checked. |
| "Watch this service after the change and tell me if it regresses." | Run agreed checks before and after maintenance, compare results, investigate deviations and report whether the change met its acceptance criteria. Continue scheduled observation for a defined period. |
| "This circuit drops every few days. Build a case for the carrier." | Revisit the circuit, collect timestamped state, counter deltas and optics where available, and relate findings to supplied incident history. Produce a concise evidence package and list missing measurements. |
| "Bring this new branch into service and find what is still missing." | Execute the approved commissioning workflow, check inventory, connectivity, addressing and routing, then investigate failed acceptance tests. Return completed checks, blockers and evidence for handover. |
| "The same fault is back. Use what we learned last time." | Retrieve prior findings and procedures, verify that the symptoms match, execute a configured recovery workflow when permitted, and test the outcome. Record what changed in the diagnosis or procedure. |
| "Hand over the unresolved network issues to the next shift." | Summarize selected sessions and scheduled findings: affected services, evidence, actions taken, current status and next checks. Preserve references so the next operator can continue the investigation. |

These workflows need the relevant inventory, device tasks and evidence sources.
Ticket history, telemetry and carrier systems require configured tools or supplied
data; the Hermes wrapper does not add those integrations automatically.

Evaluate success through investigation time, verified outcomes, incorrect
conclusions and model cost.

## The WHAT

Create a dedicated **`hermes` service**. Each worker hosts a Hermes instance
with multiple named agents using native profiles. Instances can run across
hosts; agent count is not tied to worker count.

### Key features

| Capability | Implementation owner |
| --- | --- |
| Profiles, concurrent sessions and local subagents | Hermes |
| Models, reasoning and context management | Hermes |
| Memory, skills and optional retrieval integrations | Hermes |
| Cron, execution history and native delivery | Hermes |
| Agent discovery and cross-worker routing | NorFab |
| Network tools | Native `NFPClient` calls; no MCP integration |
| Remote chat, commands, progress and interruption | Thin NorFab adapters |

Preserve native profile creation, cloning and lifecycle management. Keep existing
`agent` and `client-agent` implementations separate. Do not introduce another
agent framework, scheduler, memory store or incident coordinator.

### Operator interface

Use `hermes <action> <agent>` for commands and `hermes chat <agent>` for chat.
The examples assume profiles named `interfaces` and `routing`; these are actual
profile names, not aliases. `workers` selects the Hermes host.

**Discover and invoke:**

```bash
nf# hermes agents
nf# hermes agents workers hermes-lab-*
nf# hermes status workers hermes-lab-1
nf# hermes invoke interfaces "Check interfaces on r1"
nf# hermes invoke interfaces "Check interfaces on r1" workers hermes-lab-1
nf# hermes chat interfaces workers hermes-lab-1
```

**Sessions and runs:**

```bash
nf# hermes sessions interfaces workers hermes-lab-1
nf# hermes chat interfaces session session-123 workers hermes-lab-1
nf# hermes invoke interfaces "Summarize the errors" session session-123 workers hermes-lab-1
nf# hermes interrupt interfaces run run-456 workers hermes-lab-1
```

Use returned session/run IDs. `session` maps to task `session_id`; `run` maps
to `run_id`. Omitting `session` starts a new conversation.

**Schedules and agent management:**

```bash
nf# hermes schedules interfaces workers hermes-lab-1
nf# hermes pause interfaces schedule check-123 workers hermes-lab-1
nf# hermes resume interfaces schedule check-123 workers hermes-lab-1
nf# hermes history interfaces schedule check-123 workers hermes-lab-1
nf# hermes create interfaces from nf://hermes/agents/interface-check.yaml workers hermes-lab-2
nf# hermes stop interfaces workers hermes-lab-2
nf# hermes start interfaces workers hermes-lab-2
```

`pause`/`resume` affect a schedule; `stop`/`start` use native profile lifecycle
operations. Neither implicitly interrupts already dispatched work. These short
commands map to `schedule` and `manage_agent`; they add no new runtime behavior.

**Chat keeps the selected worker, agent and session:**

```bash
nf# hermes chat interfaces workers hermes-lab-1
hermes-lab-1/interfaces> Check interfaces on r1
hermes-lab-1/interfaces> Check them every five minutes and report persistent errors
hermes-lab-1/interfaces> /sessions
hermes-lab-1/interfaces> /new
hermes-lab-1/interfaces> /agent routing
hermes-lab-1/routing> /agent interfaces workers hermes-lab-2
hermes-lab-2/interfaces> /exit
```

Schedule creation through chat requires the native cron tools. `/agent` resolves
within the current worker unless `workers` is supplied, then starts a session
on the selected profile. `/exit` leaves chat without stopping schedules.
`hermes chat` alone opens a worker/agent selector.

**Targeting rules:**

- Without `workers`, resolve the agent across available Hermes workers. A unique
  match runs directly; duplicate names require explicit worker selection.
- `agents` and `status` may query multiple workers, including glob selectors.
  Invocation, chat and changes must resolve to exactly one worker/profile.
  Creation requires one explicit worker because the profile does not exist yet.
- Resume sessions on their original worker. An unavailable owner returns an
  error; do not silently route the conversation elsewhere.
- This selects the **Hermes worker**. Network worker/device targets come from
  the agent's tool configuration and request, such as `r1` above.

### Worker tasks

All tasks use service `hermes` and standard NorFab `Result` envelopes.

| Task | Interface |
| --- | --- |
| `get_agents` | List all hosted profiles, including dynamically created agents, with worker and availability. |
| `get_agent` | `agent`: effective instructions, tools and redacted configuration. |
| `manage_agent` | `action`, `agent`, optional `definition`/`source`: native create, clone, start, stop, restart or explicit delete. |
| `invoke` | `agent`, `instructions`, optional `session_id`: response, run/session IDs, worker, stop reason and available usage. |
| `get_sessions` | `agent`, `limit=20`: native session listing. |
| `get_session` | `agent`, `session_id`, `limit=50`: native session messages. |
| `command` | `agent`, `command`, optional `session_id`: supported native commands, without shell dispatch. |
| `interrupt` | `agent`, `run_id`: request interruption and return acknowledgement. |
| `schedule` | `agent`, `action`, optional `schedule_id`/`definition`: native cron create, list, update, pause, resume, remove, run or history. |
| `get_status` | Optional `agent`: instance/profile readiness, active runs, scheduler health and errors. |
| `get_inventory` | Redacted worker inventory. |
| `get_version` | NorFab, Python and pinned Hermes revision. |

### Limitations

- Hosting, native commands and scheduled execution require verification against
  a pinned Hermes revision; full remote CLI parity is not assumed.
- Profiles isolate state, not OS permissions. Instance failure affects its agents.
- Sessions and schedules remain with their owner; no automatic migration or failover.
- Concurrency depends on host capacity, provider limits and model cost.
- Scheduled AI investigations do not replace high-rate telemetry collection.
- Memory can become stale; diagnoses and remediation need current evidence.
- Tool configuration and service credentials bound actions. Prompts do not
  provide authorization; this wrapper adds no broker-wide access control.
- Interruption cannot undo dispatched changes. Inspect results before retrying.

## The HOW

### Critique: why choose Hermes despite its drawbacks?

#### Cons — the case against this approach

- **A full application is a heavy worker dependency.** Hosting its gateway,
  profiles, commands and background jobs creates more integration work than
  embedding a model/tool loop. A "thin wrapper" is an assumption to prove.
- **Upstream coupling becomes an ongoing cost.** Changes to profile contexts,
  tool registration or process startup can break the integration. NorFab must
  pin versions, test upgrades and potentially wait for upstream fixes.
- **It complicates operations.** Operators must understand NorFab jobs and Hermes
  sessions/schedules. Inventory and live configuration can disagree; a failure
  may span the broker, gateway, model provider and downstream network task.
- **Distribution does not supply reliable fleet coordination.** Routing agents
  across workers does not provide shared device ownership, failover or protection
  against conflicting changes. Those gaps remain even if every agent works well.
- **Routine monitoring is a poor reason to add an LLM.** Known thresholds,
  configuration comparisons and verification tests are cheaper, faster and more
  repeatable as deterministic tasks. Running an agent on every healthy polling
  cycle can add expense without improving detection.
- **Memory and delegation can amplify errors.** An incorrect lesson can influence
  later runs; several agents can repeat or reinforce the same mistaken diagnosis.
  More agents add cost and coordination overhead without guaranteed accuracy.
- **A shared instance increases failure impact.** Multiple profiles save resources,
  but a runtime failure affects all hosted agents. Profile separation does not
  provide process-level security isolation.

#### Pros — what justifies considering it

- **A complete persistent-agent feature set:** profiles, sessions, skills,
  memory, scheduling and delegation address the requested use cases together.
- **Less agent machinery for NorFab to maintain:** reuse native implementations
  and their improvements instead of implementing each capability locally.
- **Useful adaptive investigations:** an agent can choose follow-up checks when
  the next step depends on device output and no complete runbook exists.
- **Natural operator interaction:** one command starts work; chat continues it
  with the same context and access to network tools.
- **Flexible placement:** several specialists can share a lab worker, while
  larger deployments place instances near their network services.

#### Why it is chosen nonetheless

The requirement includes persistent specialists that investigate, retain useful
procedures, schedule work and collaborate through NorFab. A small model wrapper
would leave NorFab responsible for building much of that behavior. Hermes is
chosen provisionally because reusing that feature set may cost less than owning
an equivalent agent framework.

Hosting it as a NorFab worker gives operators remote discovery, invocation and
job reporting through their existing interfaces. Native `NFPClient` tools reuse
network task schemas and routing directly. This convenience is the reason to
accept hosting complexity over a standalone Hermes installation.

The trade-off is explicit: **accept dependency and lifecycle integration work
in exchange for native agent capabilities.** This does not establish Hermes as
better at monitoring, safer at remediation, or more accurate than alternatives.
Those outcomes need comparative tests.

#### Integration options

| Option | Best fit | Trade-off / decision |
| --- | --- | --- |
| Hosted Hermes worker (proposed) | Persistent specialists, remote chat and scheduled investigations | Unified NorFab access; highest lifecycle and upstream compatibility burden. Proceed only if the hosting spike stays small. |
| Standalone Hermes with a native NorFab tool plugin | Hermes users needing network automation and native interfaces | Less hosting glue and a useful fallback. NorFab would not own agent discovery, invocation or lifecycle without another adapter. No MCP required. |
| Extend the existing client/Agent service | Interactive task assistance with limited persistence needs | Reuses existing interfaces, but matching Hermes profiles, skills and scheduling would expand NorFab's agent implementation. |
| Deterministic NorFab tasks/workflows plus external triggers | Known checks, drift rules, remediation and verification | Predictable execution and no model cost for routine work; engineers must encode the procedure. |
| Monitoring-triggered agent investigations | Continuous monitoring with occasional ambiguous faults | Monitoring detects events; an agent investigates selected cases. Requires trigger filtering, but avoids model calls for every healthy polling cycle. |

#### Fit to the use cases

| Use case | Preferred approach | Where Hermes adds value |
| --- | --- | --- |
| Customer reachability | Structured inventory and device checks, directed by an agent | Choose the next check across services and explain where the evidence stops. |
| Common fault across sites | Monitoring correlation plus topology/dependency queries | Investigate competing causes and coordinate specialists when the fault crosses domains. |
| Maintenance readiness | Deterministic prechecks and operator review | Investigate blockers and assemble a device/service-specific impact and verification plan. |
| Observation after a change | Explicit acceptance tests and existing monitoring | Investigate regressions and retain the change context across follow-up checks. |
| Intermittent circuit faults | Telemetry/history for capture; scheduled agent investigation | Assemble evidence over time and prepare a carrier escalation. Polling alone can miss short faults. |
| Branch commissioning | Approved workflow and repeatable acceptance tests | Diagnose failed steps and explain what prevents handover. |
| Recurring fault recovery | Reviewed recovery workflow with measured postconditions | Recall prior lessons, check applicability and investigate unsuccessful recovery. |
| Shift handover | Session/evidence records with operator review | Produce a concise briefing and preserve context for continued work. |

#### When to reconsider the decision

Use standalone Hermes with the native NorFab plugin if worker hosting requires
copying runtime internals or maintaining a fork. Prefer the existing agent or
deterministic workflows if representative investigations gain little from
persistent skills, memory or delegation. Expand to a fleet only when it improves
verified outcomes or investigation time enough to justify its extra cost.

### Runtime

```text
NFCLI / Python -> broker -> HermesWorker
                              |-- Hermes gateway: profiles, sessions, cron
                              |-- native tools -> NFPClient -> network workers
```

Host Hermes's multiplexing gateway through a small platform adapter. Use native
profile contexts, concurrency and session handling. Keep controls responsive
while agents run; never switch process-wide environment variables per request.
Hermes supports [gateway multiplexing](https://hermes-agent.nousresearch.com/docs/user-guide/multi-profile-gateways),
and agent cron requires a [running gateway](https://hermes-agent.nousresearch.com/docs/user-guide/features/cron).

Pin Hermes in an optional dedicated environment. Set a worker-specific instance
root under `__norfab__` before importing it; Hermes owns profile homes beneath
that root. Preserve state on restart and close native resources on shutdown.
Verify the selected revision's Python requirements and Windows/Linux support.

### Custom agents

Map the worker file through normal NorFab inventory:

```yaml title="hermes/network-worker.yaml"
service: hermes
agents:
  interface-check-agent:
    from_yaml_file: nf://hermes/agents/interface-check.yaml
  routing-check-agent:
    instructions: Analyze supplied routing evidence and explain findings.
    hermes:
      model:
        provider: ollama
        default: qwen3:8b
    toolsets: [memory, skills]
    tools: {}
```

Each mapping key names a native profile. Definitions are inline or referenced
through `nf://` or `git://`; referenced files have no name wrapper. Do not merge
sibling overrides into referenced definitions.

```yaml title="hermes/agents/interface-check.yaml"
instructions: |
  Check interface health, report evidence and retain useful procedures.
hermes:
  model:
    provider: ollama
    default: qwen3:8b
  agent:
    max_turns: 15
toolsets: [norfab, memory, skills]
tools:
  inspect_interfaces:
    description: Read interface details on r1.
    norfab:
      service: nornir
      task: cli
      workers: nornir-worker-1
      timeout: 60
      kwargs:
        FB: r1
        commands: show interfaces
run_timeout: 300
```

Choose commands appropriate to the devices. Native Hermes keys/toolset names
must be verified against the pinned revision.

| Definition field | Meaning |
| --- | --- |
| `instructions` | Required operating instructions. |
| `description` | Optional discovery summary; defaults to profile name. |
| `hermes` | Native configuration; credentials use Hermes auth/environment handling. |
| `toolsets` | Enabled native toolsets, including `norfab` for network tools. |
| `tools` | Named NorFab tool definitions; empty means no network tools. |
| `run_timeout` | Run budget in seconds, default 300; applies to scheduled runs too. |

Validate inventory at startup and apply changes on restart. Inventory-owned
settings remain authoritative; native profile lifecycle changes refresh discovery
live. Removing an inventory entry does not delete history. Preserve profiles
created through Hermes and never write runtime state back into inventory.

### Native tools

Register tools through Hermes's [plugin interface](https://hermes-agent.nousresearch.com/docs/developer-guide/plugins).
Use existing NorFab task schemas and bind calls to their profile/run context.

| Tool field | Meaning |
| --- | --- |
| `description` | Optional override of the task description. |
| `input_schema` | Optional narrower JSON Schema; otherwise derive from the task, excluding fixed arguments. |
| `norfab.service`, `norfab.task` | Required destination. |
| `norfab.workers` | Job routing selector, default `any`; never a task kwarg. |
| `norfab.timeout` | Child timeout, default 60 seconds, capped by remaining run budget. |
| `norfab.kwargs` | Fixed arguments; reject model attempts to override them. |
| `norfab.job_data` | Model argument names moved into task `job_data`; fixed job data takes precedence. |

Validate final arguments and preserve downstream failures and job UUIDs.
Profile-specific tool definitions must remain isolated under concurrent calls,
including identical tool names. In-process handlers use `self.client`; Hermes
child processes create their own `NFPClient`, never inherit live sockets.

### Routing, chat and continuous operation

- Resolve agent names to `(worker, profile)`; duplicate names require an explicit
  worker selector. Session identity is `(worker, profile, session_id)`.
- Use one invocation path for chat and tasks. Hermes retains transcripts;
  NorFab retains job outcomes and session references.
- Bridge progress to job events and required replies to `Job.request_input`.
  Noninteractive runs must defer or fail required interactions without hanging.
- Wrap supported native commands; publish the supported subset. Start with
  help, session selection/reset, memory and skill inspection.
- Use native cron stores, history, restart handling and delivery. Scheduled
  results remain accessible without an active NFCLI client.
- Preserve native local delegation. Cross-worker delegation calls `hermes.invoke`
  with an explicit agent/worker, propagated deadline and bounded call depth.

### Implementation and acceptance

1. **Prove hosting:** pin Hermes; verify multiplexing, profile lifecycle,
   concurrent tool isolation, sessions, commands, scheduled child clients and
   cleanup on Windows/Linux. Seek an upstream extension if hosting would require
   copying substantial runtime code.
2. **Build the wrapper:** worker, task models, native tools and platform adapter;
   register service `hermes`.
3. **Add interfaces:** profile management, sessions, commands, one-command
   invocation and `hermes chat`. Verify positional syntax with PICLE.
4. **Enable monitoring:** native cron management/history and an interface-check
   example with configured remediation and verification.
5. **Validate the fleet:** concurrent profiles within one worker, multiple workers,
   delegation, restart persistence, owner failure and interruption while busy.

Follow the [testing framework](../testing/norfab_testing_framework.md), using
fake model responses and dummy tasks for repeatable tests. Acceptance requires:

- One-command invocation and resumable chat with the correct named agent.
- Multiple concurrent profiles with isolated tools and persistent state.
- Native-client network calls and working cross-worker delegation.
- Scheduled checks without NFCLI, visible history and restart persistence.
- Responsive controls, preserved failures and clean resource shutdown.
- Reuse of Hermes implementations for profiles, memory, skills and scheduling.
