import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { MantineProvider } from "@mantine/core";
import AppFooter from "./AppFooter";

describe("AppFooter", () => {
  it("renders the configured message and resource links", () => {
    const markup = renderToStaticMarkup(
      <MantineProvider>
        <AppFooter
          config={{
            message: "Lab topology",
            fastapi_url: "http://127.0.0.1:8000/docs",
            docs_url: "https://docs.norfablabs.com/",
            github_url: "https://github.com/norfablabs/NORFAB",
          }}
        />
      </MantineProvider>,
    );

    expect(markup).toContain("Lab topology");
    expect(markup).toContain('aria-label="Open NORFAB FastAPI"');
    expect(markup).toContain('aria-label="Open NORFAB documentation"');
    expect(markup).toContain('aria-label="Open NORFAB GitHub repository"');
    expect(markup).toContain('target="_blank"');
  });

  it("omits disabled links and an empty message", () => {
    const markup = renderToStaticMarkup(
      <MantineProvider>
        <AppFooter
          config={{
            message: "",
            fastapi_url: null,
            docs_url: null,
            github_url: null,
          }}
        />
      </MantineProvider>,
    );

    expect(markup).not.toContain("<a");
    expect(markup).not.toContain("<p");
  });
});
