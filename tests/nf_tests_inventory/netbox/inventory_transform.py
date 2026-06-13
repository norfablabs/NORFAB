from typing import Any


def transform(
    device_name: str,
    parsed_data: list[dict[str, str | None]],
    worker: Any,
) -> list[dict[str, str | None]]:
    """Map the FakeNOS RSP record to test NetBox inventory names."""
    transformed_data = []

    for record in parsed_data:
        item = dict(record)
        if (
            device_name == "fakenos-iosxr1"
            and worker.name.startswith("netbox-worker")
            and item["module"] == "A9K-RSP440-TR"
        ):
            item["slot"] = "mapped transformer RSP bay"
            item["module"] = "TEST-TRANSFORMED-RSP"
        transformed_data.append(item)

    return transformed_data
