---
name: mc-mod-compat-check
description: Use when verifying whether a Minecraft mod has a build for a specific MC version and modloader before recommending KEEP, ADD, REPLACE, or REMOVE for that mod.
---

# Minecraft Mod Compatibility Check

Verify a mod has an actual build for the target MC version before including it in any verdict or recommendation. Run this for EVERY mod assessed and EVERY gap candidate — never skip.

## Procedure

For each mod, call Modrinth:

```
GET https://api.modrinth.com/v2/project/{slug}/version?game_versions=["{mc-version}"]&loaders=["{loader}"]
```

If the slug is unknown, find it first:
```
GET https://api.modrinth.com/v2/search?query={mod-name}&facets=[["project_type:mod"]]
```
Take the top result's `slug`.

### Read the response

| Result | Status | Action |
|--------|--------|--------|
| Versions returned, game version matches exactly | `✓ exact` | Use latest version + date |
| No results → retry with minor series (e.g. `1.21.1` for target `1.21.11`) → found | `~ minor` | Flag as unconfirmed |
| No results on Modrinth → check CurseForge / GitHub | `? external` | Note source |
| Nothing found anywhere | `✗ none` | Block — see rules |

### Check dependencies

For every ADD candidate, also check its required dependencies:
```
GET https://api.modrinth.com/v2/project/{slug}/version?game_versions=["{mc-version}"]&loaders=["{loader}"]
```
Read `dependencies` array. For each required dep not already in the user's mod list, run this same procedure on it. If any required dep has `✗ none`, the candidate cannot be recommended.

## Rules

- **`✗ none`** → NEVER recommend KEEP, ADD, or REPLACE with this mod. Flag as `INCOMPATIBLE` (user mod) or drop from gap list (candidate).
- **`~ minor`** → May include, but flag in report as "unconfirmed for exact version".
- **`? external`** → Include with source noted.
- **Missing dep with `✗ none`** → Drop the candidate entirely; note why.

## Report column

Add to every row in the Category Report:

```
| Compat | Latest for target | Date |
| ✓ exact | 0.21.3+1.21.11 | 2026-02 |
| ~ minor | 0.21.2+1.21.1 | 2025-11 |
| ✗ none | — | — |
```

## Baseline failure (why this skill exists)

In a real audit run, 6 category agents recommended ADD for 14 mods without verifying exact 1.21.11 builds. The `versions:1.21.11` Modrinth search facet filters results but does not confirm that a downloadable JAR for exactly 1.21.11 exists — a mod can appear in search results via minor-series matching. This skill closes that gap.
