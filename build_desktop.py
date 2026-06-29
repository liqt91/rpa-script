"""
RPA Script 桌面应用打包脚本
用法: python build_desktop.py
"""

import os
import sys
import shutil
import subprocess

# ---------------------------------------------------------------------------
# 前置检查
# ---------------------------------------------------------------------------

REPO_ROOT = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(REPO_ROOT, "src", "ui", "workflow-editor")
STATIC_DIR = os.path.join(REPO_ROOT, "src", "runtime", "static", "workflow-editor")
BUILD_DIR = os.path.join(REPO_ROOT, "build", "desktop")
DIST_DIR = os.path.join(REPO_ROOT, "dist", "desktop")


def run(cmd, cwd=None, check=True):
    print(f"\n>>> {' '.join(cmd)}")
    kwargs = {"cwd": cwd, "check": check}
    if sys.platform == "win32":
        kwargs["shell"] = True
    result = subprocess.run(cmd, **kwargs)
    return result


# ---------------------------------------------------------------------------
# 1. 构建前端
# ---------------------------------------------------------------------------

def build_frontend():
    print("=" * 60)
    print("Step 1: Build frontend")
    print("=" * 60)

    node_modules = os.path.join(FRONTEND_DIR, "node_modules")
    if not os.path.isdir(node_modules):
        run(["npm", "install"], cwd=FRONTEND_DIR)

    run(["npm", "run", "build"], cwd=FRONTEND_DIR)

    if not os.path.isfile(os.path.join(STATIC_DIR, "index.html")):
        print("ERROR: frontend build failed — index.html not found")
        sys.exit(1)

    print("Frontend build OK")


# ---------------------------------------------------------------------------
# 2. PyInstaller 打包
# ---------------------------------------------------------------------------

def build_executable():
    print("=" * 60)
    print("Step 2: PyInstaller bundle")
    print("=" * 60)

    # 清理旧构建
    for d in (BUILD_DIR, DIST_DIR):
        if os.path.isdir(d):
            shutil.rmtree(d)

    # 入口脚本（临时）—— 确保 src 包在 PYTHONPATH 中
    entry_path = os.path.join(REPO_ROOT, "_desktop_entry.py")
    with open(entry_path, "w", encoding="utf-8") as f:
        f.write(
            f'''import sys
import os
sys.path.insert(0, {repr(REPO_ROOT)})
os.chdir(os.path.dirname(os.path.abspath(__file__)))
from src.desktop import main
if __name__ == "__main__":
    main()
'''
        )

    # 数据文件映射: (源路径, 目标路径在打包后)
    datas = [
        # 前端静态资源
        (os.path.join(REPO_ROOT, "src", "runtime", "static"), "src/runtime/static"),
        # Jinja2 模板
        (os.path.join(REPO_ROOT, "src", "runtime", "admin_templates"), "src/runtime/admin_templates"),
        # 任务脚本（通过文件系统动态遍历加载）
        (os.path.join(REPO_ROOT, "src", "service", "jobs"), "src/service/jobs"),
        # 浏览器插件（打包进 exe 运行时目录）
        (os.path.join(REPO_ROOT, "extension"), "extension"),
        # 版本文件（如果存在）
        (os.path.join(REPO_ROOT, "VERSION"), "VERSION"),
    ]

    # 过滤不存在的路径
    datas = [(src, dst) for src, dst in datas if os.path.exists(src)]

    # hidden imports — FastAPI / SQLAlchemy / Jinja2 动态导入较多
    hidden = [
        "src.runtime.main",
        "src.runtime.auth",
        "src.runtime.admin_router",
        "src.runtime.routers.auth_router",
        "src.runtime.routers.tasks_router",
        "src.runtime.routers.workflows_router",
        "src.runtime.routers.elements_router",
        "src.runtime.routers.extension_router",
        "src.runtime.routers.commands_router",
        "src.runtime.routers.data_tables_router",
        "src.runtime.routers.other_routers",
        "src.runtime.workflow.commands",
        "src.runtime.dify_client",
        "src.repo.runtime_models",
        "src.repo.migrations",
        "src.config.settings",
        "src.config.runtime_config",
        "jinja2",
        "jinja2.ext",
        "passlib.handlers.bcrypt",
        "uvicorn.logging",
        "uvicorn.loops.auto",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets.auto",
        "sqlalchemy.sql.default_comparator",
        "sqlalchemy.ext.baked",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--name", "RPA-Script",
        "--onefile",
        "--console",
        "--noconfirm",
        "--clean",
        "--workpath", BUILD_DIR,
        "--distpath", DIST_DIR,
        "--specpath", BUILD_DIR,
        # 图标（如果有的话）
        # "--icon", os.path.join(REPO_ROOT, "extension", "icons", "icon128.png"),
    ]

    for src, dst in datas:
        cmd.extend(["--add-data", f"{src}{os.pathsep}{dst}"])

    for mod in hidden:
        cmd.extend(["--hidden-import", mod])

    cmd.append(entry_path)

    run(cmd, cwd=REPO_ROOT)

    # 清理临时入口
    if os.path.exists(entry_path):
        os.remove(entry_path)

    exe_path = os.path.join(DIST_DIR, "RPA-Script.exe")
    if not os.path.isfile(exe_path):
        print("ERROR: PyInstaller did not produce the expected exe")
        sys.exit(1)

    print(f"\nExecutable: {exe_path}")
    print(f"Size: {os.path.getsize(exe_path) / 1024 / 1024:.1f} MB")

    # 将浏览器插件目录复制到输出目录，方便与 exe 一起分发
    ext_src = os.path.join(REPO_ROOT, "extension")
    ext_dst = os.path.join(DIST_DIR, "extension")
    if os.path.isdir(ext_src):
        if os.path.isdir(ext_dst):
            shutil.rmtree(ext_dst)
        shutil.copytree(ext_src, ext_dst, ignore=shutil.ignore_patterns("*.map"))
        print(f"Extension copied to: {ext_dst}")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    build_frontend()
    build_executable()
    print("\n" + "=" * 60)
    print("Build complete. Output: dist/desktop/RPA-Script.exe")
    print("Extension: dist/desktop/extension/")
    print("=" * 60)
