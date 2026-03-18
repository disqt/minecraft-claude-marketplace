---
name: dhs-reference
description: Use when working with the Distant Horizons Support (DHS) server plugin — configuring LOD generation, running or debugging pregen, understanding chunk lifecycle, diagnosing stalls or performance issues, or deciding config values like generate_new_chunks, builder_type, scheduler_threads
---

# DHS (Distant Horizons Support) Internals Reference

Reference for the DHS server plugin (v0.12.0). Source: `https://gitlab.com/distant-horizons-team/distant-horizons-server-plugin`

## What DHS Does

DHS generates Level-of-Detail (LOD) terrain data server-side and sends it to Distant Horizons clients via plugin messaging. Clients render distant terrain from these LODs instead of loading full chunks. LODs are stored in SQLite (`plugins/DHSupport/data.sqlite`).

## LOD Generation Pipeline

```
Client requests LOD (or pregen spiral reaches position)
  |
  v
Check SQLite for existing LOD --> found? return it
  |  not found
  v
Load 4x4 = 16 chunks for this section (64x64 blocks)
  |-- generate_new_chunks=true:  getChunkAtAsync(x, z, true)   [generates if missing]
  |-- generate_new_chunks=false: getChunkAtAsync(x, z, false)  [load only, reject if missing]
  v
All chunks loaded? (CompletableFuture.allOf)
  |-- Any rejected + no dummy_chunk config: abort, return null
  |-- Any rejected + dummy_chunk configured: switch to dummy mode
  v
Queue builder on worker thread pool (DHSupport-Worker-N)
  |-- FullBuilder: scans entire Y column, captures all detail
  |-- FastOverworldBuilder: stops at solid ground, skips deep underground
  v
Encode LOD data (LZMA2 compression) + beacon data
  v
Save to SQLite (single-threaded async executor)
  v
Discard the 16 loaded chunks (unloadChunk(x, z, false) -- no save)
```

Each LOD covers a 64x64 block section at detail level 6. The section coordinate system is `blockCoord / 64`.

## Pregen System

`/dhs pregen start <world> <centerX> <centerZ> <radius> [force]`

- Generates LODs in an **outward spiral** from center
- `radius` is in **chunks** (converted to blocks internally)
- Total LODs = `(radius/2)^2` — e.g., radius 625 = 97,656 LODs
- Skips existing LODs unless `force` is specified
- Runs on a DHSupport-Worker thread from the shared pool
- Concurrency controlled by `full_data_request_concurrency_limit` (default 20)
- Blocks via `CompletableFuture.anyOf(requests).join()` when at capacity

### Pregen Status

`/dhs pregen status <world>` shows:
- Generation progress (%)
- Processed LODs: completed / total (momentary CPS)
- Time elapsed and estimated remaining

"Time remaining: infinite" means momentary CPS is 0 (division by zero). The pregen may still be running.

### Pregen Known Issues

**Silent death (no try-catch):** `PreGenerator.run()` has no exception handling. If any LOD generation throws, `CompletableFuture.anyOf(...).join()` propagates a `CompletionException` that kills the worker thread. The `run` flag stays `true`, so `status` falsely reports "running" while the thread is dead. Verify by checking for `DHSupport-Worker-*` threads in `jstack`, or check if `data.sqlite` mtime is advancing.

**No persistence across restarts:** Pregen state is in-memory only. Server restart = pregen lost. Re-running skips already-generated LODs (fast), so progress isn't lost, just the running task.

**Stale CPS display:** The "5.35 CPS" in status can be a cached value from the last active period. Check `dhs status` (global) for the real-time `Current generation speed`.

## Config Quick Reference

See `references/config-and-internals.md` for full code-traced details on every option.

| Config | Default | What It Actually Does |
|--------|---------|----------------------|
| `generate_new_chunks` | true | true = `getChunkAtAsync(x,z,true)` generates missing chunks. false = load-only, rejects missing chunks. **Chunks are discarded after LOD build** (not saved to world) |
| `builder_type` | FullBuilder | `FullBuilder`: full Y scan, all detail, slower. `FastOverworldBuilder`: stops at solid ground, ~2-3x faster, good for overworld. `None`: disables building |
| `scheduler_threads` | 4 | Worker thread pool size for LOD generation. Also used by pregen thread itself |
| `full_data_request_concurrency_limit` | 20 | Max in-flight LOD builds during pregen. Higher = more parallel chunk loads |
| `render_distance` | 1024 | Max LOD render distance (chunks). Clients capped to this |
| `real_time_updates_enabled` | true | Push LOD updates when blocks change near players |
| `real_time_update_radius` | 128 | How close (blocks) a player must be to receive live updates |
| `lod_refresh_interval` | 15 | Seconds between processing world-change LOD invalidations |
| `material_map` | (ores/plants) | Block substitution during LOD build (e.g., hide diamond ore as stone) |
| `dummy_chunk` | disabled | Fallback column data when chunks can't be loaded |
| `border_center_x/z`, `border_radius` | - | Custom LOD generation boundary (per-world) |
| `trust_height_map` | true | false = ignore heightmap, return maxY-1 for all blocks (debug escape hatch) |
| `sample_biomes_3d` | false | true = sample biome at each Y level (for 3D biome worlds like nether) |
| `fast_underfill` | true | (FastOverworldBuilder) Extend bottom block to y=0 for visual completeness |
| `scan_to_sea_level` | false | (FastOverworldBuilder) true = keep scanning down to sea level even after hitting ground |

## Builder Selection Guide

| World Type | Recommended Builder | Why |
|------------|-------------------|-----|
| Overworld (vanilla) | FastOverworldBuilder | 2-3x faster; solid ground assumption holds |
| Nether | FullBuilder | No "solid ground" — need full scan for caves/lava |
| End | FullBuilder | Floating islands need full scan |
| Custom (floating islands) | FullBuilder + `scan_to_sea_level: true` | Prevents underfill from hiding overhangs |
| Datapack terrain | FullBuilder | Custom generation may violate fast builder assumptions |

## Threading Model

- **DHSupport-Worker-N**: Shared `ThreadPoolExecutor` (core/max = `scheduler_threads`). Used for LOD builds AND the pregen loop itself. With `scheduler_threads: 8`, pregen occupies 1 thread leaving 7 for builders — so `full_data_request_concurrency_limit` above 7-8 just queues futures without increasing parallelism. Pool uses `allowCoreThreadTimeOut(true)` with 60s timeout — idle worker threads are destroyed after 60 seconds. This means after a pregen stall or completion, all DHSupport-Worker threads disappear. Zero workers in `jstack` = pool timed out (strong signal the pregen thread died)
- **Server thread**: Chunk snapshots read here (on Paper, `canReadWorldAsync()=true` allows off-thread reads)
- **AsyncLodRepository executor**: Single-threaded — all SQLite writes are serial. Secondary bottleneck: if builders are fast (e.g., FastOverworldBuilder), they can produce LODs faster than the single DB thread can write them
- **FoliaLib**: Wraps Paper/Folia scheduler. On Paper, `runOnRegionThread` maps to `Bukkit.getScheduler().runTask()`

## Known Bugs (v0.12.0)

1. **Loads map key collision** (`DhSupport.java:414`): All 16 chunk loads use key `worldX+"x"+worldZ` instead of `chunkX+"x"+chunkZ`. Only last chunk tracked; 15 orphaned. Chunk discard only cleans 1 of 16
2. **PreGenerator silent death** (`PreGenerator.java`): No try-catch in `run()`. Any exception kills thread silently
3. **Potential NPE in LodHandler** (line 65): `Bukkit.getPlayer()` can return null if player disconnects mid-request
4. **LodRepository unchecked ResultSet** (line 104): `result.next()` return value not checked; NPE if no rows

## Diagnostic Commands

| Command | What It Shows |
|---------|---------------|
| `dhs status` | Global: generation enabled, builder type, connected DH players, **real-time CPS** |
| `dhs status <player>` | Player's DH config, LODs sent count |
| `dhs pregen status <world>` | Progress %, completed/total, elapsed, ETA |
| `dhs pregen start <world> <cx> <cz> <radius> [force]` | Start pregen (radius in chunks) |
| `dhs pregen stop <world>` | Stop pregen |
| `dhs pause` / `dhs unpause` | Pause all LOD generation globally |
| `dhs reload` | Reload config.yml |
| `dhs worlds` | List all worlds |
| `dhs trim <world> <cx> <cz> <radius>` | Delete LODs outside area |
| `dhs bench <world> [iterations] [concurrency]` | Benchmark LOD build speed |

## Debugging a Stalled Pregen

1. `dhs pregen status <world>` — is it "running"?
2. `dhs status` — check `Current generation speed`. If 0.00 CPS but status says running, pregen thread is likely dead
3. `jstack <pid> | grep DHSupport` — are worker threads alive? Zero threads = pool timed out after thread death
4. Check `data.sqlite` mtime — is it advancing? (`stat plugins/DHSupport/data.sqlite`)
5. If dead: `dhs pregen stop <world>` then `dhs pregen start` — it skips existing LODs

## Further Reading

- `references/config-and-internals.md` — Full config tracing, threading details, client protocol, database schema, all bugs with code references
- Source: `https://gitlab.com/distant-horizons-team/distant-horizons-server-plugin`
