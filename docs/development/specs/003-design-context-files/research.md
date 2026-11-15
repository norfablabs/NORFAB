# Design Context File Research

**Date**: 2026-11-15. **Status**: Design research complete. Implementation delivered.

## Existing Preparation Flow

Decision: Add file defaults after Markdown processing and before schema validation.
Rationale: `design_tasks.py` already merges parsed Markdown context with task input
before validating `design_input_schema`. Load every declared file into a separate dictionary and merge design-file, Markdown and task values in that order.
Alternatives considered: loading before Markdown parsing would risk expanding block
scope. Separate Jinja globals would contradict the clarified context dictionary.

## Metadata Recognition

Decision: Extend `DesignDocument`, Markdown `metadata_keys`, dictionary metadata
extraction and the leading YAML metadata scan.
Rationale: `DesignDocument` forbids unknown fields. Markdown derives collections
from its fields minus metadata. All four locations must agree.
Alternatives considered: a new parser or metadata model adds unnecessary code.
YAML metadata after collections is unsupported by the existing scan and is not
introduced here. Markdown metadata can appear in any design fence and is assembled first.

## File Fetch And Parsing

Decision: Validate supported schemes and YAML suffixes in the existing Pydantic design model. Reuse `self.fetch_file(url, raise_on_fail=True)` and `yaml.safe_load` directly.
Rationale: `norfab/core/worker.py` recognizes nf:// and git://, and fetches text.
`norfab/core/client.py` already resolves Git references through FileSharing.
Do not add Git or cache logic. Do not use `or {}` after YAML parsing.
Alternatives considered: raw text, JSON and CSV loaders, recursive resolution and
Jinja rendering were explicitly excluded.

Decision: Accept YAML path suffixes .yaml and .yml. Validate declaration shape once
and source eligibility at the Pydantic model boundary for every declaration before fetching.
Rationale: Both suffixes identify YAML files. All declared files are fetched even when their values are later replaced. Whole-key merging preserves null and false values.
JSON-compatible content inside a YAML file remains valid YAML. No format-sniffing
or separate JSON parser is needed.

## Compatibility And Validation

Decision: Preserve task signature, client models, dry-run output and handlers.
Rationale: This is document metadata, not a new public task argument.
Dictionary designs load effective context but retain existing no-template behavior.

Decision: Use few focused public-client previews and existing regression tests.
Rationale: `test_designs.py` has preview and Markdown patterns. An overridden missing file must still fail, proving all declared sources are loaded. Git support can use the existing local
repository registration pattern from `tests/services/filesharing/test_git.py`.
No new global test fixture or Netbox database ownership is required.

Decision: Preserve existing loader behavior for duplicate keys inside YAML mappings.
Rationale: Replacing PyYAML loading to enforce duplicate-key rejection would broaden
this feature. Existing duplicate Markdown metadata and context definitions remain errors.
The spec edge case is narrowed to those existing duplicate checks.

## Outcome

No unresolved technical questions. No new dependencies, public task arguments,
shared utilities or architecture decision are required.
