# Version Agent Prompt Template

Each agent checks one mod's version status. Follow this procedure exactly.

---

## Lookup order

### 1. Modrinth (primary)

```
GET https://api.modrinth.com/v2/search?query=<mod-name>&facets=[["project_type:mod"],["versions:<mc-version>"]]
```

Take the top result's `project_id`, then:

```
GET https://api.modrinth.com/v2/project/{id}/versions?game_versions=["<mc-version>"]&loaders=["fabric"]
```

Use the most recent version from the response.

### 2. CurseForge

If not found on Modrinth, search CurseForge via `/v1/mods/search`. Retrieve the latest file supporting the target MC version and modloader.

### 3. GitHub / GitLab releases

If not found on CurseForge, search GitHub/GitLab for `<mod-name> minecraft` and inspect releases for a JAR matching the target MC version.

### 4. Not found anywhere

Flag as `NOT_FOUND`. Notes column: `Check Discord for <mod-name>`.

---

## Compatibility heuristic

| Situation | Flag |
|-----------|------|
| Exact MC version match in API | Confirmed compatible |
| Same minor series (e.g. `1.21.10` for target `1.21.11`) | Likely compatible — add note |
| Open GitHub issues (last 90 days) with target version + `crash`/`broken`/`incompatible` | Add issue URL to Notes |

---

## Status definitions

| Status | Meaning |
|--------|---------|
| `UP_TO_DATE` | Latest available version matches current installed version |
| `UPDATE_AVAILABLE` | A newer version exists for the target MC version |
| `INCOMPATIBLE` | Mod exists but has no build for the target MC version |
| `ABANDONED` | No update in 12+ months AND no build for any newer MC version |
| `NOT_FOUND` | Could not locate the mod on any source |

---

## Report format

Return EXACTLY this format:

```
## Mod Report: {mod-name}

- **Status:** {UP_TO_DATE | UPDATE_AVAILABLE | INCOMPATIBLE | ABANDONED | NOT_FOUND}
- **Installed version:** {version from JAR filename}
- **Latest version:** {version} — [{source}]({url})
- **Version bump:** {e.g. "2.4.5-b → 2.5.0" or "UP_TO_DATE"}
- **Source:** {Modrinth | CurseForge | GitHub | GitLab | Not found}
- **Source URL:** {direct link to mod page or releases page — used by changelog agent}
- **MC version match:** {Exact | Same minor series (flag) | No build found}
- **Open issues (last 90 days):** {None | [title](url)}
- **Disabled:** {Yes | No}
- **Notes:** {any extra context, e.g. "dev confirmed no 1.21.11 path" or "edge build — stable now available"}
```
