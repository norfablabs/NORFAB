const NAVIGATION = [
  { id: "overview", label: "Overview", items: [] },
  {
    id: "dashboards",
    label: "Dashboards",
    items: [{ label: "Topology", href: "#topology" }],
  },
  { id: "admin", label: "Admin", items: [] },
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
    <aside className="control-panel">
      <nav className="sidebar-navigation" aria-label="NFWeb applications">
        {NAVIGATION.map((section) => {
          const expanded = open === section.id;
          return (
            <div className="navigation-group" key={section.id}>
              <button
                className="navigation-heading"
                type="button"
                aria-expanded={expanded}
                aria-controls={`navigation-${section.id}`}
                onClick={() => onToggle(expanded ? null : section.id)}
              >
                <span>{section.label}</span>
                <span className="navigation-chevron" aria-hidden="true" />
              </button>
              <div
                className={`navigation-submenu ${expanded ? "expanded" : ""}`}
                id={`navigation-${section.id}`}
                aria-hidden={!expanded}
              >
                <div>
                  {section.items.map((item) => (
                    <a
                      href={item.href}
                      aria-current="page"
                      tabIndex={expanded ? 0 : -1}
                      key={item.href}
                    >
                      {item.label}
                    </a>
                  ))}
                </div>
              </div>
            </div>
          );
        })}
      </nav>
    </aside>
  );
}
