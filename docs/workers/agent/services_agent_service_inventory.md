# Agent Worker Inventory

The `agent` service runs on a worker. For local chat, see [Client Agent](../../clients/clients_agent.md).

## Worker configuration

```yaml title="inventory.yaml"
workers:
  agent-worker-1:
    - agents/common.yaml
topology:
  workers:
    - agent-worker-1
```

```yaml title="agents/common.yaml"
service: agent
default_llm:
  provider: ollama
  model: qwen3:8b
  base_url: http://127.0.0.1:11434
  temperature: 0.0
```

`default_llm` is required for the built-in `NorFab` agent and custom definitions
without a nonempty `llm` mapping. Supported providers are **ollama** and **groq**.
Set `model` and `provider`; other keys are passed to the provider's LangChain
constructor, for example `base_url`, `temperature`, or `api_key`.
Groq requires `langchain-groq` to be installed separately.

The old `llm_flavour`, `llm_model`, `llm_temperature` and `llm_base_url` settings
are not read. Worker inventory does not define named agent profiles.

## Custom agent definitions

Invoke `name: NorFab` to use the built-in agent, whose tools list available tasks
and retrieve task descriptions. To run custom tools, pass an `nf://` or `git://`
YAML file URL as `name`. Bare custom names and local paths are not supported.

```yaml title="agents/interface_check.yaml"
name: Interface Check
system_prompt: |
  Retrieve interface information for the requested devices.
  Report errors and operational state with supporting evidence.
tools:
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

Use commands appropriate to your devices.

| Key | Meaning |
| --- | --- |
| `name` | Required agent display name. |
| `system_prompt` | Required operating instructions. |
| `llm` | Optional complete model configuration; a nonempty mapping replaces `default_llm`, without merging. |
| `tools` | Mapping of tool names to definitions; defaults to no tools. |

### Tool definitions

The client agent supports the same inline tool format.

| Key | Meaning |
| --- | --- |
| `description` | Required description shown to the model. |
| `input_schema` | Optional JSON Schema object with `properties`, `required`, etc. Omit for an argument-free tool. |
| `norfab.task` | Required NorFab task name. |
| `norfab.service` | Fixed service name. If omitted, the model must supply a `service` argument. A fixed service takes precedence. |
| `norfab.kwargs` | Fixed task arguments; override model-supplied values with the same names. |
| `norfab.job_data` | List of model argument names to move into the task's `job_data` mapping, for example template variables. |

Tool calls use the client's default worker selection. There is no tool-level
worker-routing setting; `workers` in `norfab.kwargs` is passed as a task argument.

## Run the agent

=== "CLI"

    ```bash
    nf# agent invoke name nf://agents/interface_check.yaml instructions "Check interfaces on r1"
    ```

=== "Python"

    ```python
    result = client.run_job(
        service="agent", task="invoke", workers="any",
        kwargs={
            "name": "nf://agents/interface_check.yaml",
            "instructions": "Check interfaces on r1",
        },
    )
    ```

Each invocation starts a fresh conversation. Worker definitions do not support
client-agent `memory`, `rag`, `mcp`, `from_yaml_file`, or tool-discovery switches.
See [Invoke](services_agent_service_tasks_chat.md) for results and usage.
