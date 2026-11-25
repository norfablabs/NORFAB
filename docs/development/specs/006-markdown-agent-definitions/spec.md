# Feature Specification: Markdown Agent Definitions

**Feature Branch** `master` (specification prepared on the current branch)  
**Created** 2026-11-24  
**Status** Draft  
**Acceptance** Pending maintainer review  
**Implementation** Planned  
**Input** Define NorFab agents in Markdown and convert them to the existing YAML definition format using the Markdown parser library used by Netbox designs.

## User Scenarios & Testing

### User Story 1 - Author And Run A Markdown Agent (Priority: P1)

A network operator writes a readable interface health runbook with the agent's instructions and tool settings in the same document.

**Why this priority**. Operators can review the procedure and the actions available to the agent together.

**Independent Test**. Load a Markdown equivalent of the existing interface health definition through a worker and compare its effective configuration and tool behavior with the YAML definition.

**Acceptance Scenarios**

1. **Given** equivalent Markdown and YAML files, **when** an operator invokes each through the existing worker interface, **then** both use the same prompt, model selection, tool names, argument schemas, fixed arguments, and job data routing.
2. **Given** a client profile referencing the Markdown file, **when** a user opens that profile, **then** it uses the same configuration and profile defaults as the equivalent file-backed YAML profile.

### User Story 2 - Keep Documentation And Settings Together (Priority: P2)

An author puts agent settings at the top of the file, writes instructions in Markdown, and configures the model and tools under their own headings.

**Why this priority**. Authors can review the prompt as rendered Markdown and edit the model and tool settings in one place.

**Independent Test**. Load a document with YAML frontmatter and a prompt containing a horizontal rule and a fenced example, followed by an LLM section and a Tools section with two tool definitions.

**Acceptance Scenarios**

1. **Given** YAML frontmatter followed by Markdown instructions, **when** NorFab loads the document, **then** the frontmatter supplies agent settings, the System Prompt section supplies the prompt, the LLM section supplies the model settings, and each tool subsection defines one tool that the frontmatter can select.
2. **Given** malformed frontmatter, duplicate tool names, or a prompt supplied in both locations, **when** either loader opens the document, **then** it reports the source and offending section or field before building an agent.

### Edge Cases

- A document without opening and closing frontmatter delimiters fails. Use `{}` when the agent needs only a prompt.
- An unindented `---` on its own line closes the frontmatter. Horizontal rules and code fences before the first configuration section are part of the prompt.
- A blank or whitespace-only System Prompt section supplies no prompt. An explicit `system_prompt: ""` in frontmatter supplies an empty prompt.
- YAML literal blocks preserve command text and template expressions for the task that already handles them.

## Requirements

### Functional Requirements

- **FR-001**. The agent worker MUST accept `.md` and `.markdown` files at the existing `nf://` and `git://` definition URLs through the `name` argument.
- **FR-002**. Client inventory MUST support `from_markdown_file` for local agent profiles, with the same path resolution, default-profile merge and caching behavior as `from_yaml_file`. A profile that declares both file settings MUST fail with a clear error.
- **FR-003**. A Markdown file MUST describe a single agent. Its first line MUST be `---`. The next unindented line containing only `---` closes the YAML frontmatter. The frontmatter MUST contain a single mapping of existing agent settings, which may be empty (`{}`). An optional string `description` summarizes the role for readers.
- **FR-004**. An optional top-level `# System Prompt` section MUST be the first section after frontmatter. Its Markdown content ends at the first top-level `# LLM`, `# Guardrails`, `# Skills`, or `# Tools` section, or at the end of the file. Preserve the content as `system_prompt`, including headings, blank lines, and fenced examples. The heading itself is excluded. Reject duplicate System Prompt sections and non-whitespace text outside a recognized section. The frontmatter MAY supply `system_prompt` when the section is absent or blank. When neither supplies a prompt, existing defaults apply.
- **FR-005**. The resulting definition MUST be usable as ordinary agent YAML and follow the same defaults and execution behavior as an equivalent YAML file on the same surface. NorFab MUST convert in memory and MUST preserve nested configuration values, including tool schemas and literal task templates. Tool selection in Markdown MUST be applied to the effective tool set, including tools introduced by defaults.
- **FR-006**. Missing delimiters, malformed YAML, a non-mapping frontmatter value, duplicate YAML keys, unknown top-level fields, a non-string `description`, invalid or unresolved tool names, a malformed LLM, Guardrails, Skills, or Tools section, duplicate LLM settings, duplicate tool names, and a prompt supplied in both locations MUST produce an error identifying the source and the section or field where applicable before model or tool initialization.
- **FR-007**. Existing YAML files, inline profiles, public task arguments, and the built-in `NorFab` agent MUST remain compatible.
- **FR-008**. Authoring documentation MUST show the Markdown syntax and how to reference a file from both the client and worker.

- **FR-009**. An optional top-level ATX heading written as `# Tools` MUST start the final section. Each tool MUST begin with a top-level `## <tool_name>` heading. The nonempty Markdown text following the heading and preceding the first definition fence MUST supply `description`, with surrounding whitespace trimmed. Each tool MUST have exactly one `yaml norfab` fence containing the call mapping and MAY have one preceding `yaml input_schema` fence containing the argument schema. The fence labels supply the mapping keys. NorFab MUST use the heading text as the tool name and reject duplicate or reserved names, empty sections, missing descriptions or calls, duplicate or unrecognized fences, and invalid mappings.
- **FR-010**. Frontmatter `tools` MAY contain a comma-separated string of exact tool names or a YAML list of those names. An explicit list MUST expose only the named tools, resolving each name against the Tools section or tools available through NorFab on the selected surface. Trim whitespace around comma-separated names. Reject empty entries, duplicate names, unknown names and ambiguous matches before invocation. An explicit empty YAML list selects no tools. When omitted, existing discovery defaults apply and all tools defined in the Tools section are available. Tool mappings in frontmatter MUST be rejected. A `# Tools` line inside a fence or quotation MUST remain prompt text. A second top-level `# Tools` or another level-one heading after it MUST produce a source-specific error.

- **FR-011**. An optional top-level `# LLM` section MUST appear after the prompt and before `# Guardrails`, `# Skills`, and `# Tools`, when present. It MUST contain exactly one top-level `yaml` fence with a nonempty mapping of existing `llm` settings. NorFab MUST use that mapping as `llm` with the same model selection and default behavior as an equivalent YAML definition. A model may also be configured with frontmatter `llm` when the section is absent. Authors MAY add explanatory prose alongside the fence. Only the fence supplies model settings. Reject duplicate sections, model settings in both places, and missing or extra fences. A `# LLM` line inside a fence or quotation remains prompt text.

- **FR-012**. An optional top-level `# Guardrails` section MUST follow the prompt and `# LLM` if present, and precede `# Skills` and `# Tools` if present. It MUST contain exactly one top-level `yaml` fence mapping one or more supported guardrail names to positive integers. Authors MAY add explanatory prose alongside the fence. Only the fence supplies guardrail settings. Normalize this mapping to `guardrails` in the agent definition. An equivalent YAML definition MAY use the same `guardrails` mapping. Reject duplicate sections or keys, unknown guardrail names, invalid values, and a Markdown definition that supplies guardrails in both places.
- **FR-013**. `max_input_chars` MUST reject a request whose submitted text exceeds the limit before a model or tool call. `max_tool_calls` MUST cap individual tool calls dispatched for that request, including parallel calls and retries. Reject an entire batch that would exceed the remaining budget before dispatching any call in that batch. `max_output_chars` MUST reject a final answer that exceeds the limit before the caller receives it, including when using streaming. Each limit applies independently per request. Omitted limits add no restriction. Report a violation through the existing client or worker error path and identify the guardrail that fired. Completed tool calls may already have effects when a later guardrail fires.

- **FR-014**. An optional top-level `# Skills` section MUST follow the prompt, LLM, and Guardrails sections that are present and precede Tools. It MUST contain exactly one top-level `yaml` fence with a mapping from skill names to `nf://` URLs for `SKILL.md` files published by the NorFab File Sharing service. Optional prose may explain the selection. Resolve these URLs through File Sharing on both the client and worker, regardless of where the agent definition is loaded from. An equivalent standalone YAML definition MAY use a top-level `skills` mapping. Reject a duplicate Skills section, simultaneous Markdown frontmatter and section declarations, invalid references, duplicate mapping keys, and a key that differs from the referenced skill's declared name.
- **FR-015**. NorFab MUST make the declared skills' names and descriptions available to the agent and provide their Markdown instructions when the agent selects a declared skill. A missing skill or invalid skill metadata MUST identify the reference in an error before it is offered to the agent. Selecting a skill supplies instructions only. It MUST preserve the selected tool set and guardrails. Commands and other resources referenced by a skill remain subject to the agent's existing capabilities.

### Key Entities

- **Markdown Agent Definition**. One document with YAML frontmatter, an optional Markdown prompt, and optional LLM, Guardrails, Skills, and Tools sections.
- **Agent Configuration**. The existing mapping of name, prompt, model, tools, MCP, retrieval and memory settings. An option has the same effect it has in YAML on the same surface.
- **Skill**. A reusable procedure published as a referenced `SKILL.md` file with a name, description, and Markdown instructions.
- **Tool Binding**. A named tool with a description, optional input schema, target service and task, fixed arguments, and optional routing of inputs into job data.

### Markdown Definition Format

The frontmatter sets the name, optional description, and names of tools the agent can use. Write the prompt under `# System Prompt`, then add model settings under `# LLM`, invocation limits under `# Guardrails`, reusable procedures under `# Skills`, and custom tools under `# Tools`. Each heading supplies the tool name and the prose below it supplies the description. Use a `yaml input_schema` fence for arguments the model can supply and a `yaml norfab` fence for the task binding. Omit the input schema for a tool that takes no model-supplied arguments.

````markdown
---
name: interface-health
description: Review network interfaces for link and error issues.
tools: inspect_interfaces, list_devices
---

# System Prompt

Check link state and error counters for the requested devices. Include the evidence for each finding.

# Settings

Run the interface review with Qwen3 4B on the local Ollama server.

```yaml
llm:
  provider: ollama
  model: qwen3:4b
  base_url: http://127.0.0.1:11434
```

# Guardrails

Limit each review to a 4,000-character request, five tool calls, and an 8,000-character answer.

```yaml
max_input_chars: 4000
max_tool_calls: 5
max_output_chars: 8000
```

# Skills

Use the interface review procedure when evaluating link state and counters.

```yaml
interface-review: nf://skills/interface-review/SKILL.md
```

# Tools

## inspect_interfaces

Read interface counters and state from matching devices.

```yaml input_schema
type: object
properties:
  FB:
    type: string
    description: Device name glob.
required: [FB]
```

```yaml norfab
service: nornir
task: cli
kwargs:
  commands: show interfaces
```

## list_devices

List available network devices.

```yaml norfab
service: nornir
task: get_nornir_hosts
```
````

## Success Criteria

### Measurable Outcomes

- **SC-001**. An interface health definition runs through both supported entry points with the same effective settings and task arguments as its existing equivalent.
- **SC-002**. A definition with a horizontal rule and a fenced YAML example in the prompt, an LLM section, and two tool subsections produces exactly the frontmatter settings, the full content of the System Prompt section, the model settings from the LLM section, and exactly the two tools named in the frontmatter, with descriptions from prose, schemas from input fences where supplied, and calls from NorFab fences.
- **SC-003**. All malformed-definition cases in FR-006 report the source before execution.
- **SC-004**. Existing agent definition and profile checks continue to pass.

- **SC-005**. On both entry points, an oversized request makes zero model or tool calls, an over-budget batch dispatches zero additional calls, and an oversized answer reaches the caller only as a guardrail error.

- **SC-006**. An agent with a declared skill can see its name and description, load its instructions when selected, and retains the same tool selection and guardrails afterward.

## Assumptions

- The change covers definition authoring, loading, declared skill use, and enforcement of the declared invocation limits. Existing authentication, conversation lifecycle, and result formats determine the remaining runtime behavior.
- NorFab MUST reuse `markdown-it-py`, the library used by the [Netbox design parser](../../adr/adr_netbox_design_markdown_parser.md). Use the Markdown parser to recognize configuration headings and YAML fences. Preserve the original prompt source and parse tool fence contents as YAML.
- Existing model and service configuration is available to run the interface health example. This feature adds no export command or orchestration DSL.
