# ADR: Netbox Markdown design parser

## Status

Accepted, 2026-10-29. Extends the [design specification](adr_netbox_design_specification.md).

## Decision

Use `markdown-it-py` in a separate `parse_markdown_design` task to convert
Markdown text or a file URL into YAML/Jinja source and literal context. Return
`design` and `context` separately. `design_deploy` also calls this parser for file
URLs ending in `.md` or `.markdown`. Explicit task context overrides document values by top-level
key before schema validation. Conversion does not render templates,
discover includes, execute functions or access Netbox.

### Blocks

| Fence info | Meaning |
| --- | --- |
| `yaml design` | One or more YAML/Jinja collections or metadata sections |
| `yaml context.vlans` | YAML value assigned to `context.vlans` |
| `csv context.connections` | CSV rows assigned as a list of dictionaries |
| `<!-- context.site_vlans -->` before an unfenced table | Table rows assigned as a list of dictionaries |
| `json context.name` | JSON context value |
| `text context.name` | Literal context string |

Scan each `yaml design` block for unindented literal `key:` headers. Each header
starts a section ending at the next header or block end. A block may contain
multiple collections, and collections may recur across blocks:

````markdown
## Router

```yaml design
devices:
  - name: branch-rtr-1
    site: "{{ context.site }}"
interfaces:
  - device: branch-rtr-1
    name: Ethernet1
    type: 1000base-t
```

## Access switch

```yaml design
devices:
  - name: branch-access-1
    site: "{{ context.site }}"
```
````

Group sections by collection key, remove their headers, append bodies in document
order, and emit one header per collection. Preserve indentation and Jinja text;
do not YAML-parse unrendered design source. Blank lines, comments, and Jinja
statements are not headers. Require indented list items and block-scalar content;
keep Jinja control flow within a section so regrouping preserves its scope.
Reject unknown top-level keys and inline collection values such as `devices: []`.
Repeated collection headers are expected and their bodies are concatenated.
Rendered YAML validation is outside this task. No record deduplication or deep merging.

Put literal `design_input_schema`, `jinja_functions`, and `custom_functions` in
any `yaml design` block; each metadata key occurs once. Emit them before
collections, with the schema first, followed by Jinja and custom functions.
Keep existing function URLs;
inline Python is outside scope. This block is visible in Markdown previews;
front matter is unnecessary.

Collect context as literal data without Jinja rendering. CSV/table cells remain
strings. Reject duplicate/empty headers, malformed CSV row widths, and duplicate
context targets. Return document context separately. Callers can override its
top-level keys before deployment. Targets name one top-level key.
Mark unfenced pipe-delimited tables with `<!-- context.KEY -->` on its own line
immediately before the table. Extract rows using markdown-it-py's table tokens. Unmarked tables
remain ignored. Table row widths follow the library's padding and truncation rules.

### Processing

1. Parse Markdown tokens; ignore unmarked examples and prose.
2. Assemble one YAML/Jinja source, with metadata first and grouped collections.
3. Return the unrendered source and extracted context.
4. Callers optionally use existing schema validation, rendering and deployment
   through a separate `design_deploy` call.

NorFab handles task errors. Conversion has no dry-run mode.
Direct `.md` or `.markdown` deployment resolves includes from the Markdown file's directory.
When deploying converted source separately, save the YAML at an
appropriate file URL and pass that URL to `design_deploy`; source text does not
carry the Markdown directory into rendering.

## Parser findings

- The client uses `mdutils` through `markdown_results.py`; it generates Markdown
  and does not provide the required structured parser. [Documentation](https://mdutils.readthedocs.io/en/latest/mdutils.html)
- `markdown-it-py` provides fence content/info, source line ranges, and table
  tokens. It is already a transitive lockfile dependency; declare it explicitly
  for the Netbox runtime. [Documentation](https://markdown-it-py.readthedocs.io/en/v4.0.0/using.html)
- Latest release checked: 4.2.0, 2026-05-07. Recent releases include performance
  fixes and multiple contributors; PyPI lists one publishing maintainer.
  Maintenance appears healthy, with maintainer concentration as a limitation.
  [Releases](https://github.com/executablebooks/markdown-it-py/releases), [PyPI](https://pypi.org/project/markdown-it-py/)
- Mistune supports AST/table parsing, but adds another dependency without a
  needed advantage here. [Documentation](https://mistune.lepture.com/en/stable/plugins.html)

## Verification

Use public-client integration tests for source conversion, multiple collections
per block, repeated collection sections, literal context, preserved filters and
include directives, and malformed input. Add an ACME Markdown companion example
and compare its converted source with the YAML original.
