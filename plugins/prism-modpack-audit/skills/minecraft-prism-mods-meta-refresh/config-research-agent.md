# Config Research Agent

Dispatched by the executor (end of version-refresh) for every mod that was added or used as a replacement. Run in background (`run_in_background: true`), one agent per mod.

---

## Steps

1. **Find source repo:** `GET https://api.modrinth.com/v2/project/{id}` → read `source_url`
2. **Locate config file in repo:** check `src/main/resources/`, `/config/`, look for `.json` / `.toml` / `.yaml` config files
3. **If no config file found:** search source for classes named `Config`, `Settings`, `Options`, `ModConfig` — read fields and defaults
4. **For each config option:** understand name, default, valid values, and effect
5. **Reason about optimal values** for vanilla+ Fabric client — maximize performance, keep visuals subtle, no gameplay changes
6. **Write tuned config file** to new instance `.minecraft/config/<mod-id>.<ext>`
7. **Return report:**

```
## Config Report: {mod-name}

- **Source repo:** {url}
- **Config file written:** {path, e.g. .minecraft/config/lithium.toml}

### Settings changed from default
| Setting | Default | Applied | Reason |
|---------|---------|---------|--------|
| chunk_loading.threads | auto | 4 | cap threads for client-side stability |

### Settings left at default
| Setting | Value | Reason kept |
|---------|-------|-------------|
| render.lod_transition | false | not applicable client-only |

### Notes
{any warnings, e.g. "no config file found — mod uses hardcoded defaults, nothing to tune"}
```
