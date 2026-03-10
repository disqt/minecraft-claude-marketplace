# disqt/minecraft

Claude Code marketplace for Minecraft server and modpack management.

## Plugins

| Plugin | Description | Status |
|--------|-------------|--------|
| **prism-modpack-audit** | Audit and update Prism Launcher Fabric modpacks | v1.0.0 |
| **papermc-server-audit** | Audit and update PaperMC server plugins | planned |

## Install

```bash
claude plugin add prism-modpack-audit@disqt/minecraft
```

## prism-modpack-audit

Full modset audit workflow for Prism Launcher Fabric instances:

1. **Meta refresh** — are your mods still best-in-class? Find better alternatives, detect gaps and redundancies using live Modrinth data
2. **Version refresh** — are your mods up to date? Check every mod for updates with changelogs
3. **Executor** — clone instance, apply approved changes, verify boot, publish zip to friends

### Skills

| Skill | Invocation |
|-------|------------|
| `minecraft-prism-mods-full-audit` | `/minecraft-prism-mods-full-audit` |
| `minecraft-prism-mods-meta-refresh` | `/minecraft-prism-mods-meta-refresh` |
| `minecraft-prism-mods-version-refresh` | `/minecraft-prism-mods-version-refresh` |
| `mc-mod-compat-check` | Claude-invoked (sub-procedure) |

### Prerequisites

- Prism Launcher installed (Windows)
- SSH access to game server (optional, for server-side companion detection)
