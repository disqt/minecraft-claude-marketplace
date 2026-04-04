#!/usr/bin/env python3
"""Modpack Release Tool -- zip, upload, changelog, publish."""

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import zipfile
from datetime import date
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent
DEFAULT_CONFIG = SCRIPT_DIR / "modpack-release.json"


def load_config(path: Path) -> dict:
    return json.loads(path.read_text())


def parse_args():
    parser = argparse.ArgumentParser(description="Release a Prism Launcher modpack version")
    parser.add_argument("instance_path", type=Path, help="Path to Prism instance directory")
    parser.add_argument("--version", required=True, help="Version to publish (e.g. 2.10)")
    parser.add_argument("--keep", type=int, help="Versions to retain on VPS (default: from config)")
    parser.add_argument("--no-notify", action="store_true", help="Skip Discord notification")
    parser.add_argument("--dry-run", action="store_true", help="Show plan without executing")
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG, help="Config file path")
    return parser.parse_args()


def validate_instance(instance_path: Path):
    """Check that the path looks like a valid Prism instance."""
    if not instance_path.is_dir():
        sys.exit(f"Error: {instance_path} is not a directory")
    if not (instance_path / "mmc-pack.json").exists():
        sys.exit(f"Error: {instance_path}/mmc-pack.json not found (not a Prism instance?)")
    mods_dir = instance_path / ".minecraft" / "mods"
    if not mods_dir.is_dir():
        sys.exit(f"Error: {mods_dir} not found")


def load_packignore(instance_path: Path) -> list[str]:
    """Read .packignore patterns (one per line, relative to instance root)."""
    packignore = instance_path / ".packignore"
    if not packignore.exists():
        return []
    return [line.strip() for line in packignore.read_text().splitlines() if line.strip()]


def should_exclude(rel_path: str, ignore_patterns: list[str]) -> bool:
    """Check if a relative path matches any .packignore pattern."""
    for pattern in ignore_patterns:
        normalized = pattern.replace("\\", "/")
        if rel_path.startswith(normalized) or rel_path.startswith(normalized + "/"):
            return True
    return False


def zip_instance(instance_path: Path, output_path: Path, root_name: str) -> int:
    """Zip the instance directory, respecting .packignore.
    Returns the zip file size in bytes.
    """
    ignore_patterns = load_packignore(instance_path)
    ignore_patterns.extend([
        ".minecraft/logs",
        ".minecraft/crash-reports",
    ])

    print("Zipping instance...")
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for file_path in sorted(instance_path.rglob("*")):
            if file_path.is_dir():
                continue
            rel = file_path.relative_to(instance_path).as_posix()
            if should_exclude(rel, ignore_patterns):
                continue
            arcname = f"{root_name}/{rel}"
            zf.write(file_path, arcname)

    size = output_path.stat().st_size
    size_mb = size / (1024 * 1024)
    print(f"  Created {output_path.name} ({size_mb:.0f} MB)")
    return size


def ssh_cmd(host: str, cmd: str) -> str:
    """Run a command on the VPS via SSH and return stdout."""
    result = subprocess.run(
        ["ssh", host, cmd],
        capture_output=True, text=True, timeout=30,
    )
    if result.returncode != 0:
        raise RuntimeError(f"SSH command failed: {cmd}\n{result.stderr}")
    return result.stdout


def get_previous_mod_list(config: dict) -> dict[str, str]:
    """Get mod jar filenames from the latest version on VPS.
    Returns {filename: filename} mapping.
    """
    host = config["vps_host"]
    vps_path = config["vps_path"]
    try:
        manifest_raw = ssh_cmd(host, f"cat {vps_path}/manifest.json")
        manifest = json.loads(manifest_raw)
    except Exception:
        return {}
    if not manifest.get("latest"):
        return {}
    prev_file = manifest["latest"]["file"]
    try:
        output = ssh_cmd(host, f"unzip -l '{vps_path}/{prev_file}' 2>/dev/null | grep '\\.jar'")
    except Exception:
        return {}
    jars = {}
    for line in output.splitlines():
        parts = line.strip().split()
        if not parts:
            continue
        path = parts[-1]
        if "/mods/" in path:
            name = path.split("/")[-1]
            jars[name] = name
    return jars


def extract_mod_version(jar_name: str) -> tuple[str, str]:
    """Split a jar filename into (prefix, version).
    E.g. 'ModName-1.2.3.jar' -> ('ModName', '1.2.3')
    """
    base = jar_name.removesuffix(".jar").removesuffix(".jar.disabled")
    m = re.match(r"^(.+?)[_-](\d+\.\d+.*)$", base)
    if m:
        return m.group(1), m.group(2)
    return base, ""


def get_local_mod_list(instance_path: Path) -> dict[str, str]:
    """Get mod jar filenames from the local instance.
    Returns {filename: filename} mapping.
    """
    mods_dir = instance_path / ".minecraft" / "mods"
    return {f.name: f.name for f in mods_dir.iterdir() if f.suffix == ".jar"}


def get_config_diff(instance_path: Path, config: dict) -> list[str]:
    """Diff config directory against previous version on VPS.
    Returns list of changelog lines for config changes.
    """
    host = config["vps_host"]
    vps_path = config["vps_path"]
    try:
        manifest_raw = ssh_cmd(host, f"cat {vps_path}/manifest.json")
        manifest = json.loads(manifest_raw)
    except Exception:
        return []
    if not manifest.get("latest"):
        return []
    prev_file = manifest["latest"]["file"]
    try:
        output = ssh_cmd(host, f"unzip -l '{vps_path}/{prev_file}' 2>/dev/null | grep '/config/'")
    except Exception:
        return []
    prev_configs = set()
    for line in output.splitlines():
        parts = line.strip().split()
        if parts:
            path = parts[-1]
            if "/config/" in path:
                prev_configs.add(path.split("/config/", 1)[-1])
    local_configs = set()
    config_dir = instance_path / ".minecraft" / "config"
    if config_dir.is_dir():
        for f in config_dir.rglob("*"):
            if f.is_file():
                local_configs.add(f.relative_to(config_dir).as_posix())
    added = local_configs - prev_configs
    removed = prev_configs - local_configs
    changes = []
    if added:
        changes.append(f"Added {len(added)} config files")
    if removed:
        changes.append(f"Removed {len(removed)} config files")
    return changes


def get_disquests_changelog(old_jars: dict, new_jars: dict, repo: str) -> list[str]:
    """If disquests version changed, fetch first 3 lines from GitHub release."""
    old_ver, new_ver = None, None
    for name in old_jars:
        if "disquests-client" in name.lower():
            _, old_ver = extract_mod_version(name)
    for name in new_jars:
        if "disquests-client" in name.lower():
            _, new_ver = extract_mod_version(name)
    if not new_ver or new_ver == old_ver:
        return []
    try:
        result = subprocess.run(
            ["gh", "release", "view", f"v{new_ver}", "--repo", repo, "--json", "body", "--jq", ".body"],
            capture_output=True, text=True, timeout=15,
        )
        if result.returncode != 0:
            return [f"Updated Disquests to v{new_ver}"]
        lines = [l.strip() for l in result.stdout.splitlines() if l.strip() and not l.startswith("#")]
        return [f"Disquests v{new_ver}:"] + [f"  {l}" for l in lines[:3]]
    except Exception:
        return [f"Updated Disquests to v{new_ver}"]


def generate_changelog(instance_path: Path, config: dict) -> list[str]:
    """Generate changelog by diffing mod jars and configs against previous VPS version."""
    old_jars = get_previous_mod_list(config)
    new_jars = get_local_mod_list(instance_path)
    changelog = []

    if not old_jars:
        changelog.append("Initial release")
        return changelog

    old_by_prefix = {}
    for name in old_jars:
        prefix, ver = extract_mod_version(name)
        old_by_prefix[prefix.lower()] = (name, ver)
    new_by_prefix = {}
    for name in new_jars:
        prefix, ver = extract_mod_version(name)
        new_by_prefix[prefix.lower()] = (name, ver)

    for prefix in sorted(set(old_by_prefix) | set(new_by_prefix)):
        old_entry = old_by_prefix.get(prefix)
        new_entry = new_by_prefix.get(prefix)
        if old_entry and not new_entry:
            changelog.append(f"Removed {old_entry[0]}")
        elif new_entry and not old_entry:
            changelog.append(f"Added {new_entry[0]}")
        elif old_entry and new_entry and old_entry[1] != new_entry[1]:
            name = new_entry[0].split("-")[0] if "-" in new_entry[0] else prefix
            changelog.append(f"Updated {name} {old_entry[1]} -> {new_entry[1]}")

    config_changes = get_config_diff(instance_path, config)
    changelog.extend(config_changes)

    dq_lines = get_disquests_changelog(old_jars, new_jars, config.get("disquests_repo", ""))
    if dq_lines:
        changelog.extend(dq_lines)

    return changelog


def main():
    args = parse_args()
    config = load_config(args.config)
    validate_instance(args.instance_path)

    mc_version = config["mc_version"]
    version = args.version
    filename = f"{mc_version} v{version}.zip"
    keep = args.keep or config.get("keep", 3)

    print(f"Modpack Release: {mc_version} v{version}")
    print("=" * 50)
    print(f"  Instance: {args.instance_path}")
    print(f"  Filename: {filename}")
    print(f"  VPS:      {config['vps_host']}:{config['vps_path']}")
    print()

    with tempfile.TemporaryDirectory() as tmp:
        zip_path = Path(tmp) / filename
        zip_size = zip_instance(args.instance_path, zip_path, f"{mc_version} v{version}")
        size_str = f"{zip_size / (1024 * 1024):.0f} MB"
        print()

        # Generate changelog
        changelog = generate_changelog(args.instance_path, config)
        print("Changelog:")
        for line in changelog:
            print(f"  {line}")
        print()

        if args.dry_run:
            print("[dry-run] Would upload, update manifest, and notify.")
            return

        confirm = input("Publish? [y/n] ").strip().lower()
        if confirm != "y":
            print("Aborted.")
            return

        # Upload and publish steps follow...


if __name__ == "__main__":
    main()
