import { NavLink, ScrollArea, Stack, Text } from "@mantine/core";
import {
  IconGauge,
  IconLayoutDashboard,
  IconSettings,
  IconTopologyStar3,
} from "@tabler/icons-react";

const NAVIGATION = [
  { id: "overview", label: "Overview", icon: IconGauge, items: [] },
  {
    id: "dashboards",
    label: "Dashboards",
    icon: IconLayoutDashboard,
    items: [
      {
        label: "Topology",
        href: "#topology",
        icon: IconTopologyStar3,
      },
    ],
  },
  { id: "admin", label: "Admin", icon: IconSettings, items: [] },
] as const;

export type NavigationSection = (typeof NAVIGATION)[number]["id"];

interface ApplicationNavigationProps {
  open: NavigationSection | null;
  onToggle: (section: NavigationSection | null) => void;
}

export default function ApplicationNavigation({
  open,
  onToggle,
}: ApplicationNavigationProps) {
  return (
    <aside className="control-panel" aria-label="NFWeb applications">
      <ScrollArea h="100%" type="auto" scrollbarSize={6}>
        <Text className="navigation-heading" fw={600} size="sm" mb="sm" px="sm">
          Applications
        </Text>
        <Stack className="sidebar-navigation" gap={4}>
          {NAVIGATION.map((section) => {
            const SectionIcon = section.icon;
            const hasChildren = section.items.length > 0;
            return (
              <NavLink
                className="navigation-link"
                component="button"
                key={section.id}
                label={section.label}
                leftSection={<SectionIcon size={18} />}
                opened={hasChildren ? open === section.id : undefined}
                disabled={!hasChildren}
                onChange={
                  hasChildren
                    ? (opened) => onToggle(opened ? section.id : null)
                    : undefined
                }
                variant="light"
              >
                {section.items.map((item) => {
                  const ItemIcon = item.icon;
                  return (
                    <NavLink
                      className="navigation-child-link"
                      component="a"
                      href={item.href}
                      key={item.href}
                      label={item.label}
                      leftSection={<ItemIcon size={16} />}
                      active
                      variant="light"
                    />
                  );
                })}
              </NavLink>
            );
          })}
        </Stack>
      </ScrollArea>
    </aside>
  );
}
