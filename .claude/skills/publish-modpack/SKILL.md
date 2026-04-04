---
name: publish-modpack
description: Use when the user wants to publish, release, or upload a new Prism Launcher modpack version to disqt.com/minecraft/modpack/. Triggers on "publish modpack", "push modpack", "release modpack", "upload modpack", or when making a new version available to players.
---

# Publish Modpack

Publishes a Prism Launcher modpack version to disqt.com/minecraft using the release CLI at `C:\Users\leole\Documents\code\minecraft\prism-modpack-releaser\modpack_release.py`.

The script zips the instance (respecting `.packignore`), auto-generates a changelog by diffing mods against the previous VPS version, uploads via SCP, updates `manifest.json`, rotates the `latest.zip` symlink, prunes old versions, and posts to Discord.

## Prerequisites

**Minecraft must be closed** before running. Locked files cause incomplete zips.

## Steps

1. **Resolve the instance path.** List instances in `C:\Users\leole\AppData\Roaming\PrismLauncher\instances\` matching `*.* v*`. Use the one the user specifies, or ask.

2. **Resolve the version number.** Read `<instance>/.minecraft/modpack-version.txt` if it exists. Confirm with the user.

3. **Check `.packignore` exists** in the instance root. If missing, warn the user -- without it, runtime dirs (saves, screenshots, DH data, logs) will bloat the zip (~1 GB vs ~200 MB).

4. **Dry-run first** to preview the changelog:
   ```bash
   python C:\Users\leole\Documents\code\minecraft\prism-modpack-releaser\modpack_release.py "<instance>" --version "<version>" --dry-run
   ```

5. **Run for real** once the user approves:
   ```bash
   python C:\Users\leole\Documents\code\minecraft\prism-modpack-releaser\modpack_release.py "<instance>" --version "<version>"
   ```
   The script prompts for confirmation before publishing.

6. **Update CLAUDE.md** -- update the "Current modpack" line in `./CLAUDE.md` to reflect the new version, if one exists.

7. **Report** the result: version published, zip size, changelog summary, Discord notification status.

## CLI Options

| Flag | Effect |
|------|--------|
| `--dry-run` | Preview without publishing |
| `--no-notify` | Skip Discord webhook |
| `--keep N` | Versions to retain on VPS (default: 3) |
| `--config PATH` | Override config file |

## Gotchas

- Config file at `prism-modpack-releaser/modpack-release.json` contains the Discord webhook secret and is gitignored. If missing, copy from `modpack-release.example.json` and fill in the webhook URL.
- The DisqtVersion server plugin refreshes from the manifest URL every 30 minutes -- no manual reload needed after publishing.
- The zip filename includes spaces (e.g. `1.21.11 v2.11.zip`). The script handles quoting for SCP and SSH.
