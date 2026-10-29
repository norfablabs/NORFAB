"""Markdown design conversion through the public Netbox client."""

from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

import pytest
import yaml
from jinja2 import Environment

from tests.nf_tests_inventory.netbox.designs.acme_site_description import (
    acme_site_description,
)

pytestmark = [pytest.mark.netbox, pytest.mark.netbox_parse_markdown_design]


class TestParseMarkdownDesign:
    @pytest.mark.parametrize("extension", ["md", "markdown", "yaml"])
    @pytest.mark.parametrize("context", [{}, {"site": "OVERRIDE"}])
    def test_deploy_file_preview(
        self, nfclient: Any, extension: str, context: dict
    ) -> None:
        root = Path(nfclient.inventory.base_dir) / "netbox" / "designs"
        with TemporaryDirectory(prefix="markdown-preview-", dir=root) as directory:
            folder = Path(directory)
            source = "tenants:\n{% include 'records.yaml' %}\n"
            if extension in {"md", "markdown"}:
                source = (
                    "Ignored {{ unfinished Jinja and {% include 'missing.yaml' %}.\n"
                    "```yaml context.site\nDOCUMENT\n```\n"
                    "```yaml design\n" + source + "```\n"
                    "```yaml design\ndesign_input_schema:\n  type: object\n"
                    "  properties:\n    site: {type: string}\n  required: [site]\n```\n"
                )
            (folder / f"design.{extension}").write_text(source, encoding="utf-8")
            (folder / "records.yaml").write_text(
                "{% include 'tenant.yaml' %}\n", encoding="utf-8"
            )
            (folder / "tenant.yaml").write_text(
                "  - name: \"{{ context.site | default('YAML') }}\"\n", encoding="utf-8"
            )
            response = nfclient.run_job(
                "netbox",
                "design_deploy",
                workers="any",
                kwargs={
                    "design": f"nf://netbox/designs/{folder.name}/design.{extension}",
                    "context": context,
                    "dry_run_render": True,
                },
            )
            assert response
            for result in response.values():
                assert not result["failed"], result
                rendered = yaml.safe_load(result["result"])
                assert rendered["tenants"] == [
                    {
                        "name": context.get(
                            "site",
                            "DOCUMENT" if extension in {"md", "markdown"} else "YAML",
                        )
                    }
                ]

    def test_sections_and_context(self, nfclient: Any) -> None:
        markdown = """# Branch
Ignored {{ broken Jinja and {% include 'missing' %}.
```yaml
devices: []
```
```yaml design
design_input_schema: nf://models/site.py
jinja_functions:
  label: nf://functions/label.py
devices:
{% for name in context.names %}
  - name: {{ name | label }}
{% endfor %}
interfaces:
  - name: Ethernet1
```
```yaml design
devices:
  - name: fixed
devices:
  - name: fixed
```
```yaml context.names
- router1
```
```json context.options
{"enabled": true}
```
```csv context.links
port,description
Ethernet1,"uplink, primary"
```
```text context.note
{{ literal }}
```
"""
        response = nfclient.run_job(
            "netbox",
            "parse_markdown_design",
            workers="any",
            kwargs={"markdown": markdown},
        )
        assert response
        for result in response.values():
            assert not result["failed"], result
            assert result["result"] == {
                "design": "design_input_schema: nf://models/site.py\n"
                "jinja_functions:\n  label: nf://functions/label.py\n"
                "devices:\n{% for name in context.names %}\n"
                "  - name: {{ name | label }}\n{% endfor %}\n"
                "  - name: fixed\n  - name: fixed\n"
                "interfaces:\n  - name: Ethernet1\n",
                "context": {
                    "names": ["router1"],
                    "options": {"enabled": True},
                    "links": [{"port": "Ethernet1", "description": "uplink, primary"}],
                    "note": "{{ literal }}\n",
                },
            }

    @pytest.mark.parametrize(
        "blocks,error",
        [
            ("", "no yaml design blocks"),
            ("```yaml design\nunknown:\n  - name: x\n```", "unknown design key"),
            ("```yaml design\ndevices: []\n```", "inline collection"),
            ("```yaml design\ndevices:\n- name: x\n```", "indent"),
            (
                "```yaml design\ndevices:\n{% for x in [] %}\ninterfaces:\n{% endfor %}\n```",
                "end of template",
            ),
            ("```csv context.links\na,a\n1,2\n```", "CSV headers"),
            ("```csv context.links\na,b\n1\n```", "CSV row"),
            (
                "```yaml context.x\n1\n```\n```json context.x\n2\n```",
                "duplicate context",
            ),
            ("```text context.x.y\nx\n```", "context target"),
            (
                "```yaml design\njinja_functions: {}\njinja_functions: {}\n```",
                "metadata",
            ),
            ("```json context.x\n{invalid}\n```", "Expecting"),
            ("```csv context.x\na,\n1,2\n```", "CSV headers"),
            ("```python design\nx\n```", "invalid design/context fence"),
            (
                "<!-- context.x -->\n\nnot a table",
                "expected a Markdown table",
            ),
            (
                "<!-- context.x -->\n\n| a | a |\n| --- | --- |\n| 1 | 2 |\n",
                "MARKDOWN headers",
            ),
            (
                "<!-- context.x -->\n\n| a | |\n| --- | --- |\n| 1 | 2 |\n",
                "MARKDOWN headers",
            ),
            (
                "<!-- context.x -->\n\n| a |\n| --- |\n| 1 |\n\n```yaml context.x\n[]\n```",
                "duplicate context",
            ),
            (
                "```yaml context.x\n100: {name: USERS}\n```",
                "context.x must be JSON-serializable",
            ),
            (
                "```yaml context.x\n!!binary YWJj\n```",
                "context.x must be JSON-serializable",
            ),
            (
                "```yaml context.x\n!!set {a: null}\n```",
                "context.x must be JSON-serializable",
            ),
        ],
    )
    def test_invalid_input(self, nfclient: Any, blocks: str, error: str) -> None:
        response = nfclient.run_job(
            "netbox",
            "parse_markdown_design",
            workers="any",
            kwargs={"markdown": blocks},
        )
        assert response
        for result in response.values():
            assert result["failed"], result
            assert error in " ".join(result["errors"])

    def test_acme_file(self, nfclient: Any) -> None:
        response = nfclient.run_job(
            "netbox",
            "parse_markdown_design",
            workers="any",
            kwargs={"markdown": "nf://netbox/designs/acme_branch_network_design_v1.md"},
        )
        original = (
            Path(__file__).parents[2]
            / "nf_tests_inventory/netbox/designs/acme_branch_network_design_v1.yaml"
        ).read_text(encoding="utf-8")
        assert response
        for result in response.values():
            assert not result["failed"], result
            converted = result["result"]
            assert converted["design"].startswith("design_input_schema:\n")
            assert converted["context"] == {
                "site": "NORFAB ACME TEST",
                "parent_prefix": "198.19.224.0/20",
                "vlans": [
                    {"name": "USERS", "vid": 100, "enabled": True},
                    {"name": "MANAGEMENT", "vid": 200, "enabled": False},
                ],
                "links": [
                    {"port": "Ethernet1", "description": "uplink, primary"},
                    {"port": "Ethernet2", "description": "backup uplink"},
                ],
                "site_vlans": [
                    {
                        "site": "NORFAB ACME TEST",
                        "name": "USERS",
                        "vid": "100",
                        "status": "active",
                    },
                    {
                        "site": "NORFAB ACME TEST",
                        "name": "MANAGEMENT",
                        "vid": "200",
                        "status": "planned",
                    },
                ],
            }
            environment = Environment()
            environment.filters["acme_site_description"] = acme_site_description
            expected = yaml.safe_load(
                environment.from_string(original).render(context=converted["context"])
            )
            actual = yaml.safe_load(
                environment.from_string(converted["design"]).render(
                    context=converted["context"]
                )
            )
            expected["design_input_schema"]["properties"].update(
                {
                    "links": {"type": "array"},
                    "vlans": {"type": "array"},
                    "site_vlans": {"type": "array"},
                }
            )
            assert actual == expected

        preview = nfclient.run_job(
            "netbox",
            "design_deploy",
            workers="any",
            kwargs={
                "design": "nf://netbox/designs/acme_branch_network_design_v1.md",
                "dry_run_render": True,
            },
        )
        assert preview
        for result in preview.values():
            assert not result["failed"], result
            assert yaml.safe_load(result["result"]) == expected

    @pytest.mark.parametrize(
        "ending,extra",
        [
            ("tenants:\n  - name: B", {"tenants": [{"name": "A"}, {"name": "B"}]}),
            (
                "design_input_schema:\n  type: object",
                {"design_input_schema": {"type": "object"}},
            ),
        ],
    )
    def test_final_fence_boundaries(
        self, nfclient: Any, ending: str, extra: dict
    ) -> None:
        response = nfclient.run_job(
            "netbox",
            "parse_markdown_design",
            workers="any",
            kwargs={
                "markdown": "```yaml design\ntenants:\n  - name: A\nregions:\n  - name: R\n```\n```yaml design\n"
                + ending
            },
        )
        assert response
        for result in response.values():
            assert not result["failed"], result
            assert yaml.safe_load(result["result"]["design"]) == {
                "tenants": [{"name": "A"}],
                "regions": [{"name": "R"}],
                **extra,
            }

    @pytest.mark.parametrize("closing", ["```", ""])
    def test_literal_yaml(self, nfclient: Any, closing: str) -> None:
        response = nfclient.run_job(
            "netbox",
            "parse_markdown_design",
            workers="any",
            kwargs={
                "markdown": "```yaml design\ntenants:\n  - name: A\n```\n"
                "```yaml design\ntenants:\n  - name: B\n" + closing
            },
        )
        assert response
        for result in response.values():
            assert not result["failed"], result
            assert yaml.safe_load(result["result"]["design"]) == {
                "tenants": [{"name": "A"}, {"name": "B"}]
            }

    def test_preserve_includes_and_scalars(self, nfclient: Any) -> None:
        source = (
            "devices: # hardware\n"
            "{% include 'devices.yaml' %}\n"
            "  - name: router1\n"
            "    description: |\n"
            "      devices:\n"
            "      literal scalar content\n"
        )
        response = nfclient.run_job(
            "netbox",
            "parse_markdown_design",
            workers="any",
            kwargs={
                "markdown": "```yaml design\n" + source + "```\n"
                "```yaml context.empty\nnull\n```\n"
                '```csv context.links\na,b\n01,"first\nsecond"\n```'
            },
        )
        assert response
        for result in response.values():
            assert not result["failed"], result
            assert result["result"]["design"] == source.replace(
                "devices: # hardware\n", "devices:\n# hardware\n", 1
            )
            assert result["result"]["context"] == {
                "empty": None,
                "links": [{"a": "01", "b": "first\nsecond"}],
            }

    @pytest.mark.parametrize("gap", ["\n", "\n\n"])
    @pytest.mark.parametrize("indent", ["", " ", "  ", "   "])
    def test_markdown_table_cells(self, nfclient: Any, gap: str, indent: str) -> None:
        response = nfclient.run_job(
            "netbox",
            "parse_markdown_design",
            workers="any",
            kwargs={
                "markdown": "```yaml design\ntenants:\n  - name: ACME\n```\n"
                "```markdown\n<!-- context.ignored -->\n```\n"
                "| annotation |\n| --- |\n| <!-- context.ignored --> |\n\n"
                + indent
                + "<!-- context.vlans -->"
                + gap
                + "| vid | description |\n| --- | --- |\n"
                "| 0100 | users \\| office |\n| 0200 | {{ literal }} |\n"
            },
        )
        assert response
        for result in response.values():
            assert not result["failed"], result
            assert result["result"]["context"]["vlans"] == [
                {"vid": "0100", "description": "users | office"},
                {"vid": "0200", "description": "{{ literal }}"},
            ]
