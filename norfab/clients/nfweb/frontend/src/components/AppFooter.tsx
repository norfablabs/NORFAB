import { ActionIcon, Group, Text, Tooltip } from "@mantine/core";
import { IconApi, IconBook2, IconBrandGithub } from "@tabler/icons-react";
import type { ComponentType } from "react";
import type { NFWebFooterConfig } from "../types";

interface FooterLinkProps {
  href: string | null;
  label: string;
  icon: ComponentType<{ size?: number }>;
}

function FooterLink({ href, label, icon: Icon }: FooterLinkProps) {
  if (!href) return null;
  return (
    <Tooltip label={label}>
      <ActionIcon
        component="a"
        href={href}
        target="_blank"
        rel="noreferrer"
        aria-label={label}
        variant="subtle"
        color="gray"
      >
        <Icon size={17} />
      </ActionIcon>
    </Tooltip>
  );
}

export default function AppFooter({ config }: { config: NFWebFooterConfig }) {
  return (
    <footer className="app-footer">
      <Group
        component="nav"
        className="footer-links"
        gap={4}
        aria-label="NORFAB resources"
      >
        <FooterLink
          href={config.fastapi_url}
          label="Open NORFAB FastAPI"
          icon={IconApi}
        />
        <FooterLink
          href={config.docs_url}
          label="Open NORFAB documentation"
          icon={IconBook2}
        />
        <FooterLink
          href={config.github_url}
          label="Open NORFAB GitHub repository"
          icon={IconBrandGithub}
        />
      </Group>
      {config.message && (
        <Text c="dimmed" size="xs" truncate>
          {config.message}
        </Text>
      )}
    </footer>
  );
}
