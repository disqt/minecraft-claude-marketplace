---
name: prism-audit
description: Use when the user wants to do a full refresh of their Prism Launcher modset in one session — both auditing mod quality (replacing outdated or superseded mods) and updating all mod versions to their latest compatible builds.
---

REQUIRED SUB-SKILL: meta-refresh
REQUIRED SUB-SKILL: version-refresh
REQUIRED SUB-SKILL: compat-check

# Minecraft Prism Client Audit

Entry point for a full modset refresh. Creates the shared decision doc, runs a compat scan to identify incompatible mods, then invokes meta-refresh with that knowledge. The skills chain: compat-scan → meta-refresh → version-refresh → background executor.

## Paths

Detect the user's OS and resolve these automatically. If detection fails (path doesn't exist, `prismlauncher` not in PATH), ask: "I couldn't auto-detect your Prism Launcher install. What's the path to your instances directory?"

| Variable | Windows | Linux | macOS |
|----------|---------|-------|-------|
| `{PRISM_INSTANCES}` | `%APPDATA%/PrismLauncher/instances/` | `~/.local/share/PrismLauncher/instances/` | `~/Library/Application Support/PrismLauncher/instances/` |
| `{PRISM_EXE}` | `prismlauncher.exe` (find via `where` or check `%LOCALAPPDATA%/Programs/PrismLauncher/`) | `prismlauncher` (in PATH) | `/Applications/PrismLauncher.app/Contents/MacOS/prismlauncher` |

Pass resolved paths to all sub-skills. Sub-skills should never hardcode OS-specific paths.

## Inputs

Ask for any of these not already provided:

- **Prism instance name** — auto-detect by listing `{PRISM_INSTANCES}`
- **Target MC version** — e.g. `1.21.11`
- **Modloader** — default: `Fabric`
- **Player profile** — default: vanilla+ Fabric client (performance, subtlety, no gameplay changes)
- **Reference packs** — default: DisruptiveBuilds REFINED (`dbs-minecraft-refined`) and PLUS (`dbs-minecraft-plus`) on Modrinth
- **Server SSH host** *(optional)* — e.g. `minecraft`. Used to check which server-side companion mods are active, affecting client mod recommendations.

---

## Flow

```
prism-audit
  └─ creates decision doc
  └─ runs compat scan (lightweight: checks every mod + library for target MC build)
       └─ flags INCOMPATIBLE mods → writes compat scan section to decision doc
  └─ invokes meta-refresh (receives compat results so it knows what's already dead)
       └─ research → upgrade plan → user approves → writes meta decisions to doc
  └─ invokes version-refresh (full pass: changelogs + executor)
       └─ research → upgrade plan → user approves → appends version decisions to doc
       └─ dispatches background executor
            └─ clones instance → applies meta changes → applies version updates → config research
```

---

## Step 1 — Create decision doc

Create `./minecraft-audits/` if it doesn't exist.

Create `./minecraft-audits/prism-<instance-name>-YYYY-MM-DD.md` with this header:

```md
# Minecraft Audit — YYYY-MM-DD
Instance: <name>
MC Version: <version>
Modloader: <loader>
```

---

## Step 2 — Compat scan

Before any meta analysis, check whether each existing mod and library has a build for the target MC version. This prevents meta-refresh from recommending KEEP for mods that can't run, or ADD for mods whose required libraries are missing.

**Dispatch parallel agents** (batch by 5-6 mods each) to run the compat-check procedure on every mod and library JAR in the instance. Use `run_in_background: true`.

For each mod, record: `✓ exact`, `~ minor`, `~ community` (see compat-check skill), or `✗ none`.

**Write results to the decision doc** as a compat scan section:

```md
## Compat scan

| Mod | Type | Current Version | 26.1.2 Build? | Status |
|-----|------|-----------------|---------------|--------|
| Sodium | performance | 0.8.7 | 0.8.12 | ✓ exact |
| Architectury API | library | 19.0.1 | — | ✗ none |
```

**Present incompatible mods to the user** before proceeding. Say:

> These mods/libraries have no confirmed build for MC {version}:
> - {list}
>
> They'll be flagged for removal in the meta-refresh. Proceed?

---

## Step 3 — Invoke meta-refresh

Say: "Invoking `meta-refresh`."

Invoke `meta-refresh`, passing:
- Instance name
- MC version
- Modloader
- Player profile
- Server SSH host (if provided)
- Decision doc path
- **Compat scan results** — the list of INCOMPATIBLE mods/libraries, so meta-refresh can pre-flag them as REMOVE candidates and avoid recommending gap mods that depend on missing libraries.

Meta-refresh chains to version-refresh, which chains to the executor. No further action needed from audit.

---

## Common Mistakes

- **Skipping the compat scan** — this is the #1 failure mode. Without it, meta-refresh recommends KEEP for dead mods and ADD for mods with missing library deps. Always run compat scan first.
- **Skipping inputs** — always ask for any missing values. Don't assume MC version or instance name.
- **Wrong decision doc path** — must be `./minecraft-audits/prism-<instance-name>-YYYY-MM-DD.md`, not in the instance directory or elsewhere.
