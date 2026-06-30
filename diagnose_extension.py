"""
诊断脚本：查看浏览器 Extensions 目录实际结构
直接运行即可：python diagnose_extension.py
"""

import json
import os

_EXTENSION_NAME = "RPA Script Browser Agent"
_TARGET_ID = "bokpcehmmkemnfhjbnpfphpblcbfcpce"

def main():
    local_app_data = os.environ.get("LOCALAPPDATA", os.path.expandvars(r"%LOCALAPPDATA%"))
    print(f"LOCALAPPDATA: {local_app_data}\n")

    browsers = [
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

    for browser_name, user_data_dir in browsers:
        print(f"=== {browser_name.upper()} ===")
        print(f"User Data Dir: {user_data_dir}")
        if not os.path.isdir(user_data_dir):
            print("  目录不存在\n")
            continue

        profiles = []
        try:
            for name in os.listdir(user_data_dir):
                profile_path = os.path.join(user_data_dir, name)
                if not os.path.isdir(profile_path):
                    continue
                if os.path.isfile(os.path.join(profile_path, "Preferences")) or os.path.isdir(
                    os.path.join(profile_path, "Extensions")
                ):
                    profiles.append(name)
        except OSError:
            pass

        print(f"  Profiles: {profiles}")

        for profile in profiles:
            profile_path = os.path.join(user_data_dir, profile)
            print(f"\n  Profile: {profile}")

            # 1) Extensions 目录
            ext_root = os.path.join(profile_path, "Extensions")
            if os.path.isdir(ext_root):
                print(f"    Extensions dir: {ext_root}")
                found_in_ext = False
                for ext_id in os.listdir(ext_root):
                    ext_dir = os.path.join(ext_root, ext_id)
                    if not os.path.isdir(ext_dir):
                        continue
                    for version in os.listdir(ext_dir):
                        manifest_path = os.path.join(ext_dir, version, "manifest.json")
                        if os.path.isfile(manifest_path):
                            try:
                                with open(manifest_path, "r", encoding="utf-8") as f:
                                    manifest = json.load(f)
                                name = manifest.get("name", "")
                                if name == _EXTENSION_NAME:
                                    print(
                                    f"      [MATCH] ext_id={ext_id}, version={version}, "
                                    f"mv={manifest.get('manifest_version')}"
                                )
                                    found_in_ext = True
                                elif ext_id == _TARGET_ID:
                                    print(f"      [TARGET_ID] ext_id={ext_id}, name={name}, version={version}")
                            except Exception as e:
                                print(f"      [error] ext_id={ext_id}, err={e}")
                if not found_in_ext:
                    print(f"    Extensions 目录下未找到 {_EXTENSION_NAME}")
            else:
                print("    无 Extensions 目录")

            # 2) Preferences 文件
            pref_path = os.path.join(profile_path, "Preferences")
            if os.path.isfile(pref_path):
                try:
                    with open(pref_path, "r", encoding="utf-8", errors="ignore") as f:
                        prefs = json.load(f)
                    settings = prefs.get("extensions", {}).get("settings", {})
                    print(f"    Preferences settings count: {len(settings)}")

                    found_in_prefs = False
                    for ext_id, info in settings.items():
                        manifest = info.get("manifest", {})
                        name = manifest.get("name", "")
                        path = info.get("path", "")
                        location = info.get("location", "?")

                        if ext_id == _TARGET_ID:
                            print(f"    [TARGET_ID] {ext_id}: name={name!r}, path={path!r}, location={location}")
                            found_in_prefs = True

                        if name == _EXTENSION_NAME:
                            print(
                                f"    [PREFS MATCH] ext_id={ext_id}, "
                                f"version={manifest.get('version')}, path={path!r}, location={location}"
                            )
                            found_in_prefs = True

                        # 未打包扩展：manifest 无 name 但 path 存在
                        if not name and path and ext_id == _TARGET_ID:
                            manifest_path = os.path.join(path, "manifest.json")
                            if os.path.isfile(manifest_path):
                                try:
                                    with open(manifest_path, "r", encoding="utf-8") as f:
                                        m = json.load(f)
                                    if m.get("name") == _EXTENSION_NAME:
                                        print(
                                    f"    [PREFS PATH MATCH] ext_id={ext_id}, "
                                    f"path={path!r}, mv={m.get('manifest_version')}"
                                )
                                        found_in_prefs = True
                                except Exception:
                                    pass

                    if not found_in_prefs:
                        print(f"    Preferences 中未找到 {_EXTENSION_NAME} 或 {_TARGET_ID}")
                except Exception as e:
                    print(f"    Preferences 读取失败: {e}")
            else:
                print("    无 Preferences 文件")
        print()

if __name__ == "__main__":
    main()
