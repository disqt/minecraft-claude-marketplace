# Executor Agent Spec

Background agent dispatched after version-refresh Step 5. Receives: decision doc path, instance name, MC version, modloader.

**Model note:** This agent makes many judgment calls (version lookups, naming, failure handling). For best results, run the parent session with Opus (`/model`).

---

## Steps

### 1. Read the decision doc

Collect all approved meta decisions (`## Meta decisions`) and approved version decisions (`## Version decisions`).

### 2. Ask the user for version increment type

Assess the approved changes and recommend one:

- **Minor increment** (e.g. `v1.1` → `v1.2.beta`): few changes, mostly bugfixes or version bumps, no significant UX difference
- **Major increment** (e.g. `v1.1` → `v2.0.beta`): many mods added/replaced, noticeable change in audio/performance/UX

Present your recommendation with a one-line justification, then ask:
> Recommended: **major** — 13 of 31 mods changing (11 adds, 2 replaces), significant new audio and performance profile. Use **major** or **minor**?

Wait for the user's response before proceeding.

### 3. Clone the instance

```
xcopy /E /I /H "<old-instance-path>" "<new-instance-path>"
```

**Naming rules:**
- Minor: bump the minor version digit — `v1.1` → `v1.2.beta`, `v2.3` → `v2.4.beta`
- Major: bump the major version, reset minor to 0 — `v1.1` → `v2.0.beta`, `v2.3` → `v3.0.beta`
- **NEVER append `(2)` or any copy suffix** — that's a Prism artifact. If the target `.beta` already exists, delete it first (it's from an aborted run — beta instances are disposable by design).

### 4. Tell the user

State the new instance name and remind them to refresh Prism (Ctrl+R).

### 5. Delete removals

For each `REMOVE` or `REDUNDANT`: delete the JAR (and `.disabled` twin if present) from the new instance `.minecraft/mods/`. Sequential, instant.

### 6. Dispatch parallel download agents

For every `ADD`, `REPLACE`, and `UPDATE` in the decision doc, dispatch one download agent with `run_in_background: true`.

Read `./download-agent-prompt.md` (in this skill's directory) for the agent spec and the variables to inject per agent.

**Wait for all download agents to complete before proceeding.**

If any download agent returns `FAILED`: report the failure to the user and stop. Ask how to proceed before continuing.

### 7. Dispatch config research agents + apply ENABLEs

These two can happen concurrently:

- **Config research (parallel):** For each `ADD` or `REPLACE`, dispatch one config research agent with `run_in_background: true`. Read `../minecraft-prism-mods-meta-refresh/config-research-agent.md` for the agent spec. Resolve this relative path against this skill's base directory before dispatching.
- **ENABLEs (instant):** For each `ENABLE`, rename `<mod>.jar.disabled` → `<mod>.jar`.

### 8. Wait for all config research agents to complete.

### 9. Verify the client boots

Dispatch a boot verification agent (`run_in_background: false`, wait for result).

Read `./boot-verification-agent.md` (in this skill's directory) for the agent spec. Pass: new instance path, MC version.

- If boot **fails**: report the crash log excerpt and stop. Do NOT promote. Ask the user how to proceed.
- If boot **passes**: continue to step 10.

### 10. Report

Summarise: changes applied (meta + version), config files written, boot result.

Then tell the user:
> Instance `<name>.beta` is ready and verified. Test it yourself, then reply **"promote"** to rename it to `<name-without-.beta>` (e.g. `1.21.11 v2.0`).

### 11. On "promote"

Rename the instance folder from `<name>.beta` to `<name-without-.beta>`. Remind user to refresh Prism (Ctrl+R).

### 12. Publish the modpack

After promote, zip and upload the instance so friends can download it.

**12a. Zip with exclusions:**

```bash
cd "C:/Users/leole/AppData/Roaming/PrismLauncher/instances"
7z a -tzip "<instance-name>.zip" "<instance-name>/" \
  -xr!"Distant_Horizons_server_data" \
  -xr!"screenshots" \
  -xr!"saves" \
  -xr!"downloads" \
  -xr!".mixin.out" \
  -xr!"debug" \
  -xr!"logs"
```

If `7z` is not available, use PowerShell:
```powershell
$src = "C:/Users/leole/AppData/Roaming/PrismLauncher/instances/<instance-name>"
$tmp = "$env:TEMP/<instance-name>"
$excludes = @("Distant_Horizons_server_data","screenshots","saves","downloads",".mixin.out","debug","logs")
robocopy $src $tmp /E /XD $excludes /NFL /NDL /NJH /NJS
Compress-Archive -Path $tmp -DestinationPath "C:/Users/leole/AppData/Roaming/PrismLauncher/instances/<instance-name>.zip"
Remove-Item -Recurse -Force $tmp
```

**12b. Upload to VPS:**

```bash
scp "C:/Users/leole/AppData/Roaming/PrismLauncher/instances/<instance-name>.zip" dev:/home/dev/prism/
```

**12c. Update the `latest.zip` symlink:**

```bash
ssh dev "cd /home/dev/prism && ln -sf '<instance-name>.zip' latest.zip"
```

**12d. Update `manifest.json`:**

Read the current manifest from the VPS, prepend the new version to the `versions` array, update `latest`, and write it back:

```bash
ssh dev "python3 -c \"
import json, os
path = '/home/dev/prism/manifest.json'
data = json.load(open(path)) if os.path.exists(path) else {'latest':{}, 'versions':[]}
entry = {
  'version': '<instance-name>',
  'file': '<instance-name>.zip',
  'date': '$(date +%Y-%m-%d)',
  'mc': '<mc-version>',
  'modloader': '<modloader>',
  'size': '<size in MB> MB'
}
data['latest'] = entry
data['versions'].insert(0, entry)
json.dump(data, open(path,'w'), indent=2)
print('manifest updated')
\""
```

Compute `<size in MB>` from the zip file size before uploading.

**12e. Cleanup — keep last 3 zips (exclude symlink):**

```bash
ssh dev "cd /home/dev/prism && ls -t *.zip | grep -v latest.zip | tail -n +4 | xargs -r rm -f"
```

**12f. Report the URLs:**

> Modpack published: **https://disqt.com/minecraft/**
> - Latest (stable link): `https://disqt.com/minecraft/modpack/latest.zip`
> - This version: `https://disqt.com/minecraft/modpack/<instance-name>.zip`
