import { chromium } from "playwright";

const workers = Array.from({ length: 12 }, (_, index) => ({
  id: `worker:nornir-worker-${index + 1}`,
  name: `nornir-worker-${index + 1}`,
  role: "worker",
  status: "alive",
  service: "nornir",
  cpu_percent: 8 + index * 4,
  memory_mbyte: 128 + index * 32,
  uptime_seconds: 7200,
  holdtime_seconds: 8,
  keepalives_sent: 120,
  keepalives_received: 120,
  messages_sent: null,
  messages_received: null,
  reconnects: null,
  queue_depth: null,
  worker_count: null,
  service_count: null,
}));
const snapshots = Array.from({ length: 8 }, (_, index) => ({
  collected_at: new Date(Date.UTC(2026, 7, 31, 12, index)).toISOString(),
  duration_ms: 37,
  status: "complete",
  broker: { ...workers[0], id: "broker", name: "NFPBroker", role: "broker", status: "active", worker_count: 12, service_count: 3 },
  client: { ...workers[0], id: "client:nfweb", name: "nfweb", role: "client", status: "active", queue_depth: 0 },
  workers: workers.map((worker) => ({ ...worker, cpu_percent: worker.cpu_percent + index, memory_mbyte: worker.memory_mbyte + index * 2 })),
  database: { total_jobs: 1200 + index * 8, jobs_last_24h: 94, total_events: 3500, avg_completion_seconds: 1.4, oldest_job_ts: null, newest_job_ts: null, jobs_by_status: { COMPLETED: 1100 + index * 5, FAILED: 12 + index, STARTED: 5 + index, STALE: 2 }, jobs_by_service: { nornir: 1200 }, events_by_severity: { INFO: 3490, ERROR: 10 } },
  errors: [],
}));

const browser = await chromium.launch({ channel: "chrome", headless: true });
const page = await browser.newPage({ viewport: { width: 1920, height: 1080 } });
await page.route("**/api/v1/**", async (route) => {
  const path = new URL(route.request().url()).pathname;
  let body;
  if (path === "/api/v1/config") body = { footer: { message: "Visual check", fastapi_url: null, docs_url: null, github_url: null } };
  else if (path === "/api/v1/monitoring/history") body = snapshots;
  else if (path === "/api/v1/monitoring/refresh") body = snapshots.at(-1);
  else if (path.endsWith("/database")) body = { worker: decodeURIComponent(path.split("/").at(-2)), service: "nornir", returned_jobs: 247, window_limit: 1000, potentially_truncated: false, oldest_job_ts: "2026-08-30T10:00:00Z", newest_job_ts: "2026-08-31T12:07:00Z", jobs_by_status: { COMPLETED: 231, PENDING: 16 }, jobs_by_task: { cli: 140, parse: 72, inventory: 35 } };
  else body = { error: `No fixture for ${path}` };
  await route.fulfill({ status: body.error ? 404 : 200, contentType: "application/json", body: JSON.stringify(body) });
});
await page.routeWebSocket("**/api/v1/monitoring/stream", () => {});
await page.goto("http://127.0.0.1:4173/#monitoring");
await page.getByText("nornir-worker-1 job database", { exact: true }).waitFor();
await page.waitForTimeout(700);
await page.screenshot({ path: "test-results/nfweb-worker-db-card.png", fullPage: true });
const layout = await page.evaluate(() => ({
  viewportHeight: window.innerHeight,
  documentHeight: document.documentElement.scrollHeight,
  cardWidth: document.querySelector(".monitoring-worker-db-card")?.getBoundingClientRect().width,
  dashboardWidth: document.querySelector(".monitoring-dashboard-content")?.getBoundingClientRect().width,
}));
if (layout.documentHeight > layout.viewportHeight || layout.cardWidth !== layout.dashboardWidth - 24) {
  throw new Error(`Layout check failed: ${JSON.stringify(layout)}`);
}
await browser.close();
console.log(JSON.stringify(layout));
