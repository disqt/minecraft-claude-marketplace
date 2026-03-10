# Upgrade Plan Format

Use this format for the Phase 4 upgrade plan presented to the user.

---

## Format

```
## Upgrade Plan — {instance-name}

### Summary
| Action | Count |
|--------|-------|
| Replace | N |
| Add | N |
| Remove | N |
| Enable | N |
| Keep | N |

### Proposed changes
| # | Action | Mod | Current | Alternative | DL | Last Updated | Pros | Cons | Links |
|---|--------|-----|---------|-------------|-----|--------------|------|------|-------|
| 1 | REPLACE | flow | 2.2.0 | Smooth Gui | 45k → 800k | 2024-12 → 2025-11 | 800k DL, 1.21.11 ✓ | different anim scope | [flow](url) [alt](url) |
| 2 | ADD | Lithium | — | — | — → 77M | 2026-02 | transparent optimizer, in REFINED | — | [link](url) |
| 3 | REMOVE | noisium [disabled] | — | — | — | — | no 1.21.11 build | — | [link](url) |
| 4 | ENABLE | DistantHorizons [disabled] | — | — | — | — | file was .disabled by mistake | — | — |

### No changes needed (N mods)
sodium, ferritecore, iris, ... (collapsed)
```

## Action types

| Action | When to use |
|--------|-------------|
| `REPLACE` | Clearly better alternative exists AND is compat-confirmed |
| `ADD` | Strong mod missing from list, compat-confirmed including all deps |
| `REMOVE` | `.disabled` mod with no build for target MC version — safe to delete |
| `ENABLE` | `.disabled` mod the user wants re-enabled (no download needed) |
| `KEEP` | Current mod is best or near-best for this slot |

## Rules

- **Mod names are always hyperlinked** — in every table row and in the collapsed "no changes" list. Link to wherever the mod was found (Modrinth preferred, CurseForge or GitHub if that's the only source).
- Real Modrinth links for every mod and every alternative — no guessed URLs
- Stats from actual API calls — never guessed
- Pros/cons: factual, max 2-3 points, no padding
- If uncertain: say so and link to where user can verify
- Sort: REPLACE first, ADD second, REMOVE/ENABLE last
