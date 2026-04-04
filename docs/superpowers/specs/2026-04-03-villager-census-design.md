# Villager Census — Design Spec

**Date:** 2026-04-03
**Status:** Draft

## Purpose

Track the Minecraft villager population in Piwigord over time. Store every piece of entity data so we can answer questions like: where do villagers sleep vs wander, who survived events, population trends, bed occupancy rates, gossip propagation, and trade economy evolution.

## Context

- PaperMC 1.21.11 server at `ssh minecraft`
- Piwigord area: roughly x=3050-3250, z=-1100 to -750
- ~130 villagers currently, 38 beds (from POI data)
- Simulation distance 8 chunks (128 blocks) — villagers are frozen ~88% of real time (only active when a player is nearby)
- Data collection is manual: user invokes a census skill every few days
- Expected volume: ~130 villagers x ~100 snapshots/year = ~13k state rows/year

## Database

**SQLite** — single `.db` file stored at `villager-census/census.db` in this repo.

Reasons: already installed on VPS (3.40), Python stdlib support, zero maintenance, trivially backed up, real SQL for cross-snapshot queries, Grafana-compatible via plugin. The data volume (~13k rows/year for the largest table) is far below any performance concern.

## Schema

### `snapshots`

One row per census run.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| timestamp | TEXT | ISO 8601 UTC |
| players_online | TEXT | JSON array of player names online at time of census |
| area_center_x | INTEGER | Center of scanned area |
| area_center_z | INTEGER | Center of scanned area |
| scan_radius | INTEGER | Radius in blocks |
| villager_count | INTEGER | Total villagers found |
| bed_count | INTEGER | Total beds found (from POI) |
| notes | TEXT | Optional free-text (e.g. "post-culling census") |

### `villagers`

One row per unique villager UUID. Identity data that never changes. Upserted on each census (first-seen stays, last-seen updates).

| Column | Type | Description |
|--------|------|-------------|
| uuid | TEXT PK | Hex UUID (e.g. `0a077d31-a230-41b5-bf50-c74d83892338`) |
| first_seen_snapshot | INTEGER FK | Snapshot where this villager first appeared |
| last_seen_snapshot | INTEGER FK | Most recent snapshot containing this villager |
| spawn_reason | TEXT | `BREEDING`, `DEFAULT`, etc. (from `Paper.SpawnReason`) |
| origin_x | REAL | Birth position x (from `Paper.Origin`) |
| origin_y | REAL | Birth position y |
| origin_z | REAL | Birth position z |
| presumed_dead | INTEGER | 1 if disappeared between snapshots, 0 otherwise |
| death_snapshot | INTEGER FK | Snapshot where villager was last seen before disappearing |

### `villager_states`

One row per villager per snapshot. The main time-series table.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| snapshot_id | INTEGER FK | References `snapshots.id` |
| villager_uuid | TEXT FK | References `villagers.uuid` |
| pos_x | REAL | Current x |
| pos_y | REAL | Current y |
| pos_z | REAL | Current z |
| health | REAL | Current HP (max 20) |
| food_level | INTEGER | Food level |
| profession | TEXT | `farmer`, `librarian`, `none`, etc. |
| profession_level | INTEGER | Trade level (1-5) |
| villager_type | TEXT | Biome type (`plains`, `taiga`, etc.) |
| xp | INTEGER | Villager XP |
| ticks_lived | INTEGER | `Spigot.ticksLived` — total active ticks |
| age | INTEGER | 0 = adult, negative = baby |
| home_x | INTEGER | Bed position x (NULL if homeless) |
| home_y | INTEGER | Bed position y |
| home_z | INTEGER | Bed position z |
| job_site_x | INTEGER | Workstation x (NULL if unemployed) |
| job_site_y | INTEGER | Workstation y |
| job_site_z | INTEGER | Workstation z |
| meeting_point_x | INTEGER | Meeting point x (NULL if none) |
| meeting_point_y | INTEGER | Meeting point y |
| meeting_point_z | INTEGER | Meeting point z |
| last_slept | INTEGER | Game tick of last sleep |
| last_woken | INTEGER | Game tick of last wake |
| last_worked | INTEGER | Game tick of last work at POI |
| last_restock | INTEGER | Game tick of last restock |
| restocks_today | INTEGER | Number of restocks today |
| on_ground | INTEGER | 1/0 |
| last_gossip_decay | INTEGER | Game tick of last gossip decay |

**Unique constraint:** `(snapshot_id, villager_uuid)`

### `villager_trades`

One row per trade offer per villager per snapshot.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| snapshot_id | INTEGER FK | |
| villager_uuid | TEXT FK | |
| slot | INTEGER | Trade slot index (0-based) |
| buy_item | TEXT | e.g. `emerald` |
| buy_count | INTEGER | |
| buy_b_item | TEXT | Second buy slot (NULL if none) |
| buy_b_count | INTEGER | |
| sell_item | TEXT | e.g. `cooked_cod` |
| sell_count | INTEGER | |
| price_multiplier | REAL | |
| max_uses | INTEGER | |
| xp | INTEGER | XP reward for this trade |

### `villager_inventory`

One row per item stack per villager per snapshot.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| snapshot_id | INTEGER FK | |
| villager_uuid | TEXT FK | |
| item | TEXT | e.g. `wheat`, `beetroot_seeds` |
| count | INTEGER | |

### `villager_gossip`

One row per gossip entry per villager per snapshot.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| snapshot_id | INTEGER FK | |
| villager_uuid | TEXT FK | |
| gossip_type | TEXT | `major_negative`, `minor_negative`, `trading`, `major_positive`, `minor_positive` |
| target_uuid | TEXT | Hex UUID of the gossip target (player or villager) |
| value | INTEGER | Gossip strength (0-200) |

### `beds`

One row per bed per snapshot. Parsed from POI region files.

| Column | Type | Description |
|--------|------|-------------|
| id | INTEGER PK | Auto-increment |
| snapshot_id | INTEGER FK | |
| pos_x | INTEGER | |
| pos_y | INTEGER | |
| pos_z | INTEGER | |
| free_tickets | INTEGER | Available claim slots |
| claimed_by | TEXT | Villager UUID whose `home` matches this position (NULL if unclaimed) |

**Unique constraint:** `(snapshot_id, pos_x, pos_y, pos_z)`

## Data Collection Pipeline

The census skill runs these steps:

1. **Check a player is online and near Piwigord** — chunks must be loaded or entity data is unavailable
2. **Dump villager entities** — `execute as @e[type=minecraft:villager,...] run data get entity @s` via tmux console, capture from `latest.log`
3. **Parse entity dumps** — regex extraction of all fields from MC's SNBT format (same approach proven in this session)
4. **Download POI region files** — `scp` the relevant `poi/r.X.Z.mca` files, parse NBT for `minecraft:home` entries
5. **Cross-reference beds** — match each bed position to a villager's `Brain.home` to determine `claimed_by`
6. **Detect deaths** — any UUID in `villagers` table with `last_seen_snapshot = previous` but missing from current census gets `presumed_dead = 1`
7. **Write to SQLite** — upsert villagers, insert new snapshot + state rows + child tables
8. **Report summary** — print population delta, new births, deaths, homeless count, bed occupancy

## Key Queries Enabled

- **Population over time:** `SELECT s.timestamp, s.villager_count, s.bed_count FROM snapshots s ORDER BY s.timestamp`
- **Villager travel:** `SELECT pos_x, pos_z FROM villager_states WHERE villager_uuid = ? ORDER BY snapshot_id` — shows movement between censuses
- **Bed occupancy rate:** beds with `claimed_by IS NOT NULL` / total beds per snapshot
- **Survivors of an event:** villagers present in both the pre-event and post-event snapshots
- **Homeless population:** `villager_states WHERE home_x IS NULL` grouped by snapshot
- **Gossip decay tracking:** gossip value for a given target across snapshots
- **Profession distribution over time:** `GROUP BY profession, snapshot_id`
- **Trade economy:** which trades exist, how many max uses remain
- **Birth rate:** new UUIDs appearing per snapshot with `spawn_reason = 'BREEDING'`
- **Who's been hurt:** health < 20, `last_hurt_by_mob` tracking

## File Layout

```
plugins/minecraft-papermc-server/
  skills/villager-census/
    SKILL.md                # Skill entry point
    references/             # Reference docs for the skill
  agents/                   # Any parallel agents if needed

villager-census/            # Python tooling (repo root level)
  census.py                 # CLI entry point + pipeline orchestration
  census_collect.py         # Entity data collection (tmux commands, log parsing)
  census_parse.py           # SNBT parsing into structured dicts
  census_poi.py             # POI region file parsing for beds
  census_db.py              # SQLite schema, upserts, queries
  census_report.py          # Summary output after census
  census_seed.py            # One-time historical seeding from March 30 logs
  census.db                 # SQLite database (gitignored)
```

All stdlib Python — no pip dependencies. Reuses the NBT parsing approach from `world-migration-cli/migrate_nbt.py` for POI files.

## Invocation

A Claude Code skill (`/villager-census`) that:

1. SSHs to the Minecraft server
2. Verifies a player is online and near the target area (chunks must be loaded)
3. Runs entity data collection via tmux console commands + log parsing
4. Downloads and parses POI region files for bed data
5. Cross-references beds with villager brain data
6. Writes everything to SQLite
7. Detects births (new UUIDs) and deaths (missing UUIDs) since last snapshot
8. Invokes the `playground` skill to generate an interactive HTML census viewer

The skill is written using `/writing-skills` and lives in the minecraft plugin structure.

No automation, no cron — purely manual, invoked every few days.

## Playground Output

Each census run produces an interactive HTML playground (via the `playground` skill) that lets the user:

- **Inspect the current census** — villager list with profession, health, bed assignment, position, inventory, gossip
- **Compare to previous censuses** — population delta, new births, deaths, bed occupancy changes
- **Map view** — villager positions plotted on a 2D grid, color-coded by profession, with bed locations marked
- **Filter and sort** — by profession, homeless status, health, gossip activity, spawn origin
- **Timeline** — population count over all snapshots, including the seeded historical data

The playground reads directly from the SQLite database (embedded as JSON in the HTML) so it's a single self-contained file that can be opened in a browser.

## Historical Seeding

The database is seeded with reconstructed snapshots from server logs, giving us population history before the first live census.

### Source data

- **Server logs:** `2026-03-30-3.log.gz` contains 107 villager death entries with UUIDs, positions, and death messages from the Great Culling
- **Today's live census:** full entity dumps for 130 villagers including `Paper.SpawnReason`, `Paper.Origin`, `Spigot.ticksLived`

### Reconstructed snapshots

**Snapshot 0 — Pre-culling (2026-03-30 ~18:30 UTC)**
- Partial data. We know the UUIDs and approximate positions of the 107 villagers who died (from death logs). We also know the 11 DEFAULT-spawn villagers who survived (from today's census). Total reconstructed: ~118+ villagers.
- Most fields will be NULL (no trade, inventory, gossip, or brain data available).
- `villager_states` rows have: UUID, position (from death log coordinates or today's origin), profession (from death log display name where available — e.g. `[Farmer]`).
- `notes`: "Reconstructed from death logs. Partial data — only UUIDs and positions known."

**Snapshot 1 — Post-culling (2026-03-30 ~19:55 UTC)**
- The survivors: all villagers from today's census whose `spawn_reason = 'DEFAULT'` (the 11 originals), plus any early BREEDING villagers whose `ticksLived` suggests they existed at culling time.
- Estimated population: ~43 survivors (150 total minus 107 killed).
- Most fields NULL except UUID and approximate position.
- `notes`: "Reconstructed. Survivors inferred from current census DEFAULT villagers + death log subtraction."

**Snapshot 2 — First live census (2026-04-03)**
- Full data from today's entity dumps. All fields populated.
- This becomes the baseline for all future deltas.

### Seeding approach

A one-time `census_seed.py` script that:
1. Parses `2026-03-30-3.log.gz` death entries — extracts UUID (from int array), position, death message, profession display name
2. Identifies survivors by cross-referencing today's census UUIDs against the death list
3. Creates snapshot 0 (pre-culling) and snapshot 1 (post-culling) with partial `villager_states` rows
4. Marks the 107 killed villagers as `presumed_dead = 1, death_snapshot = 0`
5. Inserts today's census as snapshot 2 with full data

This gives us the 150 → ~43 → 130 population curve from day one.
