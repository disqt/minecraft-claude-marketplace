# Villagers Dashboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an interactive villager census dashboard at `disqt.com/minecraft/villagers/` that loads the SQLite DB client-side and renders D3 visualizations.

**Architecture:** Standalone Astro page in the `disqt-minecraft` app. Browser fetches the census SQLite DB, opens it with sql.js (WASM), and queries it directly. D3.js renders all visualizations: zone cards with sparklines, 2D position map, alluvial flow diagram, snapshot comparison, and individual villager tracker.

**Tech Stack:** Astro 5 (SSR, `@astrojs/node`), sql.js (SQLite WASM), D3.js v7, d3-sankey

**Spec:** `docs/superpowers/specs/2026-04-04-villagers-dashboard-design.md`

**Existing app:** `/home/leo/documents/code/disqt.com/disqt-minecraft/`
- Base URL: `/minecraft/`, SSR mode, port 4322
- Pattern: standalone `.astro` pages with `<script is:inline>` for client-side JS
- Reference page: `src/pages/chunks.astro` (data-driven viz, same pattern)
- Dark theme CSS vars in `:root`, glassmorphism UI

**Census DB:** `/home/dev/villager-census/census.db` on VPS. Tables: `snapshots`, `villager_states`, `villagers`, `beds`, `villager_trades`, `villager_inventory`, `villager_gossip`, `census_runs`. Zone config: `/home/leo/documents/code/disqt.com/minecraft/villager-census/zones.toml`.

---

## File Structure

```
disqt-minecraft/
  src/pages/
    villagers.astro          # Page shell: HTML structure, CSS, loads JS modules
  src/villagers/
    db.js                    # sql.js init, DB fetch, query helpers
    queries.js               # All SQL queries as functions
    state.js                 # Shared state: current snapshot, active view, selected villager
    zones.js                 # Zone config (embedded JSON from zones.toml)
    views/
      cards.js               # Zone cards with sparklines
      map.js                 # 2D position map with layers + heatmap toggle
      flows.js               # Alluvial/Sankey diagram
      compare.js             # Snapshot comparison
      tracker.js             # Individual villager deep dive
    components/
      slider.js              # Snapshot timeline slider
      tooltip.js             # Shared hover tooltip
      legend.js              # Profession color legend
```

Each view module exports `init(container)` and `update(snapshotId)`. The page shell calls `init` once and `update` when the snapshot slider changes or the view tab switches.

---

### Task 1: Nginx config and DB serving

**Files:**
- Modify: VPS nginx config (via SSH)

This is a one-time infra setup — no tests needed.

- [ ] **Step 1: Add nginx location block**

SSH to the VPS and add the location block for serving the census DB:

```bash
ssh dev "sudo tee /etc/nginx/snippets/minecraft-villagers.conf > /dev/null << 'CONF'
location /minecraft/villagers/census.db {
    alias /home/dev/villager-census/census.db;
    add_header Cache-Control \"public, max-age=1800\";
    add_header Access-Control-Allow-Origin \"*\";
    types { application/octet-stream db; }
}
CONF"
```

Then include it in the server block (check where other minecraft snippets are included) and reload:

```bash
ssh dev "sudo nginx -t && sudo systemctl reload nginx"
```

- [ ] **Step 2: Verify DB is accessible**

```bash
curl -sI https://disqt.com/minecraft/villagers/census.db | head -10
```

Expected: HTTP 200, Content-Type `application/octet-stream`, Cache-Control header present.

- [ ] **Step 3: Commit nginx config note**

No file to commit locally — this is VPS-side config. Document in the spec that it's done.

---

### Task 2: Install dependencies in disqt-minecraft

**Files:**
- Modify: `/home/leo/documents/code/disqt.com/disqt-minecraft/package.json`

- [ ] **Step 1: Install D3, d3-sankey, and sql.js**

```bash
cd /home/leo/documents/code/disqt.com/disqt-minecraft
npm install d3 d3-sankey sql.js
```

- [ ] **Step 2: Verify package.json updated**

```bash
grep -E "d3|sql.js" package.json
```

Expected: `"d3"`, `"d3-sankey"`, `"sql.js"` in dependencies.

- [ ] **Step 3: Commit**

```bash
git add package.json package-lock.json
git commit -m "feat(villagers): add d3, d3-sankey, sql.js dependencies"
```

---

### Task 3: DB module — sql.js init and query helpers

**Files:**
- Create: `src/villagers/db.js`
- Create: `src/villagers/queries.js`

- [ ] **Step 1: Create db.js — sql.js initialization and DB loading**

```js
// src/villagers/db.js
// Loads sql.js WASM, fetches census.db, returns a ready-to-query DB instance.

let _db = null;

export async function initDB() {
  if (_db) return _db;

  const SQL = await window.initSqlJs({
    locateFile: (file) => `https://sql.js.org/dist/${file}`,
  });

  const response = await fetch('/minecraft/villagers/census.db');
  if (!response.ok) throw new Error(`Failed to fetch census.db: ${response.status}`);
  const buf = await response.arrayBuffer();
  _db = new SQL.Database(new Uint8Array(buf));
  return _db;
}

export function query(sql, params = []) {
  if (!_db) throw new Error('DB not initialized — call initDB() first');
  const stmt = _db.prepare(sql);
  stmt.bind(params);
  const rows = [];
  while (stmt.step()) {
    rows.push(stmt.getAsObject());
  }
  stmt.free();
  return rows;
}

export function queryOne(sql, params = []) {
  const rows = query(sql, params);
  return rows.length > 0 ? rows[0] : null;
}
```

- [ ] **Step 2: Create queries.js — all SQL queries as functions**

```js
// src/villagers/queries.js
// Named query functions. Each returns plain JS objects.

import { query, queryOne } from './db.js';

export function getSnapshots() {
  return query(`
    SELECT id, timestamp, villager_count, bed_count, notes,
           zones_scanned, zones_skipped
    FROM snapshots ORDER BY id ASC
  `);
}

export function getLatestSnapshotId() {
  const row = queryOne('SELECT id FROM snapshots ORDER BY id DESC LIMIT 1');
  return row ? row.id : null;
}

export function getZoneStats(snapshotId) {
  return query(`
    SELECT
      zone,
      COUNT(*) as villager_count,
      SUM(CASE WHEN home_x IS NULL THEN 1 ELSE 0 END) as homeless
    FROM villager_states
    WHERE snapshot_id = ? AND zone IS NOT NULL
    GROUP BY zone
  `, [snapshotId]);
}

export function getBedStats(snapshotId) {
  return query(`
    SELECT
      zone,
      COUNT(*) as bed_count,
      SUM(CASE WHEN claimed_by IS NOT NULL THEN 1 ELSE 0 END) as claimed
    FROM beds
    WHERE snapshot_id = ? AND zone IS NOT NULL
    GROUP BY zone
  `, [snapshotId]);
}

export function getZoneTimeSeries() {
  return query(`
    SELECT s.id as snapshot_id, s.timestamp, vs.zone, COUNT(*) as count
    FROM villager_states vs
    JOIN snapshots s ON s.id = vs.snapshot_id
    WHERE vs.zone IS NOT NULL
    GROUP BY s.id, vs.zone
    ORDER BY s.id ASC
  `);
}

export function getProfessionBreakdown(snapshotId) {
  return query(`
    SELECT zone, profession, COUNT(*) as count
    FROM villager_states
    WHERE snapshot_id = ? AND zone IS NOT NULL
    GROUP BY zone, profession
    ORDER BY count DESC
  `, [snapshotId]);
}

export function getVillagerPositions(snapshotId) {
  return query(`
    SELECT
      villager_uuid, pos_x, pos_z, profession, health, zone,
      home_x, home_z, job_site_x, job_site_z,
      meeting_point_x, meeting_point_z
    FROM villager_states
    WHERE snapshot_id = ?
  `, [snapshotId]);
}

export function getBedPositions(snapshotId) {
  return query(`
    SELECT pos_x, pos_z, zone, claimed_by, free_tickets
    FROM beds WHERE snapshot_id = ?
  `, [snapshotId]);
}

export function getMigrationFlows(fromSnapshotId, toSnapshotId) {
  return query(`
    SELECT
      prev.zone AS from_zone,
      curr.zone AS to_zone,
      COUNT(*) AS count
    FROM villager_states curr
    JOIN villager_states prev
      ON curr.villager_uuid = prev.villager_uuid
      AND prev.snapshot_id = ?
      AND curr.snapshot_id = ?
    WHERE prev.zone IS NOT NULL AND curr.zone IS NOT NULL
    GROUP BY prev.zone, curr.zone
  `, [fromSnapshotId, toSnapshotId]);
}

export function getBirths(fromSnapshotId, toSnapshotId) {
  return query(`
    SELECT vs.villager_uuid, vs.profession, vs.zone, vs.pos_x, vs.pos_z
    FROM villager_states vs
    WHERE vs.snapshot_id = ?
      AND vs.villager_uuid NOT IN (
        SELECT villager_uuid FROM villager_states WHERE snapshot_id = ?
      )
  `, [toSnapshotId, fromSnapshotId]);
}

export function getDeaths(fromSnapshotId, toSnapshotId) {
  return query(`
    SELECT vs.villager_uuid, vs.profession, vs.zone, vs.pos_x, vs.pos_z
    FROM villager_states vs
    WHERE vs.snapshot_id = ?
      AND vs.villager_uuid NOT IN (
        SELECT villager_uuid FROM villager_states WHERE snapshot_id = ?
      )
  `, [fromSnapshotId, toSnapshotId]);
}

export function getProfessionChanges(fromSnapshotId, toSnapshotId) {
  return query(`
    SELECT
      prev.villager_uuid,
      prev.profession AS old_profession,
      curr.profession AS new_profession,
      curr.zone
    FROM villager_states curr
    JOIN villager_states prev
      ON curr.villager_uuid = prev.villager_uuid
      AND prev.snapshot_id = ?
      AND curr.snapshot_id = ?
    WHERE prev.profession != curr.profession
  `, [fromSnapshotId, toSnapshotId]);
}

export function getVillagerInfo(uuid) {
  return queryOne(`
    SELECT * FROM villagers WHERE uuid = ?
  `, [uuid]);
}

export function getVillagerHistory(uuid) {
  return query(`
    SELECT vs.*, s.timestamp
    FROM villager_states vs
    JOIN snapshots s ON s.id = vs.snapshot_id
    WHERE vs.villager_uuid = ?
    ORDER BY s.id ASC
  `, [uuid]);
}

export function getVillagerTrades(snapshotId, uuid) {
  return query(`
    SELECT * FROM villager_trades
    WHERE snapshot_id = ? AND villager_uuid = ?
    ORDER BY slot ASC
  `, [snapshotId, uuid]);
}

export function getVillagerInventory(snapshotId, uuid) {
  return query(`
    SELECT * FROM villager_inventory
    WHERE snapshot_id = ? AND villager_uuid = ?
  `, [snapshotId, uuid]);
}

export function getVillagerGossip(snapshotId, uuid) {
  return query(`
    SELECT * FROM villager_gossip
    WHERE snapshot_id = ? AND villager_uuid = ?
  `, [snapshotId, uuid]);
}

export function getAllVillagersList(snapshotId) {
  return query(`
    SELECT vs.villager_uuid, vs.profession, vs.zone, vs.health,
           v.spawn_reason, v.presumed_dead
    FROM villager_states vs
    JOIN villagers v ON v.uuid = vs.villager_uuid
    WHERE vs.snapshot_id = ?
    ORDER BY vs.zone, vs.profession
  `, [snapshotId]);
}
```

- [ ] **Step 3: Commit**

```bash
git add src/villagers/db.js src/villagers/queries.js
git commit -m "feat(villagers): add sql.js DB module and query helpers"
```

---

### Task 4: Shared state and zone config

**Files:**
- Create: `src/villagers/state.js`
- Create: `src/villagers/zones.js`

- [ ] **Step 1: Create state.js — shared reactive state**

```js
// src/villagers/state.js
// Simple event-based state. Views subscribe to changes.

const listeners = [];
const state = {
  snapshotId: null,
  snapshots: [],
  activeView: 'map',
  selectedVillager: null,
};

export function getState() {
  return state;
}

export function setState(updates) {
  Object.assign(state, updates);
  listeners.forEach((fn) => fn(state));
}

export function subscribe(fn) {
  listeners.push(fn);
}
```

- [ ] **Step 2: Create zones.js — zone geometry config**

This is the client-side equivalent of `zones.toml`. Embedded as JS so it's available at build time. Update this when `zones.toml` changes.

```js
// src/villagers/zones.js
// Zone geometry for map overlays. Matches villager-census/zones.toml.
// Update this file when zones.toml changes.

export const ZONE_COLORS = {
  'north-village': '#4a9eff',
  'old-city': '#ff9f43',
  'farm': '#44cc88',
};

export const ZONES = [
  {
    name: 'north-village',
    type: 'rect',
    x_min: 3090, z_min: -1040,
    x_max: 3220, z_max: -980,
    color: ZONE_COLORS['north-village'],
  },
  {
    name: 'old-city',
    type: 'rect',
    x_min: 3090, z_min: -980,
    x_max: 3220, z_max: -890,
    color: ZONE_COLORS['old-city'],
  },
  {
    name: 'farm',
    type: 'rect',
    x_min: 3090, z_min: -890,
    x_max: 3220, z_max: -826,
    color: ZONE_COLORS['farm'],
  },
];

// Default color for unknown/unclassified zones
export const DEFAULT_ZONE_COLOR = '#5a5e72';

export function getZoneColor(zoneName) {
  return ZONE_COLORS[zoneName] || DEFAULT_ZONE_COLOR;
}
```

- [ ] **Step 3: Commit**

```bash
git add src/villagers/state.js src/villagers/zones.js
git commit -m "feat(villagers): add shared state manager and zone config"
```

---

### Task 5: Profession colors and shared components

**Files:**
- Create: `src/villagers/components/legend.js`
- Create: `src/villagers/components/tooltip.js`

- [ ] **Step 1: Create legend.js — profession color map and legend renderer**

```js
// src/villagers/components/legend.js
// Profession color palette and optional legend DOM element.

export const PROFESSION_COLORS = {
  farmer: '#44cc88',
  fisherman: '#4a9eff',
  librarian: '#cc88ff',
  cleric: '#ff6044',
  weaponsmith: '#ff4466',
  mason: '#8899aa',
  leatherworker: '#cc8844',
  toolsmith: '#aabb44',
  cartographer: '#44bbcc',
  butcher: '#ee6688',
  shepherd: '#88cc66',
  fletcher: '#66aa44',
  armorer: '#99aabb',
  nitwit: '#666677',
  none: '#5a5e72',
};

export function getProfessionColor(profession) {
  return PROFESSION_COLORS[profession] || PROFESSION_COLORS.none;
}

export function renderLegend(container) {
  container.innerHTML = '';
  const ul = document.createElement('div');
  ul.className = 'legend';
  for (const [name, color] of Object.entries(PROFESSION_COLORS)) {
    if (name === 'none') continue;
    const item = document.createElement('span');
    item.className = 'legend-item';
    item.innerHTML = `<span class="legend-dot" style="background:${color}"></span>${name}`;
    ul.appendChild(item);
  }
  container.appendChild(ul);
}
```

- [ ] **Step 2: Create tooltip.js — shared hover tooltip**

```js
// src/villagers/components/tooltip.js
// Reusable tooltip positioned near the mouse.

let el = null;

function ensure() {
  if (!el) {
    el = document.createElement('div');
    el.className = 'tooltip';
    el.style.display = 'none';
    document.body.appendChild(el);
  }
  return el;
}

export function show(html, x, y) {
  const tip = ensure();
  tip.innerHTML = html;
  tip.style.display = 'block';
  tip.style.left = `${x + 12}px`;
  tip.style.top = `${y - 8}px`;
}

export function hide() {
  if (el) el.style.display = 'none';
}
```

- [ ] **Step 3: Commit**

```bash
git add src/villagers/components/legend.js src/villagers/components/tooltip.js
git commit -m "feat(villagers): add profession legend and tooltip components"
```

---

### Task 6: Snapshot slider component

**Files:**
- Create: `src/villagers/components/slider.js`

- [ ] **Step 1: Create slider.js — timeline slider with play button**

```js
// src/villagers/components/slider.js
// Horizontal snapshot slider with play/pause and coverage indicators.

import { getState, setState } from '../state.js';

let playInterval = null;

export function initSlider(container) {
  container.innerHTML = `
    <div class="slider-row">
      <button class="slider-play" title="Play">&#9654;</button>
      <input type="range" class="slider-range" min="0" max="0" value="0">
      <span class="slider-label"></span>
    </div>
  `;

  const range = container.querySelector('.slider-range');
  const label = container.querySelector('.slider-label');
  const playBtn = container.querySelector('.slider-play');

  range.addEventListener('input', () => {
    const { snapshots } = getState();
    const snap = snapshots[parseInt(range.value)];
    if (snap) {
      setState({ snapshotId: snap.id });
    }
  });

  playBtn.addEventListener('click', () => {
    if (playInterval) {
      clearInterval(playInterval);
      playInterval = null;
      playBtn.innerHTML = '&#9654;';
    } else {
      playBtn.innerHTML = '&#9646;&#9646;';
      playInterval = setInterval(() => {
        const idx = parseInt(range.value);
        const max = parseInt(range.max);
        if (idx >= max) {
          clearInterval(playInterval);
          playInterval = null;
          playBtn.innerHTML = '&#9654;';
          return;
        }
        range.value = idx + 1;
        range.dispatchEvent(new Event('input'));
      }, 1500);
    }
  });
}

export function updateSlider(container) {
  const { snapshots, snapshotId } = getState();
  const range = container.querySelector('.slider-range');
  const label = container.querySelector('.slider-label');
  if (!range || !snapshots.length) return;

  range.max = snapshots.length - 1;
  const idx = snapshots.findIndex((s) => s.id === snapshotId);
  if (idx >= 0) range.value = idx;

  const snap = snapshots[idx] || snapshots[snapshots.length - 1];
  if (snap) {
    const ts = new Date(snap.timestamp).toLocaleString();
    const scanned = snap.zones_scanned ? JSON.parse(snap.zones_scanned) : [];
    const skipped = snap.zones_skipped ? JSON.parse(snap.zones_skipped) : [];
    const coverage = skipped.length === 0 ? 'full' : `partial (${scanned.length}/${scanned.length + skipped.length})`;
    label.textContent = `${ts} — ${coverage}`;
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add src/villagers/components/slider.js
git commit -m "feat(villagers): add snapshot timeline slider component"
```

---

### Task 7: Zone cards view

**Files:**
- Create: `src/villagers/views/cards.js`

- [ ] **Step 1: Create cards.js — zone summary cards with sparklines**

```js
// src/villagers/views/cards.js
// Dynamic zone cards: population, beds, homeless, profession breakdown, sparkline.

import * as d3 from 'd3';
import { getZoneColor } from '../zones.js';
import { getZoneStats, getBedStats, getProfessionBreakdown, getZoneTimeSeries, getSnapshots } from '../queries.js';

export function init(container) {
  container.innerHTML = '<div class="zone-cards"></div>';
}

export function update(container, snapshotId) {
  const cardsEl = container.querySelector('.zone-cards');
  const zoneStats = getZoneStats(snapshotId);
  const bedStats = getBedStats(snapshotId);
  const professions = getProfessionBreakdown(snapshotId);
  const timeSeries = getZoneTimeSeries();
  const snapshots = getSnapshots();

  // Build bed lookup
  const bedMap = {};
  bedStats.forEach((b) => { bedMap[b.zone] = b; });

  // Build profession lookup
  const profMap = {};
  professions.forEach((p) => {
    if (!profMap[p.zone]) profMap[p.zone] = [];
    profMap[p.zone].push({ profession: p.profession, count: p.count });
  });

  // Build time series per zone
  const seriesMap = {};
  timeSeries.forEach((row) => {
    if (!seriesMap[row.zone]) seriesMap[row.zone] = [];
    seriesMap[row.zone].push({ snapshotId: row.snapshot_id, count: row.count });
  });

  // Compute totals
  const totalVillagers = zoneStats.reduce((s, z) => s + z.villager_count, 0);
  const totalBeds = bedStats.reduce((s, b) => s + b.bed_count, 0);
  const totalHomeless = zoneStats.reduce((s, z) => s + z.homeless, 0);

  // Previous snapshot for delta
  const snapIdx = snapshots.findIndex((s) => s.id === snapshotId);
  const prevId = snapIdx > 0 ? snapshots[snapIdx - 1].id : null;
  const prevStats = prevId ? getZoneStats(prevId) : [];
  const prevMap = {};
  prevStats.forEach((z) => { prevMap[z.zone] = z.villager_count; });

  let html = '';

  // Total card
  const prevTotal = prevStats.reduce((s, z) => s + z.villager_count, 0);
  const totalDelta = prevId !== null ? totalVillagers - prevTotal : 0;
  const totalDeltaStr = totalDelta > 0 ? `+${totalDelta}` : `${totalDelta}`;
  html += `<div class="zone-card zone-card--total">
    <div class="zone-card__name">Total</div>
    <div class="zone-card__pop">${totalVillagers} ${prevId !== null ? `<span class="delta ${totalDelta >= 0 ? 'up' : 'down'}">(${totalDeltaStr})</span>` : ''}</div>
    <div class="zone-card__beds">${totalBeds} beds / ${totalHomeless} homeless</div>
  </div>`;

  // Per-zone cards
  for (const zone of zoneStats) {
    const beds = bedMap[zone.zone] || { bed_count: 0, claimed: 0 };
    const profs = profMap[zone.zone] || [];
    const top3 = profs.slice(0, 3);
    const othersCount = profs.slice(3).reduce((s, p) => s + p.count, 0);
    const color = getZoneColor(zone.zone);

    const prev = prevMap[zone.zone] || 0;
    const delta = prevId !== null ? zone.villager_count - prev : 0;
    const deltaStr = delta > 0 ? `+${delta}` : `${delta}`;

    const profHtml = top3.map((p) => `${p.profession} (${p.count})`).join(', ')
      + (othersCount > 0 ? `, +${othersCount} others` : '');

    html += `<div class="zone-card" style="border-top: 3px solid ${color}">
      <div class="zone-card__name">${zone.zone}</div>
      <div class="zone-card__pop">${zone.villager_count} ${prevId !== null ? `<span class="delta ${delta >= 0 ? 'up' : 'down'}">(${deltaStr})</span>` : ''}</div>
      <div class="zone-card__beds">${beds.bed_count} beds / ${zone.homeless} homeless</div>
      <div class="zone-card__profs">${profHtml}</div>
      <div class="zone-card__spark" data-zone="${zone.zone}"></div>
    </div>`;
  }

  cardsEl.innerHTML = html;

  // Render sparklines
  cardsEl.querySelectorAll('.zone-card__spark').forEach((sparkEl) => {
    const zoneName = sparkEl.dataset.zone;
    const data = seriesMap[zoneName] || [];
    if (data.length < 2) return;

    const w = sparkEl.clientWidth || 120;
    const h = 30;
    const x = d3.scaleLinear().domain([0, data.length - 1]).range([0, w]);
    const y = d3.scaleLinear().domain([0, d3.max(data, (d) => d.count)]).range([h - 2, 2]);
    const line = d3.line().x((d, i) => x(i)).y((d) => y(d.count));

    const svg = d3.select(sparkEl).append('svg').attr('width', w).attr('height', h);
    svg.append('path').datum(data).attr('d', line)
      .attr('fill', 'none').attr('stroke', getZoneColor(zoneName)).attr('stroke-width', 1.5);
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add src/villagers/views/cards.js
git commit -m "feat(villagers): add zone cards view with sparklines"
```

---

### Task 8: Map view

**Files:**
- Create: `src/villagers/views/map.js`

- [ ] **Step 1: Create map.js — 2D position map with layers**

```js
// src/villagers/views/map.js
// 2D scatter plot with zoom/pan, layer toggles, heatmap mode.

import * as d3 from 'd3';
import { ZONES, getZoneColor } from '../zones.js';
import { getProfessionColor } from '../components/legend.js';
import { show as showTip, hide as hideTip } from '../components/tooltip.js';
import { getVillagerPositions, getBedPositions } from '../queries.js';
import { setState } from '../state.js';

let svg, g, zoom;
let layers = { villagers: true, beds: true, jobSites: false, meetingPoints: false, homes: false, heatmap: false };

export function init(container) {
  container.innerHTML = `
    <div class="map-controls">
      <label><input type="checkbox" data-layer="villagers" checked> Villagers</label>
      <label><input type="checkbox" data-layer="beds" checked> Beds</label>
      <label><input type="checkbox" data-layer="jobSites"> Job sites</label>
      <label><input type="checkbox" data-layer="meetingPoints"> Meeting points</label>
      <label><input type="checkbox" data-layer="homes"> Homes</label>
      <label><input type="checkbox" data-layer="heatmap"> Heatmap</label>
    </div>
    <div class="map-svg-container"></div>
  `;

  const svgContainer = container.querySelector('.map-svg-container');
  const width = svgContainer.clientWidth || 800;
  const height = 500;

  svg = d3.select(svgContainer).append('svg')
    .attr('width', width).attr('height', height)
    .style('background', '#0a0c14');

  g = svg.append('g');

  zoom = d3.zoom().scaleExtent([0.5, 20]).on('zoom', (e) => {
    g.attr('transform', e.transform);
  });
  svg.call(zoom);

  // Layer toggle handlers
  container.querySelectorAll('[data-layer]').forEach((cb) => {
    cb.addEventListener('change', () => {
      layers[cb.dataset.layer] = cb.checked;
      // Re-render with current data
      const event = new CustomEvent('layers-changed');
      container.dispatchEvent(event);
    });
  });
}

export function update(container, snapshotId) {
  const villagers = getVillagerPositions(snapshotId);
  const beds = getBedPositions(snapshotId);

  // Compute bounds from zone config
  const allX = ZONES.flatMap((z) => [z.x_min, z.x_max]);
  const allZ = ZONES.flatMap((z) => [z.z_min, z.z_max]);
  const margin = 20;
  const xExtent = [Math.min(...allX) - margin, Math.max(...allX) + margin];
  const zExtent = [Math.min(...allZ) - margin, Math.max(...allZ) + margin];

  const width = parseInt(svg.attr('width'));
  const height = parseInt(svg.attr('height'));

  const x = d3.scaleLinear().domain(xExtent).range([0, width]);
  const z = d3.scaleLinear().domain(zExtent).range([height, 0]); // Z inverted (north up)

  g.selectAll('*').remove();

  // Zone boundaries
  ZONES.forEach((zone) => {
    g.append('rect')
      .attr('x', x(zone.x_min)).attr('y', z(zone.z_max))
      .attr('width', x(zone.x_max) - x(zone.x_min))
      .attr('height', z(zone.z_min) - z(zone.z_max))
      .attr('fill', zone.color).attr('fill-opacity', 0.08)
      .attr('stroke', zone.color).attr('stroke-opacity', 0.3);

    g.append('text')
      .attr('x', x((zone.x_min + zone.x_max) / 2))
      .attr('y', z((zone.z_min + zone.z_max) / 2))
      .attr('text-anchor', 'middle').attr('fill', zone.color)
      .attr('font-size', '11px').attr('opacity', 0.5)
      .text(zone.name);
  });

  // Heatmap layer
  if (layers.heatmap) {
    const cellSize = 16; // 1 chunk
    const grid = {};
    villagers.forEach((v) => {
      if (v.pos_x == null || v.pos_z == null) return;
      const gx = Math.floor(v.pos_x / cellSize);
      const gz = Math.floor(v.pos_z / cellSize);
      const key = `${gx},${gz}`;
      grid[key] = (grid[key] || 0) + 1;
    });
    const maxCount = Math.max(1, ...Object.values(grid));
    const colorScale = d3.scaleSequential(d3.interpolateYlOrRd).domain([0, maxCount]);

    Object.entries(grid).forEach(([key, count]) => {
      const [gx, gz] = key.split(',').map(Number);
      g.append('rect')
        .attr('x', x(gx * cellSize)).attr('y', z((gz + 1) * cellSize))
        .attr('width', Math.abs(x(gx * cellSize + cellSize) - x(gx * cellSize)))
        .attr('height', Math.abs(z(gz * cellSize) - z((gz + 1) * cellSize)))
        .attr('fill', colorScale(count)).attr('opacity', 0.6);
    });
  }

  // Beds layer
  if (layers.beds) {
    beds.forEach((b) => {
      g.append('rect')
        .attr('x', x(b.pos_x) - 3).attr('y', z(b.pos_z) - 3)
        .attr('width', 6).attr('height', 6)
        .attr('fill', b.claimed_by ? '#44cc88' : '#ef4444')
        .attr('opacity', 0.6);
    });
  }

  // Connection lines (homes, job sites, meeting points)
  villagers.forEach((v) => {
    if (v.pos_x == null || v.pos_z == null) return;
    if (layers.homes && v.home_x != null) {
      g.append('line')
        .attr('x1', x(v.pos_x)).attr('y1', z(v.pos_z))
        .attr('x2', x(v.home_x)).attr('y2', z(v.home_z))
        .attr('stroke', '#44cc88').attr('stroke-width', 0.5).attr('opacity', 0.3);
    }
    if (layers.jobSites && v.job_site_x != null) {
      g.append('line')
        .attr('x1', x(v.pos_x)).attr('y1', z(v.pos_z))
        .attr('x2', x(v.job_site_x)).attr('y2', z(v.job_site_z))
        .attr('stroke', '#ff9f43').attr('stroke-width', 0.5).attr('opacity', 0.3);
    }
    if (layers.meetingPoints && v.meeting_point_x != null) {
      g.append('line')
        .attr('x1', x(v.pos_x)).attr('y1', z(v.pos_z))
        .attr('x2', x(v.meeting_point_x)).attr('y2', z(v.meeting_point_z))
        .attr('stroke', '#cc88ff').attr('stroke-width', 0.5).attr('opacity', 0.3);
    }
  });

  // Villager dots
  if (layers.villagers && !layers.heatmap) {
    villagers.forEach((v) => {
      if (v.pos_x == null || v.pos_z == null) return;
      const dot = g.append('circle')
        .attr('cx', x(v.pos_x)).attr('cy', z(v.pos_z))
        .attr('r', Math.max(3, (v.health || 20) / 5))
        .attr('fill', getProfessionColor(v.profession))
        .attr('stroke', '#fff').attr('stroke-width', 0.5)
        .attr('opacity', 0.85)
        .style('cursor', 'pointer');

      dot.on('mouseover', (event) => {
        showTip(`
          <strong>${v.profession || 'none'}</strong><br>
          Zone: ${v.zone || '?'}<br>
          Health: ${v.health}<br>
          ${v.villager_uuid.slice(0, 8)}...
        `, event.pageX, event.pageY);
      });
      dot.on('mouseout', () => hideTip());
      dot.on('click', () => {
        setState({ activeView: 'tracker', selectedVillager: v.villager_uuid });
      });
    });
  }

  // Re-render on layer toggle
  container.removeEventListener('layers-changed', container._layerHandler);
  container._layerHandler = () => update(container, snapshotId);
  container.addEventListener('layers-changed', container._layerHandler);
}
```

- [ ] **Step 2: Commit**

```bash
git add src/villagers/views/map.js
git commit -m "feat(villagers): add 2D map view with layers, heatmap, zoom"
```

---

### Task 9: Flows view (Alluvial/Sankey)

**Files:**
- Create: `src/villagers/views/flows.js`

- [ ] **Step 1: Create flows.js — alluvial diagram with d3-sankey**

```js
// src/villagers/views/flows.js
// Alluvial diagram showing population flows between zones across snapshots.

import * as d3 from 'd3';
import { sankey, sankeyLinkHorizontal } from 'd3-sankey';
import { getZoneColor } from '../zones.js';
import { getSnapshots, getMigrationFlows, getBirths, getDeaths, getZoneStats } from '../queries.js';

export function init(container) {
  container.innerHTML = '<div class="flows-svg-container"></div>';
}

export function update(container) {
  const flowsEl = container.querySelector('.flows-svg-container');
  flowsEl.innerHTML = '';

  const snapshots = getSnapshots();
  if (snapshots.length < 2) {
    flowsEl.innerHTML = '<p class="empty-msg">Need at least 2 snapshots for flow data.</p>';
    return;
  }

  const width = flowsEl.clientWidth || 800;
  const height = 400;
  const svg = d3.select(flowsEl).append('svg').attr('width', width).attr('height', height);

  // Build nodes: one node per (zone, snapshot) + birth/death nodes
  const nodes = [];
  const nodeMap = {};
  const zones = new Set();

  // Gather all zone names
  snapshots.forEach((snap) => {
    const stats = getZoneStats(snap.id);
    stats.forEach((s) => zones.add(s.zone));
  });

  const zoneList = [...zones].sort();

  snapshots.forEach((snap, i) => {
    zoneList.forEach((zone) => {
      const id = `${zone}-${snap.id}`;
      const node = { id, zone, snapshotIdx: i, name: zone };
      nodes.push(node);
      nodeMap[id] = nodes.length - 1;
    });
    // Birth/death virtual nodes
    const birthId = `born-${snap.id}`;
    nodes.push({ id: birthId, zone: 'born', snapshotIdx: i, name: 'born' });
    nodeMap[birthId] = nodes.length - 1;

    const deathId = `died-${snap.id}`;
    nodes.push({ id: deathId, zone: 'died', snapshotIdx: i, name: 'died' });
    nodeMap[deathId] = nodes.length - 1;
  });

  // Build links between consecutive snapshots
  const links = [];
  for (let i = 0; i < snapshots.length - 1; i++) {
    const fromSnap = snapshots[i];
    const toSnap = snapshots[i + 1];

    const flows = getMigrationFlows(fromSnap.id, toSnap.id);
    flows.forEach((f) => {
      const source = nodeMap[`${f.from_zone}-${fromSnap.id}`];
      const target = nodeMap[`${f.to_zone}-${toSnap.id}`];
      if (source !== undefined && target !== undefined) {
        links.push({ source, target, value: f.count });
      }
    });

    // Births
    const births = getBirths(fromSnap.id, toSnap.id);
    if (births.length > 0) {
      const byZone = {};
      births.forEach((b) => { byZone[b.zone] = (byZone[b.zone] || 0) + 1; });
      Object.entries(byZone).forEach(([zone, count]) => {
        const source = nodeMap[`born-${toSnap.id}`];
        const target = nodeMap[`${zone}-${toSnap.id}`];
        if (source !== undefined && target !== undefined) {
          links.push({ source, target, value: count });
        }
      });
    }

    // Deaths
    const deaths = getDeaths(fromSnap.id, toSnap.id);
    if (deaths.length > 0) {
      const byZone = {};
      deaths.forEach((d) => { byZone[d.zone] = (byZone[d.zone] || 0) + 1; });
      Object.entries(byZone).forEach(([zone, count]) => {
        const source = nodeMap[`${zone}-${fromSnap.id}`];
        const target = nodeMap[`died-${toSnap.id}`];
        if (source !== undefined && target !== undefined) {
          links.push({ source, target, value: count });
        }
      });
    }
  }

  if (links.length === 0) {
    flowsEl.innerHTML = '<p class="empty-msg">No flow data available.</p>';
    return;
  }

  // Layout
  const sankeyGen = sankey()
    .nodeId((d) => d.id)
    .nodeWidth(15)
    .nodePadding(10)
    .extent([[20, 20], [width - 20, height - 20]]);

  const graph = sankeyGen({
    nodes: nodes.map((d) => ({ ...d })),
    links: links.map((d) => ({ ...d })),
  });

  // Render links
  svg.append('g').selectAll('path')
    .data(graph.links)
    .join('path')
    .attr('d', sankeyLinkHorizontal())
    .attr('fill', 'none')
    .attr('stroke', (d) => getZoneColor(d.source.zone))
    .attr('stroke-opacity', 0.4)
    .attr('stroke-width', (d) => Math.max(1, d.width));

  // Render nodes
  svg.append('g').selectAll('rect')
    .data(graph.nodes)
    .join('rect')
    .attr('x', (d) => d.x0).attr('y', (d) => d.y0)
    .attr('width', (d) => d.x1 - d.x0)
    .attr('height', (d) => Math.max(1, d.y1 - d.y0))
    .attr('fill', (d) => {
      if (d.zone === 'born') return '#44cc88';
      if (d.zone === 'died') return '#ef4444';
      return getZoneColor(d.zone);
    });

  // Node labels
  svg.append('g').selectAll('text')
    .data(graph.nodes)
    .join('text')
    .attr('x', (d) => d.x0 < width / 2 ? d.x1 + 6 : d.x0 - 6)
    .attr('y', (d) => (d.y0 + d.y1) / 2)
    .attr('dy', '0.35em')
    .attr('text-anchor', (d) => d.x0 < width / 2 ? 'start' : 'end')
    .attr('fill', '#c8cad0')
    .attr('font-size', '10px')
    .text((d) => d.value > 0 ? d.name : '');
}
```

- [ ] **Step 2: Commit**

```bash
git add src/villagers/views/flows.js
git commit -m "feat(villagers): add alluvial/Sankey flow diagram view"
```

---

### Task 10: Compare view

**Files:**
- Create: `src/villagers/views/compare.js`

- [ ] **Step 1: Create compare.js — snapshot comparison with births/deaths/migrations**

```js
// src/villagers/views/compare.js
// Pick two snapshots, see population deltas, births, deaths, migration matrix, profession changes.

import { getZoneColor } from '../zones.js';
import {
  getSnapshots, getZoneStats, getBirths, getDeaths,
  getMigrationFlows, getProfessionChanges,
} from '../queries.js';
import { setState } from '../state.js';

export function init(container) {
  container.innerHTML = `
    <div class="compare-controls">
      <label>From: <select class="compare-from"></select></label>
      <label>To: <select class="compare-to"></select></label>
    </div>
    <div class="compare-results"></div>
  `;

  const fromSel = container.querySelector('.compare-from');
  const toSel = container.querySelector('.compare-to');

  const onChange = () => {
    const fromId = parseInt(fromSel.value);
    const toId = parseInt(toSel.value);
    if (fromId && toId && fromId !== toId) {
      renderComparison(container.querySelector('.compare-results'), fromId, toId);
    }
  };
  fromSel.addEventListener('change', onChange);
  toSel.addEventListener('change', onChange);
}

export function update(container, snapshotId) {
  const snapshots = getSnapshots();
  const fromSel = container.querySelector('.compare-from');
  const toSel = container.querySelector('.compare-to');

  const options = snapshots.map((s) => {
    const ts = new Date(s.timestamp).toLocaleString();
    return `<option value="${s.id}">${ts} (${s.villager_count}v)</option>`;
  }).join('');

  fromSel.innerHTML = options;
  toSel.innerHTML = options;

  // Default: second-to-last vs last
  if (snapshots.length >= 2) {
    fromSel.value = snapshots[snapshots.length - 2].id;
    toSel.value = snapshots[snapshots.length - 1].id;
    renderComparison(
      container.querySelector('.compare-results'),
      snapshots[snapshots.length - 2].id,
      snapshots[snapshots.length - 1].id,
    );
  }
}

function renderComparison(resultsEl, fromId, toId) {
  const fromStats = getZoneStats(fromId);
  const toStats = getZoneStats(toId);
  const births = getBirths(fromId, toId);
  const deaths = getDeaths(fromId, toId);
  const flows = getMigrationFlows(fromId, toId);
  const profChanges = getProfessionChanges(fromId, toId);

  const toMap = {};
  toStats.forEach((z) => { toMap[z.zone] = z.villager_count; });
  const fromMap = {};
  fromStats.forEach((z) => { fromMap[z.zone] = z.villager_count; });

  let html = '<div class="compare-section">';

  // Population delta
  html += '<h3>Population by zone</h3><table class="compare-table"><tr><th>Zone</th><th>Before</th><th>After</th><th>Delta</th></tr>';
  const allZones = new Set([...fromStats.map((z) => z.zone), ...toStats.map((z) => z.zone)]);
  for (const zone of allZones) {
    const before = fromMap[zone] || 0;
    const after = toMap[zone] || 0;
    const delta = after - before;
    const cls = delta > 0 ? 'up' : delta < 0 ? 'down' : '';
    html += `<tr><td style="color:${getZoneColor(zone)}">${zone}</td><td>${before}</td><td>${after}</td><td class="delta ${cls}">${delta > 0 ? '+' : ''}${delta}</td></tr>`;
  }
  html += '</table>';

  // Births
  html += `<h3>Births (${births.length})</h3>`;
  if (births.length > 0) {
    html += '<table class="compare-table"><tr><th>UUID</th><th>Profession</th><th>Zone</th></tr>';
    births.forEach((b) => {
      html += `<tr><td class="uuid-link" data-uuid="${b.villager_uuid}">${b.villager_uuid.slice(0, 8)}...</td><td>${b.profession || 'none'}</td><td>${b.zone || '?'}</td></tr>`;
    });
    html += '</table>';
  }

  // Deaths
  html += `<h3>Deaths (${deaths.length})</h3>`;
  if (deaths.length > 0) {
    html += '<table class="compare-table"><tr><th>UUID</th><th>Profession</th><th>Zone</th></tr>';
    deaths.forEach((d) => {
      html += `<tr><td class="uuid-link" data-uuid="${d.villager_uuid}">${d.villager_uuid.slice(0, 8)}...</td><td>${d.profession || 'none'}</td><td>${d.zone || '?'}</td></tr>`;
    });
    html += '</table>';
  }

  // Migration matrix
  html += '<h3>Migration</h3><table class="compare-table"><tr><th>From \\ To</th>';
  const flowZones = [...new Set(flows.flatMap((f) => [f.from_zone, f.to_zone]))].sort();
  flowZones.forEach((z) => { html += `<th style="color:${getZoneColor(z)}">${z}</th>`; });
  html += '</tr>';
  flowZones.forEach((from) => {
    html += `<tr><td style="color:${getZoneColor(from)}">${from}</td>`;
    flowZones.forEach((to) => {
      const flow = flows.find((f) => f.from_zone === from && f.to_zone === to);
      const val = flow ? flow.count : 0;
      const bold = from !== to && val > 0 ? 'font-weight:bold' : 'opacity:0.4';
      html += `<td style="${bold}">${val}</td>`;
    });
    html += '</tr>';
  });
  html += '</table>';

  // Profession changes
  html += `<h3>Profession changes (${profChanges.length})</h3>`;
  if (profChanges.length > 0) {
    html += '<table class="compare-table"><tr><th>UUID</th><th>From</th><th>To</th><th>Zone</th></tr>';
    profChanges.forEach((p) => {
      html += `<tr><td class="uuid-link" data-uuid="${p.villager_uuid}">${p.villager_uuid.slice(0, 8)}...</td><td>${p.old_profession}</td><td>${p.new_profession}</td><td>${p.zone || '?'}</td></tr>`;
    });
    html += '</table>';
  }

  html += '</div>';
  resultsEl.innerHTML = html;

  // UUID click handlers
  resultsEl.querySelectorAll('.uuid-link').forEach((el) => {
    el.addEventListener('click', () => {
      setState({ activeView: 'tracker', selectedVillager: el.dataset.uuid });
    });
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add src/villagers/views/compare.js
git commit -m "feat(villagers): add snapshot comparison view"
```

---

### Task 11: Tracker view

**Files:**
- Create: `src/villagers/views/tracker.js`

- [ ] **Step 1: Create tracker.js — individual villager deep dive**

```js
// src/villagers/views/tracker.js
// Shows full history, position trail, trades, inventory, gossip for one villager.

import * as d3 from 'd3';
import { ZONES, getZoneColor } from '../zones.js';
import { getProfessionColor } from '../components/legend.js';
import {
  getVillagerInfo, getVillagerHistory, getVillagerTrades,
  getVillagerInventory, getVillagerGossip, getAllVillagersList,
} from '../queries.js';
import { getState, setState } from '../state.js';

export function init(container) {
  container.innerHTML = `
    <div class="tracker-controls">
      <input type="text" class="tracker-search" placeholder="Search by UUID or profession...">
      <select class="tracker-list"></select>
    </div>
    <div class="tracker-detail"></div>
  `;

  const search = container.querySelector('.tracker-search');
  const select = container.querySelector('.tracker-list');

  select.addEventListener('change', () => {
    if (select.value) {
      setState({ selectedVillager: select.value });
    }
  });

  search.addEventListener('input', () => {
    const q = search.value.toLowerCase();
    const options = select.querySelectorAll('option');
    options.forEach((opt) => {
      opt.hidden = q && !opt.textContent.toLowerCase().includes(q);
    });
  });
}

export function update(container, snapshotId) {
  const { selectedVillager } = getState();
  const select = container.querySelector('.tracker-list');
  const detail = container.querySelector('.tracker-detail');

  // Populate list
  const villagers = getAllVillagersList(snapshotId);
  select.innerHTML = '<option value="">Select a villager...</option>'
    + villagers.map((v) =>
      `<option value="${v.villager_uuid}" ${v.villager_uuid === selectedVillager ? 'selected' : ''}>`
      + `${v.villager_uuid.slice(0, 8)}... — ${v.profession || 'none'} (${v.zone || '?'})`
      + `${v.presumed_dead ? ' [dead]' : ''}</option>`
    ).join('');

  if (!selectedVillager) {
    detail.innerHTML = '<p class="empty-msg">Select a villager from the list or click one on the map.</p>';
    return;
  }

  const info = getVillagerInfo(selectedVillager);
  const history = getVillagerHistory(selectedVillager);
  const trades = getVillagerTrades(snapshotId, selectedVillager);
  const inventory = getVillagerInventory(snapshotId, selectedVillager);
  const gossip = getVillagerGossip(snapshotId, selectedVillager);

  if (!info) {
    detail.innerHTML = '<p class="empty-msg">Villager not found.</p>';
    return;
  }

  let html = '<div class="tracker-content">';

  // Identity
  html += `<div class="tracker-section">
    <h3>Identity</h3>
    <table class="tracker-table">
      <tr><td>UUID</td><td><code>${info.uuid}</code></td></tr>
      <tr><td>Spawn</td><td>${info.spawn_reason || '?'}</td></tr>
      <tr><td>Origin</td><td>${info.origin_x?.toFixed(0)}, ${info.origin_y?.toFixed(0)}, ${info.origin_z?.toFixed(0)}</td></tr>
      <tr><td>Status</td><td>${info.presumed_dead ? '<span style="color:#ef4444">Dead</span>' : '<span style="color:#44cc88">Alive</span>'}</td></tr>
    </table>
  </div>`;

  // Position trail mini-map
  if (history.length > 0) {
    html += '<div class="tracker-section"><h3>Position trail</h3><div class="tracker-minimap"></div></div>';
  }

  // Timeline
  html += '<div class="tracker-section"><h3>Timeline</h3><table class="tracker-table"><tr><th>#</th><th>Time</th><th>Zone</th><th>Profession</th><th>Health</th></tr>';
  history.forEach((h, i) => {
    const ts = new Date(h.timestamp).toLocaleString();
    html += `<tr><td>${i + 1}</td><td>${ts}</td><td style="color:${getZoneColor(h.zone)}">${h.zone || '?'}</td><td>${h.profession || 'none'}</td><td>${h.health}</td></tr>`;
  });
  html += '</table></div>';

  // Current anchors
  const latest = history[history.length - 1];
  if (latest) {
    html += '<div class="tracker-section"><h3>Anchors</h3><table class="tracker-table">';
    if (latest.home_x != null) html += `<tr><td>Home</td><td>${latest.home_x?.toFixed(0)}, ${latest.home_y?.toFixed(0)}, ${latest.home_z?.toFixed(0)}</td></tr>`;
    else html += '<tr><td>Home</td><td style="color:#ef4444">Homeless</td></tr>';
    if (latest.job_site_x != null) html += `<tr><td>Job site</td><td>${latest.job_site_x?.toFixed(0)}, ${latest.job_site_y?.toFixed(0)}, ${latest.job_site_z?.toFixed(0)}</td></tr>`;
    if (latest.meeting_point_x != null) html += `<tr><td>Meeting point</td><td>${latest.meeting_point_x?.toFixed(0)}, ${latest.meeting_point_y?.toFixed(0)}, ${latest.meeting_point_z?.toFixed(0)}</td></tr>`;
    html += '</table></div>';
  }

  // Trades
  if (trades.length > 0) {
    html += '<div class="tracker-section"><h3>Trades</h3><table class="tracker-table"><tr><th>Slot</th><th>Buy</th><th>Sell</th><th>Uses</th></tr>';
    trades.forEach((t) => {
      const buy = `${t.buy_count}x ${t.buy_item?.replace('minecraft:', '')}` + (t.buy_b_item ? ` + ${t.buy_b_count}x ${t.buy_b_item.replace('minecraft:', '')}` : '');
      html += `<tr><td>${t.slot}</td><td>${buy}</td><td>${t.sell_count}x ${t.sell_item?.replace('minecraft:', '')}</td><td>${t.max_uses}</td></tr>`;
    });
    html += '</table></div>';
  }

  // Inventory
  if (inventory.length > 0) {
    html += '<div class="tracker-section"><h3>Inventory</h3><ul>';
    inventory.forEach((item) => {
      html += `<li>${item.count}x ${item.item.replace('minecraft:', '')}</li>`;
    });
    html += '</ul></div>';
  }

  // Gossip
  if (gossip.length > 0) {
    html += '<div class="tracker-section"><h3>Gossip</h3><table class="tracker-table"><tr><th>Type</th><th>Target</th><th>Value</th></tr>';
    gossip.forEach((g) => {
      html += `<tr><td>${g.gossip_type}</td><td>${g.target_uuid ? g.target_uuid.slice(0, 8) + '...' : '?'}</td><td>${g.value}</td></tr>`;
    });
    html += '</table></div>';
  }

  html += '</div>';
  detail.innerHTML = html;

  // Render position trail mini-map
  const minimapEl = detail.querySelector('.tracker-minimap');
  if (minimapEl && history.length > 0) {
    renderMinimap(minimapEl, history);
  }
}

function renderMinimap(container, history) {
  const w = container.clientWidth || 300;
  const h = 200;

  const positions = history.filter((h) => h.pos_x != null && h.pos_z != null);
  if (positions.length === 0) return;

  // Use zone bounds for consistent framing
  const allX = [...ZONES.flatMap((z) => [z.x_min, z.x_max]), ...positions.map((p) => p.pos_x)];
  const allZ = [...ZONES.flatMap((z) => [z.z_min, z.z_max]), ...positions.map((p) => p.pos_z)];

  const x = d3.scaleLinear().domain(d3.extent(allX)).range([10, w - 10]);
  const z = d3.scaleLinear().domain(d3.extent(allZ)).range([h - 10, 10]);

  const svg = d3.select(container).append('svg').attr('width', w).attr('height', h)
    .style('background', '#0a0c14').style('border-radius', '4px');

  // Zone outlines
  ZONES.forEach((zone) => {
    svg.append('rect')
      .attr('x', x(zone.x_min)).attr('y', z(zone.z_max))
      .attr('width', x(zone.x_max) - x(zone.x_min))
      .attr('height', z(zone.z_min) - z(zone.z_max))
      .attr('fill', 'none').attr('stroke', zone.color).attr('stroke-opacity', 0.2);
  });

  // Trail line
  const line = d3.line().x((d) => x(d.pos_x)).y((d) => z(d.pos_z));
  svg.append('path').datum(positions).attr('d', line)
    .attr('fill', 'none').attr('stroke', '#fff').attr('stroke-width', 1).attr('opacity', 0.5);

  // Waypoints
  positions.forEach((p, i) => {
    svg.append('circle')
      .attr('cx', x(p.pos_x)).attr('cy', z(p.pos_z))
      .attr('r', i === positions.length - 1 ? 5 : 3)
      .attr('fill', getProfessionColor(p.profession))
      .attr('stroke', '#fff').attr('stroke-width', 0.5);

    svg.append('text')
      .attr('x', x(p.pos_x) + 6).attr('y', z(p.pos_z) + 3)
      .attr('fill', '#888').attr('font-size', '8px')
      .text(i + 1);
  });
}
```

- [ ] **Step 2: Commit**

```bash
git add src/villagers/views/tracker.js
git commit -m "feat(villagers): add villager tracker view with position trail"
```

---

### Task 12: Astro page shell — HTML, CSS, and page orchestrator

**Files:**
- Create: `src/pages/villagers.astro`

This is the main page that ties everything together. It contains the HTML structure, all CSS, and the orchestrator script that initializes views and wires up state changes.

- [ ] **Step 1: Create villagers.astro**

```astro
---
// Villagers Dashboard — Census data explorer
// Standalone page (does not use Layout.astro)
---
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<meta name="robots" content="noindex, nofollow">
<title>Villager Census — Piwigord</title>
<link rel="icon" type="image/png" href="/minecraft/favicon.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<script src="https://sql.js.org/dist/sql-wasm.js"></script>
<style is:global>
:root {
  --ui: 'Inter', system-ui, sans-serif;
  --mono: 'JetBrains Mono', 'Consolas', monospace;
  --bg: #07080c;
  --glass-bg: rgba(10, 12, 20, 0.75);
  --glass-border: rgba(255, 255, 255, 0.08);
  --text: #c8cad0;
  --text-dim: #5a5e72;
  --text-bright: #eaecf0;
  --accent: #4a9eff;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: var(--ui); font-size: 13px; background: var(--bg); color: var(--text); min-height: 100vh; }

/* Loading */
.loading { display: flex; align-items: center; justify-content: center; height: 100vh; }
.loading p { font-family: var(--mono); color: var(--text-dim); letter-spacing: 0.08em; }

/* Header */
.header { padding: 16px 24px; border-bottom: 1px solid var(--glass-border); }
.header h1 { font-size: 18px; font-weight: 600; color: var(--text-bright); }
.header .meta { font-size: 11px; color: var(--text-dim); margin-top: 4px; }
.header .coverage { display: inline-block; padding: 1px 6px; border-radius: 3px; font-size: 10px; }
.header .coverage.full { background: rgba(68, 204, 136, 0.15); color: #44cc88; }
.header .coverage.partial { background: rgba(255, 159, 67, 0.15); color: #ff9f43; }

/* Zone cards */
.zone-cards { display: flex; gap: 12px; padding: 16px 24px; overflow-x: auto; }
.zone-card { background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: 8px; padding: 12px 16px; min-width: 180px; flex: 1; }
.zone-card--total { border-top: 3px solid var(--accent); }
.zone-card__name { font-weight: 600; font-size: 14px; color: var(--text-bright); margin-bottom: 4px; }
.zone-card__pop { font-size: 20px; font-weight: 600; color: var(--text-bright); }
.zone-card__beds { font-size: 11px; color: var(--text-dim); margin-top: 2px; }
.zone-card__profs { font-size: 10px; color: var(--text-dim); margin-top: 4px; }
.zone-card__spark { height: 30px; margin-top: 8px; }
.delta { font-size: 12px; font-weight: 400; }
.delta.up { color: #44cc88; }
.delta.down { color: #ef4444; }

/* View tabs */
.view-tabs { display: flex; gap: 0; padding: 0 24px; border-bottom: 1px solid var(--glass-border); }
.view-tab { padding: 10px 20px; font-size: 12px; font-weight: 500; color: var(--text-dim); cursor: pointer; border-bottom: 2px solid transparent; transition: all 0.2s; }
.view-tab:hover { color: var(--text); }
.view-tab.active { color: var(--accent); border-bottom-color: var(--accent); }

/* View container */
.view-container { padding: 16px 24px; min-height: 400px; }

/* Slider */
.slider-row { display: flex; align-items: center; gap: 12px; padding: 12px 24px; border-top: 1px solid var(--glass-border); }
.slider-play { background: none; border: 1px solid var(--glass-border); color: var(--text); padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: 12px; }
.slider-play:hover { border-color: var(--accent); color: var(--accent); }
.slider-range { flex: 1; accent-color: var(--accent); }
.slider-label { font-family: var(--mono); font-size: 11px; color: var(--text-dim); min-width: 220px; text-align: right; }

/* Map */
.map-controls { display: flex; gap: 16px; padding: 8px 0; font-size: 11px; color: var(--text-dim); flex-wrap: wrap; }
.map-controls label { cursor: pointer; display: flex; align-items: center; gap: 4px; }
.map-controls input { accent-color: var(--accent); }
.map-svg-container svg { border-radius: 6px; width: 100%; }

/* Flows */
.flows-svg-container svg { width: 100%; }

/* Compare */
.compare-controls { display: flex; gap: 16px; padding: 8px 0; }
.compare-controls select { background: var(--glass-bg); border: 1px solid var(--glass-border); color: var(--text); padding: 4px 8px; border-radius: 4px; font-size: 11px; font-family: var(--mono); }
.compare-section h3 { font-size: 13px; color: var(--text-bright); margin: 16px 0 8px; }
.compare-table { border-collapse: collapse; font-size: 11px; width: 100%; }
.compare-table th, .compare-table td { padding: 4px 10px; text-align: left; border-bottom: 1px solid var(--glass-border); }
.compare-table th { color: var(--text-dim); font-weight: 500; }

/* Tracker */
.tracker-controls { display: flex; gap: 12px; padding: 8px 0; }
.tracker-search { background: var(--glass-bg); border: 1px solid var(--glass-border); color: var(--text); padding: 6px 10px; border-radius: 4px; font-size: 12px; width: 200px; }
.tracker-list { background: var(--glass-bg); border: 1px solid var(--glass-border); color: var(--text); padding: 4px 8px; border-radius: 4px; font-size: 11px; font-family: var(--mono); flex: 1; }
.tracker-content { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 16px; }
.tracker-section { background: var(--glass-bg); border: 1px solid var(--glass-border); border-radius: 8px; padding: 12px 16px; }
.tracker-section h3 { font-size: 12px; color: var(--text-bright); margin-bottom: 8px; }
.tracker-table { border-collapse: collapse; font-size: 11px; width: 100%; }
.tracker-table td, .tracker-table th { padding: 3px 8px; border-bottom: 1px solid var(--glass-border); }
.tracker-minimap { width: 100%; }

/* Shared */
.uuid-link { color: var(--accent); cursor: pointer; font-family: var(--mono); }
.uuid-link:hover { text-decoration: underline; }
.empty-msg { color: var(--text-dim); font-style: italic; padding: 40px; text-align: center; }
.tooltip { position: fixed; background: rgba(10,12,20,0.95); border: 1px solid var(--glass-border); border-radius: 6px; padding: 8px 12px; font-size: 11px; color: var(--text); pointer-events: none; z-index: 100; max-width: 240px; }
.legend { display: flex; flex-wrap: wrap; gap: 8px; font-size: 10px; }
.legend-item { display: flex; align-items: center; gap: 4px; color: var(--text-dim); }
.legend-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; }
code { font-family: var(--mono); font-size: 11px; background: rgba(255,255,255,0.05); padding: 1px 4px; border-radius: 3px; }
</style>
</head>
<body>

<div id="app">
  <div class="loading"><p>Loading census data...</p></div>
</div>

<script type="module">
import { initDB } from '../villagers/db.js';
import { getSnapshots, getLatestSnapshotId } from '../villagers/queries.js';
import { getState, setState, subscribe } from '../villagers/state.js';
import { initSlider, updateSlider } from '../villagers/components/slider.js';
import { renderLegend } from '../villagers/components/legend.js';
import * as cardsView from '../villagers/views/cards.js';
import * as mapView from '../villagers/views/map.js';
import * as flowsView from '../villagers/views/flows.js';
import * as compareView from '../villagers/views/compare.js';
import * as trackerView from '../villagers/views/tracker.js';

const views = { map: mapView, flows: flowsView, compare: compareView, tracker: trackerView };

async function main() {
  try {
    await initDB();
  } catch (err) {
    document.getElementById('app').innerHTML = `<div class="loading"><p style="color:#ef4444">Failed to load census data: ${err.message}</p></div>`;
    return;
  }

  const snapshots = getSnapshots();
  if (snapshots.length === 0) {
    document.getElementById('app').innerHTML = '<div class="loading"><p>No census data yet.</p></div>';
    return;
  }

  const latestId = getLatestSnapshotId();
  const latest = snapshots.find((s) => s.id === latestId);
  const scanned = latest.zones_scanned ? JSON.parse(latest.zones_scanned) : [];
  const skipped = latest.zones_skipped ? JSON.parse(latest.zones_skipped) : [];
  const coverageClass = skipped.length === 0 ? 'full' : 'partial';
  const coverageText = skipped.length === 0 ? 'Full coverage' : `Partial (${scanned.length}/${scanned.length + skipped.length} zones)`;

  document.getElementById('app').innerHTML = `
    <div class="header">
      <h1>Villager Census</h1>
      <div class="meta">
        Last census: ${new Date(latest.timestamp).toLocaleString()}
        &mdash; ${latest.villager_count} villagers, ${latest.bed_count} beds
        &mdash; <span class="coverage ${coverageClass}">${coverageText}</span>
      </div>
    </div>
    <div id="cards"></div>
    <div id="legend" style="padding:4px 24px"></div>
    <div class="view-tabs">
      <div class="view-tab active" data-view="map">Map</div>
      <div class="view-tab" data-view="flows">Flows</div>
      <div class="view-tab" data-view="compare">Compare</div>
      <div class="view-tab" data-view="tracker">Tracker</div>
    </div>
    <div id="view" class="view-container"></div>
    <div id="slider"></div>
  `;

  setState({ snapshots, snapshotId: latestId, activeView: 'map' });

  // Init components
  cardsView.init(document.getElementById('cards'));
  renderLegend(document.getElementById('legend'));
  initSlider(document.getElementById('slider'));

  // Init all views
  const viewEl = document.getElementById('view');
  for (const [name, view] of Object.entries(views)) {
    const div = document.createElement('div');
    div.id = `view-${name}`;
    div.style.display = 'none';
    viewEl.appendChild(div);
    view.init(div);
  }

  // Tab switching
  document.querySelectorAll('.view-tab').forEach((tab) => {
    tab.addEventListener('click', () => {
      setState({ activeView: tab.dataset.view });
    });
  });

  // State change handler
  subscribe((state) => {
    // Update tabs
    document.querySelectorAll('.view-tab').forEach((tab) => {
      tab.classList.toggle('active', tab.dataset.view === state.activeView);
    });

    // Show/hide views
    for (const name of Object.keys(views)) {
      const el = document.getElementById(`view-${name}`);
      el.style.display = name === state.activeView ? 'block' : 'none';
    }

    // Update active view
    const activeEl = document.getElementById(`view-${state.activeView}`);
    if (state.activeView === 'flows') {
      views.flows.update(activeEl);
    } else {
      views[state.activeView].update(activeEl, state.snapshotId);
    }

    // Always update cards and slider
    cardsView.update(document.getElementById('cards'), state.snapshotId);
    updateSlider(document.getElementById('slider'));
  });

  // Trigger initial render
  setState({});
}

main();
</script>
</body>
</html>
```

- [ ] **Step 2: Verify local dev server**

```bash
cd /home/leo/documents/code/disqt.com/disqt-minecraft
npm run dev
```

Open `http://localhost:4322/minecraft/villagers/` in a browser. The page should load, show "Loading census data...", then either render (if nginx is proxied) or show an error (expected locally without the DB file).

- [ ] **Step 3: Commit**

```bash
git add src/pages/villagers.astro
git commit -m "feat(villagers): add villagers dashboard page with all views"
```

---

### Task 13: Deploy and verify

- [ ] **Step 1: Push to main**

```bash
cd /home/leo/documents/code/disqt.com/disqt-minecraft
git push origin main
```

This triggers the GitHub Actions deploy workflow.

- [ ] **Step 2: Verify nginx config is active**

```bash
ssh dev "curl -sI http://localhost:4322/minecraft/villagers/ | head -5"
```

Expected: HTTP 200 from the Astro SSR server.

```bash
curl -sI https://disqt.com/minecraft/villagers/census.db | head -5
```

Expected: HTTP 200 with `application/octet-stream`.

- [ ] **Step 3: Open in browser and verify**

Open `https://disqt.com/minecraft/villagers/` and verify:
- Page loads, sql.js initializes, DB fetches successfully
- Zone cards show population numbers with sparklines
- Map view renders villager dots with zone boundaries
- Layer toggles work (beds, job sites, meeting points, homes, heatmap)
- Flows view shows alluvial diagram (needs 2+ snapshots)
- Compare view shows births/deaths between snapshots
- Tracker view shows villager detail when clicked
- Snapshot slider scrubs through time
- Tooltips and click-to-track work

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix(villagers): post-deploy fixes"
git push origin main
```

---

### Task 14: UI polish with /frontend-design

This task is intentionally left as a checkpoint. After verifying the functional dashboard works end-to-end, invoke the `/frontend-design` skill with the visual companion to explore design options in the browser and iterate on:

- Color palette and visual hierarchy
- Card layout and spacing
- Map styling and interaction feel
- Sankey diagram aesthetics
- Typography and spacing
- Dark theme refinements
- Responsive breakpoints

Do NOT attempt UI polish before the functional dashboard is verified working.
