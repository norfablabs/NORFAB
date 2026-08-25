import { expect, test, type Page, type Route } from "@playwright/test";

const snapshot = {
  snapshot_id: "e2e-snapshot",
  collected_at: "2026-08-25T10:15:30.000Z",
  duration_ms: 42,
  status: "complete",
  devices: ["leaf-01", "spine-01"],
  layers: ["lldp", "interfaces"],
  nodes: [
    {
      id: "leaf-01",
      label: "leaf-01",
      kind: "device",
      health: "healthy",
      layers: ["lldp"],
      attributes: { role: "leaf", site: "lab" },
    },
    {
      id: "spine-01",
      label: "spine-01",
      kind: "device",
      health: "healthy",
      layers: ["lldp"],
      attributes: { role: "spine", site: "lab" },
    },
  ],
  links: [
    {
      id: "leaf-01--spine-01--lldp",
      source: "leaf-01",
      target: "spine-01",
      layer: "lldp",
      health: "healthy",
      metrics: {},
      attributes: {
        source_interface: "Ethernet1",
        target_interface: "Ethernet1",
      },
    },
  ],
  errors: [],
  events: [
    {
      service: "nornir",
      message: "collected LLDP topology",
      severity: "INFO",
      status: "completed",
      worker: "nornir-worker-1",
      timestamp: "2026-08-25T10:15:30.000Z",
    },
  ],
};

const olderSnapshot = {
  ...snapshot,
  snapshot_id: "e2e-snapshot-old",
  collected_at: "2026-08-25T09:10:00.000Z",
  devices: ["leaf-01"],
  nodes: [
    {
      id: "leaf-01",
      label: "leaf-01",
      kind: "device",
      health: "healthy",
      layers: ["lldp"],
      attributes: { role: "leaf", site: "lab" },
    },
  ],
  links: [],
  events: [
    {
      service: "nornir",
      message: "collected earlier LLDP topology",
      severity: "INFO",
      status: "completed",
      worker: "nornir-worker-1",
      timestamp: "2026-08-25T09:10:00.000Z",
    },
  ],
};

function historyLabel(collectedAt: string): string {
  return new Date(collectedAt).toLocaleString(undefined, {
    month: "short",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

const responses: Record<string, unknown> = {
  "/api/v1/config": {
    footer: {
      message: "NFWeb Playwright environment",
      fastapi_url: "http://127.0.0.1:8000/docs",
      docs_url: "https://docs.norfablabs.com/",
      github_url: "https://github.com/norfablabs/NORFAB",
    },
  },
  "/api/v1/topology/devices": {
    devices: [
      { name: "leaf-01", sources: ["nornir"] },
      { name: "spine-01", sources: ["nornir"] },
    ],
    selected: ["leaf-01", "spine-01"],
    errors: [],
  },
  "/api/v1/topology/history": [
    {
      snapshot_id: olderSnapshot.snapshot_id,
      collected_at: olderSnapshot.collected_at,
    },
    {
      snapshot_id: snapshot.snapshot_id,
      collected_at: snapshot.collected_at,
    },
  ],
  "/api/v1/topology/logs": [],
  [`/api/v1/topology/snapshots/${olderSnapshot.snapshot_id}`]: olderSnapshot,
  [`/api/v1/topology/snapshots/${snapshot.snapshot_id}`]: snapshot,
  "/api/v1/topology/refresh": snapshot,
  "/api/v1/topology/selection": {
    selected: ["leaf-01", "spine-01"],
    snapshot,
  },
};

async function fulfillBrowserApi(route: Route) {
  const path = new URL(route.request().url()).pathname;
  const body = responses[path];
  if (body === undefined) {
    await route.fulfill({
      status: 404,
      contentType: "application/json",
      body: JSON.stringify({ error: `No E2E fixture for ${path}` }),
    });
    return;
  }
  await route.fulfill({
    status: 200,
    contentType: "application/json",
    body: JSON.stringify(body),
  });
}

async function openMockedTopology(page: Page) {
  await page.route("**/api/v1/**", fulfillBrowserApi);
  await page.routeWebSocket("**/api/v1/topology/stream", (socket) => {
    setTimeout(() => {
      socket.send(JSON.stringify({ type: "snapshot", data: snapshot }));
    }, 25);
  });
  await page.goto("/");
  await expect(page.getByText("2 nodes / 1 link", { exact: true })).toBeVisible();
}

test.beforeEach(async ({ page }) => {
  await openMockedTopology(page);
});

test("renders the topology shell, header history, and configured footer", async ({
  page,
}) => {
  await expect(page.getByText("NORFAB", { exact: true })).toBeVisible();
  if (process.env.NFWEB_CAPTURE === "true") {
    await page.waitForTimeout(1_200);
    await page.screenshot({
      path: "test-results/nfweb-refined.png",
      fullPage: true,
    });
  }
  const dashboards = page.getByRole("button", { name: "Dashboards" });
  const topologyLink = page.getByRole("link", { name: "Topology" });
  await expect(dashboards).toBeVisible();
  await expect(topologyLink).toBeVisible();
  await dashboards.click();
  await expect(topologyLink).toBeHidden();
  await dashboards.click();
  await expect(topologyLink).toBeVisible();
  await expect(
    page.getByRole("region", { name: "Topology history controls" }),
  ).toBeVisible();
  await expect(page.getByRole("button", { name: "Interfaces" })).toHaveCount(0);
  await expect(page.getByText("NFWeb Playwright environment")).toBeVisible();
  await expect(
    page.getByRole("link", { name: "Open NORFAB documentation" }),
  ).toHaveAttribute("href", "https://docs.norfablabs.com/");
  await expect(
    page.getByRole("link", { name: "Open NORFAB GitHub repository" }),
  ).toHaveAttribute("href", "https://github.com/norfablabs/NORFAB");

  const navigation = await page.locator(".control-panel").boundingBox();
  const graph = await page.locator(".graph-stage").boundingBox();
  const details = await page.locator(".detail-panel").boundingBox();
  const history = await page
    .getByRole("region", { name: "Topology history controls" })
    .boundingBox();

  expect(navigation).not.toBeNull();
  expect(graph).not.toBeNull();
  expect(details).not.toBeNull();
  expect(history).not.toBeNull();
  expect(navigation!.width).toBeCloseTo(264, 0);
  expect(graph!.width / (graph!.width + details!.width)).toBeCloseTo(0.8, 1);
  expect(details!.y).toBeCloseTo(0, 0);
  expect(details!.height).toBeGreaterThan(graph!.height);
  expect(history!.y).toBeLessThan(graph!.y);
});

test("uses working Mantine toolbar controls", async ({ page }) => {
  const deviceSelector = page.getByRole("button", {
    name: "Select topology devices",
  });
  await expect(deviceSelector).toContainText("2 selected");
  await deviceSelector.click();
  await expect(page.getByText("2 discovered", { exact: true })).toBeVisible();
  const deviceFilter = page.getByRole("textbox", {
    name: "Filter topology devices",
  });
  await expect(deviceFilter).toBeVisible();
  await deviceFilter.fill("leaf");
  await expect(
    page.getByRole("menuitemcheckbox", { name: "Select leaf-01" }),
  ).toBeVisible();
  await expect(
    page.getByRole("menuitemcheckbox", { name: "Select spine-01" }),
  ).toHaveCount(0);
  await page.getByRole("button", { name: "Clear device filter" }).click();
  await expect(deviceFilter).toHaveValue("");

  const leafDevice = page.getByRole("menuitemcheckbox", {
    name: "Select leaf-01",
  });
  const spineDevice = page.getByRole("menuitemcheckbox", {
    name: "Select spine-01",
  });
  await expect(leafDevice).toHaveAttribute("aria-checked", "true");
  await expect(spineDevice).toHaveAttribute("aria-checked", "true");
  await page.getByRole("menuitem", { name: "Clear selection" }).click();
  await expect(leafDevice).toHaveAttribute("aria-checked", "false");
  await expect(spineDevice).toHaveAttribute("aria-checked", "false");
  await leafDevice.click();
  await expect(
    page.getByRole("menuitem", { name: "Apply device scope" }),
  ).toContainText("Collect 1 device");
  await spineDevice.click();
  await page.getByRole("menuitem", { name: "Apply device scope" }).click();
  await expect(page.getByText("2 discovered", { exact: true })).toBeHidden();

  await expect(page.getByRole("button", { name: "Pause rendering" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Freeze layout" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Enable rotation" })).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Rotation speed" })).toBeVisible();
  const squareToolbarButtons = await Promise.all(
    [
      page.getByRole("button", { name: "Pause rendering" }),
      page.getByRole("button", { name: "Freeze layout" }),
      page.getByRole("button", { name: "Enable rotation" }),
      page.getByRole("button", { name: "Refresh topology" }),
      page.getByRole("button", { name: "Return to live topology" }),
    ].map((button) => button.boundingBox()),
  );
  squareToolbarButtons.forEach((box) => {
    expect(box).not.toBeNull();
    expect(box!.width).toBeCloseTo(32, 0);
    expect(box!.height).toBeCloseTo(32, 0);
  });
  const layoutDistance = page.getByRole("slider", { name: "Layout distance" });
  await expect(layoutDistance).toBeVisible();
  await expect(page.getByRole("radiogroup", { name: "Node size mode" })).toBeVisible();
  await expect(page.getByRole("button", { name: "3D controls" })).toHaveCount(0);

  const lldpLayer = page.getByRole("checkbox", { name: "LLDP layer" });
  const lldpLayerButton = page.getByText("LLDP", { exact: true });
  await expect(lldpLayer).toBeChecked();
  await lldpLayerButton.click();
  await expect(lldpLayer).not.toBeChecked();
  await expect(page.getByText("0 nodes / 0 links", { exact: true })).toBeVisible();
  await lldpLayerButton.click();
  await expect(lldpLayer).toBeChecked();
  await expect(page.getByText("2 nodes / 1 link", { exact: true })).toBeVisible();

  const [topbarBox, distanceBox, nodeSizeBox] = await Promise.all([
    page.locator(".topbar").boundingBox(),
    layoutDistance.boundingBox(),
    page.getByRole("radiogroup", { name: "Node size mode" }).boundingBox(),
  ]);
  expect(topbarBox).not.toBeNull();
  expect(distanceBox).not.toBeNull();
  expect(nodeSizeBox).not.toBeNull();
  expect(distanceBox!.y + distanceBox!.height).toBeLessThanOrEqual(
    topbarBox!.y + topbarBox!.height,
  );
  expect(nodeSizeBox!.y + nodeSizeBox!.height).toBeLessThanOrEqual(
    topbarBox!.y + topbarBox!.height,
  );

  const toolbar = page.getByRole("region", { name: "Topology toolbar" });
  const toolbarMetrics = await toolbar
    .evaluate((element) => {
      const controls = element.querySelector(".topology-controls");
      const itemBottoms = controls
        ? [...controls.children]
            .map((child) => child.getBoundingClientRect())
            .filter((rect) => rect.width > 0 && rect.height > 0)
            .map((rect) => Math.round(rect.bottom))
        : [];
      return {
        clientWidth: element.clientWidth,
        scrollWidth: element.scrollWidth,
        itemBottoms,
      };
    });
  expect(toolbarMetrics.scrollWidth).toBeGreaterThan(toolbarMetrics.clientWidth);
  expect(
    Math.max(...toolbarMetrics.itemBottoms) -
      Math.min(...toolbarMetrics.itemBottoms),
  ).toBeLessThanOrEqual(2);
  const rightScrollPosition = await toolbar.evaluate((element) => {
    element.scrollLeft = element.scrollWidth;
    return element.scrollLeft;
  });
  expect(rightScrollPosition).toBeGreaterThan(0);

  const search = page.getByRole("textbox", { name: "Find infrastructure" });
  await search.fill("not-present");
  await expect(page.getByText("0 nodes / 0 links", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Clear search" }).click();
  await expect(page.getByText("2 nodes / 1 link", { exact: true })).toBeVisible();
});

test("selects a topology snapshot from the history dropdown", async ({ page }) => {
  const toolbar = page.getByRole("region", { name: "Topology toolbar" });
  await toolbar.evaluate((element) => {
    element.scrollLeft = element.scrollWidth;
  });

  await page.getByRole("combobox", { name: "Topology snapshot" }).click();
  await page
    .getByRole("option", { name: historyLabel(olderSnapshot.collected_at) })
    .click();

  await expect(page.getByText("1 node / 0 links", { exact: true })).toBeVisible();
  await expect(page.getByText("Historical", { exact: true })).toBeVisible();
});
