# ADR: Netbox Markdown design parser

## Status

Proposed, 2026-10-28. Extends the [design specification](adr_netbox_design_specification.md).

## Decision

Use `markdown-it-py` to extract design source and context from Markdown before
passing them through the existing `design_deploy` preparation and rendering path.
Preserve the source URL for relative Jinja includes. YAML and dictionary inputs
remain supported.

### Blocks

| Fence info | Meaning |
| --- | --- |
| `yaml design` | One or more YAML/Jinja collections or metadata sections |
| `yaml context.vlans` | YAML value assigned to `context.vlans` |
| `csv context.connections` | CSV rows assigned as a list of dictionaries |
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
Reject unknown top-level keys, inline collection values, and duplicate YAML keys
after rendering. No record deduplication or deep merging.

Put literal `design_input_schema`, `jinja_functions`, and `custom_functions` in
the first `yaml design` block, before collections; each metadata key occurs once.
Keep existing function URLs;
inline Python is outside scope. This block is visible in Markdown previews;
front matter is unnecessary.

Collect context as literal data without Jinja rendering. CSV/table cells remain
strings; reject duplicate/empty headers, malformed row widths, and duplicate
context targets. Explicit task context overrides document values by top-level
key before input-schema validation. Initially, targets name one top-level key.
Native rendered tables need an explicit destination marker; syntax is deferred.

### Processing

1. Parse Markdown tokens; ignore unmarked examples and prose.
2. Assemble one YAML/Jinja source, with metadata first and grouped collections.
3. Combine document and task context.
4. Reuse schema validation, Jinja rendering, YAML parsing, flattening, and deployment.

`dry_run_render` returns assembled,
rendered YAML. Include block line numbers in parsing errors where available.

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

Use public-client integration tests for equivalent YAML/Markdown results,
multiple collections per block, repeated collection sections, context overrides, filters, relative includes,
render previews, and malformed input. Add an ACME Markdown companion example.
