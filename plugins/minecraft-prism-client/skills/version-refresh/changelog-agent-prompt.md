# Changelog Agent Prompt Template

Each agent fetches the changelog for one mod between two known versions. You are given direct links — do not search.

---

## Inputs (injected per agent)

- **Mod name:** {mod-name}
- **Installed version:** {old-version}
- **Latest version:** {new-version}
- **Source:** {Modrinth | GitHub | CurseForge}
- **Source URL:** {direct link to mod page or releases page}

---

## Lookup procedure

### If Source is Modrinth

Fetch all versions between installed and latest:
```
GET https://api.modrinth.com/v2/project/{slug}/version
```
Filter to versions newer than the installed version, up to and including the latest. For each, read the `changelog` field.

If `changelog` fields are empty or just say "No changelog provided", fall back to GitHub (check the `source_url` field on the project page: `GET https://api.modrinth.com/v2/project/{slug}`).

### If Source is GitHub

Fetch releases between the two version tags:
```
GET https://api.github.com/repos/{owner}/{repo}/releases
```
Filter to releases tagged between installed and latest version. Read the `body` field of each release.

### If Source is CurseForge

Fetch the file list and read changelogs for files between installed and latest version.

---

## Summarization rules

- Read all changelog entries between installed and latest version
- Extract only meaningful changes: new features, important fixes, breaking changes, performance improvements
- Skip: dependency bumps, CI changes, internal refactors with no user impact, "updated to MC x.y.z"
- Label each bullet: `[feature]`, `[bugfix]`, `[breaking]`, or `[perf]`
- Max 5 bullets total. If there are many small bugfixes, collapse them: `[bugfix] various crash fixes and stability improvements`
- If no meaningful changelog is available anywhere: return `No changelog available`

---

## Output format

Return EXACTLY this format:

```
## Changelog: {mod-name} ({old-version} → {new-version})

- [feature] ...
- [bugfix] ...
- [perf] ...
```

Or if nothing found:

```
## Changelog: {mod-name} ({old-version} → {new-version})

No changelog available.
```
