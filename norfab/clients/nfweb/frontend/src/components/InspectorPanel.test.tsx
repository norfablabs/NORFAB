import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { DetailRows } from "./InspectorPanel";

describe("DetailRows", () => {
  it("renders list values as readable comma-separated text", () => {
    const markup = renderToStaticMarkup(
      <DetailRows value={{ layers: ["bgp", "lldp"] }} />,
    );

    expect(markup).toContain("bgp, lldp");
    expect(markup).not.toContain('[&quot;bgp&quot;,&quot;lldp&quot;]');
  });

  it("omits empty property values", () => {
    const markup = renderToStaticMarkup(
      <DetailRows value={{ site: "dc1", description: "", address: null }} />,
    );

    expect(markup).toContain("dc1");
    expect(markup).not.toContain("description");
    expect(markup).not.toContain("address");
  });
});
