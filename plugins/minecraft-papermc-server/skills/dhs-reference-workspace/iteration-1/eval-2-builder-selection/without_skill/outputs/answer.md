# DHS Builder Type Selection for Your Worlds

## Overview

Distant Horizons Server-side (DHS) is the server companion to the Distant Horizons client mod. It offloads LOD (Level of Detail) generation from the client to the server, so players receive pre-built LOD data instead of generating it themselves. The `builder_type` setting controls how LOD data is generated for each world.

## Builder Types Available

DHS offers several builder types:

- **`WorldGeneration`** — Generates LOD data by running Minecraft's world generator on the server. It creates chunks solely for LOD purposes without fully loading them into the game world. Best for survival/exploration worlds where you want LODs to extend far beyond what players have explored.
- **`ExistingChunksOnly`** (sometimes called `ExistingChunks` or `OnlyExisting`) — Only builds LODs from chunks that already exist in the world's region files. Does not generate any new terrain. Best for worlds where you only want LODs of what has already been explored or built.
- **`None` / `Disabled`** — Disables server-side LOD generation for that world entirely.

## Recommended Configuration Per World

### 1. Overworld (`world_new`) — `WorldGeneration`

```
builder_type = WorldGeneration
```

**Why:** This is your main survival world. `WorldGeneration` will pre-generate LOD data far beyond where players have explored, giving them a seamless distant terrain view in all directions. The server generates lightweight LOD-only chunks using the world seed, so the terrain will be accurate to what players would eventually find if they traveled there.

**Key settings to tune:**
- `genThreads` / `numberOfThreads` — Control how many threads DHS uses for generation. Start with 2-3 and increase if your CPU can handle it without impacting TPS.
- `distanceGenerationMode` — Controls how far out LODs are generated. The default is usually reasonable, but you can limit the radius if generation is too resource-intensive.
- `generationPriority` — Keep this at a lower priority than live gameplay if TPS is a concern.

### 2. Nether (`world_new_nether`) — `WorldGeneration` (with caveats) or `ExistingChunksOnly`

This one is debatable, and depends on your priorities:

**Option A: `WorldGeneration`** — If you want full distant terrain in the nether:
```
builder_type = WorldGeneration
```
Note: Nether generation can be more CPU-intensive due to the complex cave/terrain geometry. The LOD results in the nether are also less visually impactful than overworld since visibility is naturally limited by the bedrock ceiling (unless players are above the nether roof). Consider reducing the generation radius compared to the overworld.

**Option B: `ExistingChunksOnly`** (recommended):
```
builder_type = ExistingChunksOnly
```
**Why this is often the better choice:** In the nether, distant terrain is largely occluded by the bedrock ceiling at Y=128, making far-out LOD generation less useful for most players. Building LODs from only the chunks players have already explored saves significant CPU resources while still providing LODs for areas they've visited. If your players do spend time above the nether roof, `WorldGeneration` becomes more worthwhile.

### 3. Creative Flatworld — `ExistingChunksOnly`

```
builder_type = ExistingChunksOnly
```

**Why:** A superflat/creative world is all about player builds, not natural terrain. Running `WorldGeneration` on a flat world would generate LODs of endless flat plains in every direction, which is both visually uninteresting and a waste of CPU. `ExistingChunksOnly` ensures LODs are built only from chunks containing actual player builds, which is exactly what you want players to see at a distance.

**Alternative:** If nobody on the server uses Distant Horizons in the creative world, you could set it to `None`/`Disabled` to save resources entirely.

## Summary Table

| World | builder_type | Rationale |
|-------|-------------|-----------|
| `world_new` (overworld) | `WorldGeneration` | Full distant terrain for exploration/survival |
| `world_new_nether` (nether) | `ExistingChunksOnly` | Nether ceiling limits LOD value; save CPU |
| Creative flatworld | `ExistingChunksOnly` | Only player builds matter; flat terrain LODs are wasteful |

## General DHS Config Tips

- **Monitor TPS** after enabling DHS. `WorldGeneration` is the most CPU-intensive mode and can impact server performance if too many threads are allocated.
- **Storage:** LOD data can consume significant disk space, especially with `WorldGeneration` on the overworld. Monitor your disk usage.
- **Per-world config:** DHS allows per-world/per-dimension configuration. Make sure you are editing the correct section for each world rather than only the global defaults.
- **Updates:** DHS is under active development and config options may change between versions. Check the DHS documentation or Discord for your specific version's config format.
