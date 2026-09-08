"""Find existing projects without migrating, opening or modifying their files."""
from __future__ import annotations

import os
import sys
from pathlib import Path


INSTALL_NAMES = ("牙槽骨吸收测量AI", "牙槽骨吸收测量")
INSTALL_IDS = (
    "{9D7D2163-EE63-4815-B2C1-37EE3B4E4B50}",
    "{8F3C1A62-4D77-4A5E-9B21-7C0E5A9D3F14}",
)


def _registered_install_dirs() -> list[Path]:
    """Both released installers are per-user; no machine-wide scan is needed."""
    try:
        import winreg
    except ImportError:
        return []
    found = []
    for app_id in INSTALL_IDS:
        key = "Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\" + app_id + "_is1"
        for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
            try:
                with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ | view) as reg:
                    value, _ = winreg.QueryValueEx(reg, "InstallLocation")
                    if isinstance(value, str) and value:
                        found.append(Path(value))
            except OSError:
                continue
    return found


def discover_existing_projects(last_project: str | Path | None = None) -> list[Path]:
    """Return known roots for an explicit UI open action; never auto-open them.

    Preserve paths instead of copying images or rewriting case status. Portable
    builds can keep a project beside their executable; installed versions also
    used that layout. Custom project locations come from the shared last_project
    setting. No directory trees or patient files are scanned.
    """
    candidates = [Path(last_project)] if last_project else []
    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).parent)
    candidates.extend(_registered_install_dirs())
    local = os.environ.get("LOCALAPPDATA")
    if local:
        candidates.extend(Path(local) / "Programs" / name for name in INSTALL_NAMES)
    found: list[Path] = []
    for candidate in candidates:
        try:
            root = candidate.resolve()
            if root not in found and (root / "project.json").is_file():
                found.append(root)
        except (OSError, ValueError, RuntimeError):
            continue
    return found
