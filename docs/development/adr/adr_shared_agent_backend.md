# ADR - Shared Core Backend for Client and Worker Agents

## Status

Implemented (MVP). Client and worker execution share `NFAgent`.

## Date

2026-10-31.

## Goals

1. Chat with a model that can call running NorFab tasks directly through native
   tools backed by `NFPClient.run_job`.
2. Define specialized agents using the existing YAML `system_prompt` and named
   `tools` format, including schemas, fixed task arguments and `job_data`.

Use `norfab/core/agent.py` for both client and worker execution. Make surgical
changes to the existing code. Backward compatibility is not a requirement.
Do not add helper functions, runtime classes, configuration translation layers
or parallel execution paths.

## Review

Review of `norfab/core/agent.py`, `norfab/core/client.py`,
`norfab/workers/agent_worker/agent_worker.py` and `norfab/core/worker.py` found:

| Finding | Smallest useful change |
| --- | --- |
| Core already discovers services, reads task schemas and creates native task tools. Worker duplicates model construction, schema generation, tool dispatch and graph invocation. | Keep core execution and delete the worker copies. |
| `NFAgent.__init__` reads client inventory itself, preventing direct worker reuse. | Accept a configuration dictionary. Move the existing profile-loading block into `NFPClient.get_agent`. |
| Worker default agent only lists tasks and fetches their descriptions. It cannot directly execute arbitrary discovered tasks. | Use core's default system prompt and native task discovery for the worker default too. Remove the obsolete built-in definition. |
| Discovered and inline tools repeat the same schema/tool construction. Both already dispatch through core `make_runnable`. | Have existing discovery collect inline-format definitions and pass them to existing `make_agent_inline_tools`. |
| Profile loading and tool construction mutate source dictionaries; dispatch pops fixed `job_data` from the definition. | Copy configuration once in the constructor and copy fixed kwargs/job data inside the dispatch closure on each call. |
| Worker model cache uses only the model name, ignoring provider and settings. Core already has a provider factory. | Delete the worker cache and use existing core `_make_llm`. Forward constructor settings there directly after removing `provider`. |
| Discovery assumes `agent` metadata is a dictionary, but `Task(agent=False)` exposes a boolean. Its docstring also incorrectly describes MCP filtering. | Skip `agent=False` and `agent.enabled=False`; correct the docstring. |
| Core imports optional MCP, RAG and SQLite dependencies even when unused; the two install extras do not independently cover core imports. | Move feature imports into their existing feature branches/functions and explicitly list common runtime dependencies in both extras. |

Core builds eagerly and always provides at least in-memory conversation history.
Keep that simple behavior and correct docstrings claiming lazy construction or
memory only when enabled. A fresh worker agent per call already prevents history
from carrying between jobs; no separate stateless policy is needed.

## Decision

Keep one linear execution path:

```text
client.get_agent -> resolve profile -> NFAgent(config)
worker.invoke   -> load definition -> NFAgent(config)

NFAgent -> discover/collect tools -> build tools -> build model/graph -> invoke
native tool -> client.run_job -> NorFab worker task
```

### One constructor and one invocation method

Change the existing constructor to accept:

```python
NFAgent(client, config, profile="default", event=None)
```

`config` is the agent definition dictionary, copied on entry. `profile` remains
an instance label for existing profile-specific storage. `event` is an optional
callable supplied as `job.event` by the worker. It requires no wrapper function.
Core does not import `Job` or `Result`.

Keep all construction in the existing `__init__` and `_build` methods. Remove
inventory lookup and inheritance from `NFAgent`; do not retain a fallback
constructor accepting the old client/profile-only form.

Extend existing `invoke` directly:

```python
invoke(message, thread_id=None, verbose_result=False)
```

It calls the graph once and returns the full invocation payload when verbose,
otherwise the final message text, including text extracted from content blocks. Keep `stream`, `reset` and `list_tools`.
Do not add `invoke_raw`, a response class or another graph invocation wrapper.

### Native tasks and specialized definitions

Use the existing `tools` mapping and switches for both entry points:

- `tools.norfab_services` defaults to `true`: discover running services and expose
  each available task as a schema-backed tool. Honor explicit agent exclusions.
- Named entries define custom tools using the current `description`,
  `input_schema` and `norfab` fields.
- Set `tools.norfab_services: false` when an agent should use only its named tools.
- Default filesystem tools to `false` for both entry points. They can still be
  enabled explicitly; native access to NorFab tasks does not require local files.

For example, the same definition body works as a client profile or a worker YAML:

```yaml
llm:
  provider: ollama
  model: qwen3:8b
system_prompt: |
  Check the requested interfaces and report findings with evidence.
tools:
  norfab_services: false
  inspect_interfaces:
    description: Read interface details from selected devices.
    input_schema:
      type: object
      properties:
        FB:
          type: string
      required: [FB]
    norfab:
      service: nornir
      task: cli
      kwargs:
        commands: show interfaces
```

Omitting `tools.norfab_services: false` adds discovered task tools alongside the
named tools. Retain existing generated names and task schemas; reject duplicate
tool names directly where the final tool list is assembled. Discovery is a
snapshot at construction, limited to reachable services and tasks permitted by
agent metadata. Do not add refresh machinery or MCP as a dependency for native
NorFab tool access.

In `_make_norfab_tools`, collect task definitions in the inline format and call
`make_agent_inline_tools` once. Remove its duplicate schema/tool creation block,
unused `_make_service_tool` and commented-out implementation. Keep and reuse the
existing dispatch closure; pass JSON schemas directly to `StructuredTool` and
remove dynamic Pydantic generation and the `RunnableLambda` wrapper. Worker task
models validate dispatched arguments; custom schemas describe the tool to the
model and are not an additional access-control boundary. Add no replacement helpers.

Inside existing `make_runnable`, retain fixed service/kwargs precedence and
`job_data` extraction, using fresh dictionaries for every call. Pass the optional
`event` through the existing tool builders and call it directly for start,
completion and failure. Use lowercase messages and `severity`. Each worker call
has its own closures, so callbacks cannot cross job boundaries.

### Client changes

In existing `NFPClient.get_agent`, load the requested profile, local YAML and
existing default inheritance directly before constructing and caching
`NFAgent(self, config, profile=profile)`. Move the current loading code; do not
add a profile resolver function or retain inventory access inside core agent.
Load YAML with a direct `open`/`safe_load`; remove the silent-fallback file helper.

Keep client profile caching and thread handling. These already support chat and
require no new session or persistence mechanism.

### Worker changes

Keep worker task transport and management tasks. In existing `AgentWorker.invoke`:

1. For `name="NorFab"`, form `config` from worker `default_llm`. Core supplies its
   default prompt and discovered tools.
2. Otherwise fetch the YAML through existing worker file fetching and parse it
   directly. Use definition `llm` or worker `default_llm` if omitted/empty. Pass
   the remaining definition fields directly to core, including its prompt/tools.
3. Construct `NFAgent(self.client, config, event=job.event)` for this invocation.
4. Call `invoke(instructions, verbose_result=verbose_result)` and wrap its return
   value in the existing `Result`.

Do this inside `invoke`; remove worker `get_agent`, `get_llm`, `make_tools`,
`make_pydantic_model`, `make_runnable`, `self.llms` and direct LangChain imports.
Delete `norfab_agent.py`, whose two discovery-only tools are replaced by actual
native task tools. A YAML `name` can label the graph but need not be required.

Do not create a worker agent cache. A fresh agent uses the same in-memory core
behavior and starts a new conversation automatically. Existing task arguments
can stay where useful, but there are no compatibility shims or legacy modes.

## Implementation plan

1. **Make core directly reusable.** Change the constructor, move client profile
   loading, add the verbose branch to existing `invoke`, and fix dictionary
   mutation in place. Reuse `_make_llm`; delete the worker model cache when the
   worker switches. Keep existing methods rather than extracting new helpers.
2. **Unify task tools.** Route discovery through the existing inline builder,
   handle excluded task metadata, forward the optional job event callable, and
   set filesystem default to false. Verify a discovered tool actually dispatches
   to a task and returns its result to the model.
3. **Replace worker execution.** Load the config and call `NFAgent` directly in
   worker `invoke`. Delete duplicate methods, obsolete definitions and imports.
   Correct extras and optional imports so a basic worker does not require RAG/MCP.
4. **Verify and document.** Run focused client and worker integration tests,
   repository checks and docs build. Update client/worker examples, docstrings and
   changelog to describe the shared definition and native worker tools. Do not
   describe the implementation as shipped before it is verified.

Acceptance checks should cover:

- Client chat and worker default invocation both let a deterministic model select
  a discovered task, provide schema-valid arguments and receive its real result.
- The same specialized definition works through both entry points, including
  fixed arguments, repeated `job_data` calls and discovery disabled.
- Source inventory and YAML-derived dictionaries remain unchanged after building
  and calling agents. Agent-excluded tasks are absent from discovered tools.
- Client conversation continues and resets; separate worker calls retain no
  history and concurrent jobs receive only their own tool events.
- Verbose results and task failures travel through the single invocation path.
- Basic client/worker imports work with their respective extras and disabled
  optional features do not require their packages.

Prefer integration through the public client, following the
[testing guide](../testing/norfab_testing_framework.md) and
`AGENTS.md`. Extend the current client test and add focused
worker tests. Use local task fixtures; no Netbox data is needed.

## Scope and trade-offs

This deliberately changes the default worker from task-description tools to
native execution tools. Custom definitions and default chat use the same core
configuration and execution. The price of per-call worker isolation is rebuilding
its graph and discovering tasks on each invocation; do not optimize this with
caches in this change.

Leave existing optional MCP, RAG and SQLite features in place without expanding
or redesigning them. Their broader resource lifecycle issues, filesystem
hardening, routing redesign, remote streaming and persistent worker sessions are
separate work. The initial consolidation deferred lifecycle management; client
conversation persistence now adds connection cleanup as described below. It does
not introduce a new memory policy or configuration framework.

The [Hermes proposal](adr_hermes_agent_runtime_and_autonomous_network_operations.md)
remains separate. Its instruction to keep client and worker implementations
separate is superseded by this shared backend decision.


## MVP verification and deferred cases

Twelve deterministic tests in `tests/core/test_agent.py` exercise client/worker
entry points, native/custom tools, repeated fixed `job_data`, verbose payloads,
client history/reset and separate worker job events. Two of these start a local
broker and File Sharing worker and execute a real task through `NFPClient`.
The model is scripted; no external model service is required.

Discovery consumes the worker's `inputSchema` metadata and removes injected
`job` arguments. The client cache is instance-owned. Direct JSON schemas avoid
generating models that inject null defaults or assume a root class name.
Explicit nulls and omitted arguments pass unchanged to the task. A task argument
named `service` is preserved when the tool has a fixed dispatch service. Missing
local definition files raise instead of falling back to a default agent.

Deferred cases: discovery refresh/name collisions after normalization,
concurrent writes to the same client thread, and remote streaming.
Worker job isolation is checked with
sequential calls; concurrent worker stress testing and clean extra-only installs
remain unverified. RAG lifecycle and filesystem limitations remain. Client SQLite
checkpoints now use an owned connection, closed when the cached agent or client
is closed. Worker invocations still create fresh conversations.
MCP adapters supply coroutine-only tools that cannot execute through the current
synchronous graph invocation; user guides do not advertise this as working chat
functionality. Async invocation requires a separate change.
Agent invocation tasks can themselves be discovered; recursive agent dispatch
has no additional guard in this MVP.

Documentation builds successfully. Repository-wide checks report existing
formatting, annotation and dead-code findings; changed agent files and tests are
checked separately. No external model-provider smoke test was run.

## Client conversation persistence

Client profiles can opt into SQLite through the existing memory settings.
`NFAgent` owns its SQLite connection; client destruction closes cached agents.
The existing per-client/per-profile database path keeps histories separate.
`list_conversations` deduplicates root checkpoints and returns recent thread IDs,
timestamps and opening messages. `resume` selects a saved thread without invoking
the model. Reset still starts a new thread without deleting old history.

Client chat uses Picle's standard `chat_shell` and `chat_commands_model`
configuration with a message callback. The chat model selects its agent and
initial thread once in Picle's `chat_on_enter` hook, before slash commands or
messages. `chat_on_exit` clears the active context without closing the cached
agent. This requires the enhanced Picle version with chat lifecycle hooks.
The validator and repeated agent selection in the message handler are removed.
Picle owns chat execution and shell state; NorFab does not
call app methods or manipulate the shell stack. Resume updates the agent's active
thread, so an original `thread-id` chat argument cannot override it.

Tests cover reopening the SQLite store, profile isolation, connection cleanup,
resume before the first chat message, default and selected profiles, unknown IDs,
and returning from chat via `/exit` or EOF. History listing scans saved
checkpoints; pagination/indexing and same-thread concurrent calls remain outside
this MVP.

`/rename <thread-id>` moves the active conversation's latest state to an unused
ID through graph `update_state`, then deletes the old thread through the saver
API. Both SQLite and in-memory savers use the same path. Earlier checkpoint
snapshots are not copied. Rename is for idle conversations; concurrent calls and
atomic recovery across the copy/delete operations remain outside this MVP.

## Progress reporting

One core LangChain callback reports model rounds and tool start, completion and
errors. Both entry points pass `AgentProgress` through invocation `callbacks`:
workers supply `job.event` as its receiver and local chat supplies a receiver
using Picle's `ChatSession.set_status` and `write`. Picle owns the persistent
editor and spinner; there is no separate Rich live display. The named `chat`
argument is injected into the message handler only. Its footer shows the profile
and thread at each message, so slash-command changes appear on the next message.
The core passes callbacks directly to the graph and has no separate event path.
Tool wrappers no longer emit duplicate events.
The callback covers native, filesystem and retrieval tools through the same
graph interface. Local chat defaults to progress enabled and supports
`progress false`; Python invocation stays quiet unless a callback is supplied.
Status describes activity rather than exposing model reasoning or tool payloads.
Completion means the tool returned; inspect the result for task-level failures.
