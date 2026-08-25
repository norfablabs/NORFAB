import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MantineProvider } from "@mantine/core";
import SearchableSortableTable, {
  filterAndSortRows,
  type InspectorTableRow,
} from "./SearchableSortableTable";

const rows: InspectorTableRow[] = [
  {
    id: "spine-2",
    values: { device: "spine-2", state: "warning" },
  },
  {
    id: "leaf-10",
    values: { device: "leaf-10", state: "healthy" },
  },
  {
    id: "leaf-2",
    values: { device: "leaf-2", state: "critical" },
  },
];

describe("SearchableSortableTable", () => {
  it("filters all fields and naturally sorts the selected column", () => {
    expect(
      filterAndSortRows(rows, "leaf", "device", false).map((row) => row.id),
    ).toEqual(["leaf-2", "leaf-10"]);
    expect(
      filterAndSortRows(rows, "healthy", "state", true).map((row) => row.id),
    ).toEqual(["leaf-10"]);
  });

  it("renders the Mantine search field and sortable table headers", () => {
    const markup = renderToStaticMarkup(
      <MantineProvider>
        <SearchableSortableTable
          label="Device connections"
          columns={[
            { key: "device", label: "Device" },
            { key: "state", label: "State" },
          ]}
          rows={rows}
        />
      </MantineProvider>,
    );

    expect(markup).toContain('placeholder="Search by any field"');
    expect(markup).toContain('aria-label="Sort by Device"');
    expect(markup).toContain('aria-label="Device connections"');
  });
});
