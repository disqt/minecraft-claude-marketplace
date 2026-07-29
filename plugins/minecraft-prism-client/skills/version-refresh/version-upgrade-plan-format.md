# Version Upgrade Plan Format

Use this format for the Step 3 upgrade plan.

---

## Format

```
## Upgrade Plan — {instance-name}

### Summary
| Action | Count |
|--------|-------|
| Update available | N |
| Incompatible (no build) | N |
| Abandoned | N |
| Not found | N |
| Up to date | N |

### Proposed changes
| # | Action | Mod | Version | Key changes | Notes |
|---|--------|-----|---------|-------------|-------|
| 1 | UPDATE | [sounds](url) | 2.4.23+edge+1.21.11 → 2.4.23+1.21.11-fabric | [bugfix] crash fix on startup; [feature] new ambient SFX | stable build now available |
| 2 | FLAG | flow [disabled] | 2.2.0 → none | — | no 1.21.11 build — consider removing |
| 3 | CHECK DISCORD | tia [disabled] | — | — | check Discord for tia |

### No changes needed (N mods)
[sodium](https://modrinth.com/mod/sodium), [ferritecore](https://modrinth.com/mod/ferrite-core), [iris](https://modrinth.com/mod/iris), ... (collapsed, all linked)
```

## Action types

| Action | When to use |
|--------|-------------|
| `MAJOR UPDATE` | First version digit changed (e.g. 1.x → 2.x, 8.x → 9.x). NOT for minor/patch jumps even if they span many versions (0.21 → 0.24 is UPDATE, not MAJOR). |
| `UPDATE` | Any version change that isn't MAJOR or MINOR (e.g. 1.3.0 → 1.4.2, 0.21.4 → 0.24.3, 3.1.3 → 4.0.1) |
| `MINOR UPDATE` | Same version number, channel/build change only (e.g. edge → stable, alpha → beta, same base recompiled for new MC) |
| `FLAG` | Mod exists but no confirmed build for target MC version — surface for user decision |
| `ABANDON` | No update in 12+ months AND no build for any newer MC version |
| `CHECK DISCORD` | Not found on any source |

### Version classification examples

| Old → New | Action | Why |
|-----------|--------|-----|
| 1.3.0 → 2.0.0 | MAJOR UPDATE | First digit changed |
| 8.2.0 → 9.0.0 | MAJOR UPDATE | First digit changed |
| 0.21.4 → 0.24.3 | UPDATE | First digit (0) unchanged; minor bump |
| 3.8.2 → 3.9.3 | UPDATE | First digit unchanged |
| 17.0.0 → 18.0.2 | MAJOR UPDATE | First digit changed |
| 0.7.6+1.21 → 0.7.6+26.1 | MINOR UPDATE | Same base version, MC rebuild only |
| 2.4.23+edge → 2.4.23+stable | MINOR UPDATE | Channel change only |

## Rules

- **Mod names are always hyperlinked** — in every table row and in the collapsed "no changes" list. Link to wherever the mod was found (Modrinth preferred, CurseForge or GitHub if that's the only source). Use the Source URL from the version agent's report.
- Every row has a link to the mod page
- Version numbers from actual API responses — never guessed
- Open issue URLs go in Notes column
- Disabled mods flagged clearly in name
