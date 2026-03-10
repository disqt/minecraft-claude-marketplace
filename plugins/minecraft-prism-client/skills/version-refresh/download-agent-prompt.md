# Download Agent Prompt Template

One agent per mod. Dispatched in parallel by the executor (Step 6). Downloads and installs one mod JAR into the new instance.

---

## Inputs (injected per agent)

- **Mod name:** {mod-name}
- **Action:** {ADD | REPLACE | UPDATE}
- **Source:** {Modrinth | CurseForge | GitHub}
- **Source URL:** {direct link to mod page — no searching needed}
- **Target directory:** {full path to new instance .minecraft/mods/}
- **MC version:** {e.g. 1.21.11}
- **Modloader:** {Fabric | NeoForge}
- **Old JAR filename:** {exact filename to delete — only for REPLACE and UPDATE; omit for ADD}

---

## Procedure

### 1. Find the download URL

**If Source is Modrinth:**
```
GET https://api.modrinth.com/v2/project/{slug}/version?game_versions=["{mc-version}"]&loaders=["{modloader-lowercase}"]
```
Take the first result (latest compatible). Read the `files[0].url` field for the direct download URL and `files[0].filename` for the target filename.

**If Source is CurseForge:**
Fetch the mod's file list page at the Source URL. Find the latest file compatible with the MC version and modloader. Extract the direct download URL.

**If Source is GitHub:**
```
GET https://api.github.com/repos/{owner}/{repo}/releases/latest
```
Find the asset whose filename matches `*{mc-version}*` and `*fabric*` (or neoforge). Read `browser_download_url`.

### 2. Download the JAR

```bash
curl -L -o "{target-directory}/{filename}" "{download-url}"
```

### 3. Handle old JAR (REPLACE and UPDATE only)

- Delete `{target-directory}/{old-jar-filename}`
- If `{target-directory}/{old-jar-filename}.disabled` exists, delete it too
- If the old JAR was `.disabled`, rename the new JAR to `{filename}.disabled` to preserve state

---

## Decision Framework

| Situation | Response |
|-----------|----------|
| No compatible version found for MC version + modloader | Return `FAILED: no {mc-version} {modloader} build found` |
| Download fails (HTTP error, network) | Retry once. If still fails, return `FAILED: download error {status}` |
| Old JAR not found for REPLACE/UPDATE | Proceed with install anyway. Note in output: `(old JAR not found — skipped delete)` |
| Multiple files in release (e.g. sources jar) | Pick the one without `-sources` or `-dev` in the filename |

---

## Output Format

Return exactly one of:

```
INSTALLED: {filename}
```

or

```
FAILED: {reason}
```
