# NSS Initial Data Model

**Status**: Proposed, unimplemented. Initial scope is persistent graph CRUD and XML sync_from only.

## Storage

One NssWorker owns one writable Ladybug database as self.graph_db, separate from the base SQLite self.db. Keep existing task scheduling, task-scoped connections, one mutation lock, and atomic transactions. Private database keys distinguish records without public semantic IDs or stored full-path keys.

## Nodes and containment

Root is caller-named. Items have namespace_uri, local_name, kind (object, collection, leaf), value_json, properties_json, and XML attribute metadata. Values preserve types, null, and supplied text without inference. Roots have unique names; object fields have unique namespace/local-name slots within their parent. Collection members are separate nodes and may share names, values, and content. No entity_name matching field is needed.

Contains links an object/root to its fields. Member links a collection to each entry; duplicate entries use distinct endpoint nodes. Both are structural containment, with one parent per item and no cycles. Generic directed links carry type and properties, one per source/target/type; they may cross roots. Generic link CRUD cannot modify structural edges.

## Source conversion

XML parsing/normalization is implemented through methods on NssWorker using namespace-aware xmltodict, disabled entity expansion, and whitespace stripping disabled. Preserve dictionary object and array structure; do not flatten wrappers or infer semantic keys. XML text-plus-attribute leaves store the text as value with separate metadata. Containers with element children remain objects. Empty tags are present null leaves. Prefix spelling and collection order are not semantic identities.

Singleton/repeated shape follows xmltodict without hints. The reference captures contain worker/NETCONF envelopes; fixture preparation extracts actual configuration XML without adding a transport adapter to NSS. JSON is a structural reference, not a new input format.

## Sync and mutation

Default merge recursively merges same-shape object fields, preserving omitted fields. Supplied arrays replace every entry; omitted arrays survive. Shape changes replace only that supplied field subtree. Explicit root replacement removes omitted fields. Delete incident links of removed nodes, preserve other roots and links among surviving nodes, and do not promise persistent collection-entry identity across syncs. Reordering preserves content and multiplicity but may replace membership records.

Root creation requires only its name (parent=null, node=null), rejecting duplicates. Child creation requires a payload and exactly one resolved parent. Object field duplicates fail; duplicate collection entries are valid. Updates distinguish omitted value from explicit null and patch supplied property keys without renaming/reparenting. Leaf value changes preserve the leaf's node; structural shape changes are performed through sync, not update_node.

## Selection and deletion

Selectors traverse named object fields and select collection members. Object-entry filters match exact direct leaf fields with AND semantics. XML attribute-wrapped leaf comparisons use leaf values. Scalar-entry selection compares the entry value exactly. Missing differs from null and strings differ from numeric/boolean values. No nested filters, regex, range, OR, list-index identity, inferred keys, or public storage handles.

Reads may resolve several entries; individual mutations, create_node parents, and generic relationship endpoints require exactly one node. Zero/ambiguous matches fail atomically. Identical duplicate entries are manageable by collection replacement.

Without cascade, deleting a container with children fails. Explicit cascade follows both structural edge kinds, removes incident generic links, and preserves nodes reachable only through generic links. No service ownership semantics, tombstones, history tables, reconciliation plans, or device operations belong in this milestone.
