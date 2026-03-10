# Category Agent Prompt Template

Use this file to construct each Phase 2 agent's prompt. Replace `{placeholders}` with actual values before dispatching.

---

## Prompt to inject

Every category agent prompt MUST start with:

> Read the file `{resolved-path-to}/compat-check/SKILL.md` and follow its procedure for every mod you assess and every gap candidate you recommend.

**Path resolution:** Replace `{resolved-path-to}` with the absolute path to `../compat-check/SKILL.md` resolved from this skill's base directory.

Then inject:

---

You are auditing the **{category}** category for a Prism Launcher Fabric mod meta-refresh.

**Your mods in this category:**
{mod list — filenames + inferred versions}

**Target MC version:** {mc-version}
**Modloader:** {loader}
**Reference pack:** `dbs-minecraft-refined` on Modrinth
**Server-side companions active:** {list from Phase 1, or "none provided"}

---

## Research steps

**Step 1 — Fetch top 10 mods for this category on Modrinth:**
```
GET https://api.modrinth.com/v2/search?facets=[["categories:{category}"],["versions:{mc-version}"],["project_type:mod"]]&index=downloads&limit=10
```
If the category facet returns 0 results, try `utility` or search by keyword.

**Step 2 — For each user mod, fetch stats and run compat check:**
```
GET https://api.modrinth.com/v2/search?query={mod-name}&facets=[["versions:{mc-version}"],["project_type:mod"]]
```
Get: download count, `date_modified`, project slug. Then run the Mod Compatibility Check (from compat-check skill) for each mod.

**Step 3 — Fetch DisruptiveBuilds REFINED modlist:**
```
GET https://api.modrinth.com/v2/project/dbs-minecraft-refined/version
```
Get latest version dependencies. Check each user mod and gap candidate against the list.

**Step 4 — Detect redundancy:** Multiple mods in this category doing the same thing.

**Step 5 — Detect gaps:** Top-10 mods not in the user's list that suit the vanilla+ profile (performance, subtlety, no gameplay changes). Run the Mod Compatibility Check for every gap candidate before recommending ADD. Drop any candidate with `✗ none`. Check all required dependencies too.

**Vanilla+ exclusions — never recommend these:**
- Minimap or world map mods (Xaero's Minimap, Xaero's World Map, Voxelmap, etc.)
- Block/entity info overlay mods (Jade, WAILA, HWYLA, etc.) — reveal world info not in vanilla
- Persistent HUD info overlays (MiniHUD, etc.) if BetterF3 or equivalent is already in the pack
- Any mod whose primary effect is revealing information the player wouldn't otherwise have

**Step 6 — Assign verdict per mod:**

| Signal | Verdict |
|--------|---------|
| Top-3 by DL for category, compat ✓, fits vanilla+ | `KEEP` |
| Alternative has 2x+ DL, compat ✓, covers same function | `REPLACE(<alt>)` |
| Two mods cover identical function | `REDUNDANT(with <x>)` |
| Top-10 mod not in list, compat ✓, deps ✓, suits vanilla+ | `ADD` |
| Data insufficient or signals conflict | `INVESTIGATE` |
| Mod has `✗ none` compat | `INCOMPATIBLE` |

---

## Output format

Return a Category Report in EXACTLY this format:

```
## Category Report: {category-name}

### Assessed mods
| Mod | Downloads | Last Updated | Compat | In REFINED? | Verdict | Alternative | Pros | Cons |
|-----|-----------|--------------|--------|-------------|---------|-------------|------|------|
| sodium | 128M | 2026-02 | ✓ exact | Yes | KEEP | — | best-in-class | — |
| flow | 45k | 2024-12 | ✗ none | No | INCOMPATIBLE | [Smooth Gui](url) | 800k DL, 1.21.11 ✓ | — |

### Gap recommendations
| Mod | Downloads | Last Updated | Compat | Deps OK? | In REFINED? | Reason to add | Link |
|-----|-----------|--------------|--------|----------|-------------|---------------|------|
| Lithium | 77M | 2026-02 | ✓ exact | Yes | Yes | transparent optimizer | [link](url) |

### Redundancies detected
| Mod A | Mod B | Overlap | Recommendation |
|-------|-------|---------|----------------|

### Raw signals used
- Modrinth top-10 for {category} + {mc-version} (by downloads): [list names]
- DisruptiveBuilds REFINED inclusion checked: Yes
- Compatibility verified via compat-check for all mods and candidates
```
