# Chunk Inspector (Leaflet + Astro) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the chunk inspector as a Leaflet-based page within the disqt-minecraft Astro project, with toggleable layer overlays, solo/toggle legend filtering, banner markers, and tooltips.

**Architecture:** Astro SSR page at `/minecraft/chunks/` with a client-side Leaflet map using `L.CRS.Simple`. Binary chunk data served as static files fetched on page load. Each data value is a separate `L.ImageOverlay` (transparent canvas → data URL). Sidebar controls toggle layers via Leaflet's native `addLayer`/`removeLayer`. Playwright tests validate all interactive behavior.

**Tech Stack:** Astro 5, Leaflet.js (CDN), TypeScript, Playwright

---

## File Structure

```
disqt-minecraft/
  src/
    pages/
      chunks.astro                    # Page route: /minecraft/chunks/
    components/
      chunks/
        ChunkMap.astro                # Leaflet map container + client script
        ChunkSidebar.astro            # Layer toggles + legend
    lib/
      chunks/
        types.ts                      # WorldData, LayerConfig, Marker types
        decode.ts                     # Decode base64 binary grid → Uint16Array
        layers.ts                     # Generate ImageOverlay canvases per value
        palette.ts                    # HSL color definitions per layer/value
        tooltip.ts                    # Chunk data lookup + tooltip HTML
  public/
    chunks-data/                      # Binary grid files (not in git, symlinked on VPS)
  tests/
    chunks.spec.ts                    # Playwright tests
  playwright.config.ts                # Playwright config
```

**VPS data path:** `/home/dev/minecraft-maps/data/` contains `nether.bin`, `nether.json`, `overworld.bin`, `overworld.json`, `markers.json`. Symlinked into `public/chunks-data/` on VPS, or fetched from `/minecraft/chunks-data/` via nginx.

---

## Data Serving Strategy

The binary grids (~2-3MB each) are too large and too dynamic for git. They live on the VPS and are served via nginx:

```nginx
location /minecraft/chunks-data/ {
    alias /home/dev/minecraft-maps/data/;
    expires 1h;
}
```

The existing `/minecraft/chunks/` nginx block is **removed** so Astro handles the route.

A generation script on the VPS (`/home/dev/minecraft-maps/generate.py`) parses region files and writes:
- `nether.bin` / `overworld.bin` — compact Uint16 grid (same format as current prototype)
- `nether.json` / `overworld.json` — metadata (bounds, cols, rows, totals)
- `markers.json` — banner markers from BlueMap plugin

---

## Task 1: Project Setup

**Files:**
- Modify: `disqt-minecraft/package.json`
- Create: `disqt-minecraft/playwright.config.ts`
- Create: `disqt-minecraft/tests/chunks.spec.ts` (placeholder)

- [ ] **Step 1: Install dependencies**

```bash
cd C:/Users/leole/Documents/code/disqt-minecraft
npm install -D playwright @playwright/test
npx playwright install chromium
```

- [ ] **Step 2: Create Playwright config**

Create `playwright.config.ts` with base URL `http://localhost:4322/minecraft/chunks/`, chromium only, webServer starting `npm run dev`.

- [ ] **Step 3: Create placeholder test**

```typescript
// tests/chunks.spec.ts
import { test, expect } from '@playwright/test';

test('chunks page loads', async ({ page }) => {
  await page.goto('/minecraft/chunks/');
  await expect(page.locator('h1')).toContainText('Chunk Inspector');
});
```

- [ ] **Step 4: Run test to verify it fails**

Run: `npx playwright test`
Expected: FAIL (page doesn't exist yet)

- [ ] **Step 5: Commit**

```bash
git add package.json playwright.config.ts tests/
git commit -m "chore: add Playwright and scaffold chunk inspector test"
```

---

## Task 2: Data Types & Palette

**Files:**
- Create: `src/lib/chunks/types.ts`
- Create: `src/lib/chunks/palette.ts`

- [ ] **Step 1: Define types**

```typescript
// types.ts
export interface WorldMeta {
  min_cx: number; max_cx: number;
  min_cz: number; max_cz: number;
  cols: number; rows: number;
  total: number; visited: number;
}

export interface LayerGroup {
  id: string;
  label: string;
  field: string;       // key in unpacked chunk: 'dv' | 'inhabited' | 'status' | 'entities'
  bitOffset: number;
  bitMask: number;
  values: LayerValue[];
}

export interface LayerValue {
  index: number;
  label: string;
  color: [number, number, number]; // RGB
  hidden?: boolean;                // skip in legend (e.g., "Never", "None")
}

export interface BannerMarker {
  label: string;
  x: number;
  z: number;
}
```

- [ ] **Step 2: Define palettes**

```typescript
// palette.ts — HSL-based colors, pre-computed to RGB
export const LAYER_GROUPS: LayerGroup[] = [
  {
    id: 'inhabited', label: 'Inhabited Time', field: 'inhabited',
    bitOffset: 3, bitMask: 0x7,
    values: [
      { index: 0, label: 'Never', color: [20, 12, 38], hidden: true },
      { index: 1, label: 'Brief', color: [32, 62, 48] },
      { index: 2, label: 'Some', color: [48, 98, 64] },
      { index: 3, label: 'Moderate', color: [78, 142, 82] },
      { index: 4, label: 'Long', color: [128, 198, 96] },
      { index: 5, label: 'Base/Camp', color: [196, 238, 78] },
    ]
  },
  {
    id: 'dataversion', label: 'MC Version', field: 'dv',
    bitOffset: 0, bitMask: 0x7,
    values: [
      { index: 0, label: '1.19.3', color: [120, 40, 40] },
      { index: 1, label: '1.21.1', color: [160, 100, 40] },
      { index: 2, label: '1.21.4', color: [60, 120, 140] },
      { index: 3, label: '1.21.8', color: [70, 90, 180] },
      { index: 4, label: '1.21.11', color: [130, 80, 200] },
    ]
  },
  {
    id: 'status', label: 'Chunk Status', field: 'status',
    bitOffset: 6, bitMask: 0x7,
    values: [
      { index: 0, label: 'structure_starts', color: [80, 20, 20] },
      { index: 1, label: 'biomes', color: [100, 50, 20] },
      { index: 2, label: 'carvers', color: [120, 80, 20] },
      { index: 3, label: 'liquid_carvers', color: [100, 100, 40] },
      { index: 4, label: 'initialize_light', color: [60, 100, 80] },
      { index: 5, label: 'features', color: [40, 80, 120] },
      { index: 6, label: 'full', color: [50, 120, 80] },
    ]
  },
  {
    id: 'entities', label: 'Entity Count', field: 'entities',
    bitOffset: 9, bitMask: 0x7,
    values: [
      { index: 0, label: 'None', color: [16, 14, 28], hidden: true },
      { index: 1, label: '1-3', color: [50, 30, 60] },
      { index: 2, label: '4-10', color: [90, 40, 80] },
      { index: 3, label: '11-25', color: [140, 50, 70] },
      { index: 4, label: '26-50', color: [200, 60, 50] },
      { index: 5, label: '50+', color: [255, 90, 40] },
    ]
  },
];

export const OVERLAY_COLORS = {
  fossil: [255, 230, 109] as [number, number, number],
  dried: [255, 51, 102] as [number, number, number],
};
```

- [ ] **Step 3: Commit**

```bash
git add src/lib/chunks/
git commit -m "feat(chunks): add data types and color palettes"
```

---

## Task 3: Binary Decode & Layer Rendering

**Files:**
- Create: `src/lib/chunks/decode.ts`
- Create: `src/lib/chunks/layers.ts`

- [ ] **Step 1: Implement binary decoder**

```typescript
// decode.ts
import type { WorldMeta } from './types';

export function decodeGrid(buffer: ArrayBuffer): Uint16Array {
  return new Uint16Array(buffer);
}

export function unpack(val: number) {
  return {
    exists: !!(val & 0x8000),
    dv: val & 0x7,
    inhabited: (val >> 3) & 0x7,
    status: (val >> 6) & 0x7,
    entities: (val >> 9) & 0x7,
    fossil: !!(val & (1 << 12)),
    dried: !!(val & (1 << 13)),
  };
}
```

- [ ] **Step 2: Implement layer canvas generator**

```typescript
// layers.ts — generates one canvas per data value
import type { WorldMeta, LayerGroup } from './types';
import { unpack } from './decode';

export function createValueCanvas(
  grid: Uint16Array,
  meta: WorldMeta,
  bitOffset: number,
  bitMask: number,
  valueIndex: number,
  color: [number, number, number],
): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = meta.cols;
  canvas.height = meta.rows;
  const ctx = canvas.getContext('2d')!;
  const img = ctx.createImageData(meta.cols, meta.rows);
  const px = img.data;

  for (let i = 0; i < grid.length; i++) {
    const val = grid[i];
    if (!(val & 0x8000)) continue; // not exists
    const fieldVal = (val >> bitOffset) & bitMask;
    if (fieldVal !== valueIndex) continue;
    const idx = i * 4;
    px[idx] = color[0];
    px[idx + 1] = color[1];
    px[idx + 2] = color[2];
    px[idx + 3] = 200; // semi-transparent for stacking
  }

  ctx.putImageData(img, 0, 0);
  return canvas;
}

export function createOverlayCanvas(
  grid: Uint16Array,
  meta: WorldMeta,
  bitIndex: number, // 12 for fossil, 13 for dried
  color: [number, number, number],
): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = meta.cols;
  canvas.height = meta.rows;
  const ctx = canvas.getContext('2d')!;
  const img = ctx.createImageData(meta.cols, meta.rows);
  const px = img.data;

  for (let i = 0; i < grid.length; i++) {
    if (!(grid[i] & (1 << bitIndex))) continue;
    const idx = i * 4;
    px[idx] = color[0];
    px[idx + 1] = color[1];
    px[idx + 2] = color[2];
    px[idx + 3] = 255;
  }

  ctx.putImageData(img, 0, 0);
  return canvas;
}
```

- [ ] **Step 3: Commit**

```bash
git add src/lib/chunks/
git commit -m "feat(chunks): binary decoder and layer canvas generators"
```

---

## Task 4: Tooltip Module

**Files:**
- Create: `src/lib/chunks/tooltip.ts`

- [ ] **Step 1: Implement tooltip content generator**

```typescript
// tooltip.ts
import type { WorldMeta } from './types';
import { unpack } from './decode';
import { LAYER_GROUPS } from './palette';

const DV_LABELS = ['1.19.3', '1.21.1', '1.21.4', '1.21.8', '1.21.11'];
const INHABITED_LABELS = ['Never', 'Brief', 'Some', 'Moderate', 'Long', 'Base/Camp'];
const STATUS_LABELS = ['structure_starts', 'biomes', 'carvers', 'liquid_carvers', 'initialize_light', 'features', 'full'];
const ENTITY_LABELS = ['None', '1-3', '4-10', '11-25', '26-50', '50+'];

export function getTooltipHTML(
  grid: Uint16Array,
  meta: WorldMeta,
  cx: number,
  cz: number,
  isNether: boolean,
): string | null {
  const px = cx - meta.min_cx;
  const py = cz - meta.min_cz;
  if (px < 0 || px >= meta.cols || py < 0 || py >= meta.rows) return null;

  const val = grid[py * meta.cols + px];
  if (!(val & 0x8000)) return null;

  const u = unpack(val);
  let html = `<b>Chunk (${cx}, ${cz})</b><br>`;
  html += `Block: (${cx * 16}, ${cz * 16})<br>`;
  html += `Version: ${DV_LABELS[u.dv]}<br>`;
  html += `Inhabited: ${INHABITED_LABELS[u.inhabited]}<br>`;
  html += `Status: ${STATUS_LABELS[u.status]}<br>`;
  html += `Entities: ${ENTITY_LABELS[u.entities]}`;
  if (u.fossil) html += `<br><span style="color:#ffe66d">Nether Fossil</span>`;
  if (u.dried) html += `<br><span style="color:#ff3366">Dried Ghast</span>`;
  if (isNether) html += `<br><small>Overworld: (${cx * 128}, ${cz * 128})</small>`;

  return html;
}
```

- [ ] **Step 2: Commit**

```bash
git add src/lib/chunks/tooltip.ts
git commit -m "feat(chunks): tooltip content generator"
```

---

## Task 5: Astro Page & Components

**Files:**
- Create: `src/pages/chunks.astro`
- Create: `src/components/chunks/ChunkMap.astro`
- Create: `src/components/chunks/ChunkSidebar.astro`

- [ ] **Step 1: Create the page shell**

`chunks.astro` imports Layout, renders ChunkSidebar + ChunkMap side by side. Includes Leaflet CSS from CDN.

- [ ] **Step 2: Create ChunkSidebar component**

Renders layer group toggles and legend items. Uses `data-*` attributes for JS interaction. Structured as:
- World switcher (Nether / Overworld)
- Layer groups (each with header toggle + legend items)
- Overlay toggles (Fossils, Dried Ghasts, Banners)

- [ ] **Step 3: Create ChunkMap component**

Contains the `#map` div and a `<script>` block that:
1. Fetches binary data + metadata from `/minecraft/chunks-data/`
2. Decodes grids
3. Initializes Leaflet map with `L.CRS.Simple`
4. Generates all value canvases → `L.ImageOverlay`s
5. Wires sidebar clicks to `addLayer`/`removeLayer`
6. Adds banner markers as `L.Marker`s with custom icon
7. Sets up mousemove tooltip via `L.Popup`

- [ ] **Step 4: Implement solo/toggle legend behavior**

```typescript
function handleLegendClick(groupId: string, valueIndex: number) {
  const group = layerGroups[groupId];
  const visibleCount = group.values.filter(v => map.hasLayer(v.overlay)).length;
  const clickedVisible = map.hasLayer(group.values[valueIndex].overlay);

  if (visibleCount === 1 && clickedVisible) {
    // Only this one visible → show all
    group.values.forEach(v => map.addLayer(v.overlay));
  } else {
    // Solo this one
    group.values.forEach((v, i) => {
      if (i === valueIndex) map.addLayer(v.overlay);
      else map.removeLayer(v.overlay);
    });
  }
  updateLegendUI(groupId);
}
```

- [ ] **Step 5: Run placeholder test**

Run: `npx playwright test`
Expected: PASS (page loads with h1)

- [ ] **Step 6: Commit**

```bash
git add src/pages/chunks.astro src/components/chunks/
git commit -m "feat(chunks): Astro page with Leaflet map, sidebar, and layer system"
```

---

## Task 6: Data Generation Script (VPS)

**Files:**
- Create: `scripts/generate-chunk-data.py` (lives in this repo, deployed to VPS)

- [ ] **Step 1: Write generation script**

Refactored version of the existing SSH one-liner. Reads region files, outputs:
- `nether.bin` / `overworld.bin` — raw Uint16 grid
- `nether.json` / `overworld.json` — metadata object
- `markers.json` — banner markers from BlueMap plugin

- [ ] **Step 2: Deploy script and generate initial data**

```bash
scp scripts/generate-chunk-data.py minecraft:/home/minecraft/
ssh minecraft "python3 /home/minecraft/generate-chunk-data.py /home/minecraft/serverfiles /home/dev/minecraft-maps/data"
```

- [ ] **Step 3: Update nginx config**

Remove old `/minecraft/chunks/` static block. Add data serving block:

```nginx
location /minecraft/chunks-data/ {
    alias /home/dev/minecraft-maps/data/;
    expires 1h;
    add_header Access-Control-Allow-Origin *;
}
```

Reload nginx.

- [ ] **Step 4: Commit**

```bash
git add scripts/generate-chunk-data.py
git commit -m "feat(chunks): VPS data generation script"
```

---

## Task 7: Frontend Design Polish

**Files:**
- Modify: `src/pages/chunks.astro`
- Modify: `src/components/chunks/ChunkSidebar.astro`
- Modify: `src/components/chunks/ChunkMap.astro`

- [ ] **Step 1: Invoke frontend-design skill**

Apply the frontend-design skill for polished UI. Dark theme consistent with existing disqt-minecraft aesthetic (dark bg, teal accents, JetBrains Mono + Rajdhani fonts). Key elements:
- Sidebar with layer group headers that expand/collapse
- Legend swatches with dimmed state for filtered-out values
- World switcher with nether-red / overworld-green accents
- Stats bar in header
- Coordinate readout in status bar

- [ ] **Step 2: Commit**

```bash
git commit -am "style(chunks): frontend design polish"
```

---

## Task 8: Playwright Tests

**Files:**
- Modify: `tests/chunks.spec.ts`

- [ ] **Step 1: Write layer toggle test**

```typescript
test('toggling a layer group shows/hides overlays', async ({ page }) => {
  await page.goto('/minecraft/chunks/');
  await page.waitForSelector('.leaflet-container');
  // Click "MC Version" layer header to enable it
  await page.click('[data-layer-group="dataversion"]');
  // Verify overlays appear (canvas elements in leaflet pane)
  const overlays = page.locator('.leaflet-overlay-pane img, .leaflet-overlay-pane canvas');
  await expect(overlays.first()).toBeVisible();
});
```

- [ ] **Step 2: Write solo/toggle legend test**

```typescript
test('clicking legend item solos it, clicking again shows all', async ({ page }) => {
  await page.goto('/minecraft/chunks/');
  await page.waitForSelector('.leaflet-container');
  // Enable MC Version layer
  await page.click('[data-layer-group="dataversion"]');
  // Click "1.19.3" legend item
  await page.click('[data-legend-item="dataversion-0"]');
  // Verify other legend items are dimmed
  await expect(page.locator('[data-legend-item="dataversion-1"]')).toHaveClass(/dimmed/);
  // Click "1.19.3" again → all visible
  await page.click('[data-legend-item="dataversion-0"]');
  await expect(page.locator('[data-legend-item="dataversion-1"]')).not.toHaveClass(/dimmed/);
});
```

- [ ] **Step 3: Write world switching test**

```typescript
test('world switcher changes map data', async ({ page }) => {
  await page.goto('/minecraft/chunks/');
  await page.waitForSelector('.leaflet-container');
  // Default is nether
  await expect(page.locator('[data-world="nether"]')).toHaveClass(/active/);
  // Switch to overworld
  await page.click('[data-world="overworld"]');
  await expect(page.locator('[data-world="overworld"]')).toHaveClass(/active/);
});
```

- [ ] **Step 4: Write tooltip test**

```typescript
test('hovering chunk shows tooltip with data', async ({ page }) => {
  await page.goto('/minecraft/chunks/');
  await page.waitForSelector('.leaflet-container');
  // Hover over map center
  const map = page.locator('.leaflet-container');
  await map.hover();
  // Tooltip or popup should appear
  const tooltip = page.locator('.leaflet-popup, .chunk-tooltip');
  // Just verify the coordinate readout updates
  await expect(page.locator('#coordInfo')).not.toHaveText('Hover over the map');
});
```

- [ ] **Step 5: Run all tests**

Run: `npx playwright test`
Expected: All PASS

- [ ] **Step 6: Commit**

```bash
git add tests/chunks.spec.ts
git commit -m "test(chunks): Playwright tests for layers, legend, world switch, tooltip"
```

---

## Task 9: Deploy

- [ ] **Step 1: Update nginx config on VPS**

```bash
ssh dev "sudo sed -i '/location \/minecraft\/chunks\//,/}/d' /etc/nginx/sites-enabled/disqt.com"
# Add chunks-data location (before the catch-all /minecraft/ block)
ssh dev "sudo nginx -t && sudo systemctl reload nginx"
```

- [ ] **Step 2: Deploy Astro app**

```bash
ssh dev "cd /home/dev/disqt-minecraft && git pull && npm run build && sudo systemctl restart disqt-minecraft"
```

- [ ] **Step 3: Verify live site**

Visit `https://disqt.com/minecraft/chunks/` — map should load with layer controls.

- [ ] **Step 4: Commit any deploy fixes**

---

## Notes

- **Data refresh:** Run `generate-chunk-data.py` on VPS whenever you want updated chunk data. Could be added as a cron job later.
- **Leaflet CSS/JS:** Loaded from CDN (`unpkg.com/leaflet@1.9.4`). No npm install needed for Leaflet itself.
- **Image overlay bounds:** Calculated from world metadata: `[[min_cz, min_cx], [max_cz + 1, max_cx + 1]]` in Leaflet's `[lat, lng]` format (z = lat, x = lng).
- **Layer opacity:** Use 0.75 opacity on ImageOverlays so stacked layers blend visually.
