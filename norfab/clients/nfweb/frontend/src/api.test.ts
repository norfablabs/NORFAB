import { describe, expect, it } from "vitest";
import { webSocketUrl } from "./api";

describe("webSocketUrl", () => {
  it("uses an encrypted WebSocket for an HTTPS page", () => {
    expect(
      webSocketUrl("/api/v1/monitoring/stream", {
        protocol: "https:",
        host: "fabric.example:9005",
      }),
    ).toBe("wss://fabric.example:9005/api/v1/monitoring/stream");
  });

  it("uses a plain WebSocket for an HTTP page", () => {
    expect(
      webSocketUrl("/api/v1/topology/stream", {
        protocol: "http:",
        host: "127.0.0.1:9005",
      }),
    ).toBe("ws://127.0.0.1:9005/api/v1/topology/stream");
  });
});
