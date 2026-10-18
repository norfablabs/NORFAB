# Client Agent

The client agent runs in your Python or NFCLI process and calls NorFab services
through the client. It does not require an Agent service worker.

```bash
pip install "norfab[clientagent,agentservice,nfcli]"
```

This includes current agent construction dependencies and NFCLI. Install
additional provider packages as needed below.

## Inventory profiles

Define profiles under `client.agent_profiles` in `inventory.yaml`:

```yaml
client:
  agent_profiles:
    default:
      llm:
        provider: ollama
        model: qwen3:8b
        base_url: http://127.0.0.1:11434
        temperature: 0.0
      tools:
        norfab_services: true
        filesystem: false
      system_prompt: |
        You are a network assistant. Support findings with collected evidence.
    interfaces_check_agent:
      from_yaml_file: ./agents/interfaces_check.yaml
```

Profiles other than `default` inherit its settings: mappings merge recursively,
lists append unique entries, and scalar values override defaults. Keep shared
defaults inline under `default`.

`from_yaml_file` loads a local YAML profile relative to the process working
directory. The file contains profile fields directly, without a `client` or
`agent_profiles` wrapper. Its contents replace the referring profile's other
fields before inheritance. It is read as plain YAML without template rendering;
`nf://` and `git://` URLs are not supported here.

```yaml title="agents/interfaces_check.yaml"
system_prompt: |
  Check interface health on requested devices and report the evidence.
tools:
  norfab_services: false
  filesystem: false
  inspect_interfaces:
    description: Read interface details from selected devices.
    input_schema:
      type: object
      properties:
        FB:
          type: string
          description: Device name glob pattern.
      required: [FB]
    norfab:
      service: nornir
      task: cli
      kwargs:
        commands: show interfaces
```

Use commands appropriate to your devices. See the shared
[inline tool reference](workers/agent/services_agent_service_inventory.md#tool-definitions)
for fixed arguments and `job_data` handling.

## Profile settings

| Setting | Default and behavior |
| --- | --- |
| `llm.provider` | `openai`; supported providers listed below. |
| `llm.model` | Model identifier; choose a model that supports tool calls. |
| `llm.api_key` | Optional credential; omitted values use provider defaults/environment. |
| `llm.base_url` | Optional endpoint. OpenRouter defaults to `https://openrouter.ai/api/v1`. |
| `llm.temperature` | Optional sampling temperature; otherwise provider default. |
| `system_prompt` | Built-in network automation instructions. A supplied string replaces them. |
| `tools.norfab_services` | `true`: discover running service tasks, excluding tasks with `agent.enabled: false`. Discovery happens when the agent is created. |
| `tools.filesystem` | `true`: enable read, write, edit and directory-list tools rooted at the current working directory. Accepts a boolean or `{enabled: false}`; no custom root setting. |
| Other entries in `tools` | Named inline NorFab tool definitions. |
| `mcp` | External tools; disabled by default. |
| `rag` | Local document retrieval; disabled by default. |
| `memory` | Conversation checkpoint settings, described below. |

Only the listed `llm` fields are passed to the model; arbitrary provider options
are not forwarded.

| Provider | Python package |
| --- | --- |
| `openai`, `openrouter` | `langchain-openai` |
| `anthropic` | `langchain-anthropic` |
| `ollama` | `langchain-ollama` |
| `groq` | `langchain-groq` |
| `mistral` | `langchain-mistralai` |
| `google` | `langchain-google-genai` |
| `bedrock` | `langchain-aws` |

### MCP tools

```yaml
mcp:
  enabled: true
  servers:
    - name: network_tools
      transport: streamable-http
      url: http://localhost:8001/mcp/
```

Each server requires `name`. `transport` defaults to `stdio`, which uses
`command`, optional `args` (default `[]`), and optional `env`.
`sse` and `streamable-http` use `url`. Headers and other connection options are
not forwarded by the current client agent.

### Local document retrieval

```yaml
rag:
  enabled: true
  sources: [./runbooks]
  embed_model: sentence-transformers/all-MiniLM-L6-v2
  collection: norfab
  top_k: 4
```

`sources` accepts files and recursively scanned directories, read as UTF-8 text.
Relative paths use the process working directory; PDF/Word extraction is not
provided. Sources are indexed when the agent is created, in 800-character chunks
with 100-character overlap. `top_k` controls retrieved chunk count.

`persist_dir` defaults to `<inventory base>/__norfab__/rag/<profile>` and accepts
`{profile}`. A supplied relative directory uses the working directory. With no
sources, the agent searches the existing collection. Reindexing does not remove
obsolete chunks; rebuild the store when removing documents. Results include
source paths and matching text.

### Conversation memory

In-memory history is always enabled, including when `memory.enabled` is `false`
or omitted. Calls reuse the agent's thread unless you supply `thread_id`.
`reset()` starts a new default thread; it does not erase stored history or reset
an explicitly supplied thread ID.

The configuration recognizes `memory: {enabled: true, backend: sqlite}` and
selects `<inventory base>/__norfab__/files/client/<client name>/agent_<profile>.db`.
The current SQLite initialization requires a fix before persistent checkpoints
can be used; use in-memory history for now. Other backend values, including the
default `buffer`, select in-memory history.

## Use the agent

=== "CLI"

    ```bash
    nf# client-agent chat
    nf# client-agent chat agent-name interfaces_check_agent thread-id interface-review
    ```

    Enter natural-language messages in the chat shell. `agent-name` selects the
    inventory profile; `thread-id` selects a conversation.

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()
        agent = client.get_agent(profile="interfaces_check_agent")
        print(agent.invoke("Check interfaces on r1", thread_id="review"))
        print(agent.invoke("Summarize the errors", thread_id="review"))
        print(agent.list_tools(name="*interface*"))
    ```

`get_agent()` caches one agent per profile and builds its tools and model on
creation. Recreate the client to pick up profile or discovery changes.
`agent.stream(message, thread_id=...)` yields response chunks.

For jobs executed on a dedicated worker, use the separate
[Agent service inventory](workers/agent/services_agent_service_inventory.md).
