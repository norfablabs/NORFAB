# Feature Specification: Design Context File References

**Feature Branch**: `003-design-context-files`

**Created**: 2026-11-15

**Status**: Draft

**Acceptance status**: Clarified requirements. **Implementation status**: Implemented and validated with focused public-client tests. See validation evidence in [plan.md](plan.md).

**Input**: User description: "Add a global design context mapping whose keys become Jinja2 context names and whose nf:// or git:// URL values provide the referenced data, supported by YAML and Markdown definitions. Review current NetBox design context boundaries and plan the feature."

## Clarifications

### Session 2026-11-15

- Q: When the same context key appears in a referenced file declaration, a Markdown context block, and task-supplied context, which value should win? → A: Task context overrides Markdown context, which overrides file-backed context. Replace whole top-level keys without a nested merge. Final implementation clarification: validate all declarations with Pydantic and load every declared file. Preserve existing skipped rendering of task-overridden Markdown definitions.
- Q: Which file formats should context URLs support? → A: YAML files only, for example `defaults.yaml`. No separate JSON, CSV, or raw-text format support.
- Q: What may a referenced YAML file contain at its top level? → A: Any YAML value. Assign the complete parsed value directly to the declared context key.
- Q: Should referenced YAML files support Jinja expressions before their contents are parsed? → A: No. Parse referenced context data directly as YAML without Jinja2 rendering.
- Q: Should existing Markdown context blocks be able to reference values loaded from context files? → A: No. Preserve current Markdown context blocks exactly: they render using explicit task input only. Keep this feature simple and surgical with minimal changes.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Reuse file-backed design data (Priority: P1)

As a NetBox design author, I can declare named context files in a design so shared data can be loaded from NorFab or Git URLs and used by Jinja2 without copying the data into every design.

**Why this priority**: File-backed shared data is the primary value of the feature and reduces duplication in reusable designs.

**Independent Test**: Preview a YAML design with one declared context name and a Jinja reference to it; the rendered design contains the referenced data.

**Acceptance Scenarios**:

1. **Given** a YAML design with `site_data: nf://...` inside its top-level `context` mapping, **When** the design is rendered, **Then** the referenced file content is available to Jinja2 as `context.site_data`.
2. **Given** a YAML design with a `git://` entry, **When** the design is rendered, **Then** its content is available under the declared key.
3. **Given** a referenced file cannot be fetched or parsed, **When** rendering starts, **Then** the job fails with an actionable error identifying the key or URL.

### User Story 2 - Use the same capability in Markdown designs (Priority: P1)

As a Markdown design author, I can declare the same named context files in a design metadata block and use their loaded values from design blocks.

**Why this priority**: Markdown is a supported design authoring format and must have equivalent capability to YAML.

**Independent Test**: Preview a Markdown design containing the mapping and a Jinja reference to one loaded value; the preview contains the expected value.

**Acceptance Scenarios**:

1. **Given** a Markdown design metadata block declaring the mapping, **When** it is parsed and rendered, **Then** the mapping is preserved and named values are available to Jinja2.
2. **Given** an existing Markdown context block, **When** rendered, **Then** only explicit task context is available, exactly as before. File-backed values, other document context, schema defaults, and shared design variables are unavailable to that block.

### User Story 3 - Preserve existing context boundaries (Priority: P2)

As a design author, I can continue using task `context` and device `local_context_data` without their meaning changing when global context files are present.

**Why this priority**: Existing designs depend on these distinct scopes and compatibility is required.

**Independent Test**: Render a design using task `context.site`, file-backed `context.site_defaults`, and device `local_context_data`; each remains in its documented scope.

**Acceptance Scenarios**:

1. **Given** task context and file-backed values, **When** rendering occurs, **Then** both are available under the Jinja2 `context` dictionary.
2. **Given** device or top-level `local_context_data`, **When** deployment occurs, **Then** it still updates device-local NetBox context and is not interpreted as a file-backed global.
3. **Given** the same key in task input, a Markdown context block, and the file mapping, **When** rendering occurs, **Then** task input replaces that key, the overridden block is not rendered, and the declared file is still loaded.
4. **Given** a Markdown context key without a task override but with a file declaration of the same key, **When** rendering occurs, **Then** the file is loaded and the Markdown value replaces it.

### Edge Cases

- Empty mappings are accepted and behave like no file-backed globals.
- Non-mapping declarations, empty keys, and unsupported URL schemes are rejected with field-specific errors. Existing duplicate Markdown metadata/context checks and YAML duplicate-key handling remain unchanged.
- Referenced files must be YAML documents. JSON, CSV, and raw-text file formats are unsupported. Invalid YAML fails before deployment.
- A referenced YAML document may contain a dictionary, list, string, number, boolean, or null. Assign its complete parsed value to the declared key without unwrapping or merging it. An empty YAML document produces null.
- Referenced context files are never Jinja2-rendered. Quoted Jinja expressions remain literal strings. Unquoted expressions must still form valid YAML or parsing fails. Existing Markdown context-block rendering is unchanged.
- Task context overrides Markdown context, which overrides file-backed context. Values replace whole top-level keys, including dictionaries, lists, empty values, and null. No nested merge occurs.
- Schema validation, dry-run rendering, and ordinary deployment observe the same loaded globals.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: The design document MUST accept an optional top-level `context` mapping for file-backed values, distinct from device `local_context_data` and NetBox `config_context`.
- **FR-002**: Each entry MUST have a non-empty string key and a URL using `nf://` or `git://`.
- **FR-003**: The system MUST fetch and parse every declared file, including values later replaced, before design rendering and expose its result as `context.<key>` in the existing Jinja2 context dictionary.
- **FR-014**: File-backed context MUST support YAML files ending in `.yaml` or `.yml` only, such as `nf://netbox/data/defaults.yaml`. Separate JSON, CSV, and raw-text file formats are outside scope.
- **FR-015**: The complete parsed YAML value MUST be assigned directly to its declared key, preserving dictionaries, lists, strings, numbers, booleans, and null. An empty YAML document MUST assign null. The file's dictionary entries MUST NOT be expanded into sibling context keys.
- **FR-016**: Referenced context-file contents MUST be parsed directly as YAML without Jinja2 rendering or recursive evaluation of loaded strings. Existing Markdown context-block rendering MUST retain its documented behavior.
- **FR-004**: YAML designs MUST support the mapping directly in their top-level definition.
- **FR-005**: Markdown designs MUST support the mapping through document metadata and preserve it during assembly.
- **FR-006**: File-backed context values MUST be available to design rendering after existing Markdown context processing. Markdown context blocks MUST continue rendering with explicit task input only. File-backed values MUST NOT be added to their rendering scope.
- **FR-007**: Task-supplied values MUST remain under the Jinja2 variable `context`, and device-local values MUST continue to use `local_context_data`.
- **FR-008**: Initial Pydantic design metadata validation MUST reject invalid mappings, unsupported schemes and non-YAML suffixes for every entry. Fetch and YAML parsing failures MUST fail before any NetBox write. Names inside `context` MUST NOT be rejected solely because they match design metadata or Jinja global names, since they remain nested dictionary keys.
- **FR-009**: Task context MUST override Markdown context, which MUST override file-backed context, by replacing whole top-level keys without nested merging. Every declared file MUST be loaded without override checks. Markdown definitions overridden by task input MUST NOT be rendered. Other keys from lower-priority sources MUST remain available.
- **FR-010**: The effective context MUST be assembled after existing Markdown context processing and before input-schema validation and design rendering. Dry-run rendering and deployment MUST use that same context. Existing schema validation behavior MUST be preserved.
- **FR-011**: Designs without file-backed globals MUST retain existing public arguments and behavior.
- **FR-012**: Documentation MUST include YAML and Markdown examples, URL and data-format rules, scope boundaries, precedence, and failure behavior.
- **FR-013**: Focused public-client integration tests MUST cover YAML loading, Markdown loading, both URL schemes through existing fixtures, failures, precedence, and device-local context preservation.
- **FR-017**: Implementation MUST remain a minimal, surgical extension of existing design metadata and context preparation, reuse existing file-fetch facilities, and avoid unrelated refactoring, new task arguments, or changes to Markdown context-block semantics.

### Key Entities *(include if feature involves data)*

- **File-backed context value**: A key in the design's top-level `context` mapping and a trusted `nf://` or `git://` source whose parsed content becomes a value in the effective context dictionary.
- **Task context**: The caller-supplied mapping exposed under `context` and optionally validated by `design_input_schema`.
- **Device-local context**: The `local_context_data` payload written to a specific NetBox device.
- **Effective context**: The dictionary assembled from file-backed defaults, Markdown context, and task input using the specified precedence, then passed through existing input-schema validation for design rendering and deployment functions.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Authors can preview YAML and Markdown designs using one file-backed global without duplicating its contents.
- **SC-002**: Invalid scheme, fetch, parse, and mapping cases covered by focused integration tests all fail before NetBox writes.
- **SC-003**: Existing designs without the mapping retain unchanged task-context and device-local-context behavior.
- **SC-004**: Documentation provides at least one verified YAML example and one verified Markdown example.
- **SC-005**: Context precedence tests demonstrate task input overriding Markdown and file-backed values, Markdown overriding file-backed values, and unrelated lower-priority keys remaining available.

## Assumptions

- Existing NorFab file-fetch behavior is reused for `nf://` and `git://`; no new storage backend or URL scheme is added.
- Referenced files are trusted design inputs, consistent with existing Jinja, custom-function, and schema files.
- The top-level `context` mapping declares file sources. Loaded values, Markdown context values, and task input populate the same Jinja2 `context` dictionary. No separate Jinja globals are introduced.
- Markdown context blocks retain all current parsing, rendering, and override behavior. Loading file-backed defaults occurs afterward and does not expand those blocks' input scope.
- Referenced files are parsed as YAML data and their complete parsed values are assigned to the declared context keys.
- NetBox device config context and device `local_context_data` remain outside the file-backed global namespace.
- This feature covers design authoring and rendering. It does not change NetBox ConfigContext records unless a design separately declares `config_context`.
