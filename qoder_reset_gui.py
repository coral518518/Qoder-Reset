#!/usr/bin/env python3
"""
Qoder Reset Tool - Modern GUI Version
Implemented using PyQt5, fully designed according to user prototype
"""

__version__ = "1.3.0"

import os
import sys

if hasattr(sys.stdout, "reconfigure"):
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

import json
import uuid
import shutil
import hashlib
import subprocess
import webbrowser
import platform
import random
from pathlib import Path
from datetime import datetime, timedelta
from typing import Callable, Mapping, Optional, Tuple
import sqlite3

try:
    from PyQt5.QtWidgets import *
    from PyQt5.QtCore import *
    from PyQt5.QtGui import *
    HAS_PYQT5 = True
except ImportError:
    try:
        from PyQt6.QtWidgets import *
        from PyQt6.QtCore import *
        from PyQt6.QtGui import *
        HAS_PYQT5 = True
    except ImportError:
        try:
            from PySide6.QtWidgets import *
            from PySide6.QtCore import *
            from PySide6.QtGui import *
            HAS_PYQT5 = True
        except ImportError:
            HAS_PYQT5 = False

            class QMainWindow:
                def __init__(self, *args, **kwargs):
                    pass

            class QWidget:
                def __init__(self, *args, **kwargs):
                    pass

            class QDialog:
                def __init__(self, *args, **kwargs):
                    pass

            class QApplication:
                @staticmethod
                def instance():
                    return None

                @staticmethod
                def clipboard():
                    class DummyClipboard:
                        def setText(self, text):
                            pass
                    return DummyClipboard()

                def __init__(self, *args, **kwargs):
                    pass

            class QMessageBox:
                Yes = 16384
                No = 65536

                @staticmethod
                def question(*args, **kwargs):
                    return 16384

                @staticmethod
                def information(*args, **kwargs):
                    pass

                @staticmethod
                def warning(*args, **kwargs):
                    pass

                @staticmethod
                def critical(*args, **kwargs):
                    pass


def _safe_write_text(path: Path, content: str, encoding: str = "utf-8"):
    """Write text ensuring parent directory exists and clearing read-only flags."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            os.chmod(path, 0o666)
        except Exception:
            pass
    path.write_text(content, encoding=encoding)


def _safe_unlink(path: Path) -> bool:
    """Safely remove a file clearing read-only permissions."""
    if path.exists():
        try:
            os.chmod(path, 0o666)
        except Exception:
            pass
        try:
            path.unlink()
            return True
        except Exception:
            return False
    return False


def _repair_sqlite_fts(db_path: Path) -> bool:
    """Repair/rebuild FTS5 virtual table in main.sqlite if format was invalidated."""
    if not db_path.is_file():
        return False
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type in ('table', 'view') AND name='chat_session_search_fts'")
        if cur.fetchone():
            try:
                cur.execute(
                    "INSERT OR REPLACE INTO chat_session_search_fts_config (k, v) VALUES ('version', 4)"
                )
                cur.execute(
                    "INSERT INTO chat_session_search_fts(chat_session_search_fts) VALUES('rebuild')"
                )
                conn.commit()
            except Exception:
                pass
        conn.close()
        return True
    except Exception:
        return False


def _purge_sqlite_chat_data(db_path: Path) -> int:
    """Purge chat/session/turn tables from Modern Qoder main.sqlite safely without corrupting FTS5."""
    if not db_path.is_file():
        return 0
    chat_tables = [
        "chat_sessions",
        "chat_session_sidebar_placements",
        "chat_session_sidebar_groups",
        "chat_session_sidebar_group_memberships",
        "chat_session_messages",
        "chat_session_highlights",
        "chat_session_recaps",
        "chat_session_context_usage",
        "chat_generated_image_assets",
        "chat_session_generated_images",
        "chat_session_input_receipts",
        "chat_session_search_segments",
        "chat_session_history_revisions",
        "chat_session_turn_states",
        "chat_session_input_provenance",
        "turn_file_change_sets",
        "turn_file_change_files",
        "turn_file_change_patches",
        "turn_file_change_unsupported",
        "turn_file_change_operations",
        "discussion_agent_contexts",
        "discussion_agent_context_deliveries",
        "discussion_agent_workspaces",
        "discussion_launches",
        "cloud_session_cache",
    ]
    purged = 0
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type in ('table', 'view')")
        existing_tables = set(r[0] for r in cur.fetchall())
        for table in chat_tables:
            if table in existing_tables:
                try:
                    cur.execute(f'DELETE FROM "{table}"')
                    purged += 1
                except Exception:
                    pass

        # Safely rebuild/clean FTS5 full-text index without corrupting its internal format
        if "chat_session_search_fts" in existing_tables:
            try:
                cur.execute(
                    "INSERT OR REPLACE INTO chat_session_search_fts_config (k, v) VALUES ('version', 4)"
                )
                cur.execute(
                    "INSERT INTO chat_session_search_fts(chat_session_search_fts) VALUES('rebuild')"
                )
                purged += 1
            except Exception:
                try:
                    cur.execute(
                        "INSERT INTO chat_session_search_fts(chat_session_search_fts) VALUES('delete-all')"
                    )
                except Exception:
                    pass

        conn.commit()
        try:
            conn.execute("VACUUM")
        except Exception:
            pass
        conn.close()
    except Exception:
        pass
    return purged


def _purge_sqlite_auth_data(db_path: Path) -> int:
    """Purge account/credential tables from Modern Qoder main.sqlite."""
    if not db_path.is_file():
        return 0
    auth_tables = [
        "account_profiles",
        "collaboration_runtime_credentials",
        "mcp_oauth_credentials",
        "cloud_session_cache",
    ]
    purged = 0
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type in ('table', 'view')")
        existing_tables = set(r[0] for r in cur.fetchall())
        for table in auth_tables:
            if table in existing_tables:
                try:
                    cur.execute(f'DELETE FROM "{table}"')
                    purged += 1
                except Exception:
                    pass
        conn.commit()
        try:
            conn.execute("VACUUM")
        except Exception:
            pass
        conn.close()
    except Exception:
        pass
    return purged


def _update_sqlite_device_identity(db_path: Path, new_device_id: Optional[str] = None) -> bool:
    """Update device UUID in local_device_identity table in main.sqlite."""
    if not db_path.is_file():
        return False
    dev_id = new_device_id or str(uuid.uuid4())
    try:
        conn = sqlite3.connect(str(db_path))
        cur = conn.cursor()
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='local_device_identity'")
        if cur.fetchone():
            cur.execute(
                "UPDATE local_device_identity SET device_id = ?, initialized_at = ? WHERE singleton_key = 1",
                (dev_id, datetime.now().isoformat()),
            )
            if cur.rowcount == 0:
                cur.execute(
                    "INSERT OR REPLACE INTO local_device_identity (singleton_key, device_id, initialized_at) VALUES (1, ?, ?)",
                    (dev_id, datetime.now().isoformat()),
                )
            conn.commit()
            conn.close()
            return True
        conn.close()
    except Exception:
        pass
    return False


def _reset_qoder_data_json(path: Path) -> bool:
    """Reset turns, issues, deliveries, and history arrays in qoder-data.v1.json."""
    if not path.is_file():
        return False
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        reset_fields = [
            "turns",
            "turnInputs",
            "sessionDeliveries",
            "attention",
            "evidence",
            "projects",
            "issues",
            "comments",
            "subscriptions",
            "updates",
            "localProjectOverrides",
            "localIssueOverrides",
        ]
        modified = False
        for f in reset_fields:
            if f in data and data[f]:
                data[f] = []
                modified = True
        if modified:
            path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
        return True
    except Exception:
        return False


def resolve_qoder_home_dir(home_dir: Optional[Path] = None) -> Path:
    """Resolve user-level Qoder agent directory (~/.qoder)."""
    home = home_dir or Path.home()
    return home / ".qoder"


def resolve_qoder_data_dir(
    system: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    home_dir: Optional[Path] = None,
) -> Path:
    """
    Resolve primary Qoder application data directory.
    Supports both Modern Qoder (com.qoder.app.stable) and Legacy Qoder (Qoder).
    """
    system = system or platform.system()
    env = env or os.environ
    home_dir = home_dir or Path.home()

    if system == "Windows":
        appdata = env.get("APPDATA")
        base = Path(appdata) if appdata else (home_dir / "AppData" / "Roaming")
        # Modern Qoder (v0.4.x+) uses com.qoder.app.stable
        modern_dir = base / "com.qoder.app.stable"
        if modern_dir.exists():
            return modern_dir
        legacy_dir = base / "Qoder"
        if legacy_dir.exists():
            return legacy_dir
        # Default fallback for backwards compatibility
        return legacy_dir

    if system == "Linux":
        xdg_config_home = env.get("XDG_CONFIG_HOME")
        base = Path(xdg_config_home) if xdg_config_home else (home_dir / ".config")
        modern_dir = base / "com.qoder.app.stable"
        if modern_dir.exists():
            return modern_dir
        return base / "Qoder"

    # macOS (and default fallback)
    base = home_dir / "Library" / "Application Support"
    modern_dir = base / "com.qoder.app.stable"
    if modern_dir.exists():
        return modern_dir
    return base / "Qoder"


def resolve_all_qoder_targets(
    system: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
    home_dir: Optional[Path] = None,
) -> Mapping[str, object]:
    """Discover all modern and legacy Qoder directories across the system."""
    system = system or platform.system()
    env = env or os.environ
    home_dir = home_dir or Path.home()

    primary_dir = resolve_qoder_data_dir(system, env, home_dir)
    home_qoder = resolve_qoder_home_dir(home_dir)

    candidate_appdata = []
    if system == "Windows":
        appdata = env.get("APPDATA")
        base = Path(appdata) if appdata else (home_dir / "AppData" / "Roaming")
        for d in [base / "com.qoder.app.stable", base / "Qoder"]:
            if d.exists() and d not in candidate_appdata:
                candidate_appdata.append(d)
    elif system == "Darwin":
        base = home_dir / "Library" / "Application Support"
        for d in [base / "com.qoder.app.stable", base / "Qoder"]:
            if d.exists() and d not in candidate_appdata:
                candidate_appdata.append(d)
    elif system == "Linux":
        xdg = env.get("XDG_CONFIG_HOME")
        base = Path(xdg) if xdg else (home_dir / ".config")
        for d in [base / "com.qoder.app.stable", base / "Qoder"]:
            if d.exists() and d not in candidate_appdata:
                candidate_appdata.append(d)

    if primary_dir not in candidate_appdata:
        candidate_appdata.append(primary_dir)

    local_dirs = []
    if system == "Windows":
        local_appdata = env.get("LOCALAPPDATA")
        if local_appdata:
            lb = Path(local_appdata)
            for ld in [lb / "Qoder", lb / "qoder", lb / "qoder-updater"]:
                if ld.exists():
                    local_dirs.append(ld)

    return {
        "primary_dir": primary_dir,
        "appdata_dirs": candidate_appdata,
        "home_qoder": home_qoder,
        "home_qoder_exists": home_qoder.exists(),
        "local_dirs": local_dirs,
    }


def _qoder_platform_value(system: Optional[str] = None) -> str:
    system = system or platform.system()
    if system == "Windows":
        return "win32"
    if system == "Linux":
        return "linux"
    return "darwin"


def kill_qoder_process(
    system: Optional[str] = None,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> Tuple[bool, str]:
    """
    Best-effort attempt to terminate Qoder and its background helper/launcher processes.
    Returns (success, details) where details is stdout/stderr text when available.
    """
    system = system or platform.system()
    details = []

    if system == "Windows":
        targets = [
            "qoder.exe",
            "Qoder.exe",
            "Qoder Launcher.exe",
            "qoder-context-hook.exe",
            "QoderComputerUse.exe",
        ]
        any_success = False
        for proc in targets:
            result = run(
                ["taskkill", "/F", "/T", "/IM", proc],
                capture_output=True,
                text=True,
            )
            out = getattr(result, "stdout", "") or ""
            err = getattr(result, "stderr", "") or ""
            comb = (out + "\n" + err).strip()
            if result.returncode == 0:
                any_success = True
                details.append(f"Terminated {proc}")
            elif (
                "not found" in comb.lower()
                or "没有找到" in comb
                or "无法找到" in comb
            ):
                pass
            else:
                if comb:
                    details.append(comb)

        import time

        time.sleep(0.5)
        return True, (
            "\n".join(details)
            if details
            else "Qoder processes terminated or not running."
        )

    elif system == "Darwin":
        run(["pkill", "-f", "-i", "qoder"], capture_output=True, text=True)
        return True, "Terminated Qoder processes on macOS"
    elif system == "Linux":
        run(["pkill", "-f", "-i", "qoder"], capture_output=True, text=True)
        return True, "Terminated Qoder processes on Linux"
    else:
        return False, f"Unsupported platform: {system}"


def reset_qoder_machine_id(qoder_support_dir: Path) -> str:
    """Reset machine ID across Modern, Legacy, and Home ~/.qoder locations."""
    if not qoder_support_dir.exists():
        qoder_support_dir.mkdir(parents=True, exist_ok=True)

    new_machine_id = str(uuid.uuid4())

    # 1. Legacy machineid file
    machine_id_file = qoder_support_dir / "machineid"
    _safe_write_text(machine_id_file, new_machine_id)

    # 2. Modern Qoder auth.machine-id file
    auth_mid = qoder_support_dir / "auth.machine-id"
    _safe_write_text(auth_mid, new_machine_id + "\n")

    # 3. Modern Qoder ~/.qoder context bundler machine_id
    dot_qoder = resolve_qoder_home_dir()
    plugin_mid = (
        dot_qoder
        / "plugins"
        / "data"
        / "qoder-context-qoderapp-bundler"
        / "machine_id"
    )
    if plugin_mid.parent.exists():
        _safe_write_text(plugin_mid, new_machine_id)

    # 4. Modern Qoder ~/.qoder/installation_id
    if dot_qoder.exists():
        _safe_write_text(dot_qoder / "installation_id", str(uuid.uuid4()) + "\n")

    # 5. Modern Qoder ~/.qoder/umid-cache.json
    _safe_unlink(dot_qoder / "umid-cache.json")

    # 6. Modern Qoder first-launch onboarding reset
    onboarding = qoder_support_dir / "first-launch-onboarding.v1.json"
    _safe_unlink(onboarding)

    # 7. Modern Qoder SQLite device identity
    main_db = qoder_support_dir / "main.sqlite"
    _update_sqlite_device_identity(main_db, new_machine_id)

    return new_machine_id


def reset_qoder_telemetry(
    qoder_support_dir: Path, system: Optional[str] = None
) -> Mapping[str, str]:
    if not qoder_support_dir.exists():
        qoder_support_dir.mkdir(parents=True, exist_ok=True)

    storage_json_file = (
        qoder_support_dir / "User" / "globalStorage" / "storage.json"
    )
    storage_json_file.parent.mkdir(parents=True, exist_ok=True)

    if storage_json_file.exists():
        try:
            data = json.loads(storage_json_file.read_text(encoding="utf-8"))
        except Exception:
            data = {}
    else:
        data = {}

    new_uuid = str(uuid.uuid4())
    machine_id_hash = hashlib.sha256(new_uuid.encode()).hexdigest()
    device_id = str(uuid.uuid4())
    sqm_id = str(uuid.uuid4())
    session_id = str(uuid.uuid4())
    installation_id = str(uuid.uuid4())

    data["telemetry.machineId"] = machine_id_hash
    data["telemetry.devDeviceId"] = device_id
    data["telemetry.sqmId"] = sqm_id
    data["telemetry.sessionId"] = session_id
    data["telemetry.installationId"] = installation_id

    # Additional identifiers commonly used as fallbacks.
    data["telemetry.clientId"] = str(uuid.uuid4())
    data["telemetry.userId"] = str(uuid.uuid4())
    data["telemetry.anonymousId"] = str(uuid.uuid4())
    data["machineId"] = machine_id_hash
    data["deviceId"] = device_id
    data["installationId"] = str(uuid.uuid4())
    data["hardwareId"] = str(uuid.uuid4())
    data["platformId"] = str(uuid.uuid4())

    data["system.platform"] = _qoder_platform_value(system)
    data["system.arch"] = platform.machine()

    storage_json_file.write_text(
        json.dumps(data, indent=4, ensure_ascii=False),
        encoding="utf-8",
    )

    # Clear active telemetry runs in ~/.qoder
    dot_qoder = resolve_qoder_home_dir()
    telemetry_runs_dir = dot_qoder / "tmp" / "telemetry"
    if telemetry_runs_dir.exists():
        try:
            shutil.rmtree(telemetry_runs_dir)
        except Exception:
            pass

    return {
        "telemetry.machineId": machine_id_hash,
        "telemetry.devDeviceId": device_id,
        "telemetry.sqmId": sqm_id,
        "telemetry.sessionId": session_id,
        "telemetry.installationId": installation_id,
    }


def check_is_qoder_running(
    system: Optional[str] = None,
    run: Callable[..., subprocess.CompletedProcess] = subprocess.run,
) -> bool:
    """Check if Qoder or its launcher is currently running (cross-platform)."""
    system = system or platform.system()
    try:
        if system == "Windows":
            result = run(
                ["tasklist"],
                capture_output=True,
                text=True,
            )
            out = getattr(result, "stdout", "").lower()
            return any(
                p in out
                for p in [
                    "qoder.exe",
                    "qoder launcher.exe",
                    "qoder-context-hook.exe",
                ]
            )
        elif system == "Darwin" or system == "Linux":
            result = run(
                ["pgrep", "-f", "-i", "qoder"], capture_output=True, text=True
            )
            return result.returncode == 0
        return False
    except Exception:
        return False


def backup_qoder_identity(
    qoder_support_dir: Path,
    backup_dest_dir: Optional[Path] = None,
) -> Path:
    """
    Back up Qoder identity files (auth.machine-id, machineid, storage.json, hardware_info.json, ~/.qoder status)
    to a timestamped directory. Returns the path of the created backup directory.
    """
    if not qoder_support_dir.exists():
        qoder_support_dir.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if backup_dest_dir is None:
        backup_base = qoder_support_dir.parent / "Qoder_Backups"
        target_dir = backup_base / f"backup_{timestamp}"
    else:
        target_dir = backup_dest_dir

    target_dir.mkdir(parents=True, exist_ok=True)

    manifest = {
        "timestamp": timestamp,
        "created_at": datetime.now().isoformat(),
        "version": __version__,
        "platform": platform.system(),
        "files_backed_up": [],
    }

    # Backup files from qoder_support_dir
    id_files = [
        "auth.machine-id",
        "auth.v1.dat",
        "auth-profile-overlays.v1.dat",
        "first-launch-onboarding.v1.json",
        "machineid",
        "deviceid",
        "hardware_uuid",
        "system_uuid",
        "platform_id",
        "installation_id",
        "hardware_info.json",
    ]
    for filename in id_files:
        src = qoder_support_dir / filename
        if src.is_file():
            dst = target_dir / filename
            shutil.copy2(src, dst)
            manifest["files_backed_up"].append(filename)

    # Backup storage.json
    storage_json = qoder_support_dir / "User" / "globalStorage" / "storage.json"
    if storage_json.is_file():
        storage_dest = target_dir / "storage.json"
        shutil.copy2(storage_json, storage_dest)
        manifest["files_backed_up"].append("User/globalStorage/storage.json")

    # Backup from ~/.qoder
    dot_qoder = resolve_qoder_home_dir()
    status_file = dot_qoder / ".qoder-app-status.json"
    if status_file.is_file():
        shutil.copy2(status_file, target_dir / "dot_qoder_app_status.json")
        manifest["files_backed_up"].append(".qoder-app-status.json")

    plugin_mid = (
        dot_qoder
        / "plugins"
        / "data"
        / "qoder-context-qoderapp-bundler"
        / "machine_id"
    )
    if plugin_mid.is_file():
        shutil.copy2(plugin_mid, target_dir / "plugin_machine_id")
        manifest["files_backed_up"].append("plugin_machine_id")

    inst_file = dot_qoder / "installation_id"
    if inst_file.is_file():
        shutil.copy2(inst_file, target_dir / "dot_qoder_installation_id")
        manifest["files_backed_up"].append("~/.qoder/installation_id")

    umid_file = dot_qoder / "umid-cache.json"
    if umid_file.is_file():
        shutil.copy2(umid_file, target_dir / "dot_qoder_umid_cache.json")
        manifest["files_backed_up"].append("~/.qoder/umid-cache.json")

    manifest_file = target_dir / "manifest.json"
    manifest_file.write_text(
        json.dumps(manifest, indent=4, ensure_ascii=False), encoding="utf-8"
    )
    return target_dir


def list_qoder_backups(qoder_support_dir: Optional[Path] = None) -> list:
    """List available identity backups, ordered newest first."""
    qoder_dir = qoder_support_dir or resolve_qoder_data_dir()
    backup_base = qoder_dir.parent / "Qoder_Backups"
    if not backup_base.is_dir():
        return []
    backups = [
        p
        for p in backup_base.iterdir()
        if p.is_dir() and (p / "manifest.json").is_file()
    ]
    backups.sort(key=lambda p: p.name, reverse=True)
    return backups


def restore_qoder_identity(
    backup_dir: Path, qoder_support_dir: Path
) -> Tuple[bool, str]:
    """Restore identity files from backup into qoder_support_dir and ~/.qoder."""
    if not backup_dir.is_dir():
        return False, f"Backup directory not found: {backup_dir}"

    qoder_support_dir.mkdir(parents=True, exist_ok=True)
    restored_count = 0

    for src in backup_dir.iterdir():
        if src.name in (
            "manifest.json",
            "storage.json",
            "dot_qoder_app_status.json",
            "plugin_machine_id",
            "dot_qoder_installation_id",
            "dot_qoder_umid_cache.json",
        ):
            continue
        if src.is_file():
            dst = qoder_support_dir / src.name
            shutil.copy2(src, dst)
            restored_count += 1

    storage_backup = backup_dir / "storage.json"
    if storage_backup.is_file():
        storage_dest = (
            qoder_support_dir / "User" / "globalStorage" / "storage.json"
        )
        storage_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(storage_backup, storage_dest)
        restored_count += 1

    # Restore ~/.qoder files
    dot_qoder = resolve_qoder_home_dir()
    status_backup = backup_dir / "dot_qoder_app_status.json"
    if status_backup.is_file():
        dot_qoder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(status_backup, dot_qoder / ".qoder-app-status.json")
        restored_count += 1

    plugin_mid_backup = backup_dir / "plugin_machine_id"
    if plugin_mid_backup.is_file():
        plugin_mid_dest = (
            dot_qoder
            / "plugins"
            / "data"
            / "qoder-context-qoderapp-bundler"
            / "machine_id"
        )
        plugin_mid_dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(plugin_mid_backup, plugin_mid_dest)
        restored_count += 1

    inst_backup = backup_dir / "dot_qoder_installation_id"
    if inst_backup.is_file():
        dot_qoder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(inst_backup, dot_qoder / "installation_id")
        restored_count += 1

    umid_backup = backup_dir / "dot_qoder_umid_cache.json"
    if umid_backup.is_file():
        dot_qoder.mkdir(parents=True, exist_ok=True)
        shutil.copy2(umid_backup, dot_qoder / "umid-cache.json")
        restored_count += 1

    return (
        True,
        f"Successfully restored {restored_count} files from {backup_dir.name}",
    )


def check_for_updates(current_version: str = __version__) -> Mapping[str, object]:
    """Check GitHub releases API for newer Qoder-Free versions."""
    url = ""
    if not url:
        return {
            "success": True,
            "has_update": False,
            "latest_version": current_version,
            "current_version": current_version,
            "url": "",
            "release_notes": "",
        }
    try:
        import urllib.request

        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": f"Qoder-Free-Updater/{current_version}",
                "Accept": "application/vnd.github.v3+json",
            },
        )
        with urllib.request.urlopen(req, timeout=5) as response:
            if response.status == 200:
                data = json.loads(response.read().decode("utf-8"))
                tag_name = data.get("tag_name", "").lstrip("v")
                html_url = data.get(
                    "html_url",
                    "",
                )
                body = data.get("body", "")

                def _parse_v(v: str):
                    return [int(x) if x.isdigit() else x for x in v.split(".")]

                has_update = False
                if tag_name:
                    try:
                        has_update = _parse_v(tag_name) > _parse_v(current_version)
                    except Exception:
                        has_update = tag_name != current_version

                return {
                    "success": True,
                    "has_update": has_update,
                    "latest_version": tag_name or "unknown",
                    "current_version": current_version,
                    "url": html_url,
                    "release_notes": body,
                }
    except Exception as e:
        return {
            "success": False,
            "has_update": False,
            "error": str(e),
            "latest_version": "unknown",
            "current_version": current_version,
            "url": "",
            "release_notes": "",
        }

    return {
        "success": False,
        "has_update": False,
        "error": "Unknown error",
        "latest_version": "unknown",
        "current_version": current_version,
        "url": "",
        "release_notes": "",
    }


def _configure_qt_runtime():
    """
    Best-effort Qt plugin path hardening.

    Helps avoid: "This application failed to start because no Qt platform plugin could be initialized"
    """
    # Some environments carry a broken/mismatched QT_PLUGIN_PATH that breaks plugin discovery.
    # Prefer the PyQt5-bundled plugins path (or PyInstaller bundle) when available.
    env_keys = (
        "QT_PLUGIN_PATH",
        "QT_QPA_PLATFORM_PLUGIN_PATH",
    )

    def _set_if_missing(key, value):
        if value and not os.environ.get(key):
            os.environ[key] = value

    def _first_existing_dir(candidates):
        for candidate in candidates:
            try:
                if candidate and Path(candidate).is_dir():
                    return str(Path(candidate))
            except Exception:
                continue
        return None

    def _platforms_dir(plugins_dir):
        if not plugins_dir:
            return None
        platforms = Path(plugins_dir) / "platforms"
        return str(platforms) if platforms.is_dir() else None

    try:
        # PyInstaller onefile/onedir support
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            base = Path(getattr(sys, "_MEIPASS"))
            plugin_candidates = [
                base / "PyQt5" / "Qt5" / "plugins",
                base / "PyQt5" / "Qt" / "plugins",
                base / "Qt5" / "plugins",
                base / "Qt" / "plugins",
                base / "plugins",
            ]
            plugins_dir = _first_existing_dir(plugin_candidates)
        else:
            # Normal (non-frozen) Python install
            plugins_dir = None
            try:
                plugins_dir = QLibraryInfo.location(QLibraryInfo.PluginsPath)
            except Exception:
                plugins_dir = None

            if not plugins_dir:
                try:
                    import PyQt5  # type: ignore

                    pyqt_root = Path(PyQt5.__file__).resolve().parent
                    plugins_dir = _first_existing_dir(
                        [
                            pyqt_root / "Qt5" / "plugins",
                            pyqt_root / "Qt" / "plugins",
                        ]
                    )
                except Exception:
                    plugins_dir = None

        platforms_dir = _platforms_dir(plugins_dir)

        if plugins_dir:
            try:
                QCoreApplication.addLibraryPath(str(plugins_dir))
            except Exception:
                pass

        if platforms_dir:
            _set_if_missing("QT_QPA_PLATFORM_PLUGIN_PATH", str(platforms_dir))

        # Allow end-users to override QPA platform when they know they need it
        # (e.g. headless Linux: offscreen).
        override_platform = os.environ.get("QODER_QT_QPA_PLATFORM")
        if override_platform:
            os.environ["QT_QPA_PLATFORM"] = override_platform

        # Keep existing env unless user explicitly requests reset via QODER_QT_RESET_ENV=1
        if os.environ.get("QODER_QT_RESET_ENV") == "1":
            for key in env_keys:
                os.environ.pop(key, None)
            if platforms_dir:
                os.environ["QT_QPA_PLATFORM_PLUGIN_PATH"] = str(platforms_dir)

        return {
            "plugins_dir": plugins_dir,
            "platforms_dir": platforms_dir,
            "frozen": bool(getattr(sys, "frozen", False)),
        }
    except Exception:
        return {"plugins_dir": None, "platforms_dir": None, "frozen": False}


class QoderResetGUI(QMainWindow):
    def __init__(self):
        """Initialize the main application window"""
        super().__init__()
        self.current_language = "en"  # Default to English
        self.init_translations()
        if HAS_PYQT5:
            self.init_ui()
        else:
            class DummyLog:
                def append(self, text):
                    pass
                def clear(self):
                    pass

            class DummyCheckBox:
                def isChecked(self):
                    return True
                def setText(self, text):
                    pass

            self.log_text = DummyLog()
            self.preserve_chat_checkbox = DummyCheckBox()

    def init_translations(self):
        """Initialize multilingual dictionary"""
        self.translations = {
            "zh": {  # Tiếng Trung
                "window_title": "Qoder-Free",
                "intro_text": "Qoder-Free 主要用于重置 Qoder 应用程序的用户身份信息",
                "operation_area": "操作区域:",
                "one_click_config": "一键修改配置",
                "close_qoder": "关闭 Qoder",
                "reset_machine_id": "重置机器 ID",
                "reset_telemetry": "重置遥测数据",
                "deep_identity_clean": "深度身份清理",
                "login_identity_clean": "清理登录身份",
                "hardware_fingerprint_reset": "硬件指纹重置",
                "backup_identity": "备份身份数据",
                "restore_identity": "恢复身份数据",
                "check_update": "检查更新",
                "advanced_options": "高级选项",
                "preserve_chat": "保留对话记录",
                "operation_log": "操作日志:",
                "clear_log": "清空日志",
                "github": "Github",
                "language": "语言",
                "diagnostic_report": "复制诊断报告",
                "issue_note": "注意: 本工具仅重置本地 Qoder 数据，服务端额度由 Qoder 控制。",
                # 日志消息
                "tool_started": "Qoder-Free 重置工具已启动",
                "log_cleared": "日志已清空",
                "qoder_running": "Qoder 正在运行",
                "qoder_not_running": "Qoder 未运行",
                "qoder_directory_exists": "Qoder 目录存在",
                "machine_id": "机器 ID",
                "telemetry_machine_id": "遥测机器 ID",
                "device_id": "设备 ID",
                "cache_directories_found": "个缓存目录",
                "chat_directories_found": "个对话相关目录",
                "identity_files_found": "个身份识别文件",
                "status_check_complete": "状态检查完成，可以开始操作",
                "backup_success": "身份数据已成功备份至:",
                "restore_success": "身份数据恢复成功！",
                # 对话框消息
                "qoder_detected_running": "检测到 Qoder 正在运行",
                "please_close_qoder": "请手动关闭 Qoder 应用程序",
                "confirm_one_click": "确认一键修改",
                "confirm_deep_clean": "确认深度清理",
                "confirm_login_clean": "确认清理登录身份",
                "confirm_backup": "确认备份当前的 Qoder 身份数据吗？",
                "confirm_restore": "确认从备份恢复 Qoder 身份数据吗？",
                "no_backups_found": "未找到任何可用备份",
                "update_available": "发现新版本",
                "latest_version_installed": "已是最新版本",
                "operation_complete": "操作完成",
                "operation_failed": "操作失败",
                "error": "错误",
                "success": "成功",
                "warning": "警告",
                "status_check": "状态检查",
            },
            "en": {  # Tiếng Anh
                "window_title": "Qoder-Free",
                "intro_text": "Qoder-Free is mainly used to reset user identity information of Qoder application",
                "operation_area": "Operation Area:",
                "one_click_config": "One-Click Configuration",
                "close_qoder": "Close Qoder",
                "reset_machine_id": "Reset Machine ID",
                "reset_telemetry": "Reset Telemetry",
                "deep_identity_clean": "Deep Identity Cleanup",
                "login_identity_clean": "Clean Login Identity",
                "hardware_fingerprint_reset": "Hardware Fingerprint Reset",
                "backup_identity": "Backup Identity",
                "restore_identity": "Restore Identity",
                "check_update": "Check Updates",
                "advanced_options": "Advanced Options",
                "preserve_chat": "Preserve Chat History",
                "operation_log": "Operation Log:",
                "clear_log": "Clear Log",
                "github": "Github",
                "language": "Language",
                "diagnostic_report": "Copy Diagnostic Report",
                "issue_note": "Note: this tool can reset local Qoder data, but server-side trial credits and model access are controlled by Qoder.",
                # Log messages
                "tool_started": "Qoder-Free reset tool started",
                "log_cleared": "Log cleared",
                "qoder_running": "Qoder is running",
                "qoder_not_running": "Qoder is not running",
                "qoder_directory_exists": "Qoder directory exists",
                "machine_id": "Machine ID",
                "telemetry_machine_id": "Telemetry Machine ID",
                "device_id": "Device ID",
                "cache_directories_found": "cache directories found",
                "chat_directories_found": "chat-related directories found",
                "identity_files_found": "identity files found",
                "status_check_complete": "Status check completed, ready to operate",
                "backup_success": "Identity data successfully backed up to:",
                "restore_success": "Identity data restored successfully!",
                # Dialog messages
                "qoder_detected_running": "Qoder Detected Running",
                "please_close_qoder": "Please close Qoder application manually",
                "confirm_one_click": "Confirm One-Click Reset",
                "confirm_deep_clean": "Confirm Deep Cleanup",
                "confirm_login_clean": "Confirm Login Identity Cleanup",
                "confirm_close_qoder": "Confirm Close Qoder",
                "confirm_reset_machine_id": "Confirm Machine ID Reset",
                "confirm_reset_telemetry": "Confirm Telemetry Reset",
                "confirm_hardware_fingerprint_reset": "Confirm Hardware Fingerprint Reset",
                "confirm_backup": "Confirm backup of current Qoder identity data?",
                "confirm_restore": "Confirm restore of Qoder identity data from backup?",
                "no_backups_found": "No backups found",
                "update_available": "New version available",
                "latest_version_installed": "You are using the latest version",
                "operation_complete": "Operation Complete",
                "operation_failed": "Operation Failed",
                "error": "Error",
                "success": "Success",
                "warning": "Warning",
                "status_check": "Status Check",
            },
            "ru": {  # Tiếng Nga
                "window_title": "Qoder-Free",
                "intro_text": "Qoder-Free в основном используется для сброса пользовательской информации приложения Qoder",
                "operation_area": "Область операций:",
                "one_click_config": "Одним кликом",
                "close_qoder": "Закрыть Qoder",
                "reset_machine_id": "Сбросить ID машины",
                "reset_telemetry": "Сбросить телеметрию",
                "deep_identity_clean": "Глубокая очистка",
                "login_identity_clean": "Очистить вход",
                "hardware_fingerprint_reset": "Сброс железа",
                "backup_identity": "Резервная копия",
                "restore_identity": "Восстановление",
                "check_update": "Проверить обновления",
                "advanced_options": "Дополнительно",
                "preserve_chat": "Сохранить чат",
                "operation_log": "Журнал операций:",
                "clear_log": "Очистить журнал",
                "github": "Github",
                "language": "Язык",
                "diagnostic_report": "Копировать отчет",
                "issue_note": "Примечание: инструмент сбрасывает локальные данные Qoder; баланс триала контролируется сервером.",
                # Сообщения журнала
                "tool_started": "Инструмент сброса Qoder-Free запущен",
                "log_cleared": "Журнал очищен",
                "qoder_running": "Qoder запущен",
                "qoder_not_running": "Qoder не запущен",
                "qoder_directory_exists": "Папка Qoder существует",
                "machine_id": "ID машины",
                "telemetry_machine_id": "ID машины телеметрии",
                "device_id": "ID устройства",
                "cache_directories_found": "папок кеша найдено",
                "chat_directories_found": "папок чата найдено",
                "identity_files_found": "файлов идентификации найдено",
                "status_check_complete": "Проверка статуса завершена, готов к работе",
                "backup_success": "Данные успешно сохранены в:",
                "restore_success": "Данные успешно восстановлены!",
                # Диалоговые сообщения
                "qoder_detected_running": "Обнаружен запущенный Qoder",
                "please_close_qoder": "Пожалуйста, закройте приложение Qoder вручную",
                "confirm_one_click": "Подтвердить сброс одним кликом",
                "confirm_deep_clean": "Подтвердить глубокую очистку",
                "confirm_login_clean": "Подтвердить очистку входа",
                "confirm_backup": "Подтвердить создание резервной копии?",
                "confirm_restore": "Подтвердить восстановление из копии?",
                "no_backups_found": "Резервные копии не найдены",
                "update_available": "Доступна новая версия",
                "latest_version_installed": "У вас установлена последняя версия",
                "operation_complete": "Операция завершена",
                "operation_failed": "Операция не удалась",
                "error": "Ошибка",
                "success": "Успех",
                "warning": "Предупреждение",
                "status_check": "Проверка статуса",
            },
            "pt-br": {  # Tiếng Bồ Đào Nha (Brazil)
                "window_title": "Qoder-Free",
                "intro_text": "Qoder-Free é principalmente usado para redefinir as informações de identidade do usuário do aplicativo Qoder",
                "operation_area": "Área de Operações:",
                "one_click_config": "Configuração com um clique",
                "close_qoder": "Fechar Qoder",
                "reset_machine_id": "Redefinir ID da Máquina",
                "reset_telemetry": "Redefinir Telemetria",
                "deep_identity_clean": "Limpeza Profunda de Identidade",
                "login_identity_clean": "Limpar Login",
                "hardware_fingerprint_reset": "Reset de Hardware",
                "backup_identity": "Backup de Identidade",
                "restore_identity": "Restaurar Identidade",
                "check_update": "Verificar Atualizações",
                "advanced_options": "Opções Avançadas",
                "preserve_chat": "Preservar Histórico do chat",
                "operation_log": "Log de Operações:",
                "clear_log": "Limpar Log",
                "github": "Github",
                "language": "Idioma",
                "diagnostic_report": "Copiar Relatório",
                "issue_note": "Nota: esta ferramenta redefine dados locais do Qoder; o crédito de avaliação é controlado pelo servidor.",
                # Mensagens de log
                "tool_started": "Ferramenta de redefinição Qoder-Free iniciada",
                "log_cleared": "Log limpo",
                "qoder_running": "Qoder está em execução",
                "qoder_not_running": "Qoder não está em execução",
                "qoder_directory_exists": "Diretório Qoder existe",
                "machine_id": "ID da Máquina",
                "telemetry_machine_id": "ID da Máquina de Telemetria",
                "device_id": "ID do Dispositivo",
                "cache_directories_found": "diretórios de cache encontrados",
                "chat_directories_found": "diretórios relacionados ao chat encontrados",
                "identity_files_found": "arquivos de identidade encontrados",
                "status_check_complete": "Verificação de status concluída, pronto para operar",
                "backup_success": "Dados de identidade salvos em:",
                "restore_success": "Dados de identidade restaurados com sucesso!",
                # Mensagens de diálogo
                "qoder_detected_running": "Qoder Detectado em Execução",
                "please_close_qoder": "Por favor, feche o aplicativo Qoder manualmente",
                "confirm_one_click": "Confirmar Redefinição com um clique",
                "confirm_deep_clean": "Confirmar Limpeza Profunda",
                "confirm_login_clean": "Confirmar Limpeza de Identidade de Login",
                "confirm_backup": "Confirmar backup dos dados de identidade?",
                "confirm_restore": "Confirmar restauração da identidade?",
                "no_backups_found": "Nenhum backup encontrado",
                "update_available": "Nova versão disponível",
                "latest_version_installed": "Você está usando a versão mais recente",
                "operation_complete": "Operação Concluída",
                "operation_failed": "Operação Falhou",
                "error": "Erro",
                "success": "Sucesso",
                "warning": "Aviso",
                "status_check": "Verificação de Status",
            },
            "vi": {  # Tiếng Việt
                "window_title": "Qoder-Free: Công Cụ Làm Sạch",
                "intro_text": "Công cụ giúp bạn đặt lại và làm sạch thông tin nhận dạng của ứng dụng Qoder một cách dễ dàng và an toàn.",
                "operation_area": "Khu Vực Thao Tác:",
                "one_click_config": "Cấu Hình Một Chạm",
                "close_qoder": "Đóng Qoder",
                "reset_machine_id": "Đặt Lại ID Máy",
                "reset_telemetry": "Đặt Lại Dữ Liệu Điện Toán",
                "deep_identity_clean": "Làm Sạch Danh Tính Sâu",
                "login_identity_clean": "Xóa Thông Tin Đăng Nhập",
                "hardware_fingerprint_reset": "Đặt Lại Dấu Vân Tay Phần Cứng",
                "backup_identity": "Sao Lưu Danh Tính",
                "restore_identity": "Khôi Phục Danh Tính",
                "check_update": "Kiểm Tra Cập Nhật",
                "advanced_options": "Tùy Chọn Nâng Cao",
                "preserve_chat": "Giữ Lại Lịch Sử Trò Chuyện",
                "operation_log": "Nhật Ký Thao Tác:",
                "clear_log": "Xóa Nhật Ký",
                "github": "Liên Kết GitHub",
                "language": "Ngôn Ngữ",
                "diagnostic_report": "Sao Chép Báo Cáo Chẩn Đoán",
                "issue_note": "Lưu ý: công cụ chỉ đặt lại dữ liệu Qoder cục bộ; trial credit và quyền dùng model có thể do máy chủ Qoder quyết định.",
                # Các thông báo nhật ký
                "tool_started": "Công cụ đặt lại Qoder-Free đã được khởi động",
                "log_cleared": "Nhật ký đã được xóa",
                "qoder_running": "Qoder đang chạy",
                "qoder_not_running": "Qoder không chạy",
                "qoder_directory_exists": "Thư mục Qoder tồn tại",
                "machine_id": "ID Máy",
                "telemetry_machine_id": "ID Máy Điện Toán",
                "device_id": "ID Thiết Bị",
                "cache_directories_found": "thư mục bộ nhớ đệm được tìm thấy",
                "chat_directories_found": "thư mục liên quan đến trò chuyện được tìm thấy",
                "identity_files_found": "tệp nhận dạng được tìm thấy",
                "status_check_complete": "Kiểm tra trạng thái hoàn tất, sẵn sàng thực hiện",
                "backup_success": "Đã sao lưu dữ liệu nhận dạng vào:",
                "restore_success": "Khôi phục dữ liệu nhận dạng thành công!",
                # Các thông báo hộp thoại
                "qoder_detected_running": "Phát Hiện Qoder Đang Chạy",
                "please_close_qoder": "Vui lòng đóng ứng dụng Qoder theo cách thủ công",
                "confirm_one_click": "Xác Nhận Đặt Lại Một Chạm",
                "confirm_deep_clean": "Xác Nhận Làm Sạch Sâu",
                "confirm_login_clean": "Xác Nhận Xóa Thông Tin Đăng Nhập",
                "confirm_close_qoder": "Xác Nhận Đóng Qoder",
                "confirm_reset_machine_id": "Xác Nhận Đặt Lại ID Máy",
                "confirm_reset_telemetry": "Xác Nhận Đặt Lại Telemetry",
                "confirm_hardware_fingerprint_reset": "Xác Nhận Đặt Lại Dấu Vân Tay Phần Cứng",
                "confirm_backup": "Xác nhận sao lưu dữ liệu nhận dạng Qoder hiện tại?",
                "confirm_restore": "Xác nhận khôi phục nhận dạng Qoder từ bản sao lưu?",
                "no_backups_found": "Không tìm thấy bản sao lưu nào",
                "update_available": "Đã có phiên bản mới",
                "latest_version_installed": "Bạn đang dùng phiên bản mới nhất",
                "operation_complete": "Thao Tác Hoàn Tất",
                "operation_failed": "Thao Tác Thất Bại",
                "error": "Lỗi",
                "success": "Thành Công",
                "warning": "Cảnh Báo",
                "status_check": "Kiểm Tra Trạng Thái",
            },
        }

    def tr(self, key):
        """Get translation text for the current language"""
        return (
            self.translations.get(self.current_language, {}).get(key)
            or self.translations.get("en", {}).get(key)
            or key
        )

    def init_ui(self):
        """Initialize the user interface"""
        # Set window properties
        self.setWindowTitle(self.tr("window_title"))
        self.setMinimumSize(860, 680)
        self.resize(940, 740)

        # Set application-wide font
        font = QFont("Segoe UI", 10)
        QApplication.setFont(font)

        # Create main widget and layout
        main_widget = QWidget()
        main_widget.setObjectName("appRoot")
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(24, 22, 24, 18)
        main_layout.setSpacing(14)

        # Title Label
        self.title_label = QLabel(self.tr("window_title"))
        self.title_label.setObjectName("titleLabel")
        main_layout.addWidget(self.title_label)

        # Intro Label
        self.intro_label = QLabel(self.tr("intro_text"))
        self.intro_label.setObjectName("introLabel")
        self.intro_label.setWordWrap(True)
        main_layout.addWidget(self.intro_label)

        self.issue_note_label = QLabel(self.tr("issue_note"))
        self.issue_note_label.setObjectName("issueNoteLabel")
        self.issue_note_label.setWordWrap(True)
        main_layout.addWidget(self.issue_note_label)

        # Language Selector
        language_layout = QHBoxLayout()
        language_layout.setSpacing(10)
        self.language_label = QLabel(self.tr("language"))
        self.language_selector = QComboBox()
        self.language_selector.addItems(["English", "Tiếng Việt", "中文", "Русский"])
        self.language_selector.setCurrentText("English")
        self.language_selector.currentTextChanged.connect(self.change_language)

        language_layout.addWidget(self.language_label)
        language_layout.addWidget(self.language_selector)
        language_layout.addStretch()
        main_layout.addLayout(language_layout)

        # Nút một chạm
        self.one_click_btn = self.create_styled_button(
            self.tr("one_click_config"), "#1f6feb", self.one_click_reset
        )
        self.one_click_btn.setMinimumHeight(52)
        main_layout.addWidget(self.one_click_btn)

        # Bố cục các nút chức năng
        self.operation_title = QLabel(self.tr("operation_area"))
        self.operation_title.setObjectName("sectionLabel")
        main_layout.addWidget(self.operation_title)

        button_layout = QGridLayout()
        button_layout.setSpacing(10)

        # Nút đóng Qoder
        self.close_qoder_btn = self.create_styled_button(
            self.tr("close_qoder"), "#c2410c", self.close_qoder
        )
        button_layout.addWidget(self.close_qoder_btn, 0, 0)

        # Nút đặt lại ID máy
        self.reset_machine_id_btn = self.create_styled_button(
            self.tr("reset_machine_id"), "#2563eb", self.reset_machine_id
        )
        button_layout.addWidget(self.reset_machine_id_btn, 0, 1)

        # Nút đặt lại dữ liệu điện toán
        self.reset_telemetry_btn = self.create_styled_button(
            self.tr("reset_telemetry"), "#15803d", self.reset_telemetry
        )
        button_layout.addWidget(self.reset_telemetry_btn, 0, 2)

        self.login_clean_btn = self.create_styled_button(
            self.tr("login_identity_clean"), "#475569", self.login_identity_cleanup
        )
        button_layout.addWidget(self.login_clean_btn, 1, 0)

        # Nút làm sạch danh tính sâu
        self.deep_clean_btn = self.create_styled_button(
            self.tr("deep_identity_clean"), "#a16207", self.deep_identity_cleanup
        )
        button_layout.addWidget(self.deep_clean_btn, 1, 1)

        self.hardware_reset_btn = self.create_styled_button(
            self.tr("hardware_fingerprint_reset"),
            "#7c3aed",
            self.hardware_fingerprint_reset,
        )
        button_layout.addWidget(self.hardware_reset_btn, 1, 2)

        # Hàng mới: Sao lưu, Khôi phục, Kiểm tra cập nhật
        self.backup_btn = self.create_styled_button(
            self.tr("backup_identity"), "#0891b2", self.backup_identity
        )
        button_layout.addWidget(self.backup_btn, 2, 0)

        self.restore_btn = self.create_styled_button(
            self.tr("restore_identity"), "#4f46e5", self.restore_identity
        )
        button_layout.addWidget(self.restore_btn, 2, 1)

        self.check_update_btn = self.create_styled_button(
            self.tr("check_update"), "#0284c7", self.check_update_action
        )
        button_layout.addWidget(self.check_update_btn, 2, 2)

        self.diagnostic_btn = self.create_styled_button(
            self.tr("diagnostic_report"), "#334155", self.copy_diagnostic_report
        )
        button_layout.addWidget(self.diagnostic_btn, 3, 0)

        self.github_btn = self.create_styled_button(
            self.tr("github"), "#0f766e", self.open_github
        )
        button_layout.addWidget(self.github_btn, 3, 1)

        self.clear_log_btn = self.create_styled_button(
            self.tr("clear_log"), "#64748b", self.clear_log
        )
        button_layout.addWidget(self.clear_log_btn, 3, 2)

        # Thêm bố cục nút vào bố cục chính
        main_layout.addLayout(button_layout)

        # Preserve Chat Checkbox
        self.preserve_chat_checkbox = QCheckBox(self.tr("preserve_chat"))
        self.preserve_chat_checkbox.setChecked(True)
        main_layout.addWidget(self.preserve_chat_checkbox)

        # Log Area
        log_layout = QVBoxLayout()
        self.log_title = QLabel(self.tr("operation_log"))
        self.log_title.setObjectName("sectionLabel")
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMinimumHeight(190)

        log_layout.addWidget(self.log_title)
        log_layout.addWidget(self.log_text)

        main_layout.addLayout(log_layout)

        # Set main layout
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # Set overall window style
        self.setStyleSheet("""
            QMainWindow, QWidget#appRoot {
                background-color: #f7f8fa;
            }
            QWidget {
                color: #111827;
            }
            QLabel#titleLabel {
                color: #0f172a;
                font-size: 26px;
                font-weight: 700;
            }
            QLabel#introLabel {
                color: #475569;
                font-size: 13px;
                line-height: 1.35;
            }
            QLabel#issueNoteLabel {
                background-color: #fff7ed;
                border: 1px solid #fed7aa;
                border-radius: 6px;
                color: #7c2d12;
                padding: 8px 10px;
            }
            QLabel#sectionLabel {
                color: #334155;
                font-size: 13px;
                font-weight: 700;
                margin-top: 4px;
            }
            QComboBox {
                background-color: white;
                border: 1px solid #cbd5e1;
                border-radius: 5px;
                padding: 6px 10px;
                min-width: 150px;
            }
            QCheckBox {
                color: #334155;
                spacing: 8px;
            }
            QCheckBox::indicator {
                width: 18px;
                height: 18px;
            }
            QTextEdit {
                background-color: #0f172a;
                border: 1px solid #1e293b;
                border-radius: 6px;
                color: #dbeafe;
                font-family: Consolas, "Courier New", monospace;
                font-size: 12px;
                padding: 10px;
            }
        """)

        # Status bar with version info
        self.statusBar().showMessage(f"Qoder-Free v{__version__}")
        self.statusBar().setStyleSheet("""
            QStatusBar {
                background-color: #ecf0f1;
                color: #7f8c8d;
                font-size: 12px;
            }
        """)

        # Initialize status check
        self.initialize_status_check()

    def create_styled_button(self, text, color, connect_func):
        """Tạo nút với phong cách thống nhất"""
        btn = QPushButton(text)
        btn.setMinimumHeight(42)
        btn.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        btn.setCursor(Qt.PointingHandCursor)
        btn.setStyleSheet(f"""
            QPushButton {{
                background-color: {color};
                color: white;
                font-size: 12px;
                font-weight: 700;
                border: none;
                border-radius: 6px;
                padding: 9px 12px;
            }}
            QPushButton:hover {{
                background-color: {color}EE;
            }}
            QPushButton:pressed {{
                background-color: {color}CC;
            }}
            QPushButton:disabled {{
                background-color: #94a3b8;
                color: #e2e8f0;
            }}
        """)
        btn.clicked.connect(connect_func)
        return btn

    def change_language(self, language_text):
        """Change the application language"""
        try:
            # Normalize language text
            language_text = language_text.strip()

            # Map language display text to language codes
            language_map = {
                "English": "en",
                "Tiếng Việt": "vi",
                "中文": "zh",
                "Русский": "ru",
            }

            # Get language code, default to English
            language = language_map.get(language_text, "en")

            # Update current language
            self.current_language = language

            # Update UI elements with translations
            self.setWindowTitle(self.tr("window_title"))

            # Update labels
            self.title_label.setText(self.tr("window_title"))
            self.intro_label.setText(self.tr("intro_text"))
            self.issue_note_label.setText(self.tr("issue_note"))
            self.language_label.setText(self.tr("language"))
            self.operation_title.setText(self.tr("operation_area"))
            self.log_title.setText(self.tr("operation_log"))

            # Update buttons with translations
            button_translations = {
                "one_click_btn": "one_click_config",
                "close_qoder_btn": "close_qoder",
                "reset_machine_id_btn": "reset_machine_id",
                "reset_telemetry_btn": "reset_telemetry",
                "login_clean_btn": "login_identity_clean",
                "deep_clean_btn": "deep_identity_clean",
                "hardware_reset_btn": "hardware_fingerprint_reset",
                "backup_btn": "backup_identity",
                "restore_btn": "restore_identity",
                "check_update_btn": "check_update",
                "diagnostic_btn": "diagnostic_report",
                "clear_log_btn": "clear_log",
                "github_btn": "github",
            }

            # Update buttons with translated texts
            for btn_name, translation_key in button_translations.items():
                if hasattr(self, btn_name):
                    getattr(self, btn_name).setText(self.tr(translation_key))

            # Update checkbox
            self.preserve_chat_checkbox.setText(self.tr("preserve_chat"))

            # Optional: log the language change
            self.log(f"Language changed to: {language_text}")

        except Exception as e:
            # Log any errors during language change
            self.log(f"Error changing language: {e}")
            # Fallback to English
            self.current_language = "en"

        # Ensure language selector reflects the current selection
        language_index = self.language_selector.findText(language_text)
        if language_index >= 0:
            self.language_selector.setCurrentIndex(language_index)

    def update_ui_text(self):
        """更新界面文本"""
        # 更新窗口标题
        self.setWindowTitle(self.tr("window_title"))

        # 更新标签文本
        self.title_label.setText(self.tr("window_title"))
        self.intro_label.setText(self.tr("intro_text"))
        self.issue_note_label.setText(self.tr("issue_note"))
        self.language_label.setText(self.tr("language"))
        self.operation_title.setText(self.tr("operation_area"))
        self.log_title.setText(self.tr("operation_log"))

        # 更新按钮文本
        self.one_click_btn.setText(self.tr("one_click_config"))
        self.close_qoder_btn.setText(self.tr("close_qoder"))
        self.reset_machine_id_btn.setText(self.tr("reset_machine_id"))
        self.reset_telemetry_btn.setText(self.tr("reset_telemetry"))
        self.deep_clean_btn.setText(self.tr("deep_identity_clean"))
        self.login_clean_btn.setText(self.tr("login_identity_clean"))
        self.hardware_reset_btn.setText(self.tr("hardware_fingerprint_reset"))
        self.backup_btn.setText(self.tr("backup_identity"))
        self.restore_btn.setText(self.tr("restore_identity"))
        self.check_update_btn.setText(self.tr("check_update"))
        self.diagnostic_btn.setText(self.tr("diagnostic_report"))
        self.clear_log_btn.setText(self.tr("clear_log"))
        self.github_btn.setText(self.tr("github"))

        # 更新复选框文本
        self.preserve_chat_checkbox.setText(self.tr("preserve_chat"))

        # 清空日志并重新初始化
        self.log_text.clear()
        self.log(self.tr("tool_started"))
        self.log("=" * 50)

    def log(self, message):
        """Log messages with timestamp in English"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        log_message = f"[{timestamp}] {message}"
        self.log_text.append(log_message)

    def initialize_status_check(self):
        """Check initial Qoder status across Modern and Legacy components"""
        try:
            self.log("Qoder-Free reset tool started")
            self.log("=" * 50)

            # 1. Process status
            self.log("1. Checking Qoder process status...")
            is_running = self.is_qoder_running()
            if is_running:
                self.log("   ❌ Qoder (or helper/launcher) is running")
            else:
                self.log("   ✅ Qoder is not running")

            # 2. Directory check
            self.log("2. Checking Qoder directories...")
            qoder_support_dir = self.get_qoder_data_dir()
            dot_qoder = resolve_qoder_home_dir()
            if qoder_support_dir.exists():
                self.log(f"   ✅ Primary AppData dir exists: {qoder_support_dir.name}")
                _repair_sqlite_fts(qoder_support_dir / "main.sqlite")
            else:
                self.log(f"   ⚠️  Primary AppData dir not found ({qoder_support_dir})")

            if dot_qoder.exists():
                self.log("   ✅ ~/.qoder home directory exists")
            else:
                self.log("   ℹ️  ~/.qoder home directory not found")

            # 3. Machine ID check (Modern auth.machine-id + Legacy machineid)
            self.log("3. Checking Machine ID files...")
            auth_mid = qoder_support_dir / "auth.machine-id"
            if auth_mid.exists():
                try:
                    amid = auth_mid.read_text(encoding="utf-8").strip()
                    self.log(f"   ✅ Modern Machine ID (auth.machine-id): {amid}")
                except Exception:
                    pass

            machine_id_file = qoder_support_dir / "machineid"
            if machine_id_file.exists():
                try:
                    with open(machine_id_file, "r", encoding="utf-8") as f:
                        machine_id = f.read().strip()
                    self.log(f"   ✅ Legacy Machine ID: {machine_id}")
                except Exception:
                    pass

            # 4. Login and user status check
            status_file = dot_qoder / ".qoder-app-status.json"
            if status_file.exists():
                try:
                    sdata = json.loads(status_file.read_text(encoding="utf-8"))
                    email = sdata.get("email", "")
                    masked = (email[:2] + "***@" + email.split("@")[-1]) if "@" in email else (email[:3] + "***" if email else "N/A")
                    self.log(f"   👤 Qoder Account: logged_in={sdata.get('logged_in', False)}, user={masked}")
                except Exception:
                    pass

            # 5. Telemetry data files
            self.log("4. Checking Telemetry data files...")
            storage_json_file = qoder_support_dir / "User/globalStorage/storage.json"
            if storage_json_file.exists():
                try:
                    with open(storage_json_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                    telemetry_machine_id = data.get("telemetry.machineId", "N/A")
                    device_id = data.get("telemetry.devDeviceId", "N/A")
                    self.log(f"   ✅ Telemetry Machine ID: {telemetry_machine_id[:16]}...")
                    self.log(f"   ✅ Device ID: {device_id}")
                except Exception:
                    pass
            else:
                self.log("   ℹ️  Legacy storage.json not present")

            self.log("=" * 50)
            self.log("Status check completed, ready to operate")

        except Exception as e:
            self.log(f"Error during status check: {e}")

    def clear_log(self):
        """Clear log contents"""
        self.log_text.clear()
        self.log(self.tr("log_cleared"))

    def collect_diagnostic_report(self):
        """Collect non-secret state useful for GitHub issue reports."""
        qoder_support_dir = self.get_qoder_data_dir()
        dot_qoder = resolve_qoder_home_dir()
        lines = [
            f"Qoder-Free version: {__version__}",
            f"OS: {platform.system()} {platform.release()} ({platform.machine()})",
            f"Python: {platform.python_version()}",
            f"Qoder running: {self.is_qoder_running()}",
            f"Qoder data dir: {qoder_support_dir}",
            f"Qoder data dir exists: {qoder_support_dir.exists()}",
        ]

        auth_mid_file = qoder_support_dir / "auth.machine-id"
        if auth_mid_file.exists():
            try:
                amid = auth_mid_file.read_text(encoding="utf-8").strip()
                lines.append(f"modern auth.machine-id prefix: {amid[:8]}...")
            except Exception:
                pass

        lines.append(f"~/.qoder exists: {dot_qoder.exists()}")
        status_file = dot_qoder / ".qoder-app-status.json"
        if status_file.exists():
            try:
                sdata = json.loads(status_file.read_text(encoding="utf-8"))
                lines.append(f"qoder logged in: {sdata.get('logged_in', False)}")
            except Exception:
                pass

        machine_id_file = qoder_support_dir / "machineid"
        lines.append(f"machineid file exists: {machine_id_file.exists()}")
        if machine_id_file.exists():
            try:
                machine_id = machine_id_file.read_text(encoding="utf-8").strip()
                lines.append(f"machineid prefix: {machine_id[:8]}...")
            except Exception as exc:
                lines.append(f"machineid read error: {exc}")

        storage_json_file = (
            qoder_support_dir / "User" / "globalStorage" / "storage.json"
        )
        lines.append(f"storage.json exists: {storage_json_file.exists()}")
        if storage_json_file.exists():
            try:
                data = json.loads(storage_json_file.read_text(encoding="utf-8"))
                telemetry_keys = sorted(
                    key for key in data.keys() if "telemetry" in str(key).lower()
                )
                login_like_keys = sorted(
                    key
                    for key in data.keys()
                    if any(
                        token in str(key).lower()
                        for token in ("auth", "token", "login", "session")
                    )
                )
                lines.append(f"telemetry key count: {len(telemetry_keys)}")
                lines.append(f"telemetry keys: {', '.join(telemetry_keys) or 'none'}")
                lines.append(f"login/session-like key count: {len(login_like_keys)}")
            except Exception as exc:
                lines.append(f"storage.json parse error: {exc}")

        lines.append("")
        lines.append(
            "Limit note: local reset can change local identifiers, but trial credits and model access may be decided server-side by Qoder."
        )
        return "\n".join(lines)

    def copy_diagnostic_report(self):
        """Copy diagnostic report and log it for issue follow-up."""
        try:
            report = self.collect_diagnostic_report()
            QApplication.clipboard().setText(report)
            self.log("Diagnostic report copied to clipboard.")
            self.log("Use it when replying to GitHub issues #13/#14.")
            QMessageBox.information(
                self,
                self.tr("success"),
                "Diagnostic report copied to clipboard.",
            )
        except Exception as e:
            self.log(f"Error collecting diagnostic report: {e}")
            QMessageBox.critical(
                self,
                self.tr("error"),
                f"Failed to collect diagnostic report: {e}",
            )

    def get_qoder_data_dir(self):
        """Get Qoder data directory path (cross-platform support)"""
        return resolve_qoder_data_dir()

    def is_qoder_running(self):
        """Check if Qoder is currently running"""
        return check_is_qoder_running()

    def backup_identity(self):
        """Backup current Qoder identity files."""
        try:
            qoder_dir = self.get_qoder_data_dir()
            if not qoder_dir.exists():
                QMessageBox.warning(
                    self, self.tr("warning"), f"Qoder directory not found: {qoder_dir}"
                )
                return

            reply = QMessageBox.question(
                self,
                self.tr("backup_identity"),
                self.tr("confirm_backup"),
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply != QMessageBox.Yes:
                return

            backup_path = backup_qoder_identity(qoder_dir)
            self.log(f"✅ {self.tr('backup_success')} {backup_path.name}")
            QMessageBox.information(
                self,
                self.tr("success"),
                f"{self.tr('backup_success')}\n{backup_path}",
            )
        except Exception as e:
            self.log(f"❌ Backup failed: {e}")
            QMessageBox.critical(self, self.tr("error"), f"Backup failed: {e}")

    def restore_identity(self):
        """Restore Qoder identity from backup."""
        try:
            qoder_dir = self.get_qoder_data_dir()
            backups = list_qoder_backups(qoder_dir)
            if not backups:
                QMessageBox.warning(
                    self, self.tr("warning"), self.tr("no_backups_found")
                )
                return

            latest_backup = backups[0]
            reply = QMessageBox.question(
                self,
                self.tr("restore_identity"),
                f"{self.tr('confirm_restore')}\n({latest_backup.name})",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.Yes,
            )
            if reply != QMessageBox.Yes:
                return

            success, message = restore_qoder_identity(latest_backup, qoder_dir)
            if success:
                self.log(f"✅ {message}")
                QMessageBox.information(
                    self, self.tr("success"), f"{self.tr('restore_success')}\n{message}"
                )
            else:
                self.log(f"❌ Restore failed: {message}")
                QMessageBox.warning(self, self.tr("error"), message)
        except Exception as e:
            self.log(f"❌ Restore failed: {e}")
            QMessageBox.critical(self, self.tr("error"), f"Restore failed: {e}")

    def check_update_action(self):
        """Check for updates on GitHub."""
        try:
            self.log("🔍 Checking for updates...")
            info = check_for_updates()
            if not info.get("success"):
                self.log(f"⚠️ Could not check updates: {info.get('error')}")
                QMessageBox.information(
                    self,
                    self.tr("check_update"),
                    f"Unable to check updates: {info.get('error')}\n\nYou can check manually at:\n{info.get('url')}",
                )
                return

            if info.get("has_update"):
                self.log(f"🎉 New version available: v{info['latest_version']}")
                reply = QMessageBox.question(
                    self,
                    self.tr("update_available"),
                    f"New version v{info['latest_version']} is available! (Current: v{info['current_version']})\n\nOpen download page?",
                    QMessageBox.Yes | QMessageBox.No,
                    QMessageBox.Yes,
                )
                if reply == QMessageBox.Yes:
                    webbrowser.open(str(info.get("url")))
            else:
                self.log(f"✅ Qoder-Free is up-to-date (v{__version__})")
                QMessageBox.information(
                    self,
                    self.tr("check_update"),
                    f"{self.tr('latest_version_installed')} (v{__version__})",
                )
        except Exception as e:
            self.log(f"❌ Update check failed: {e}")
            QMessageBox.critical(self, self.tr("error"), f"Update check failed: {e}")

    def generate_system_version(self, system_type):
        """根据系统类型生成合适的系统版本号"""
        if system_type == "Darwin":  # macOS
            # macOS 版本号格式: 14.x.x (Sonoma), 13.x.x (Ventura), 12.x.x (Monterey)
            major_versions = [12, 13, 14, 15]  # 支持新版本
            major = random.choice(major_versions)
            minor = random.randint(0, 6)
            patch = random.randint(0, 9)
            return f"{major}.{minor}.{patch}"
        elif system_type == "Windows":
            # Windows 10/11 版本号
            versions = [
                "10.0.19045",  # Windows 10 22H2
                "10.0.22621",  # Windows 11 22H2
                "10.0.22631",  # Windows 11 23H2
                "10.0.26100",  # Windows 11 24H2
            ]
            base_version = random.choice(versions)
            # 添加随机的小版本号
            build_suffix = random.randint(1, 999)
            return f"{base_version}.{build_suffix}"
        else:  # Linux 或其他系统
            # Linux 内核版本号格式: 5.x.x, 6.x.x
            major_versions = [5, 6]
            major = random.choice(major_versions)
            if major == 5:
                minor = random.randint(10, 19)  # 5.10-5.19
            else:  # major == 6
                minor = random.randint(0, 8)  # 6.0-6.8
            patch = random.randint(0, 50)
            return f"{major}.{minor}.{patch}"

    def close_qoder(self):
        """Close Qoder application"""
        try:
            # Check if Qoder is running
            if not self.is_qoder_running():
                self.log("Qoder is not running.")
                return

            # Confirm closing
            reply = QMessageBox.question(
                self,
                self.tr("confirm_close_qoder"),
                "Are you sure you want to close Qoder?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                # Execute Qoder closing operation
                self.log("Closing Qoder...")
                ok, details = kill_qoder_process()
                if ok:
                    self.log("✅ Qoder process terminated.")
                else:
                    self.log("⚠️  Failed to terminate Qoder process.")
                if details:
                    self.log(details)

                QMessageBox.information(
                    self,
                    self.tr("success") if ok else self.tr("warning"),
                    (
                        "Qoder has been closed successfully."
                        if ok
                        else "Failed to close Qoder."
                    ),
                )
        except Exception as e:
            # Log error
            self.log(f"Error closing Qoder: {str(e)}")
            QMessageBox.critical(
                self, self.tr("error"), f"Failed to close Qoder: {str(e)}"
            )

    def login_identity_cleanup(self):
        """Clean login-related identity information"""
        try:
            qoder_support_dir = self.get_qoder_data_dir()
            self.perform_login_identity_cleanup(qoder_support_dir)

            # Prompt successful cleanup
            QMessageBox.information(
                self, self.tr("success"), "Login identity cleaned successfully."
            )
        except Exception as e:
            # Log error
            self.log(f"Error during login identity cleanup: {e}")
            QMessageBox.critical(
                self, self.tr("error"), f"Failed to clean login identity: {e}"
            )

    def perform_login_identity_cleanup(self, qoder_support_dir):
        """Clean login/session identity files inside the Qoder data directory and ~/.qoder."""
        cleaned_count = 0

        # Modern Qoder auth files in AppData (com.qoder.app.stable)
        modern_auth_files = [
            "auth.v1.dat",
            "auth-profile-overlays.v1.dat",
            "first-launch-onboarding.v1.json",
        ]
        for fname in modern_auth_files:
            p = qoder_support_dir / fname
            if p.exists():
                try:
                    p.unlink()
                    self.log(f"   已清除现代登录凭据: {fname}")
                    cleaned_count += 1
                except Exception as e:
                    self.log(f"   清除现代凭据失败 {fname}: {e}")

        # Modern Qoder auth in ~/.qoder
        dot_qoder = resolve_qoder_home_dir()
        dot_auth = dot_qoder / ".auth"
        if dot_auth.exists():
            try:
                shutil.rmtree(dot_auth)
                self.log("   已清除 ~/.qoder/.auth 凭据目录")
                cleaned_count += 1
            except Exception as e:
                self.log(f"   清除 ~/.qoder/.auth 失败: {e}")

        dot_status = dot_qoder / ".qoder-app-status.json"
        if dot_status.exists():
            try:
                data = json.loads(dot_status.read_text(encoding="utf-8"))
                data["logged_in"] = False
                data["name"] = ""
                data["email"] = ""
                data["avatar_url"] = ""
                dot_status.write_text(json.dumps(data, indent=2), encoding="utf-8")
                self.log("   已重置 ~/.qoder/.qoder-app-status.json 登录状态")
                cleaned_count += 1
            except Exception as e:
                self.log(f"   重置 app-status 失败: {e}")

        # Clear modern ~/.qoder user caches and models
        for dot_sub in [dot_qoder / ".cache", dot_qoder / ".models", dot_qoder / "sites" / "sessions"]:
            if dot_sub.exists():
                try:
                    if dot_sub.is_dir():
                        shutil.rmtree(dot_sub)
                    else:
                        dot_sub.unlink()
                    self.log(f"   已清除 ~/.qoder/{dot_sub.name} 用户缓存")
                    cleaned_count += 1
                except Exception as e:
                    self.log(f"   清除 ~/.qoder/{dot_sub.name} 失败: {e}")

        # Modern Qoder SQLite credentials in main.sqlite
        main_sqlite = qoder_support_dir / "main.sqlite"
        if main_sqlite.is_file():
            purged = _purge_sqlite_auth_data(main_sqlite)
            _repair_sqlite_fts(main_sqlite)
            if purged > 0:
                self.log(f"   已清空 main.sqlite 中 {purged} 个身份凭据数据表")
                cleaned_count += purged

        # Modern Chromium network & partition stores
        modern_session_dirs = [
            "Network",
            "Partitions",
            "Local Storage",
            "Session Storage",
            "blob_storage",
            "rum-electron-store",
            "crash-feedback-v1",
        ]
        for sdir in modern_session_dirs:
            dir_path = qoder_support_dir / sdir
            if dir_path.exists():
                try:
                    shutil.rmtree(dir_path)
                    self.log(f"   已清除现代网络会话目录: {sdir}")
                    cleaned_count += 1
                except Exception as e:
                    self.log(f"   清除网络会话目录失败 {sdir}: {e}")

        login_files = [
            "Network Persistent State",
            "Cookies",
            "Cookies-journal",
            "Login Data",
            "Login Data-journal",
            "Web Data",
            "Web Data-journal",
            "Trust Tokens",
            "Trust Tokens-journal",
            "TransportSecurity",
            "DIPS",
            "SharedStorage",
            "SharedStorage-wal",
        ]

        for login_file in login_files:
            file_path = qoder_support_dir / login_file
            if file_path.exists():
                try:
                    file_path.unlink()
                    self.log(f"   已清除登录文件: {login_file}")
                    cleaned_count += 1
                except Exception as e:
                    self.log(f"   清除登录文件失败 {login_file}: {e}")

        storage_json_file = (
            qoder_support_dir / "User" / "globalStorage" / "storage.json"
        )
        if storage_json_file.exists():
            try:
                data = json.loads(storage_json_file.read_text(encoding="utf-8"))
                login_keywords = (
                    "accessToken",
                    "refreshToken",
                    "auth",
                    "credential",
                    "login",
                    "oauth",
                    "session",
                    "token",
                    "user.account",
                )
                removed_keys = [
                    key
                    for key in list(data.keys())
                    if any(
                        keyword.lower() in str(key).lower()
                        for keyword in login_keywords
                    )
                ]
                for key in removed_keys:
                    data.pop(key, None)
                    self.log(f"   已清除登录配置: {key}")

                if removed_keys:
                    storage_json_file.write_text(
                        json.dumps(data, indent=4, ensure_ascii=False),
                        encoding="utf-8",
                    )
                    cleaned_count += len(removed_keys)
            except Exception as e:
                self.log(f"   清理登录配置失败: {e}")

        self.log(f"   登录身份清理完成，处理了 {cleaned_count} 个项目")

    def reset_telemetry(self):
        """Reset telemetry data"""
        try:
            # Check if Qoder is running
            if self.is_qoder_running():
                QMessageBox.warning(
                    self,
                    self.tr("warning"),
                    self.tr("qoder_detected_running")
                    + "\n"
                    + self.tr("please_close_qoder"),
                )
                return

            # Confirm reset
            reply = QMessageBox.question(
                self,
                self.tr("confirm_reset_telemetry"),
                "Are you sure you want to reset Telemetry data?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                # Execute telemetry reset operation
                self.log("Resetting Telemetry data...")
                qoder_support_dir = self.get_qoder_data_dir()
                updated = reset_qoder_telemetry(qoder_support_dir)
                self.log(
                    f"   New Telemetry Machine ID: {updated['telemetry.machineId'][:16]}..."
                )
                self.log(f"   New Device ID: {updated['telemetry.devDeviceId']}")
                self.log(f"   New SQM ID: {updated['telemetry.sqmId']}")

                QMessageBox.information(
                    self,
                    self.tr("success"),
                    "Telemetry data has been reset successfully.",
                )
        except Exception as e:
            # Log error
            self.log(f"Error resetting Telemetry data: {str(e)}")
            QMessageBox.critical(
                self, self.tr("error"), f"Failed to reset Telemetry data: {str(e)}"
            )

    def reset_machine_id(self):
        """Reset machine ID"""
        try:
            # Check if Qoder is running
            if self.is_qoder_running():
                QMessageBox.warning(
                    self,
                    self.tr("warning"),
                    self.tr("qoder_detected_running")
                    + "\n"
                    + self.tr("please_close_qoder"),
                )
                return

            # Confirm reset
            reply = QMessageBox.question(
                self,
                self.tr("confirm_reset_machine_id"),
                "Are you sure you want to reset the Machine ID?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                # Execute machine ID reset operation
                self.log("Resetting Machine ID...")
                qoder_support_dir = self.get_qoder_data_dir()
                new_machine_id = reset_qoder_machine_id(qoder_support_dir)
                self.log(f"   New Machine ID: {new_machine_id}")

                QMessageBox.information(
                    self, self.tr("success"), "Machine ID has been reset successfully."
                )
        except Exception as e:
            # Log error
            self.log(f"Error resetting Machine ID: {str(e)}")
            QMessageBox.critical(
                self, self.tr("error"), f"Failed to reset Machine ID: {str(e)}"
            )

    def deep_identity_cleanup(self):
        """Perform deep identity cleanup"""
        try:
            # Check if Qoder is running
            if self.is_qoder_running():
                QMessageBox.warning(
                    self,
                    self.tr("warning"),
                    self.tr("qoder_detected_running")
                    + "\n"
                    + self.tr("please_close_qoder"),
                )
                return

            # Confirm cleanup
            reply = QMessageBox.question(
                self,
                self.tr("confirm_deep_clean"),
                "This will perform a deep identity cleanup. Are you sure?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                # Execute deep identity cleanup
                self.log("Performing deep identity cleanup...")
                qoder_support_dir = self.get_qoder_data_dir()
                if not qoder_support_dir.exists():
                    raise FileNotFoundError(
                        f"Qoder data directory not found: {qoder_support_dir}"
                    )

                preserve_chat = self.preserve_chat_checkbox.isChecked()
                self.perform_advanced_identity_cleanup(qoder_support_dir, preserve_chat)
                self.perform_login_identity_cleanup(qoder_support_dir)
                self.perform_super_deep_cleanup(qoder_support_dir)

                # Prompt cleanup success
                QMessageBox.information(
                    self,
                    self.tr("success"),
                    "Deep identity cleanup completed successfully.",
                )
        except Exception as e:
            # Log error
            self.log(f"Error during deep identity cleanup: {str(e)}")
            QMessageBox.critical(
                self,
                self.tr("error"),
                f"Failed to perform deep identity cleanup: {str(e)}",
            )

    def hardware_fingerprint_reset(self):
        """Reset hardware fingerprint"""
        try:
            # Check if Qoder is running
            if self.is_qoder_running():
                QMessageBox.warning(
                    self,
                    self.tr("warning"),
                    self.tr("qoder_detected_running")
                    + "\n"
                    + self.tr("please_close_qoder"),
                )
                return

            # Confirm reset
            reply = QMessageBox.question(
                self,
                self.tr("confirm_hardware_fingerprint_reset"),
                "This will reset all hardware-related identifiers. Are you sure?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                # Execute hardware fingerprint reset
                self.log("Resetting hardware fingerprint...")
                qoder_support_dir = self.get_qoder_data_dir()
                self.perform_hardware_fingerprint_reset(qoder_support_dir)

                # Prompt reset success
                QMessageBox.information(
                    self,
                    self.tr("success"),
                    "Hardware fingerprint reset completed successfully.",
                )
        except Exception as e:
            # Log error
            self.log(f"Error resetting hardware fingerprint: {str(e)}")
            QMessageBox.critical(
                self,
                self.tr("error"),
                f"Failed to reset hardware fingerprint: {str(e)}",
            )

    def one_click_reset(self):
        """一键修改所有配置"""
        try:
            # If Qoder is running, offer to close it automatically so we can patch its data.
            if self.is_qoder_running():
                reply = QMessageBox.question(
                    self,
                    self.tr("confirm_close_qoder"),
                    self.tr("qoder_detected_running")
                    + "\n"
                    + self.tr("please_close_qoder")
                    + "\n\nClose Qoder now and continue?",
                    QMessageBox.Yes | QMessageBox.No,
                )
                if reply != QMessageBox.Yes:
                    return

                ok, details = kill_qoder_process()
                if details:
                    self.log(details)
                if not ok and self.is_qoder_running():
                    QMessageBox.warning(
                        self,
                        self.tr("warning"),
                        "Failed to close Qoder. Please close it manually and retry.",
                    )
                    return

            # 确认操作
            reply = QMessageBox.question(
                self,
                self.tr("confirm_one_click"),
                "Are you sure you want to perform a one-click reset?",
                QMessageBox.Yes | QMessageBox.No,
            )

            if reply == QMessageBox.Yes:
                preserve_chat = self.preserve_chat_checkbox.isChecked()

                # 执行重置操作
                self.log("Performing one-click reset...")
                self.perform_full_reset(preserve_chat=preserve_chat)

                # 提示操作完成
                QMessageBox.information(
                    self, self.tr("success"), "One-click reset completed successfully."
                )

                self.log("One-click reset completed.")
        except Exception as e:
            # 记录错误
            self.log(f"Error during one-click reset: {str(e)}")
            QMessageBox.critical(self, self.tr("error"), f"An error occurred: {str(e)}")

    def perform_full_reset(self, preserve_chat=True):
        """执行完整重置"""
        qoder_support_dir = self.get_qoder_data_dir()

        if not qoder_support_dir.exists():
            raise Exception("未找到 Qoder 应用数据目录")

        # 1. 重置机器ID（增强版）
        self.log("1. 重置机器ID...")
        reset_qoder_machine_id(qoder_support_dir)
        self.log("   主机器ID已重置")

        # 增强：创建多个可能的机器ID文件
        additional_id_files = [
            "deviceid",
            "hardware_uuid",
            "system_uuid",
            "platform_id",
            "installation_id",
        ]
        for id_file in additional_id_files:
            file_path = qoder_support_dir / id_file
            new_id = str(uuid.uuid4())
            with open(file_path, "w") as f:
                f.write(new_id)
            self.log(f"   已创建: {id_file}")

        # 2. 重置遥测数据
        self.log("2. 重置遥测数据...")
        updated = reset_qoder_telemetry(qoder_support_dir)
        storage_json_file = qoder_support_dir / "User/globalStorage/storage.json"
        with open(storage_json_file, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Ensure system fingerprint fields are consistent with the current platform.
        data["system.platform"] = _qoder_platform_value()
        data["system.arch"] = platform.machine()
        data["system.version"] = self.generate_system_version(platform.system())

        # Optional identity cleanup: avoid deleting telemetry keys we just wrote.
        if not preserve_chat:
            identity_keywords = (
                "auth",
                "login",
                "token",
                "credential",
                "fingerprint",
                "tracking",
                "analytics",
            )
            protected_prefixes = ("telemetry.",)
            protected_keys = {
                "machineId",
                "deviceId",
                "installationId",
                "hardwareId",
                "platformId",
            }

            identity_keys_to_remove = []
            for key in list(data.keys()):
                key_lower = str(key).lower()
                if key in protected_keys or key_lower.startswith(protected_prefixes):
                    continue
                if any(keyword in key_lower for keyword in identity_keywords):
                    identity_keys_to_remove.append(key)

            for key in identity_keys_to_remove:
                data.pop(key, None)
                self.log(f"   已清除配置: {key}")
        else:
            self.log("   保留对话模式：保留非身份相关配置")

        with open(storage_json_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)

        self.log(f"   新遥测机器ID: {updated['telemetry.machineId'][:16]}...")
        self.log(f"   新设备ID: {updated['telemetry.devDeviceId']}")
        self.log(f"   新SQM ID: {updated['telemetry.sqmId']}")

        # 3. 清理缓存（增强版）
        self.log("3. 清理缓存数据...")
        cache_dirs = [
            "Cache",
            "blob_storage",
            "Code Cache",
            "SharedClientCache",
            "GPUCache",
            "DawnGraphiteCache",
            "DawnWebGPUCache",
            # 新增：更多可能包含指纹的缓存
            "ShaderCache",
            "DawnCache",
            "Dictionaries",
            "CachedData",
            "CachedProfilesData",
            "CachedExtensions",
            "IndexedDB",
            "CacheStorage",
            "WebSQL",
        ]

        cleaned = 0
        for cache_dir in cache_dirs:
            cache_path = qoder_support_dir / cache_dir
            if cache_path.exists():
                try:
                    shutil.rmtree(cache_path)
                    cleaned += 1
                except:
                    pass

        self.log(f"   已清理 {cleaned} 个缓存目录")

        # 4. 清理身份识别文件（增强版）
        self.log("4. 清理身份识别文件...")
        identity_files = [
            "Network Persistent State",  # 网络服务器连接历史和指纹
            "TransportSecurity",  # HSTS等安全策略记录
            "Trust Tokens",
            "Trust Tokens-journal",  # 信任令牌数据库
            "SharedStorage",
            "SharedStorage-wal",  # 共享存储数据库
            "Preferences",  # 用户偏好设置（可能包含指纹）
            "Secure Preferences",  # 安全偏好设置
            "Login Credentials",  # 登录凭据（如果存在）
            "Web Data",
            "Web Data-journal",  # Web数据数据库（如果存在）
            "cert_transparency_reporter_state.json",  # 证书透明度状态
            "Local State",  # Chromium本地状态（包含加密密钥）
            "NetworkDataMigrated",  # 网络数据迁移标记
            # 新增：硬件指纹相关文件
            "DeviceMetadata",
            "HardwareInfo",
            "SystemInfo",
            "QuotaManager",
            "QuotaManager-journal",
            "origin_bound_certs",
            "Network Action Predictor",
            "AutofillStrikeDatabase",
            "AutofillStrikeDatabase-journal",
            "Feature Engagement Tracker",
            "PasswordStoreDefault",
            "PreferredApps",
            "UserPrefs",
            "UserPrefs.backup",
            "Platform Notifications",
            "VideoDecodeStats",
            "OriginTrials",
            "BrowserMetrics",
            "SafeBrowsing",
            "Visited Links",
            "History",
            "History-journal",
            "Favicons",
            "Favicons-journal",
            "Shortcuts",
            "Shortcuts-journal",
            "Top Sites",
            "Top Sites-journal",
        ]

        identity_cleaned = 0
        for identity_file in identity_files:
            file_path = qoder_support_dir / identity_file
            if file_path.exists():
                try:
                    file_path.unlink()
                    self.log(f"   已清除: {identity_file}")
                    identity_cleaned += 1
                except Exception as e:
                    self.log(f"   清除失败 {identity_file}: {e}")

        # 5. 清理存储目录
        storage_dirs = [
            "Service Worker",  # 服务工作者缓存
            "Certificate Revocation Lists",  # 证书撤销列表
            "SSLCertificates",  # SSL证书缓存
            "databases",  # 数据库目录
            "clp",  # 剪贴板数据，可能包含敏感信息
            "logs",  # 日志文件，可能记录用户活动
            "Backups",  # 备份文件，可能包含历史身份信息
            "CachedExtensionVSIXs",  # 扩展缓存，显示用户安装的扩展
        ]

        # 根据是否保留对话记录来决定清理哪些存储目录
        if not preserve_chat:
            # 如果不保留对话记录，清理所有存储目录
            storage_dirs.extend(
                [
                    "Local Storage",  # 本地存储数据库（可能包含对话索引）
                    "Session Storage",  # 会话存储
                    "WebStorage",  # Web存储
                    "Shared Dictionary",  # 共享字典
                ]
            )
            self.log("   不保留对话模式：清理所有存储目录")
        else:
            # 如果保留对话记录，保留可能包含对话索引的存储
            # 但仍需清理可能包含身份信息的存储
            storage_dirs.extend(
                [
                    "Session Storage",  # 会话存储（可能包含身份信息）
                    "WebStorage",  # Web存储（可能包含身份信息）
                    "Shared Dictionary",  # 共享字典
                ]
            )
            self.log("   保留对话模式：保留 Local Storage（可能包含对话索引）")

        for storage_dir in storage_dirs:
            storage_path = qoder_support_dir / storage_dir
            if storage_path.exists():
                try:
                    shutil.rmtree(storage_path)
                    self.log(f"   已清除: {storage_dir}")
                    identity_cleaned += 1
                except Exception as e:
                    self.log(f"   清除失败 {storage_dir}: {e}")

        self.log(f"   已清理 {identity_cleaned} 个身份识别文件/目录")

        # 5. 执行高级身份清理（新增）
        self.log("5. 执行高级身份清理...")
        self.perform_advanced_identity_cleanup(qoder_support_dir, preserve_chat)

        # 6. 执行登录身份清理（新增 - 清理登录状态）
        self.log("6. 执行登录身份清理...")
        self.perform_login_identity_cleanup(qoder_support_dir)

        # 7. 执行硬件指纹重置（新增 - 最强反检测）
        self.log("7. 执行硬件指纹重置...")
        self.perform_hardware_fingerprint_reset(qoder_support_dir)

        # 8. 执行超级深度清理（新增增强功能）
        self.log("8. 执行超级深度清理...")
        self.perform_super_deep_cleanup(qoder_support_dir)

        # 9. 处理对话记录
        if preserve_chat:
            self.log("9. 保留对话记录...")
            self.log("   对话记录已保留")
        else:
            self.log("9. 清除对话记录...")
            self.clear_chat_history(qoder_support_dir)

    def perform_advanced_identity_cleanup(self, qoder_support_dir, preserve_chat=False):
        """执行高级身份清理，清除所有可能的身份识别信息"""
        try:
            self.log("开始高级身份清理...")
            cleaned_count = 0

            # 1. 清理 SharedClientCache 内部文件
            shared_cache = qoder_support_dir / "SharedClientCache"
            if shared_cache.exists():
                # 总是清理这些关键的身份文件（会重新生成）
                critical_files = [".info", ".lock", "mcp.json"]
                for file_name in critical_files:
                    file_path = shared_cache / file_name
                    if file_path.exists():
                        try:
                            file_path.unlink()
                            self.log(f"   已清除: SharedClientCache/{file_name}")
                            cleaned_count += 1
                        except Exception as e:
                            self.log(f"   清除失败 {file_name}: {e}")

                # 总是清理 cache 目录（缓存数据）
                cache_dir = shared_cache / "cache"
                if cache_dir.exists():
                    try:
                        shutil.rmtree(cache_dir)
                        self.log("   已清除: SharedClientCache/cache")
                        cleaned_count += 1
                    except Exception as e:
                        self.log(f"   清除失败 cache: {e}")

                # 根据保留对话设置决定是否清理 index 目录
                index_dir = shared_cache / "index"
                if index_dir.exists():
                    if not preserve_chat:
                        # 不保留对话：清理所有索引
                        try:
                            shutil.rmtree(index_dir)
                            self.log("   已清除: SharedClientCache/index")
                            cleaned_count += 1
                        except Exception as e:
                            self.log(f"   清除失败 index: {e}")
                    else:
                        # 保留对话：只清理非对话相关的索引
                        # 保留可能包含对话搜索索引的文件
                        for index_item in index_dir.iterdir():
                            if (
                                index_item.is_dir()
                                and "chat" not in index_item.name.lower()
                            ):
                                try:
                                    shutil.rmtree(index_item)
                                    self.log(
                                        f"   已清除: SharedClientCache/index/{index_item.name}"
                                    )
                                    cleaned_count += 1
                                except Exception as e:
                                    self.log(
                                        f"   清除失败 index/{index_item.name}: {e}"
                                    )
                        self.log("   保留对话模式：保留可能的对话索引")

            # 2. 清理系统级别的身份文件
            system_files = ["code.lock", "languagepacks.json"]

            for sys_file in system_files:
                file_path = qoder_support_dir / sys_file
                if file_path.exists():
                    try:
                        file_path.unlink()
                        self.log(f"   已清除: {sys_file}")
                        cleaned_count += 1
                    except Exception as e:
                        self.log(f"   清除失败 {sys_file}: {e}")

            # 3. 清理崩溃报告目录（可能包含设备信息）
            crashpad_dir = qoder_support_dir / "Crashpad"
            if crashpad_dir.exists():
                try:
                    shutil.rmtree(crashpad_dir)
                    self.log("   已清除: Crashpad")
                    cleaned_count += 1
                except Exception as e:
                    self.log(f"   清除失败 Crashpad: {e}")

            # 4. 清理缓存目录（CachedData和 CachedProfilesData）
            cached_dirs = ["CachedData", "CachedProfilesData"]
            for cached_dir in cached_dirs:
                dir_path = qoder_support_dir / cached_dir
                if dir_path.exists():
                    try:
                        shutil.rmtree(dir_path)
                        self.log(f"   已清除: {cached_dir}")
                        cleaned_count += 1
                    except Exception as e:
                        self.log(f"   清除失败 {cached_dir}: {e}")

            # 5. 清理 socket 文件
            import glob

            socket_pattern = str(qoder_support_dir / "*.sock")
            socket_files = glob.glob(socket_pattern)
            for socket_file in socket_files:
                try:
                    Path(socket_file).unlink()
                    self.log(f"   已清除: {Path(socket_file).name}")
                    cleaned_count += 1
                except Exception as e:
                    self.log(f"   清除失败 {Path(socket_file).name}: {e}")

            # 6. 清理设备指纹和活动记录文件（新增）
            fingerprint_and_activity_files = [
                "DeviceMetadata",
                "HardwareInfo",
                "SystemInfo",
                "QuotaManager",
                "QuotaManager-journal",
                "ActivityLog",
                "EventLog",
                "UserActivityLog",
                "origin_bound_certs",
                "Network Action Predictor",
                "AutofillStrikeDatabase",
                "AutofillStrikeDatabase-journal",
                "Feature Engagement Tracker",
                "PasswordStoreDefault",
                "PreferredApps",
                "UserPrefs",
                "UserPrefs.backup",
            ]

            for file_name in fingerprint_and_activity_files:
                file_path = qoder_support_dir / file_name
                if file_path.exists():
                    try:
                        if file_path.is_dir():
                            shutil.rmtree(file_path)
                        else:
                            file_path.unlink()
                        self.log(f"   已清除: {file_name}")
                        cleaned_count += 1
                    except Exception as e:
                        self.log(f"   清除失败 {file_name}: {e}")

            # 7. 清理数据库目录内的所有文件（新增）
            databases_dir = qoder_support_dir / "databases"
            if databases_dir.exists():
                try:
                    shutil.rmtree(databases_dir)
                    self.log("   已清除: databases 目录及其所有内容")
                    cleaned_count += 1
                except Exception as e:
                    self.log(f"   清除失败 databases: {e}")

            # 8. 清理 Electron 相关的持久化数据（新增）
            electron_files = [
                "Dictionaries",
                "Platform Notifications",
                "ShaderCache",
                "VideoDecodeStats",
                "OriginTrials",
                "BrowserMetrics",
                "AutofillRegexes",
                "SafeBrowsing",
            ]

            for electron_file in electron_files:
                file_path = qoder_support_dir / electron_file
                if file_path.exists():
                    try:
                        if file_path.is_dir():
                            shutil.rmtree(file_path)
                        else:
                            file_path.unlink()
                        self.log(f"   已清除: {electron_file}")
                        cleaned_count += 1
                    except Exception as e:
                        self.log(f"   清除失败 {electron_file}: {e}")

            self.log(f"   高级身份清理完成，处理了 {cleaned_count} 个项目")

        except Exception as e:
            self.log(f"   高级身份清理失败: {e}")

    def clear_chat_history(self, qoder_support_dir):
        """清除对话记录（支持 Modern Qoder SQLite 数据库与 Legacy 目录）"""
        try:
            cleared = 0

            # 1. Modern Qoder: SQLite chat buffers, caches, and migrations
            modern_chat_sqlite_patterns = [
                "chat-session-turn-payload-buffer.sqlite*",
                "collaboration-message-cache.sqlite*",
                "memoryMigration.sqlite*",
                "sessionMigration.sqlite*",
            ]
            import glob
            for pattern in modern_chat_sqlite_patterns:
                for match in glob.glob(str(qoder_support_dir / pattern)):
                    try:
                        p = Path(match)
                        if p.is_file():
                            p.unlink()
                            self.log(f"   已清除现代对话数据库: {p.name}")
                            cleared += 1
                    except Exception as e:
                        self.log(f"   清除对话数据库失败 {match}: {e}")

            # 2. Modern Qoder: main.sqlite chat & turn tables purge
            main_sqlite = qoder_support_dir / "main.sqlite"
            if main_sqlite.is_file():
                purged_tables = _purge_sqlite_chat_data(main_sqlite)
                if purged_tables > 0:
                    self.log(f"   已清空 main.sqlite 中 {purged_tables} 个对话数据表")
                    cleared += purged_tables

            # 3. Modern Qoder: qoder-data.v1.json turns and session deliveries
            qoder_data_json = qoder_support_dir / "qoder-data.v1.json"
            if qoder_data_json.is_file():
                if _reset_qoder_data_json(qoder_data_json):
                    self.log("   已清空 qoder-data.v1.json 中的会话交付与对话轮次")
                    cleared += 1

            # 4. Modern Qoder: ~/.qoder session, project, tasks, and snapshot data
            dot_qoder = resolve_qoder_home_dir()
            dot_chat_targets = [
                dot_qoder / "logs" / "sessions",
                dot_qoder / "projects",
                dot_qoder / "tasks",
                dot_qoder / "sites" / "sessions",
                dot_qoder / "shell-snapshots",
                dot_qoder / "host-actions" / "result-index",
                dot_qoder / "memory",
            ]
            for target in dot_chat_targets:
                if target.exists():
                    try:
                        if target.is_dir():
                            shutil.rmtree(target)
                        else:
                            target.unlink()
                        try:
                            rel_name = target.relative_to(dot_qoder)
                        except Exception:
                            rel_name = target.name
                        self.log(f"   已清除 ~/.qoder/{rel_name}")
                        cleared += 1
                    except Exception as e:
                        self.log(f"   清除 ~/.qoder 记录失败 {target.name}: {e}")

            # 3. 清除工作区中的对话会话
            workspace_storage = qoder_support_dir / "User/workspaceStorage"
            if workspace_storage.exists():
                for workspace_dir in workspace_storage.iterdir():
                    if workspace_dir.is_dir():
                        chat_sessions = workspace_dir / "chatSessions"
                        if chat_sessions.exists():
                            try:
                                shutil.rmtree(chat_sessions)
                                self.log(
                                    f"   已清除: {chat_sessions.relative_to(qoder_support_dir)}"
                                )
                                cleared += 1
                            except Exception as e:
                                self.log(
                                    f"   清除失败 {chat_sessions.relative_to(qoder_support_dir)}: {e}"
                                )

                        chat_editing = workspace_dir / "chatEditingSessions"
                        if chat_editing.exists():
                            try:
                                shutil.rmtree(chat_editing)
                                self.log(
                                    f"   已清除: {chat_editing.relative_to(qoder_support_dir)}"
                                )
                                cleared += 1
                            except Exception as e:
                                self.log(
                                    f"   清除失败 {chat_editing.relative_to(qoder_support_dir)}: {e}"
                                )

            # 4. 清除历史记录
            history_dir = qoder_support_dir / "User/History"
            if history_dir.exists():
                try:
                    shutil.rmtree(history_dir)
                    self.log(f"   已清除: User/History")
                    cleared += 1
                except Exception as e:
                    self.log(f"   清除失败 User/History: {e}")

            # 5. 清除会话存储中的对话相关数据
            session_storage = qoder_support_dir / "Session Storage"
            if session_storage.exists():
                try:
                    shutil.rmtree(session_storage)
                    self.log(f"   已清除: Session Storage")
                    cleared += 1
                except Exception as e:
                    self.log(f"   清除失败 Session Storage: {e}")

            # 6. 清除用户数据中的对话相关配置
            user_data_file = qoder_support_dir / "User/globalStorage/storage.json"
            if user_data_file.exists():
                try:
                    with open(user_data_file, "r", encoding="utf-8") as f:
                        data = json.load(f)

                    # 清除对话相关的键
                    chat_keys = [
                        key
                        for key in data.keys()
                        if "chat" in key.lower()
                        or "conversation" in key.lower()
                        or "history" in key.lower()
                        or "session" in key.lower()
                    ]

                    if chat_keys:
                        for key in chat_keys:
                            del data[key]
                            self.log(f"   已清除配置: {key}")

                        with open(user_data_file, "w", encoding="utf-8") as f:
                            json.dump(data, f, indent=4, ensure_ascii=False)

                        cleared += 1

                except Exception as e:
                    self.log(f"   清除用户配置失败: {e}")

            self.log(f"   对话记录清除完成 (处理了 {cleared} 个项目)")

        except Exception as e:
            self.log(f"   清除对话记录失败: {e}")

    def open_github(self):
        """打开外部链接"""
        target_url = ""
        if target_url:
            webbrowser.open(target_url)
        else:
            self.log("未配置外部仓库链接")

    def _write_fake_hardware_info(self, qoder_support_dir):
        """Create fake hardware information used by hardware fingerprint reset."""
        try:
            # 5. Create fake hardware information (interference detection)
            self.log("5. Creating fake hardware information...")
            try:
                # Generate appropriate fake hardware information based on system type
                system_type = platform.system()
                self.log(f"   Detected system type: {system_type}")

                if system_type == "Darwin":  # macOS
                    fake_hardware_info = {
                        "cpu": {
                            "name": f"Apple M{random.randint(2, 5)} Pro",
                            "cores": random.choice([8, 10, 12, 16]),
                            "threads": random.choice([8, 10, 12, 16]),
                            "frequency": f"{random.uniform(2.0, 4.0):.1f}GHz",
                        },
                        "gpu": {
                            "name": f"Apple M{random.randint(2, 5)} Pro GPU",
                            "memory": f"{random.choice([16, 24, 32])}GB",
                            "cores": random.choice([16, 19, 24, 32]),
                        },
                        "memory": {
                            "total": f"{random.choice([16, 24, 32, 64])}GB",
                            "type": "LPDDR5",
                            "speed": f"{random.choice([6400, 7467])}MT/s",
                        },
                    }
                elif system_type == "Windows":  # Windows
                    cpu_brands = ["Intel", "AMD"]
                    cpu_brand = random.choice(cpu_brands)

                    if cpu_brand == "Intel":
                        cpu_series = random.choice(["Core i5", "Core i7", "Core i9"])
                        cpu_gen = random.randint(12, 14)
                        cpu_model = f"{random.randint(600, 900)}{'K' if random.choice([True, False]) else ''}"
                        cpu_name = f"Intel {cpu_series}-{cpu_gen}{cpu_model}"
                    else:  # AMD
                        cpu_series = random.choice(["Ryzen 5", "Ryzen 7", "Ryzen 9"])
                        cpu_gen = random.randint(5000, 7000)
                        cpu_name = f"AMD {cpu_series} {cpu_gen}X"

                    gpu_brands = ["NVIDIA", "AMD", "Intel"]
                    gpu_brand = random.choice(gpu_brands)

                    if gpu_brand == "NVIDIA":
                        gpu_series = random.choice(
                            ["RTX 4060", "RTX 4070", "RTX 4080", "RTX 4090"]
                        )
                        gpu_name = f"NVIDIA GeForce {gpu_series}"
                        gpu_memory = f"{random.choice([8, 12, 16, 24])}GB"
                    elif gpu_brand == "AMD":
                        gpu_series = random.choice(
                            ["RX 7600", "RX 7700 XT", "RX 7800 XT", "RX 7900 XTX"]
                        )
                        gpu_name = f"AMD Radeon {gpu_series}"
                        gpu_memory = f"{random.choice([8, 12, 16, 20])}GB"
                    else:  # Intel
                        gpu_series = random.choice(["Arc A750", "Arc A770", "Iris Xe"])
                        gpu_name = f"Intel {gpu_series}"
                        gpu_memory = f"{random.choice([8, 12, 16])}GB"

                    fake_hardware_info = {
                        "cpu": {
                            "name": cpu_name,
                            "cores": random.choice([6, 8, 12, 16, 24]),
                            "threads": random.choice([12, 16, 20, 24, 32]),
                            "frequency": f"{random.uniform(3.0, 5.0):.1f}GHz",
                        },
                        "gpu": {
                            "name": gpu_name,
                            "memory": gpu_memory,
                            "cores": random.choice([1024, 1536, 2048, 2560]),
                        },
                        "memory": {
                            "total": f"{random.choice([16, 24, 32])}GB",
                            "type": "LPDDR5",
                            "speed": f"{random.choice([4266, 5500, 6400])}MHz",
                        },
                    }
                else:
                    # Default case for other systems
                    fake_hardware_info = {
                        "cpu": {
                            "name": "Generic CPU",
                            "cores": random.choice([4, 6, 8]),
                            "threads": random.choice([8, 12, 16]),
                            "frequency": f"{random.uniform(2.0, 4.0):.1f}GHz",
                        },
                        "gpu": {
                            "name": "Generic GPU",
                            "memory": f"{random.choice([4, 8, 12])}GB",
                            "cores": random.choice([512, 1024, 1536]),
                        },
                        "memory": {
                            "total": f"{random.choice([8, 16, 24])}GB",
                            "type": "DDR4",
                            "speed": f"{random.choice([2400, 3200, 4000])}MHz",
                        },
                    }

                # Write fake hardware information to a file
                hardware_file = qoder_support_dir / "hardware_info.json"
                with open(hardware_file, "w", encoding="utf-8") as f:
                    json.dump(fake_hardware_info, f, indent=4, ensure_ascii=False)

                self.log("   Successfully created fake hardware information")

            except Exception as e:
                self.log(f"   Failed to create fake hardware information: {e}")

        except Exception as e:
            self.log(f"Error during hardware fingerprint reset: {e}")
            raise

    def perform_super_deep_cleanup(self, qoder_support_dir):
        """🛡️ 执行超级深度清理（安全增强版，只清理与Qoder相关的文件）"""
        try:
            self.log("🔥 开始安全的超级深度清理...")
            cleaned_count = 0

            # 1. 清理系统级别的身份文件
            self.log("1. 清理系统级别身份文件...")
            system_identity_files = [
                # 日志和临时文件
                "logs",
                "tmp",
                "temp",
                "crash_dumps",
                # 更多可能的身份识别文件
                "identity.json",
                "machine.json",
                "device.json",
                "fingerprint.json",
                "tracking.json",
                "analytics.json",
                # 浏览器相关文件
                "BrowserUserAgent",
                "ClientHints",
                "NavigatorInfo",
                "ScreenInfo",
                "TimezoneInfo",
                "LanguageInfo",
                # 网络相关文件
                "DNSCache",
                "HTTPCache",
                "ProxySettings",
                "NetworkConfiguration",
                "ConnectionHistory",
                # 系统信息文件
                "OSInfo",
                "HardwareProfile",
                "SystemMetrics",
                "PerformanceInfo",
                "MemoryInfo",
                "DiskInfo",
                # 用户活动相关
                "UserActivity",
                "AppUsage",
                "FeatureUsage",
                "InteractionHistory",
                "AccessLog",
                "AuditLog",
                # 安全相关文件
                "SecuritySettings",
                "CertificateStore",
                "TrustStore",
                "EncryptionKeys",
                "AuthTokens",
                "SessionKeys",
                # 缓存相关文件
                "MetadataCache",
                "ThumbnailCache",
                "IndexCache",
                "SearchCache",
                "QueryCache",
                "ResultsCache",
                # 扩展和插件相关
                "ExtensionData",
                "PluginData",
                "AddonData",
                "ExtensionPrefs",
                "PluginPrefs",
                "AddonPrefs",
                # 更多 WebKit 相关文件
                "WebKitCache",
                "WebProcessCache",
                "PluginProcessCache",
                "RenderProcessCache",
                "GPUProcessCache",
                # 更多 Chromium 相关文件
                "ChromiumState",
                "ChromiumPrefs",
                "ChromiumHistory",
                "ChromiumCookies",
                "ChromiumSessions",
            ]

            for file_name in system_identity_files:
                file_path = qoder_support_dir / file_name
                if file_path.exists():
                    try:
                        if file_path.is_dir():
                            shutil.rmtree(file_path)
                        else:
                            file_path.unlink()
                        self.log(f"   ✅ 已清除: {file_name}")
                        cleaned_count += 1
                    except Exception as e:
                        self.log(f"   ⚠️  清除失败 {file_name}: {e}")

            # 2. 谨慎清理指定扩展名的可疑文件（增加安全检查）
            self.log("2. 谨慎清理可疑扩展名文件...")
            suspicious_extensions = [
                ".tmp",
                ".temp",
                ".cache",
                ".lock",
                ".pid",
                ".sock",
                ".session",
                ".fingerprint",
                ".tracking",
                ".analytics",
            ]

            # 🚫 绝对安全白名单 - 永远不删除的重要文件
            safe_keywords = [
                "settings",
                "config",
                "workspace",
                "preference",
                "backup",
                "license",
                "certificate",
            ]
            protected_keywords = [
                "settings",
                "config",
                "workspace",
                "preference",
                "user",
                "important",
                "backup",
                "license",
                "key",
                "certificate",
                "password",
                "auth",
                "secret",
                "critical",
                "system",
                "apple",
                "microsoft",
                "windows",
                "macos",
                "safari",
                "chrome",
            ]

            # ✅ 只清理与这些应用相关的文件
            qoder_keywords = ["qoder", "vscode", "electron", "code-", "ms-vscode"]

            for root, dirs, files in os.walk(qoder_support_dir):
                for file in files:
                    file_path = Path(root) / file
                    file_ext = file_path.suffix.lower()

                    if file_ext in suspicious_extensions:
                        # 安全检查：跳过重要文件
                        is_safe_file = any(
                            safe_word in file.lower() for safe_word in safe_keywords
                        )

                        # 🛡️ 多重安全检查
                        is_protected = any(
                            keyword in file.lower() for keyword in protected_keywords
                        )
                        is_in_qoder_dir = str(qoder_support_dir) in str(file_path)
                        is_qoder_related = any(
                            keyword in file.lower() or keyword in root.lower()
                            for keyword in qoder_keywords
                        )

                        # ✅ 只有同时满足以下条件才删除：
                        # 1. 在Qoder目录内  2. 与Qoder相关  3. 不在保护列表
                        if is_in_qoder_dir and is_qoder_related and not is_protected:
                            try:
                                file_path.unlink()
                                self.log(f"   ✅ 已清除可疑文件: {file}")
                                cleaned_count += 1
                            except Exception as e:
                                self.log(f"   ⚠️  清除失败 {file}: {e}")
                        else:
                            if not is_qoder_related:
                                self.log(f"   ℹ️  跳过非相关文件: {file}")
                            if is_safe_file:
                                self.log(f"   ℹ️  保护重要文件: {file}")

            # 3. 清理隐藏文件和目录
            self.log("3. 清理隐藏文件...")
            for root, dirs, files in os.walk(qoder_support_dir):
                # 清理隐藏文件（以点开头）
                for file in files:
                    if file.startswith(".") and file not in [".gitignore", ".gitkeep"]:
                        file_path = Path(root) / file
                        try:
                            file_path.unlink()
                            self.log(f"   ✅ 已清除隐藏文件: {file}")
                            cleaned_count += 1
                        except Exception as e:
                            self.log(f"   ⚠️  清除失败 {file}: {e}")

                # 清理隐藏目录（以点开头）
                for dir_name in dirs[:]:
                    if dir_name.startswith(".") and dir_name not in [".git"]:
                        dir_path = Path(root) / dir_name
                        try:
                            shutil.rmtree(dir_path)
                            self.log(f"   ✅ 已清除隐藏目录: {dir_name}")
                            dirs.remove(dir_name)  # 从遍历中移除
                            cleaned_count += 1
                        except Exception as e:
                            self.log(f"   ⚠️  清除失败 {dir_name}: {e}")

            # 4. 重置文件权限（防止文件时间戳检测）
            self.log("4. 重置文件权限...")
            try:
                # 重置整个目录的权限
                if platform.system() != "Windows":
                    subprocess.run(
                        ["chmod", "-R", "755", str(qoder_support_dir)],
                        check=False,
                        timeout=30,
                    )
                    self.log("   ✅ 文件权限已重置")
            except Exception as e:
                self.log(f"   ⚠️  权限重置失败: {e}")

            # 5. Do not create decoy files. Keeping cleanup output minimal makes
            # diagnostics easier and avoids adding new state that users did not ask for.
            self.log("5. 跳过迷惑文件创建，保持清理结果可验证")

            # 6. 安全清理系统级别的缓存（macOS）
            if platform.system() == "Darwin":
                self.log("6. 安全清理 macOS 系统级缓存...")
                try:
                    # 只清理用户级别的系统缓存，不影响系统稳定性
                    user_system_cache_paths = [
                        Path.home() / "Library/Caches",
                        Path.home()
                        / "Library/Application Support/com.apple.sharedfilelist",
                    ]

                    for cache_path in user_system_cache_paths:
                        if cache_path.exists() and cache_path != qoder_support_dir:
                            # 只清理与 Qoder/VSCode 相关的文件，不影响其他应用
                            for item in cache_path.iterdir():
                                item_name_lower = item.name.lower()
                                if any(
                                    keyword in item_name_lower
                                    for keyword in [
                                        "qoder",
                                        "vscode",
                                        "com.microsoft.vscode",
                                        "electron",
                                    ]
                                ):
                                    try:
                                        if item.is_dir():
                                            shutil.rmtree(item)
                                        else:
                                            item.unlink()
                                        self.log(f"   ✅ 已清理系统缓存: {item.name}")
                                        cleaned_count += 1
                                    except Exception as e:
                                        self.log(
                                            f"   ⚠️  系统缓存清理失败 {item.name}: {e}"
                                        )

                    # 不清理 LaunchServices，避免影响系统功能
                    self.log("   ℹ️  为保护系统稳定性，跳过 LaunchServices 清理")

                except Exception as e:
                    self.log(f"   ⚠️  macOS 系统缓存清理失败: {e}")

            elif platform.system() == "Windows":
                self.log("6. 安全清理 Windows 系统级缓存...")
                try:
                    # 只清理用户级别的 Qoder 缓存，绝不影响其他应用
                    user_cache_paths = [
                        Path(os.environ.get("LOCALAPPDATA", "")) / "Temp",
                        Path(os.environ.get("APPDATA", ""))
                        / "Microsoft"
                        / "Windows"
                        / "Recent",
                    ]

                    for cache_path in user_cache_paths:
                        if cache_path.exists():
                            for item in cache_path.iterdir():
                                if "qoder" in item.name.lower():
                                    try:
                                        if item.is_dir():
                                            shutil.rmtree(item)
                                        else:
                                            item.unlink()
                                        self.log(
                                            f"   ✅ 已清理Windows缓存: {item.name}"
                                        )
                                        cleaned_count += 1
                                    except Exception as e:
                                        self.log(f"   ⚠️  清理失败: {e}")

                    # 清理 qoder-updater 临时目录
                    updater_cache = Path(os.environ.get("LOCALAPPDATA", "")) / "qoder-updater"
                    if updater_cache.exists():
                        try:
                            shutil.rmtree(updater_cache)
                            self.log("   ✅ 已清理 qoder-updater 更新缓存目录")
                            cleaned_count += 1
                        except Exception as e:
                            self.log(f"   ⚠️  清理 qoder-updater 失败: {e}")

                    # 清理 Qoder Launcher 诊断日志与状态写入锁
                    launcher_dir = Path(os.environ.get("LOCALAPPDATA", "")) / "Qoder" / "Qoder Launcher"
                    if launcher_dir.is_dir():
                        diag_log = launcher_dir / "launcher-diagnostics.log"
                        if diag_log.is_file():
                            _safe_unlink(diag_log)
                            cleaned_count += 1
                        writers_dir = launcher_dir / "state.ini.writers"
                        if writers_dir.is_dir():
                            try:
                                shutil.rmtree(writers_dir)
                                cleaned_count += 1
                            except Exception:
                                pass

                except Exception as e:
                    self.log(f"   ⚠️  Windows 系统缓存清理失败: {e}")

            # 7. 深度清理 ~/.qoder 代理运行时与缓存
            self.log("7. 深度清理 ~/.qoder 代理运行时与缓存...")
            dot_qoder = resolve_qoder_home_dir()
            if dot_qoder.exists():
                dot_deep_targets = [
                    dot_qoder / "tmp",
                    dot_qoder / "logs",
                    dot_qoder / "host-actions",
                    dot_qoder / "shell-snapshots",
                    dot_qoder / "tasks",
                    dot_qoder / "sites",
                    dot_qoder / "memory",
                    dot_qoder / ".cache",
                    dot_qoder / ".last-cleanup",
                    dot_qoder / "umid-cache.json",
                ]
                for target in dot_deep_targets:
                    if target.exists():
                        try:
                            if target.is_dir():
                                shutil.rmtree(target)
                            else:
                                target.unlink()
                            self.log(f"   ✅ 已清除 ~/.qoder/{target.name}")
                            cleaned_count += 1
                        except Exception as e:
                            self.log(f"   ⚠️  清除 ~/.qoder/{target.name} 失败: {e}")

                # 清理插件内部运行锁与端点缓存（保留插件代码）
                plugins_data = dot_qoder / "plugins" / "data"
                if plugins_data.is_dir():
                    for pdir in plugins_data.iterdir():
                        if pdir.is_dir():
                            for sub_run in ["run", "state"]:
                                srp = pdir / sub_run
                                if srp.exists():
                                    try:
                                        shutil.rmtree(srp)
                                        self.log(f"   ✅ 已清除插件运行状态: {pdir.name}/{sub_run}")
                                        cleaned_count += 1
                                    except Exception:
                                        pass

                # 刷新 installation_id
                _safe_write_text(dot_qoder / "installation_id", str(uuid.uuid4()) + "\n")
                cleaned_count += 1

            self.log(f"   超级深度清理完成，处理了 {cleaned_count} 个项目")

        except Exception as e:
            self.log(f"   超级深度清理失败: {e}")

    def perform_hardware_fingerprint_reset(self, qoder_support_dir):
        """Thực hiện reset dấu vân tay phần cứng"""
        try:
            # Kiểm tra thư mục tồn tại
            if not qoder_support_dir.exists():
                raise Exception("Không tìm thấy thư mục Qoder")

            # Sinh UUID mới
            import uuid
            import json
            import hashlib

            # Tạo các ID mới
            new_machine_id = str(uuid.uuid4())
            new_device_id = str(uuid.uuid4())
            machine_id_hash = hashlib.sha256(new_machine_id.encode()).hexdigest()

            # Đường dẫn file storage
            storage_json_file = qoder_support_dir / "User/globalStorage/storage.json"

            # Đọc và cập nhật file storage
            if storage_json_file.exists():
                with open(storage_json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)

                # Cập nhật các trường liên quan đến hardware
                data["telemetry.machineId"] = machine_id_hash
                data["telemetry.devDeviceId"] = new_device_id
                data["machineId"] = machine_id_hash

                with open(storage_json_file, "w", encoding="utf-8") as f:
                    json.dump(data, f, indent=4, ensure_ascii=False)

            # Ghi log
            self.log(
                f"Reset hardware fingerprint: New Machine ID {machine_id_hash[:16]}..."
            )
            self.log(f"New Device ID: {new_device_id}")
            self._write_fake_hardware_info(qoder_support_dir)

        except Exception as e:
            self.log(f"Error resetting hardware fingerprint: {e}")
            raise


def parse_args():
    import argparse

    parser = argparse.ArgumentParser(
        description="Qoder 重置工具：专为 Qoder AI IDE 设计的本地隐私与机器码重置工具"
    )
    parser.add_argument(
        "--cli",
        action="store_true",
        help="以命令行控制台模式运行（不打开图形界面）",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="一键执行 Qoder 机器码、指纹与遥测数据全量重置",
    )
    parser.add_argument(
        "--preserve-chat",
        action="store_true",
        default=True,
        help="重置时保留对话历史记录（默认：保留）",
    )
    parser.add_argument(
        "--no-preserve-chat",
        action="store_false",
        dest="preserve_chat",
        help="重置时不保留对话记录（彻底干净清理）",
    )
    parser.add_argument(
        "--backup",
        action="store_true",
        help="创建当前 Qoder 身份数据的快照备份",
    )
    parser.add_argument(
        "--restore",
        nargs="?",
        const="latest",
        default=None,
        help="从最近一次或指定路径恢复身份数据",
    )
    parser.add_argument(
        "--list-backups",
        action="store_true",
        help="列出所有可用的历史身份备份",
    )
    parser.add_argument(
        "--check-update",
        action="store_true",
        help="检查更新状态",
    )
    parser.add_argument(
        "--status",
        action="store_true",
        help="显示当前 Qoder 运行状态、安装目录与机器码标识",
    )
    parser.add_argument(
        "--close-qoder",
        action="store_true",
        help="强制关闭所有正在运行的 Qoder 相关进程",
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"Qoder 重置工具 v{__version__}",
    )
    return parser.parse_args()


def run_cli(args) -> int:
    qoder_dir = resolve_qoder_data_dir()
    dot_qoder = resolve_qoder_home_dir()
    targets = resolve_all_qoder_targets()

    print("=" * 60)
    print(f"🔒 Qoder 重置工具 v{__version__} [控制台模式]")
    print(f"操作系统平台: {platform.system()} ({platform.machine()})")
    print(f"主数据目录: {qoder_dir}")
    print(f"用户主目录: {dot_qoder}")
    print("=" * 60)
    _repair_sqlite_fts(qoder_dir / "main.sqlite")

    if args.close_qoder:
        print("[*] 正在终止 Qoder 进程...")
        success, details = kill_qoder_process()
        if success:
            print(f"[+] {details}")
        else:
            print(f"[-] 终止 Qoder 进程失败: {details}")

    if args.check_update:
        print("[*] 检查更新...")
        update_info = check_for_updates()
        if update_info.get("success"):
            if update_info.get("has_update"):
                print(
                    f"[!] 发现新版本: v{update_info['latest_version']} (当前: v{update_info['current_version']})"
                )
                print(f"    下载链接: {update_info['url']}")
            else:
                print(f"[+] 当前已是最新版本 (v{__version__})。")
        else:
            print(
                f"[-] 未检查到更新信息: {update_info.get('error', '未知状态')}"
            )

    if args.list_backups:
        print("[*] 可用历史备份:")
        backups = list_qoder_backups(qoder_dir)
        if not backups:
            print("    未找到任何备份。")
        else:
            for b in backups:
                print(f"    - {b.name} ({b})")

    if args.backup:
        print("[*] 正在创建身份数据备份...")
        try:
            backup_path = backup_qoder_identity(qoder_dir)
            print(f"[+] 备份已成功创建于: {backup_path}")
        except Exception as e:
            print(f"[-] 备份失败: {e}")
            return 1

    if args.restore is not None:
        print("[*] 正在从备份恢复身份数据...")
        backups = list_qoder_backups(qoder_dir)
        if args.restore == "latest":
            if not backups:
                print("[-] 未找到可用于恢复的备份。")
                return 1
            target_backup = backups[0]
        else:
            target_backup = Path(args.restore)
            if not target_backup.is_dir():
                print(f"[-] 指定的备份路径不存在: {target_backup}")
                return 1

        print(f"[*] 正在从该目录恢复: {target_backup}")
        success, msg = restore_qoder_identity(target_backup, qoder_dir)
        if success:
            print(f"[+] {msg}")
        else:
            print(f"[-] 恢复失败: {msg}")
            return 1

    if args.status:
        is_running = check_is_qoder_running()
        dir_exists = qoder_dir.exists()
        print(f"[*] Qoder 状态信息:")
        print(f"    - 进程状态: {'运行中' if is_running else '未运行'}")
        print(f"    - 主数据目录 ({qoder_dir.name}): {'存在' if dir_exists else '未找到'}")

        # Check Modern Qoder Machine ID
        modern_mid_file = qoder_dir / "auth.machine-id"
        if modern_mid_file.is_file():
            try:
                m_mid = modern_mid_file.read_text(encoding="utf-8").strip()
                print(f"    - 现代机器码 (auth.machine-id): {m_mid}")
            except Exception:
                pass

        # Check Legacy Machine ID
        machine_id_file = qoder_dir / "machineid"
        if machine_id_file.is_file():
            try:
                m_id = machine_id_file.read_text(encoding="utf-8").strip()
                print(f"    - 旧版机器码 (machineid): {m_id}")
            except Exception:
                pass

        # Check Home ~/.qoder status
        print(f"    - 用户主目录 (~/.qoder): {'存在' if dot_qoder.exists() else '未找到'}")
        inst_id_file = dot_qoder / "installation_id"
        if inst_id_file.is_file():
            try:
                print(f"    - 安装标识 (installation_id): {inst_id_file.read_text(encoding='utf-8').strip()}")
            except Exception:
                pass
        status_file = dot_qoder / ".qoder-app-status.json"
        if status_file.is_file():
            try:
                sdata = json.loads(status_file.read_text(encoding="utf-8"))
                email = sdata.get("email", "")
                masked = (email[:2] + "***@" + email.split("@")[-1]) if "@" in email else (email[:3] + "***" if email else "无")
                print(f"    - 登录账号: 已登录={sdata.get('logged_in', False)}, 用户={masked}")
            except Exception:
                pass

        storage_file = qoder_dir / "User" / "globalStorage" / "storage.json"
        if storage_file.is_file():
            try:
                data = json.loads(storage_file.read_text(encoding="utf-8"))
                print(
                    f"    - 遥测机器码: {data.get('telemetry.machineId', '无')[:16]}..."
                )
                print(f"    - 设备标识: {data.get('telemetry.devDeviceId', '无')}")
            except Exception:
                pass

    if args.reset:
        if check_is_qoder_running():
            print("[*] 检测到 Qoder 正在运行，正在先终止进程...")
            kill_qoder_process()

        # Auto-backup before reset
        try:
            b_path = backup_qoder_identity(qoder_dir)
            print(f"[+] 重置前自动备份已保存至: {b_path.name}")
        except Exception:
            pass

        print(
            f"[*] 正在执行全量重置 (保留对话记录={args.preserve_chat})..."
        )
        try:
            if not qoder_dir.exists():
                qoder_dir.mkdir(parents=True, exist_ok=True)

            # 1. Reset machine id (modern auth.machine-id + legacy machineid + plugin machine_id)
            m_id = reset_qoder_machine_id(qoder_dir)
            print(f"    [+] 机器标识重置完成: {m_id}")

            # Additional legacy ID files
            for id_file in [
                "deviceid",
                "hardware_uuid",
                "system_uuid",
                "platform_id",
                "installation_id",
            ]:
                _safe_write_text(qoder_dir / id_file, str(uuid.uuid4()))

            # 2. Reset telemetry
            t_data = reset_qoder_telemetry(qoder_dir)
            print(
                f"    [+] 遥测数据重置完成: {t_data.get('telemetry.machineId', '')[:16]}..."
            )

            # 3. Clean Modern Qoder login credentials & status
            modern_auth_files = [
                "auth.v1.dat",
                "auth-profile-overlays.v1.dat",
                "first-launch-onboarding.v1.json",
            ]
            for fname in modern_auth_files:
                _safe_unlink(qoder_dir / fname)

            dot_auth = dot_qoder / ".auth"
            if dot_auth.exists():
                try:
                    shutil.rmtree(dot_auth)
                except Exception:
                    pass

            status_file = dot_qoder / ".qoder-app-status.json"
            if status_file.exists():
                try:
                    sdata = json.loads(status_file.read_text(encoding="utf-8"))
                    sdata["logged_in"] = False
                    sdata["name"] = ""
                    sdata["email"] = ""
                    sdata["avatar_url"] = ""
                    status_file.write_text(json.dumps(sdata, indent=2), encoding="utf-8")
                except Exception:
                    pass

            # Purge SQLite auth tables
            main_db = qoder_dir / "main.sqlite"
            if main_db.is_file():
                _purge_sqlite_auth_data(main_db)

            print("    [+] Qoder 账号凭证与登录配置重置完成。")

            # 4. Clean cache and modern session directories
            cache_dirs = [
                "Cache",
                "blob_storage",
                "Code Cache",
                "SharedClientCache",
                "GPUCache",
                "DawnGraphiteCache",
                "DawnWebGPUCache",
                "IndexedDB",
                "CacheStorage",
                "Network",
                "Partitions",
                "Local Storage",
                "Session Storage",
                "rum-electron-store",
                "crash-feedback-v1",
            ]
            c_count = 0
            for cd in cache_dirs:
                cp = qoder_dir / cd
                if cp.exists():
                    try:
                        shutil.rmtree(cp)
                        c_count += 1
                    except Exception:
                        pass

            # Clean ~/.qoder .cache, .models, and tmp/telemetry
            for dot_c in [dot_qoder / ".cache", dot_qoder / ".models", dot_qoder / "tmp" / "telemetry"]:
                if dot_c.exists():
                    try:
                        shutil.rmtree(dot_c)
                        c_count += 1
                    except Exception:
                        pass
            print(f"    [+] 已清除 {c_count} 个缓存与会话目录。")

            # 5. Clean identity files
            identity_files = [
                "Network Persistent State",
                "Cookies",
                "Cookies-journal",
                "Trust Tokens",
                "Trust Tokens-journal",
                "TransportSecurity",
                "Local State",
                "DIPS",
                "SharedStorage",
            ]
            f_count = 0
            for ifile in identity_files:
                ip = qoder_dir / ifile
                if ip.is_file():
                    try:
                        ip.unlink()
                        f_count += 1
                    except Exception:
                        pass
            print(f"    [+] 已清除 {f_count} 个身份状态文件。")

            # 6. Chat history if not preserved
            if not args.preserve_chat:
                import glob
                for pat in [
                    "chat-session-turn-payload-buffer.sqlite*",
                    "collaboration-message-cache.sqlite*",
                    "memoryMigration.sqlite*",
                    "sessionMigration.sqlite*",
                ]:
                    for m in glob.glob(str(qoder_dir / pat)):
                        _safe_unlink(Path(m))

                # Purge main.sqlite chat tables
                if main_db.is_file():
                    _purge_sqlite_chat_data(main_db)

                # Reset qoder-data.v1.json
                qoder_data_json = qoder_dir / "qoder-data.v1.json"
                if qoder_data_json.is_file():
                    _reset_qoder_data_json(qoder_data_json)

                # Clean ~/.qoder chat targets
                for dot_target in [
                    dot_qoder / "logs" / "sessions",
                    dot_qoder / "projects",
                    dot_qoder / "tasks",
                    dot_qoder / "sites" / "sessions",
                    dot_qoder / "shell-snapshots",
                    dot_qoder / "host-actions" / "result-index",
                    dot_qoder / "memory",
                ]:
                    if dot_target.exists():
                        try:
                            if dot_target.is_dir():
                                shutil.rmtree(dot_target)
                            else:
                                dot_target.unlink()
                        except Exception:
                            pass
                print("    [+] 历史对话记录与会话数据库清理完成。")
            else:
                print("    [+] 历史对话记录已保留。")

            print("[成功] Qoder 重置全部完成！")
            return 0
        except Exception as e:
            print(f"[-] 重置失败: {e}")
            return 1

    return 0


def main():
    args = parse_args()

    # Determine if CLI mode should be executed
    cli_flags_present = any(
        [
            args.cli,
            args.reset,
            args.backup,
            args.restore is not None,
            args.list_backups,
            args.check_update,
            args.status,
            args.close_qoder,
        ]
    )

    if cli_flags_present or not HAS_PYQT5:
        if not HAS_PYQT5 and not cli_flags_present:
            print("Notice: PyQt5 is not installed. Running in CLI status mode.")
            print("To launch the GUI, run: pip install PyQt5")
            print("Use --help to see all available CLI commands.")
            print()
            args.status = True
        sys.exit(run_cli(args))

    _configure_qt_runtime()
    app = QApplication(sys.argv)

    # Set application style
    app.setStyle("Fusion")

    # Set global style sheet
    app.setStyleSheet("""
        QMessageBox {
            background-color: white;
            color: black;
        }
        QMessageBox QLabel {
            color: black;
        }
        QMessageBox QPushButton {
            background-color: white;
            color: black;
            border: 1px solid #ccc;
            padding: 5px 15px;
        }
    """)

    window = QoderResetGUI()
    window.show()

    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
