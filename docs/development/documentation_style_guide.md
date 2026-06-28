# Documentation Style Guide

This guide defines lightweight conventions for NORFAB documentation. The goal is to keep pages consistent, easy to scan, and easy to maintain.

## Page types

Use the page type that matches the reader intent:

- **Overview**: what a component does, when to use it, key concepts.
- **How-to**: step-by-step for a specific goal (task-oriented).
- **Reference**: complete options/arguments, defaults, and output schema.
- **Troubleshooting**: common failure modes and fixes.

## Recommended page template

For most service task pages, prefer this order:

1. **Purpose** (1–2 paragraphs)
2. **Inputs** (kwargs, required vs optional, defaults)
3. **Output** (what the result looks like)
4. **Examples** (in tabbed format)
   - CLI example in the `=== "CLI"` tab
   - Python example in the `=== "Python"` tab
5. **Notes / Gotchas** (timeouts, filters, permissions)
6. **Troubleshooting**
7. **Task Command Shell Reference** in tree format
8. **Python API Reference**

## Agent workflow for service task docs

When updating a service task page:

1. Read the task implementation, input/output Pydantic models, and NFCLI/PICLE command model before editing.
2. Derive Inputs from the Pydantic model and task signature.
3. Add an Output section to every task page. If the exact output shape is unclear, write `TBD` and leave it for maintainer review.
4. Derive CLI examples from NFCLI aliases and command structure.
5. Derive Python examples from `client.run_job(...)` using the task API name and Python kwargs.
6. Do not document exposed-but-unused parameters as active behavior. Mention them in Notes / Gotchas if they appear in the command model.
7. Keep examples safe, realistic, and runnable-looking.
8. Proofread the page for grammar, consistent capitalization, readable flow, and human-friendly wording.
9. Verify Markdown structure, code fence languages, links, command references, and API references after editing.

## Writing style

- Prefer short sentences and active voice.
- Use **NetBox** for the product name in prose and headings. Keep lowercase `netbox` only for service names, task names, command paths, Python imports, and API references.
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

- Provide both **CLI** and **Python** examples for user-facing tasks.
- Use exact tab labels: `=== "CLI"` and `=== "Python"`.
- In the CLI tab, show NFCLI shell commands with the `nf#` prompt.
- In the Python tab, show both context-manager usage (`with NorFab(...) as nf:`) and direct lifecycle usage (`nf.start()` / `nf.destroy()`) when practical.
- Use real-looking but safe sample values (avoid private endpoints/keys).
- If a task supports `markdown=True`, include one example showing how to render or store the markdown output.

## Command shell references

- Use a `bash` code block for command tree output.
- Use `nf# man tree ...` with a space after `nf#`.
- Keep command shell references near the end of the page.
- Keep the tree in sync with the NFCLI/PICLE command model.

## Output sections

- Every service task page must include an `Output` or `Outputs` section.
- Prefer `Output` for single-task pages and `Outputs` for pages that document several task APIs.
- Show the real result shape when it is known.
- Use `TBD` when the exact result shape is uncertain, so maintainers can review and fill it later.

## Python API references

- End service task pages with the autodoc reference for the task method:

```markdown
::: package.module.Class.task_method
```

- Prefer the concrete task mixin/class that defines the method over a broad worker class when possible.
- When one page documents multiple task APIs, add a readable `###` subheading before every autodoc reference. Use Title Case task names in the subheading and keep the autodoc target immediately below it:

```markdown
### SNMP Get

::: norfab.workers.nornir_worker.snmp_task.SnmpTask.snmp_get

### SNMP Walk

::: norfab.workers.nornir_worker.snmp_task.SnmpTask.snmp_walk
```

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

Create a new page when:

- The topic is referenced from multiple places (avoid duplication).
- A task page exceeds ~2–3 screens and includes multiple distinct workflows.

Otherwise, keep content in the closest existing page and add anchors.

## Verification checklist

Before finishing a documentation change:

- Confirm every code block has a language.
- Confirm user-facing tasks have both CLI and Python examples.
- Confirm common behavior such as `dry_run`, `branch`, filters, and task modes are covered when supported.
- Confirm examples use real task names, aliases, and Python kwargs.
- Confirm notes call out exposed-but-unused options or version restrictions.
- Run Markdown, docs build, or diff checks when practical.
