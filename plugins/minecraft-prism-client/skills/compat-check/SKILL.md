---
name: compat-check
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
| No results on Modrinth → check CurseForge / GitHub → found | `? external` | Note source |
| Nothing found on any platform → **run community research** (see below) → evidence found | `~ community` | Include with evidence link |
| Nothing found anywhere, no community evidence | `✗ none` | Block — see rules |

### Community research (before declaring `✗ none`)

Not every MC update is breaking. Many mods work on newer versions even when the author hasn't published a tagged build. Before flagging a mod as `✗ none`, check for community evidence:

1. **Modrinth project page** — read the mod description for statements like "works with X.Y.Z" or "compatible with 26.x"
2. **Modrinth version comments** — check the latest version's comments for users reporting success/failure on the target MC version
3. **GitHub issues/discussions** — search for the target MC version: `is:issue {mc-version}` or `is:discussion {mc-version}`
4. **Web search** — `"{mod-name}" "{mc-version}" compatible OR works OR tested`

**Evaluate the evidence:**

| Evidence | Status | Action |
|----------|--------|--------|
| Multiple users confirm it works, no crash reports | `~ community` | Include with link to evidence |
| Author says "should work" but no tagged build | `~ community` | Include, note author statement |
| Mixed reports (some work, some crash) | `~ community` | Include, flag as risky in Notes |
| Only crash reports or author says incompatible | `✗ none` | Block |
| No discussion found at all | `✗ none` | Block |

**Time limit:** Spend max 2 minutes per mod on community research. If nothing surfaces quickly, it's `✗ none`.

### Check dependencies

For every ADD candidate, also check its required dependencies:
```
GET https://api.modrinth.com/v2/project/{slug}/version?game_versions=["{mc-version}"]&loaders=["{loader}"]
```
Read `dependencies` array. For each required dep not already in the user's mod list, run this same procedure on it. If any required dep has `✗ none`, the candidate cannot be recommended.

## Rules

- **`✗ none`** → NEVER recommend KEEP, ADD, or REPLACE with this mod. Flag as `INCOMPATIBLE` (user mod) or drop from gap list (candidate).
- **`~ minor`** → May include, but flag in report as "unconfirmed for exact version".
- **`~ community`** → May include, but flag in report as "community-reported compatible (no official build)". Link to evidence.
- **`? external`** → Include with source noted.
- **Missing dep with `✗ none`** → Drop the candidate entirely; note why.

## Report column

Add to every row in the Category Report:

```
| Compat | Latest for target | Date |
| ✓ exact | 0.21.3+1.21.11 | 2026-02 |
| ~ minor | 0.21.2+1.21.1 | 2025-11 |
| ~ community | 0.21.2+1.21.1 (users confirm works on 1.21.11) | 2025-11 |
| ✗ none | — | — |
```

## Baseline failure (why this skill exists)

In a real audit run, 6 category agents recommended ADD for 14 mods without verifying exact 1.21.11 builds. The `versions:1.21.11` Modrinth search facet filters results but does not confirm that a downloadable JAR for exactly 1.21.11 exists — a mod can appear in search results via minor-series matching. This skill closes that gap.
