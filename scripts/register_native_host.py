"""注册 Native Messaging Host 到 Chrome/Edge。

用法:
  python scripts/register_native_host.py          # 注册
  python scripts/register_native_host.py --unregister  # 卸载

将 com.rpa.host.json 写入磁盘并在注册表中注册。
"""
import sys
import os
import json

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Native Host 配置
HOST_NAME = "com.rpa.host"
HOST_DESC = "RPA Script Native Messaging Host"

# 根据当前 Python 构建命令
PYTHON_EXE = sys.executable
NATIVE_HOST_SCRIPT = os.path.join(_PROJECT_ROOT, "scripts", "native_host.py")
CMD_LINE = f'"{PYTHON_EXE}" "{NATIVE_HOST_SCRIPT}"'

# Chrome 和 Edge 的扩展 ID（自动从 manifest.json 的 key 推导，也可环境变量覆盖）
def _derive_ext_id():
    """从 extension/manifest.json 的 key 推导固定的 Chrome 扩展 ID。"""
    manifest_path = os.path.join(_PROJECT_ROOT, "extension", "manifest.json")
    if os.path.exists(manifest_path):
        import base64
        import hashlib
        with open(manifest_path, encoding="utf-8") as f:
            key_b64 = json.load(f).get("key", "")
        if key_b64:
            key_der = base64.b64decode(key_b64)
            h = hashlib.sha256(key_der).digest()[:16]
            result = []
            for b in h:
                result.append(chr(ord('a') + (b >> 4)))
                result.append(chr(ord('a') + (b & 0x0f)))
            return ''.join(result)
    return ""

CHROME_EXT_ID = os.getenv("RPA_CHROME_EXT_ID", "") or _derive_ext_id()
EDGE_EXT_ID = os.getenv("RPA_EDGE_EXT_ID", "") or CHROME_EXT_ID  # Edge 同 ID 也兼容

ALLOWED_ORIGINS = []
if CHROME_EXT_ID:
    ALLOWED_ORIGINS.append(f"chrome-extension://{CHROME_EXT_ID}/")
if EDGE_EXT_ID:
    ALLOWED_ORIGINS.append(f"extension://{EDGE_EXT_ID}/")

MANIFEST = {
    "name": HOST_NAME,
    "description": HOST_DESC,
    "path": PYTHON_EXE,
    "type": "stdio",
    "allowed_origins": ALLOWED_ORIGINS,
}


def _get_manifest_path():
    return os.path.join(_PROJECT_ROOT, "data", "com.rpa.host.json")


def _register(browser_key: str):
    r"""写注册表: HKCU\Software\{browser_key}\NativeMessagingHosts\{HOST_NAME}"""
    import winreg
    key_path = f"Software\\{browser_key}\\NativeMessagingHosts\\{HOST_NAME}"
    manifest_path = _get_manifest_path()

    # 确保目录和 manifest 文件存在
    os.makedirs(os.path.dirname(manifest_path), exist_ok=True)
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(MANIFEST, f, indent=2, ensure_ascii=False)

    key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, key_path)
    winreg.SetValueEx(key, "", 0, winreg.REG_SZ, manifest_path)
    winreg.CloseKey(key)
    print(f"  [OK] {browser_key} 注册成功")


def _unregister(browser_key: str):
    """删除注册表项。"""
    import winreg
    key_path = f"Software\\{browser_key}\\NativeMessagingHosts\\{HOST_NAME}"
    try:
        winreg.DeleteKey(winreg.HKEY_CURRENT_USER, key_path)
        print(f"  [OK] {browser_key} 已卸载")
    except FileNotFoundError:
        print(f"  [SKIP] {browser_key} 未注册，跳过")


def register_all():
    """注册到所有支持的浏览器。"""
    print("注册 RPA Native Messaging Host...")
    _register("Google\\Chrome")
    _register("Microsoft\\Edge")
    print(f"\nManifest: {_get_manifest_path()}")
    print(f"命令:     {CMD_LINE}")
    print("Chrome/Edge 扩展调用 chrome.runtime.connectNative('com.rpa.host') 即可连接。")


def unregister_all():
    """从所有浏览器卸载。"""
    print("卸载 RPA Native Messaging Host...")
    _unregister("Google\\Chrome")
    _unregister("Microsoft\\Edge")


if __name__ == "__main__":
    if "--unregister" in sys.argv:
        unregister_all()
    else:
        register_all()
