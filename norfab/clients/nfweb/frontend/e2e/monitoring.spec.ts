import { expect, test } from "@playwright/test";
import type { MonitoringComponent, MonitoringSnapshot } from "../src/types";

function component(name: string, role: MonitoringComponent["role"]): MonitoringComponent {
  return {
    id: name, name, role, status: role === "worker" ? "alive" : "active",
    service: role === "worker" ? "nornir" : null,
    cpu_percent: 3, memory_mbyte: 100, uptime_seconds: 3600,
    holdtime_seconds: null, keepalives_sent: 10, keepalives_received: 10,
    messages_sent: 10, messages_received: 10, reconnects: 0, queue_depth: 0,
    worker_count: 12, service_count: 2,
  };
}

const history: MonitoringSnapshot[] = Array.from({ length: 12 }, (_, index) => ({
  collected_at: new Date(Date.UTC(2026, 9, 20, 10, index)).toISOString(),
  duration_ms: 150, status: "complete",
  broker: component("broker", "broker"), client: component("nfweb", "client"),
  workers: Array.from({ length: 12 }, (_, worker) => ({
    ...component(`nornir-worker-${worker + 1}`, "worker"),
    cpu_percent: worker + index, memory_mbyte: 100 + worker * 10 + index,
  })),
  database: {
    total_jobs: 25 + index, jobs_last_24h: 12, total_events: 35,
    avg_completion_seconds: 2, oldest_job_ts: null, newest_job_ts: null,
    jobs_by_status: { COMPLETED: 20 + index, FAILED: 5 },
    jobs_by_service: { nornir: 25 + index }, events_by_severity: { INFO: 35 },
  },
  errors: [],
}));
const snapshot = history.at(-1)!;

test.beforeEach(async ({ page }) => {
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let body: unknown;
    if (path === "/api/v1/config") body = { footer: { message: "Monitoring E2E", fastapi_url: null, docs_url: null, github_url: null } };
    else if (path === "/api/v1/topology/devices") body = { devices: [], selected: [], errors: [] };
    else if (path === "/api/v1/topology/history" || path === "/api/v1/topology/logs") body = [];
    else if (path === "/api/v1/monitoring/history") body = history;
    else if (path === "/api/v1/monitoring/snapshot" || path === "/api/v1/monitoring/refresh") body = snapshot;
    else if (path.endsWith("/database")) body = { worker: "nornir-worker-1", service: "nornir", returned_jobs: 5, window_limit: 1000, potentially_truncated: false, oldest_job_ts: null, newest_job_ts: null, jobs_by_status: { COMPLETED: 5 }, jobs_by_task: { cli: 5 } };
    else throw new Error(`Unexpected browser request: ${path}`);
    await route.fulfill({ json: body });
  });
  await page.routeWebSocket("**/api/v1/monitoring/stream", (socket) => {
    socket.send(JSON.stringify({ type: "snapshot", data: snapshot }));
  });
  await page.routeWebSocket("**/api/v1/topology/stream", () => {});
});

test("keeps all monitoring charts readable and reachable at desktop and mobile sizes", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => { if (message.type() === "error") errors.push(message.text()); });
  for (const [width, height] of [[1440, 900], [1366, 768], [1024, 768], [390, 844]]) {
    await page.setViewportSize({ width, height });
    await page.goto("/#monitoring");
    await expect(page.locator(".echarts-for-react canvas")).toHaveCount(7);
    await expect(page).toHaveTitle("NORFAB NFWeb - Monitoring");
    const sizes = await page.evaluate(() => {
      const dashboard = document.querySelector(".monitoring-dashboard")!;
      return {
        overflow: dashboard.scrollWidth - dashboard.clientWidth,
        pageOverflow: document.body.scrollWidth - innerWidth,
        charts: [...document.querySelectorAll(".echarts-for-react")].map((chart) => {
          const bounds = chart.getBoundingClientRect();
          const card = chart.closest(".mantine-Card-root")!.getBoundingClientRect();
          return { height: bounds.height, bottom: bounds.bottom, cardBottom: card.bottom };
        }),
      };
    });
    expect(sizes.overflow).toBeLessThanOrEqual(1);
    expect(sizes.pageOverflow).toBeLessThanOrEqual(1);
    for (const chart of sizes.charts) {
      expect(chart.height).toBeGreaterThanOrEqual(134);
      expect(chart.bottom).toBeLessThanOrEqual(chart.cardBottom);
    }
    await page.locator(".monitoring-dashboard").evaluate((element) => { element.scrollTop = 0; });
    await expect(page.getByRole("button", { name: "Refresh", exact: true })).toBeInViewport();
    if (process.env.NFWEB_CAPTURE === "true") {
      await page.screenshot({ path: `test-results/monitoring-${width}.png` });
    }
    await page.locator(".monitoring-worker-db-card").scrollIntoViewIfNeeded();
    await expect(page.getByText("jobs returned", { exact: true })).toBeInViewport();
  }
  expect(errors).toEqual([]);
});

test("refreshes the selected worker database without changing selection", async ({ page }) => {
  await page.goto("/#monitoring");
  const jobs = page.locator(".monitoring-worker-db-metric").filter({ hasText: "jobs returned" });
  await expect(jobs.locator("b")).toHaveText("5");
  await page.route("**/api/v1/monitoring/workers/*/database", (route) => route.fulfill({ json: {
    worker: "nornir-worker-1", service: "nornir", returned_jobs: 9,
    window_limit: 1000, potentially_truncated: false,
    oldest_job_ts: null, newest_job_ts: null,
    jobs_by_status: { COMPLETED: 9 }, jobs_by_task: { cli: 9 },
  } }));
  await page.getByRole("button", { name: "Refresh", exact: true }).click();
  await expect(jobs.locator("b")).toHaveText("9");
  await expect(page.getByText(/Recent worker jobs · updated/)).toBeVisible();
});

test("switches applications through the mobile sidebar button", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/#monitoring");
  const navigation = page.getByRole("complementary", { name: "NFWeb applications" });
  const toggle = page.getByRole("button", { name: "Toggle applications" });
  await expect(navigation).toBeHidden();
  await toggle.click();
  await expect(navigation).toBeVisible();
  await expect(toggle).toHaveAttribute("aria-expanded", "true");
  await page.getByRole("link", { name: "Topology", exact: true }).click();
  await expect(page).toHaveTitle("NORFAB NFWeb - Topology");
  await expect(navigation).toBeHidden();
  await expect(toggle).toHaveAttribute("aria-expanded", "false");
  await toggle.focus();
  await page.keyboard.press("Enter");
  await page.getByRole("link", { name: "Monitoring", exact: true }).click();
  await expect(page.locator(".echarts-for-react canvas")).toHaveCount(7);
  await expect(navigation).toBeHidden();
});
