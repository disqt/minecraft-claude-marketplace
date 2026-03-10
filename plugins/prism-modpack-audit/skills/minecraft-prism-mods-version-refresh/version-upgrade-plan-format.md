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
| `MAJOR UPDATE` | Different major version (e.g. 1.x → 2.x) |
| `UPDATE` | Different minor or patch version (e.g. 1.3.0 → 1.4.2) |
| `MINOR UPDATE` | Same version number, channel/build change only (e.g. edge → stable, alpha → beta) |
| `FLAG` | Mod exists but no build for target MC version — surface for user decision |
| `ABANDON` | No update in 12+ months, no newer MC builds |
| `CHECK DISCORD` | Not found on any source |

## Rules

- **Mod names are always hyperlinked** — in every table row and in the collapsed "no changes" list. Link to wherever the mod was found (Modrinth preferred, CurseForge or GitHub if that's the only source). Use the Source URL from the version agent's report.
- Every row has a link to the mod page
- Version numbers from actual API responses — never guessed
- Open issue URLs go in Notes column
- Disabled mods flagged clearly in name
