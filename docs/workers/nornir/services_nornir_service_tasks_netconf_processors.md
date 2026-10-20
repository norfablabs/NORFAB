# NETCONF XML Processors

Process NETCONF replies on the worker before result serialization. These options
are available on `get`, `get-config`, `edit-config`, and `get-schema`. Capability
discovery returns lists rather than XML and does not expose XML processors.

## Supported Processors

| NFCLI option | Python argument | Output | Purpose |
| --- | --- | --- | --- |
| `xmltodict` | `xmltodict=True` | Nested dictionary | Parse an XML reply using Nornir-Salt `load_xml` and the xmltodict library. |
| `xpath EXPRESSION` | `xpath="EXPRESSION"` | XML string | Select XML elements locally using XPath. Namespaces are removed before selection. |
| `xml-flake PATTERN` | `xml_flake="PATTERN"` | Flat dictionary | Flatten XML and select dictionary keys using a case-sensitive glob pattern. |

The outer worker and host result structure is preserved. Each processor changes
only the operation payload. `add_details=True` retains execution metadata around
that payload; `to_dict=False` changes result serialization, not XML conversion.

## Convert XML to a Dictionary

=== "CLI"

    ```text
    nf# nornir netconf get-config xmltodict FL ceos-spine-1
    ```

=== "Python"

    ```python
    from norfab.core.nfapi import NorFab

    with NorFab(inventory="inventory.yaml") as nf:
        client = nf.make_client()
        result = client.run_job(
            "nornir", "netconf_get_config",
            kwargs={"FL": ["ceos-spine-1"], "xmltodict": True},
        )
        print(result)
    ```

Conversion preserves XML names and prefixes. Attributes normally use `@` keys,
text alongside attributes uses `#text`, and repeated elements become lists.
Empty elements can become `None`. Conversion does not provide a normalized
cross-vendor schema; dictionary shape depends on the device reply.

## Select XML Elements with XPath

The local `xpath` processor operates on the reply after retrieval. It differs
from `filter_xpath`, which asks the device to filter data before sending it.
Local XPath does not require the device XPath capability. NorFab removes XML
namespaces and enables parser recovery for this processor.

=== "CLI"

    ```text
    nf# nornir netconf get xpath "//hostname" FL ceos-spine-1
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "netconf_get",
        kwargs={"FL": ["ceos-spine-1"], "xpath": "//hostname"},
    )
    ```

Use expressions that select elements. Nornir-Salt serializes selected elements
back to XML; scalar expressions such as `count(...)`, text nodes, and attribute
selections are not supported by this wrapper. Several matches produce multiple
XML fragments; no matches produce an empty string.

## Extract Flat Values with XML Flake

`xml-flake` means XML flattened key filter. It parses XML, flattens nested paths
into dictionary keys, and selects matching keys. It returns dictionary values,
not XML fragments. For example, `*hostname*` selects paths containing hostname.

=== "CLI"

    ```text
    nf# nornir netconf get-config xml-flake *hostname* FL ceos-spine-1
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "netconf_get_config",
        kwargs={"FL": ["ceos-spine-1"], "xml_flake": "*hostname*"},
    )
    ```

Patterns match flattened paths, not values. Use `*in-octets*` to select matching
interface counter paths when the device reply includes those counters. No
matching paths returns an empty dictionary.

## Combine XPath and Dictionary Conversion

XML shortcuts execute in this order: `xml_flake`, `xpath`, then `xmltodict`,
regardless of argument order. Use `xml_flake` alone: it produces a dictionary,
which cannot be parsed again as XML by XPath or xmltodict.

XPath can precede xmltodict when it selects exactly one element, yielding a
single valid XML document:

=== "CLI"

    ```text
    nf# nornir netconf get xpath "(//hostname)[1]" xmltodict FL ceos-spine-1
    ```

=== "Python"

    ```python
    result = client.run_job(
        "nornir", "netconf_get",
        kwargs={
            "FL": ["ceos-spine-1"],
            "xpath": "(//hostname)[1]",
            "xmltodict": True,
        },
    )
    ```

For a matching hostname element, the operation payload is
`{"hostname": "ceos-spine-1"}`. Empty XPath output or multiple top-level fragments
cannot be parsed by xmltodict. A get-schema reply may contain YANG text inside its XML wrapper; conversion
does not parse the YANG language.

## Notes

- These processors work on data returned by the device; they do not reduce
  network transfer size. Use subtree or server-side XPath filters for that.
- XPath requires lxml; dictionary conversion and XML flake require xmltodict.
- Failed host operations are skipped by Nornir-Salt DataProcessor. Processor
  errors appear in task details; inspect `add_details=True` when diagnosing them.
- Common file saving and diff options remain available. Saved results reflect
  processor output.
