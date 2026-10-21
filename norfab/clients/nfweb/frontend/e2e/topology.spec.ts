import { expect, test, type Page, type Route, type WebSocketRoute } from "@playwright/test";
import type { Mesh, Object3D, PerspectiveCamera, Scene, WebGLRenderer } from "three";

type GraphTestWindow = Window & {
  __THREE_DEVTOOLS__?: EventTarget;
  graphFrame?: { scene: Scene; camera: PerspectiveCamera };
};

const snapshot = {
  snapshot_id: "e2e-snapshot",
  collected_at: "2026-08-25T10:15:30.000Z",
  duration_ms: 42,
  status: "complete",
  devices: ["leaf-01", "spine-01"],
  layers: ["topology", "lldp", "bgp", "interfaces"],
  nodes: [
    {
      id: "leaf-01",
      label: "leaf-01",
      health: "healthy",
      layers: ["topology"],
      origin: ["nornir", "live-lldp"],
      attributes: { role: "leaf", site: "lab" },
    },
    {
      id: "spine-01",
      label: "spine-01",
      health: "healthy",
      layers: ["topology"],
      origin: ["nornir", "live-lldp"],
      attributes: { role: "spine", site: "lab" },
    },
  ],
  links: [
    {
      id: "leaf-01--spine-01--lldp",
      source: "leaf-01",
      target: "spine-01",
      layer: "topology",
      health: "healthy",
      origin: ["live-lldp"],
      metrics: {
        source_rate_bps_out: 2_500_000_000,
        target_rate_bps_out: 850_000_000,
        source_output_utilization: 62,
        target_output_utilization: 24,
      },
      attributes: {
        source_interface: "Ethernet1",
        target_interface: "Ethernet1",
      },
    },
    {
      id: "leaf-01--spine-01--lldp-secondary",
      source: "spine-01",
      target: "leaf-01",
      layer: "topology",
      health: "healthy",
      origin: ["live-lldp"],
      metrics: {
        source_rate_bps_out: 900_000_000,
        target_rate_bps_out: 1_400_000_000,
        source_output_utilization: 27,
        target_output_utilization: 48,
      },
      attributes: {
        source_interface: "Ethernet2",
        target_interface: "Ethernet2",
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
      health: "healthy",
      layers: ["topology"],
      origin: ["nornir", "live-lldp"],
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
  const search = await page.getByRole("textbox", { name: "Find infrastructure" }).boundingBox();
  expect(search).not.toBeNull();
  expect(search!.x).toBeGreaterThan(graph!.x + graph!.width / 2);
  expect(search!.x + search!.width).toBeLessThanOrEqual(details!.x);
  const refresh = await page.getByRole("button", { name: "Refresh topology" }).boundingBox();
  const inspectorHeader = await page.locator(".detail-header").boundingBox();
  expect(search!.y).toBeCloseTo(refresh!.y, 0);
  expect(inspectorHeader!.y + inspectorHeader!.height).toBeCloseTo(graph!.y, 0);
});

test("keeps collection entries on one horizontally scrollable line with severity colors", async ({ page }) => {
  await page.routeWebSocket("**/api/v1/topology/stream", (socket) => {
    socket.send(JSON.stringify({ type: "snapshot", data: snapshot }));
    for (const severity of ["INFO", "WARNING", "ERROR"]) {
      socket.send(JSON.stringify({ type: "log", data: {
        id: `format-${severity}`, snapshot_id: snapshot.snapshot_id,
        collected_at: snapshot.collected_at, timestamp: snapshot.collected_at,
        kind: "event", service: "nornir", worker: "nornir-worker-1",
        severity, status: "running", message: `${severity} collection output with enough detail to wrap inside the inspector`,
      } }));
    }
  });
  await page.reload();
  for (const [severity, color] of [["INFO", "rgb(185, 196, 209)"], ["WARNING", "rgb(255, 212, 59)"], ["ERROR", "rgb(255, 135, 135)"]]) {
    const row = page.locator(".terminal-line").filter({ hasText: `${severity} collection output` });
    await expect(row.locator(".terminal-message")).toHaveCSS("color", color);
    if (severity !== "INFO") await expect(row.locator("time")).toHaveCSS("color", color);
    const time = await row.locator("time").boundingBox();
    const worker = await row.locator(".terminal-worker").boundingBox();
    expect(worker!.y).toBeCloseTo(time!.y, 0);
    const message = await row.locator(".terminal-message").boundingBox();
    expect(message!.y).toBeCloseTo(time!.y, 0);
  }
  expect(await page.locator(".terminal-log").evaluate((element) => element.scrollWidth > element.clientWidth)).toBe(true);
});

test("shows collection progress before selection completes without duplicating the final log", async ({ page }) => {
  let stream!: WebSocketRoute;
  await page.routeWebSocket("**/api/v1/topology/stream", (socket) => {
    stream = socket;
    socket.send(JSON.stringify({ type: "snapshot", data: snapshot }));
  });
  await page.reload();
  await expect(page.getByText("2 nodes / 1 link", { exact: true })).toBeVisible();
  const event = {
    service: "nornir", task: "parse_ttp", severity: "INFO", status: "running",
    message: "collecting output from leaf-01", timestamp: snapshot.collected_at,
  };
  const completed = { ...snapshot, snapshot_id: "progress-snapshot", events: [event] };
  let release!: () => void;
  const pending = new Promise<void>((resolve) => { release = resolve; });
  await page.route("**/api/v1/topology/selection", async (route) => {
    stream.send(JSON.stringify({ type: "log", data: {
      ...event, id: "progress-snapshot:event:0", snapshot_id: "progress-snapshot",
      collected_at: snapshot.collected_at, kind: "event",
    } }));
    await pending;
    stream.send(JSON.stringify({ type: "snapshot", data: completed }));
    await route.fulfill({ json: { selected: snapshot.devices, snapshot: completed } });
  });
  await page.getByRole("button", { name: "Select topology devices" }).click();
  await page.getByRole("menuitem", { name: "Apply device scope" }).click();
  const line = page.locator(".terminal-line").filter({ hasText: event.message });
  await expect(line).toHaveCount(1);
  await expect(page.getByRole("menuitem", { name: "Apply device scope" })).toContainText("Collecting");
  release();
  await expect(page.getByRole("menuitem", { name: "Apply device scope" })).toBeHidden();
  await expect(line).toHaveCount(1);
});

test("uses working Mantine toolbar controls", async ({ page }) => {
  test.setTimeout(60_000);
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
  const bloomToggle = page.getByRole("button", { name: "Enable bloom" });
  await expect(bloomToggle).toBeVisible();
  await bloomToggle.click();
  await expect(page.getByRole("button", { name: "Disable bloom" })).toBeVisible();
  await page.evaluate(() => new Promise<void>((resolve) => {
    requestAnimationFrame(() => requestAnimationFrame(() => resolve()));
  }));
  const bloomImage = await page.locator(".graph-stage canvas").screenshot();
  const darkFraction = await page.evaluate(async (encoded) => {
    const image = new Image();
    image.src = `data:image/png;base64,${encoded}`;
    await image.decode();
    const canvas = document.createElement("canvas");
    canvas.width = image.width;
    canvas.height = image.height;
    const context = canvas.getContext("2d")!;
    context.drawImage(image, 0, 0);
    const { data } = context.getImageData(0, 0, canvas.width, canvas.height);
    let dark = 0;
    for (let index = 0; index < data.length; index += 4) {
      if (Math.max(data[index], data[index + 1], data[index + 2]) < 40) dark++;
    }
    return dark / (canvas.width * canvas.height);
  }, bloomImage.toString("base64"));
  expect(darkFraction).toBeGreaterThan(0.75);
  await page.getByRole("button", { name: "Disable bloom" }).click();
  const rotationSpeed = page.getByRole("button", {
    name: "Select rotation speed, current 1x",
  });
  await expect(rotationSpeed).toBeVisible();
  await expect(page.getByRole("combobox", { name: "Rotation speed" })).toHaveCount(0);
  await rotationSpeed.click();
  await page.getByRole("menuitemradio", { name: "2×" }).click();
  await expect(
    page.getByRole("button", { name: "Select rotation speed, current 2x" }),
  ).toBeVisible();
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

  const healthFilter = page.getByRole("combobox", { name: "Health filter" });
  await healthFilter.click();
  const healthColors = [
    ["Healthy", "rgb(34, 197, 94)"],
    ["Warning", "rgb(250, 204, 21)"],
    ["Critical", "rgb(239, 68, 68)"],
    ["Unknown", "rgb(148, 163, 184)"],
  ] as const;
  for (const [state, color] of healthColors) {
    await expect(
      page.getByRole("option", { name: state }).locator(".health-color-key"),
    ).toHaveCSS("background-color", color);
  }
  await healthFilter.press("Escape");

  const topologySelector = page.getByRole("button", {
    name: "Select topology links",
  });
  const protocolsSelector = page.getByRole("button", {
    name: "Select protocols",
  });
  const statsSelector = page.getByRole("button", {
    name: "Select topology statistics",
  });
  await expect(topologySelector).toHaveText(/Topology/);
  await expect(protocolsSelector).toHaveText(/Protocols/);
  await expect(statsSelector).toHaveText(/Stats/);

  await statsSelector.click();
  const trafficMode = page.getByRole("menuitemradio", { name: "Traffic" });
  await trafficMode.click();
  await expect(trafficMode).toHaveAttribute("aria-checked", "true");
  await expect(page.getByText("2 nodes / 1 link", { exact: true })).toBeVisible();
  await statsSelector.click();

  await topologySelector.click();
  const netboxLayer = page.getByRole("menuitemcheckbox", {
    name: "NetBox links",
  });
  const lldpLayer = page.getByRole("menuitemcheckbox", { name: "LLDP links" });
  await expect(netboxLayer).toHaveAttribute("aria-checked", "true");
  await expect(lldpLayer).toHaveAttribute("aria-checked", "true");
  await lldpLayer.click();
  await expect(lldpLayer).toHaveAttribute("aria-checked", "false");
  await expect(page.getByText("2 nodes / 0 links", { exact: true })).toBeVisible();
  await lldpLayer.click();
  await expect(lldpLayer).toHaveAttribute("aria-checked", "true");
  await expect(page.getByText("2 nodes / 1 link", { exact: true })).toBeVisible();

  await topologySelector.click();
  await protocolsSelector.click();
  const bgpPeerings = page.getByRole("menuitemcheckbox", {
    name: "BGP peerings",
  });
  await expect(bgpPeerings).toHaveAttribute("aria-checked", "true");

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
  await expect(page.getByText("2 nodes / 1 link", { exact: true })).toBeVisible();
  await search.press("Enter");
  await expect(page.getByRole("button", { name: "Disable topology search" })).toBeVisible();
  await expect(page.getByText("2 nodes / 1 link", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Disable topology search" }).click();
  await expect(page.getByRole("button", { name: "Apply topology search" })).toBeVisible();
  await page.getByRole("button", { name: "Apply topology search" }).click();
  await expect(page.getByRole("button", { name: "Disable topology search" })).toBeVisible();
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


test("frames disconnected groups and isolated nodes while preserving user zoom", async ({ page }) => {
  test.setTimeout(60_000);
  // Observe Three.js through its devtools hook without exposing application state.
  await page.addInitScript(() => {
    const target = window as GraphTestWindow;
    target.__THREE_DEVTOOLS__ = new EventTarget();
    target.__THREE_DEVTOOLS__.addEventListener("observe", (event) => {
      const renderer = (event as CustomEvent).detail as WebGLRenderer & { isWebGLRenderer?: boolean };
      if (!renderer.isWebGLRenderer) return;
      const render = renderer.render;
      renderer.render = (scene, camera) => {
        if (camera.type === "PerspectiveCamera") {
          target.graphFrame = { scene: scene as Scene, camera: camera as PerspectiveCamera };
        }
        render.call(renderer, scene, camera);
      };
    });
  });
  const nodes = Array.from({ length: 36 }, (_, index) => ({
    ...snapshot.nodes[0], id: `group-node-${index}`, label: `node-${index}`,
  }));
  const links = Array.from({ length: 24 }, (_, index) => {
    const group = Math.floor(index / 3) * 4;
    const member = index % 3;
    return { ...snapshot.links[0], id: `group-link-${index}`,
      source: nodes[group + member].id, target: nodes[group + member + 1].id };
  });
  await page.routeWebSocket("**/api/v1/topology/stream", (socket) => {
    socket.send(JSON.stringify({ type: "snapshot", data: { ...snapshot, nodes, links } }));
  });
  for (const [width, height] of [[1440, 900], [1024, 768], [390, 844]]) {
    await page.setViewportSize({ width, height });
    await page.reload();
    await expect(page.getByText("36 nodes / 24 links", { exact: true })).toBeVisible();
    const visibleNodes = () => page.evaluate(() => {
      const frame = (window as GraphTestWindow).graphFrame;
      if (!frame) return { count: 0, outside: ["not ready"] };
      const outside: string[] = [];
      let count = 0;
      frame.scene.traverse((object: Object3D & { __graphObjType?: string; __data?: { id: string } }) => {
        if (object.__graphObjType !== "node") return;
        count++;
        const position = object.getWorldPosition(object.position.clone()).project(frame.camera);
        if (Math.abs(position.x) > 0.98 || Math.abs(position.y) > 0.98 || Math.abs(position.z) > 1) {
          outside.push(object.__data?.id ?? "unknown");
        }
        // Check sphere/label bounds as well as node centers.
        object.traverse((child) => {
          const geometry = (child as Mesh).geometry;
          if (!geometry) return;
          geometry.computeBoundingBox();
          const box = geometry.boundingBox!;
          for (const x of [box.min.x, box.max.x]) {
            for (const y of [box.min.y, box.max.y]) {
              for (const z of [box.min.z, box.max.z]) {
                const point = child.position.clone().set(x, y, z).applyMatrix4(child.matrixWorld).project(frame.camera);
                if (Math.abs(point.x) > 1 || Math.abs(point.y) > 1 || Math.abs(point.z) > 1) outside.push("clipped geometry");
              }
            }
          }
        });
      });
      return { count, outside };
    });
    await expect.poll(visibleNodes).toEqual({ count: 36, outside: [] });
    if (width === 1440) {
      const before = await page.evaluate(() => (window as GraphTestWindow).graphFrame!.camera.position.z);
      await page.locator(".graph-stage canvas").hover();
      await page.mouse.wheel(0, -200);
      await expect.poll(() => page.evaluate(() => (window as GraphTestWindow).graphFrame!.camera.position.z)).not.toBe(before);
      const after = await page.evaluate(() => (window as GraphTestWindow).graphFrame!.camera.position.toArray());
      await expect(page.getByRole("button", { name: "Recalculate layout" })).toBeVisible({ timeout: 15_000 });
      const settled = await page.evaluate(() => (window as GraphTestWindow).graphFrame!.camera.position.toArray());
      settled.forEach((coordinate, index) => expect(coordinate).toBeCloseTo(after[index], 5));
    } else {
      await expect(page.getByRole("button", { name: "Recalculate layout" })).toBeVisible({ timeout: 15_000 });
    }
    await expect.poll(visibleNodes).toEqual({ count: 36, outside: [] });
  }
});
