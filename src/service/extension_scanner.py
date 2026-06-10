"""
扫描本地浏览器用户数据目录，检测 RPA Script 扩展是否已安装。
支持 Chrome / Edge（Windows 默认路径）。
"""

import json
import os
from typing import List, Dict, Optional

_EXTENSION_NAME = "RPA Script Browser Agent"


def _get_browser_user_data_dirs() -> List[Dict]:
    """返回支持的浏览器用户数据目录列表。"""
    dirs = []
    local_app_data = os.environ.get("LOCALAPPDATA", os.path.expandvars(r"%LOCALAPPDATA%"))
    if not local_app_data or not os.path.isdir(local_app_data):
        return dirs

    candidates = [
        ("chrome", os.path.join(local_app_data, "Google", "Chrome", "User Data")),
        ("chrome_canary", os.path.join(local_app_data, "Google", "Chrome SxS", "User Data")),
        ("chrome_beta", os.path.join(local_app_data, "Google", "Chrome Beta", "User Data")),
        ("chrome_dev", os.path.join(local_app_data, "Google", "Chrome Dev", "User Data")),
        ("chromium", os.path.join(local_app_data, "Chromium", "User Data")),
        ("edge", os.path.join(local_app_data, "Microsoft", "Edge", "User Data")),
        ("edge_dev", os.path.join(local_app_data, "Microsoft", "Edge Dev", "User Data")),
        ("edge_beta", os.path.join(local_app_data, "Microsoft", "Edge Beta", "User Data")),
        ("edge_canary", os.path.join(local_app_data, "Microsoft", "Edge SxS", "User Data")),
    ]
    for browser, path in candidates:
        if os.path.isdir(path):
            mapped = browser.split("_")[0]
            dirs.append({"browser": mapped, "path": path})
    return dirs


def _list_profiles(user_data_dir: str) -> List[str]:
    """列出用户数据目录下的 Profile 名称。"""
    profiles = []
    try:
        for name in os.listdir(user_data_dir):
            full = os.path.join(user_data_dir, name)
            if not os.path.isdir(full):
                continue
            if os.path.isfile(os.path.join(full, "Preferences")) or os.path.isdir(
                os.path.join(full, "Extensions")
            ):
                profiles.append(name)
    except OSError:
        pass
    return profiles


def _read_manifest_from_path(manifest_path: str) -> Optional[dict]:
    """读取指定路径的 manifest.json。"""
    if not os.path.isfile(manifest_path):
        return None
    try:
        with open(manifest_path, "r", encoding="utf-8", errors="ignore") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return None


def _parse_preferences_file(pref_path: str) -> dict:
    """解析 Preferences 或 Secure Preferences 文件。"""
    if not os.path.isfile(pref_path):
        return {}
    try:
        with open(pref_path, "r", encoding="utf-8", errors="ignore") as f:
            text = f.read()
        idx = text.find("{")
        if idx == -1:
            return {}
        return json.loads(text[idx:])
    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
        return {}


def _match_extension_from_settings(settings: dict, profile: str, source: str) -> List[Dict]:
    """从 extensions.settings 中匹配 RPA Script 扩展。"""
    results = []
    for ext_id, info in settings.items():
        manifest = info.get("manifest", {}) or {}
        name = manifest.get("name", "")
        path = info.get("path", "")

        if not name and path:
            manifest = _read_manifest_from_path(os.path.join(path, "manifest.json")) or manifest
            name = manifest.get("name", "")

        if name == _EXTENSION_NAME:
            results.append(
                {
                    "browser": "",
                    "profile": profile,
                    "extension_id": ext_id,
                    "version": manifest.get("version", ""),
                    "manifest_version": manifest.get("manifest_version"),
                    "source": source,
                    "path": path,
                }
            )
    return results


def _scan_profile(user_data_dir: str, profile: str, browser: str, visited_ids: set) -> List[Dict]:
    """扫描单个 Profile 的 Extensions 目录 + Preferences + Secure Preferences。"""
    results: List[Dict] = []
    profile_path = os.path.join(user_data_dir, profile)

    ext_root = os.path.join(profile_path, "Extensions")
    if os.path.isdir(ext_root):
        try:
            for ext_id in os.listdir(ext_root):
                ext_dir = os.path.join(ext_root, ext_id)
                if not os.path.isdir(ext_dir):
                    continue
                for version in os.listdir(ext_dir):
                    manifest_path = os.path.join(ext_dir, version, "manifest.json")
                    if not os.path.isfile(manifest_path):
                        continue
                    try:
                        with open(manifest_path, "r", encoding="utf-8") as f:
                            manifest = json.load(f)
                        if manifest.get("name") == _EXTENSION_NAME:
                            key = (browser, ext_id)
                            if key not in visited_ids:
                                visited_ids.add(key)
                                results.append(
                                    {
                                        "browser": browser,
                                        "profile": profile,
                                        "extension_id": ext_id,
                                        "version": version,
                                        "manifest_version": manifest.get("manifest_version"),
                                        "source": "extensions_dir",
                                    }
                                )
                            break
                    except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                        continue
        except OSError:
            pass

    pref_path = os.path.join(profile_path, "Preferences")
    prefs = _parse_preferences_file(pref_path)
    settings = prefs.get("extensions", {}).get("settings", {})
    for r in _match_extension_from_settings(settings, profile, "preferences"):
        key = (browser, r["extension_id"])
        if key not in visited_ids:
            visited_ids.add(key)
            results.append({**r, "browser": browser})

    secure_path = os.path.join(profile_path, "Secure Preferences")
    secure_prefs = _parse_preferences_file(secure_path)
    secure_settings = secure_prefs.get("extensions", {}).get("settings", {})
    for r in _match_extension_from_settings(secure_settings, profile, "secure_preferences"):
        key = (browser, r["extension_id"])
        if key not in visited_ids:
            visited_ids.add(key)
            results.append({**r, "browser": browser})

    return results


def scan_installed_extensions() -> List[Dict]:
    """
    扫描所有支持的浏览器的用户数据目录，查找 RPA Script 扩展。
    返回列表项: {browser, profile, extension_id, version, manifest_version}
    """
    results: List[Dict] = []
    visited_ids: set = set()

    for entry in _get_browser_user_data_dirs():
        browser = entry["browser"]
        user_data_dir = entry["path"]
        for profile in _list_profiles(user_data_dir):
            results.extend(_scan_profile(user_data_dir, profile, browser, visited_ids))

    return results
