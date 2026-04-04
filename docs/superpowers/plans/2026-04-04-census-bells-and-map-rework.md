# Census Bell POIs + Map Rework Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add bell POI scraping to the villager census tool and redesign the dashboard map view with a clean entity/connection layer model, Lucide icon markers, and tooltips on all interactive elements.

**Architecture:** Two-phase delivery. Phase 1 adds bell scraping to the Python census tool (new `bells` DB table, extended POI parser, census pipeline integration). Phase 2 reworks the dashboard map.js with a two-tier control system (entity layers + connection toggle), SVG icon markers, and comprehensive tooltips. Bell data flows from Phase 1 into Phase 2 via the existing sql.js pipeline.

**Tech Stack:** Python 3 + SQLite (census tool), Astro 5 + D3.js + sql.js (dashboard), Lucide icon SVG paths (embedded, no dependency)

**Spec:** `docs/superpowers/specs/2026-04-04-census-bells-and-map-rework-design.md`

**Census tool:** `/home/leo/documents/code/disqt.com/minecraft/villager-census/`
**Dashboard app:** `/home/leo/documents/code/disqt.com/disqt-minecraft/`

---

## File Structure

### Phase 1: Census bell scraping

```
villager-census/
  census_poi.py              # Modify: extend parser for minecraft:meeting
  census_db.py               # Modify: add bells table, bell_count column, insert_bell()
  census.py                  # Modify: split POIs, build meeting_point lookup, insert bells
  tests/test_census_poi.py   # Modify: add bell parsing tests
  tests/test_census_db.py    # Modify: add bell insert/schema tests
```

### Phase 2: Dashboard map rework

```
disqt-minecraft/
  src/villagers/icons.js                # Create: Lucide SVG path constants
  src/villagers/views/map.js            # Rewrite: new layer model, icon markers, tooltips
  src/villagers/queries.js              # Modify: add getBellPositions query
  src/pages/villagers.astro             # Modify: update CSS for new map controls
```

---

### Task 1: Extend POI parser for bells

**Files:**
- Modify: `villager-census/census_poi.py:74-127`
- Modify: `villager-census/tests/test_census_poi.py`

- [ ] **Step 1: Write test for bell parsing**

Add to `tests/test_census_poi.py`:

```python
def test_parse_poi_region_finds_bells(tmp_path):
    """Bell POIs (minecraft:meeting) are returned with type field."""
    region_path = _build_poi_region(
        tmp_path,
        records=[
            ("minecraft:home", [100, 64, 200], 0),
            ("minecraft:meeting", [110, 65, 210], 30),
            ("minecraft:meeting", [120, 65, 220], 28),
        ],
    )
    results = parse_poi_region(region_path)
    assert len(results) == 3
    beds = [r for r in results if r["type"] == "minecraft:home"]
    bells = [r for r in results if r["type"] == "minecraft:meeting"]
    assert len(beds) == 1
    assert len(bells) == 2
    assert bells[0]["pos"] == [110, 65, 210]
    assert bells[0]["free_tickets"] == 30
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd /home/leo/documents/code/disqt.com/minecraft/villager-census
python -m pytest tests/test_census_poi.py::test_parse_poi_region_finds_bells -v
```

Expected: FAIL — results filtered to only `minecraft:home`, no `type` field in output.

- [ ] **Step 3: Update census_poi.py to parse both types**

In `census_poi.py`, update `parse_poi_region`:

```python
def parse_poi_region(region_path):
    """Parse a POI .mca file. Returns list of
    {"type": str, "pos": [x, y, z], "free_tickets": int} dicts,
    filtered to minecraft:home and minecraft:meeting types.
    """
    _WANTED_TYPES = {b"minecraft:home", b"minecraft:meeting"}
    _WANTED_STRS = {"minecraft:home", "minecraft:meeting"}
    results = []
    with open(region_path, "rb") as f:
        location_header = f.read(4096)
        f.read(4096)  # skip timestamp header

        for slot in range(1024):
            entry_bytes = location_header[slot * 4: slot * 4 + 4]
            entry = struct.unpack(">I", entry_bytes)[0]
            offset = (entry >> 8) & 0xFFFFFF
            sector_count = entry & 0xFF
            if offset == 0 and sector_count == 0:
                continue  # empty slot

            f.seek(offset * 4096)
            length = struct.unpack(">I", f.read(4))[0]
            compression_type = struct.unpack(">B", f.read(1))[0]
            compressed_data = f.read(length - 1)

            if compression_type == 2:
                raw = zlib.decompress(compressed_data)
            elif compression_type == 1:
                import gzip
                raw = gzip.decompress(compressed_data)
            else:
                raw = compressed_data  # uncompressed

            # Fast pre-filter: skip chunks without any wanted POI type
            if not any(t in raw for t in _WANTED_TYPES):
                continue

            nbt = read_nbt(io.BytesIO(raw))
            sections = nbt.get("Sections", {})
            for section_key, section in sections.items():
                records = section.get("Records", [])
                for record in records:
                    rtype = record.get("type")
                    if rtype in _WANTED_STRS:
                        results.append({
                            "type": rtype,
                            "pos": record["pos"],
                            "free_tickets": record.get("free_tickets", 0),
                        })

    return results


def parse_poi_regions(region_paths):
    """Parse multiple POI region files. Returns combined list of POI records."""
    results = []
    for path in region_paths:
        results.extend(parse_poi_region(path))
    return results
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
python -m pytest tests/test_census_poi.py -v
```

Expected: ALL PASS. Existing bed tests still pass (results now include `type` field, but existing tests only check `pos` and `free_tickets`).

**Note:** Existing tests that check `len(results)` may need updating since bells in test fixtures would now also be returned. Check each test — if fixtures only contain `minecraft:home` records, they'll be fine. The `test_parse_poi_region_finds_beds` test creates records with `minecraft:armorer` which is still filtered out.

- [ ] **Step 5: Update existing tests for new `type` field**

The existing `test_parse_poi_region_finds_beds` test creates 2 beds + 1 armorer. Results now have a `type` field. Verify the test still passes as-is (it checks `len(results) == 2` and `results[0]["pos"]` — the `type` field addition doesn't break this). If any assertion fails, add `type` checks.

- [ ] **Step 6: Commit**

```bash
git add census_poi.py tests/test_census_poi.py
git commit -m "feat(census): extend POI parser for bell scraping (minecraft:meeting)"
```

---

### Task 2: Add bells table and insert helper to DB

**Files:**
- Modify: `villager-census/census_db.py:16-131` (schema), `:148-165` (migrate), `:311-322` (insert_bed pattern)
- Modify: `villager-census/tests/test_census_db.py` (if exists) or create test

- [ ] **Step 1: Write test for bells table and insert**

Create or add to `tests/test_census_db.py`:

```python
import sqlite3
from census_db import init_db, insert_snapshot, insert_bell


def test_insert_bell(tmp_path):
    conn = init_db(tmp_path / "test.db")
    snap_id = insert_snapshot(
        conn, timestamp="2026-04-04T12:00:00Z", players_online="[]",
        area_center_x=100, area_center_z=200, scan_radius=64,
        villager_count=10, bed_count=5, bell_count=2, notes="test",
    )
    bell_id = insert_bell(
        conn, snapshot_id=snap_id,
        pos_x=110, pos_y=65, pos_z=210,
        free_tickets=30, villager_count=3, zone="north-village",
    )
    assert bell_id is not None

    row = conn.execute("SELECT * FROM bells WHERE id = ?", (bell_id,)).fetchone()
    assert row["pos_x"] == 110
    assert row["free_tickets"] == 30
    assert row["villager_count"] == 3
    assert row["zone"] == "north-village"

    # Check bell_count in snapshot
    snap = conn.execute("SELECT bell_count FROM snapshots WHERE id = ?", (snap_id,)).fetchone()
    assert snap["bell_count"] == 2
```

- [ ] **Step 2: Run test to verify it fails**

```bash
python -m pytest tests/test_census_db.py::test_insert_bell -v
```

Expected: FAIL — no `bells` table, no `insert_bell`, no `bell_count` column.

- [ ] **Step 3: Add bells table to schema**

In `census_db.py`, add after the `beds` table definition (line 130, before the closing `"""`):

```sql
CREATE TABLE IF NOT EXISTS bells (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    snapshot_id     INTEGER NOT NULL REFERENCES snapshots(id),
    pos_x           INTEGER NOT NULL,
    pos_y           INTEGER NOT NULL,
    pos_z           INTEGER NOT NULL,
    free_tickets    INTEGER NOT NULL DEFAULT 0,
    villager_count  INTEGER NOT NULL DEFAULT 0,
    zone            TEXT,
    UNIQUE(snapshot_id, pos_x, pos_y, pos_z)
);
```

- [ ] **Step 4: Add bell_count to snapshots and update insert_snapshot**

Add `bell_count` column to snapshots schema (after `bed_count`):

```sql
    bell_count       INTEGER NOT NULL DEFAULT 0,
```

Update `insert_snapshot` signature and SQL to include `bell_count`:

```python
def insert_snapshot(conn, *, timestamp, players_online, area_center_x,
                    area_center_z, scan_radius, villager_count, bed_count,
                    bell_count=0, notes, zones_scanned=None, zones_skipped=None):
    """Insert a snapshot row and return its lastrowid."""
    cur = conn.execute(
        """
        INSERT INTO snapshots
            (timestamp, players_online, area_center_x, area_center_z,
             scan_radius, villager_count, bed_count, bell_count, notes,
             zones_scanned, zones_skipped)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (timestamp, players_online, area_center_x, area_center_z,
         scan_radius, villager_count, bed_count, bell_count, notes,
         zones_scanned, zones_skipped),
    )
    conn.commit()
    return cur.lastrowid
```

- [ ] **Step 5: Add migration for existing DBs**

In `_migrate()`, add after the `zones_skipped` migration:

```python
    cur = conn.execute("PRAGMA table_info(snapshots)")
    cols = {row[1] for row in cur.fetchall()}
    if "bell_count" not in cols:
        conn.execute("ALTER TABLE snapshots ADD COLUMN bell_count INTEGER NOT NULL DEFAULT 0")

    # Create bells table if missing (old DBs)
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS bells (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            snapshot_id     INTEGER NOT NULL REFERENCES snapshots(id),
            pos_x           INTEGER NOT NULL,
            pos_y           INTEGER NOT NULL,
            pos_z           INTEGER NOT NULL,
            free_tickets    INTEGER NOT NULL DEFAULT 0,
            villager_count  INTEGER NOT NULL DEFAULT 0,
            zone            TEXT,
            UNIQUE(snapshot_id, pos_x, pos_y, pos_z)
        );
    """)
```

- [ ] **Step 6: Add insert_bell function**

After `insert_bed`:

```python
def insert_bell(conn, *, snapshot_id, pos_x, pos_y, pos_z, free_tickets,
                villager_count=0, zone=None):
    """Insert a bell row. UNIQUE(snapshot_id, pos_x, pos_y, pos_z)."""
    cur = conn.execute(
        """
        INSERT INTO bells (snapshot_id, pos_x, pos_y, pos_z, free_tickets, villager_count, zone)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (snapshot_id, pos_x, pos_y, pos_z, free_tickets, villager_count, zone),
    )
    conn.commit()
    return cur.lastrowid
```

- [ ] **Step 7: Run tests**

```bash
python -m pytest tests/ -v
```

Expected: ALL PASS.

- [ ] **Step 8: Commit**

```bash
git add census_db.py tests/test_census_db.py
git commit -m "feat(census): add bells table, bell_count column, insert_bell helper"
```

---

### Task 3: Integrate bell scraping into census pipeline

**Files:**
- Modify: `villager-census/census.py:99-110` (POI download/filter), `:118-130` (snapshot insert), `:230-251` (bed insert section)

- [ ] **Step 1: Split parsed POIs into beds and bells**

Replace the current Step 5-6 in `census.py` (lines 99-110):

```python
    # Step 5: download and parse POI files
    poi_local_dir = Path("/tmp/census_poi")
    poi_paths = get_poi_files(poi_regions, poi_local_dir)
    all_pois = parse_poi_regions(poi_paths)

    # Step 6: filter POIs to bounding box (with margin) and split by type
    margin = 50
    def in_bounds(poi):
        return ((x_min - margin) <= poi["pos"][0] <= (x_max + margin)
                and (z_min - margin) <= poi["pos"][2] <= (z_max + margin))

    beds = [p for p in all_pois if p["type"] == "minecraft:home" and in_bounds(p)]
    bells = [p for p in all_pois if p["type"] == "minecraft:meeting" and in_bounds(p)]
```

- [ ] **Step 2: Add bell_count to snapshot insert**

In Step 7 (line 118-130), add `bell_count=len(bells)` to the `insert_snapshot` call:

```python
    snapshot_id = insert_snapshot(
        conn,
        timestamp=timestamp,
        players_online=json.dumps(players),
        area_center_x=cx,
        area_center_z=cz,
        scan_radius=scan_radius,
        villager_count=len(villagers),
        bed_count=len(beds),
        bell_count=len(bells),
        notes=notes,
        zones_scanned=json.dumps(zone_names_scanned),
        zones_skipped=json.dumps(skipped_zones),
    )
```

- [ ] **Step 3: Build meeting_point lookup and insert bells**

After Step 9 (bed insert, line 251), add Step 9b:

```python
    # Step 9b: classify and insert bells
    # Build meeting_point → villager count lookup
    meeting_point_counts = Counter()
    for v in villagers:
        mx = v.get("meeting_point_x")
        my = v.get("meeting_point_y")
        mz = v.get("meeting_point_z")
        if mx is not None and my is not None and mz is not None:
            meeting_point_counts[(int(mx), int(my), int(mz))] += 1

    bell_zone_counts = Counter()
    for bell in bells:
        bx, by, bz = bell["pos"][0], bell["pos"][1], bell["pos"][2]
        vcount = meeting_point_counts.get((int(bx), int(by), int(bz)), 0)
        bell_zone = classify_bed(zones, x=bx, z=bz)  # same zone logic as beds
        bell_zone_counts[bell_zone or "unclassified"] += 1
        insert_bell(
            conn,
            snapshot_id=snapshot_id,
            pos_x=bx,
            pos_y=by,
            pos_z=bz,
            free_tickets=bell.get("free_tickets", 0),
            villager_count=vcount,
            zone=bell_zone,
        )
```

- [ ] **Step 4: Add insert_bell import**

At the top of `census.py`, update the import from `census_db`:

```python
from census_db import (
    init_db, insert_snapshot, insert_villager, insert_villager_state,
    insert_trade, insert_inventory_item, insert_gossip, insert_bed,
    insert_bell, get_latest_snapshot, mark_dead,
)
```

- [ ] **Step 5: Run full test suite**

```bash
python -m pytest tests/ -v
```

Expected: ALL PASS.

- [ ] **Step 6: Commit**

```bash
git add census.py
git commit -m "feat(census): integrate bell scraping into census pipeline"
```

---

### Task 4: Add bell query to dashboard

**Files:**
- Modify: `disqt-minecraft/src/villagers/queries.js`

- [ ] **Step 1: Add getBellPositions query**

Add to `queries.js` after `getBedPositions`:

```js
export function getBellPositions(snapshotId, zoneNames) {
  return query(`
    SELECT pos_x, pos_z, zone, free_tickets, villager_count
    FROM bells
    WHERE snapshot_id = ? AND zone IN (${zoneInClause(zoneNames)})
  `, [snapshotId, ...zoneNames]);
}
```

- [ ] **Step 2: Commit**

```bash
cd /home/leo/documents/code/disqt.com/disqt-minecraft
git add src/villagers/queries.js
git commit -m "feat(villagers): add getBellPositions query"
```

---

### Task 5: Create icon constants module

**Files:**
- Create: `disqt-minecraft/src/villagers/icons.js`

- [ ] **Step 1: Create icons.js with Lucide SVG paths**

Copy the `d` attribute from Lucide SVGs. All paths are designed for a 24x24 viewBox with stroke-based rendering (stroke-width 2, stroke-linecap round, stroke-linejoin round, no fill).

```js
// src/villagers/icons.js
// Lucide icon SVG paths for map markers. 24x24 viewBox, stroke-based.
// Source: https://lucide.dev — MIT license.

export const ICONS = {
  user: 'M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z',
  bed: 'M2 4v16M2 8h18a2 2 0 0 1 2 2v10M2 17h20M6 8v9',
  bell: 'M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0',
  hammer: 'M15 12l-8.5 8.5c-.83.83-2.17.83-3 0 0 0 0 0 0 0a2.12 2.12 0 0 1 0-3L12 9M17.64 15 22 10.64M20.91 11.7l-1.25-1.25c-.6-.6-.93-1.4-.93-2.25V6.5a.5.5 0 0 0-.5-.5H16.5a3.17 3.17 0 0 1-2.25-.93L13 3.82M10.12 5.88l4 4',
  link: 'M9 17H7A5 5 0 0 1 7 7h2M15 7h2a5 5 0 1 1 0 10h-2M8 12h8',
  flame: 'M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z',
};

// Render a Lucide icon path into an SVG <g> group positioned at (cx, cy) with given size
export function iconMarker(g, cx, cy, iconName, size, bgColor, bgOpacity = 0.85) {
  const group = g.append('g')
    .attr('transform', `translate(${cx},${cy})`);

  // Background circle
  group.append('circle')
    .attr('r', size)
    .attr('fill', bgColor)
    .attr('fill-opacity', bgOpacity)
    .attr('stroke', 'rgba(255,255,255,0.3)')
    .attr('stroke-width', 0.5);

  // Icon path scaled to fit inside circle
  const iconScale = (size * 1.2) / 24;  // ~60% of circle diameter
  group.append('path')
    .attr('d', ICONS[iconName])
    .attr('transform', `scale(${iconScale}) translate(-12,-12)`)
    .attr('fill', 'none')
    .attr('stroke', '#fff')
    .attr('stroke-width', 2 / iconScale)  // compensate for scale
    .attr('stroke-linecap', 'round')
    .attr('stroke-linejoin', 'round')
    .attr('opacity', 0.9);

  return group;
}
```

- [ ] **Step 2: Commit**

```bash
git add src/villagers/icons.js
git commit -m "feat(villagers): add Lucide icon constants and marker renderer"
```

---

### Task 6: Rewrite map.js with new layer model

**Files:**
- Rewrite: `disqt-minecraft/src/villagers/views/map.js`

This is a full rewrite. The new map has:
- Two-tier controls: entity layer toggles + connection toggle
- Icon markers for all entities
- Tooltips on markers and lines
- Selection with POI highlight
- Click-to-deselect on empty space

- [ ] **Step 1: Write the new map.js**

```js
// src/villagers/views/map.js
// 2D position map with entity layers, icon markers, connection lines, tooltips.

import * as d3 from 'd3';
import { getZonesForPlace, getZoneColor } from '../zones.js';
import { getProfessionColor } from '../components/legend.js';
import { show as showTip, hide as hideTip } from '../components/tooltip.js';
import { getVillagerPositions, getBedPositions, getBellPositions } from '../queries.js';
import { getState, setState } from '../state.js';
import { iconMarker } from '../icons.js';

let svg, g, zoom;
let layers = { villagers: true, beds: true, bells: false, jobSites: false, heatmap: false, connections: false };

export function init(container) {
  container.innerHTML = `
    <div class="map-controls">
      <div class="map-control-group">
        <button class="map-toggle active" data-layer="villagers" title="Villagers">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M19 21v-2a4 4 0 0 0-4-4H9a4 4 0 0 0-4 4v2M12 3a4 4 0 1 0 0 8 4 4 0 0 0 0-8z"/></svg>
          Villagers
        </button>
        <button class="map-toggle active" data-layer="beds" title="Beds">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M2 4v16M2 8h18a2 2 0 0 1 2 2v10M2 17h20M6 8v9"/></svg>
          Beds
        </button>
        <button class="map-toggle" data-layer="bells" title="Bells">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9M10.3 21a1.94 1.94 0 0 0 3.4 0"/></svg>
          Bells
        </button>
        <button class="map-toggle" data-layer="jobSites" title="Job Sites">
          <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M15 12l-8.5 8.5c-.83.83-2.17.83-3 0 0 0 0 0 0 0a2.12 2.12 0 0 1 0-3L12 9M17.64 15 22 10.64M20.91 11.7l-1.25-1.25c-.6-.6-.93-1.4-.93-2.25V6.5a.5.5 0 0 0-.5-.5H16.5a3.17 3.17 0 0 1-2.25-.93L13 3.82M10.12 5.88l4 4"/></svg>
          Job Sites
        </button>
      </div>
      <div class="map-control-sep"></div>
      <button class="map-toggle" data-layer="heatmap" title="Heatmap">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M8.5 14.5A2.5 2.5 0 0 0 11 12c0-1.38-.5-2-1-3-1.072-2.143-.224-4.054 2-6 .5 2.5 2 4.9 4 6.5 2 1.6 3 3.5 3 5.5a7 7 0 1 1-14 0c0-1.153.433-2.294 1-3a2.5 2.5 0 0 0 2.5 2.5z"/></svg>
        Heatmap
      </button>
      <div class="map-control-sep"></div>
      <button class="map-toggle" data-layer="connections" title="Show Connections">
        <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M9 17H7A5 5 0 0 1 7 7h2M15 7h2a5 5 0 1 1 0 10h-2M8 12h8"/></svg>
        Connections
      </button>
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

  // Click empty space to deselect
  svg.on('click', (event) => {
    if (event.target === svg.node()) {
      setState({ selectedVillager: null });
    }
  });

  // Layer toggle handlers
  container.querySelectorAll('.map-toggle').forEach((btn) => {
    btn.addEventListener('click', () => {
      const layer = btn.dataset.layer;
      layers[layer] = !layers[layer];
      btn.classList.toggle('active', layers[layer]);

      // Heatmap and villagers are mutually exclusive
      if (layer === 'heatmap' && layers.heatmap) {
        layers.villagers = false;
        container.querySelector('[data-layer="villagers"]').classList.remove('active');
      } else if (layer === 'villagers' && layers.villagers) {
        layers.heatmap = false;
        container.querySelector('[data-layer="heatmap"]').classList.remove('active');
      }

      const event = new CustomEvent('layers-changed');
      container.dispatchEvent(event);
    });
  });
}

export function update(container, snapshotId, zoneNames) {
  const { activePlace, selectedVillager } = getState();
  const ZONES = getZonesForPlace(activePlace);
  const villagers = getVillagerPositions(snapshotId, zoneNames);
  const beds = getBedPositions(snapshotId, zoneNames);

  // bells query — graceful fallback if table doesn't exist yet
  let bells = [];
  try { bells = getBellPositions(snapshotId, zoneNames); } catch (e) { /* table may not exist */ }

  // Compute bounds from zone config
  const allX = ZONES.flatMap((z) => [z.x_min, z.x_max]);
  const allZ = ZONES.flatMap((z) => [z.z_min, z.z_max]);
  const margin = 20;
  const xExtent = [Math.min(...allX) - margin, Math.max(...allX) + margin];
  const zExtent = [Math.min(...allZ) - margin, Math.max(...allZ) + margin];

  const width = parseInt(svg.attr('width'));
  const height = parseInt(svg.attr('height'));

  const x = d3.scaleLinear().domain(xExtent).range([0, width]);
  const z = d3.scaleLinear().domain(zExtent).range([0, height]); // negative Z (north) at top

  g.selectAll('*').remove();

  // Zone boundaries
  ZONES.forEach((zone) => {
    g.append('rect')
      .attr('x', x(zone.x_min)).attr('y', z(zone.z_min))
      .attr('width', x(zone.x_max) - x(zone.x_min))
      .attr('height', z(zone.z_max) - z(zone.z_min))
      .attr('fill', zone.color).attr('fill-opacity', 0.08)
      .attr('stroke', zone.color).attr('stroke-opacity', 0.3);

    g.append('text')
      .attr('x', x((zone.x_min + zone.x_max) / 2))
      .attr('y', z((zone.z_min + zone.z_max) / 2))
      .attr('text-anchor', 'middle').attr('fill', zone.color)
      .attr('font-size', '11px').attr('opacity', 0.5)
      .text(zone.name);
  });

  // --- Heatmap layer ---
  if (layers.heatmap) {
    const cellSize = 4;
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
        .attr('x', x(gx * cellSize)).attr('y', z(gz * cellSize))
        .attr('width', Math.abs(x(gx * cellSize + cellSize) - x(gx * cellSize)))
        .attr('height', Math.abs(z((gz + 1) * cellSize) - z(gz * cellSize)))
        .attr('fill', colorScale(count)).attr('opacity', 0.6);
    });
  }

  // --- Connection lines (drawn before markers so markers render on top) ---
  if (layers.connections || selectedVillager) {
    villagers.forEach((v) => {
      if (v.pos_x == null || v.pos_z == null) return;
      const isSelected = v.villager_uuid === selectedVillager;
      // When connections toggle is off, only draw for selected villager
      if (!layers.connections && !isSelected) return;
      const lineOpacity = isSelected ? 0.7 : 0.25;
      const lineWidth = isSelected ? 1.5 : 0.5;
      const dash = isSelected ? '4,3' : 'none';

      const drawLine = (tx, tz, color, label) => {
        const line = g.append('line')
          .attr('x1', x(v.pos_x)).attr('y1', z(v.pos_z))
          .attr('x2', x(tx)).attr('y2', z(tz))
          .attr('stroke', color).attr('stroke-width', lineWidth)
          .attr('opacity', lineOpacity).attr('stroke-dasharray', dash)
          .style('cursor', 'default');

        line.on('mouseover', (event) => {
          showTip(`<strong>${label}</strong><br>${v.villager_uuid.slice(0, 8)}...`, event.pageX, event.pageY);
        });
        line.on('mouseout', () => hideTip());
      };

      if ((layers.beds || isSelected) && v.home_x != null) {
        drawLine(v.home_x, v.home_z, '#44cc88', 'Home');
      }
      if ((layers.bells || isSelected) && v.meeting_point_x != null) {
        drawLine(v.meeting_point_x, v.meeting_point_z, '#cc88ff', 'Meeting point');
      }
      if ((layers.jobSites || isSelected) && v.job_site_x != null) {
        drawLine(v.job_site_x, v.job_site_z, '#ff9f43', 'Job site');
      }
    });
  }

  // --- Bed markers ---
  if (layers.beds) {
    beds.forEach((b) => {
      const color = b.claimed_by ? '#44cc88' : '#ef4444';
      const dimmed = selectedVillager && true;  // dim all POI markers when a villager is selected
      const marker = iconMarker(g, x(b.pos_x), z(b.pos_z), 'bed', 5, color, dimmed ? 0.3 : 0.8);
      marker.style('cursor', 'pointer');

      marker.on('mouseover', (event) => {
        const claim = b.claimed_by ? `Claimed by ${b.claimed_by.slice(0, 8)}...` : 'Unclaimed';
        showTip(`<strong>Bed</strong><br>${claim}<br>Zone: ${b.zone || '?'}<br>Free tickets: ${b.free_tickets}`, event.pageX, event.pageY);
      });
      marker.on('mouseout', () => hideTip());
    });
  }

  // --- Bell markers ---
  if (layers.bells) {
    bells.forEach((b) => {
      const color = b.villager_count > 0 ? '#44cc88' : '#ef4444';
      const dimmed = selectedVillager && true;
      const marker = iconMarker(g, x(b.pos_x), z(b.pos_z), 'bell', 5, color, dimmed ? 0.3 : 0.8);
      marker.style('cursor', 'pointer');

      marker.on('mouseover', (event) => {
        const status = b.villager_count > 0 ? `${b.villager_count} villager(s) gather here` : 'No villagers';
        showTip(`<strong>Bell</strong><br>${status}<br>Zone: ${b.zone || '?'}<br>Free tickets: ${b.free_tickets}`, event.pageX, event.pageY);
      });
      marker.on('mouseout', () => hideTip());
    });
  }

  // --- Job site markers ---
  if (layers.jobSites) {
    villagers.forEach((v) => {
      if (v.job_site_x == null || v.job_site_z == null) return;
      const dimmed = selectedVillager && v.villager_uuid !== selectedVillager;
      const marker = iconMarker(g, x(v.job_site_x), z(v.job_site_z), 'hammer', 4, '#ff9f43', dimmed ? 0.2 : 0.75);
      marker.style('cursor', 'pointer');

      marker.on('mouseover', (event) => {
        showTip(`<strong>Job site</strong><br>${v.profession || 'none'}<br>${v.villager_uuid.slice(0, 8)}...`, event.pageX, event.pageY);
      });
      marker.on('mouseout', () => hideTip());
    });
  }

  // --- Villager dots ---
  if (layers.villagers && !layers.heatmap) {
    villagers.forEach((v) => {
      if (v.pos_x == null || v.pos_z == null) return;
      const isSelected = selectedVillager === v.villager_uuid;
      const dimmed = selectedVillager && !isSelected;

      const marker = iconMarker(g, x(v.pos_x), z(v.pos_z), 'user',
        isSelected ? 7 : 5, getProfessionColor(v.profession), dimmed ? 0.2 : 0.85);
      marker.style('cursor', 'pointer');

      marker.on('mouseover', (event) => {
        showTip(`
          <strong>${v.profession || 'none'}</strong><br>
          Zone: ${v.zone || '?'}<br>
          Health: ${v.health}<br>
          ${v.villager_uuid.slice(0, 8)}...
        `, event.pageX, event.pageY);
      });
      marker.on('mouseout', () => hideTip());
      marker.on('click', (event) => {
        event.stopPropagation();
        setState({ selectedVillager: selectedVillager === v.villager_uuid ? null : v.villager_uuid });
      });
      marker.on('dblclick', (event) => {
        event.stopPropagation();
        setState({ activeView: 'tracker', selectedVillager: v.villager_uuid });
      });
    });
  }

  // --- Selected villager highlight ring + POI markers ---
  if (selectedVillager) {
    const sv = villagers.find((v) => v.villager_uuid === selectedVillager);
    if (sv && sv.pos_x != null && sv.pos_z != null) {
      g.append('circle')
        .attr('cx', x(sv.pos_x)).attr('cy', z(sv.pos_z))
        .attr('r', 12)
        .attr('fill', 'none')
        .attr('stroke', '#fff')
        .attr('stroke-width', 2)
        .attr('stroke-dasharray', '3,2')
        .attr('opacity', 0.9);

      // Always show selected villager's POI markers
      if (sv.home_x != null) {
        iconMarker(g, x(sv.home_x), z(sv.home_z), 'bed', 6, '#44cc88', 0.9);
      }
      if (sv.job_site_x != null) {
        iconMarker(g, x(sv.job_site_x), z(sv.job_site_z), 'hammer', 5, '#ff9f43', 0.9);
      }
      if (sv.meeting_point_x != null) {
        iconMarker(g, x(sv.meeting_point_x), z(sv.meeting_point_z), 'bell', 5, '#cc88ff', 0.9);
      }
    }
  }

  // Re-render on layer toggle
  container.removeEventListener('layers-changed', container._layerHandler);
  container._layerHandler = () => update(container, snapshotId, zoneNames);
  container.addEventListener('layers-changed', container._layerHandler);
}
```

- [ ] **Step 2: Commit**

```bash
git add src/villagers/views/map.js
git commit -m "feat(villagers): rewrite map with entity layers, icon markers, tooltips"
```

---

### Task 7: Update CSS for new map controls

**Files:**
- Modify: `disqt-minecraft/src/pages/villagers.astro` (CSS section)

- [ ] **Step 1: Replace map-controls CSS**

Replace the existing `.map-controls` CSS block with:

```css
/* Map controls */
.map-controls {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 0;
  font-size: 11px;
  color: var(--text-dim);
  flex-wrap: wrap;
  border-bottom: 1px solid var(--glass-border);
  margin-bottom: 12px;
  padding-bottom: 12px;
}
.map-control-group { display: flex; gap: 6px; }
.map-control-sep { width: 1px; height: 24px; background: var(--glass-border); margin: 0 4px; }
.map-toggle {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 5px 10px;
  border-radius: 6px;
  border: 1px solid var(--glass-border);
  background: none;
  color: var(--text-dim);
  font-family: var(--ui);
  font-size: 11px;
  cursor: pointer;
  transition: all 0.2s;
}
.map-toggle svg { flex-shrink: 0; }
.map-toggle:hover { color: var(--text); border-color: rgba(255,255,255,0.15); }
.map-toggle.active {
  color: var(--text-bright);
  background: var(--accent-dim);
  border-color: rgba(91, 168, 255, 0.25);
}
```

- [ ] **Step 2: Build and verify**

```bash
cd /home/leo/documents/code/disqt.com/disqt-minecraft
npm run build
```

Expected: Build succeeds, ~100 kB client bundle.

- [ ] **Step 3: Commit**

```bash
git add src/pages/villagers.astro
git commit -m "feat(villagers): update CSS for pill-style map layer controls"
```

---

### Task 8: Deploy and verify

- [ ] **Step 1: Run the census with bell scraping**

SSH to VPS and trigger a census run to populate bell data:

```bash
ssh dev
cd /home/dev/villager-census
python census.py
```

Verify bells were found in the output log.

- [ ] **Step 2: Push dashboard changes**

```bash
cd /home/leo/documents/code/disqt.com/disqt-minecraft
git push origin main
```

Wait for auto-deploy.

- [ ] **Step 3: Verify in browser**

Open `https://disqt.com/minecraft/villagers/` and check:
- Pill-style toggle buttons with icons render in map controls
- Villager/bed/bell/job site markers show as circles with icons on zoom
- Toggling layers on/off updates the map correctly
- Heatmap and Villagers are mutually exclusive
- Connections toggle draws dashed lines between villagers and their visible POIs
- Hovering any marker or line shows a tooltip
- Click villager → highlight + POI lines/markers, dim others
- Re-click → deselect
- Double-click → tracker view
- Click empty space → deselect
- Bells show green (active) vs red (unclaimed)

- [ ] **Step 4: Commit any fixes**

```bash
git add -A
git commit -m "fix(villagers): post-deploy map fixes"
git push origin main
```
