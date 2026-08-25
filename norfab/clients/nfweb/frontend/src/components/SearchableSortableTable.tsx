import { useMemo, useState } from "react";
import type { ReactNode } from "react";
import {
  Center,
  Group,
  Stack,
  Table,
  Text,
  TextInput,
  UnstyledButton,
} from "@mantine/core";
import {
  IconChevronDown,
  IconChevronUp,
  IconSearch,
  IconSelector,
} from "@tabler/icons-react";

export interface InspectorTableColumn {
  key: string;
  label: string;
}

export interface InspectorTableRow {
  id: string;
  values: Record<string, string>;
  cells?: Partial<Record<string, ReactNode>>;
}

interface SearchableSortableTableProps {
  label: string;
  columns: InspectorTableColumn[];
  rows: InspectorTableRow[];
  minWidth?: number;
}

export function filterAndSortRows(
  rows: InspectorTableRow[],
  search: string,
  sortBy: string,
  reversed: boolean,
): InspectorTableRow[] {
  const query = search.trim().toLocaleLowerCase();
  return rows
    .filter(
      (row) =>
        !query ||
        Object.values(row.values).some((value) =>
          value.toLocaleLowerCase().includes(query),
        ),
    )
    .slice()
    .sort((left, right) => {
      const compared = (left.values[sortBy] ?? "").localeCompare(
        right.values[sortBy] ?? "",
        undefined,
        { numeric: true, sensitivity: "base" },
      );
      return reversed ? -compared : compared;
    });
}

export default function SearchableSortableTable({
  label,
  columns,
  rows,
  minWidth = 320,
}: SearchableSortableTableProps) {
  const [search, setSearch] = useState("");
  const [sortBy, setSortBy] = useState(columns[0]?.key ?? "");
  const [reversed, setReversed] = useState(false);
  const visibleRows = useMemo(
    () => filterAndSortRows(rows, search, sortBy, reversed),
    [rows, search, sortBy, reversed],
  );

  const selectSort = (key: string) => {
    if (key === sortBy) setReversed((value) => !value);
    else {
      setSortBy(key);
      setReversed(false);
    }
  };

  return (
    <Stack className="inspector-table" gap="xs">
      <TextInput
        aria-label={`Search ${label.toLocaleLowerCase()}`}
        label="Filter rows"
        leftSection={<IconSearch size={14} />}
        placeholder="Search by any field"
        size="xs"
        value={search}
        onChange={(event) => setSearch(event.currentTarget.value)}
      />
      <Table.ScrollContainer minWidth={minWidth} type="native">
        <Table
          aria-label={label}
          highlightOnHover
          stickyHeader
          horizontalSpacing="xs"
          verticalSpacing="sm"
        >
          <Table.Thead>
            <Table.Tr>
              {columns.map((column) => {
                const SortIcon =
                  sortBy !== column.key
                    ? IconSelector
                    : reversed
                      ? IconChevronUp
                      : IconChevronDown;
                return (
                  <Table.Th key={column.key}>
                    <UnstyledButton
                      className="table-sort-control"
                      aria-label={`Sort by ${column.label}`}
                      onClick={() => selectSort(column.key)}
                    >
                      <Group gap={4} justify="space-between" wrap="nowrap">
                        <Text fw={600} size="xs">
                          {column.label}
                        </Text>
                        <Center c="dimmed">
                          <SortIcon size={13} />
                        </Center>
                      </Group>
                    </UnstyledButton>
                  </Table.Th>
                );
              })}
            </Table.Tr>
          </Table.Thead>
          <Table.Tbody>
            {visibleRows.length ? (
              visibleRows.map((row) => (
                <Table.Tr key={row.id}>
                  {columns.map((column) => (
                    <Table.Td key={column.key}>
                      {row.cells?.[column.key] ?? row.values[column.key] ?? ""}
                    </Table.Td>
                  ))}
                </Table.Tr>
              ))
            ) : (
              <Table.Tr>
                <Table.Td colSpan={columns.length}>
                  <Text c="dimmed" py="sm" size="xs" ta="center">
                    No matching records
                  </Text>
                </Table.Td>
              </Table.Tr>
            )}
          </Table.Tbody>
        </Table>
      </Table.ScrollContainer>
    </Stack>
  );
}
