# Agent Worker Inventory

Configure the model used by an agent worker, then optionally define a focused
agent for a repeated check. For chat in your local process, see
[Client Agent](../../clients/clients_agent.md).

## Worker configuration

Add the worker to your existing `inventory.yaml`:

```yaml title="inventory.yaml"
workers:
  agent-worker-1:
    - agents/common.yaml
topology:
  workers:
    - agent-worker-1
```

Choose a model that supports tool calls:

=== "Ollama"

    Run the model on an Ollama server reachable from the worker.

    ```yaml title="agents/common.yaml"
    service: agent
    default_llm:
      provider: ollama
      model: qwen3:8b
      base_url: http://127.0.0.1:11434
      temperature: 0.0
    ```

=== "OpenAI"

    Install `langchain-openai` on the worker host and set `OPENAI_API_KEY` in
    the worker's environment.

    ```yaml title="agents/common.yaml"
    service: agent
    default_llm:
      provider: openai
      model: gpt-4.1-mini
      temperature: 0.0
    ```

`default_llm` supplies the model for the default `NorFab` agent and custom
agents that omit `llm`. See the
[provider list](../../clients/clients_agent.md#profile-settings) for other options.

## Custom agent definitions

Save the following file where your File Sharing service publishes
`nf://agents/interface_check.yaml`. It gives the agent one tool for reading
interface state, with the command fixed in the definition. Adjust the command
for your device platform.

```yaml title="agents/interface_check.yaml"
name: Interface Check
system_prompt: |
  Check interfaces on the requested devices.
  Report down interfaces and error counters with supporting evidence.
  State which checks could not be completed.
tools:
  norfab_services: false
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

Run the same check whenever needed:

=== "CLI"

    ```bash
    nf# agent invoke workers agent-worker-1 name nf://agents/interface_check.yaml instructions "Check interfaces on r1 and r2. Summarize problems by device."
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()
        results = client.run_job(
            service="agent",
            task="invoke",
            workers="agent-worker-1",
            kwargs={
                "name": "nf://agents/interface_check.yaml",
                "instructions": (
                    "Check interfaces on r1 and r2. Summarize problems by device."
                ),
            },
        )
        for worker, response in results.items():
            print(worker, response["result"])
    ```

The `name` task argument accepts `NorFab` or an `nf://` or `git://` definition URL.
Each invocation starts fresh; include device scope and relevant context every time.

| Definition field | Use |
| --- | --- |
| `name` | Optional display name. |
| `system_prompt` | Instructions used on every request. Omit to use the default network automation prompt. |
| `llm` | Optional model settings for this agent. A nonempty mapping replaces `default_llm` completely. |
| `tools.norfab_services` | Defaults to `true`. Set `false` to use only the named tools in your definition. |
| Other `tools` entries | Named tools, as in the example above. |

### Tool definitions

Client profiles and worker definitions use the same tool format.

| Field | Use |
| --- | --- |
| `description` | Explain when the model should use the tool. |
| `input_schema` | JSON Schema describing the arguments the model can supply. Omit for a tool with no arguments. |
| `norfab.service` | Service to call. If omitted, include a `service` argument in the tool schema. |
| `norfab.task` | Task to execute. |
| `norfab.kwargs` | Fixed task arguments. These override model-supplied values with the same names. |
| `norfab.job_data` | Names of model arguments to pass inside task `job_data`, for example template variables. |

Native discovery adds the tasks available when the agent starts, except tasks
excluded from agents. To add discovered tasks alongside custom tools, omit
`norfab_services: false`. Filesystem tools require explicit `tools.filesystem: true`.
Tool calls use the client's default worker selection; device filters such as `FB`
belong in task arguments.
