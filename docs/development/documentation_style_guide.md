# Documentation Style Guide

This guide defines lightweight conventions for NORFAB documentation. The goal is to keep pages consistent, easy to scan, and easy to maintain.

## Audience and purpose

Before writing, identify the primary audience: users or developers. Tailor wording, examples,
and detail to that audience. User guides MUST explain what the feature does, when/why to use it,
and how to use it. Omit implementation details unless essential to usage or a limitation.
Developer guides may explain architecture, interfaces, and maintenance decisions.

Overviews MUST describe the task and its purpose before examples. Keep device names, example
resources, and walkthrough instructions in Examples. Avoid test terminology such as "test-owned"
or "resources you own"; describe the actual device operation and its effects.

## Page types

Use the page type that matches the reader intent:

- **Overview**: what a component does, when to use it, key concepts.
- **How-to**: step-by-step for a specific goal (task-oriented).
- **Reference**: complete options/arguments, defaults, and output schema.
- **Troubleshooting**: common failure modes and fixes.

## Recommended page template

Each service task MUST have its own Markdown page. Use this order; omit optional sections
when they add no useful information:

1. **Purpose** (1–2 paragraphs)
2. **Output** (what the result looks like)
3. **Examples** (in tabbed format)
   - CLI example in the `=== "CLI"` tab
   - Python example in the `=== "Python"` tab
   - Python requests and curl examples in the `=== "FastAPI"` tab
   - A natural-language tool prompt in the `=== "MCP"` tab
4. **Notes / Gotchas** (timeouts, filters, permissions)
5. **Troubleshooting**
6. **Task Command Shell Reference** in tree format
7. **Python API Reference**

## Agent workflow for service task docs

When updating a service task page:

1. Read this guide, related task pages, the task implementation, input/output Pydantic models, and NFCLI/PICLE command model before editing. Reuse established presentation patterns.
2. Do not add an Inputs section. Document task arguments in the Google-style task docstring and expose them through the Python API Reference.
3. Add an Output section to every task page. If the exact output shape is unclear, write `TBD` and leave it for maintainer review.
4. Derive CLI examples from NFCLI aliases and command structure.
5. Derive Python examples from `client.run_job(...)` using the task API name and Python kwargs.
6. Do not document exposed-but-unused parameters as active behavior. Mention them in Notes / Gotchas if they appear in the command model.
7. Verify examples use actual supported arguments and interfaces. Keep them practical and runnable; do not invent routes, payloads, tool names, or output.
8. Proofread the page for grammar, consistent capitalization, readable flow, and human-friendly wording.
9. Verify Markdown structure, code fence languages, links, command references, and API references after editing.

## Writing style

- Never use "contract" or "contracts" in prose or headings. Use "documentation", "reference", "interface", "arguments", or "behavior" to describe what you mean. Preserve literal file paths and code identifiers.
- Before adding user-facing content, check whether users need it to use a feature, interpret results, or understand a limitation. Omit internal implementation details and routine fixes that do not help with these goals; task pages do not need an entry for every code change.
- Prefer short sentences and active voice.
- Use periods to end sentences. Do not use semicolons to separate sentences or clauses.
- Use only the plain ASCII hyphen (`-`) for dashes. Do not use en dashes (`?`) or em dashes (`?`) in prose. Preserve punctuation required by code, commands, URLs, and identifiers.
- Use **Netbox** for the product name in prose and headings. Keep lowercase `netbox` for service names, task names, command paths, Python imports, and API references.
- Use consistent terminology:
  - Pick one: **Service** vs **Worker** wording in headings and keep it consistent per section.
  - Use the same names for the same concept everywhere (e.g. `kwargs`, `workers`, `service`, `task`).
- Put the most common path first; hide long outputs behind collapsible blocks.

## Headings

- Use `#` once per page.
- Use `##` for major sections and `###` for subsections.
- Keep headings action-oriented for How-to pages (e.g. “Run tests”, “Generate inventory”).

## Code blocks

- Always specify a language: `bash`, `yaml`, `json`, `python`.
- For long outputs, use `<details><summary>…</summary>…</details>`.
- If you need nested code fences (code block inside a code block), use longer outer fences:

````markdown
```python
print("nested")
```
````

## Examples

Examples MUST use tabbed Markdown with exact labels `=== "CLI"`, `=== "Python"`,
`=== "FastAPI"`, and `=== "MCP"`. Indent tab contents by four spaces. Demonstrate the same
operation through each interface. If an interface is unsupported, state that limitation instead
of inventing support. Introduce required service setup briefly or link its existing guide.

### CLI

Show runnable NFCLI commands with the `nf#` prompt and actual aliases. Distinguish interactive
commands such as `nornir restconf get` from dotted command-reference paths.

### Python

Follow existing task examples with readable multiline `client.run_job(...)` calls and explicit
`kwargs`. Assume an established client in task examples; keep lifecycle setup in client/quickstart
guides unless the example specifically teaches startup. Avoid repeated lifecycle boilerplate,
chained one-line `nf.make_client().run_job(...)` calls, and excessively long lines.

```python
result = client.run_job(
    "nornir", "restconf_get",
    kwargs={
        "FL": ["ceos-spine-1"],
        "url": "openconfig-system:system/state/hostname",
    },
)
```

### FastAPI

Include BOTH Python `requests` and `curl` examples within the FastAPI tab. Show the actual endpoint,
bearer-token placeholder and JSON body. A raw HTTP request block alone is insufficient. Check the
route, outer HTTP method, and argument structure against the FastAPI implementation; the device
operation may differ from the method used to submit the NorFab job.

### MCP

Show a natural-language prompt identifying the NorFab service and task tool, device, operation,
and necessary values. Do not show JSON-RPC envelopes, internal tool identifiers such as
`service_nornir__task_restconf_delete`, or raw argument dictionaries as the prompt.

```text
Use the NorFab Nornir RESTCONF delete tool to remove Loopback100 from ceos-spine-1.
Report whether the operation succeeded.
```

Use realistic sample values without private keys/tokens. Describe device support and payload
requirements where necessary. If `markdown=True` is supported, show how to render/store that output.

## Command shell references

- Use a `bash` code block for command tree output.
- Use dotted paths, for example `nf# man tree nornir.restconf.get`, with a space after `nf#`.
  Never use `nf# man tree nornir restconf get`.
- Keep command shell references near the end of the page.
- Keep the tree in sync with the NFCLI/PICLE command model.

## Output sections

- Every service task page must include an `Output` or `Outputs` section.
- Use `Output` on each task page. Grouping/overview pages may summarize multiple outputs and link to the individual task pages.
- Show the real result shape when it is known.
- Use `TBD` when the exact result shape is uncertain, so maintainers can review and fill it later.

## Python API references

- Never append notes or other content after the final API reference. Place updates in the relevant section above it, such as Output, Examples, or Notes / Gotchas.
- End service task pages with the autodoc reference for the task method:

```markdown
<!-- Write an mkdocstrings directive here, for example:
     ::: package.module.Class.task_method
-->
```

- Prefer the concrete task mixin/class that defines the method over a broad worker class when possible.
- Each task page references only its task method. Use separate pages for separate tasks.

## Links

- Prefer relative links to pages that are in `nav`.
- Avoid linking to folders (MkDocs does not treat folders as pages). Link to a concrete page.
- Keep anchor links lowercase (MkDocs generates lowercase header IDs).

## Naming conventions

- Use consistent filenames:
  - `services_<service>_service.md`
  - `services_<service>_service_inventory.md`
  - `services_<service>_service_tasks_<task>.md`
- Use consistent nav labels:
  - Task names in Title Case (e.g. “Get Devices”, “File Copy”).

## When to create a new page

Always create a separate page for each service task, even when tasks share a protocol or helper.
For other documentation, create a new page when:

- The topic is referenced from multiple places (avoid duplication).
- A task page exceeds ~2–3 screens and includes multiple distinct workflows.

Otherwise, keep content in the closest existing page and add anchors.

## Verification checklist

Before finishing a documentation change:

- Confirm every code block has a language.
- Confirm one task per page and a task-focused overview without example/test narration.
- Confirm all four interface tabs, multiline Python client usage, requests AND curl for FastAPI,
  and a natural-language NorFab tool prompt for MCP.
- Confirm dotted `man tree` paths, API reference last, and no Inputs section.
- Confirm common behavior such as `dry_run`, `branch`, filters, and task modes are covered when supported.
- Confirm examples use real task names, aliases, and Python kwargs.
- Confirm notes call out exposed-but-unused options or version restrictions.
- Run Markdown, docs build, or diff checks when practical.

## Documentation layout

- `clients/`: user guides for client interfaces.
- `tutorials/`: installation, quickstart, deployment, and integration walkthroughs.
- `api_ref/core/`, `api_ref/clients/`, and `api_ref/workers/`: generated Python API references.
- `reference/`: inventory and architecture reference material.
- `workers/<service>/`: service overviews, inventory, and task documentation.
- `customization/`: hooks and service plugin guides.
- `development/adr/`: architecture decision records, with an index recording their stated status.
- `development/testing/`: testing framework documentation.
- `development/specs/<NNN-feature-name>/`: durable Spec Kit feature specifications, plans, tasks, interface definitions, and checklists.

Keep the homepage, feature catalogue, project overview pages, changelog, contact page, and tags at the documentation root. Keep shared assets in `images/`, `stylesheets/`, and `javascripts/`.

When moving pages, update `mkdocs.yml`, relative links, image paths, and repository references. Avoid publishing pages containing only `TBD`. Index entries without an explicit status must say that the status is not stated; do not infer completion from a filename.
