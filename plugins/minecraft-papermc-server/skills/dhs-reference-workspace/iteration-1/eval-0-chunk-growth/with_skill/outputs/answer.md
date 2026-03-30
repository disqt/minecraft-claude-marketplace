# Does `generate_new_chunks: true` permanently grow my world?

## Short answer

**No -- by design it should not.** DHS generates chunks temporarily, builds the LOD data from them, then discards them without saving. Your 8GB world should not balloon from pregen alone.

However, there is a known bug that causes chunk leaks, so in practice **some growth is possible**. Read on for the details.

## How it works

When `generate_new_chunks: true`, DHS calls `getChunkAtAsync(x, z, true)` which tells Paper to generate a chunk if it does not already exist on disk. After the LOD is built from that chunk, DHS calls `world.unloadChunk(chunkX, chunkZ, false)` -- the `false` parameter means **do not save to disk**. The chunk is removed from memory and the world files should not grow.

So the intended lifecycle is:

1. Generate chunk in memory (if missing)
2. Take a snapshot for the LOD builder
3. Discard the chunk without saving
4. Only the LOD data (stored in `plugins/DHSupport/data.sqlite`) persists

## The catch: Bug #1 (loads map key collision)

DHS v0.12.0 has a bug where the chunk tracking map uses the wrong key. For each LOD section, DHS loads 16 chunks (a 4x4 grid), but all 16 are stored under the same map key (`worldX+"x"+worldZ` instead of `chunkX+"x"+chunkZ`). This means only the last chunk's reference is kept -- the other 15 are orphaned. When DHS calls `discardChunk()`, it only unloads 1 of the 16 chunks.

The 15 orphaned chunks remain in Paper's memory. Whether they eventually get saved to disk depends on Paper's internal chunk management -- Paper may auto-save dirty chunks during its normal tick cycle, or it may unload them without saving when memory pressure increases. In the worst case, if Paper decides to save those orphaned generated chunks, your world **will** grow.

## Recommendation

1. **Do not blindly switch to `false`.** With `generate_new_chunks: false`, DHS can only build LODs from chunks that already exist on disk. If your world is 8GB, you likely have plenty of explored area -- but pregen will produce gaps (null LODs) wherever chunks have never been generated. The visual result is missing terrain in unexplored areas.

2. **Monitor world size during pregen.** Before starting (or resuming) pregen, note your world folder size. Check it periodically. If it is growing significantly, the bug is causing chunk saves on your server.

3. **If world growth is unacceptable**, set `generate_new_chunks: false` and accept that LODs will only cover already-explored terrain. This is the safe option for keeping your world at 8GB.

4. **If you want full coverage without world growth**, the real fix is patching the map key bug (changing `worldX+"x"+worldZ` to `chunkX+"x"+chunkZ` in `DhSupport.java` line 414). With that fix, all 16 chunks per section would be properly tracked and discarded without saving.

## What about the SQLite database?

The LOD data itself is stored in `plugins/DHSupport/data.sqlite`, not in your world folder. This file will grow during pregen regardless of the `generate_new_chunks` setting -- that is expected and is typically much smaller than world data (LODs are LZMA2-compressed summaries, not full chunk data).
