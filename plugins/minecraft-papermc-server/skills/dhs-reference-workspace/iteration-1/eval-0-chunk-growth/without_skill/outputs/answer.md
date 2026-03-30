# Does `generate_new_chunks = true` in DHS Pregen Permanently Add Chunks to Your World?

**Short answer: Yes, but it depends on which chunks you're talking about.**

There are two separate things at play here, and it's important to distinguish them:

## What `generate_new_chunks` actually controls

In Distant Horizons Serverside (DHS), the `generate_new_chunks` setting controls whether the server will generate **real vanilla Minecraft chunks** when DHS needs LOD (Level of Detail) data for areas that haven't been explored yet.

When set to `true`:
- DHS pregen will fully generate vanilla chunks in the world to extract LOD data from them.
- These chunks are **permanently saved to your world's region files** just like any chunk a player walks through.
- Your world size will grow as new chunks are generated, because they become real `.mca` region file data on disk.

When set to `false`:
- DHS will only create LOD data for chunks that have **already been generated** (i.e., chunks players have already explored).
- No new vanilla chunks are added to your world.
- Your world size stays the same (aside from the separate DH database).

## The world size concern

If your world is already 8 GB and you run pregen with `generate_new_chunks = true` over a large radius, **yes, your world will balloon significantly**. Each fully generated chunk consumes real disk space in the vanilla world save. Pregenerating a large area (e.g., 10,000+ block radius) can easily add tens of gigabytes to your world.

It's worth noting that DH's own LOD data (stored in its own database/folder, separate from the vanilla world) also takes space, but that grows regardless of this setting -- it's the vanilla chunk generation that this setting gates.

## Recommendation

**Set `generate_new_chunks` to `false` if you want to control world size growth.**

With it set to `false`, DHS will only build LODs from chunks that already exist. Players will still get distant horizons rendered for explored areas, and as players naturally explore, DHS will pick up those new chunks for LOD generation.

If your goal is to pregen LODs for a large area without inflating the world, the typical approach is:

1. **If you've already pregenned vanilla chunks** (e.g., with Chunky or a similar chunk pregenerator), set `generate_new_chunks = false` and let DHS scan the existing chunks for LOD data.
2. **If you haven't pregenned and don't want to**, keep it `false` -- DHS will only serve LODs for explored territory.
3. **If you want full LOD coverage of unexplored areas** and accept the world size cost, leave it `true` but understand the disk trade-off.

The only reason to use `generate_new_chunks = true` is if you want LODs for areas no player has visited yet and you're okay with those chunks becoming permanent parts of your world. For an 8 GB world where size is a concern, `false` is the safer choice.
