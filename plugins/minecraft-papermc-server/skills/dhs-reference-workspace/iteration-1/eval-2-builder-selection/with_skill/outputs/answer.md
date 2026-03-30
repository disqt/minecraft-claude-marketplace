# DHS Builder Selection for Your 3 Worlds

## 1. Overworld (`world_new`) -- FastOverworldBuilder

```yaml
world_new:
  builder_type: FastOverworldBuilder
  generate_new_chunks: true
  fast_underfill: true
  scan_to_sea_level: false
  sample_biomes_3d: false
```

**Why:** FastOverworldBuilder is 2-3x faster than FullBuilder for vanilla overworld terrain. It works by stopping its downward scan once it hits "solid ground" (stone, grass, dirt, gravel, sand, sandstone, mycelium), which is a safe assumption for standard overworld generation. `fast_underfill: true` (the default) extends the bottommost block down to y=0 so LODs look visually complete from below. `sample_biomes_3d` is not needed since the overworld does not have vertical biome layering.

## 2. Nether (`world_new_nether`) -- FullBuilder

```yaml
world_new_nether:
  builder_type: FullBuilder
  generate_new_chunks: true
  sample_biomes_3d: true
  perform_underglow_hack: false
```

**Why:** The nether has no "solid ground" in the overworld sense -- it is a cave dimension with lava lakes, ceiling blocks, and open voids at multiple Y levels. FastOverworldBuilder's early termination would miss most of the terrain detail. FullBuilder scans the entire Y column, capturing all cave layers and lava. Enable `sample_biomes_3d: true` because the nether has vertical biome variation (e.g., soul sand valley layers at different heights). `perform_underglow_hack` is optional -- it helps with cave rendering under the nether ceiling but can have visual side effects; leave it off unless you see rendering artifacts at cave/solid transitions.

## 3. Creative Flatworld -- FullBuilder

```yaml
creative_flatworld:
  builder_type: FullBuilder
  generate_new_chunks: true
  sample_biomes_3d: false
```

**Why:** Although a flatworld is simple terrain, it falls under "datapack/custom terrain" in the builder selection guide -- custom generation may violate the FastOverworldBuilder's hardcoded solid-ground assumptions. Specifically, a superflat world's layer composition (e.g., a few layers of grass/dirt/stone then bedrock) could trigger early termination at odd points depending on how thin the layers are. FullBuilder is the safe choice. Since flatworlds are trivially simple (very few Y levels to scan), the performance difference versus FastOverworldBuilder is negligible -- there is almost no terrain depth to scan, so FullBuilder finishes quickly anyway.

The `fast_underfill` and `scan_to_sea_level` options are FastOverworldBuilder-only and have no effect on FullBuilder, so they are omitted from the nether and flatworld configs.
