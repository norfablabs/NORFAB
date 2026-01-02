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
3. **Outputs** (what the result looks like)
4. **Examples**
   - CLI example
   - Python example
5. **Notes / Gotchas** (timeouts, filters, permissions)
6. **Troubleshooting**

## Writing style

- Prefer short sentences and active voice.
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
- Use real-looking but safe sample values (avoid private endpoints/keys).
- If a task supports `markdown=True`, include one example showing how to render or store the markdown output.

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
