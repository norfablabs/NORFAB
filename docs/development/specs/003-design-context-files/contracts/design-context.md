# Design Context File Reference

**Status**: Implemented.

## Document Syntax

YAML metadata precedes collections:

```yaml
context:
  defaults: nf://netbox/data/defaults.yaml
  links: git://design-data/links.yml
sites:
  - name: "{{ context.defaults.site }}"
```

The same declaration is accepted in a Markdown design fence:

````markdown
```yaml design
context:
  defaults: nf://netbox/data/defaults.yaml
```

```yaml design
sites:
  - name: "{{ context.defaults.site }}"
```
````

Declare the metadata key once. Existing Markdown context.KEY blocks and tables
continue rendering using explicit task input only.

## Values And Precedence

Fetch every declared YAML source and assign each complete parsed value to its key.
For example, a source containing `[10, 20]` becomes `context.links == [10, 20]`.
A source containing `null` or an empty document produces null.
Do not unwrap dictionaries, render file contents, merge nested data or fetch nested URLs.

Task input overrides Markdown values, which override file defaults.
All declared files are validated by Pydantic and loaded even when their values are later replaced. Task-overridden Markdown definitions are not rendered.
Existing input-schema validation runs on the assembled context afterward.

## Public Interfaces

Existing `design_deploy(design=..., context=..., dry_run_render=True)` arguments
and output remain unchanged across Python, CLI, FastAPI and MCP.
The design metadata mapping does not become a new task argument.
Parsed dictionary designs retain existing no-template and unchanged preview behavior.

## Errors And Boundaries

Unsupported source schemes/extensions, invalid mapping entries, missing files and
invalid YAML fail through existing task error results before writes. Errors identify
the failing key or URL without exposing file contents.
Use .yaml or .yml paths. JSON, CSV and text files have no separate loading mode.
Existing YAML duplicate-key handling remains unchanged.
Netbox configuration context and device-local context keep their existing behavior.
