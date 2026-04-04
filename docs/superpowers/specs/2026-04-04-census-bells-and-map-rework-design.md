# Census Bell POIs + Map Rework — Design Spec

**Date:** 2026-04-04

## Overview

Two linked changes: (1) add bell scraping to the villager census tool so bells appear as POI data in the DB, and (2) redesign the dashboard map view with a cleaner entity/connection layer model, icon markers, and tooltips on everything.

## Part 1: Bell POI Scraping

### Background

The census tool already scrapes bed POIs from Minecraft's `poi/` region files (`minecraft:home` type). Bells are another POI type in the same files (`minecraft:meeting`). The parsing infrastructure is identical — just a different type filter.

### Data Model

Bells parallel beds:

| Concept | Beds | Bells |
|---------|------|-------|
| World block POI type | `minecraft:home` | `minecraft:meeting` |
| Villager memory field | `home_x/y/z` | `meeting_point_x/y/z` |
| Relationship | 1 bed → 1 villager (claimed_by) | 1 bell → N villagers (villager_count) |
| "Unclaimed" means | No villager sleeps here | No villager gathers here |

### DB Schema

New `bells` table:

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

`villager_count` is computed during census by counting villagers whose `meeting_point_x/y/z` matches the bell position (rounded to int). A bell with `villager_count = 0` is "unclaimed" — no villager considers it their gathering point.

Add `bell_count` column to `snapshots` table (parallel to `bed_count`).

### Census Pipeline Changes

`census_poi.py`:
- Extend byte pre-filter to check for `b"minecraft:meeting"` alongside `b"minecraft:home"`
- Return a `type` field in each result so callers can separate beds from bells

`census.py`:
- Split parsed POIs into beds and bells lists by type
- Filter bells to bounding box (same margin as beds)
- Build `meeting_point_to_uuid` lookup (like `home_to_uuid` for beds, but accumulates a count since multiple villagers share bells)
- Insert bells with `villager_count` computed from the lookup

## Part 2: Map View Rework

### Entity/Connection Layer Model

Replace the current flat checkbox list with a two-tier system:

**Entity layers** (toggle which things appear as markers):

| Layer | Data source | Marker style | Color logic |
|-------|------------|--------------|-------------|
| Villagers | `villager_states` | Circle + user icon | Profession color |
| Beds | `beds` table | Circle + bed icon | Green=claimed, red=unclaimed |
| Bells | `bells` table | Circle + bell icon | Green=active (villager_count>0), red=unclaimed |
| Job Sites | `villager_states.job_site_x/z` | Circle + hammer icon | Orange always |
| Heatmap | `villager_states` | Grid cells | Yellow→Red density |

**Connection toggle** (one button):

| Toggle | Effect |
|--------|--------|
| Show Connections | Draw dashed lines from each villager to their POIs, but only for POI types whose entity layer is currently visible |

Example: Villagers ON + Beds ON + Connections ON → villager→bed lines visible. Turn off Beds → those lines disappear. Turn on Bells → villager→bell lines appear.

Heatmap and Villagers remain mutually exclusive.

### Markers

Each marker is an SVG `<g>` group:
- Colored circle background (radius ~5)
- White Lucide icon path scaled to fit inside (~60% of circle diameter)

Icon paths embedded as constants (no npm dependency). Source: Lucide icon set.

| Entity | Lucide icon name | SVG `d` path |
|--------|-----------------|--------------|
| Villager | `user` | (copy from lucide) |
| Bed | `bed` | (copy from lucide) |
| Bell | `bell` | (copy from lucide) |
| Job Site | `hammer` | (copy from lucide) |

At low zoom, icons are too small to read — the colored circle carries meaning. On zoom-in, icons become legible.

### Tooltips

Every interactive element gets a tooltip on hover:

| Element | Tooltip content |
|---------|----------------|
| Villager dot | Profession, zone, health, UUID snippet |
| Bed marker | Zone, "Claimed by [UUID snippet]" or "Unclaimed", free tickets |
| Bell marker | Zone, "N villagers gather here" or "No villagers", free tickets |
| Job site marker | "Job site for [UUID snippet] ([profession])" |
| Connection line | Relationship type ("Home", "Job site", "Meeting point") + villager UUID snippet |

### Selection Behavior

- **Click villager**: Highlight selected, dim all others to 0.2 opacity. Show ALL of that villager's POI connections and markers (regardless of layer toggles). Dashed ring around selected.
- **Re-click same villager**: Deselect, restore normal view.
- **Double-click villager**: Navigate to Tracker view with that villager selected.
- **Click empty space**: Deselect any selected villager.

### Control Bar Layout

```
[icon] Villagers  [icon] Beds  [icon] Bells  [icon] Job Sites  |  [icon] Heatmap  |  [icon] Connections
```

Pill-style toggle buttons with the Lucide icon + label. Active state: accent-colored background. Separated into groups: entity layers | density | connections.

### Dashboard Query: Bells

New query function `getBellPositions(snapshotId, zoneNames)`:

```sql
SELECT pos_x, pos_z, zone, free_tickets, villager_count
FROM bells
WHERE snapshot_id = ? AND zone IN (...)
```
