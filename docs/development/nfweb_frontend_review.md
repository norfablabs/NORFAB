# NFWeb frontend review and refinement plan

**Review date:** 20 October 2026  
**Status:** Targeted implementation completed; broader proposals below remain a review backlog.

## Iterative implementation scope

The implementation preserves the existing sidebar, Dashboards hierarchy, toolbar,
80/20 topology/inspector split, and file structure, as requested. It applies:

- neutral Mantine/CSS/chart surfaces, orange branding, the existing NORFAB logo,
  consistent small card radii, and larger chart/log labels;
- vertical Monitoring scrolling without chart shrinkage, wrapping mobile controls,
  and a keyboard/touch sidebar button;
- removal of disabled Overview/Admin entries and the confirmed unused CSS/map entries;
- modular ECharts imports, bloom off by default without allocating its pass while off,
  and active-application browser titles;
- selected-worker job-count reloads on manual Refresh, a retrieval timestamp, and
  explicit fabric-wide job activity wording;
- regenerated production assets and browser coverage for all seven charts at four
  viewport sizes, mobile navigation, and worker database refresh.

The header navigation replacement, collapsible inspector/new Events panel, toolbar
regrouping, application subscription restructuring, polling/recovery changes, and
selective Mantine CSS imports are deferred to keep this change surgical. Existing
collection behavior, view state handling, and public interfaces are retained.

The production Monitoring chunk is approximately 623 kB, compared with 1,162 kB
before this change (about 46% smaller). All 26 frontend unit tests and all six
browser tests pass, including a run against the generated production bundle. The
production build, 21 focused Python server/contract tests, and documentation build
also pass. The full Python NFWeb suite has 43 passes and five existing monitoring-fixture failures
because `process.threads` is required but absent from those fixtures; no Python
implementation or fixtures are changed here.

The remaining sections preserve the original audit evidence and proposals; they
are not a claim that every proposed change was implemented.

## Recommendation

Keep React, Mantine, Tabler, ECharts, and the existing 3D topology renderer.
Simplify the shell, align its visual identity with NORFAB, fix content clipping,
and reduce unnecessary loading and updates. A framework replacement would add
work and regression risk without addressing the demonstrated problems.

Design direction: a compact network operations console with neutral charcoal
surfaces, readable data, and restrained orange branding. Preserve the existing
Monitoring and Topology applications, hash links, operational controls, and
public Python/browser contracts.

## Evidence and limits

Reviewed the frontend source, dependency manifests, packaged assets, relevant
Python routes and collectors, repository development guides, the
[NORFAB GitHub page](https://github.com/norfablabs/NORFAB), and the local
`docs/images/logo.jpg` used by both README and MkDocs.

Validation completed:

- Installed the pinned frontend dependencies with `npm ci --ignore-scripts`.
- All 26 frontend unit tests passed.
- All three existing Chromium E2E tests passed.
- Type checking passed, including an additional run with `noUnusedLocals` and
  `noUnusedParameters`.
- Built an isolated production baseline without overwriting `nfweb/static`.
- Inspected the topology E2E screenshot at 1440 × 900.
- Rendered Monitoring with explicit synthetic data for 12 workers at
  1440 × 900, 1366 × 768, 1024 × 768, and 390 × 844; inspected desktop and mobile
  screenshots and measured DOM geometry.
- Built and browser-smoke-tested an isolated modular ECharts experiment.

Local scripts, experimental builds, and Monitoring screenshots are under
`__norfab__/nfweb-review/` and are intentionally ignored by Git. The topology
capture is `norfab/clients/nfweb/frontend/test-results/nfweb-refined.png`.

The fixtures are review data, not observations from the user's fabric. No live
broker, network devices, or Netbox records were changed. Existing tests cover
Topology interactions, not the full Monitoring application. GPU timing,
large-topology behavior, long-session memory, and full accessibility conformance
were not measured. Bundle savings are measured; runtime speedups remain
unproven until profiled.

## Findings

| Priority | Finding and evidence | Proposed change | Proof required before merging |
| --- | --- | --- | --- |
| High | Monitoring charts are squeezed and clipped at 1366 × 768. The screenshot shows overlapping worker labels and truncated lower charts. `styles.css` gives the dashboard stack `height: 100%`, while cards can shrink and hide overflow. | Allow vertical scrolling at every desktop width; prevent chart sections shrinking below their readable height. Adapt columns to available content width. | All axes and ten worker labels remain readable at 1366 × 768 and 1024 × 768; every section is reachable by scrolling. |
| High | The shell reserves 264 px for two real application links. `ApplicationNavigation.tsx` also renders disabled Overview and Admin entries and an expandable Dashboards wrapper. At 1440 px, the empty inspector reserves another ~235 px. The toolbar already scrolls horizontally. | Move the two applications into compact header navigation. Remove disabled destinations and the unnecessary navigation hierarchy. Open the inspector on selection; provide an explicit persistent Events control independently of selection. | Preserve `#monitoring` and `#topology`, keyboard navigation, selection details, history, and access to collection failures with no selection. |
| High | At 390 px, Monitoring's content is 444 px wide. Navigation is positioned at x = -213 with only a 7 px strip exposed, relying on hover or focus to reveal it. | Keep application navigation visible or provide a labelled menu button. Wrap essential controls; place secondary controls in a Mantine menu/popover. | Touch and keyboard users can switch applications and reach Refresh; no page-wide horizontal overflow. |
| High | Full ECharts is imported through `echarts-for-react`. The installed wrapper's default entry imports the complete `echarts` module. | Use the wrapper's ESM core entry with explicit chart/component registration. | Production build, type checking, all seven charts, legends, tooltips, synchronized worker zoom, time zoom, resize, and error-free mount/unmount. |
| Medium | Opening Monitoring still requests topology history, devices, and logs and opens the topology stream. This is in the unconditional initialization effect in `App.tsx`; production browser requests confirmed the three HTTP calls. | Separate application-specific lifecycle work from the shared shell. Subscribe and calculate only for the active view, with a defined resynchronization path when returning. | Monitoring-only startup performs no topology requests or WebSocket connection. Switching back restores device scope, selected history/live mode, filters, and current data without duplicate subscriptions. |
| Medium | Monitoring receives WebSocket snapshots and also fetches the latest snapshot every five seconds by default. The Python collector already publishes completed samples. | Define one primary update path. Prefer push while healthy, with bounded polling/reconciliation for disconnection or stale streams. Reconsider the interval control's wording accordingly. | Count requests during a healthy minute, disconnect/reconnect, and a silent/stale stream. Prove recovery before removing unconditional polling. |
| Medium | Branding is a teal `N` avatar and teal custom favicon. The actual NORFAB logo uses orange, white, gray, and black. Colors are repeated across Mantine, CSS, chart options, and graph code. | Use the existing brand artwork in an appropriately sized asset and centralize a small theme palette. Separate branding from operational status colors. | Visual comparison with the existing logo; contrast checks for each control state; matching colors in controls, charts, and legend labels. |
| Medium | Bloom defaults to enabled in `App.tsx`; the topology capture shows large neon halos around nodes and labels. | Default bloom off and retain it as an optional display setting. Keep rotation, spacing, size, and layout controls available under Display. | Compare dense and sparse topologies with bloom on/off; measure GPU/frame cost before claiming a performance gain. |
| Medium | Small text is pervasive: terminal lines use 9 px, database labels 9 px, and several chart labels 9–10 px. Decorative grids, card shadows, accent strips, and many rounded containers compete with data. | Use a consistent compact type/spacing scale; increase operational labels and log text. Remove decorative grids, accent strips, and unnecessary shadows. | At 100% zoom, key values and events remain readable; no lost data or new clipping at the target sizes. |
| Medium | Worker database data is fetched only when the selected worker name changes. Monitoring Refresh updates the snapshot but does not reload these statistics. | Define and display freshness for worker database data, with a bounded refresh action or deliberate refresh integration. | The same selected worker can show new job counts without switching away and back; avoid creating a new expensive polling loop. |
| Low | `frontend/index.html` always identifies the application as Network Topology, including while Monitoring is open. Worker DB copy exposes `job_list` implementation terminology. | Use an NFWeb title with active-view context and plain operational labels such as “Recent worker jobs.” | Browser title follows the selected application; wording still explains any truncated result window. |

## Proposed layout

```text
NORFAB logo / NFWeb     Monitoring | Topology                  connection
-----------------------------------------------------------------------
View-specific controls: primary actions visible; secondary settings menu
-----------------------------------------------------------------------
Monitoring: summary strip, charts, worker details in a scrollable page
Topology: full remaining canvas, optional inspector, explicit Events panel
-----------------------------------------------------------------------
Configured footer message and links
```

This removes the permanent sidebar rather than merely narrowing it. A top-level
application selector still scales to additional applications later. Do not add
placeholder navigation for applications that do not exist.

For Topology, keep Devices, Refresh, Search, and collection state immediately
available. Group source/protocol/health/statistics controls under Filters and
rendering controls under Display. Keep historical/live mode visible. Verify
the exact grouping with the current E2E interactions before moving controls.
Collection events must remain accessible even when the inspector is closed.

For Monitoring, retain the existing metrics initially. Reorganize them into
fabric summary, worker comparison, fabric history, and selected-worker details.
Job status activity currently uses the **client database across the fabric**,
despite appearing beside selected-worker trends. Give it a clearly labelled
fabric-wide section rather than implying that worker selection filters it.
Do not remove charts merely because they occupy space.

## Visual direction

The existing logo is the brand reference; GitHub's surrounding interface is not
NORFAB's design system. Proposed starting tokens, subject to rendered contrast
checks:

| Purpose | Direction |
| --- | --- |
| Canvas and page | Neutral charcoal, approximately `#111111` |
| Panels | `#191919`, with subtle `#343434` dividers |
| Primary and secondary text | Near-white `#eeeeee`, muted gray around `#aaaaaa` |
| Brand accent | Orange around `#ff7900`, inspired by the existing artwork |
| Filled orange controls | Near-black labels; verify contrast rather than defaulting to white |
| Status | Distinct success, warning, error, and unknown colors with text/icons |
| Typography | Keep the existing system font stack; tabular numbers for metrics |
| Shape and spacing | Small consistent corner radii and a 4/8/12/16 px spacing scale |

Orange is for active navigation, focus, and primary actions. Do not recolor
healthy nodes or every chart series orange. Maintain distinguishable topology
layers, statuses, and process series. A central palette should reduce accidental
variation without flattening meaningful data distinctions.

Preserve Mantine and Tabler, as required by the developer guide. Do not add a
second component system, external font downloads, animation framework, or new
icon family. Start by refining the existing dark mode; adding a second theme is
separate scope.

## Removal decisions

Confirmed cleanup candidates:

- Disabled Overview and Admin entries; Dashboards expansion state becomes
  unnecessary after flattening the application navigation.
- CSS selector families `toolbar-link-selector`, `layer-color-key`,
  `layer-color-key__segment`, `layer-menu-label`, and
  `layer-menu-label__line`: present in CSS, absent from production TS/TSX, with
  no corresponding dynamic class construction found.
- CSS variables `--panel-raised` and `--quiet`: declarations without consumers.
- `jobStatusColors` entries DISPATCHED, SUBMITTING, and NEW: this local map is
  indexed only by the four `trackedJobStatuses` values. Removing these map
  entries does not remove supported backend statuses.
- Decorative grid backgrounds, summary accent strips, and card shadows:
  these are used presentation, not dead code; removing them is a deliberate
  visual simplification.

Do not delete based on a text search alone:

- `monitoring-job-status-*` and terminal severity/status selectors are generated
  dynamically. In particular, PENDING is a real worker database status.
- `@mantine/hooks` has no direct application import but is an explicit peer
  dependency of the installed `@mantine/core`.
- Three.js is directly used for graph labels, materials, and postprocessing;
  `react-force-graph-3d` provides the required renderer.
- ECharts and its React wrapper are used. Reduce their bundled surface instead
  of removing chart functionality or introducing a custom wrapper.
- Lazy-loaded modules are reachable, and tests/devDependencies do not represent
  shipped application code.
- Generated static assets are required for Python-only production deployment.
  Rebuild them normally; do not prune them by hand.
- `normalizeHistory` accepts legacy string values, while the current API is
  typed as structured history. Treat this as a separate compatibility review,
  not an automatically safe deletion.

No entire production source file or top-level runtime dependency was proven
unused in this review. TypeScript's unused-symbol checks also passed. This does
not establish complete reachability, but it rules out claiming broad dead-code
removal without further evidence.

## Measured bundle experiment

The isolated builds used the pinned dependencies and current source. The
experiment changed imports through a temporary Vite transform, leaving source
and packaged assets untouched.

| Asset | Baseline kB | Modular experiment kB |
| --- | ---: | ---: |
| Shared JavaScript | 486.20 | 486.20 |
| Monitoring JavaScript | 1,161.63 | 622.29 |
| Topology JavaScript | 1,396.43 | 1,396.43 |
| CSS | 242.60 | 242.60 |
| Monitoring gzip, reported by Vite | 384.24 | 207.92 |

Monitoring JavaScript decreased by approximately **46.4%**; total JavaScript
decreased by approximately **17.7%**. Gzip figures describe compressed file size,
not a verified production HTTP transfer configuration.

Registered modules: BarChart, LineChart, GridComponent, TooltipComponent,
LegendComponent, DataZoomComponent, AriaComponent, and CanvasRenderer, using
`echarts/core` and `echarts-for-react/esm/core`.

An initial experiment using `echarts-for-react/lib/core` built successfully but
failed at runtime with an invalid React element type. The ESM entry corrected
that failure. This is why build success alone is insufficient evidence.
The corrected production bundle rendered at all four viewport sizes without
reported page errors. Its single-sample fixture verifies mounting and layout,
not full time-series behavior or all chart interactions.

Mantine's full CSS import is another possible optimization, but no saving was
measured. Defer selective CSS imports until controls, portals, overlays, focus
states, and error paths can be covered. Do not make speculative bundle promises.

## Implementation sequence and acceptance

1. **Fix layout and simplify navigation.** Replace placeholders/sidebar with
   compact application navigation, correct Monitoring shrink/overflow, make
   mobile navigation explicit, and make inspector/events visibility deliberate.
   Update the existing E2E assertions that currently enforce a 264 px sidebar
   and a fixed 80/20 graph/inspector split.
2. **Apply the NORFAB visual system.** Introduce shared tokens, brand artwork,
   readable typography, consistent controls, and restrained graph defaults.
   Remove the confirmed CSS/map leftovers alongside these changes.
3. **Reduce shipped and active work.** Implement modular ECharts; isolate
   application subscriptions and computations; define stream recovery before
   changing polling. Preserve view state deliberately across application switches.
4. **Verify and document.** Rebuild packaged static assets; update the developer
   guide, affected user guides, and relevant feature catalogue wording/date.

Required checks:

- Existing 26 unit tests, TypeScript checks, and three E2E tests continue to pass
  after their intentional layout assertions are updated.
- Add focused browser coverage for Monitoring, application switching, touch and
  keyboard navigation, and inspector/events access with no selected object.
- Cover 1440 × 900, 1366 × 768, 1024 × 768, and 390 × 844; test enough workers
  to exercise the ten-row chart window, long names, errors, empty data, and
  disconnected streams.
- Test chart histories with multiple samples, missing metrics, zoom/legend
  interaction, and repeated mount/unmount. Capture console errors.
- Check large topology behavior using the repository's scale-test guidance:
  measure frame time, memory, and update behavior before asserting performance
  improvement. Include bloom on/off and inactive-view resource use.
- Verify no collection starts with an empty device selection, no filters/history
  regress, and failures remain visible.
- Run focused Python NFWeb tests from `tests/` through Poetry if contracts,
  lifecycle, routes, or packaged-asset expectations change.
- Record comparable before/after build sizes and request counts. No new runtime
  dependencies or CDN assets are needed for this plan.
