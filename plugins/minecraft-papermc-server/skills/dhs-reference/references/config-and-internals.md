# DHS Config and Internals — Deep Reference

Detailed code-traced reference for DHS v0.12.0. Read this when you need to understand exactly what a config option does, how the threading works, or how the client protocol operates.

## Table of Contents

1. [Config Options: Code-Traced Behavior](#config-options-code-traced-behavior)
2. [Builder Internals](#builder-internals)
3. [Chunk Lifecycle](#chunk-lifecycle)
4. [Threading Model Details](#threading-model-details)
5. [Client Protocol](#client-protocol)
6. [Database Layer](#database-layer)
7. [Real-Time Updates](#real-time-updates)
8. [Bugs with Code References](#bugs-with-code-references)
9. [Key Source Files](#key-source-files)

---

## Config Options: Code-Traced Behavior

### generate_new_chunks (bool, default: true, per-world)

Controls which async chunk loader is called in `DhSupport.generateLod()` (line 413-416):
```
true  → world.loadOrGenerateChunkAsync(chunkX, chunkZ)
         → getChunkAtAsync(chunkX, chunkZ, true)    // generates if missing
false → world.loadChunkAsync(chunkX, chunkZ)
         → getChunkAtAsync(chunkX, chunkZ, false)   // load only
```

If `getChunkAtAsync` is unavailable (non-Paper server), falls back to synchronous `runOnMainThread(() -> world.loadChunk(...))`.

**Chunk saving:** After LOD generation, chunks are discarded via `world.unloadChunk(chunkX, chunkZ, false)` — the `false` means do NOT save. Generated chunks should not persist to the world. However, see Bug #1 (map key collision) — only 1 of 16 chunks is actually discarded per LOD section.

### builder_type (string, default: "FullBuilder", per-world)

Instantiated via reflection in `DhSupport.getBuilder()` (line 332):
```java
Class.forName(LodBuilder.class.getPackageName() + "." + builderType)
    .asSubclass(LodBuilder.class);
```

Valid values: `FullBuilder`, `FastOverworldBuilder`, `None` (disables generation).

### scheduler_threads (int, default: 4, global)

Sets both core and max pool size for `ThreadPoolExecutor` in `BukkitScheduler` (line 49):
```java
new ThreadPoolExecutor(threadCount, threadCount, 60, TimeUnit.SECONDS, new LinkedBlockingQueue<>())
```

Pool has `allowCoreThreadTimeOut(true)` — threads die after 60s idle. This means after a quiet period, all worker threads disappear. New tasks spawn fresh threads up to the pool size.

The pregen thread itself runs on this pool (via `runOnSeparateThread`), consuming one slot. With `scheduler_threads: 8` and `full_data_request_concurrency_limit: 20`, up to 7 builders can run concurrently (1 thread occupied by pregen loop).

### full_data_request_concurrency_limit (int, default: 20, per-world)

Read by `PreGenerator.run()` (line 71) as `rateLimit`. Controls how many LOD generations can be in-flight before the pregen blocks:
```java
while (this.inFlight >= rateLimit) {
    CompletableFuture.anyOf(requests.toArray(new CompletableFuture[0])).join();
    requests.removeIf(CompletableFuture::isDone);
}
```

Higher values = more parallel chunk loads + builds. Limited by `scheduler_threads` (workers) and Paper's `global-max-concurrent-loads` (chunk system).

### render_distance (int, default: 1024, per-world)

Client render distance is capped to this value. Stored per-player when client sends config. Used in `dhs status` display and bStats metrics.

### trust_height_map (bool, default: true, per-world)

In `BukkitWorldInterface.getHighestYAt()` (line 501):
- true: uses `ChunkSnapshot.getHighestBlockYAt()` (fast, relies on Minecraft's heightmap)
- false: returns `maxY - 1` for all positions (everything treated as max height)

Setting false effectively disables meaningful LOD generation. It's an escape hatch for corrupted heightmap data.

### material_map (map, per-world)

Applied during block reading in `BukkitWorldInterface.getMaterialAt()` (line 548). For each block material, checks if a mapping exists:
```
material_map:
  iron_ore: stone        # Hide ores in LODs
  diamond_ore: stone
  bamboo: air            # Remove bamboo clutter
  kelp: water            # Simplify ocean
```

Maps are applied without the `minecraft:` prefix.

### dummy_chunk (list, per-world)

Parsed in `BukkitWorldInterface` (line 230). Format:
```yaml
dummy_chunk:
  - "0-3,minecraft:stone"
  - "4-79,minecraft:dirt"
  - "80,minecraft:grass_block"
```

If all 16 chunks fail to load AND dummy_chunk is configured, the builder uses this fake column instead of aborting. If dummy_chunk is empty/unset, failed loads return null (LOD generation aborted).

### lod_refresh_interval (int, default: 5, per-world)

Timer period in seconds for the periodic task (DhSupportBukkitPlugin line 98). Each tick:
1. Prunes performance tracker (removes old pings)
2. Calls `updateTouchedLods()` — regenerates LODs that were invalidated by world changes

### update_events (list, global)

Dynamically registers Bukkit event listeners via reflection in `WorldHandler` (line 84). For each event class:
1. Instantiates listener
2. On event fire, uses reflection to find block locations (tries `blockList()`, `getBlocks()`, `getBlock()`, `getLocation()`, `getChunk()`)
3. Calls `touchLod()` for each affected LOD section

### use_vanilla_world_border (bool, default: true, per-world)

Controls border source in `LodHandler` (line 106):
- true: reads from `world.getWorldBorder().getCenter()` and `.getSize()`
- false: reads from `border_center_x`, `border_center_z`, `border_radius` config keys

LOD requests outside the border are rejected.

### vanilla_world_border_expansion (string, default: "auto", per-world)

In `BukkitWorldInterface` (line 295):
- `"auto"`: expands border by server view distance (chunks → blocks)
- Integer string: expands border by that many blocks

Prevents fog-of-war at the border edge by generating LODs slightly beyond.

### sample_biomes_3d (bool, default: false, per-world)

Both builders check this. If false, biome is sampled once per column at surface level. If true, biome is sampled at each Y level during the column scan. Enable for worlds with vertical biomes (e.g., nether with soul sand valley layers).

### fast_underfill (bool, default: true, per-world)

FastOverworldBuilder only (line 210). After scanning, extends the bottommost DataPoint to y=0:
```java
if (underfill && previous != null) {
    previous.setHeight(previous.getStartY() + previous.getHeight());
    previous.setStartY(0);
}
```

Makes LODs look "complete" from below. Disable if you have worlds with visible underside (e.g., floating islands).

### scan_to_sea_level (bool, default: false, per-world)

FastOverworldBuilder only (line 144). Normally, solid ground detection stops scanning at the first solid layer. With this enabled, scanning continues down to sea level even after hitting solid ground. Enable for worlds with large overhangs or floating structures above sea level.

### perform_underglow_hack (bool, default: false, per-world)

FullBuilder only. When air is encountered below a non-air block, splits the DataPoint to prevent DH from merging adjacent air/solid layers. Helps with cave rendering on nether ceiling but has visual side effects.

---

## Builder Internals

### FullBuilder Algorithm

For each of 64x64 blocks in a section:
1. Get highest Y via heightmap
2. Optionally scan upward for non-colliding blocks (grass, flowers, snow)
3. Scan downward from top to min Y with configurable step (always 1 currently)
4. Each Y position: get material, biome, sky/block light
5. Consecutive identical materials compressed into single DataPoint
6. Special handling for air layers (skip from top to topmost block)
7. Underglow hack splits DataPoints at air/solid transitions

### FastOverworldBuilder Algorithm

Same as FullBuilder but with early termination:
1. Scan downward from top
2. When hitting "solid ground" (stone, grass, dirt, gravel, sand, sandstone, mycelium):
   - Set `solidGround` threshold to 10 blocks below (or sea level - 10)
   - Stop scanning once below threshold
3. If `fast_underfill`: stretch bottom block to y=0

Solid ground materials are hardcoded — custom terrain with other base blocks won't trigger early termination.

### LOD Data Structure

Each LOD section contains:
- `idMappings`: List of unique (biome, material) pairs
- `columns`: 64x64 = 4096 columns, each a list of DataPoints
- `beacons`: List of beacon positions + colors in this section

Each DataPoint is packed into a long: mappingId (16 bits), height (16 bits), startY (16 bits), skyLight (4 bits), blockLight (4 bits).

Encoded via LZMA2 at compression level 3 with CRC64 check.

---

## Chunk Lifecycle

### Loading

For each LOD section, DHS loads a 4x4 grid of chunks (16 total, each 16x16 blocks = 64x64 block section):
```java
for (int xMultiplier = 0; xMultiplier < 4; xMultiplier++) {
    for (int zMultiplier = 0; zMultiplier < 4; zMultiplier++) {
        int chunkX = worldX + 16 * xMultiplier;
        int chunkZ = worldZ + 16 * zMultiplier;
        loads.put(..., world.loadOrGenerateChunkAsync(chunkX, chunkZ));
    }
}
```

### Snapshot Caching

Block data is read via `ChunkSnapshot` objects, cached per-build in `BukkitWorldInterface.chunks` map. Each snapshot captures block types, biomes, and light levels at creation time. Multiple reads during a single LOD build hit this cache.

### Discarding

After LOD generation, `discardChunk()` calls `world.unloadChunk(chunkX, chunkZ, false)`:
- `false` = do NOT save to disk
- Chunk is removed from memory
- World files should not grow from pregen (verify by comparing world size before/after)

---

## Threading Model Details

### Thread Contexts

| Context | Used For | Thread Name |
|---------|----------|-------------|
| Server thread | Console commands, event handling | `Server thread` |
| Worker pool | LOD builds, pregen loop | `DHSupport-Worker-N` |
| DB executor | All SQLite operations | Single unnamed thread |
| ForkJoinPool.commonPool | CompletableFuture.thenComposeAsync default | `ForkJoinPool.commonPool-worker-N` |
| Paper chunk threads | Async chunk loading/generation | Paper internal |

### Deadlock Risk

The pregen thread blocks at `.join()` waiting for LOD futures. LOD futures need worker threads for building. Both share the same pool. With `scheduler_threads: 8`, pregen occupies 1 thread, leaving 7 for builders. With `full_data_request_concurrency_limit: 20`, up to 13 builder tasks queue in the `LinkedBlockingQueue` waiting for a worker.

This isn't a deadlock (the queue is unbounded), but throughput is limited to 7 concurrent builds regardless of the concurrency limit setting.

### Worker Thread Lifecycle

`allowCoreThreadTimeOut(true)` with 60s timeout means idle workers die. After the pregen stalls or finishes, all DHSupport-Worker threads disappear within 60s. When `dhs pregen status` reports "running" but zero worker threads exist, the pregen thread has died from an uncaught exception.

---

## Client Protocol

Channel: `distant_horizons:message`, protocol version 13.

### Message Types

**Client → Server:**
- `FullDataSourceRequestMessage`: Request LOD at section (x, z)
- `RemotePlayerConfigMessage`: Client config (render_distance, generation_enabled, etc.)

**Server → Client:**
- `FullDataSourceResponseMessage`: LOD metadata + buffer ID
- `FullDataChunkMessage`: 16KB data chunks (LOD data split into CHUNK_SIZE = 16384 bytes)
- `FullDataPartialUpdateMessage`: Real-time LOD update (beacons included)
- `ExceptionMessage`: Error (`section_requires_splitting`, `request_rejected`)

### Envelope Format

```
[protocolVersion: short][messageTypeId: short][trackerId: int (if trackable)][payload: bytes]
```

---

## Database Layer

### SQLite Schema

```sql
CREATE TABLE lods (
    worldId TEXT,     -- UUID as string
    x INT,            -- Section X coordinate
    z INT,            -- Section Z coordinate
    data BLOB,        -- LZMA2-compressed LOD data
    beacons BLOB,     -- Encoded beacon data
    timestamp INT,    -- Unix timestamp of generation
    version INT       -- LOD format version (currently 2)
);
```

### Access Pattern

All DB operations go through `AsyncLodRepository` which queues to a **single-threaded executor**. This ensures serial access (no concurrent writes) but means DB throughput is limited to one operation at a time.

### Optimization

`LodRepository.trimLods()` runs:
```sql
PRAGMA optimize; ANALYZE; REINDEX; VACUUM;
```

---

## Real-Time Updates

When blocks change near players:

1. `WorldHandler` receives Bukkit event (from `update_events` config)
2. Extracts block locations via reflection
3. Calls `DhSupport.touchLod(worldId, x, z, reason)` — marks LOD as invalidated
4. Periodic timer (every `lod_refresh_interval` seconds) processes `touchedLods` map:
   - Deletes old LOD from database
   - Regenerates LOD
   - For each player within `real_time_update_radius`:
     - Sends `FullDataChunkMessage` (data in 16KB chunks)
     - Sends `FullDataPartialUpdateMessage` (metadata + beacons)

---

## Bugs with Code References

### Bug 1: Loads Map Key Collision

**File:** `DhSupport.java`, line 414

```java
loads.put(worldX + "x" + worldZ, world.loadOrGenerateChunkAsync(chunkX, chunkZ));
```

Should be `chunkX + "x" + chunkZ`. All 16 iterations overwrite the same key. Only 1 of 16 chunk loads is tracked and later discarded. The other 15 chunks are loaded (potentially generated), their futures are orphaned, and they are never explicitly discarded.

### Bug 2: PreGenerator Silent Death

**File:** `PreGenerator.java`, lines 69-130

`run()` has no try-catch. The method is called inside `runOnSeparateThread(() -> { pregen.run(); return null; })` which catches exceptions into a CompletableFuture that nobody reads. If `CompletableFuture.anyOf(requests).join()` at line 117 throws `CompletionException` (from any failed LOD), the thread dies. `run` flag (line 51) stays `true` because the assignment at line 129 (`this.run = false`) is never reached.

### Bug 3: LodHandler NPE

**File:** `LodHandler.java`, line 65

```java
UUID worldUuid = Bukkit.getPlayer(requestMessage.getSender()).getWorld().getUID();
```

If player disconnects between message receipt and processing, `getPlayer()` returns null. No null check.

### Bug 4: LodRepository Unchecked ResultSet

**File:** `LodRepository.java`, line 104

```java
result.next();  // return value not checked
byte[] data = result.getBytes("data");
```

If no row found, `next()` returns false but code proceeds to read columns, causing an exception.

---

## Key Source Files

| File | Purpose |
|------|---------|
| `DhSupportBukkitPlugin.java` | Plugin entry point, initialization, timer setup |
| `DhSupport.java` | Core orchestrator: getLod, generateLod, queueBuilder, pause, pregen management |
| `PreGenerator.java` | Spiral pregen: concurrency control, progress tracking |
| `BukkitScheduler.java` | Threading: FoliaLib wrapper, worker pool, main/region/separate thread dispatch |
| `BukkitWorldInterface.java` | World abstraction: chunk loading, block/biome/light reads, chunk snapshots |
| `FullBuilder.java` | Full terrain LOD builder |
| `FastOverworldBuilder.java` | Overworld-optimized LOD builder |
| `LodHandler.java` | Client LOD request processing |
| `PluginMessageHandler.java` | Client message encode/decode, protocol version |
| `WorldHandler.java` | Event listener, real-time LOD invalidation |
| `AsyncLodRepository.java` | Database access (single-threaded async) |
| `DhsConfig.java` | All config key constants |
| `Coordinates.java` | Block/chunk/section/region coordinate conversion |
