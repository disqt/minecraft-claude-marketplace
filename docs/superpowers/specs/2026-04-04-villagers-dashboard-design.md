# Villagers Dashboard — Design Spec

**Page:** `disqt.com/minecraft/villagers/`
**Date:** 2026-04-04

## Overview

An interactive dashboard for exploring villager census data collected by the automated census cron. Serves as both a monitoring glance (are populations healthy?) and an exploration tool (where do villagers move? who's doing what?).

## Architecture

### Data Pipeline

1. Census cron runs every 30 min on VPS, writes to SQLite at `/home/dev/villager-census/census.db`
2. Nginx serves the DB file at `/minecraft/villagers/census.db` (static file, Cache-Control for 30 min)
3. Browser page loads **sql.js** (SQLite compiled to WASM, ~1 MB cached) and fetches the DB file
4. D3.js queries SQL directly client-side and renders all views

No export step, no JSON generation, no build pipeline for data. The page always reads the latest DB.

### Tech Stack

- **Astro SSR page** in the `disqt-minecraft` app — fits existing deploy pattern (auto-deploys on push)
- **sql.js** (~1 MB WASM) — client-side SQLite
- **D3.js** (~80 KB) with `d3-sankey` plugin — all visualizations
- Zero server-side data processing

### Page in the Astro App

New page at `src/pages/villagers.astro`. Client-side JS handles all data loading and rendering. The Astro page provides the shell, loads the scripts, and includes the D3/sql.js dependencies.

## Page Layout

```
┌─────────────────────────────────────────────────┐
│  Header: Place name, last census timestamp,     │
│          coverage indicator (full/partial)       │
├─────────────────────────────────────────────────┤
│  Zone Cards (N cards, dynamic from data)        │
│  Each: name, population, beds, homeless,        │
│        sparkline of population over time         │
│  Plus a "Total" summary card                    │
├─────────────────────────────────────────────────┤
│  [ Map ] [ Flows ] [ Compare ] [ Tracker ]      │
│  ┌─────────────────────────────────────────────┐│
│  │                                             ││
│  │          Active view renders here           ││
│  │                                             ││
│  └─────────────────────────────────────────────┘│
│  Snapshot slider (shared across all views)       │
└─────────────────────────────────────────────────┘
```

The snapshot slider is global — scrubbing it updates whichever view is active.

## Zone Cards

Dynamic grid of cards, one per zone found in the data plus a totals card. Each card shows:

- Zone name
- Current villager count with delta from previous snapshot (e.g. "51 (+3)")
- Bed count and homeless count
- Profession breakdown (compact: top 3 + "N others")
- Sparkline: population over all snapshots (tiny inline D3 line chart)

**Data source:** `SELECT zone, COUNT(*) FROM villager_states WHERE snapshot_id = ? GROUP BY zone` across all snapshots.

Zone list is derived from `SELECT DISTINCT zone FROM villager_states WHERE zone IS NOT NULL`, not hardcoded.

## Views

### Map View

2D scatter plot of the census area. Axes are Minecraft X and Z coordinates (Z inverted so north is up).

**Layers (toggleable):**

- **Villagers** — dots color-coded by profession, sized by health
- **Beds** — smaller markers, color indicates claimed (green) vs unclaimed (red)
- **Job sites** — workstation positions from `job_site_x/y/z`, connected to their villager by a thin line
- **Meeting points** — gathering positions from `meeting_point_x/y/z`, connected to their villager
- **Homes** — bed positions from `home_x/y/z`, connected to their villager
- **Zone boundaries** — rectangles drawn from zone config (loaded from `zones_scanned` metadata or a static config)

**Interactions:**

- Hover a villager: tooltip with name/profession/zone/health
- Click a villager: opens Tracker view for that UUID
- Snapshot slider: animates dot positions between snapshots (D3 transitions)
- Zoom and pan

**Data source:** `SELECT pos_x, pos_z, profession, health, zone, home_x, home_z, job_site_x, job_site_z, meeting_point_x, meeting_point_z FROM villager_states WHERE snapshot_id = ?`

### Flows View (Alluvial/Sankey)

Vertical alluvial diagram showing population flows between zones across consecutive snapshots.

- Each snapshot is a vertical column
- Zones are nodes within each column (height proportional to population)
- Ribbons connect zones between consecutive snapshots
  - Width = number of villagers that stayed in or moved to that zone
  - Color by source zone
- Special nodes for "born" (new UUIDs) and "died" (disappeared UUIDs)

**Data source:** Join `villager_states` on consecutive `snapshot_id`s, compare `zone` per `villager_uuid` to compute exact migration flows.

```sql
SELECT
  prev.zone AS from_zone,
  curr.zone AS to_zone,
  COUNT(*) AS count
FROM villager_states curr
JOIN villager_states prev
  ON curr.villager_uuid = prev.villager_uuid
  AND prev.snapshot_id = ?  -- previous snapshot
  AND curr.snapshot_id = ?  -- current snapshot
GROUP BY prev.zone, curr.zone
```

Births/deaths derived from UUIDs present in one snapshot but not the other.

### Compare View

Pick two snapshots from dropdowns. Shows:

- **Population delta** — per-zone count changes
- **Births table** — new villager UUIDs with profession, zone, position
- **Deaths table** — disappeared UUIDs with last known profession, zone, position
- **Migration matrix** — zone-to-zone flow counts (origin-destination table)
- **Profession changes** — villagers who changed profession between the two snapshots

**Data source:** Two queries on `villager_states` for the two selected snapshot IDs, diffed client-side.

### Tracker View

Deep dive on a single villager. Accessed by clicking a villager on the map, selecting from a searchable list, or from births/deaths in Compare view.

Shows:

- **Identity** — UUID, spawn reason, origin position, first/last seen, alive/dead status
- **Position trail** — all historical positions plotted on a mini-map with numbered waypoints
- **Timeline** — horizontal timeline showing zone, profession, and health at each snapshot
- **Trades** — current trade offers (if any)
- **Inventory** — items held
- **Gossip** — reputation data (gossip type + value towards other players)
- **Anchors** — current home, job site, meeting point positions

**Data source:** `get_villager_history` equivalent — join `villager_states` with `snapshots` for timestamp, plus `villager_trades`, `villager_inventory`, `villager_gossip` for the selected snapshot.

## Heatmap Mode

A toggle on the Map View (not a separate tab). Replaces individual dots with a density heatmap grid. Cell color intensity = villager count in that grid cell.

Combined with the snapshot slider, this shows population density shifting over time.

Grid resolution: ~16 blocks per cell (one Minecraft chunk) feels natural.

## Zone Boundaries

Zone geometry (rectangles + circles) needs to be available client-side for the map overlay. Options:

1. **Embed in the Astro page** as a static JSON config (simplest, matches `zones.toml`)
2. **Store in the DB** as a zones table (self-contained, but adds schema complexity)
3. **Serve `zones.toml`** as a static file and parse client-side

**Decision:** Option 1 — static JSON embedded in the page. Zone boundaries change rarely and are already defined in `zones.toml`. The Astro page can import them at build time.

## Snapshot Slider

Horizontal range slider below the active view. Shows all available snapshots with timestamps.

- Scrubbing updates the active view (map repositions, Sankey highlights, etc.)
- Tick marks at each snapshot timestamp
- Current snapshot timestamp displayed
- Play button for auto-advancing through snapshots (animation mode)
- Coverage indicator per tick: full (all zones) vs partial (some zones skipped)

## DB Schema — No Changes Needed

Audited all views against the current schema. Every field needed for every visualization is already stored:

- Positions: `pos_x/y/z`, `home_x/y/z`, `job_site_x/y/z`, `meeting_point_x/y/z`
- Identity: `uuid`, `spawn_reason`, `origin_x/y/z`, `presumed_dead`, `death_snapshot`
- State: `profession`, `health`, `zone`, `ticks_lived`, `age`
- Relations: `villager_trades`, `villager_inventory`, `villager_gossip`
- Coverage: `zones_scanned`, `zones_skipped` on snapshots
- Runs: `census_runs` for monitoring cron health

No schema migration required.

## Nginx Config

Add a location block to serve the DB file:

```nginx
location /minecraft/villagers/census.db {
    alias /home/dev/villager-census/census.db;
    add_header Cache-Control "public, max-age=1800";  # 30 min
    add_header Content-Type "application/octet-stream";
}
```

## Deploy

Same as existing `disqt-minecraft` app:
1. Add `villagers.astro` page + client-side JS
2. Push to main → GitHub Actions builds and restarts
3. Nginx serves the DB file separately (one-time config)

## Non-Goals (v1)

- Real-time updates (polling/websockets) — 30 min cache is fine
- Server-side rendering of charts — all client-side
- Multi-place support in the UI — v1 shows one place (whichever census is running), extensible later
- Mobile optimization — desktop-first, responsive is nice-to-have
