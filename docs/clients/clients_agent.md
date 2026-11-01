# Client Agent

Use the client agent for an ongoing conversation about your network. Ask it to
collect device state, explain task results and follow up on earlier findings.
It runs in your Python or NFCLI process and calls available NorFab services;
an Agent service worker is not required.

## Configure a model

```bash
pip install "norfab[clientagent,nfcli]"
```

Choose a model that supports tool calls. For the example below, run the model on
an Ollama server reachable from your client. Add this to your existing inventory:

```yaml title="inventory.yaml"
client:
  agent_profiles:
    default:
      llm:
        provider: ollama
        model: qwen3:8b
        base_url: http://127.0.0.1:11434
        temperature: 0.0
      system_prompt: |
        Investigate network state using the available tools.
        Support findings with evidence and state what could not be checked.
```

The agent can use tasks from running services. Interface examples need a Nornir
service with the named devices in its inventory; inventory questions need the
corresponding inventory service.

## Investigate and follow up

=== "CLI"

    Start chat:

    ```bash
    nf# client-agent chat
    ```

    Then enter these messages in the chat prompt:

    ```text
    Check interfaces on r1. Report down interfaces and error counters with evidence.
    Which of those findings should I investigate first, and why?
    ```

    The multiline editor stays visible while the agent runs. A `thinking...`
    spinner and tool progress appear above it; the footer shows the profile and
    thread used for the latest message. To hide progress:

    ```bash
    nf# client-agent chat progress false
    ```

    Press Alt+Enter to insert a newline and Enter to send. You can compose the
    next message while waiting, but cannot send it until the current response
    finishes. Ctrl+C and Ctrl+D do not cancel a running request.

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        client = nf.make_client()
        agent = client.get_agent()
        print(agent.invoke(
            "Check interfaces on r1. Report down interfaces and error counters "
            "with evidence."
        ))
        print(agent.invoke(
            "Which of those findings should I investigate first, and why?"
        ))
    ```

Responses are text. Include exact device names, expected state and the evidence
you need. To verify a change, describe the expected outcome and ask the agent to
report pass/fail results and checks it could not complete.

Progress describes activity, without showing model reasoning or full tool inputs
and outputs. Python calls remain quiet by default.

By default, conversation history lasts for the current client session. Follow-up
questions use the same conversation unless you select another thread. Enable
persistent history below to keep conversations after restarting the client.

## Keep investigations separate

Use a thread name for each investigation so a follow-up stays with its context.

=== "CLI"

    ```bash
    nf# client-agent chat thread-id branch-a
    ```

    Start another chat with `thread-id branch-b` for a separate investigation.

=== "Python"

    ```python
    print(agent.invoke("Check interfaces on r1", thread_id="branch-a"))
    print(agent.invoke("Check interfaces on r2", thread_id="branch-b"))
    print(agent.invoke("Summarize the remaining issues", thread_id="branch-a"))
    ```

Use the `agent` created in the previous example. `agent.reset()` starts a fresh
conversation for calls without an explicit `thread_id`; named threads keep their
own context.

## Save and resume conversations

Add these settings to a client agent profile to save its conversations locally:

```yaml title="inventory.yaml"
client:
  agent_profiles:
    default:
      llm:
        provider: ollama
        model: qwen3:8b
        base_url: http://127.0.0.1:11434
      memory:
        enabled: true
        backend: sqlite
```

=== "CLI"

    Start an investigation with a memorable thread name:

    ```bash
    nf# client-agent chat thread-id branch-a
    > Check interfaces on r1 and summarize the findings.
    > /exit
    ```

    After restarting NFCLI, open chat and resume it:

    ```bash
    nf# client-agent chat
    > /resume
    > /resume branch-a
    > Which findings should I investigate first?
    ```

    `/resume` lists up to 20 recent conversations with their IDs, last update
    times and opening questions. Copy an ID into `/resume <thread-id>` to
    continue it. Use `agent-name` when opening chat to resume another profile.
    Press Tab after `/resume ` to complete saved thread IDs for the active profile.

    Give the current conversation a memorable ID after sending a message:

    ```text
    > /rename branch-a-interfaces
    ```

    Later, use `/resume branch-a-interfaces`. The previous ID is replaced;
    an existing conversation's ID cannot be reused.

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="./inventory.yaml") as nf:
        agent = nf.client.get_agent()
        print(agent.invoke("Check interfaces on r1", thread_id="branch-a"))

    # In a later run, use the same inventory, client name and profile.
    with NorFab(inventory="./inventory.yaml") as nf:
        agent = nf.client.get_agent()
        print(agent.list_conversations())
        agent.resume("branch-a")
        print(agent.invoke("Which findings should I investigate first?"))
    ```

    To rename the current conversation in Python:

    ```python
    agent.rename("branch-a-interfaces")
    ```

History is separate for each client name and agent profile. Reopen NFCLI from
its usual working directory with the same inventory to find its saved history.
Python clients should reuse the same client name when resuming saved work.
Starting a new conversation does not delete older ones. Without SQLite enabled,
`/resume` can only find conversations from the current client session.
Renaming keeps the current messages, but does not retain older checkpoint
snapshots. SQLite must be enabled to keep the renamed conversation after restart.

## Use a focused agent

For a repeatable check, put the operating instructions and tools in a definition
file. This example offers a single tool with a fixed command; adjust the command
for your device platform.

```yaml title="agents/interfaces_check.yaml"
system_prompt: |
  Check interface health on the requested devices.
  Report problems with evidence and state which checks could not be completed.
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

Add a profile pointing to this local file:

```yaml title="inventory.yaml"
client:
  agent_profiles:
    default:
      llm:
        provider: ollama
        model: qwen3:8b
        base_url: http://127.0.0.1:11434
    interfaces_check_agent:
      from_yaml_file: ./agents/interfaces_check.yaml
```

The profile uses the default model. A local definition path is relative to the
working directory where you start NorFab; its file contains the prompt and tools
directly. See the [tool reference](../workers/agent/services_agent_service_inventory.md#tool-definitions)
for fixed arguments and template `job_data`.

=== "CLI"

    ```bash
    nf# client-agent chat agent-name interfaces_check_agent
    ```

    Ask: `Check interfaces on r1 and r2. Summarize problems by device.`

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    nf = NorFab(inventory="./inventory.yaml")
    try:
        nf.start()
        client = nf.make_client()
        agent = client.get_agent(profile="interfaces_check_agent")
        print(agent.invoke(
            "Check interfaces on r1 and r2. Summarize problems by device."
        ))
        print(agent.list_tools())
    finally:
        nf.destroy()
    ```

Recreate the client after editing profiles or changing which tasks are available.

## Profile settings

| Setting | Use |
| --- | --- |
| `llm.provider` | Provider from the table below. Defaults to `openai`. |
| `llm.model` | Name of a model with tool-call support. |
| `llm.api_key` | Optional API credential; omit to use the provider's environment settings. |
| `llm.base_url` | Provider endpoint; OpenRouter defaults to `https://openrouter.ai/api/v1`. |
| `llm.temperature` | Optional sampling setting. |
| `system_prompt` | Instructions for every request; replaces the default network automation prompt. |
| `tools.norfab_services` | Defaults to `true`; discovers available tasks. Set `false` to use only your named tools. |
| `tools.filesystem` | Defaults to `false`; enable explicitly to read, write, edit and list local files. |
| `memory` | Set `{enabled: true, backend: sqlite}` to save conversations across restarts. Otherwise history stays in memory. |

Other `llm` keys are passed to the selected provider. Profiles inherit settings
from `default`; values in the selected profile override matching defaults.

| Provider | Package |
| --- | --- |
| `openai`, `openrouter` | `langchain-openai` |
| `anthropic` | `langchain-anthropic` |
| `ollama` | `langchain-ollama` |
| `groq` | `langchain-groq` |
| `mistral` | `langchain-mistralai` |
| `google` | `langchain-google-genai` |
| `bedrock` | `langchain-aws` |

The client extra includes OpenAI, Anthropic and Ollama providers. Install the
corresponding package for other providers and configure their credentials.

## Use local runbooks

Add a runbook directory to your profile when the agent should consult local
procedures as well as collect task results:

```yaml
rag:
  enabled: true
  sources: [./runbooks]
  top_k: 4
```

Use Markdown or other UTF-8 text files on the client machine. PDF and Word
files need conversion to text first. Ask the agent to consult the runbooks,
run the relevant checks and cite the retrieved evidence. After removing source
documents, stop the client process, remove
`<inventory directory>/__norfab__/rag/<profile>/` and restart it to rebuild the
knowledge store.

External MCP tool calls are currently unavailable in this chat interface.
Native NorFab tasks do not require MCP.

Use [Agent service](../workers/agent/services_agent_service.md) when the request
should run on a dedicated worker instead of in your client process.
