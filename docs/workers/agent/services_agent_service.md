---
tags:
  - agent
---

# Agent Service

Run an LLM agent on a NorFab worker and submit instructions through NFCLI or
the Python job API. Agents use configured NorFab tasks as tools and return a
final response. Each invocation starts a fresh conversation.

```bash
pip install "norfab[agentservice]"
```

The worker supports Ollama and Groq. For Ollama, run an Ollama server and install
the selected model. For Groq, also install `langchain-groq` and configure credentials.

- [Inventory and custom agent definitions](services_agent_service_inventory.md)
- [Invoke an agent](services_agent_service_tasks_chat.md)
- [Local client agent](../../clients/clients_agent.md), for profile-based chat in NFCLI or Python

The built-in `NorFab` agent discovers services and task descriptions. Custom
definitions supply the tools needed to perform network operations.
